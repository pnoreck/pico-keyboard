#!/usr/bin/env python3
import sys
import time
import glob
import csv
import os
import subprocess
import re
from datetime import datetime
try:
    import serial  # pip install pyserial
    from serial.serialutil import SerialException
except ImportError:
    print("Please install first: pip install pyserial")
    sys.exit(1)

try:
    import yaml  # pip install pyyaml
except ImportError:
    yaml = None
    print("[WARN] PyYAML not installed. Config file support disabled. Install with: pip install pyyaml")

# ----- CONFIG -----
# LED Layout (8 LEDs total):
#   LED 0: Tracking status (green when tracking, off when not)
#   LED 1: Prevent sleep indicator (blue when active)
#   LED 2: Project color (shows current project color)
#   LED 3-6: Available for future use
#   LED 7: Layer indicator (yellow when layer 1 is active)
#
# Keymap structure: layer -> button -> config dict
# Each config can have: "action" (required), "label" (for projects), "color" (RGB tuple)
KEYMAP = {
    0: {  # Layer 0 (default)
        1: {"action": "tracking_toggle"},
        2: {"action": "project", "label": "Support", "color": (255, 255, 0)},  # Yellow
        3: {"action": "project", "label": "Meeting", "color": (255, 100, 0)},  # Orange
        4: {"action": "project", "label": "Project 1", "color": (0, 255, 0)},  # Green
        5: {"action": "project", "label": "Project 2", "color": (0, 0, 255)},  # Blue
        6: {"action": "project", "label": "Project 3", "color": (255, 0, 255)},  # Magenta
        7: {"action": "project", "label": "Project 4", "color": (255, 0, 128)},  # Pink
        8: {"action": "show_today"},
        9: {"action": "layer_shift"},  # Layer shift key - toggles to layer 1
    },
    1: {  # Layer 1 (activated by key 9)
        1: {"action": "project", "label": "Project 5", "color": (128, 255, 0)},  # Lime
        2: {"action": "project", "label": "Project 6", "color": (0, 255, 128)},  # Cyan-green
        3: {"action": "project", "label": "Project 7", "color": (128, 0, 255)},  # Purple
        4: {"action": "project", "label": "Project 8", "color": (255, 128, 0)},  # Orange-red
        5: {"action": "project", "label": "Project 9", "color": (0, 128, 255)},  # Sky blue
        6: {"action": "project", "label": "Project 10", "color": (255, 192, 0)},  # Gold
        7: {"action": "project", "label": "Project 11", "color": (192, 0, 255)},  # Violet
        8: {"action": "prevent_sleep"},
        9: {"action": "layer_shift"},  # Layer shift key - toggles back to layer 0
    }
}

# ----- CONFIG FILE LOADING -----
def load_project_config():
    """Load project labels from config.yaml if it exists and update KEYMAP"""
    if yaml is None:
        return  # PyYAML not available
    
    config_file = "config.yaml"
    if not os.path.exists(config_file):
        return  # Config file doesn't exist, use defaults
    
    try:
        with open(config_file, "r") as f:
            config = yaml.safe_load(f)
        
        if not config or "projects" not in config:
            return  # Invalid config structure
        
        projects = config["projects"]
        
        # Update labels for Project 1-11
        # Project 1-3 are in layer 0, buttons 4-6
        # Project 4 is in layer 0, button 7
        # Project 5-11 are in layer 1, buttons 1-7
        
        project_mapping = [
            (0, 4, 1),  # Layer 0, Button 4 -> Project 1
            (0, 5, 2),  # Layer 0, Button 5 -> Project 2
            (0, 6, 3),  # Layer 0, Button 6 -> Project 3
            (0, 7, 4),  # Layer 0, Button 7 -> Project 4
            (1, 1, 5),  # Layer 1, Button 1 -> Project 5
            (1, 2, 6),  # Layer 1, Button 2 -> Project 6
            (1, 3, 7),  # Layer 1, Button 3 -> Project 7
            (1, 4, 8),  # Layer 1, Button 4 -> Project 8
            (1, 5, 9),  # Layer 1, Button 5 -> Project 9
            (1, 6, 10), # Layer 1, Button 6 -> Project 10
            (1, 7, 11), # Layer 1, Button 7 -> Project 11
        ]
        
        for layer, button, project_num in project_mapping:
            project_key = str(project_num)
            if project_key in projects:
                new_label = projects[project_key]
                if layer in KEYMAP and button in KEYMAP[layer]:
                    if KEYMAP[layer][button].get("action") == "project":
                        KEYMAP[layer][button]["label"] = new_label
                        print(f"[CONFIG] Updated Project {project_num} label to: {new_label}")
        
    except Exception as e:
        print(f"[WARN] Error loading config.yaml: {e}")
        print("[WARN] Using default project labels")

