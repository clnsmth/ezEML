#!/usr/bin/env python3
"""Summarize error occurrences in ezEML logs from the command line."""

import argparse
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta
import re
from typing import Optional
from urllib.parse import urlparse


LOG_HEADER_RE = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}) "
    r"\[PID (?P<pid>\d+)\] "
    r"\[(?P<level>[A-Z]+)\]"
    r"(?: \[USER: (?P<user>[^\]]+)\])? "
    r"(?P<rest>.*)$"
)

REQUEST_RE = re.compile(r"\*\*\*\* INCOMING REQUEST:\s+(?P<url>\S+)\s+\[(?P<method>[A-Z]+)\]")
TRACE_FRAME_RE = re.compile(r'^\s*File "(?P<file>[^"]+)", line (?P<line>\d+), in (?P<func>.+)$')
# Correlate request/traceback context close in time to the logged error event.
MAX_CORRELATION_WINDOW = timedelta(minutes=30)
PREFERRED_PATH_PATTERNS = ("/webapp/", "/ezeml/")
GENERIC_LOGGER_NAME = "webapp"


@dataclass
class RequestContext:
    timestamp: datetime
    route: str


@dataclass
class TracebackContext:
    timestamp: Optional[datetime]
    pid: Optional[str]
    lines: list[str]
    function: str
    exception: str


@dataclass
class ErrorEvent:
    timestamp: datetime
    pid: str
    user: str
    route: str
    function: str
    exception: str
    status_message: str
    traceback_lines: list[str]
    preceding_line: Optional[str] = None


