"""
Colored logging formatter utility for better log visibility.

Provides a custom formatter that adds ANSI color codes to log messages
and prefixes them with module names for easier identification.
"""

import logging
import sys
import os


class ColoredFormatter(logging.Formatter):
    """
    Custom logging formatter that adds colors and module prefixes.
    
    Colors:
    - DEBUG: Cyan
    - INFO: Green
    - WARNING: Yellow
    - ERROR: Red
    - CRITICAL: Red (bold)
    """
    
    # ANSI color codes
    COLORS = {
        'DEBUG': '\033[36m',      # Cyan
        'INFO': '\033[32m',       # Green
        'WARNING': '\033[33m',    # Yellow
        'ERROR': '\033[31m',      # Red
        'CRITICAL': '\033[1;31m', # Bold Red
    }
    RESET = '\033[0m'
    
    def __init__(self, module_name: str = None, use_colors: bool = True):
        """
        Initialize the colored formatter.
        
        Args:
            module_name: Optional module name prefix (e.g., "ebay_scraper")
            use_colors: Whether to use colors (default: True, auto-detects if TTY)
        """
        # Auto-detect if colors should be used (only if stdout is a TTY)
        if use_colors and not hasattr(sys.stdout, 'isatty'):
            use_colors = False
        elif use_colors:
            try:
                use_colors = sys.stdout.isatty()
            except (AttributeError, OSError):
                use_colors = False
        
        self.use_colors = use_colors
        self.module_name = module_name
        
        # Build format string
        if module_name:
            fmt = f'[{module_name}] %(levelname)s: %(message)s'
        else:
            fmt = '%(levelname)s: %(message)s'
        
        super().__init__(fmt)
    
    def format(self, record: logging.LogRecord) -> str:
        """
        Format the log record with colors and module prefix.
        """
        # Store original levelname before modification
        original_levelname = record.levelname
        
        # Add color to levelname
        if self.use_colors:
            color = self.COLORS.get(original_levelname, '')
            record.levelname = f"{color}{original_levelname}{self.RESET}"
        
        # Format the message
        formatted = super().format(record)
        
        # Restore original levelname for next log
        record.levelname = original_levelname
        
        return formatted


def _get_log_level() -> int:
    """
    Determine the logging level from environment variables or command-line arguments.
    
    Checks for DEBUG environment variable or --debug flag in sys.argv.
    Returns logging.DEBUG if debug mode is enabled, otherwise logging.INFO.
    """
    # Check for DEBUG environment variable
    if os.environ.get("DEBUG", "").lower() in ("1", "true", "yes"):
        return logging.DEBUG
    
    # Check for LOG_LEVEL environment variable
    log_level_env = os.environ.get("LOG_LEVEL", "").upper()
    if log_level_env == "DEBUG":
        return logging.DEBUG
    elif log_level_env == "INFO":
        return logging.INFO
    elif log_level_env == "WARNING":
        return logging.WARNING
    elif log_level_env == "ERROR":
        return logging.ERROR
    
    # Check for --debug flag in command-line arguments
    if "--debug" in sys.argv:
        return logging.DEBUG
    
    return logging.INFO


def setup_colored_logger(module_name: str, level: int = None) -> logging.Logger:
    """
    Set up a logger with colored formatting and module prefix.
    
    Args:
        module_name: Name of the module (e.g., "ebay_scraper")
        level: Logging level (default: None, will auto-detect from DEBUG env var or --debug flag)
        
    Returns:
        Configured logger instance
    """
    # Auto-detect log level if not provided
    if level is None:
        level = _get_log_level()
    
    logger = logging.getLogger(module_name)
    logger.setLevel(level)
    
    # Remove existing handlers to avoid duplicates
    logger.handlers.clear()
    
    # Create console handler
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)
    
    # Set colored formatter
    formatter = ColoredFormatter(module_name=module_name)
    handler.setFormatter(formatter)
    
    logger.addHandler(handler)
    logger.propagate = False  # Prevent propagation to root logger
    
    return logger
