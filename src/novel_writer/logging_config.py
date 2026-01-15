"""Logging configuration - Sets up file and console logging."""

import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

# Global log file handler reference
_file_handler: Optional[logging.FileHandler] = None


def setup_logging(log_dir: Optional[Path] = None, level: int = logging.INFO) -> Optional[Path]:
    """
    Set up logging with both console and file output.
    
    Args:
        log_dir: Directory to save log files. If None, only console logging is used.
        level: Logging level (default: INFO)
        
    Returns:
        Path to log file if file logging is enabled, None otherwise
    """
    global _file_handler
    
    # Create formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Get root logger for novel_writer package
    root_logger = logging.getLogger('novel_writer')
    root_logger.setLevel(level)
    
    # Clear existing handlers to avoid duplicates
    root_logger.handlers.clear()
    
    # Console handler (always enabled)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)
    
    log_file_path = None
    
    # File handler (if log_dir is provided)
    if log_dir:
        # Create logs directory if it doesn't exist
        log_dir = Path(log_dir)
        log_dir.mkdir(parents=True, exist_ok=True)
        
        # Generate log filename with timestamp
        timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
        log_file_path = log_dir / f"novel_writer_{timestamp}.log"
        
        # Remove old file handler if exists
        if _file_handler:
            root_logger.removeHandler(_file_handler)
        
        # Create new file handler
        _file_handler = logging.FileHandler(log_file_path, encoding='utf-8')
        _file_handler.setLevel(level)
        _file_handler.setFormatter(formatter)
        root_logger.addHandler(_file_handler)
    
    return log_file_path


def get_log_dir_for_novel(novel_path: Path) -> Path:
    """
    Get the logs directory for a novel project.
    
    Args:
        novel_path: Path to the novel project directory
        
    Returns:
        Path to the logs directory (novels/小说名/logs/)
    """
    return novel_path / "logs"
