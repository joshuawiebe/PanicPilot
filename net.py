# =============================================================================
#  net.py  –  Panic Pilot | Network layer (Phase 2)
# =============================================================================
#
#  Protocol:
#    TCP + length-prefixed JSON
#    ┌──────────┬──────────────────────────────┐
#    │ 4 Bytes  │  N Bytes                     │
#    │ uint32   │  UTF-8 JSON payload          │
#    │ big-end. │                              │
#    └──────────┴──────────────────────────────┘
#    The length prefix cleanly resolves TCP fragmentation —
#    no need to search for delimiters.
#
#  Threading model:
#    Each connection has ONE background thread that reads blocking.
#    The game loop never blocks waiting on recv().
#    The game loop only calls get_*()/send_*() → never blocking.
#    Thread → game loop handoff: threading.Lock + latest packet (inbox).
#
#  IP configuration:
#    Change HOST_IP in host.py above or leave empty for automatic detection.
#    Set CLIENT_HOST_IP in client.py to the host's IP address.
# =============================================================================
from __future__ import annotations

import json
import socket
import struct
import threading
import logging
from typing import Optional

log = logging.getLogger("net")

# ── Konstanten ────────────────────────────────────────────────────────────────
HEADER_FMT  = ">I"        # big-endian unsigned int (4 Bytes)
HEADER_SIZE = struct.calcsize(HEADER_FMT)
RECV_BUFSIZE = 4096


# ── Low-level stream helpers ────────────────────────────────────────────────

def _recv_exact(sock: socket.socket, n: int) -> bytes:
    """Reads exactly n bytes from a TCP socket (blocking)."""
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("Socket closed (recv=0)")
        buf += chunk
    return buf


def send_message(sock: socket.socket, data: dict) -> None:
    """Serializes dict as JSON and sends it length-prefixed."""
    payload = json.dumps(data, separators=(",", ":")).encode("utf-8")
    header  = struct.pack(HEADER_FMT, len(payload))
    sock.sendall(header + payload)


def recv_message(sock: socket.socket) -> dict:
    """Receives a length-prefixed message (blocking)."""
    raw_len  = _recv_exact(sock, HEADER_SIZE)
    msg_len, = struct.unpack(HEADER_FMT, raw_len)
    payload  = _recv_exact(sock, msg_len)
    return json.loads(payload.decode("utf-8"))


# ── HostConnection ────────────────────────────────────────────────────────────

