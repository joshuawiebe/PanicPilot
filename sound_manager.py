# =============================================================================
#  sound_manager.py  –  Panic Pilot | Central Audio System (Phase 12)
# =============================================================================
#
#  All sounds are generated procedurally if no files are present.
#  The class is always safe to use – on errors all methods become no-ops.
#  No crashes on missing files or missing mixer.
#
#  Directory structure (optional, for custom sounds):
#    assets/sounds/
#      engine_idle.wav      – engine idle loop
#      engine_hi.wav        – engine high-rev loop
#      crash.ogg            – collision sound
#      pickup_fuel.ogg      – collect fuel canister
#      pickup_item.ogg      – collect item box
#      countdown_beep.ogg   – 3-2-1 countdown beep
#      countdown_go.ogg     – GO signal
#      boomerang.ogg        – boomerang throw
#      music_menu.ogg       – lobby/menu music (loop)
#      music_race.ogg       – race music (loop)
#
#  Usage (from main.py):
#      from sound_manager import SoundManager
#      sm = SoundManager()
#      sm.set_sfx_volume(80)      # 0-100
#      sm.set_music_volume(70)    # 0-100
#      sm.play_music("menu")
#      sm.play_pickup_fuel()
#
#  Usage (from game.py):
#      self._sm.update_engine(speed, max_speed, dt)
#      self._sm.play_collision(intensity)   # intensity 0.0-1.0
# =============================================================================
from __future__ import annotations

import os
import math
import struct
import random
import logging
import pygame

# Optional import of improved Engine-Sound-System
try:
    from engine_sound import create_inline_four
    _HAS_ENGINE_SOUND = True
except ImportError:
    _HAS_ENGINE_SOUND = False

log = logging.getLogger("SoundManager")

_SAMPLE_RATE   = 44100
_CHANNELS      = 2       # Stereo
_SAMPLE_SIZE   = -16     # Signed 16-bit
_BUFFER        = 512

# Engine frequencies: 8 RPM levels (Hz of fundamental) - when no v2 available
_ENGINE_BANDS  = 16  # Increased to 16 when engine_sound v2 available
_ENGINE_FREQS  = [52, 68, 88, 112, 142, 180, 225, 278]  # Legacy fallback

# Channel reservations
_CH_ENGINE_A   = 0
_CH_ENGINE_B   = 1
_CH_SFX_START  = 2   # Channels 2-9 for SFX

_ASSETS_DIR    = os.path.join("assets", "sounds")


# ─── Numpy-Import (optional) ──────────────────────────────────────────────────

try:
    import numpy as np
    _HAS_NP = True
except ImportError:
    _HAS_NP = False
    log.warning("numpy not found – using Python fallback for sound generation.")


# ─── Hilfsfunktionen ──────────────────────────────────────────────────────────

def _make_stereo_sound(wave_mono: list[int]) -> pygame.Sound:
    """Converts a mono int16 list to a pygame.Sound (stereo)."""
    n = len(wave_mono)
    # Interleaved stereo: L R L R ...
    data = struct.pack(f"{n * 2}h", *[v for s in wave_mono for v in (s, s)])
    return pygame.mixer.Sound(buffer=data)


def _sine_wave(freq: float, duration: float, amp: float = 0.5,
               phase: float = 0.0) -> list[float]:
    n = int(_SAMPLE_RATE * duration)
    return [amp * math.sin(2 * math.pi * freq * i / _SAMPLE_RATE + phase)
            for i in range(n)]


def _apply_envelope(wave: list[float],
                    attack: float = 0.01,
                    release: float = 0.08) -> list[float]:
    n      = len(wave)
    att_n  = int(attack  * _SAMPLE_RATE)
    rel_n  = int(release * _SAMPLE_RATE)
    result = list(wave)
    for i in range(min(att_n, n)):
        result[i] *= i / max(1, att_n)
    for i in range(min(rel_n, n)):
        idx = n - 1 - i
        result[idx] *= i / max(1, rel_n)
    return result


def _normalize(wave: list[float], peak: float = 0.85) -> list[int]:
    mx = max(abs(v) for v in wave) or 1.0
    scale = peak / mx * 32767
    return [max(-32767, min(32767, int(v * scale))) for v in wave]


