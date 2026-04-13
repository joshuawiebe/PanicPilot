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
        self._inbox: Optional[dict] = None      # neuester Client-Input
        self._connected  = False
        self._running    = False
        self._new_client = False  # True einmal nach jedem Accept → got_new_client()

    # ─── Öffentliche API ─────────────────────────────────────────────────────

    def start(self) -> None:
        """
        Startet den Accept-Thread.
        Kehrt sofort zurück — der Game-Loop kann weiterlaufen.
        """
        self._running = True
        t = threading.Thread(target=self._accept_loop, daemon=True, name="host-accept")
        t.start()
        log.info(f"Host wartet auf Port {self._port} …")

    def send_state(self, state_dict: dict) -> None:
        """Schickt Spielzustand an verbundenen Client. Sicher bei Disconnect."""
        with self._lock:
            sock = self._client_sock
        if sock is None:
            return
        try:
            send_message(sock, state_dict)
        except (OSError, ConnectionError) as e:
            log.warning(f"send_state fehlgeschlagen: {e}")
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
        self.send_state({"type": "map", **track_data})

    def shutdown(self) -> None:
        self._running = False
        self._mark_disconnected()

    # ─── Interne Threads ─────────────────────────────────────────────────────

    def _accept_loop(self) -> None:
        """Wartet auf eine Client-Verbindung, startet dann den Recv-Thread."""
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            server.bind(("", self._port))
            server.listen(1)
            server.settimeout(1.0)   # damit shutdown() nicht ewig wartet

            while self._running:
                try:
                    client, addr = server.accept()
                except socket.timeout:
                    continue
                log.info(f"Client verbunden: {addr}")
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
                log.info("Client getrennt – warte auf neuen Client …")
        except OSError as e:
            log.error(f"Server-Socket Fehler: {e}")
        finally:
            server.close()

    def _recv_loop(self, sock: socket.socket) -> None:
        """Empfängt Client-Inputs in einer Schleife (blockierend in eigenem Thread)."""
        try:
            while self._running:
                msg = recv_message(sock)
                with self._lock:
                    self._inbox = msg   # immer nur neuesten behalten
        except (ConnectionError, OSError, json.JSONDecodeError) as e:
            log.warning(f"recv_loop beendet: {e}")
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
        self._inbox: Optional[dict] = None        # neuester State
        self._map_inbox: Optional[dict] = None    # einmaliger Map-Handshake
        self._connected  = False

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
            log.warning(f"Verbindung zu {self._host_ip}:{self._port} fehlgeschlagen: {e}")
            sock.close()
            return False

        sock.settimeout(None)   # auf blockierend für Recv-Thread umstellen
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        with self._lock:
            self._sock      = sock
            self._connected = True

        t = threading.Thread(target=self._recv_loop, daemon=True, name="client-recv")
        t.start()
        log.info(f"Verbunden mit {self._host_ip}:{self._port}")
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
            log.warning(f"send_input fehlgeschlagen: {e}")
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
          "map"       → _map_inbox (einmaliger Handshake)
          sonst       → _inbox     (laufender State-Strom)
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
                    else:
                        self._inbox = msg
        except (ConnectionError, OSError, json.JSONDecodeError) as e:
            log.warning(f"client recv_loop beendet: {e}")
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
