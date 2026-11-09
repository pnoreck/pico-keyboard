# Timelog - Hardware Time Tracker

A physical time tracking system using a Raspberry Pi Pico with buttons and RGB LEDs. Track your time across multiple projects with a simple button press, and view daily summaries directly from the device.

## Features

- **Physical Button Interface**: 9 buttons for quick project switching
- **Visual Feedback**: 8 RGB LEDs show tracking status, project colors, and layer indicators
- **Multi-Layer Support**: Access up to 11 projects across 2 layers
- **Daily Time Tracking**: Automatic CSV files per day with detailed timestamps
- **Project Customization**: Configure real project names via YAML config file (kept out of git)
- **Prevent Sleep Mode**: Keep your Mac awake during long tracking sessions
- **Daily Summary**: View today's time breakdown by project

## Hardware Requirements

- **Raspberry Pi Pico** (or Pico W)
- **9 Push Buttons** connected to GPIO pins (see pin mapping below)
- **8 NeoPixel RGB LEDs** (WS2812B or compatible) connected to GPIO 22
- **Wiring**: Buttons connected to 3.3V with internal pull-down resistors

### Pin Mapping

**Buttons:**
- Button 1: GP11
- Button 2: GP3
- Button 3: GP4
- Button 4: GP5
- Button 5: GP6
- Button 6: GP7
- Button 7: GP8
- Button 8: GP9
- Button 9: GP10

**LEDs:**
- NeoPixel Data: GP22
- 8 LEDs total

## Software Requirements

### Python Dependencies

Listed in `requirements.txt` (pyserial, pyyaml). The launcher `run_tracker.sh` creates a `.venv`
and installs them automatically, so normally there is nothing to do by hand. For a manual setup:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

### Pico Firmware Setup

1. Install CircuitPython on your Raspberry Pi Pico
2. Copy the files from `pico/` directory to your Pico:
   - `boot.py` (if needed for your setup)
   - `code.py` (main Pico firmware)

The Pico will automatically run `code.py` on boot and communicate via USB serial.

## Installation

1. **Clone or download this repository**

2. **Install Python dependencies:**
   ```bash
   ./run_tracker.sh   # creates .venv and installs requirements.txt on first run
   ```

3. **Set up your Pico:**
   - Flash CircuitPython to your Pico
   - Copy `pico/code.py` and `pico/boot.py` to the Pico's CIRCUITPY drive

4. **Configure project names (optional):**
   ```bash
   cp config.yaml.example config.yaml
   # Edit config.yaml with your real project names
   ```

5. **Connect your Pico** via USB to your computer

## Configuration

### Project Labels

To customize project names while keeping them private (out of git), create a `config.yaml` file:

```bash
cp config.yaml.example config.yaml
```

Edit `config.yaml`:
```yaml
projects:
  "1": "My Real Project Name"
  "2": "Another Project"
  "3": "Client Work"
  # ... etc for projects 1-11
```

The `config.yaml` file is automatically ignored by git (see `.gitignore`), so your real project names stay private.

### Data Directory

By default the CSV files are written next to `tracker.py`. To keep them outside the repository
checkout (for example in a synced folder), set `data_dir` in `config.yaml`:

```yaml
data_dir: ~/Documents/timelog
```

The directory is created on first use. Move any existing `times.*.csv` files there by hand.

## Usage

### Starting the Tracker

Use the launcher script. It creates the `.venv` on first run, rebuilds it after a Homebrew
Python upgrade broke it, and installs missing dependencies:
```bash
./run_tracker.sh
```

Running `python3 tracker.py` directly also works if pyserial and pyyaml are available to that Python.

### Command-Line Options

All options are passed through by the launcher (`./run_tracker.sh --summary`):

| Option | Description |
|---|---|
| `-s`, `--summary` | Print all entries and per-project totals for all tracking files, then exit. No Pico needed. |
| `-n`, `--no-pico` | Interactive menu to start/stop tracking from the terminal, without the Pico. |
| `-h`, `--help` | Show usage. |

The serial port can be pinned with `PICO_PORT_FILTER=<substring>` when several USB modems are connected.

### Normal Operation

The tracker will:
1. Automatically find and connect to your Pico
2. Load project labels from `config.yaml` if it exists
3. Wait for button presses

### Button Layout

#### Layer 0 (Default Layer)

| Button | Function | Description |
|--------|----------|-------------|
| 1 | Toggle Tracking | Start/stop time tracking (defaults to "Allgemein") |
| 2 | Support | Track support time (Yellow) |
| 3 | Meeting | Track meeting time (Orange) |
| 4 | Project 1 | Track Project 1 (Green) |
| 5 | Project 2 | Track Project 2 (Blue) |
| 6 | Project 3 | Track Project 3 (Magenta) |
| 7 | Project 4 | Track Project 4 (Pink) |
| 8 | Show Today | Display today's time summary |
| 9 | Layer Shift | Switch to Layer 1 |

