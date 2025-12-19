"""Logging configuration for Upwork Automation"""
import sys
from pathlib import Path

from loguru import logger

from .config import get_config, get_project_root


def setup_logging():
    """Configure logging based on config settings"""
    config = get_config()
    log_config = config.logging
    
    # Remove default handler
    logger.remove()
    
    # Add console handler
    logger.add(
        sys.stderr,
        level=log_config.level,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"
    )
    
    # Create logs directory if it doesn't exist
    log_path = get_project_root() / log_config.file
    log_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Add file handler with rotation
    logger.add(
        log_path,
        level=log_config.level,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
        rotation=f"{log_config.max_size_mb} MB",
        retention=log_config.backup_count,
        compression="zip"
    )
    
    return logger


def get_logger():
    """Get the configured logger instance"""
    return logger
