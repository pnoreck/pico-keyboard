# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Hardware time tracker using a Raspberry Pi Pico with 9 buttons and 8 NeoPixel LEDs. The system consists of:
- **Pico firmware** (CircuitPython): Handles button input, LED output, USB serial communication
- **Host application** (Python): Runs on macOS, receives button events, manages time tracking, sends LED commands

## Running the Tracker

```bash
./run_tracker.sh              # creates/repairs .venv, installs requirements.txt, runs tracker.py
./run_tracker.sh --summary    # print all tracked days, no Pico needed
./run_tracker.sh --no-pico    # terminal menu to control tracking without the Pico
```

Dependencies live in `requirements.txt`. Never suggest a bare `pip install`: on macOS that hits a different Python than the venv.
Data files go to the script directory, or to `data_dir` from `config.yaml`.

## Architecture

### Communication Flow
```
Pico (code.py)  <--USB Serial-->  Host (tracker.py)
   |                                    |
   | BTN:n events  ---->                | Process button via KEYMAP
   |                                    |
   | <---- LED:idx:r,g,b commands       | Update LEDs
   | <---- LED:ALL:r,g,b                |
   | <---- LED:ANIM:idx:r,g,b           |
```

### Key Components

**tracker.py** - Main host application
- `KEYMAP`: Two-layer button mapping (layer 0 and layer 1), each button maps to action + optional label/color
- `TimeTracker`: Manages CSV-based time tracking with daily files (`times.YYMMDD.csv`)
- `load_project_config()`: Loads custom project labels from `config.yaml`
- Serial protocol: Sends `LED:` commands, receives `BTN:n` events

**pico/code.py** - CircuitPython firmware
- Button polling with edge detection (False→True = click)
- NeoPixel control with optional pulse animation
- Parses LED commands: `LED:idx:r,g,b`, `LED:ALL:r,g,b`, `LED:ANIM:idx:r,g,b`, `LED:STOP`

**pico/boot.py** - Enables dual USB CDC (console + data channel)

### LED Layout (8 LEDs)
- LED 0: Tracking status (green = active)
- LED 1: Prevent sleep indicator (blue)
- LED 2: Current project color
- LED 7: Layer indicator (yellow = layer 1)

### Button Layout
- Layer 0: Button 1 = toggle tracking, 2-7 = projects/Support/Meeting, 8 = show today, 9 = layer shift
- Layer 1: Buttons 1-7 = additional projects, 8 = prevent sleep (caffeinate), 9 = layer shift back

## Data Format

CSV files per day with columns: `timestamp,label`
- Entries are written on start, `STOP` marks end of tracking
- Duration calculated between consecutive entries
