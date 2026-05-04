# PanicPilot

A cooperative Mario Kart–like game where one player controls the car (steering/driving) while the other player sees the map. Both players must communicate to reach the destination.

Future improvements may include items, buffs, or alternative control mechanics (e.g., one player steering while the other controls acceleration).

---

## Setup

### Linux (Ubuntu / Debian)

#### 1. Install system dependencies

```bash
sudo apt install python3 python3-pip python3-venv python3-dev build-essential \
  libsdl2-dev libsdl2-image-dev libsdl2-mixer-dev libsdl2-ttf-dev libportaudio2
```

> Python 3.11+ is included in Ubuntu 22.04 LTS and later — no pyenv needed.

#### 2. Set up the project

```bash
cd PanicPilot
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

#### 3. Run the game

```bash
python main.py
```

---

### Linux (Arch)

#### 1. Install dependencies

```bash
sudo pacman -S python python-pip pyenv base-devel tk zlib bzip2 openssl readline sqlite libffi
```

#### 2. Install Python version

```bash
pyenv install 3.12.2
cd PanicPilot
pyenv local 3.12.2
```

#### 3. Create virtual environment

```bash
python -m venv .venv
source .venv/bin/activate
```

#### 4. Install dependencies

```bash
pip install -r requirements.txt
```

#### 5. Run the game

```bash
python main.py
```

---

### macOS

#### 1. Install dependencies

```bash
brew install pyenv
brew install tcl-tk
```

#### 2. Install Python version

```bash
pyenv install 3.12.2
pyenv local 3.12.2
```

#### 3. Setup project

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

---

### Windows (school PCs)

#### 1. Create virtual environment

```powershell
py -3.11 -m venv .venv
```

#### 2. Activate environment

```powershell
.venv\Scripts\Activate
```

#### 3. Install dependencies

```powershell
pip install -r requirements.txt
```

#### 4. Run the game

```powershell
python main.py
```

---

## Requirements

- Python 3.11 or higher (3.12 recommended)
- pygame
- numpy (for audio processing)

---

## Notes

- On Ubuntu/Debian, the system Python 3 is sufficient — no pyenv needed
- On Arch/macOS, pyenv is used to manage Python versions
- Always create the virtual environment after selecting the correct Python version
- If pygame errors occur, it is usually caused by a Python version mismatch, not the code
- Settings (volume, fullscreen) are saved automatically to `user_settings.json`

## Controls

| Key | Action |
|-----|--------|
| A / D | Steer left / right (host car) |
| R | Restart race |
| M | Return to main menu (post-race) |
| N | Request mode switch (post-race, requires navigator confirmation) |
| P | Pause / unpause |
| F11 | Toggle fullscreen (works everywhere) |
| ESC | Back / leave |
| Click (Mode 2) | Place navigator ping on map |
| Y / N | Accept / decline mode switch request (navigator) |

---

## TODOs

- [x] Add connection history and LAN room discovery (UDP). **✅ DONE**
- [x] Fix copy & paste for IP addresses (cross-platform). **✅ DONE**
- [x] Implement engine (motor) sound. **✅ DONE** — procedural synthesis, RPM-reactive
- [x] Add ping visualization in fog (Mode 2). **✅ DONE** — ripple animation, off-screen arrows, urgency colors
- [x] Fullscreen mode with correct scaling. **✅ DONE** — F11 shortcut, smooth upscaling, persisted setting
- [x] Mode switching while connected. **✅ DONE** — post-race, requires navigator confirmation
- [x] Translate everything to English. **✅ DONE**
- [x] Client returns to lobby/menu after being kicked. **✅ DONE** — ESC dismisses kick screen
- [ ] Upload Ben's documentation.
- [x] GitHub Actions release with bundled executable. **✅ DONE** — PyInstaller spec + `.github/workflows/release.yml`; push a `vX.Y.Z` tag to trigger a multi-platform release (Windows / macOS / Linux)

### Currently working on

Nothing — all major tasks complete. See above for open items.