#### Layer 1 (Activated by Button 9)

| Button | Function | Description |
|--------|----------|-------------|
| 1 | Project 5 | Track Project 5 (Lime) |
| 2 | Project 6 | Track Project 6 (Cyan-green) |
| 3 | Project 7 | Track Project 7 (Purple) |
| 4 | Project 8 | Track Project 8 (Orange-red) |
| 5 | Project 9 | Track Project 9 (Sky blue) |
| 6 | Project 10 | Track Project 10 (Gold) |
| 7 | Project 11 | Track Project 11 (Violet) |
| 8 | Prevent Sleep | Toggle Mac sleep prevention (macOS only) |
| 9 | Layer Shift | Switch back to Layer 0 |

### LED Indicators

The 8 LEDs provide visual feedback:

- **LED 0**: Tracking status (Green = tracking, Off = not tracking)
- **LED 1**: Prevent sleep indicator (Blue = active)
- **LED 2**: Current project color
- **LED 3-6**: Available for future use
- **LED 7**: Layer indicator (Yellow = Layer 1 active, Off = Layer 0)

### How It Works

1. **Start Tracking**: Press a project button (2-7 on Layer 0, or 1-7 on Layer 1)
   - Automatically stops any currently running task
   - Starts tracking the selected project
   - LED 0 turns green, LED 2 shows project color

2. **Stop Tracking**: Press Button 1 (toggle) to stop
   - Saves the current session to today's CSV file
   - LEDs turn off

3. **Switch Projects**: Press any project button
   - Automatically stops current task and starts new one
   - Updates LEDs accordingly

4. **View Summary**: Press Button 8 on Layer 0
   - Shows all entries for today
   - Shows summary by project with total time

5. **Change Layer**: Press Button 9
   - Toggles between Layer 0 and Layer 1
   - LED 7 indicates Layer 1 is active

## Data Storage

Time tracking data is stored in CSV files, one per day, in the data directory
(next to `tracker.py` unless `data_dir` is set in `config.yaml`):

- Format: `times.YYMMDD.csv`
- Example: `times.251117.csv` (November 17, 2025)

Each row is one button press:
- `timestamp`: ISO timestamp of the press
- `label`: Project/task name, or `STOP` when tracking was stopped

The duration of an entry is the time until the next row. A day whose last row is not `STOP`
has a running task, which the tracker restores on the next start.

### CSV Structure

```csv
timestamp,label
2025-11-17T09:00:00,Project 1
2025-11-17T10:30:00,Meeting
2025-11-17T11:15:00,STOP
```

## Troubleshooting

### Pico Not Found

- Ensure the Pico is connected via USB
- Check that CircuitPython is properly installed
- Verify the Pico appears as `/dev/tty.usbmodem*` (macOS) or similar on Linux
- Try unplugging and replugging the USB cable

### Buttons Not Working

- Check wiring connections
- Verify buttons are connected to 3.3V (not 5V)
- Ensure internal pull-down resistors are configured (handled in code)

### LEDs Not Working

- Verify NeoPixel data line is connected to GP22
- Check power supply (NeoPixels can be power-hungry)
- Ensure correct number of LEDs is configured (8)

### "pyserial is missing" / PyYAML Warning

- Start via `./run_tracker.sh`; it installs `requirements.txt` into `.venv`
- A plain `pip install` on macOS usually targets a different Python than the one running the tracker

### Config File Not Loading

- Ensure `config.yaml` exists in the same directory as `tracker.py`
- Check YAML syntax is correct (use `config.yaml.example` as reference)
- Check console output for error messages

## Development

### Project Structure

```
Timelog/
├── tracker.py          # Main Python tracker application
├── pico/
│   ├── code.py         # CircuitPython firmware for Pico
│   └── boot.py         # Boot configuration (if needed)
├── calibrate_keymap.py # Helper to map physical buttons to numbers
├── config.yaml.example # Example configuration file
├── config.yaml         # Your actual config (git-ignored)
├── requirements.txt    # Python dependencies
├── run_tracker.sh      # Launcher script (creates/repairs .venv)
├── times.*.csv         # Time tracking data files (or in data_dir)
├── CLAUDE.md           # Notes for Claude Code
└── README.md           # This file
```

### Modifying Button Layout

Edit the `KEYMAP` dictionary in `tracker.py` to change button assignments, colors, or add new projects.

### Adding More Projects

1. Add new entries to `KEYMAP` in `tracker.py`
2. Update `config.yaml.example` with new project numbers
3. Update the `project_mapping` list in `load_project_config()` if needed

## License

See LICENSE file for details.

## Contributing

Feel free to submit issues or pull requests for improvements!

