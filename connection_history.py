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
        self._ip_index: dict[str, dict] = {}
        self._load()

    def _load(self) -> None:
        """Load connection history from JSON file."""
        if not os.path.exists(HISTORY_FILE):
            self.connections = []
            self._ip_index = {}
            return

        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.connections = data.get("connections", [])
                self._rebuild_index()
        except (json.JSONDecodeError, IOError):
            self.connections = []
            self._ip_index = {}

    def _rebuild_index(self) -> None:
        """Rebuild the IP index from the connections list."""
        self._ip_index = {conn["ip"]: conn for conn in self.connections}

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
        now = datetime.now().isoformat()
        existing = self._ip_index.get(ip)

        if existing:
            existing["last_used"] = now
            existing["success"] = success
            if username:
                existing["username"] = username
            # Move to front
            self.connections.remove(existing)
            self.connections.insert(0, existing)
        else:
            new_entry = {
                "ip": ip,
                "username": username or f"Host {ip}",
                "last_used": now,
                "success": success,
            }
            self.connections.insert(0, new_entry)
            self._ip_index[ip] = new_entry
            self.connections = self.connections[:self.MAX_ENTRIES]

        self.connections.sort(
            key=lambda x: (not x.get("success", False), x.get("last_used", "")),
            reverse=True,
        )
        self._rebuild_index()
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
        conn = self._ip_index.get(ip)
        return conn.copy() if conn else None

    def remove(self, ip: str) -> bool:
        """
        Remove a connection from history.

        Returns:
            True if found and removed, False otherwise
        """
        if ip in self._ip_index:
            conn = self._ip_index.pop(ip)
            self.connections.remove(conn)
            self._save()
            return True
        return False

    def clear(self) -> None:
        """Clear all history."""
        self.connections = []
        self._ip_index = {}
        self._save()

    def update_username(self, ip: str, new_username: str) -> bool:
        """
        Update the custom username for a connection.

        Returns:
            True if found and updated, False otherwise
        """
        conn = self._ip_index.get(ip)
        if conn:
            conn["username"] = new_username
            self._save()
            return True
        return False
