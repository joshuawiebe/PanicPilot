# =============================================================================
#  net.py  –  Panic Pilot | Netzwerk-Schicht (Phase 2)
# =============================================================================
#
#  Protokoll:
#    TCP + length-prefixed JSON
#    ┌──────────┬──────────────────────────────┐
#    │ 4 Bytes  │  N Bytes                     │
#    │ uint32   │  UTF-8 JSON payload          │
#    │ big-end. │                              │
#    └──────────┴──────────────────────────────┘
#    Das Längen-Präfix löst TCP-Fragmentierung sauber auf —
#    kein Suchen nach Trennzeichen nötig.
#
#  Threading-Modell:
#    Jede Connection hat EINEN Background-Thread, der blockierend liest.
#    Das Spielfeld dreht sich damit nie auf recv() wartend.
#    Der Game-Loop ruft nur get_*()/send_*() auf → nie blockierend.
#    Thread → Game-Loop Übergabe: threading.Lock + neuestes Paket (inbox).
#
#  IP-Konfiguration:
#    HOST_IP in host.py oben ändern oder leer lassen für automatische Erkennung.
#    CLIENT_HOST_IP in client.py auf die IP des Hosts setzen.
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


# ── Low-Level Stream-Helfer ───────────────────────────────────────────────────

def _recv_exact(sock: socket.socket, n: int) -> bytes:
    """Liest exakt n Bytes aus einem TCP-Socket (blockierend)."""
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("Socket geschlossen (recv=0)")
        buf += chunk
    return buf


def send_message(sock: socket.socket, data: dict) -> None:
    """Serialisiert dict als JSON und schickt es length-prefixed."""
    payload = json.dumps(data, separators=(",", ":")).encode("utf-8")
    header  = struct.pack(HEADER_FMT, len(payload))
    sock.sendall(header + payload)


def recv_message(sock: socket.socket) -> dict:
    """Empfängt eine length-prefixed Nachricht (blockierend)."""
    raw_len  = _recv_exact(sock, HEADER_SIZE)
    msg_len, = struct.unpack(HEADER_FMT, raw_len)
    payload  = _recv_exact(sock, msg_len)
    return json.loads(payload.decode("utf-8"))


# ── HostConnection ────────────────────────────────────────────────────────────

