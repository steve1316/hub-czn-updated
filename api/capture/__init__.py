"""
Capture module for intercepting CZN game data via mitmproxy.

This module provides a complete capture system for intercepting and extracting
Memory Fragment inventory and character data from the Chaos Zero Nightmare mobile game.

Public API:
    - CaptureManager: Main orchestration class for capture workflow
    - CaptureError: Exception raised when capture operations fail
    - setup_certificate: Generate the mitmproxy CA certificate in-process
    - check_prerequisites: Check if all prerequisites are met
    - PrerequisiteStatus: Dataclass with prerequisite status info
    - PROXY_PORT: Port used for local proxy
    - GAME_PORT: Port used by game server

Example:
    >>> from capture import CaptureManager, check_prerequisites
    >>>
    >>> # Check prerequisites
    >>> status = check_prerequisites()
    >>>
    >>> # Start capture
    >>> manager = CaptureManager(
    >>>     output_folder=Path("snapshots"),
    >>>     log_callback=print
    >>> )
    >>> manager.start_capture()
    >>> # ... play game ...
    >>> captured_file = manager.stop_capture()
"""

from .manager import CaptureManager, CaptureError
from .setup import (
    setup_certificate,
    check_prerequisites,
    open_certificate,
    PrerequisiteStatus
)
from .constants import PROXY_PORT, GAME_PORT, OUTPUT_DIR

__all__ = [
    # Manager
    'CaptureManager',
    'CaptureError',

    # Setup
    'setup_certificate',
    'check_prerequisites',
    'open_certificate',
    'PrerequisiteStatus',

    # Constants
    'PROXY_PORT',
    'GAME_PORT',
    'OUTPUT_DIR',
]

__version__ = '1.0.0'