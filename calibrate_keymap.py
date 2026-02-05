#!/usr/bin/env python3
"""
Key Map Calibration Script

This script calibrates the button mapping for a Pico keypad by asking the user
to press buttons 1-9 in order. The resulting mapping is saved to the device
itself (.key_map file on CIRCUITPY), so each keypad maintains its own correct
button order even if the wiring differs.
"""
import sys
import time
import glob
import os
import re

try:
    import serial
    from serial.serialutil import SerialException
except ImportError:
    print("Please install first: pip install pyserial")
    sys.exit(1)

CIRCUITPY_PATH = "/Volumes/CIRCUITPY"
KEY_MAP_FILENAME = ".key_map"
EXPECTED_DEVICE_ID = "PICO-KEYPAD-V1"


def ping_device(port, timeout=1.0):
    """Send PING command and check if device responds with correct ID."""
    try:
        ser = serial.Serial(port, 115200, timeout=timeout)
        time.sleep(0.1)
        ser.reset_input_buffer()
        ser.write(b"PING\n")
        ser.flush()

        start = time.time()
        buf = b""
        while time.time() - start < timeout:
            if ser.in_waiting > 0:
                buf += ser.read(ser.in_waiting)
                if b"\n" in buf:
                    break
            time.sleep(0.05)

        ser.close()

        response = buf.decode("utf-8", errors="ignore").strip()
        if response.startswith(f"PONG:{EXPECTED_DEVICE_ID}"):
            return True
        return False
    except SerialException:
        return False


def find_pico_port():
    """Find the Pico keypad serial port."""
    candidates = sorted(
        glob.glob("/dev/tty.usbmodem*") + glob.glob("/dev/tty.usbserial*")
    )
    if not candidates:
        raise RuntimeError("No Pico found (/dev/tty.usbmodem*).")

    print(f"[INFO] Found ports: {candidates}")

    # Group by common prefix (Pico dual CDC pattern)
    from collections import defaultdict
    groups = defaultdict(list)
    for port in candidates:
        match = re.search(r'usbmodem(\d{5,})', port)
        if match:
            prefix = match.group(1)[:5]
            groups[prefix].append(port)
        else:
            groups['other'].append(port)

    # Prefer groups with exactly 2 ports (Pico dual CDC pattern)
    pico_candidates = []
    for prefix, ports in groups.items():
        if len(ports) == 2:
            pico_candidates.extend(ports)

    if pico_candidates:
        candidates = sorted(pico_candidates)

    # Try to identify the correct device using PING
    for port in reversed(candidates):
        try:
            print(f"[INFO] Pinging {port}...")
            if ping_device(port):
                print(f"[INFO] Found keypad on {port}")
                return port
            else:
                print(f"[INFO] {port} is not the keypad")
        except SerialException as e:
            print(f"[WARN] Port {port} not usable: {e}")

    raise RuntimeError(f"No Pico keypad found. Make sure the device responds to PING.")


def wait_for_button(ser, timeout=30.0):
    """Wait for a button press and return the raw button number."""
    start = time.time()
    buf = b""

    while time.time() - start < timeout:
        if ser.in_waiting > 0:
            buf += ser.read(ser.in_waiting)
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                line = line.decode("utf-8", errors="ignore").strip()
                if line.startswith("BTN:"):
                    parts = line.split(":")
                    # Skip long press events
                    if len(parts) > 2 and parts[2] == "LONG":
                        continue
                    return int(parts[1])
        time.sleep(0.01)

    return None


def send_led(ser, idx, r, g, b):
    """Set a single LED color."""
    ser.write(f"LED:{idx}:{r},{g},{b}\n".encode("utf-8"))
    ser.flush()


def send_led_all(ser, r, g, b):
    """Set all LEDs to a color."""
    ser.write(f"LED:ALL:{r},{g},{b}\n".encode("utf-8"))
    ser.flush()


def is_circuitpy_mounted():
    """Check if CIRCUITPY drive is mounted."""
    return os.path.isdir(CIRCUITPY_PATH)