# ── numpy-beschleunigte Versionen ─────────────────────────────────────────────

def _np_make_stereo(samples_float: "np.ndarray") -> pygame.Sound:
    """Faster path when numpy available."""
    s16  = (samples_float * 32767).astype("int16")
    stereo = np.column_stack([s16, s16])
    return pygame.sndarray.make_sound(stereo)


# ─── Prozeduale SFX-Generatoren ───────────────────────────────────────────────

def _gen_engine_sound(freq: float, duration: float = 0.8) -> pygame.Sound:
    """
    Engine sound: fundamental + overtones + light noise.
    Sounds like a small, fast kart engine.
    """
    if _HAS_NP:
        n = int(_SAMPLE_RATE * duration)
        t = np.linspace(0, duration, n, endpoint=False)
        # Kart-like sound synthesis: many overtones
        w  = 0.35 * np.sin(2 * np.pi * freq       * t)
        w += 0.28 * np.sin(2 * np.pi * freq * 2   * t + 0.3)
        w += 0.18 * np.sin(2 * np.pi * freq * 3   * t + 0.6)
        w += 0.10 * np.sin(2 * np.pi * freq * 4   * t + 0.9)
        w += 0.06 * np.sin(2 * np.pi * freq * 5   * t + 1.2)
        w += 0.03 * np.sin(2 * np.pi * freq * 6.5 * t)
        # Mechanical noise
        w += 0.02 * np.random.uniform(-1, 1, n)
        # Normalisieren
        w /= np.max(np.abs(w)) * (1.0 / 0.82)
        return _np_make_stereo(w * 0.82)
    else:
        wave: list[float] = []
        n = int(_SAMPLE_RATE * duration)
        for i in range(n):
            t = i / _SAMPLE_RATE
            v = (0.35 * math.sin(2*math.pi*freq*t) +
                 0.28 * math.sin(2*math.pi*freq*2*t + 0.3) +
                 0.18 * math.sin(2*math.pi*freq*3*t + 0.6) +
                 0.10 * math.sin(2*math.pi*freq*4*t + 0.9) +
                 0.06 * math.sin(2*math.pi*freq*5*t + 1.2) +
                 0.02 * random.uniform(-1, 1))
            wave.append(v)
        return _make_stereo_sound(_normalize(wave, 0.82))


def _gen_collision_sound() -> pygame.Sound:
    """Muffled impact: deep tone + noise burst."""
    if _HAS_NP:
        n = int(_SAMPLE_RATE * 0.30)
        t = np.linspace(0, 0.30, n, endpoint=False)
        # Deep thump
        thump = 0.7 * np.sin(2*np.pi*60*t) * np.exp(-t * 14)
        # Scratch noise
        noise = 0.4 * np.random.uniform(-1, 1, n) * np.exp(-t * 20)
        # Kurzer Metallklang
        ring  = 0.2 * np.sin(2*np.pi*380*t) * np.exp(-t * 30)
        w = thump + noise + ring
        w /= np.max(np.abs(w)) * (1.0 / 0.9)
        return _np_make_stereo(w * 0.9)
    else:
        n    = int(_SAMPLE_RATE * 0.30)
        wave = []
        for i in range(n):
            t = i / _SAMPLE_RATE
            v = (0.7 * math.sin(2*math.pi*60*t) * math.exp(-t*14) +
                 0.4 * random.uniform(-1, 1)      * math.exp(-t*20) +
                 0.2 * math.sin(2*math.pi*380*t)  * math.exp(-t*30))
            wave.append(v)
        return _make_stereo_sound(_normalize(wave, 0.9))


