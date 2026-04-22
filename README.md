# PanicPilot

A cooperative Mario Kart–like game where one player controls the car (steering/driving) while the other player sees the map. Both players must communicate to reach the destination.

Future improvements may include items, buffs, or alternative control mechanics (e.g., one player steering while the other controls acceleration).

---

## Setup

### Linux (Arch / Ubuntu / etc.)

This project uses pyenv to manage Python versions via :contentReference[oaicite:0]{index=0}.

#### 1. Install dependencies (Arch example)
```bash
sudo pacman -S python python-pip pyenv base-devel tk zlib bzip2 openssl readline sqlite libffi
````

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

* Python 3.11 or higher (3.12 recommended)
* pygame
* numpy (for audio processing)

---

## Notes

* On Linux, pyenv is used to manage Python versions
* Always create the virtual environment after selecting the correct Python version
* If pygame errors occur, it is usually caused by a Python version mismatch, not the code

