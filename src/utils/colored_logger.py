"""
Colored logging formatter and reusable log helpers.

- setup_colored_logger(module_name): get a logger that outputs message only (no INFO/DEBUG prefix, no module prefix). WARNING/ERROR messages are colored when stdout is a TTY.
- log_step_sep(logger, title): separator line for a main step (overall query only: Step 1, Step 2, ...).
- log_section_sep(logger, title): separator line for a section within a flow (e.g. per-listing header). Do not use "Step N" here.
- log_step_title(logger, message, level=INFO): separator line, bold title, separator line (for main steps or section titles).
- log_data_line(logger, label, **kwargs): one-line key=value data.
- log_data_block(logger, label, indent='  ', **kwargs): label then one line per field (indented); use for listing/retrieved blocks.
- log_listing_box_sep(logger): single dash line to visually contain a list element (wrap each Retrieved or FB listing block).
- log_error_short(logger, message, max_len=100): error with consistent truncation.
- wait_status(logger, label, inline=True): context manager that logs
  "⏳ Waiting for X..." and, on exit, "✅ Done: X (N.NNNs)".
"""

import logging
import os
import sys
import threading
import time
from contextlib import contextmanager
# Per-thread indent for section content (e.g. "  "). Set/cleared by callers; formatter prepends to each line.
_step_indent = threading.local()


class ColoredFormatter(logging.Formatter):
    """
    Formats log records as message only (no level name, no module prefix). WARNING and
    ERROR/CRITICAL messages use ANSI colors (yellow, bold red); INFO and DEBUG are uncolored.
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
        super().__init__('%(message)s')

    def format(self, record: logging.LogRecord) -> str:
        """
        Output only the message (no INFO/DEBUG prefix). When colors are enabled,
        WARNING and ERROR messages are colored. Applies step indent when set.
        """
        if not record.getMessage():
            return ""
        message = record.getMessage()
        if self.use_colors:
            color = self.COLORS.get(record.levelname, '')
            if color:
                message = f"{color}{message}{self.RESET}"
        return _indent_formatted(message)


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


def set_all_loggers_level(level: int):
    """
    Update the level of all loggers that were created with setup_colored_logger.
    
    This is useful when DEBUG mode is detected after module import time (e.g. when
    the DEBUG env var is set by a shell script that runs uvicorn). Call this at
    application startup to ensure all loggers respect the current DEBUG setting.
    """
    logger_names = ("api", "fb_scraper", "listing_processor", "openai_helpers", "ebay_scraper")
    for name in logger_names:
        logger = logging.getLogger(name)
        logger.setLevel(level)
        for handler in logger.handlers:
            handler.setLevel(level)


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
    """Log separator line, bold title on its own line, then separator line. Shared by step/section/step_title."""
    logger.info("─" * SEP_LINE_LEN)
    logger.log(level, _bold_if_tty(title))
    logger.info("─" * SEP_LINE_LEN)


def log_step_sep(logger: logging.Logger, title: str) -> None:
    """Log a main step break (overall query only): separator line, bold title, separator line."""
    _log_sep_with_title(logger, title)


def log_section_sep(logger: logging.Logger, title: str) -> None:
    """Log a section break within a flow (e.g. per-listing). Same visual as step sep but not a 'Step N'."""
    _log_sep_with_title(logger, title)


def log_step_title(logger: logging.Logger, message: str, level: int = logging.INFO) -> None:
    """Log a title with separator lines above and below (main steps or section titles)."""
    _log_sep_with_title(logger, message, level)


def log_listing_box_sep(logger: logging.Logger) -> None:
    """Log a single dash line to visually contain a list element (e.g. one Retrieved or FB listing block)."""
    logger.info("─" * SEP_LINE_LEN)


def set_step_indent(indent: str) -> None:
    """Set the indent string for subsequent log lines in this thread (e.g. "  " for section content)."""
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


def log_data_block(logger: logging.Logger, label: str, indent: str = "  ", **kwargs) -> None:
    """
    Log a label on one line, then each key=value on its own indented line (one field per line).
    Keys with value None are omitted. Uses the same value formatting as log_data_line (price as
    currency, long values truncated). Use for listing/retrieved blocks so each element is easy to scan.
    If label is empty, skip the label line (useful when label was already logged via separator).
    """
    if label:
        logger.info(label if label.endswith(":") else f"{label}:")
    for k, v in kwargs.items():
        if v is not None:
            logger.info(f"{indent}{k}={_format_data_value(k, v)}")


def log_warning(logger: logging.Logger, message: str) -> None:
    """
    Log message at WARNING level. Uses the logger's warning method which will be
    colored yellow by the ColoredFormatter when stdout is a TTY.
    """
    logger.warning(message)


def log_error_short(logger: logging.Logger, message: str, max_len: int = DEFAULT_ERROR_MAX_LEN) -> None:
    """
    Log message at ERROR level with a short prefix. The message is truncated so the
    full output (prefix + message) is at most max_len characters, keeping error output bounded.
    """
    prefix = "❌ "
    msg = str(message)[: max_len - len(prefix)]
    logger.error(f"{prefix}{msg}")


def truncate_lines(content: str, n_lines: int) -> str:
    """
    Truncate content to first n_lines, adding a summary line if truncated.
    
    Args:
        content: The content string to truncate
        n_lines: Number of lines to keep
    
    Returns:
        Truncated content with "... (N more lines)" appended if truncated
    """
    lines = content.split('\n')
    truncated = '\n'.join(lines[:n_lines])
    if len(lines) > n_lines:
        truncated += f"\n... ({len(lines) - n_lines} more lines)"
    return truncated


@contextmanager
def wait_status(logger: logging.Logger, label: str, inline: bool = True):
    """
    Context manager for long-running work (e.g. API requests). Logs "Waiting for {label}..."
    on entry and logs "Done: {label} (N.NNNs)" on exit.

    We intentionally do not emit periodic elapsed-timer updates because concurrent
    workers make intermediate timer lines noisy and hard to read.
    """
    _ = inline  # retained for backward compatibility with existing call sites
    logger.info(f"⏳ Waiting for {label}...")
    start = time.monotonic()
    try:
        yield
    finally:
        elapsed = time.monotonic() - start
        logger.info(f"✅ Done: {label} ({elapsed:.3f}s)")
