#!/usr/bin/env python3
"""Trace the log activity leading up to a specific error in ezEML logs.

Given a search pattern that identifies a particular error line, this module
finds the matching line and returns every log line for the same process (PID)
from the nearest preceding ``**** INCOMING REQUEST:`` up to and including the
matched line.  The result is a single, self-contained snippet that shows the
exact sequence of steps the server executed before the error occurred.

Typical usage
-------------
Run from the command line::

    python trace_request.py webapp/ezeml-log.txt \
        --pattern "500 Internal Server Error"

This prints the most recent request trace that contains a line matching the
pattern.  Use ``--occurrence`` to select an earlier match (1 = oldest, -1 or
``last`` = most recent).

Programmatic usage::

    from trace_request import get_request_trace
    lines = get_request_trace("webapp/ezeml-log.txt", "500 Internal Server Error")
    for line in lines:
        print(line)
"""

import argparse
import re
from typing import Optional

# Re-use the same header / request regexes as summarize_error_log so that both
# tools agree on what constitutes a timestamped log record and an incoming
# request marker.
LOG_HEADER_RE = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}) "
    r"\[PID (?P<pid>\d+)\] "
    r"\[(?P<level>[A-Z]+)\]"
    r"(?: \[USER: (?P<user>[^\]]+)\])? "
    r"(?P<rest>.*)$"
)

REQUEST_RE = re.compile(r"\*\*\*\* INCOMING REQUEST:")


def get_request_trace(
    path: str,
    pattern: str,
    ignore_case: bool = True,
    occurrence: int = -1,
    literal: bool = False,
) -> list[str]:
    """Return the log lines from the nearest INCOMING REQUEST to a pattern match.

    Scans *path* and collects every line that matches *pattern*.  For each
    match the function assembles the sequence of log lines belonging to the
    same PID that starts at the closest preceding ``**** INCOMING REQUEST:``
    line and ends at (and includes) the matched line.  Continuation lines such
    as tracebacks are included because they carry no PID header of their own
    and are therefore always attributed to the preceding PID.

    The pattern is matched against the **full raw log line** so that users can
    paste any portion of a log entry — including timestamp, PID, level, and
    user fields — as their search string.

    Parameters
    ----------
    path:
        Path to the log file.
    pattern:
        Search string used to identify the error line of interest.  Treated as
        a regular expression by default; pass ``literal=True`` to search for
        the exact string (regex metacharacters such as ``[``, ``]``, and ``.``
        are automatically escaped).
    ignore_case:
        When ``True`` (the default) the pattern is matched case-insensitively.
    occurrence:
        Which match to return when the pattern appears more than once.
        ``1`` selects the first (oldest) occurrence, ``2`` the second, and so
        on.  Negative indices count from the end: ``-1`` (the default) selects
        the last (most recent) occurrence.
    literal:
        When ``True`` the pattern is treated as a plain fixed string rather
        than a regular expression.  This is the safe choice when pasting a
        real log line as the search term.

    Returns
    -------
    list[str]
        The log lines that form the trace, ordered chronologically from the
        INCOMING REQUEST line to the matched error line.  Returns an empty list
        when no line in the file matches *pattern*.
    """
    flags = re.IGNORECASE if ignore_case else 0
    search_pattern = re.escape(pattern) if literal else pattern
    error_re = re.compile(search_pattern, flags)

    # Each entry in *all_traces* is the complete line buffer for one match.
    all_traces: list[list[str]] = []

    # Per-PID buffer that resets each time an INCOMING REQUEST is seen for
    # that PID.  We always append every line to the buffer of the "current"
    # PID so that continuation lines (tracebacks, etc.) are captured.
    buffer_by_pid: dict[str, list[str]] = {}
    current_pid: Optional[str] = None

    with open(path, "rb") as fh:
        for raw_line in fh:
            line = raw_line.decode("utf-8", errors="replace").rstrip("\n")
            header_match = LOG_HEADER_RE.match(line)

            if header_match:
                current_pid = header_match.group("pid")
                rest = header_match.group("rest")

                # Strip the optional "logger_name -> " prefix to get the bare
                # message, which is what we test against the search pattern.
                message = rest.split(" -> ", 1)[1] if " -> " in rest else rest

                if REQUEST_RE.search(message):
                    # Start a fresh buffer for this PID from the request line.
                    buffer_by_pid[current_pid] = [line]
                else:
                    # Append to this PID's active buffer (create one if it
                    # doesn't exist yet — the request may have been before the
                    # beginning of the file).
                    if current_pid not in buffer_by_pid:
                        buffer_by_pid[current_pid] = []
                    buffer_by_pid[current_pid].append(line)

                    if error_re.search(line):
                        # Snapshot the buffer; keep it alive in case further
                        # lines continue (e.g. a second error from same PID).
                        all_traces.append(list(buffer_by_pid[current_pid]))
            else:
                # Continuation line (traceback frame, etc.) — append to the
                # current PID's buffer so tracebacks are part of the trace.
                if current_pid is not None:
                    if current_pid not in buffer_by_pid:
                        buffer_by_pid[current_pid] = []
                    buffer_by_pid[current_pid].append(line)

    if not all_traces:
        return []

    # Positive occurrence values are 1-based (1 = first/oldest).
    # Negative values use Python's native end-relative indexing (-1 = last).
    try:
        if occurrence > 0:
            return all_traces[occurrence - 1]
        return all_traces[occurrence]
    except IndexError:
        return all_traces[-1]


def print_trace(trace: list[str]) -> None:
    """Print a request trace to stdout."""
    if not trace:
        print("No matching line found in the log.")
        return
    for line in trace:
        print(line)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Show the log activity leading up to a specific error in ezEML logs. "
            "Finds the line matching --pattern and prints every log line for "
            "that process from the nearest preceding "
            "'**** INCOMING REQUEST:' through the matched line."
        )
    )
    parser.add_argument(
        "log_file",
        nargs="?",
        default="webapp/ezeml-log.txt",
        help="Path to log file (default: webapp/ezeml-log.txt)",
    )
    parser.add_argument(
        "--pattern",
        default=r"500 Internal Server Error",
        help="Regex pattern identifying the error line of interest (default: '500 Internal Server Error')",
    )
    parser.add_argument(
        "--literal",
        action="store_true",
        help=(
            "Treat --pattern as a plain fixed string rather than a regular "
            "expression. Use this when the search string contains special "
            "characters such as brackets, dots, or parentheses "
            "(e.g. when pasting a raw log line as the search term)."
        ),
    )
    parser.add_argument(
        "--case-sensitive",
        action="store_true",
        help="Use case-sensitive matching for --pattern",
    )
    parser.add_argument(
        "--occurrence",
        type=int,
        default=-1,
        help=(
            "Which match to display when the pattern appears more than once. "
            "1 = first (oldest), -1 = last (most recent, default). "
            "Negative values count from the end."
        ),
    )

    args = parser.parse_args()
    trace = get_request_trace(
        args.log_file,
        args.pattern,
        ignore_case=not args.case_sensitive,
        occurrence=args.occurrence,
        literal=args.literal,
    )
    print_trace(trace)


if __name__ == "__main__":
    main()
