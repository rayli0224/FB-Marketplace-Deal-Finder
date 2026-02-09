"""
Colored logging formatter and reusable log helpers.

- setup_colored_logger(module_name): get a logger with colors (level + message only, no module prefix).
- log_step_sep(logger, title): separator line for a main step.
- log_substep_sep(logger, title): separator line for a sub-step.
- log_step_title(logger, message, level=INFO): separator line, bold step/section title, separator line (e.g. "Step 1: ...", "Search done: ...").
- log_data_line(logger, label, **kwargs): one-line key=value data (e.g. retrieved/processed payloads).
- log_error_short(logger, message, max_len=100): error with consistent truncation.
- wait_status(logger, label, inline=True): context manager that logs "Waiting for X..."; when inline=True and stdout is a TTY, elapsed time updates in place every 100ms with millisecond precision (N.NNNs), then "Done: X (N.NNNs)" on exit.
"""

import logging
import os
import sys
import threading
import time
from contextlib import contextmanager
# Per-thread indent for sub-step content (e.g. "  "). Set/cleared by callers; formatter prepends to each line.
_step_indent = threading.local()


class ColoredFormatter(logging.Formatter):
    """
    Formats log records as level name and message only (no module prefix). WARNING and
    ERROR/CRITICAL use ANSI colors (yellow, bold red); INFO and DEBUG are uncolored.
    Colors are applied only when stdout is a TTY (detected in __init__).
    """
    COLORS = {
        'DEBUG': '',
        'INFO': '',
        'WARNING': '\033[33m',
        'ERROR': '\033[1;31m',
        'CRITICAL': '\033[1;31m',
    }
    RESET = '\033[0m'

    def __init__(self, use_colors: bool = True):
        if use_colors and not hasattr(sys.stdout, 'isatty'):
            use_colors = False
        elif use_colors:
            try:
                use_colors = sys.stdout.isatty()
            except (AttributeError, OSError):
                use_colors = False
        self.use_colors = use_colors
        super().__init__('%(levelname)s: %(message)s')
    
    def format(self, record: logging.LogRecord) -> str:
        """
        Format the record with colored level name and message text. When colors are enabled,
        both the level and the message use the same color for that level. Mutates record.levelname
        for this call only, then restores it so other handlers see the original value.
        Empty messages return "" so the handler outputs only a newline (no "INFO: " on a blank line).
        """
        if not record.getMessage():
            return ""
        original_levelname = record.levelname
        if self.use_colors:
            color = self.COLORS.get(original_levelname, '')
            record.levelname = f"{color}{original_levelname}{self.RESET}"
            formatted = super().format(record)
            record.levelname = original_levelname
            message = record.getMessage()
            if message:
                formatted = formatted.replace(message, f"{color}{message}{self.RESET}", 1)
            return _indent_formatted(formatted)
        formatted = super().format(record)
        record.levelname = original_levelname
        return _indent_formatted(formatted)


def _indent_formatted(formatted: str) -> str:
    """Prepend current step indent to each line of formatted log output."""
    indent = getattr(_step_indent, "value", "") or ""
    if not indent:
        return formatted
    return "\n".join(indent + line for line in formatted.split("\n"))


class _ThreadSafeStreamHandler(logging.StreamHandler):
    """
    StreamHandler that acquires a shared lock before writing so multiple threads
    (e.g. api and fb_scraper worker) never interleave log lines.
    """
    _lock = threading.Lock()

    def emit(self, record: logging.LogRecord) -> None:
        with self._lock:
            super().emit(record)


def _get_log_level() -> int:
    """
    Resolve log level from environment (DEBUG, LOG_LEVEL) or --debug in sys.argv.
    Returns the default logging level derived from environment and argv.
    """
    if os.environ.get("DEBUG", "").lower() in ("1", "true", "yes"):
        return logging.DEBUG
    log_level_env = os.environ.get("LOG_LEVEL", "").upper()
    if log_level_env == "DEBUG":
        return logging.DEBUG
    elif log_level_env == "INFO":
        return logging.INFO
    elif log_level_env == "WARNING":
        return logging.WARNING
    elif log_level_env == "ERROR":
        return logging.ERROR
    if "--debug" in sys.argv:
        return logging.DEBUG
    
    return logging.INFO


def setup_colored_logger(module_name: str, level: int = None) -> logging.Logger:
    """
    Return a logger that writes to stdout with colored level names and message (no module prefix).
    If level is not given, it is taken from DEBUG or LOG_LEVEL env or from --debug in sys.argv.
    Existing handlers are cleared so the returned logger has exactly one StreamHandler with ColoredFormatter.
    """
    if level is None:
        level = _get_log_level()
    logger = logging.getLogger(module_name)
    logger.setLevel(level)
    logger.handlers.clear()
    handler = _ThreadSafeStreamHandler(sys.stdout)
    handler.setLevel(level)
    handler.setFormatter(ColoredFormatter())
    logger.addHandler(handler)
    logger.propagate = False
    return logger


# Length of the separator line used to break between steps (full-width line of dashes).
SEP_LINE_LEN = 76

# ANSI bold for step titles (only used when stdout is a TTY).
BOLD = "\033[1m"
BOLD_RESET = "\033[0m"

# Max characters for a single value in a data line; longer values are truncated with ".."
MAX_DATA_VALUE_LEN = 80

# Default truncation length for log_error_short so error lines stay bounded
DEFAULT_ERROR_MAX_LEN = 100