# Load config on import
load_project_config()

# CSV files are created per day: times.YYMMDD.csv
# Format: Each row is a button press with timestamp and label
# Duration is calculated as difference to next entry when reading

# ----- PICO FIRMWARE AUTO-UPDATE -----
CIRCUITPY_PATH = "/Volumes/CIRCUITPY"
PICO_CODE_FILENAME = "code.py"

def get_script_dir():
    """Get the directory where this script is located"""
    return os.path.dirname(os.path.abspath(__file__))

def get_local_pico_code_path():
    """Get path to local pico/code.py"""
    return os.path.join(get_script_dir(), "pico", PICO_CODE_FILENAME)

def get_pico_code_path():
    """Get path to code.py on the mounted CIRCUITPY drive"""
    return os.path.join(CIRCUITPY_PATH, PICO_CODE_FILENAME)

def is_circuitpy_mounted():
    """Check if CIRCUITPY drive is mounted"""
    return os.path.isdir(CIRCUITPY_PATH)

def files_are_identical(path1, path2):
    """Compare two files by content"""
    try:
        with open(path1, "rb") as f1, open(path2, "rb") as f2:
            return f1.read() == f2.read()
    except (IOError, OSError):
        return False

def check_and_update_pico_firmware():
    """
    Check if Pico firmware needs updating and copy if necessary.
    Returns True if update was performed (Pico will restart).
    """
    local_code = get_local_pico_code_path()
    pico_code = get_pico_code_path()

    # Check if local pico/code.py exists
    if not os.path.exists(local_code):
        print(f"[WARN] Local firmware not found: {local_code}")
        return False

    # Check if CIRCUITPY is mounted
    if not is_circuitpy_mounted():
        # Not mounted - Pico is probably running normally, which is fine
        return False

    # Check if code.py exists on Pico
    if not os.path.exists(pico_code):
        print("[UPDATE] No code.py on Pico, copying firmware...")
    elif files_are_identical(local_code, pico_code):
        print("[UPDATE] Pico firmware is up to date")
        return False
    else:
        print("[UPDATE] Pico firmware differs, updating...")

    # Copy the file
    try:
        import shutil
        shutil.copy2(local_code, pico_code)
        print("[UPDATE] Firmware copied successfully!")
        print("[UPDATE] Pico will restart automatically...")
        # Give the filesystem time to sync and Pico to restart
        time.sleep(3)
        return True
    except (IOError, OSError) as e:
        print(f"[ERROR] Failed to copy firmware: {e}")
        return False

# ----- SERIAL HELPER FUNCTIONS -----
def find_pico_port(port_filter=None):
    candidates = sorted(
        glob.glob("/dev/tty.usbmodem*") + glob.glob("/dev/tty.usbserial*")
    )
    if not candidates:
        raise RuntimeError("No Pico found (/dev/tty.usbmodem*).")

    import serial  # local, so we have SerialException
    from serial.serialutil import SerialException

    print(f"[INFO] Found ports: {candidates}")

    # Apply port filter if specified (e.g., "usbmodem2022" from config)
    if port_filter:
        filtered = [p for p in candidates if port_filter in p]
        if filtered:
            print(f"[INFO] Filtered by '{port_filter}': {filtered}")
            candidates = filtered

    # Pico with dual CDC creates two ports with similar prefixes.
    # Group by common prefix and prefer groups with 2+ ports.
    from collections import defaultdict
    groups = defaultdict(list)
    for port in candidates:
        # Extract prefix: /dev/tty.usbmodem20224 -> 20224 (first 5 digits after usbmodem)
        import re
        match = re.search(r'usbmodem(\d{5,})', port)
        if match:
            prefix = match.group(1)[:5]  # First 5 digits as group key
            groups[prefix].append(port)
        else:
            groups['other'].append(port)

    # Prefer groups with exactly 2 ports (Pico dual CDC pattern)
    pico_candidates = []
    for prefix, ports in groups.items():
        if len(ports) == 2:
            pico_candidates.extend(ports)

    if pico_candidates:
        print(f"[INFO] Detected Pico dual CDC ports: {pico_candidates}")
        candidates = sorted(pico_candidates)

    # Try the last port first (data port is usually higher number)
    for port in reversed(candidates):
        try:
            test = serial.Serial(port, 115200, timeout=0.1)
            test.close()
            print(f"[INFO] Using port: {port}")
            return port
        except SerialException as e:
            print(f"[WARN] Port {port} not usable: {e}")

    # Fallback: try all in normal order
    for port in candidates:
        try:
            test = serial.Serial(port, 115200, timeout=0.1)
            test.close()
            print(f"[INFO] Using port (fallback): {port}")
            return port
        except SerialException as e:
            print(f"[WARN] Port {port} not usable: {e}")

    raise RuntimeError("No free Pico serial port found (all busy?).")


