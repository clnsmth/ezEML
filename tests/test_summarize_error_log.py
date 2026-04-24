"""Tests for summarize_error_log.py – preceding-context capture and display."""

import io
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from summarize_error_log import parse_log, print_traces, summarize, trace_to_request  # noqa: E402

# ---------------------------------------------------------------------------
# Sample log fragments
# ---------------------------------------------------------------------------

SAMPLE_LOG_PRECEDING = """\
2026-04-17 06:43:03,560 [PID 2447] [ERROR] webapp -> Exception on /eml/check_data_tables [POST]
2026-04-17 06:43:03,561 [PID 2447] [ERROR] webapp -> 500 Internal Server Error
""".encode()

SAMPLE_LOG_NO_PRECEDING = """\
2026-04-17 07:00:00,000 [PID 9999] [ERROR] webapp -> 500 Internal Server Error
""".encode()

SAMPLE_LOG_TRACEBACK_BETWEEN = """\
2026-04-17 08:00:00,000 [PID 1111] [INFO] webapp -> **** INCOMING REQUEST: /eml/save [POST]
2026-04-17 08:00:00,100 [PID 1111] [ERROR] webapp -> Something went wrong
Traceback (most recent call last):
  File "/webapp/views.py", line 42, in save
    do_save()
ValueError: bad value
2026-04-17 08:00:00,200 [PID 1111] [ERROR] webapp -> 500 Internal Server Error
""".encode()

SAMPLE_LOG_DIFFERENT_PID = """\
2026-04-17 09:00:00,000 [PID 1234] [INFO] webapp -> **** INCOMING REQUEST: /eml/load [GET]
2026-04-17 09:00:01,000 [PID 5678] [ERROR] webapp -> 500 Internal Server Error
""".encode()


def _write_tmp(content: bytes) -> str:
    """Write *content* to a named temp file and return its path."""
    fd, path = tempfile.mkstemp(suffix=".log")
    os.write(fd, content)
    os.close(fd)
    return path


# ---------------------------------------------------------------------------
# parse_log tests
# ---------------------------------------------------------------------------


def test_preceding_line_same_pid():
    """Preceding timestamped record for the same PID is captured."""
    path = _write_tmp(SAMPLE_LOG_PRECEDING)
    try:
        events = parse_log(path, r"500 Internal Server Error", ignore_case=False)
    finally:
        os.unlink(path)

    assert len(events) == 1
    event = events[0]
    assert event.preceding_line is not None
    assert "Exception on /eml/check_data_tables [POST]" in event.preceding_line


def test_no_preceding_line_when_first_record():
    """When the error is the very first record for a PID, preceding_line is None."""
    path = _write_tmp(SAMPLE_LOG_NO_PRECEDING)
    try:
        events = parse_log(path, r"500 Internal Server Error", ignore_case=False)
    finally:
        os.unlink(path)

    assert len(events) == 1
    assert events[0].preceding_line is None


def test_preceding_line_skips_traceback_continuation():
    """When a traceback falls between two timestamped records the preceding
    line reported is the last *timestamped* record for that PID, not a
    traceback continuation line."""
    path = _write_tmp(SAMPLE_LOG_TRACEBACK_BETWEEN)
    try:
        events = parse_log(path, r"500 Internal Server Error", ignore_case=False)
    finally:
        os.unlink(path)

    assert len(events) == 1
    event = events[0]
    # The preceding line must be a timestamped record, not a traceback line.
    assert event.preceding_line is not None
    assert event.preceding_line.startswith("2026-04-17")
    assert "Something went wrong" in event.preceding_line
    assert "Traceback" not in event.preceding_line
    assert "File " not in event.preceding_line


def test_no_preceding_line_for_different_pid():
    """A record from a different PID does not appear as the preceding line."""
    path = _write_tmp(SAMPLE_LOG_DIFFERENT_PID)
    try:
        events = parse_log(path, r"500 Internal Server Error", ignore_case=False)
    finally:
        os.unlink(path)

    assert len(events) == 1
    # PID 5678 has never been seen before, so preceding_line should be None.
    assert events[0].preceding_line is None


# ---------------------------------------------------------------------------
# summarize() output tests
# ---------------------------------------------------------------------------


def _capture_summarize(events, show_recent=10, show_traceback_lines=0, top_n=5):
    """Run summarize() and return captured stdout as a string."""
    captured = io.StringIO()
    old_stdout = sys.stdout
    sys.stdout = captured
    try:
        summarize(
            events=events,
            top_n=top_n,
            show_recent=show_recent,
            show_traceback_lines=show_traceback_lines,
        )
    finally:
        sys.stdout = old_stdout
    return captured.getvalue()


