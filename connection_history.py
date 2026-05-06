# =============================================================================
#  connection_history.py  –  Panic Pilot | Connection History & Persistence
# =============================================================================
#
#  Phase 12.1: Connection History + Room Discovery
#
#  Handles persistent storage of recently connected IPs with custom usernames.
#  Stores to connection_history.json in the OS user config directory:
#    - Windows : %APPDATA%\PanicPilot\connection_history.json
#    - macOS   : ~/Library/Application Support/PanicPilot/connection_history.json
#    - Linux   : ~/.config/PanicPilot/connection_history.json
# =============================================================================
from __future__ import annotations

import json
import os
import tempfile
import shutil
from datetime import datetime
from typing import Optional


def _get_config_dir() -> str:
    """Return temp-directory for PanicPilot data files."""
    cfg_dir = os.path.join(tempfile.gettempdir(), "PanicPilot")
    os.makedirs(cfg_dir, exist_ok=True)
    return cfg_dir


HISTORY_FILE = os.path.join(_get_config_dir(), "connection_history.json")

_OLD_HISTORY_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "connection_history.json"
)


def _migrate_old_file() -> None:
    """One-time migration: move connection_history.json from old location."""
    if os.path.exists(HISTORY_FILE):
        return
    if not os.path.exists(_OLD_HISTORY_FILE):
        return
    try:
        shutil.copy2(_OLD_HISTORY_FILE, HISTORY_FILE)
        os.remove(_OLD_HISTORY_FILE)
    except OSError:
        pass


class ConnectionHistory:
    """
    Manages persistent storage of previously connected IPs with custom usernames.

    File format (connection_history.json):
    {
        "connections": [
            {
                "ip": "192.168.1.42",
                "username": "Simon's Room",
                "last_used": "2026-04-30T12:45:00",
                "success": true
            },
            ...
        ]
    }
    """

    MAX_ENTRIES = 10

    def __init__(self) -> None:
        _migrate_old_file()
        self.connections: list[dict] = []
        self._load()

    def _load(self) -> None:
        """Load connection history from JSON file."""
        if not os.path.exists(HISTORY_FILE):
            self.connections = []
            return

        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.connections = data.get("connections", [])
        except (json.JSONDecodeError, IOError):
            self.connections = []

    def _save(self) -> None:
        """Save connection history to JSON file."""
        try:
            with open(HISTORY_FILE, "w", encoding="utf-8") as f:
                json.dump({"connections": self.connections}, f, indent=2)
        except IOError as e:
            print(f"Failed to save connection history: {e}")

    def add_or_update(self, ip: str, username: str = "", success: bool = True) -> None:
        """
        Add a new connection or update last_used timestamp if already exists.

        Args:
            ip: IP address (e.g., "192.168.1.42")
            username: Custom name for this connection (defaults to username)
            success: Whether connection was successful
        """
        existing = None
        for conn in self.connections:
            if conn["ip"] == ip:
                existing = conn
                break

        now = datetime.now().isoformat()

        if existing:
            existing["last_used"] = now
            existing["success"] = success
            if username:
                existing["username"] = username
        else:
            new_entry = {
                "ip": ip,
                "username": username or f"Host {ip}",
                "last_used": now,
                "success": success,
            }
            self.connections.insert(0, new_entry)
            self.connections = self.connections[:self.MAX_ENTRIES]

        self.connections.sort(
            key=lambda x: (not x.get("success", False), x.get("last_used", "")),
            reverse=True,
        )
        self._save()

    def get_recent(self, limit: int = 5) -> list[dict]:
        """
        Get recently used successful connections.

        Returns:
            List of connection dicts with "ip", "username", "last_used"
        """
        successful = [c for c in self.connections if c.get("success", False)]
        return successful[:limit]

    def get_all(self) -> list[dict]:
        """Get all stored connections."""
        return self.connections.copy()

    def find_by_ip(self, ip: str) -> Optional[dict]:
        """Find a connection entry by IP address."""
        for conn in self.connections:
            if conn["ip"] == ip:
                return conn.copy()
        return None

    def remove(self, ip: str) -> bool:
        """
        Remove a connection from history.

        Returns:
            True if found and removed, False otherwise
        """
        for i, conn in enumerate(self.connections):
            if conn["ip"] == ip:
                self.connections.pop(i)
                self._save()
                return True
        return False

    def clear(self) -> None:
        """Clear all history."""
        self.connections = []
        self._save()

    def update_username(self, ip: str, new_username: str) -> bool:
        """
        Update the custom username for a connection.

        Returns:
            True if found and updated, False otherwise
        """
        for conn in self.connections:
            if conn["ip"] == ip:
                conn["username"] = new_username
                self._save()
                return True
        return False
