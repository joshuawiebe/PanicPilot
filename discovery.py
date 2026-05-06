# =============================================================================
#  discovery.py  –  Panic Pilot | UDP-based Room Discovery (LAN)
# =============================================================================
#
#  Phase 12.1: Connection History + Room Discovery
#
#  Implements non-blocking UDP broadcast/listen for discovering hosts
#  on the local network. Hosts broadcast beacon packets periodically,
#  clients listen for and collect available rooms.
# =============================================================================
from __future__ import annotations

import json
import socket
import struct
import threading
import logging
from typing import Optional
from datetime import datetime, timedelta

log = logging.getLogger("discovery")

# ── Constants ────────────────────────────────────────────────────────────────

DISCOVERY_PORT = 54322          # Different from TCP port
BEACON_INTERVAL = 1.5           # Send beacon every 1.5 seconds
ROOM_TIMEOUT = 8.0              # Consider room dead if no beacon for 8 seconds
DISCOVER_LISTEN_TIME = 6.0      # Initial listen time before UI shows results


# ── Room Broadcaster (Host-side) ──────────────────────────────────────────────

class RoomBroadcaster:
    """
    Broadcasts a room availability beacon via UDP.
    Runs in background thread, sends beacon periodically.
    """
    
    def __init__(self, room_name: str, tcp_port: int = 54321, verify_code: str = "") -> None:
        self.room_name = room_name
        self.tcp_port = tcp_port
        self.verify_code = verify_code
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
    
    def start(self) -> None:
        """Start broadcasting beacons."""
        if self._running:
            return
        
        with self._lock:
            self._running = True
        
        self._thread = threading.Thread(target=self._broadcast_loop, daemon=True, 
                                       name="discovery-broadcaster")
        self._thread.start()
        log.info(f"Room broadcaster started: {self.room_name}")
    
    def stop(self) -> None:
        """Stop broadcasting beacons."""
        with self._lock:
            self._running = False
        if self._thread:
            self._thread.join(timeout=3.0)
        log.info("Room broadcaster stopped")
    
    def update_room_name(self, new_name: str) -> None:
        """Update the room name for future beacons."""
        with self._lock:
            self.room_name = new_name
    
    def _broadcast_loop(self) -> None:
        """Periodically sends UDP beacon packets."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.settimeout(0.5)
        
        try:
            while True:
                with self._lock:
                    if not self._running:
                        break
                    room_name = self.room_name
                
                beacon = {
                    "type": "room_beacon",
                    "room_name": room_name,
                    "tcp_port": self.tcp_port,
                    "verify_code": self.verify_code,
                    "timestamp": datetime.now().isoformat(),
                }
                
                payload = json.dumps(beacon).encode("utf-8")
                
                try:
                    # Broadcast to 255.255.255.255:DISCOVERY_PORT
                    sock.sendto(payload, ("<broadcast>", DISCOVERY_PORT))
                except (OSError, socket.error) as e:
                    log.debug(f"Broadcast failed: {e}")
                
                # Sleep with interruptible check
                for _ in range(int(BEACON_INTERVAL * 10)):
                    with self._lock:
                        if not self._running:
                            break
                    if _ < int(BEACON_INTERVAL * 10) - 1:
                        socket.socket().close() if False else None  # dummy
                    threading.Event().wait(0.1)
        
        except Exception as e:
            log.error(f"Broadcaster error: {e}")
        finally:
            try:
                sock.close()
            except:
                pass


# ── Room Listener (Client-side) ───────────────────────────────────────────────

class RoomListener:
    """
    Listens for room beacons via UDP and collects available rooms.
    Can be started once to collect rooms, or run in background continuously.
    """
    
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._rooms: dict[str, dict] = {}  # {ip: {room_name, tcp_port, last_seen}}
        self._running = False
        self._thread: Optional[threading.Thread] = None
    
    def start_discovery(self, timeout: float = DISCOVER_LISTEN_TIME) -> None:
        """
        Start listening for beacons. Continues running in background
        to discover new rooms that appear later.
        
        Args:
            timeout: Initial delay before rooms are considered "ready" (seconds)
        """
        if self._thread and self._thread.is_alive():
            return
        
        with self._lock:
            self._running = True
        
        self._thread = threading.Thread(
            target=self._listen_loop,
            args=(timeout,),
            daemon=True,
            name="discovery-listener"
        )
        self._thread.start()
    
    def restart_discovery(self) -> None:
        """Restart the listener to refresh the room list."""
        self.stop()
        self._rooms.clear()
        self.start_discovery()
    
    def stop(self) -> None:
        """Stop listening for beacons."""
        with self._lock:
            self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)
    
    def get_rooms(self) -> list[dict]:
        """
        Get currently discovered rooms (non-blocking).
        
        Returns:
            List of {ip, room_name, tcp_port, verify_code, last_seen}
        """
        now = datetime.now()
        
        with self._lock:
            # Prune expired rooms
            expired_ips = [
                ip for ip, room in self._rooms.items()
                if (now - datetime.fromisoformat(room["last_seen"])).total_seconds() > ROOM_TIMEOUT
            ]
            for ip in expired_ips:
                del self._rooms[ip]
            
            return list(self._rooms.values())
    
    def is_listening(self) -> bool:
        """Check if listener is currently active."""
        return self._running and self._thread and self._thread.is_alive()
    
    def _listen_loop(self, initial_timeout: float) -> None:
        """Listens for room beacons continuously."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.settimeout(0.5)
        
        try:
            sock.bind(("", DISCOVERY_PORT))
        except (OSError, socket.error) as e:
            log.warning(f"Could not bind to discovery port {DISCOVERY_PORT}: {e}")
            with self._lock:
                self._running = False
            return
        
        try:
            while True:
                with self._lock:
                    if not self._running:
                        break
                
                try:
                    payload, (addr, _) = sock.recvfrom(1024)
                    msg = json.loads(payload.decode("utf-8"))
                    
                    if msg.get("type") == "room_beacon":
                        ip = addr
                        room_name = msg.get("room_name", "Unknown Room")
                        tcp_port = msg.get("tcp_port", 54321)
                        verify_code = msg.get("verify_code", "")
                        
                        with self._lock:
                            self._rooms[ip] = {
                                "ip": ip,
                                "room_name": room_name,
                                "tcp_port": tcp_port,
                                "verify_code": verify_code,
                                "last_seen": datetime.now().isoformat(),
                            }
                
                except (socket.timeout, json.JSONDecodeError):
                    pass
                except Exception as e:
                    log.debug(f"Listener error: {e}")
        
        except Exception as e:
            log.error(f"Listener fatal error: {e}")
        finally:
            try:
                sock.close()
            except:
                pass
            with self._lock:
                self._running = False
