# PanicPilot

An asymmetric co-op racing game where two players share one car on a dangerous track. One player drives while the other navigates -- communication is the only way to survive.

## Game Description

PanicPilot is a local-network multiplayer racing game built with Python and pygame. The game features asymmetric gameplay where two players have different information and controls but must work together to complete a lap as fast as possible.

The Driver sees only what is directly ahead of the car -- the road, obstacles, and immediate surroundings. They have no map, no overview, and no idea what lies around the next corner. The Navigator, on the other hand, sees the entire track layout but cannot see the car's position on it. They must verbally guide the Driver through turns, hazards, and shortcuts.

This creates a unique dynamic where trust, communication, and coordination are just as important as driving skill.

## Game Modes

### Split Control (Mode 1)

Both players control the same car. The Driver handles steering while the Navigator (Client) handles throttle and braking. Requires constant communication to coordinate speed and direction through the track.

### Panic Pilot (Mode 2)

The Driver sees the track covered in thick fog -- visibility is severely limited. The Navigator has a full map view and can place glowing ping markers on the track to guide the Driver. Pings are visible through the fog and change color based on urgency: green for safe routes, orange for upcoming hazards. The Navigator can zoom in and out of the map using the mouse wheel or O/P keys.

### PvP Racing (Mode 3)

Two cars race head-to-head on the same track. Both players have full visibility and independent control of their own vehicles. Item boxes appear on the track that can be collected and used against the opponent -- boost pads for speed, oil slicks to spin out pursuers. Each player selects their car class independently.

## Car Classes

Three vehicle types with distinct handling characteristics:

- **Balanced** -- Good grip, normal speed. Reliable choice for any track.
- **Speedy** -- High top speed, slippery handling, higher fuel consumption. Fast but unforgiving.
- **Tank** -- Slow but sturdy, excellent grip, off-road king. Handles rough terrain well.

## Multiplayer

PanicPilot uses a host-client architecture over TCP for game data and UDP broadcast for LAN discovery.

- The **Host** creates a room, configures track length and game mode, and starts the race.
- The **Navigator (Client)** discovers available rooms on the LAN, connects, and enters a verification code shown on the Host screen to join.
- Both players see a car class selection screen before the race. In PvP mode, each player picks independently. In co-op modes, only the Host chooses.
- A built-in chat system lets players communicate directly from the lobby.

## File Structure

```
PanicPilot/
├── main.py                 # Entry point, menus, lobbies, UI components
├── game.py                 # Host-side game logic and rendering
├── client.py               # Client-side game logic and rendering
├── host.py                 # Host game state management
├── net.py                  # Network layer (TCP + length-prefixed JSON)
├── discovery.py            # LAN room discovery (UDP broadcast)
├── connection_history.py   # Persistent connection history storage
├── track.py                # Procedural track generation
├── car.py                  # Car physics and collision
├── car_state.py            # Car state serialization
├── entities.py             # Game entities (items, pickups, obstacles)
├── props.py                # Track decorations and scenery
├── walls.py                # Wall collision system
├── hud.py                  # Heads-up display (speed, fuel, items, position)
├── input_state.py          # Input handling abstraction
├── engine_sound.py         # Procedural engine sound synthesis
├── sound_manager.py        # Audio system (music, SFX, volume control)
├── particles.py            # Particle effects system
├── camera.py               # Camera follow and zoom
├── theme.py                # Color themes and visual constants
├── settings.py             # User settings (volume, username, fullscreen)
├── requirements.txt        # Python dependencies
├── panicpilot.spec         # PyInstaller build specification
├── .github/
│   ├── workflows/
│   │   └── release.yml     # Automated release pipeline
│   ├── instructions/       # Development guidelines
│   └── skills/             # Skill templates for code generation
└── assets/
    └── sounds/             # Custom audio files (optional, procedural fallback)
```

## Controls

### In-Game

| Key               | Action                                             |
| ----------------- | -------------------------------------------------- |
| A / D             | Steer left / right (Driver)                        |
| W / S             | Accelerate / Brake (Navigator in Mode 2)           |
| R                 | Reset car position on track                        |
| M                 | Cycle game mode (solo/host, immediate restart)     |
| N                 | Request mode switch (requires navigator approval)  |
| P / ESC           | Pause / unpause                                    |
| SPACE             | Use held item                                      |
| F11               | Toggle fullscreen                                  |

### Navigator (Mode 2)

| Key / Input       | Action                                             |
| ----------------- | -------------------------------------------------- |
| Mouse click       | Place ping marker on map                           |
| O / P             | Zoom out / in                                      |
| Mouse wheel       | Zoom out / in                                      |
| Y / N             | Accept / decline mode switch request               |

### Menus

| Key               | Action                                             |
| ----------------- | -------------------------------------------------- |
| ESC               | Back / leave                                       |
| Enter             | Confirm selection                                  |
| Ctrl+V            | Paste clipboard content (IP address input)         |

## Setup

### Linux (Ubuntu / Debian)

```bash
sudo apt install python3 python3-pip python3-venv python3-dev build-essential \
  libsdl2-dev libsdl2-image-dev libsdl2-mixer-dev libsdl2-ttf-dev libportaudio2

cd PanicPilot
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

### Linux (Arch)

```bash
sudo pacman -S python python-pip base-devel tk zlib bzip2 openssl \
  readline sqlite libffi sdl2 sdl2_image sdl2_mixer sdl2_ttf

cd PanicPilot
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

### macOS

```bash
brew install python sdl2 sdl2_image sdl2_mixer sdl2_ttf

cd PanicPilot
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

### Windows

```powershell
py -3.11 -m venv .venv
.venv\Scripts\Activate
pip install -r requirements.txt
python main.py
```

## Requirements

- Python 3.11 or higher (3.12 recommended)
- pygame
- numpy

## Notes

- Settings (volume, username, fullscreen) are saved automatically to `user_settings.json`
- Custom audio files can be placed in `assets/sounds/`. Missing files are automatically replaced with procedurally generated audio.
- If pygame audio errors occur, it is usually caused by missing SDL2 mixer libraries, not the code.
- The host's IP address is shown in the window title bar for the client to connect.
- Both players must be on the same local network for multiplayer to work.