def _gen_pickup_fuel_sound() -> pygame.Sound:
    """Ascending, bright chime – fuel found."""
    if _HAS_NP:
        n    = int(_SAMPLE_RATE * 0.28)
        t    = np.linspace(0, 0.28, n, endpoint=False)
        freq = 440 + 660 * (t / 0.28)   # aufsteigend 440→1100 Hz
        phase = 2 * np.pi * np.cumsum(freq) / _SAMPLE_RATE
        w  = 0.6 * np.sin(phase)
        w += 0.2 * np.sin(phase * 2)
        env = np.where(t < 0.04, t / 0.04,
              np.where(t > 0.20, (0.28 - t) / 0.08, 1.0))
        w *= env
        return _np_make_stereo(w * 0.75)
    else:
        n    = int(_SAMPLE_RATE * 0.28)
        wave = []
        phase = 0.0
        for i in range(n):
            t     = i / _SAMPLE_RATE
            freq  = 440 + 660 * (t / 0.28)
            phase += 2 * math.pi * freq / _SAMPLE_RATE
            env   = (t/0.04 if t < 0.04 else
                     (0.28-t)/0.08 if t > 0.20 else 1.0)
            wave.append(0.75 * math.sin(phase) * env)
        return _make_stereo_sound(_normalize(wave, 0.75))


def _gen_pickup_item_sound() -> pygame.Sound:
    """Magical jingle – item box collected."""
    if _HAS_NP:
        n    = int(_SAMPLE_RATE * 0.35)
        t    = np.linspace(0, 0.35, n, endpoint=False)
        # Two tones in arpeggio
        a = int(0.15 * _SAMPLE_RATE)
        w = np.zeros(n)
        # Erster Ton: 660 Hz
        env1 = np.exp(-t[:a] * 12)
        w[:a] = 0.6 * np.sin(2*np.pi*660*t[:a]) * env1
        w[:a] += 0.2 * np.sin(2*np.pi*1320*t[:a]) * env1
        # Zweiter Ton: 880 Hz
        t2 = t[a:] - t[a]
        env2 = np.exp(-t2 * 12)
        w[a:] = 0.6 * np.sin(2*np.pi*880*t2) * env2
        w[a:] += 0.2 * np.sin(2*np.pi*1760*t2) * env2
        return _np_make_stereo(w * 0.7)
    else:
        n = int(_SAMPLE_RATE * 0.35)
        a = int(0.15 * _SAMPLE_RATE)
        wave = []
        for i in range(n):
            t = i / _SAMPLE_RATE
            if i < a:
                env = math.exp(-t*12)
                v = (0.6*math.sin(2*math.pi*660*t) +
                     0.2*math.sin(2*math.pi*1320*t)) * env
            else:
                t2 = (i-a) / _SAMPLE_RATE
                env = math.exp(-t2*12)
                v = (0.6*math.sin(2*math.pi*880*t2) +
                     0.2*math.sin(2*math.pi*1760*t2)) * env
            wave.append(v * 0.7)
        return _make_stereo_sound(_normalize(wave, 0.7))


def _gen_countdown_beep(freq: float = 440.0, duration: float = 0.12) -> pygame.Sound:
    """Short, clear countdown beep."""
    if _HAS_NP:
        n = int(_SAMPLE_RATE * duration)
        t = np.linspace(0, duration, n, endpoint=False)
        w  = 0.7 * np.sin(2*np.pi*freq*t)
        w += 0.2 * np.sin(2*np.pi*freq*2*t)
        env = np.where(t < 0.01, t/0.01,
              np.where(t > duration*0.6, (duration-t)/(duration*0.4), 1.0))
        return _np_make_stereo(w * env * 0.8)
    else:
        n = int(_SAMPLE_RATE * duration)
        wave = []
        for i in range(n):
            t = i / _SAMPLE_RATE
            env = (t/0.01 if t < 0.01 else
                   (duration-t)/(duration*0.4) if t > duration*0.6 else 1.0)
            wave.append(0.8 * (0.7*math.sin(2*math.pi*freq*t) +
                               0.2*math.sin(2*math.pi*freq*2*t)) * env)
        return _make_stereo_sound(_normalize(wave, 0.8))


def _gen_countdown_go() -> pygame.Sound:
    """Energetic GO! signal."""
    if _HAS_NP:
        n = int(_SAMPLE_RATE * 0.45)
        t = np.linspace(0, 0.45, n, endpoint=False)
        w  = 0.5 * np.sin(2*np.pi*880*t)
        w += 0.3 * np.sin(2*np.pi*1320*t)
        w += 0.2 * np.sin(2*np.pi*440*t)
        env = np.where(t < 0.02, t/0.02, np.exp(-(t-0.02)*4))
        return _np_make_stereo(w * env * 0.9)
    else:
        n = int(_SAMPLE_RATE * 0.45)
        wave = []
        for i in range(n):
            t = i / _SAMPLE_RATE
            env = t/0.02 if t < 0.02 else math.exp(-(t-0.02)*4)
            wave.append(0.9 * (0.5*math.sin(2*math.pi*880*t) +
                               0.3*math.sin(2*math.pi*1320*t) +
                               0.2*math.sin(2*math.pi*440*t)) * env)
        return _make_stereo_sound(_normalize(wave, 0.9))