class HostConnection:
    """
    Server side: binds a TCP port, accepts one client.

    Background thread: receives client inputs.
    Game loop:
        send_state(state_dict)         → sends game state to client
        get_client_input() → dict|None → last received client input
        is_connected() → bool
    """

    def __init__(self, port: int) -> None:
        self._port       = port
        self._client_sock: Optional[socket.socket] = None
        self._lock       = threading.Lock()
        self._inbox: Optional[dict] = None
        self._client_lobby_inbox: Optional[dict] = None
        self._chat_inbox: list[dict] = []  # Chat messages from client
        self._client_left           = False
        self._client_back_lobby     = False
        self._client_requests_state = False
        self._client_ready_for_map  = False   # Phase 11.2: 3-way handshake
        self._mode_change_confirm   = False
        self._mode_change_deny      = False
        self._track_length_change_confirm = False
        self._track_length_change_deny    = False
        self._connected  = False
        self._running    = False
        self._new_client = False

    # ─── Public API ─────────────────────────────────────────────────────────────

    def start(self) -> None:
        """
        Starts the accept thread.
        Returns AFTER the socket is bound and ready.
        """
        self._running = True
        # Event to signal that the socket is ready
        ready_event = threading.Event()
        t = threading.Thread(target=self._accept_loop, args=(ready_event,), daemon=True, name="host-accept")
        t.start()
        # Wait until socket is actually bound (max 3 seconds)
        if not ready_event.wait(timeout=3.0):
            log.error("Host socket timed out while binding")
        else:
            log.info(f"Host listening on port {self._port} …")

    def send_state(self, state_dict: dict) -> None:
        """Sends game state to connected client. Safe on disconnect."""
        with self._lock:
            sock = self._client_sock
        if sock is None:
            return
        try:
            send_message(sock, state_dict)
        except (OSError, ConnectionError) as e:
            log.warning(f"send_state failed: {e}")
            self._mark_disconnected()

    def get_client_input(self) -> Optional[dict]:
        """
        Returns the last received client input (and clears the buffer).
        Returns None if no input is available yet.
        Never blocking.
        """
        with self._lock:
            inp, self._inbox = self._inbox, None
        return inp

    def is_connected(self) -> bool:
        with self._lock:
            return self._connected

    def got_new_client(self) -> bool:
        """
        True (one-time) when a new client has been accepted since the last call.
        Used for the map handshake. Never blocking.
        """
        with self._lock:
            flag, self._new_client = self._new_client, False
        return flag

    def send_map(self, track_data: dict) -> None:
        """
        Sends map data ONE-TIME to client (handshake, not per frame!).
        "type": "map" is added so the client can distinguish the message
        from the normal state stream.
        """
        print("DEBUG net: Host send_map()")
        self.send_state({"type": "map", **track_data})

    def send_lobby(self, data: dict) -> None:
        """Sends host lobby status (class, mode info) to client."""
        self.send_state({"type": "lobby_host", **data})

    def send_start(self, data: dict) -> None:
        """Sends start signal with game parameters to client."""
        print("DEBUG net: Host send_start()")
        self.send_state({"type": "start", **data})

    def send_kick(self) -> None:
        """Kicks the client from the lobby."""
        self.send_state({"type": "kick"})

    def send_chat(self, text: str, username: str = "Host") -> None:
        """Sends a chat message to the client."""
        self.send_state({"type": "chat", "text": text, "sender": username})

    def get_client_chat(self) -> Optional[dict]:
        """Returns the next chat message from client (FIFO)."""
        with self._lock:
            if self._chat_inbox:
                return self._chat_inbox.pop(0)
        return None

    def send_back_to_lobby(self) -> None:
        """Informs the client that the game is returning to the lobby."""
        self.send_state({"type": "back_to_lobby"})

    def send_mode_change_request(self, new_mode: int) -> None:
        """Asks the navigator to accept a mode switch post-race."""
        self.send_state({"type": "mode_change_request", "new_mode": new_mode})

    def send_track_length_change_request(self, new_length: int) -> None:
        """Asks the navigator to accept a track length change."""
        self.send_state({"type": "track_length_change_request", "new_length": new_length})

    def client_confirmed_mode_change(self) -> bool:
        """True (once) if the navigator accepted the mode change request."""
        with self._lock:
            flag, self._mode_change_confirm = self._mode_change_confirm, False
        return flag

    def client_denied_mode_change(self) -> bool:
        """True (once) if the navigator rejected the mode change request."""
        with self._lock:
            flag, self._mode_change_deny = self._mode_change_deny, False
        return flag

    def client_confirmed_track_length_change(self) -> bool:
        """True (once) if the navigator accepted the track length change request."""
        with self._lock:
            flag, self._track_length_change_confirm = self._track_length_change_confirm, False
        return flag

    def client_denied_track_length_change(self) -> bool:
        """True (once) if the navigator rejected the track length change request."""
        with self._lock:
            flag, self._track_length_change_deny = self._track_length_change_deny, False
        return flag

    def client_wants_lobby(self) -> bool:
        """True (one-time) when client wants to abort race back to lobby."""
        with self._lock:
            flag, self._client_back_lobby = self._client_back_lobby, False
        return flag

    def client_requests_state(self) -> bool:
        """
        True (one-time) when client requests immediate lobby snapshot.
        Happens right after TCP connect as handshake confirmation.
        """
        with self._lock:
            flag, self._client_requests_state = self._client_requests_state, False
        return flag

    def client_ready_for_map(self) -> bool:
        """
        True (one-time) when client is ready to receive track data.
        Part of 3-way handshake (Phase 11.2).
        """
        with self._lock:
            flag, self._client_ready_for_map = self._client_ready_for_map, False
        return flag

    def reset_lobby_flags(self) -> None:
        """
        Resets all transient signal flags.
        Must be called after game ends before lobby is reopened,
        so old signals do not corrupt the next startup.
        """
        with self._lock:
            self._inbox                 = None
            self._client_lobby_inbox    = None
            self._chat_inbox            = []
            self._client_left           = False
            self._client_back_lobby     = False
            self._client_requests_state = False
            self._client_ready_for_map  = False
            self._mode_change_confirm   = False
            self._mode_change_deny      = False
            self._track_length_change_confirm = False
            self._track_length_change_deny    = False
            self._new_client            = False

    def get_client_lobby(self) -> Optional[dict]:
        """Returns last lobby update from client (clears buffer)."""
        with self._lock:
            msg, self._client_lobby_inbox = self._client_lobby_inbox, None
        return msg

    def client_left(self) -> bool:
        """True (one-time) when client has left the lobby."""
        with self._lock:
            flag, self._client_left = self._client_left, False
        return flag

    def shutdown(self) -> None:
        self._running = False
        self._mark_disconnected()

    # ─── Interne Threads ─────────────────────────────────────────────────────

    def _accept_loop(self, ready_event: threading.Event) -> None:
        """Waits for a client connection, then starts the recv thread."""
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            server.bind(("", self._port))
            server.listen(1)
            server.settimeout(1.0)   # damit shutdown() nicht ewig wartet
            # Signalisiere dass der Socket bereit ist
            ready_event.set()

            while self._running:
                try:
                    client, addr = server.accept()
                except socket.timeout:
                    continue
                log.info(f"Client connected: {addr}")
                client.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                with self._lock:
                    self._client_sock = client
                    self._connected   = True
                    self._new_client  = True   # for got_new_client()
                # Recv thread for this client
                rt = threading.Thread(target=self._recv_loop, args=(client,),
                                      daemon=True, name="host-recv")
                rt.start()
                rt.join()   # wartet bis Client trennt, dann erneut accept
                log.info("Client disconnected – waiting for new client …")
        except OSError as e:
            log.error(f"Server socket error: {e}")
            ready_event.set()  # Set event even on error so start() does not hang
        finally:
            server.close()

    def _recv_loop(self, sock: socket.socket) -> None:
        """Receives client inputs in a loop (blocking in own thread)."""
        try:
            while self._running:
                msg = recv_message(sock)
                msg_type = msg.get("type", "")
                with self._lock:
                    if msg_type == "lobby_client":
                        self._client_lobby_inbox = msg
                    elif msg_type == "leave":
                        self._client_left = True
                    elif msg_type == "back_to_lobby":
                        self._client_back_lobby = True
                    elif msg_type == "request_lobby_state":
                        self._client_requests_state = True
                    elif msg_type == "ready_for_map":
                        self._client_ready_for_map = True
                        print("DEBUG net: Host received ready_for_map from client")
                    elif msg_type == "mode_change_confirm":
                        self._mode_change_confirm = True
                    elif msg_type == "mode_change_deny":
                        self._mode_change_deny = True
                    elif msg_type == "track_length_change_confirm":
                        self._track_length_change_confirm = True
                    elif msg_type == "track_length_change_deny":
                        self._track_length_change_deny = True
                    elif msg_type == "chat":
                        self._chat_inbox.append(msg)
                    else:
                        self._inbox = msg   # Game input: always keep only the newest
        except (ConnectionError, OSError, json.JSONDecodeError) as e:
            log.warning(f"recv_loop ended: {e}")
        finally:
            self._mark_disconnected()

    def _mark_disconnected(self) -> None:
        with self._lock:
            self._connected = False
            if self._client_sock:
                try:
                    self._client_sock.close()
                except OSError:
                    pass
                self._client_sock = None


