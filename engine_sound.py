# =============================================================================
#  engine_sound.py  –  Adaptive Engine Sound Synthesis (basierend auf
#                          engine-sound-simulator von jgardner8)
# =============================================================================
#
#  Generiert realistische Motor-Sounds basierend auf:
#    - RPM (U/min des Motors)
#    - Zylinderkonfiguration (Inline-4, V-Twin, etc.)
#    - Zündzeitpunkte (Firing Order)
#
#  Die Sounds werden in Echtzeit am Puffer generiert und über pygame.mixer
#  wiedergegeben.
#
#  Verwendung:
#    from engine_sound import EngineSound
#    engine = EngineSound(idle_rpm=1200, max_rpm=7500, cylinders=4)
#    engine.set_throttle(0.5)  # 0.0 = Leerlauf, 1.0 = Vollgas
#    engine.update(dt)  # Jedes Frame aufrufen
#
# =============================================================================
from __future__ import annotations

import math
import struct
import logging
from typing import Sequence

try:
    import numpy as np
    _HAS_NP = True
except ImportError:
    _HAS_NP = False
    np = None

log = logging.getLogger("EngineSound")

_SAMPLE_RATE = 44100
_CHANNELS = 1  # Mono
_SAMPLE_SIZE = -16  # Signed 16-bit
_BUFFER_SIZE = 2048
_MAX_16BIT = 32767.0


def _sine_wave(freq: float, duration: float, amp: float = 0.8):
    """Erzeugt eine Sinuswelle bei gegebener Frequenz."""
    if duration <= 0:
        return []
    n = int(_SAMPLE_RATE * duration)
    return [amp * math.sin(2 * math.pi * freq * i / _SAMPLE_RATE)
            for i in range(n)]


def _exponential_decay(values: list[float], base: float = 3.0) -> list[float]:
    """Wendet exponentielles Auslaufen auf einen Puffer an."""
    if not values:
        return []
    n = len(values)
    decay_curve = [base / (10 ** (10.0 * i / n)) for i in range(n)]
    return [v * d for v, d in zip(values, decay_curve)]


def _pad_silence(audio: list[float], num_samples: int) -> list[float]:
    """Fügt Stille am Ende hinzu."""
    return audio + [0.0] * max(0, num_samples - len(audio))


def _slice_audio(audio: list[float], duration: float) -> list[float]:
    """Schneidet Audio auf Länge."""
    if duration <= 0:
        return []
    num_samples = int(_SAMPLE_RATE * duration)
    return audio[:num_samples]


def _normalize_audio(audio: list[float]) -> list[float]:
    """Normalisiert auf MAX_16BIT."""
    if not audio:
        return []
    max_val = max(abs(v) for v in audio) if audio else 0.0
    if max_val > 0:
        scale = 0.95 * _MAX_16BIT / max_val
        return [v * scale for v in audio]
    return audio


def _overlay_audio(*buffers) -> list[float]:
    """Überlagert mehrere Audio-Puffer (Sum-Mix)."""
    if not buffers or all(not b for b in buffers):
        return []
    max_len = max(len(b) for b in buffers if b)
    result = [0.0] * max_len
    for buf in buffers:
        for i, val in enumerate(buf):
            result[i] += val
    return _normalize_audio(result)


def _concat_audio(*buffers) -> list[float]:
    """Verkettet Audio-Puffer."""
    result = []
    for buf in buffers:
        result.extend(buf)
    return result


def _resample_audio(audio: list[float], factor: float) -> list[float]:
    """Resampled Audio mit linearer Interpolation."""
    if factor <= 0 or not audio:
        return []
    if abs(factor - 1.0) < 0.001:
        return audio[:]
    
    result = []
    for i in range(int(len(audio) * factor)):
        pos = i / factor
        idx = int(pos)
        frac = pos - idx
        
        if idx + 1 < len(audio):
            val = audio[idx] * (1 - frac) + audio[idx + 1] * frac
        elif idx < len(audio):
            val = audio[idx]
        else:
            val = 0.0
        result.append(val)
    return result


# ────────────────────────────────────────────────────────────────────────────