def send_led_all(ser, r, g, b):
    ser.write(f"LED:ALL:{r},{g},{b}\n".encode("utf-8"))

def send_led(ser, idx, r, g, b):
    """Set a single LED without affecting others"""
    ser.write(f"LED:{idx}:{r},{g},{b}\n".encode("utf-8"))

def send_led_anim(ser, idx, r, g, b):
    """Start a pulse animation on a specific LED"""
    ser.write(f"LED:ANIM:{idx}:{r},{g},{b}\n".encode("utf-8"))

def send_led_stop_anim(ser):
    """Stop any running animation"""
    ser.write(f"LED:STOP\n".encode("utf-8"))

# ----- KEY GRID DISPLAY -----
def get_key_label(layer, button):
    """Get the display label for a key in the given layer"""
    config = KEYMAP.get(layer, {}).get(button, {})
    action = config.get("action", "")
    if action == "project":
        return config.get("label", "Project")
    elif action == "tracking_toggle":
        return "Toggle"
    elif action == "show_today":
        return "Today"
    elif action == "layer_shift":
        return "Layer"
    elif action == "prevent_sleep":
        return "Caffeine"
    return "?"

def print_key_grid():
    """Print a 3x3 grid showing key labels for both layers"""
    # Button layout in 3x3 grid (buttons 1-9)
    # Row 1: 1, 2, 3
    # Row 2: 4, 5, 6
    # Row 3: 7, 8, 9

    col_width = 25

    for layer in [0, 1]:
        print(f"\n┌{'─' * (col_width * 3 + 4)}┐")
        print(f"│{f'Layer {layer}':^{col_width * 3 + 4}}│")
        print(f"├{'─' * col_width}┬{'─' * col_width}┬{'─' * col_width}┤")

        for row in range(3):
            labels = []
            for col in range(3):
                btn = row * 3 + col + 1
                label = get_key_label(layer, btn)
                labels.append(f"{label:^{col_width}}")
            print(f"│{'│'.join(labels)}│")

            if row < 2:
                print(f"├{'─' * col_width}┼{'─' * col_width}┼{'─' * col_width}┤")

        print(f"└{'─' * col_width}┴{'─' * col_width}┴{'─' * col_width}┘")

# ----- TIME TRACKING LOGIC -----
def get_csv_filename():
    """Get the CSV filename for today's date in format times.YYMMDD.csv"""
    today = datetime.now()
    return f"times.{today.strftime('%y%m%d')}.csv"