# ── ClientConnection ──────────────────────────────────────────────────────────

class ClientConnection:
    """
    Client-Seite: verbindet sich zum Host.

    Background thread: receives game states from host.
    Game-Loop:
        send_input(input_dict)      → schickt W/S-Input an Host
        get_state() → dict|None     → last received game state
        is_connected() → bool
    """

    def __init__(self, host_ip: str, port: int) -> None:
        self._host_ip    = host_ip
        self._port       = port
        self._sock: Optional[socket.socket] = None
        self._lock       = threading.Lock()
        self._inbox: Optional[dict] = None
        self._map_inbox: Optional[dict] = None
        self._host_lobby_inbox: Optional[dict] = None
        self._start_inbox: Optional[dict] = None
        self._chat_inbox: list[dict] = []  # Chat messages from host
        self._kick_flag              = False
        self._host_back_lobby        = False
        self._mode_change_request    : Optional[int] = None
        self._track_length_change_request: Optional[int] = None
        self._connected              = False

    # ─── Public API ─────────────────────────────────────────────────────────────

    def connect(self, timeout: float = 5.0) -> bool:
        """
        Attempts to connect once. Returns True on success.
        Starts the recv background thread after success.
        """
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        try:
            sock.connect((self._host_ip, self._port))
        except (ConnectionRefusedError, socket.timeout, OSError) as e:
            log.warning(f"Connection to {self._host_ip}:{self._port} failed: {e}")
            sock.close()
            return False

        sock.settimeout(None)
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        with self._lock:
            self._sock      = sock
            self._connected = True

        t = threading.Thread(target=self._recv_loop, daemon=True, name="client-recv")
        t.start()
        log.info(f"Verbunden mit {self._host_ip}:{self._port}")

        # Phase 11.1: Sofort-Handshake – Host antwortet mit aktuellem Lobby-Zustand
        try:
            send_message(sock, {"type": "request_lobby_state"})
        except (OSError, ConnectionError):
            pass

        return True

    def send_input(self, input_dict: dict) -> None:
        """Schickt aktuellen Input an Host. Sicher bei Disconnect."""
        with self._lock:
            sock = self._sock
        if sock is None:
            return
        try:
            send_message(sock, input_dict)
        except (OSError, ConnectionError) as e:
            log.warning(f"send_input failed: {e}")
            self._mark_disconnected()

    def get_state(self) -> Optional[dict]:
        """Returns last state (and clears buffer). Never blocking."""
        with self._lock:
            s, self._inbox = self._inbox, None
        return s

    def get_map(self) -> Optional[dict]:
        """
        Returns map handshake data (and clears buffer).
        Only filled once (on first connect). Never blocking.
        """
        with self._lock:
            m, self._map_inbox = self._map_inbox, None
        return m

    def send_lobby(self, data: dict) -> None:
        """Sends client lobby status (class) to host."""
        self.send_input({"type": "lobby_client", **data})

    def send_chat(self, text: str, username: str = "Client") -> None:
        """Sends a chat message to the host."""
        self.send_input({"type": "chat", "text": text, "sender": username})

    def get_host_chat(self) -> Optional[dict]:
        """Returns the next chat message from host (FIFO)."""
        with self._lock:
            if self._chat_inbox:
                return self._chat_inbox.pop(0)
        return None

    def send_leave(self) -> None:
        """Informs host that client is leaving the lobby."""
        self.send_input({"type": "leave"})

    def send_request_lobby_state(self) -> None:
        """Requests immediate lobby snapshot from host."""
        self.send_input({"type": "request_lobby_state"})

    def get_host_lobby(self) -> Optional[dict]:
        """Returns last lobby update from host (clears buffer)."""
        with self._lock:
            msg, self._host_lobby_inbox = self._host_lobby_inbox, None
        return msg

    def get_start(self) -> Optional[dict]:
        """Returns start signal (clears buffer). None if no start yet."""
        with self._lock:
            s, self._start_inbox = self._start_inbox, None
        return s

    def was_kicked(self) -> bool:
        """True (one-time) when host kicked the client."""
        with self._lock:
            flag, self._kick_flag = self._kick_flag, False
        return flag

    def send_back_to_lobby(self) -> None:
        """Informs host that client is aborting race back to lobby."""
        self.send_input({"type": "back_to_lobby"})

    def host_wants_lobby(self) -> bool:
        """True (one-time) when host wants to return race to lobby."""
        with self._lock:
            flag, self._host_back_lobby = self._host_back_lobby, False
        return flag

    def send_ready_for_map(self) -> None:
        """
        Sendet 'ready_for_map' an Host – Part of 3-way handshake (Phase 11.2).
        Must be sent after receiving 'start', before host sends the map.
        """
        self.send_input({"type": "ready_for_map"})

    def get_mode_change_request(self) -> Optional[int]:
        """Returns requested new_mode (once) if host sent a mode change request."""
        with self._lock:
            val, self._mode_change_request = self._mode_change_request, None
        return val

    def send_mode_change_confirm(self) -> None:
        """Accept the host's mode change request."""
        self.send_input({"type": "mode_change_confirm"})

    def send_mode_change_deny(self) -> None:
        """Reject the host's mode change request."""
        self.send_input({"type": "mode_change_deny"})

    def get_track_length_change_request(self) -> Optional[int]:
        """Returns requested new track length (once) if host sent a track length change request."""
        with self._lock:
            val, self._track_length_change_request = self._track_length_change_request, None
        return val

    def send_track_length_change_confirm(self) -> None:
        """Accept the host's track length change request."""
        self.send_input({"type": "track_length_change_confirm"})

    def send_track_length_change_deny(self) -> None:
        """Reject the host's track length change request."""
        self.send_input({"type": "track_length_change_deny"})

    def reset_lobby_flags(self) -> None:
        """
        Resets all transient signal flags (Phase 11.2).
        Call when client returns from game to lobby.
        """
        with self._lock:
            self._inbox                  = None
            self._map_inbox              = None
            self._host_lobby_inbox       = None
            self._start_inbox            = None
            self._chat_inbox             = []
            self._kick_flag              = False
            self._host_back_lobby        = False
            self._mode_change_request    = None
            self._track_length_change_request = None

    def is_connected(self) -> bool:
        with self._lock:
            return self._connected

    def shutdown(self) -> None:
        self._mark_disconnected()

    # ─── Interner Thread ─────────────────────────────────────────────────────

    def _recv_loop(self) -> None:
        """
        Receives packets from host (blocking in own thread).
        Routing by "type" field:
          "map"          → _map_inbox     (one-time handshake)
          "lobby_host"   → _host_lobby_inbox
          "start"        → _start_inbox
          "kick"         → _kick_flag
          else          → _inbox         (ongoing state stream)
        """
        with self._lock:
            sock = self._sock
        try:
            while True:
                msg      = recv_message(sock)
                msg_type = msg.get("type", "state")
                with self._lock:
                    if msg_type == "map":
                        self._map_inbox = msg
                        print("DEBUG net: Client received map packet")
                    elif msg_type == "lobby_host":
                        self._host_lobby_inbox = msg
                    elif msg_type == "start":
                        self._start_inbox = msg
                        print("DEBUG net: Client received start packet")
                    elif msg_type == "kick":
                        self._kick_flag = True
                    elif msg_type == "back_to_lobby":
                        self._host_back_lobby = True
                    elif msg_type == "mode_change_request":
                        self._mode_change_request = msg.get("new_mode")
                    elif msg_type == "track_length_change_request":
                        self._track_length_change_request = msg.get("new_length")
                    elif msg_type == "chat":
                        self._chat_inbox.append(msg)
                    else:
                        self._inbox = msg
        except (ConnectionError, OSError, json.JSONDecodeError) as e:
            log.warning(f"client recv_loop ended: {e}")
        finally:
            self._mark_disconnected()

    def _mark_disconnected(self) -> None:
        with self._lock:
            self._connected = False
            if self._sock:
                try:
                    self._sock.close()
                except OSError:
                    pass
                self._sock = None