class EngineSound:
    """
    Synthetisiert realistische Motor-Sounds basierend auf RPM und Drosselklappe.
    """

    def __init__(self, idle_rpm: float = 1200, max_rpm: float = 7500,
                 cylinders: int = 4, timing_offsets: Sequence[float] | None = None) -> None:
        """
        :param idle_rpm: Leerlauf-Drehzahl
        :param max_rpm: Maximale Drehzahl (Limiter)
        :param cylinders: Anzahl Zylinder (2, 4, 6, 8)
        :param timing_offsets: Zündzeitpunkte in Grad (z.B. [0, 180, 180, 180] für Inline-4)
        """
        self.idle_rpm = idle_rpm
        self.max_rpm = max_rpm
        self.cylinders = cylinders
        self.current_rpm = idle_rpm
        
        # Standardwerte für verschiedene Konfigurationen
        if timing_offsets is None:
            if cylinders == 2:
                timing_offsets = [0, 360]  # Twin: 360°
            elif cylinders == 4:
                timing_offsets = [0, 180, 180, 180]  # Inline-4
            elif cylinders == 6:
                timing_offsets = [0, 120, 120, 120, 120, 120]  # Inline-6
            else:  # 8
                timing_offsets = [0, 90, 90, 90, 90, 90, 90, 90]  # V8
        
        self.timing = list(timing_offsets)
        self._audio_buffer = []
        self._throttle = 0.0
        
        # Vorgenerierte Zündsounds
        self._fire_sound = self._create_fire_sound()
        self._between_sound = [0.0] * int(0.05 * _SAMPLE_RATE)  # 50ms Stille

    def _create_fire_sound(self) -> list[float]:
        """Creates a single cylinder firing sound (short combustion pop)."""
        duration = 0.025  # 25ms — short pop, not a long tone
        n = int(_SAMPLE_RATE * duration)
        result = []
        for i in range(n):
            t = i / _SAMPLE_RATE
            # Fundamental + 2nd harmonic for a richer combustion sound
            val = (0.7 * math.sin(2 * math.pi * 180 * t) +
                   0.3 * math.sin(2 * math.pi * 360 * t))
            # Sharp attack, fast decay
            decay = math.exp(-t * 80.0)
            result.append(val * decay)
        return result

    def _gen_one_cycle_audio(self, cycle_duration: float) -> list[float]:
        """
        Generates audio for one engine cycle.
        Overlays all cylinder firings at their correct timing offsets.
        """
        cycle_samples = int(_SAMPLE_RATE * cycle_duration)
        if cycle_samples < 1:
            return []
        cycle_audio = [0.0] * cycle_samples

        # Convert delta timing_offsets to absolute degree positions
        abs_positions = []
        pos = 0.0
        for offset in self.timing:
            abs_positions.append(pos)
            pos += offset

        total_degrees = 720.0  # Full 4-stroke cycle
        samples_per_degree = cycle_samples / total_degrees

        # Fire sound should be at most 1/cylinders of cycle length to avoid
        # overlapping across the full cycle
        max_fire_samples = max(1, cycle_samples // max(1, len(self.timing)))
        fire = self._fire_sound[:max_fire_samples]

        for abs_deg in abs_positions:
            fire_sample = int(abs_deg * samples_per_degree)
            scale = 0.9 / len(self.timing)
            for i, val in enumerate(fire):
                idx = fire_sample + i
                if idx < cycle_samples:
                    cycle_audio[idx] += val * scale

        return _normalize_audio(cycle_audio)

    def set_throttle(self, throttle: float) -> None:
        """
        Setzt die Drosselklappe (0.0 = Leerlauf, 1.0 = Vollgas).
        """
        self._throttle = max(0.0, min(1.0, throttle))

    def update(self, dt: float) -> None:
        """
        Aktualisiert RPM und Puffer basierend auf Drosselklappe.
        Sollte jeden Frame aufgerufen werden.
        """
        # RPM-Interpolation (Trägheit)
        target_rpm = self.idle_rpm + self._throttle * (self.max_rpm - self.idle_rpm)
        rpm_accel = 5000.0  # U/min pro Sekunde
        
        if self.current_rpm < target_rpm:
            self.current_rpm = min(target_rpm, self.current_rpm + rpm_accel * dt)
        elif self.current_rpm > target_rpm:
            self.current_rpm = max(target_rpm, self.current_rpm - rpm_accel * dt)

    def gen_audio(self, num_samples: int) -> bytes:
        """
        Generiert Audio-Daten für pygame.mixer.
        Gibt Audio als 16-Bit Integer bytes zurück.
        """
        # RPM guard
        rpm = max(self.idle_rpm, self.current_rpm)

        # Refill buffer when running low
        if len(self._audio_buffer) < num_samples:
            # Correct formula: one 4-stroke cycle = 2 crankshaft revolutions
            cycle_duration = 2.0 * 60.0 / rpm
            cycle = self._gen_one_cycle_audio(cycle_duration)
            
            # Konvertiere zu Liste wenn numpy array
            if _HAS_NP and isinstance(cycle, np.ndarray):
                cycle = cycle.tolist()
            
            # Extend Puffer
            if isinstance(self._audio_buffer, list):
                self._audio_buffer.extend(cycle)
            else:  # numpy array
                cycle_arr = np.array(cycle, dtype=np.int16)
                self._audio_buffer = np.concatenate([self._audio_buffer, cycle_arr])
        
        # Extrahiere gewünschte Menge
        if isinstance(self._audio_buffer, list):
            audio_out = self._audio_buffer[:num_samples]
            self._audio_buffer = self._audio_buffer[num_samples:]
            audio_i16 = [max(-32768, min(32767, int(val))) for val in audio_out]
        else:  # numpy array
            audio_out = self._audio_buffer[:num_samples]
            self._audio_buffer = self._audio_buffer[num_samples:]
            audio_i16 = audio_out.astype(np.int16).tolist()
        
        # Pad mit Stille, wenn nicht genug vorhanden
        while len(audio_i16) < num_samples:
            audio_i16.append(0)
        
        # Konvertiere zu bytes
        return struct.pack(f'<{num_samples}h', *audio_i16[:num_samples])


# ────────────────────────────────────────────────────────────────────────────

def create_inline_four() -> EngineSound:
    """Erstellt einen Inline-4-Motor (z.B. für standard Auto)."""
    return EngineSound(
        idle_rpm=1200,
        max_rpm=7500,
        cylinders=4,
        timing_offsets=[0, 180, 180, 180]
    )


def create_v_twin() -> EngineSound:
    """Erstellt einen V-Twin-Motor (z.B. für Motorrad)."""
    return EngineSound(
        idle_rpm=900,
        max_rpm=9000,
        cylinders=2,
        timing_offsets=[0, 360]
    )


def create_v_eight() -> EngineSound:
    """Erstellt einen V8-Motor (z.B. für Sports Car)."""
    return EngineSound(
        idle_rpm=1500,
        max_rpm=8000,
        cylinders=8,
        timing_offsets=[0, 90, 90, 90, 90, 90, 90, 90]
    )
