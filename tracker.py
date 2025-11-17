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
except ImportError:
    print("Please install first: pip install pyserial")
    sys.exit(1)

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
        4: {"action": "project", "label": "Projekt 1", "color": (0, 255, 0)},  # Green
        5: {"action": "project", "label": "Projekt 2", "color": (0, 0, 255)},  # Blue
        6: {"action": "project", "label": "Projekt 3", "color": (255, 0, 255)},  # Magenta
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

# CSV files are created per day: times.YYMMDD.csv

# ----- SERIAL HELPER FUNCTIONS -----
def find_pico_port():
    candidates = sorted(
        glob.glob("/dev/tty.usbmodem*") + glob.glob("/dev/tty.usbserial*")
    )
    if not candidates:
        raise RuntimeError("No Pico found (/dev/tty.usbmodem*).")

    import serial  # local, so we have SerialException
    from serial.serialutil import SerialException

    # If multiple ports found, prefer the higher one (usually data port)
    # If only one exists, take it
    print(f"[INFO] Found ports: {candidates}")
    
    # Try the last port first (usually data port if both active)
    for port in reversed(candidates):
        try:
            # briefly open and immediately close for testing
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

# ----- TIME TRACKING LOGIC -----
def get_csv_filename():
    """Get the CSV filename for today's date in format times.YYMMDD.csv"""
    today = datetime.now()
    return f"times.{today.strftime('%y%m%d')}.csv"

class TimeTracker:
    def __init__(self):
        self.current_task = None
        self.current_start = None
        self.current_csv_file = None
        self._ensure_csv_file()

    def _ensure_csv_file(self):
        """Ensure the CSV file for today exists and update current_csv_file"""
        self.current_csv_file = get_csv_filename()
        if not os.path.exists(self.current_csv_file):
            with open(self.current_csv_file, "w", newline="") as f:
                w = csv.writer(f)
                w.writerow(["start", "end", "label", "duration_seconds"])

    def _check_day_change(self, stop_current_task=False):
        """Check if day has changed and switch to new CSV file if needed"""
        new_csv_file = get_csv_filename()
        if new_csv_file != self.current_csv_file:
            # Day changed - stop current task if requested and switch files
            if stop_current_task and self.current_task:
                # Save current task to old file before switching
                end = time.time()
                dur = int(end - self.current_start)
                with open(self.current_csv_file, "a", newline="") as f:
                    w = csv.writer(f)
                    w.writerow([
                        datetime.fromtimestamp(self.current_start).isoformat(timespec='seconds'),
                        datetime.fromtimestamp(end).isoformat(timespec='seconds'),
                        self.current_task,
                        dur
                    ])
                print(f"[TRACK] Day changed - saved {self.current_task} ({dur}s) to {self.current_csv_file}")
                self.current_task = None
                self.current_start = None
            self.current_csv_file = new_csv_file
            self._ensure_csv_file()

    def start_task(self, label):
        # Check if day changed (don't stop task, just switch file)
        self._check_day_change(stop_current_task=False)
        # first stop old task
        self.stop_task()
        self.current_task = label
        self.current_start = time.time()
        print(f"[TRACK] started: {label} @ {datetime.now().isoformat(timespec='seconds')}")

    def stop_task(self):
        if self.current_task is None:
            return
        # Check if day changed before writing (don't stop task recursively)
        self._check_day_change(stop_current_task=False)
        end = time.time()
        dur = int(end - self.current_start)
        with open(self.current_csv_file, "a", newline="") as f:
            w = csv.writer(f)
            w.writerow([
                datetime.fromtimestamp(self.current_start).isoformat(timespec='seconds'),
                datetime.fromtimestamp(end).isoformat(timespec='seconds'),
                self.current_task,
                dur
            ])
        print(f"[TRACK] stopped: {self.current_task} ({dur}s)")
        self.current_task = None
        self.current_start = None

    def show_today(self):
        """Show today's time tracking summary"""
        csv_file = get_csv_filename()
        if not os.path.exists(csv_file):
            print("---- TODAY ----")
            print("No tracking data for today")
            print("---------------")
            return
        
        today = datetime.now().date()
        entries = []
        per_label = {}
        
        # Read all entries for today
        with open(csv_file, newline="") as f:
            r = csv.DictReader(f)
            for row in r:
                start = datetime.fromisoformat(row["start"])
                if start.date() == today:
                    end = datetime.fromisoformat(row["end"])
                    dur = int(row["duration_seconds"])
                    label = row["label"]
                    entries.append({
                        "start": start,
                        "end": end,
                        "label": label,
                        "duration": dur
                    })
                    per_label[label] = per_label.get(label, 0) + dur
        
        # Format duration as "Xm Ys"
        def format_duration(seconds):
            mins = seconds // 60
            secs = seconds % 60
            return f"{mins}m {secs}s"
        
        # First list: All individual entries
        print("---- TODAY - ALL ENTRIES ----")
        if not entries:
            print("No entries")
        else:
            for entry in entries:
                start_str = entry["start"].strftime("%H:%M:%S")
                end_str = entry["end"].strftime("%H:%M:%S")
                dur_str = format_duration(entry["duration"])
                print(f"{start_str} - {end_str} | {entry['label']:20s} | {dur_str:>8s}")
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