def test_summarize_prints_preceding_line():
    """summarize() prints a 'Prev' line when preceding_line is set."""
    path = _write_tmp(SAMPLE_LOG_PRECEDING)
    try:
        events = parse_log(path, r"500 Internal Server Error", ignore_case=False)
    finally:
        os.unlink(path)

    output = _capture_summarize(events)
    assert "Prev" in output
    assert "Exception on /eml/check_data_tables [POST]" in output


def test_summarize_omits_preceding_line_when_none():
    """summarize() does not print a 'Prev' line when preceding_line is None."""
    path = _write_tmp(SAMPLE_LOG_NO_PRECEDING)
    try:
        events = parse_log(path, r"500 Internal Server Error", ignore_case=False)
    finally:
        os.unlink(path)

    output = _capture_summarize(events)
    assert "Prev" not in output


def test_summarize_preceding_line_with_traceback_enabled():
    """Preceding line display is unaffected by traceback display being enabled."""
    path = _write_tmp(SAMPLE_LOG_PRECEDING)
    try:
        events = parse_log(path, r"500 Internal Server Error", ignore_case=False)
    finally:
        os.unlink(path)

    output_no_tb = _capture_summarize(events, show_traceback_lines=0)
    output_with_tb = _capture_summarize(events, show_traceback_lines=5)

    for output in (output_no_tb, output_with_tb):
        assert "Prev" in output
        assert "Exception on /eml/check_data_tables [POST]" in output


def test_summarize_no_route_in_output():
    """summarize() does not print 'Top routes' section or per-event Route field."""
    path = _write_tmp(SAMPLE_LOG_PRECEDING)
    try:
        events = parse_log(path, r"500 Internal Server Error", ignore_case=False)
    finally:
        os.unlink(path)

    output = _capture_summarize(events)
    assert "Top routes" not in output
    assert "Route    :" not in output


# ---------------------------------------------------------------------------
# trace_to_request tests
# ---------------------------------------------------------------------------

SAMPLE_LOG_TRACE_BASIC = """\
2026-04-17 10:00:00,000 [PID 100] [INFO] webapp -> **** INCOMING REQUEST: /eml/save [POST]
2026-04-17 10:00:00,100 [PID 100] [INFO] webapp -> step A
2026-04-17 10:00:00,200 [PID 100] [ERROR] webapp -> 500 Internal Server Error
""".encode()

SAMPLE_LOG_TRACE_MULTI_PID = """\
2026-04-17 11:00:00,000 [PID 200] [INFO] webapp -> **** INCOMING REQUEST: /eml/load [GET]
2026-04-17 11:00:00,050 [PID 300] [INFO] webapp -> **** INCOMING REQUEST: /eml/save [POST]
2026-04-17 11:00:00,100 [PID 200] [INFO] webapp -> step A pid 200
2026-04-17 11:00:00,150 [PID 300] [INFO] webapp -> step A pid 300
2026-04-17 11:00:00,200 [PID 200] [ERROR] webapp -> 500 Internal Server Error
""".encode()

SAMPLE_LOG_TRACE_NO_REQUEST = """\
2026-04-17 12:00:00,000 [PID 400] [ERROR] webapp -> 500 Internal Server Error
""".encode()

SAMPLE_LOG_TRACE_WITH_TRACEBACK = """\
2026-04-17 13:00:00,000 [PID 500] [INFO] webapp -> **** INCOMING REQUEST: /eml/check [POST]
2026-04-17 13:00:00,100 [PID 500] [ERROR] webapp -> Something went wrong
Traceback (most recent call last):
  File "/webapp/views.py", line 10, in check
    do_check()
ValueError: bad input
2026-04-17 13:00:00,200 [PID 500] [ERROR] webapp -> 500 Internal Server Error
""".encode()

SAMPLE_LOG_TRACE_MULTI_MATCHES = """\
2026-04-17 14:00:00,000 [PID 600] [INFO] webapp -> **** INCOMING REQUEST: /eml/a [POST]
2026-04-17 14:00:00,100 [PID 600] [ERROR] webapp -> 500 Internal Server Error
2026-04-17 14:00:01,000 [PID 600] [INFO] webapp -> **** INCOMING REQUEST: /eml/b [POST]
2026-04-17 14:00:01,100 [PID 600] [INFO] webapp -> step B
2026-04-17 14:00:01,200 [PID 600] [ERROR] webapp -> 500 Internal Server Error
""".encode()