def _gen_boomerang_sound() -> pygame.Sound:
    """Whoosh sound: Doppler-like frequency sweep."""
    if _HAS_NP:
        n   = int(_SAMPLE_RATE * 0.22)
        t   = np.linspace(0, 0.22, n, endpoint=False)
        # Frequency sweep: 800→200 Hz (flyby effect)
        freq = 800 - 2700 * (t / 0.22)**1.8
        freq = np.clip(freq, 100, 1200)
        phase = 2 * np.pi * np.cumsum(freq) / _SAMPLE_RATE
        w  = 0.55 * np.sin(phase)
        w += 0.25 * np.sin(phase * 1.5)
        # Noise for "wind sound"
        w += 0.15 * np.random.uniform(-1, 1, n)
        env = np.where(t < 0.03, t/0.03,
              np.where(t > 0.16, (0.22-t)/0.06, 1.0))
        return _np_make_stereo(w * env * 0.65)
    else:
        n     = int(_SAMPLE_RATE * 0.22)
        wave  = []
        phase = 0.0
        for i in range(n):
            t    = i / _SAMPLE_RATE
            freq = max(100, 800 - 2700 * (t/0.22)**1.8)
            phase += 2*math.pi*freq / _SAMPLE_RATE
            env  = (t/0.03 if t < 0.03 else
                    (0.22-t)/0.06 if t > 0.16 else 1.0)
            wave.append(0.65 * (0.55*math.sin(phase) +
                                0.25*math.sin(phase*1.5) +
                                0.15*random.uniform(-1,1)) * env)
        return _make_stereo_sound(_normalize(wave, 0.65))


def _gen_win_fanfare() -> pygame.Sound:
    """Kurzes Sieger-Fanfare-Jingle."""
    if _HAS_NP:
        notes = [(523, 0.12), (659, 0.12), (784, 0.12), (1047, 0.25)]
        total = sum(d for _, d in notes)
        n = int(_SAMPLE_RATE * total)
        w = np.zeros(n)
        pos = 0
        for freq, dur in notes:
            nn   = int(_SAMPLE_RATE * dur)
            t    = np.linspace(0, dur, nn, endpoint=False)
            env  = np.where(t < 0.01, t/0.01, np.exp(-(t-0.01)*5))
            seg  = (0.6*np.sin(2*np.pi*freq*t) +
                    0.25*np.sin(2*np.pi*freq*2*t)) * env
            w[pos:pos+nn] = seg[:len(w)-pos]
            pos += nn
        return _np_make_stereo(w * 0.85)
    else:
        notes = [(523, 0.12), (659, 0.12), (784, 0.12), (1047, 0.25)]
        wave  = []
        for freq, dur in notes:
            n = int(_SAMPLE_RATE * dur)
            for i in range(n):
                t   = i / _SAMPLE_RATE
                env = t/0.01 if t < 0.01 else math.exp(-(t-0.01)*5)
                wave.append(0.85*(0.6*math.sin(2*math.pi*freq*t)+
                                  0.25*math.sin(2*math.pi*freq*2*t))*env)
        return _make_stereo_sound(_normalize(wave, 0.85))


def _gen_pause_sound() -> pygame.Sound:
    """Soft double tone for pause."""
    if _HAS_NP:
        n  = int(_SAMPLE_RATE * 0.18)
        t  = np.linspace(0, 0.18, n, endpoint=False)
        w  = 0.5 * np.sin(2*np.pi*660*t)
        w += 0.4 * np.sin(2*np.pi*440*(t + 0.06))
        env = np.where(t < 0.01, t/0.01, np.exp(-(t-0.01)*8))
        return _np_make_stereo(w * env * 0.5)
    else:
        n = int(_SAMPLE_RATE * 0.18)
        wave = []
        for i in range(n):
            t   = i / _SAMPLE_RATE
            env = t/0.01 if t < 0.01 else math.exp(-(t-0.01)*8)
            wave.append(0.5*(0.5*math.sin(2*math.pi*660*t) +
                             0.4*math.sin(2*math.pi*440*(t+0.06)))*env)
        return _make_stereo_sound(_normalize(wave, 0.5))


