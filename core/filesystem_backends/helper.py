"""
Generic file system helper with pluggable backends.
"""

import os
from abc import ABC, abstractmethod
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Tuple
from urllib.parse import parse_qs, urlparse

from django.conf import settings


@dataclass
class FileSystemConfig:
    """Base configuration for file system connections."""
    scheme: str
    username: Optional[str] = None
    password: Optional[str] = None
    host: Optional[str] = None
    path: str = "/"
    options: Dict[str, str] = None

    def __post_init__(self):
        if self.options is None:
            self.options = {}


class FileSystemEngine(ABC):
    """Abstract base class for file system backends."""
    def parse_dsn(self, dsn: str) -> FileSystemConfig:
        """
        Parse a DSN string into configuration.

        Args:
            dsn: The DSN string (e.g., "smb://user:pass@host/share/path")

        Returns:
            FileSystemConfig object

        Raises:
            ValueError: If DSN format is invalid
        """
        parsed = urlparse(dsn)
        options = {}
        if parsed.query:
            options = {k: v[0] if v else '' for k, v in parse_qs(parsed.query).items()}

        return FileSystemConfig(
            scheme=parsed.scheme,
            username=parsed.username,
            password=parsed.password,
            host=parsed.hostname,
            path=parsed.path,
            options=options
        )
    
    @abstractmethod
    def fetch_file_to_temp(self, file_path: str) -> Tuple[str, str]:
        """
        Fetch a file to a temporary local file.
        
        Args:
            file_path: Path to the file relative to the configured path
            
        Returns:
            Tuple of (temp_file_path, original_filename)
            
        Raises:
            Exception: If file transfer fails
        """
        pass
    
    def is_directory(self, path: str) -> bool:
        """
        Check if a path is a directory.
        
        Args:
            path: Path to check
            
        Returns:
            True if path is a directory, False otherwise
        """
        try:
            # Try to list the path - if it works, it's likely a directory
            self.list_files(path)
            return True
        except:
            return False


def get_file_system_engine() -> FileSystemEngine:
    """
    Get the configured file system engine.
    
    Returns:
        FileSystemEngine instance if configured, None otherwise
        
    Raises:
        ValueError: If DSN scheme is not supported
    """
    dsn = getattr(settings, 'REMOTE_FILE_SHARE', '')
    if not dsn:
        raise ValueError("REMOTE_FILE_SHARE not configured in Django settings")
    
    scheme = dsn.split('://', 1)[0].lower()
    if scheme == 'smb':
        from core.filesystem_backends.samba import SambaFileSystemEngine
        return SambaFileSystemEngine(dsn)
    else:
        raise ValueError(f"Unsupported file system scheme: {scheme}")


def fetch_file_to_temp(file_path: str) -> Tuple[str, str]:
    """
    Fetch a file to temporary storage using the configured file system engine.
    
    Args:
        file_path: Path to the file
        
    Returns:
        Tuple of (temp_file_path, original_filename)
        
    Raises:
        ValueError: If no file system is configured
    """
    engine = get_file_system_engine()

    return engine.fetch_file_to_temp(file_path)


def batch_by_folder(file_list: list[str], max_batch=100):
    """
    Iterate through files and yield batches grouped by directory.
    
    Files are grouped by directory and yielded in batches respecting max_batch size.
    
    Args:
        file_list: list of file paths
        max_batch: Maximum number of files per batch

    Yields:
        Tuple of (folder_path, files_in_batch[])
    """
    current_folder = None
    batch = []

    for f in file_list:
        folder = str(Path(f.replace("\\", "/")).parent).replace("/", "\\")
        if folder != current_folder:
            if batch:
                yield current_folder, batch
            current_folder = folder
            batch = []
        batch.append(f)
        if len(batch) == max_batch:
            yield current_folder, batch
            batch = []

    if batch:
        yield current_folder, batch

@contextmanager
def download_document(document):
    engine = get_file_system_engine()
    temp_file_path, original_name = engine.fetch_file_to_temp(document.file_path)
    try:
        yield temp_file_path, original_name
    finally:
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)