def _bold_if_tty(text: str) -> str:
    """Return text wrapped in ANSI bold when stdout is a TTY, else plain text."""
    try:
        if sys.stdout.isatty():
            return f"{BOLD}{text}{BOLD_RESET}"
    except (AttributeError, OSError):
        pass
    return text


def _log_sep_with_title(logger: logging.Logger, title: str, level: int = logging.INFO) -> None:
    """Log separator line, bold title on its own line, then separator line. Shared by step/substep/step_title."""
    logger.info("─" * SEP_LINE_LEN)
    logger.log(level, _bold_if_tty(title))
    logger.info("─" * SEP_LINE_LEN)


def log_step_sep(logger: logging.Logger, title: str) -> None:
    """Log a main step break: separator line, bold title, separator line."""
    _log_sep_with_title(logger, title)


def log_substep_sep(logger: logging.Logger, title: str) -> None:
    """Log a sub-step break: separator line, bold title, separator line."""
    _log_sep_with_title(logger, title)


def log_step_title(logger: logging.Logger, message: str, level: int = logging.INFO) -> None:
    """Log a step/section title with separator lines above and below (e.g. 'Step 1: ...', 'Search done: ...')."""
    _log_sep_with_title(logger, message, level)


def set_step_indent(indent: str) -> None:
    """Set the indent string for subsequent log lines in this thread (e.g. "  " for sub-step content)."""
    _step_indent.value = indent


def clear_step_indent() -> None:
    """Clear the step indent so subsequent log lines are not indented."""
    _step_indent.value = ""


def _format_data_value(key: str, value) -> str:
    """
    Format one key-value for a data log line. The key "price" is rendered as $X.2f;
    any other value is stringified and truncated to MAX_DATA_VALUE_LEN characters.
    """
    if key == "price" and isinstance(value, (int, float)):
        return f"${float(value):.2f}"
    s = str(value)
    return (s[:MAX_DATA_VALUE_LEN] + "..") if len(s) > MAX_DATA_VALUE_LEN else s


def log_data_line(logger: logging.Logger, label: str, **kwargs) -> None:
    """
    Log a single INFO line: label followed by key=value pairs joined by " | ".
    Keys with value None are omitted. Price is formatted as currency; other values are
    stringified and truncated so the line stays readable.
    """
    parts = [f"{k}={_format_data_value(k, v)}" for k, v in kwargs.items() if v is not None]
    logger.info(f"{label}: {' | '.join(parts)}")


def log_error_short(logger: logging.Logger, message: str, max_len: int = DEFAULT_ERROR_MAX_LEN) -> None:
    """
    Log message at ERROR level after truncating to max_len characters. Keeps error output
    bounded when exceptions or long messages would otherwise flood the console.
    """
    logger.error(str(message)[:max_len])


# Interval in seconds for periodic "still waiting" status updates (non-inline).
WAIT_STATUS_INTERVAL = 5

# Interval for inline (same-line) updates when inline=True; 0.1s so milliseconds visibly tick.
WAIT_STATUS_INLINE_INTERVAL = 0.1


def _get_handler_lock(logger: logging.Logger):
    """Return the lock used by our thread-safe handler if this logger uses one, else a new lock."""
    for h in logger.handlers:
        if isinstance(h, _ThreadSafeStreamHandler):
            return _ThreadSafeStreamHandler._lock
    return threading.Lock()


def _is_tty() -> bool:
    """Return True if stdout is a TTY (and we can use \\r for inline updates)."""
    try:
        return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()
    except (AttributeError, OSError):
        return False


@contextmanager
def wait_status(logger: logging.Logger, label: str, inline: bool = True):
    """
    Context manager for long-running work (e.g. API requests). Logs "Waiting for {label}..."
    on entry. If inline=True and stdout is a TTY, elapsed time is updated in place on the same
    line every 100ms with millisecond precision (e.g. "  … {label} (5.234s)").
    Otherwise logs a new line every WAIT_STATUS_INTERVAL seconds. On exit logs "Done: {label} (N.NNNs)".
    Uses a daemon thread so it does not block shutdown. Inline mode uses the same lock as the
    log handler to avoid corrupting other log lines; if other threads log during the wait, those
    lines may overwrite the status line or vice versa (best when the blocked work does not log).
    """
    logger.info(f"Waiting for {label}...")
    start = time.monotonic()
    stop_event = threading.Event()
    use_inline = inline and _is_tty()
    lock = _get_handler_lock(logger)
    interval = WAIT_STATUS_INLINE_INTERVAL if use_inline else WAIT_STATUS_INTERVAL

    def tick():
        while not stop_event.wait(timeout=interval):
            elapsed = time.monotonic() - start
            if use_inline:
                with lock:
                    sys.stdout.write(f"\r  … {label} ({elapsed:.3f}s)    ")
                    sys.stdout.flush()
            else:
                logger.info(f"  … {label} ({elapsed:.3f}s)")

    t = threading.Thread(target=tick, daemon=True)
    t.start()
    try:
        yield
    finally:
        stop_event.set()
        t.join(timeout=interval + 1)
        elapsed = time.monotonic() - start
        if use_inline:
            with lock:
                sys.stdout.write(f"\rDone: {label} ({elapsed:.3f}s)\n")
                sys.stdout.flush()
        else:
            logger.info(f"Done: {label} ({elapsed:.3f}s)")