class HostConnection:
    """
    Server-Seite: bindet einen TCP-Port, akzeptiert einen Client.

    Hintergrund-Thread: empfängt Client-Inputs.
    Game-Loop:
        send_state(state_dict)         → schickt Spielzustand an Client
        get_client_input() → dict|None → letzter empfangener Client-Input
        is_connected() → bool
    """

    def __init__(self, port: int) -> None:
        self._port       = port
        self._client_sock: Optional[socket.socket] = None
        self._lock       = threading.Lock()
        self._inbox: Optional[dict] = None
        self._client_lobby_inbox: Optional[dict] = None
        self._client_left           = False
        self._client_back_lobby     = False
        self._client_requests_state = False
        self._client_ready_for_map  = False   # Phase 11.2: 3-Wege-Handshake
        self._mode_change_confirm   = False
        self._mode_change_deny      = False
        self._connected  = False
        self._running    = False
        self._new_client = False

    # ─── Öffentliche API ─────────────────────────────────────────────────────

    def start(self) -> None:
        """
        Startet den Accept-Thread.
        Kehrt zurück NACHDEM der Socket gebunden und bereit ist.
        """
        self._running = True
        # Event um zu signalisieren dass der Socket bereit ist
        ready_event = threading.Event()
        t = threading.Thread(target=self._accept_loop, args=(ready_event,), daemon=True, name="host-accept")
        t.start()
        # Warte bis der Socket tatsächlich gebunden ist (max 3 Sekunden)
        if not ready_event.wait(timeout=3.0):
            log.error("Host socket timed out while binding")
        else:
            log.info(f"Host listening on port {self._port} …")

    def send_state(self, state_dict: dict) -> None:
        """Schickt Spielzustand an verbundenen Client. Sicher bei Disconnect."""
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
        Gibt den letzten empfangenen Client-Input zurück (und leert den Puffer).
        Gibt None zurück falls noch kein Input vorliegt.
        Nie blockierend.
        """
        with self._lock:
            inp, self._inbox = self._inbox, None
        return inp

    def is_connected(self) -> bool:
        with self._lock:
            return self._connected

    def got_new_client(self) -> bool:
        """
        True (einmalig) wenn seit dem letzten Aufruf ein neuer Client akzeptiert
        wurde. Für den Map-Handshake bestimmt. Nie blockierend.
        """
        with self._lock:
            flag, self._new_client = self._new_client, False
        return flag

    def send_map(self, track_data: dict) -> None:
        """
        Schickt Map-Daten EINMALIG an den Client (Handshake, nicht pro Frame!).
        "type": "map" wird hinzugefügt, damit der Client die Nachricht
        vom normalen State-Strom unterscheiden kann.
        """
        print("DEBUG net: Host send_map()")
        self.send_state({"type": "map", **track_data})

    def send_lobby(self, data: dict) -> None:
        """Sendet Host-Lobby-Status (Klasse, Modus-Info) an Client."""
        self.send_state({"type": "lobby_host", **data})

    def send_start(self, data: dict) -> None:
        """Sendet Start-Signal mit Spielparametern an Client."""
        print("DEBUG net: Host send_start()")
        self.send_state({"type": "start", **data})

    def send_kick(self) -> None:
        """Kicks the client from the lobby."""
        self.send_state({"type": "kick"})

    def send_back_to_lobby(self) -> None:
        """Informs the client that the game is returning to the lobby."""
        self.send_state({"type": "back_to_lobby"})

    def send_mode_change_request(self, new_mode: int) -> None:
        """Asks the navigator to accept a mode switch post-race."""
        self.send_state({"type": "mode_change_request", "new_mode": new_mode})

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

    def client_wants_lobby(self) -> bool:
        """True (einmalig) wenn Client das Rennen zur Lobby abbrechen will."""
        with self._lock:
            flag, self._client_back_lobby = self._client_back_lobby, False
        return flag

    def client_requests_state(self) -> bool:
        """
        True (einmalig) wenn Client einen sofortigen Lobby-Snapshot anfordert.
        Passiert direkt nach TCP-Connect als Handshake-Bestätigung.
        """
        with self._lock:
            flag, self._client_requests_state = self._client_requests_state, False
        return flag

    def client_ready_for_map(self) -> bool:
        """
        True (einmalig) wenn Client bereit ist, Streckendaten zu empfangen.
        Teil des 3-Wege-Handshakes (Phase 11.2).
        """
        with self._lock:
            flag, self._client_ready_for_map = self._client_ready_for_map, False
        return flag

    def reset_lobby_flags(self) -> None:
        """
        Setzt alle transienten Signalflags zurück.
        Muss nach Spielende aufgerufen werden, bevor die Lobby erneut geöffnet wird,
        damit alte Signale den nächsten Startvorgang nicht verfälschen.
        """
        with self._lock:
            self._inbox                 = None
            self._client_lobby_inbox    = None
            self._client_left           = False
            self._client_back_lobby     = False
            self._client_requests_state = False
            self._client_ready_for_map  = False
            self._mode_change_confirm   = False
            self._mode_change_deny      = False
            self._new_client            = False

    def get_client_lobby(self) -> Optional[dict]:
        """Gibt letztes Lobby-Update des Clients zurück (leert Puffer)."""
        with self._lock:
            msg, self._client_lobby_inbox = self._client_lobby_inbox, None
        return msg

    def client_left(self) -> bool:
        """True (einmalig) wenn Client die Lobby verlassen hat."""
        with self._lock:
            flag, self._client_left = self._client_left, False
        return flag

    def shutdown(self) -> None:
        self._running = False
        self._mark_disconnected()

    # ─── Interne Threads ─────────────────────────────────────────────────────

    def _accept_loop(self, ready_event: threading.Event) -> None:
        """Wartet auf eine Client-Verbindung, startet dann den Recv-Thread."""
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
                    self._new_client  = True   # für got_new_client()
                # Recv-Thread für diesen Client
                rt = threading.Thread(target=self._recv_loop, args=(client,),
                                      daemon=True, name="host-recv")
                rt.start()
                rt.join()   # wartet bis Client trennt, dann erneut accept
                log.info("Client disconnected – waiting for new client …")
        except OSError as e:
            log.error(f"Server-Socket Fehler: {e}")
            ready_event.set()  # Setze event auch bei Fehler damit start() nicht hängt
        finally:
            server.close()

    def _recv_loop(self, sock: socket.socket) -> None:
        """Empfängt Client-Inputs in einer Schleife (blockierend in eigenem Thread)."""
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
                    else:
                        self._inbox = msg   # Spiel-Input: immer nur neuesten behalten
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

    Hintergrund-Thread: empfängt Spielzustände vom Host.
    Game-Loop:
        send_input(input_dict)      → schickt W/S-Input an Host
        get_state() → dict|None     → letzter empfangener Spielzustand
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
        self._kick_flag              = False
        self._host_back_lobby        = False
        self._mode_change_request    : Optional[int] = None
        self._connected              = False

    # ─── Öffentliche API ─────────────────────────────────────────────────────

    def connect(self, timeout: float = 5.0) -> bool:
        """
        Versucht einmalig zu verbinden. Gibt True bei Erfolg zurück.
        Startet nach Erfolg den Recv-Hintergrund-Thread.
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
        """Gibt letzten State zurück (und leert Puffer). Nie blockierend."""
        with self._lock:
            s, self._inbox = self._inbox, None
        return s

    def get_map(self) -> Optional[dict]:
        """
        Gibt Map-Handshake-Daten zurück (und leert Puffer).
        Nur ein Mal befüllt (beim ersten Connect). Nie blockierend.
        """
        with self._lock:
            m, self._map_inbox = self._map_inbox, None
        return m

    def send_lobby(self, data: dict) -> None:
        """Sendet Client-Lobby-Status (Klasse) an Host."""
        self.send_input({"type": "lobby_client", **data})

    def send_leave(self) -> None:
        """Teilt dem Host mit, dass Client die Lobby verlässt."""
        self.send_input({"type": "leave"})

    def send_request_lobby_state(self) -> None:
        """Fordert vom Host einen sofortigen Lobby-Snapshot an."""
        self.send_input({"type": "request_lobby_state"})

    def get_host_lobby(self) -> Optional[dict]:
        """Gibt letztes Lobby-Update des Hosts zurück (leert Puffer)."""
        with self._lock:
            msg, self._host_lobby_inbox = self._host_lobby_inbox, None
        return msg

    def get_start(self) -> Optional[dict]:
        """Gibt Start-Signal zurück (leert Puffer). None wenn noch kein Start."""
        with self._lock:
            s, self._start_inbox = self._start_inbox, None
        return s

    def was_kicked(self) -> bool:
        """True (einmalig) wenn Host den Client gekickt hat."""
        with self._lock:
            flag, self._kick_flag = self._kick_flag, False
        return flag

    def send_back_to_lobby(self) -> None:
        """Informiert den Host, dass der Client das Rennen zur Lobby abbricht."""
        self.send_input({"type": "back_to_lobby"})

    def host_wants_lobby(self) -> bool:
        """True (einmalig) wenn Host das Rennen zur Lobby zurückkehren will."""
        with self._lock:
            flag, self._host_back_lobby = self._host_back_lobby, False
        return flag

    def send_ready_for_map(self) -> None:
        """
        Sendet 'ready_for_map' an Host – Teil des 3-Wege-Handshakes (Phase 11.2).
        Muss nach Empfang von 'start' gesendet werden, bevor Host die Karte schickt.
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

    def reset_lobby_flags(self) -> None:
        """
        Setzt alle transienten Signalflags zurück (Phase 11.2).
        Aufrufen wenn Client aus dem Spiel zurück in die Lobby geht.
        """
        with self._lock:
            self._inbox                  = None
            self._map_inbox              = None
            self._host_lobby_inbox       = None
            self._start_inbox            = None
            self._kick_flag              = False
            self._host_back_lobby        = False
            self._mode_change_request    = None

    def is_connected(self) -> bool:
        with self._lock:
            return self._connected

    def shutdown(self) -> None:
        self._mark_disconnected()

    # ─── Interner Thread ─────────────────────────────────────────────────────

    def _recv_loop(self) -> None:
        """
        Empfängt Pakete vom Host (blockierend in eigenem Thread).
        Routing nach "type"-Feld:
          "map"          → _map_inbox     (einmaliger Handshake)
          "lobby_host"   → _host_lobby_inbox
          "start"        → _start_inbox
          "kick"         → _kick_flag
          sonst          → _inbox         (laufender State-Strom)
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