def parse_timestamp(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%d %H:%M:%S,%f")


def parse_traceback(traceback_lines: list[str]) -> tuple[str, str]:
    frames = []
    for line in traceback_lines:
        match = TRACE_FRAME_RE.match(line)
        if match:
            frames.append((match.group("file"), match.group("func")))

    function = "unknown"
    if frames:
        preferred = [frame for frame in frames if any(pattern in frame[0].lower() for pattern in PREFERRED_PATH_PATTERNS)]
        chosen = preferred[-1] if preferred else frames[-1]
        function = f"{chosen[1]} ({chosen[0]})"

    exception = "unknown"
    for line in reversed(traceback_lines):
        cleaned = line.strip()
        if cleaned:
            exception = cleaned
            break

    return function, exception


def normalize_route(url: str, method: str) -> str:
    parsed = urlparse(url)
    if parsed.path:
        path = parsed.path
        if parsed.query:
            path = f"{path}?{parsed.query}"
    else:
        path = url
    return f"{method} {path}"


def print_top(title: str, counts: Counter, top_n: int) -> None:
    print(f"\n{title}:")
    if not counts:
        print("  (none)")
        return
    for key, count in counts.most_common(top_n):
        print(f"  {count:>4}  {key}")


def parse_log(path: str, error_pattern: str, ignore_case: bool) -> list[ErrorEvent]:
    flags = re.IGNORECASE if ignore_case else 0
    error_re = re.compile(error_pattern, flags)

    events: list[ErrorEvent] = []
    last_request_by_pid: dict[str, RequestContext] = {}
    last_traceback_by_pid: dict[str, TracebackContext] = {}
    last_timestamped_record_by_pid: dict[str, str] = {}

    traceback_buffer: list[str] = []
    traceback_context_ts: Optional[datetime] = None
    traceback_context_pid: Optional[str] = None

    current_ts: Optional[datetime] = None
    current_pid: Optional[str] = None

    def finalize_traceback_if_needed() -> None:
        nonlocal traceback_buffer, traceback_context_ts, traceback_context_pid
        if not traceback_buffer:
            return
        function, exception = parse_traceback(traceback_buffer)
        if traceback_context_pid:
            last_traceback_by_pid[traceback_context_pid] = TracebackContext(
                timestamp=traceback_context_ts,
                pid=traceback_context_pid,
                lines=traceback_buffer[:],
                function=function,
                exception=exception,
            )
        traceback_buffer = []
        traceback_context_ts = None
        traceback_context_pid = None

    with open(path, "rb") as infile:
        for raw_line in infile:
            line = raw_line.decode("utf-8", errors="replace").rstrip("\n")
            header_match = LOG_HEADER_RE.match(line)

            if header_match:
                finalize_traceback_if_needed()

                current_ts = parse_timestamp(header_match.group("timestamp"))
                current_pid = header_match.group("pid")
                user = header_match.group("user") or "unknown"
                rest = header_match.group("rest")

                # Capture the preceding timestamped record for this PID before
                # updating the dict with the current line.
                preceding_line = last_timestamped_record_by_pid.get(current_pid)

                logger_name = ""
                message = rest
                if " -> " in rest:
                    logger_name, message = rest.split(" -> ", 1)

                request_match = REQUEST_RE.search(message)
                if request_match:
                    route = normalize_route(request_match.group("url"), request_match.group("method"))
                    last_request_by_pid[current_pid] = RequestContext(timestamp=current_ts, route=route)

                if error_re.search(message):
                    route = "unknown"
                    req_ctx = last_request_by_pid.get(current_pid)
                    if req_ctx and current_ts - req_ctx.timestamp <= MAX_CORRELATION_WINDOW:
                        route = req_ctx.route

                    tb_ctx = last_traceback_by_pid.get(current_pid)
                    function = "unknown"
                    exception = message
                    traceback_lines: list[str] = []
                    used_traceback_context = False
                    if tb_ctx and tb_ctx.timestamp and current_ts - tb_ctx.timestamp <= MAX_CORRELATION_WINDOW:
                        used_traceback_context = True
                        function = tb_ctx.function
                        exception = tb_ctx.exception
                        traceback_lines = tb_ctx.lines

                    # Keep traceback-derived function context when logger is generic.
                    if logger_name and logger_name != GENERIC_LOGGER_NAME and not used_traceback_context:
                        function = logger_name

                    events.append(
                        ErrorEvent(
                            timestamp=current_ts,
                            pid=current_pid,
                            user=user,
                            route=route,
                            function=function,
                            exception=exception,
                            status_message=message,
                            traceback_lines=traceback_lines,
                            preceding_line=preceding_line,
                        )
                    )

                # Update the last-seen timestamped record for this PID.
                last_timestamped_record_by_pid[current_pid] = line
                continue

            if line.startswith("Traceback (most recent call last):"):
                traceback_buffer = [line]
                traceback_context_ts = current_ts
                traceback_context_pid = current_pid
                continue

            if traceback_buffer:
                traceback_buffer.append(line)

    finalize_traceback_if_needed()
    return events


def summarize(
    events: list[ErrorEvent],
    top_n: int,
    show_recent: int,
    show_traceback_lines: int,
) -> None:
    if not events:
        print("No matching errors were found.")
        return

    first_ts = events[0].timestamp
    last_ts = events[-1].timestamp

    by_route = Counter(event.route for event in events)
    by_function = Counter(event.function for event in events)
    by_exception = Counter(event.exception for event in events)
    by_day = Counter(event.timestamp.strftime("%Y-%m-%d") for event in events)

    now = last_ts
    in_last_24h = 0
    in_prev_24h = 0
    in_last_7d = 0
    in_prev_7d = 0
    for event in events:
        age = now - event.timestamp
        if age <= timedelta(hours=24):
            in_last_24h += 1
        elif age <= timedelta(hours=48):
            in_prev_24h += 1

        if age <= timedelta(days=7):
            in_last_7d += 1
        elif age <= timedelta(days=14):
            in_prev_7d += 1

    print(f"Matched errors: {len(events)}")
    print(f"Time range: {first_ts} to {last_ts}")
    print(f"Last 24h: {in_last_24h} (previous 24h: {in_prev_24h})")
    print(f"Last 7d : {in_last_7d} (previous 7d : {in_prev_7d})")

    print_top("Top routes", by_route, top_n)
    print_top("Top functions", by_function, top_n)
    print_top("Top exceptions", by_exception, top_n)
    print_top("Counts by day", by_day, top_n)

    print(f"\nMost recent {min(show_recent, len(events))} matching errors:")
    for event in events[-show_recent:]:
        print(f"\n- {event.timestamp} | PID {event.pid} | user={event.user}")
        if event.preceding_line is not None:
            print(f"  Prev     : {event.preceding_line}")
        print(f"  Route    : {event.route}")
        print(f"  Function : {event.function}")
        print(f"  Exception: {event.exception}")
        print(f"  Status   : {event.status_message}")
        if show_traceback_lines > 0 and event.traceback_lines:
            print("  Traceback:")
            for tb_line in event.traceback_lines[-show_traceback_lines:]:
                print(f"    {tb_line}")


def main() -> None:
    def positive_int(value: str) -> int:
        integer = int(value)
        if integer < 1:
            raise argparse.ArgumentTypeError("Value must be >= 1.")
        return integer

    def nonnegative_int(value: str) -> int:
        integer = int(value)
        if integer < 0:
            raise argparse.ArgumentTypeError("Value must be >= 0.")
        return integer

    parser = argparse.ArgumentParser(
        description=(
            "Summarize matching server errors from ezEML logs, including route/function/traceback context."
        )
    )
    parser.add_argument(
        "log_file",
        nargs="?",
        default="webapp/ezeml-log.txt",
        help="Path to log file (default: webapp/ezeml-log.txt)",
    )
    parser.add_argument(
        "--error-pattern",
        default=r"500 Internal Server Error",
        help="Regex pattern to match error messages (default matches 500 errors)",
    )
    parser.add_argument(
        "--case-sensitive",
        action="store_true",
        help="Use case-sensitive matching for --error-pattern",
    )
    parser.add_argument(
        "--max-errors",
        type=positive_int,
        default=500,
        help="Analyze at most the most recent N matching errors (default: 500)",
    )
    parser.add_argument(
        "--top",
        type=positive_int,
        default=10,
        help="Show top N rows in summary tables (default: 10)",
    )
    parser.add_argument(
        "--show-recent",
        type=nonnegative_int,
        default=10,
        help="Show details for the most recent N matching errors (default: 10)",
    )
    parser.add_argument(
        "--traceback-lines",
        type=nonnegative_int,
        default=0,
        help="Include the last N lines of traceback for each recent error (default: 0)",
    )

    args = parser.parse_args()
    events = parse_log(args.log_file, args.error_pattern, not args.case_sensitive)
    events = sorted(events, key=lambda e: e.timestamp)

    if args.max_errors > 0:
        events = events[-args.max_errors:]

    summarize(
        events=events,
        top_n=args.top,
        show_recent=args.show_recent,
        show_traceback_lines=args.traceback_lines,
    )


if __name__ == "__main__":
    main()