class TimeTracker:
    def __init__(self):
        self.current_task = None
        self.current_csv_file = None
        self._ensure_csv_file()
        self._restore_state()

    def _restore_state(self):
        """Restore current_task from CSV if there's an active task (no STOP after last entry)"""
        if not os.path.exists(self.current_csv_file):
            return

        last_label = None
        with open(self.current_csv_file, newline="") as f:
            r = csv.DictReader(f)
            for row in r:
                last_label = row["label"]

        # If last entry is not STOP, there's an active task
        if last_label and last_label != "STOP":
            self.current_task = last_label
            print(f"[TRACK] Restored active task: {last_label}")

    def _ensure_csv_file(self):
        """Ensure the CSV file for today exists and update current_csv_file"""
        self.current_csv_file = get_csv_filename()
        if not os.path.exists(self.current_csv_file):
            with open(self.current_csv_file, "w", newline="") as f:
                w = csv.writer(f)
                w.writerow(["timestamp", "label"])

    def _check_day_change(self):
        """Check if day has changed and switch to new CSV file if needed"""
        new_csv_file = get_csv_filename()
        if new_csv_file != self.current_csv_file:
            self.current_csv_file = new_csv_file
            self._ensure_csv_file()

    def start_task(self, label):
        """Write a new task entry immediately to CSV"""
        self._check_day_change()
        self.current_task = label
        now = datetime.now()
        with open(self.current_csv_file, "a", newline="") as f:
            w = csv.writer(f)
            w.writerow([now.isoformat(timespec='seconds'), label])
        print(f"[TRACK] started: {label} @ {now.isoformat(timespec='seconds')}")

    def stop_task(self):
        """Write a STOP entry to mark end of tracking"""
        if self.current_task is None:
            return
        self._check_day_change()
        now = datetime.now()
        with open(self.current_csv_file, "a", newline="") as f:
            w = csv.writer(f)
            w.writerow([now.isoformat(timespec='seconds'), "STOP"])
        print(f"[TRACK] stopped @ {now.isoformat(timespec='seconds')}")
        self.current_task = None

    def show_today(self):
        """Show today's time tracking summary by calculating durations between entries"""
        csv_file = get_csv_filename()
        if not os.path.exists(csv_file):
            print("---- TODAY ----")
            print("No tracking data for today")
            print("---------------")
            return

        today = datetime.now().date()
        raw_entries = []

        # Read all entries for today
        with open(csv_file, newline="") as f:
            r = csv.DictReader(f)
            for row in r:
                ts = datetime.fromisoformat(row["timestamp"])
                if ts.date() == today:
                    raw_entries.append({
                        "timestamp": ts,
                        "label": row["label"]
                    })

        if not raw_entries:
            print("---- TODAY ----")
            print("No tracking data for today")
            print("---------------")
            return

        # Calculate durations: each entry lasts until the next one
        entries = []
        per_label = {}

        for i, entry in enumerate(raw_entries):
            label = entry["label"]
            if label == "STOP":
                continue  # STOP entries are just markers, not tasks

            start = entry["timestamp"]
            # End time is the next entry's timestamp, or now if it's the last entry
            if i + 1 < len(raw_entries):
                end = raw_entries[i + 1]["timestamp"]
            else:
                end = datetime.now()  # Currently running task

            dur = int((end - start).total_seconds())
            entries.append({
                "start": start,
                "end": end,
                "label": label,
                "duration": dur,
                "is_running": i + 1 >= len(raw_entries)
            })
            per_label[label] = per_label.get(label, 0) + dur

        # Format duration as "Xh Ym Zs"
        def format_duration(seconds):
            hours = seconds // 3600
            mins = (seconds % 3600) // 60
            secs = seconds % 60
            if hours > 0:
                return f"{hours}h {mins}m {secs}s"
            return f"{mins}m {secs}s"

        # First list: All individual entries
        print("---- TODAY - ALL ENTRIES ----")
        if not entries:
            print("No entries")
        else:
            for entry in entries:
                start_str = entry["start"].strftime("%H:%M:%S")
                end_str = entry["end"].strftime("%H:%M:%S")
                if entry["is_running"]:
                    end_str = "running"
                dur_str = format_duration(entry["duration"])
                print(f"{start_str} - {end_str:>8s} | {entry['label']:20s} | {dur_str:>8s}")
        print()

        # Second list: Summary by project
        # Sort function: extract number from project name for sorting
        def project_sort_key(item):
            label = item[0]
            # Try to extract number from label (e.g., "Projekt 1" -> 1, "Project 10" -> 10)
            match = re.search(r'\d+', label)
            if match:
                # Has a number - return (1, number) so numbered projects come after non-numbered
                return (1, int(match.group()))
            else:
                # No number - return (0, label) so non-numbered projects come first
                return (0, label)

        print("---- TODAY - SUMMARY BY PROJECT ----")
        total_secs = 0
        for label, secs in sorted(per_label.items(), key=project_sort_key):
            dur_str = format_duration(secs)
            total_secs += secs
            print(f"{label:20s} | {dur_str:>8s}")
        print(f"{'TOTAL':20s} | {format_duration(total_secs):>8s}")
        print("------------------------------------")

def safe_send(ser, data):
    """Safely send data to serial port, returns False if disconnected"""
    try:
        ser.write(data.encode("utf-8"))
        ser.flush()
        return True
    except (SerialException, OSError):
        return False

