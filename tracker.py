#!/usr/bin/env python3
import sys
import time
import glob
import csv
import os
from datetime import datetime
try:
    import serial  # pip install pyserial
except ImportError:
    print("Please install first: pip install pyserial")
    sys.exit(1)

# ----- CONFIG -----
# Mapping button -> label
KEYMAP = {
    1: "prevent_sleep",
    2: "tracking_toggle",  # Start/Stop
    3: "Besprechungen",
    4: "Projekt 1",
    5: "Projekt 2",
    6: "Projekt 3",
    7: "Support",
    8: "show_or_reset",
    9: "layer_toggle",
}

CSV_FILE = "times.csv"

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
    ser.write(f"LED:{idx}:{r},{g},{b}\n".encode("utf-8"))

# ----- TIME TRACKING LOGIC -----
class TimeTracker:
    def __init__(self, csv_file):
        self.csv_file = csv_file
        self.current_task = None
        self.current_start = None
        # Create CSV if it doesn't exist
        if not os.path.exists(csv_file):
            with open(csv_file, "w", newline="") as f:
                w = csv.writer(f)
                w.writerow(["start", "end", "label", "duration_seconds"])

    def start_task(self, label):
        # first stop old task
        self.stop_task()
        self.current_task = label
        self.current_start = time.time()
        print(f"[TRACK] started: {label} @ {datetime.now().isoformat(timespec='seconds')}")

    def stop_task(self):
        if self.current_task is None:
            return
        end = time.time()
        dur = int(end - self.current_start)
        with open(self.csv_file, "a", newline="") as f:
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
        # quick&dirty: read CSV and sum today
        # TODO: Looks like it's not working properly yet
        today = datetime.now().date()
        per_label = {}
        with open(self.csv_file, newline="") as f:
            r = csv.DictReader(f)
            for row in r:
                start = datetime.fromisoformat(row["start"])
                if start.date() == today:
                    dur = int(row["duration_seconds"])
                    per_label[row["label"]] = per_label.get(row["label"], 0) + dur
        print("---- TODAY ----")
        for label, secs in per_label.items():
            mins = secs // 60
            print(f"{label:15s} {mins:4d} min")
        print("---------------")

    def reset_today(self):
        # Minimalist: we create a new file.
        # (could also filter)
        backup = self.csv_file + ".bak"
        if os.path.exists(self.csv_file):
            os.rename(self.csv_file, backup)
        with open(self.csv_file, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["start", "end", "label", "duration_seconds"])
        print("[TRACK] today's file reset (old one in .bak).")

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

    tracker = TimeTracker(CSV_FILE)

    prevent_sleep = False
    layer = 1
    last_btn8_time = 0

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
            
            # Debug: show all received lines
            if line:
                print(f"[DEBUG] Received: {repr(line)}")
            
            if not line.startswith("BTN:"):
                continue

            btn_num = int(line.split(":")[1])
            action = KEYMAP.get(btn_num, None)
            print(f"[EVENT] Button {btn_num} → {action}")

            if action == "prevent_sleep":
                # here instead of mouse jiggle simply start/stop caffeinate
                # super simple: we just toggle the state and show LED 0
                prevent_sleep = not prevent_sleep
                if prevent_sleep:
                    print("[SLEEP] Active (please in real: subprocess caffeinate)")
                    send_led(ser, 0, 0, 0, 255)  # blue
                else:
                    print("[SLEEP] Inactive")
                    send_led(ser, 0, 0, 0, 0)

            elif action == "tracking_toggle":
                if tracker.current_task:
                    tracker.stop_task()
                    send_led_all(ser, 0, 0, 0)
                else:
                    # start without label? then "Allgemein"
                    tracker.start_task("Allgemein")
                    send_led_all(ser, 0, 255, 0)

            elif action in ("Besprechungen", "Support", "Projekt 1", "Projekt 2", "Projekt 3"):
                tracker.start_task(action)
                # show on LED index 1..5
                send_led_all(ser, 0, 0, 0)
                # choose LED by button (just for fun)
                idx = max(1, min(7, btn_num - 1))
                send_led(ser, idx, 0, 255, 0)

            elif action == "show_or_reset":
                now = time.time()
                # short press → show
                if now - last_btn8_time < 1.5:
                    # second press quickly after = reset
                    tracker.reset_today()
                    send_led_all(ser, 255, 0, 0)
                    time.sleep(0.3)
                    send_led_all(ser, 0, 0, 0)
                else:
                    tracker.show_today()
                last_btn8_time = now

            elif action == "layer_toggle":
                layer = 2 if layer == 1 else 1
                print(f"[LAYER] now {layer}")
                # show layer on LED 7
                if layer == 2:
                    send_led(ser, 7, 255, 255, 0)
                else:
                    send_led(ser, 7, 0, 0, 0)

    except KeyboardInterrupt:
        print("\n[INFO] Exiting, stopping any running task...")
        tracker.stop_task()
        send_led_all(ser, 0, 0, 0)

if __name__ == "__main__":
    main()
