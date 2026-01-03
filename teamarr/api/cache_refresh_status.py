"""Cache refresh status tracking.

Provides global state for tracking cache refresh progress,
used by both SSE streaming and polling endpoints.
"""

from dataclasses import dataclass, field
from datetime import datetime
from threading import Lock
from typing import Any


@dataclass
class CacheRefreshStatus:
    """Current cache refresh status."""

    in_progress: bool = False
    status: str = "idle"  # idle, starting, discovering, saving, complete, error
    message: str = ""
    percent: int = 0
    phase: str = ""  # discovery, saving
    provider: str = ""  # current provider being processed
    current: int = 0
    total: int = 0
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error: str | None = None
    result: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert to JSON-serializable dict."""
        return {
            "in_progress": self.in_progress,
            "status": self.status,
            "message": self.message,
            "percent": self.percent,
            "phase": self.phase,
            "provider": self.provider,
            "current": self.current,
            "total": self.total,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "error": self.error,
            "result": self.result,
        }

    def reset(self) -> None:
        """Reset to idle state."""
        self.in_progress = False
        self.status = "idle"
        self.message = ""
        self.percent = 0
        self.phase = ""
        self.provider = ""
        self.current = 0
        self.total = 0
        self.started_at = None
        self.completed_at = None
        self.error = None
        self.result = {}


# Global status instance with thread-safe access
_status = CacheRefreshStatus()
_status_lock = Lock()


def get_refresh_status() -> dict:
    """Get current refresh status as dict."""
    with _status_lock:
        return _status.to_dict()


def is_refresh_in_progress() -> bool:
    """Check if refresh is in progress."""
    with _status_lock:
        return _status.in_progress


def start_refresh() -> bool:
    """Mark refresh as started.

    Returns False if already in progress.
    """
    with _status_lock:
        if _status.in_progress:
            return False
        _status.reset()
        _status.in_progress = True
        _status.status = "starting"
        _status.message = "Initializing cache refresh..."
        _status.percent = 0
        _status.started_at = datetime.now()
        return True


def update_refresh_status(
    status: str | None = None,
    message: str | None = None,
    percent: int | None = None,
    phase: str | None = None,
    provider: str | None = None,
    current: int | None = None,
    total: int | None = None,
) -> None:
    """Update refresh status."""
    with _status_lock:
        if status is not None:
            _status.status = status
        if message is not None:
            _status.message = message
        if percent is not None:
            _status.percent = percent
        if phase is not None:
            _status.phase = phase
        if provider is not None:
            _status.provider = provider
        if current is not None:
            _status.current = current
        if total is not None:
            _status.total = total


def complete_refresh(result: dict) -> None:
    """Mark refresh as complete."""
    with _status_lock:
        _status.in_progress = False
        _status.status = "complete"
        _status.message = "Cache refresh complete"
        _status.percent = 100
        _status.completed_at = datetime.now()
        _status.result = result


def fail_refresh(error: str) -> None:
    """Mark refresh as failed."""
    with _status_lock:
        _status.in_progress = False
        _status.status = "error"
        _status.message = f"Error: {error}"
        _status.error = error
        _status.completed_at = datetime.now()