def get_key_map_path():
    """Get path to .key_map on the mounted CIRCUITPY drive."""
    return os.path.join(CIRCUITPY_PATH, KEY_MAP_FILENAME)


def load_existing_key_map():
    """Load existing key map from device if it exists."""
    key_map_path = get_key_map_path()
    if not os.path.exists(key_map_path):
        return None

    try:
        key_map = {}
        with open(key_map_path, "r") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split(":")
                if len(parts) == 2:
                    raw_btn = int(parts[0])
                    logical_btn = int(parts[1])
                    key_map[raw_btn] = logical_btn
        return key_map
    except Exception as e:
        print(f"[WARN] Error reading existing key map: {e}")
        return None


def save_key_map(key_map):
    """Save key map to the CIRCUITPY device."""
    if not is_circuitpy_mounted():
        print("[ERROR] CIRCUITPY drive not mounted!")
        print("[INFO] Please ensure the Pico is in CIRCUITPY mode.")
        return False

    key_map_path = get_key_map_path()
    try:
        with open(key_map_path, "w") as f:
            f.write("# Pico Keypad Button Mapping\n")
            f.write("# Format: raw_button:logical_button\n")
            f.write("# Generated by calibrate_keymap.py\n")
            f.write(f"# Created: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("\n")
            for raw_btn, logical_btn in sorted(key_map.items()):
                f.write(f"{raw_btn}:{logical_btn}\n")

        print(f"[INFO] Key map saved to {key_map_path}")
        return True
    except Exception as e:
        print(f"[ERROR] Failed to save key map: {e}")
        return False


def print_key_map_grid(key_map):
    """Print the key map as a 3x3 grid showing raw -> logical mapping."""
    print("\n┌─────────────────────────────────────┐")
    print("│         KEY MAP (Raw → Logical)     │")
    print("├───────────┬───────────┬─────────────┤")

    # Reverse map: logical -> raw
    logical_to_raw = {v: k for k, v in key_map.items()}

    for row in range(3):
        cells = []
        for col in range(3):
            logical = row * 3 + col + 1
            raw = logical_to_raw.get(logical, "?")
            cells.append(f"  {raw} → {logical}  ")
        print(f"│{cells[0]}│{cells[1]}│{cells[2]}│")
        if row < 2:
            print("├───────────┼───────────┼─────────────┤")

    print("└───────────┴───────────┴─────────────┘")


def calibrate():
    """Main calibration routine."""
    print("=" * 50)
    print("    PICO KEYPAD CALIBRATION")
    print("=" * 50)
    print()

    # Check if CIRCUITPY is mounted
    if not is_circuitpy_mounted():
        print("[ERROR] CIRCUITPY drive not mounted!")
        print("[INFO] The key map file needs to be saved to the Pico's filesystem.")
        print("[INFO] Please ensure the Pico is connected and CIRCUITPY is mounted.")
        print(f"[INFO] Expected path: {CIRCUITPY_PATH}")
        return False

    # Show existing key map if present
    existing_map = load_existing_key_map()
    if existing_map:
        print("[INFO] Existing key map found on device:")
        print_key_map_grid(existing_map)
        print()
        response = input("Do you want to recalibrate? [y/N]: ").strip().lower()
        if response != 'y':
            print("[INFO] Keeping existing key map.")
            return True

        # Delete existing key map and prompt for reset
        # The Pico loads the key map at startup, so we need to reset it
        # to get raw button numbers during calibration
        key_map_path = get_key_map_path()
        try:
            os.remove(key_map_path)
            print(f"[INFO] Deleted existing key map: {key_map_path}")
        except Exception as e:
            print(f"[WARN] Could not delete key map: {e}")

        print()
        print("=" * 50)
        print("  IMPORTANT: Please reset the Pico now!")
        print("  (Unplug and replug the USB cable)")
        print("=" * 50)
        print()
        input("Press Enter after resetting the Pico...")
        print()

        # Wait for CIRCUITPY to remount
        print("[INFO] Waiting for CIRCUITPY to mount...")
        for _ in range(30):
            if is_circuitpy_mounted():
                break
            time.sleep(0.5)
        else:
            print("[ERROR] CIRCUITPY did not remount in time.")
            return False
        print("[INFO] CIRCUITPY mounted.")
        time.sleep(1)  # Give it a moment to stabilize

    # Find and connect to Pico
    try:
        port = find_pico_port()
    except RuntimeError as e:
        print(f"[ERROR] {e}")
        return False

    print(f"\n[INFO] Connecting to {port}...")
    ser = serial.Serial(port, 115200, timeout=0.1)
    time.sleep(0.5)
    ser.reset_input_buffer()

    # Clear all LEDs
    send_led_all(ser, 0, 0, 0)

    print()
    print("=" * 50)
    print("  Press buttons 1-9 in order (as labeled on keypad)")
    print("  The button layout should be:")
    print()
    print("      ┌───┬───┬───┐")
    print("      │ 1 │ 2 │ 3 │")
    print("      ├───┼───┼───┤")
    print("      │ 4 │ 5 │ 6 │")
    print("      ├───┼───┼───┤")
    print("      │ 7 │ 8 │ 9 │")
    print("      └───┴───┴───┘")
    print()
    print("=" * 50)
    print()

    key_map = {}  # raw_button -> logical_button

    for logical_btn in range(1, 10):
        # Light up LED to indicate which button to press (if we have enough LEDs)
        if logical_btn <= 8:
            send_led(ser, logical_btn - 1, 0, 50, 50)  # Cyan indicator

        print(f"Press button {logical_btn}...", end=" ", flush=True)

        raw_btn = wait_for_button(ser, timeout=30.0)

        if raw_btn is None:
            print("TIMEOUT!")
            send_led_all(ser, 0, 0, 0)
            ser.close()
            return False

        # Check if this raw button was already used
        if raw_btn in key_map:
            print(f"ERROR! Button {raw_btn} was already assigned to logical button {key_map[raw_btn]}")
            send_led_all(ser, 50, 0, 0)  # Red error
            time.sleep(1)
            send_led_all(ser, 0, 0, 0)
            ser.close()
            return False

        key_map[raw_btn] = logical_btn
        print(f"OK (raw button {raw_btn})")

        # Turn LED green to show success
        if logical_btn <= 8:
            send_led(ser, logical_btn - 1, 0, 50, 0)  # Green success

    # Flash all LEDs green to indicate success
    for _ in range(3):
        send_led_all(ser, 0, 100, 0)
        time.sleep(0.2)
        send_led_all(ser, 0, 0, 0)
        time.sleep(0.2)

    ser.close()

    print()
    print("=" * 50)
    print("  CALIBRATION COMPLETE!")
    print("=" * 50)
    print_key_map_grid(key_map)

    # Save the key map
    if save_key_map(key_map):
        print()
        print("[INFO] Key map saved to device.")
        print("[INFO] The Pico firmware will use this mapping automatically.")
        return True
    else:
        print()
        print("[ERROR] Failed to save key map!")
        print("[INFO] You can manually create the file at:")
        print(f"       {get_key_map_path()}")
        return False


def show_current():
    """Show the current key map without recalibrating."""
    if not is_circuitpy_mounted():
        print("[ERROR] CIRCUITPY drive not mounted!")
        return False

    existing_map = load_existing_key_map()
    if existing_map:
        print("[INFO] Current key map on device:")
        print_key_map_grid(existing_map)
        return True
    else:
        print("[INFO] No key map found on device.")
        print("[INFO] Run without --show to calibrate.")
        return False


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Calibrate Pico keypad button mapping")
    parser.add_argument("--show", "-s", action="store_true",
                        help="Show current key map without recalibrating")
    args = parser.parse_args()

    if args.show:
        success = show_current()
    else:
        success = calibrate()

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
