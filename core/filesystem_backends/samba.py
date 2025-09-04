"""
Samba/SMB file system backend implementation using proper SMB protocol.
"""

import os
import tempfile
from typing import Optional, Tuple

from core.filesystem_backends.helper import FileSystemConfig, FileSystemEngine

try:
    import smbclient
    SMB_AVAILABLE = True
except ImportError:
    SMB_AVAILABLE = False

class SambaFileSystemEngine(FileSystemEngine):
    """Samba/SMB file system backend using proper SMB protocol operations."""
    
    def __init__(self, dsn: str):
        """
        Initialize Samba engine with DSN.
        
        Args:
            dsn: The Samba DSN string
            
        Raises:
            ImportError: If smbclient is not available
        """
        if not SMB_AVAILABLE:
            raise ImportError("smbclient is required for Samba support. Install with: pip install smbclient")
        
        self.config = self.parse_dsn(dsn)
        self.share_name , self.base_path = self.get_share_and_prefix()
        if not self.share_name:
            raise ValueError("Share name not configured")

        # Parse the configuration for SMB operations
        self._setup_smb_connection()
    
    def _setup_smb_connection(self):
        """Set up SMB connection parameters."""
        # Register session with credentials
        if self.config.username and self.config.password:
            smbclient.register_session(
                server=self.config.host,
                username=self.config.username,
                password=self.config.password,
            )

    def get_share_and_prefix(self):
        # Extract share and path from the config
        path_parts = self.config.path.strip('/').split('/', 1)
        if path_parts[0]:
            return path_parts[0], path_parts[1] if len(path_parts) > 1 else ""
        return self.config.path, ""

    
    def parse_dsn(self, dsn: str) -> FileSystemConfig:
        """
        Parse a Samba DSN in the format:
        smb://username:password@server/share/path?option1=value1&option2=value2
        """
        config = super().parse_dsn(dsn)
        if config.scheme.lower() != 'smb':
            raise Exception(f"Scheme must be smb, not {config.scheme}")

        return config

    
    def _build_smb_path(self, path: Optional[str] = None) -> str:
        """Build the full SMB UNC path."""
        # Start with UNC path
        smb_path = f"\\\\{self.config.host}\\{self.share_name}"
        
        # Add base path
        if self.base_path:
            smb_path += "\\" + self.base_path.replace('/', '\\')
        
        # Add additional path
        if path:
            path_clean = path.strip('/').replace('/', '\\')
            if path_clean:
                smb_path += "\\" + path_clean
        
        return smb_path

    def is_directory(self, path: str) -> bool:
        """
        Check if a path is a directory using SMB protocol.
        
        Args:
            path: Path to check
            
        Returns:
            True if path is a directory, False otherwise
        """
        smb_path = self._build_smb_path(path)
        try:
            return smbclient.isdir(smb_path)
        except Exception:
            return False
    
    def fetch_file_to_temp(self, file_path: str) -> Tuple[str, str]:
        """
        Fetch a file from the remote Samba share to a temporary local file using SMB protocol.
        
        Args:
            file_path: Path to the file relative to the configured share path
            
        Returns:
            Tuple of (temp_file_path, original_filename)
            
        Raises:
            Exception: If connection or file transfer fails
        """
        smb_path = self._build_smb_path(file_path)
        original_filename = os.path.basename(file_path)
        temp_path = None
        
        try:
            # Create a temporary file with appropriate suffix
            temp_fd, temp_path = tempfile.mkstemp(
                suffix=f'_{original_filename}',
                prefix='smb_fetch_'
            )
            
            # Open the remote file using SMB protocol and copy to temp file
            with smbclient.open_file(smb_path, mode='rb') as remote_file:
                with os.fdopen(temp_fd, 'wb') as temp_file:
                    # Read and write in chunks for better memory usage
                    chunk_size = 64 * 1024  # 64KB chunks
                    while True:
                        chunk = remote_file.read(chunk_size)
                        if not chunk:
                            break
                        temp_file.write(chunk)
            
            return temp_path, original_filename
            
        except Exception as e:
            # Clean up temporary file on error
            if temp_path and os.path.exists(temp_path):
                try:
                    os.unlink(temp_path)
                except OSError:
                    pass
            raise Exception(f"Failed to fetch file from {smb_path}: {str(e)}")