# ─── Main class ─────────────────────────────────────────────────────────────

class SoundManager:
    """
    Central audio system for Panic Pilot.

    All sounds are automatically generated procedurally if no
    assets/sounds/ files are present.

    Thread safety: Call only from the main thread.
    """

    # Engine: Hold time before band change (prevents flickering)
    _ENGINE_HYSTERESIS = 0.08   # Sekunden

    def __init__(self) -> None:
        self._ok            = False
        self._sfx_vol       = 0.80
        self._music_vol     = 0.70
        self._current_music = ""
        self._engine_on     = False

        # Engine-State (Legacy Band-System)
        self._eng_band      = -1
        self._eng_fade_t    = 1.0
        self._eng_a_idx     = _CH_ENGINE_A
        self._eng_b_idx     = _CH_ENGINE_B
        self._eng_hold_t    = 0.0   # Hysterese-Timer
        self._eng_sounds: list[pygame.Sound] = []

        # New Engine-Sound-System (v2)
        self._engine_sound_v2 = None
        self._use_engine_sound_v2 = False

        # SFX
        self._sfx: dict[str, pygame.Sound] = {}
        # Collision cooldown (prevents spam)
        self._crash_cd      = 0.0

        try:
            pygame.mixer.init(frequency=_SAMPLE_RATE, size=_SAMPLE_SIZE,
                              channels=_CHANNELS, buffer=_BUFFER)
            pygame.mixer.set_num_channels(16)
            self._ok = True
            log.info("pygame.mixer initialized (%d Hz, %d channels).",
                     _SAMPLE_RATE, pygame.mixer.get_num_channels())
            
            # Try to initialize new Engine-Sound-System
            if _HAS_ENGINE_SOUND:
                try:
                    self._engine_sound_v2 = create_inline_four()
                    self._use_engine_sound_v2 = True
                    log.info("Engine sound v2 (synthesis) enabled.")
                except Exception as e:
                    log.warning("Engine sound v2 initialization failed: %s – falling back to legacy system.", e)
            
            self._load_all()
        except Exception as exc:
            log.warning("Audio init failed: %s – running without sound.", exc)

    # ─── Initialisierung ──────────────────────────────────────────────────────

    def _load_all(self) -> None:
        """Loads or generates all sounds."""
        # Engine sounds: Use v2 synthesis if available
        if self._use_engine_sound_v2 and self._engine_sound_v2:
            self._gen_engine_sounds_v2()
        else:
            # Legacy: Fallback to old frequency bands
            for freq in _ENGINE_FREQS:
                self._eng_sounds.append(_gen_engine_sound(freq))

        # SFX: try file first, then generate procedurally
        self._sfx["crash"]         = self._try_load("crash.ogg",
                                                     _gen_collision_sound)
        self._sfx["pickup_fuel"]   = self._try_load("pickup_fuel.ogg",
                                                     _gen_pickup_fuel_sound)
        self._sfx["pickup_item"]   = self._try_load("pickup_item.ogg",
                                                     _gen_pickup_item_sound)
        self._sfx["countdown_beep"]= self._try_load("countdown_beep.ogg",
                                                     _gen_countdown_beep)
        self._sfx["countdown_go"]  = self._try_load("countdown_go.ogg",
                                                     _gen_countdown_go)
        self._sfx["boomerang"]     = self._try_load("boomerang.ogg",
                                                     _gen_boomerang_sound)
        self._sfx["win_fanfare"]   = self._try_load("win_fanfare.ogg",
                                                     _gen_win_fanfare)
        self._sfx["pause"]         = self._try_load("pause.ogg",
                                                     _gen_pause_sound)
        # Volume anwenden
        for snd in self._sfx.values():
            if snd:
                snd.set_volume(self._sfx_vol)

    def _gen_engine_sounds_v2(self) -> None:
        """Generates engine sounds with real synthesis (engine_sound.py)."""
        if not self._engine_sound_v2:
            return
        
        log.info("Generating engine sounds via synthesis (v2)...")
        # Generate 16 RPM levels for spectral driving
        for i in range(16):
            throttle = i / 15.0  # 0.0 bis 1.0
            try:
                # Set throttle and let RPM settle
                self._engine_sound_v2.set_throttle(throttle)
                for _ in range(5):
                    self._engine_sound_v2.update(0.016)

                # Generate exactly ONE complete engine cycle so pygame can
                # loop it seamlessly (no silence padding, no loop-point click)
                rpm = self._engine_sound_v2.current_rpm
                cycle_duration = 2.0 * 60.0 / max(rpm, 1.0)
                sample_count = int(_SAMPLE_RATE * cycle_duration)
                audio_bytes = self._engine_sound_v2.gen_audio(sample_count)
                
                # Convert mono to stereo
                audio_i16 = struct.unpack(f'<{sample_count}h', audio_bytes)
                audio_stereo = b''.join(
                    struct.pack('<hh', val, val) for val in audio_i16
                )
                
                sound = pygame.mixer.Sound(buffer=audio_stereo)
                self._eng_sounds.append(sound)
                log.debug(f"Engine Sound {i}: Throttle {throttle:.2%}, RPM {self._engine_sound_v2.current_rpm:.0f}")
            except Exception as e:
                log.warning(f"Engine sound {i} generation failed: {e}")
                # Fallback to Legacy
                self._use_engine_sound_v2 = False
                self._eng_sounds.clear()
                for freq in _ENGINE_FREQS:
                    self._eng_sounds.append(_gen_engine_sound(freq))
                return

    @staticmethod
    def _try_load(filename: str, fallback_fn) -> "pygame.Sound | None":
        """Loads from assets/sounds/ or calls fallback_fn()."""
        path = os.path.join(_ASSETS_DIR, filename)
        try:
            if os.path.isfile(path):
                snd = pygame.mixer.Sound(path)
                log.info("Sound loaded: %s", path)
                return snd
        except Exception as exc:
            log.warning("Sound load error %s: %s", path, exc)
        try:
            return fallback_fn()
        except Exception as exc:
            log.warning("Sound generation error for %s: %s", filename, exc)
            return None

    # ─── Volume ───────────────────────────────────────────────────────────

    def set_sfx_volume(self, vol: int) -> None:
        """vol: 0-100"""
        if not self._ok:
            return
        self._sfx_vol = max(0.0, min(1.0, vol / 100.0))
        for snd in self._sfx.values():
            if snd:
                snd.set_volume(self._sfx_vol)
        # Adjust engine volume live
        self._refresh_engine_volume()

    def set_music_volume(self, vol: int) -> None:
        """vol: 0-100"""
        if not self._ok:
            return
        self._music_vol = max(0.0, min(1.0, vol / 100.0))
        try:
            pygame.mixer.music.set_volume(self._music_vol)
        except Exception:
            pass

    def get_sfx_volume_int(self) -> int:
        return int(self._sfx_vol * 100)

    def get_music_volume_int(self) -> int:
        return int(self._music_vol * 100)

    # ─── Music ────────────────────────────────────────────────────────────────

    def play_music(self, track: str) -> None:
        """
        track: "menu" oder "race"
        Loads the corresponding file from assets/sounds/.
        If no file exists, music stays silent.
        """
        if not self._ok:
            return
        if track == self._current_music:
            return
        names = {
            "menu":  "music_menu.ogg",
            "race":  "music_race.ogg",
        }
        filename = names.get(track, "")
        if not filename:
            return
        path = os.path.join(_ASSETS_DIR, filename)
        try:
            if os.path.isfile(path):
                pygame.mixer.music.load(path)
                pygame.mixer.music.set_volume(self._music_vol)
                pygame.mixer.music.play(-1, fade_ms=800)
                self._current_music = track
            else:
                # Fade out music gently if no file
                pygame.mixer.music.fadeout(600)
                self._current_music = track
        except Exception as exc:
            log.warning("Music error (%s): %s", track, exc)

    def stop_music(self, fade_ms: int = 800) -> None:
        if not self._ok:
            return
        try:
            pygame.mixer.music.fadeout(fade_ms)
        except Exception:
            pass
        self._current_music = ""

    # ─── Engine sound (dynamic pitch) ─────────────────────────────────────

    def engine_start(self) -> None:
        """Start engine sound (at race start)."""
        if not self._ok:
            return
        
        # Use new system if available
        if self._use_engine_sound_v2:
            self.engine_start_v2()
        else:
            self.engine_start_legacy()

    def engine_start_legacy(self) -> None:
        """Start engine sound (legacy band system)."""
        if not self._ok or not self._eng_sounds:
            return
        self._engine_on = True
        self._eng_band  = 0
        ch = pygame.mixer.Channel(_CH_ENGINE_A)
        ch.play(self._eng_sounds[0], loops=-1)
        ch.set_volume(self._sfx_vol * 0.55)

    def engine_start_v2(self) -> None:
        """Start engine sound (new synthesis system with better sounds)."""
        if not self._ok or not self._eng_sounds:
            return
        self._engine_on = True
        self._eng_band  = 0
        ch = pygame.mixer.Channel(_CH_ENGINE_A)
        ch.play(self._eng_sounds[0], loops=-1)
        ch.set_volume(self._sfx_vol * 0.55)
        log.debug("Engine v2 started (band 0)")

    def engine_stop(self) -> None:
        """Stop engine sound."""
        if not self._ok:
            return
        
        self._engine_on = False
        
        if self._use_engine_sound_v2:
            self.engine_stop_v2()
        else:
            self.engine_stop_legacy()

    def engine_stop_legacy(self) -> None:
        """Stop engine sound (legacy)."""
        try:
            pygame.mixer.Channel(_CH_ENGINE_A).fadeout(300)
            pygame.mixer.Channel(_CH_ENGINE_B).fadeout(300)
        except Exception:
            pass

    def engine_stop_v2(self) -> None:
        """Stop engine sound (v2) - use normal fade-out."""
        try:
            pygame.mixer.Channel(_CH_ENGINE_A).fadeout(300)
            pygame.mixer.Channel(_CH_ENGINE_B).fadeout(300)
        except Exception:
            pass

    def update_engine(self, speed: float, max_speed: float = 500.0,
                      dt: float = 0.016) -> None:
        """
        Call every update round.
        speed:     current vehicle speed (px/s)
        max_speed: Reference max speed
        dt:        Delta time since last frame

        Automatically selects the appropriate engine sound and crossfades smoothly.
        """
        if not self._ok or not self._engine_on:
            return
        
        self._crash_cd = max(0.0, self._crash_cd - dt)
        
        if self._use_engine_sound_v2:
            self.update_engine_v2(speed, max_speed, dt)
        else:
            self.update_engine_legacy(speed, max_speed, dt)

    def update_engine_v2(self, speed: float, max_speed: float = 500.0,
                         dt: float = 0.016) -> None:
        """
        Updates engine sound (with v2 synthesis-generated sounds).
        Uses 16 bands instead of 8 for smoother transitions.
        """
        if not self._eng_sounds:
            return

        self._eng_hold_t = max(0.0, self._eng_hold_t - dt)

        pct  = min(1.0, max(0.0, abs(speed) / max(1.0, max_speed)))
        pct_adj = math.pow(pct, 0.65)
        band = min(15, int(pct_adj * 16))  # 16 bands instead of 8

        if band == self._eng_band or self._eng_hold_t > 0:
            return

        # Band change with crossfade
        old_ch  = pygame.mixer.Channel(self._eng_a_idx)
        new_ch  = pygame.mixer.Channel(self._eng_b_idx)
        
        if band < len(self._eng_sounds):
            new_snd = self._eng_sounds[band]
            new_ch.play(new_snd, loops=-1)
            new_ch.set_volume(0.0)
            old_ch.fadeout(120)
            new_ch.set_volume(self._sfx_vol * 0.55)
            self._eng_a_idx, self._eng_b_idx = self._eng_b_idx, self._eng_a_idx
            self._eng_band   = band
            self._eng_hold_t = self._ENGINE_HYSTERESIS

    def update_engine_legacy(self, speed: float, max_speed: float = 500.0,
                             dt: float = 0.016) -> None:
        """
        Updates engine sound (legacy band system).
        """
        if not self._eng_sounds:
            return

        self._eng_hold_t = max(0.0, self._eng_hold_t - dt)

        pct  = min(1.0, max(0.0, abs(speed) / max(1.0, max_speed)))
        pct_adj = math.pow(pct, 0.65)
        band = min(_ENGINE_BANDS - 1, int(pct_adj * _ENGINE_BANDS))

        if band == self._eng_band or self._eng_hold_t > 0:
            return

        # Band change: crossfade across 2 channels
        old_ch  = pygame.mixer.Channel(self._eng_a_idx)
        new_ch  = pygame.mixer.Channel(self._eng_b_idx)
        new_snd = self._eng_sounds[band]

        new_ch.play(new_snd, loops=-1)
        new_ch.set_volume(0.0)

        # Gentle crossfade step
        old_ch.fadeout(120)
        new_ch.set_volume(self._sfx_vol * 0.55)

        # Swap channels
        self._eng_a_idx, self._eng_b_idx = self._eng_b_idx, self._eng_a_idx
        self._eng_band   = band
        self._eng_hold_t = self._ENGINE_HYSTERESIS

    @property
    def _eng_a_idx(self) -> int:
        return self.__eng_a

    @_eng_a_idx.setter
    def _eng_a_idx(self, v: int) -> None:
        self.__eng_a = v

    @property
    def _eng_b_idx(self) -> int:
        return self.__eng_b

    @_eng_b_idx.setter
    def _eng_b_idx(self, v: int) -> None:
        self.__eng_b = v

    def __init_eng_idx(self) -> None:
        self.__eng_a = _CH_ENGINE_A
        self.__eng_b = _CH_ENGINE_B

    def _refresh_engine_volume(self) -> None:
        if not self._engine_on:
            return
        try:
            pygame.mixer.Channel(_CH_ENGINE_A).set_volume(self._sfx_vol * 0.55)
        except Exception:
            pass

    # ─── SFX-Abspieler ────────────────────────────────────────────────────────

    def _play_sfx(self, key: str, vol_scale: float = 1.0) -> None:
        if not self._ok:
            return
        snd = self._sfx.get(key)
        if snd is None:
            return
        try:
            ch = snd.play()
            if ch:
                ch.set_volume(self._sfx_vol * vol_scale)
        except Exception:
            pass

    def play_collision(self, intensity: float = 1.0) -> None:
        """
        Kollisionssound.
        intensity: 0.0-1.0 (scales volume).
        Cooldown prevents spam on repeated wall contact.
        """
        if self._crash_cd > 0:
            return
        vol = max(0.25, min(1.0, intensity))
        self._play_sfx("crash", vol)
        self._crash_cd = 0.22

    def play_pickup_fuel(self) -> None:
        self._play_sfx("pickup_fuel")

    def play_pickup_item(self) -> None:
        self._play_sfx("pickup_item")

    def play_countdown_beep(self) -> None:
        self._play_sfx("countdown_beep")

    def play_countdown_go(self) -> None:
        self._play_sfx("countdown_go")

    def play_boomerang(self) -> None:
        self._play_sfx("boomerang", 0.75)

    def play_win_fanfare(self) -> None:
        self._play_sfx("win_fanfare")

    def play_pause(self) -> None:
        self._play_sfx("pause", 0.6)

    # ─── Cleanup ────────────────────────────────────────────────────────────

    def shutdown(self) -> None:
        """Close mixer – call when exiting the game."""
        if not self._ok:
            return
        try:
            pygame.mixer.fadeout(400)
            pygame.time.wait(420)
            pygame.mixer.quit()
        except Exception:
            pass
        self._ok = False


# ─── Module singleton ─────────────────────────────────────────────────────────

_instance: SoundManager | None = None


def get() -> SoundManager:
    """Returns the global SoundManager instance (lazy init)."""
    global _instance
    if _instance is None:
        _instance = SoundManager()
        # Interne Engine-Index-Attribute initialisieren
        _instance.__dict__["_SoundManager__eng_a"] = _CH_ENGINE_A
        _instance.__dict__["_SoundManager__eng_b"] = _CH_ENGINE_B
    return _instance