def main():
    port = find_pico_port()
    print(f"[INFO] Connecting to {port}")
    ser = serial.Serial(port, 115200, timeout=0.1)
    
    # Wait briefly for connection to stabilize
    time.sleep(0.5)
    
    # Clear input buffer
    ser.reset_input_buffer()
    ser.reset_output_buffer()
    
    print("[INFO] Connection established, waiting for events...")
    print("[INFO] Press a button on the Pico to test...")

    tracker = TimeTracker()

    prevent_sleep = False
    caffeinate_proc = None
    layer = 0  # Start with layer 0 (default)

    # clear LEDs on startup
    send_led_all(ser, 0, 0, 0)
    ser.flush()  # Ensure data is sent

    try:
        while True:
            line = ser.readline()
            if not line:
                time.sleep(0.01)
                continue

            line = line.decode("utf-8", errors="ignore").strip()
            if not line.startswith("BTN:"):
                continue

            btn_num = int(line.split(":")[1])
            
            # Look up action in the current layer
            layer_map = KEYMAP.get(layer, {})
            config = layer_map.get(btn_num, None)
            
            if config is None:
                print(f"[EVENT] Button {btn_num} → no mapping in layer {layer}")
                continue
            
            action = config.get("action")
            if action == "prevent_sleep":
                # here instead of mouse jiggle simply start/stop caffeinate
                # super simple: we just toggle the state and show LED 1
                prevent_sleep = not prevent_sleep
                if prevent_sleep:
                    print("[SLEEP] Active (please in real: subprocess caffeinate)")
                    caffeinate_proc = subprocess.Popen(["caffeinate", "-dimsu"])
                    send_led(ser, 1, 0, 0, 255)  # blue on LED 1
                else:
                    print("[SLEEP] Inactive")
                    if caffeinate_proc is not None:
                        caffeinate_proc.terminate()
                        caffeinate_proc = None
                    send_led(ser, 1, 0, 0, 0)  # off on LED 1

            elif action == "tracking_toggle":
                if tracker.current_task:
                    tracker.stop_task()
                    send_led_stop_anim(ser)  # Stop any animation
                    send_led(ser, 0, 0, 0, 0)  # Turn off tracking LED
                    send_led(ser, 2, 0, 0, 0)  # Turn off project color LED
                else:
                    # start without label? then "Allgemein"
                    tracker.start_task("Allgemein")
                    # Use default green color for "Allgemein"
                    send_led(ser, 0, 0, 255, 0)  # Green on LED 0 (tracking status)
                    send_led(ser, 2, 0, 255, 0)  # Green on LED 2 (project color)

            elif action == "project":
                # Start tracking a project with its color
                label = config.get("label", "Unknown Project")
                color = config.get("color", (0, 255, 0))  # Default to green if no color
                tracker.start_task(label)
                # Stop any running animation first
                send_led_stop_anim(ser)
                # Show tracking status on LED 0 (green when tracking)
                send_led(ser, 0, 0, 255, 0)
                # Show project color on LED 2
                send_led(ser, 2, color[0], color[1], color[2])
                print(f"[PROJECT] Started {label} with color {color}")

            elif action == "show_today":
                tracker.show_today()

            elif action == "layer_shift":
                # Toggle between layer 0 and layer 1
                layer = 1 if layer == 0 else 0
                print(f"[LAYER] Switched to layer {layer}")
                # Show layer indicator on LED 7 (doesn't affect other LEDs)
                if layer == 1:
                    send_led(ser, 7, 255, 255, 0)  # Yellow when layer 1 is active
                else:
                    send_led(ser, 7, 0, 0, 0)  # Off when layer 0 is active

    except KeyboardInterrupt:
        print("\n[INFO] Exiting, stopping any running task...")
        tracker.stop_task()
        send_led_stop_anim(ser)
        send_led_all(ser, 0, 0, 0)
        if caffeinate_proc is not None:
            caffeinate_proc.terminate()

if __name__ == "__main__":
    main()