def main():
    # Check and update Pico firmware if needed
    check_and_update_pico_firmware()

    # Allow port filter via env var: PICO_PORT_FILTER=2022 to match usbmodem2022*
    port_filter = os.environ.get("PICO_PORT_FILTER")

    tracker = TimeTracker()
    prevent_sleep = False
    caffeinate_proc = None
    layer = 0  # Start with layer 0 (default)
    ser = None
    reconnect_delay = 2.0  # seconds between reconnection attempts
    user_requested_exit = False

    print_key_grid()
    print("\n[INFO] Hold Layer button for 5 seconds to gracefully unmount keypad")

    try:
        while not user_requested_exit:
            # Connection loop - try to connect/reconnect
            if ser is None:
                try:
                    port = find_pico_port(port_filter)
                    print(f"[INFO] Connecting to {port}")
                    ser = serial.Serial(port, 115200, timeout=0.1)
                    time.sleep(0.5)
                    ser.reset_input_buffer()
                    ser.reset_output_buffer()
                    print("[INFO] Connection established, waiting for events...")

                    # Clear LEDs and restore state on reconnect
                    safe_send(ser, "LED:ALL:0,0,0\n")

                    # Restore LED state based on current tracking
                    if tracker.current_task:
                        safe_send(ser, "LED:0:0,255,0\n")  # Green tracking LED
                    if layer == 1:
                        safe_send(ser, "LED:7:255,255,0\n")  # Yellow layer indicator
                    if prevent_sleep:
                        safe_send(ser, "LED:1:0,0,255\n")  # Blue sleep LED

                except RuntimeError as e:
                    print(f"[WARN] {e}")
                    print(f"[INFO] Retrying in {reconnect_delay} seconds...")
                    time.sleep(reconnect_delay)
                    continue

            # Main event loop
            try:
                line = ser.readline()
                if not line:
                    time.sleep(0.01)
                    continue

                line = line.decode("utf-8", errors="ignore").strip()
                if not line.startswith("BTN:"):
                    continue

                parts = line.split(":")
                btn_num = int(parts[1])
                is_long_press = len(parts) > 2 and parts[2] == "LONG"

                # Handle long-press on layer_shift button (button 9) for graceful unmount
                if btn_num == 9 and is_long_press:
                    print("\n[INFO] Long press detected - unmounting keypad...")
                    user_requested_exit = True
                    continue

                # Skip regular button handling for long press events
                if is_long_press:
                    continue

                # Look up action in the current layer
                layer_map = KEYMAP.get(layer, {})
                config = layer_map.get(btn_num, None)

                if config is None:
                    print(f"[EVENT] Button {btn_num} → no mapping in layer {layer}")
                    continue

                action = config.get("action")
                if action == "prevent_sleep":
                    prevent_sleep = not prevent_sleep
                    if prevent_sleep:
                        print("[SLEEP] Active (please in real: subprocess caffeinate)")
                        caffeinate_proc = subprocess.Popen(["caffeinate", "-dimsu"])
                        safe_send(ser, "LED:1:0,0,255\n")
                    else:
                        print("[SLEEP] Inactive")
                        if caffeinate_proc is not None:
                            caffeinate_proc.terminate()
                            caffeinate_proc = None
                        safe_send(ser, "LED:1:0,0,0\n")

                elif action == "tracking_toggle":
                    if tracker.current_task:
                        tracker.stop_task()
                        safe_send(ser, "LED:STOP\n")
                        safe_send(ser, "LED:0:0,0,0\n")
                        safe_send(ser, "LED:2:0,0,0\n")
                    else:
                        tracker.start_task("Allgemein")
                        safe_send(ser, "LED:0:0,255,0\n")
                        safe_send(ser, "LED:2:0,255,0\n")

                elif action == "project":
                    label = config.get("label", "Unknown Project")
                    color = config.get("color", (0, 255, 0))
                    tracker.start_task(label)
                    safe_send(ser, "LED:STOP\n")
                    safe_send(ser, "LED:0:0,255,0\n")
                    safe_send(ser, f"LED:2:{color[0]},{color[1]},{color[2]}\n")
                    print(f"[PROJECT] Started {label} with color {color}")

                elif action == "show_today":
                    tracker.show_today()

                elif action == "layer_shift":
                    layer = 1 if layer == 0 else 0
                    print(f"[LAYER] Switched to layer {layer}")
                    if layer == 1:
                        safe_send(ser, "LED:7:255,255,0\n")
                    else:
                        safe_send(ser, "LED:7:0,0,0\n")

            except (SerialException, OSError) as e:
                print(f"\n[WARN] Connection lost: {e}")
                print(f"[INFO] Attempting to reconnect in {reconnect_delay} seconds...")
                try:
                    ser.close()
                except:
                    pass
                ser = None
                time.sleep(reconnect_delay)

    except KeyboardInterrupt:
        print("\n[INFO] Keyboard interrupt received...")

    # Cleanup
    print("[INFO] Exiting, stopping any running task...")
    tracker.stop_task()
    if ser is not None:
        try:
            safe_send(ser, "LED:STOP\n")
            safe_send(ser, "LED:ALL:0,0,0\n")
            ser.close()
        except:
            pass
    if caffeinate_proc is not None:
        caffeinate_proc.terminate()
    print("[INFO] Goodbye!")

if __name__ == "__main__":
    main()