def test_trace_basic_sequence():
    """trace_to_request returns lines from INCOMING REQUEST through the match."""
    path = _write_tmp(SAMPLE_LOG_TRACE_BASIC)
    try:
        traces = trace_to_request(path, r"500 Internal Server Error", ignore_case=False)
    finally:
        os.unlink(path)

    assert len(traces) == 1
    trace = traces[0]
    assert any("INCOMING REQUEST" in line for line in trace)
    assert any("step A" in line for line in trace)
    assert any("500 Internal Server Error" in line for line in trace)
    # INCOMING REQUEST must come before the error
    request_idx = next(i for i, l in enumerate(trace) if "INCOMING REQUEST" in l)
    error_idx = next(i for i, l in enumerate(trace) if "500 Internal Server Error" in l)
    assert request_idx < error_idx


def test_trace_only_same_pid_lines():
    """trace_to_request excludes lines from other PIDs."""
    path = _write_tmp(SAMPLE_LOG_TRACE_MULTI_PID)
    try:
        traces = trace_to_request(path, r"500 Internal Server Error", ignore_case=False)
    finally:
        os.unlink(path)

    assert len(traces) == 1
    trace = traces[0]
    for line in trace:
        assert "PID 300" not in line, "PID 300 line should not appear in PID 200 trace"
    assert any("PID 200" in line for line in trace)


def test_trace_no_preceding_request():
    """When no INCOMING REQUEST precedes the match, trace contains only the match."""
    path = _write_tmp(SAMPLE_LOG_TRACE_NO_REQUEST)
    try:
        traces = trace_to_request(path, r"500 Internal Server Error", ignore_case=False)
    finally:
        os.unlink(path)

    assert len(traces) == 1
    trace = traces[0]
    assert len(trace) == 1
    assert "500 Internal Server Error" in trace[0]
    assert "INCOMING REQUEST" not in trace[0]


def test_trace_includes_traceback_continuation():
    """Traceback continuation lines (no timestamp) are included in the trace."""
    path = _write_tmp(SAMPLE_LOG_TRACE_WITH_TRACEBACK)
    try:
        traces = trace_to_request(path, r"500 Internal Server Error", ignore_case=False)
    finally:
        os.unlink(path)

    assert len(traces) == 1
    trace = traces[0]
    assert any("INCOMING REQUEST" in line for line in trace)
    assert any("Traceback" in line for line in trace)
    assert any("ValueError" in line for line in trace)
    assert any("500 Internal Server Error" in line for line in trace)


def test_trace_multiple_matches_separate_traces():
    """Each distinct INCOMING REQUEST → match pair produces its own trace."""
    path = _write_tmp(SAMPLE_LOG_TRACE_MULTI_MATCHES)
    try:
        traces = trace_to_request(path, r"500 Internal Server Error", ignore_case=False)
    finally:
        os.unlink(path)

    assert len(traces) == 2
    # First trace should reference /eml/a
    assert any("/eml/a" in line for line in traces[0])
    # Second trace should reference /eml/b
    assert any("/eml/b" in line for line in traces[1])


def _capture_print_traces(traces, max_traces=10):
    """Run print_traces() and return captured stdout as a string."""
    captured = io.StringIO()
    old_stdout = sys.stdout
    sys.stdout = captured
    try:
        print_traces(traces, max_traces)
    finally:
        sys.stdout = old_stdout
    return captured.getvalue()


def test_print_traces_no_matches():
    """print_traces() reports when there are no traces."""
    output = _capture_print_traces([])
    assert "No matching events found" in output


def test_print_traces_output_format():
    """print_traces() labels each trace and includes all lines."""
    traces = [
        ["line A1", "line A2"],
        ["line B1", "line B2", "line B3"],
    ]
    output = _capture_print_traces(traces, max_traces=10)
    assert "Trace 1 of 2" in output
    assert "Trace 2 of 2" in output
    assert "line A1" in output
    assert "line B3" in output


def test_print_traces_max_traces_limits_output():
    """print_traces() respects max_traces and shows only the most recent."""
    traces = [["line%d" % i] for i in range(5)]
    output = _capture_print_traces(traces, max_traces=2)
    assert "Trace 1 of 2" in output
    assert "line4" in output  # most recent
    assert "line0" not in output  # older ones omitted
