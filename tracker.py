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
    print("Bitte zuerst installieren: pip install pyserial")
    sys.exit(1)

# ----- KONFIG -----
# Zuordnung Taste -> Label
KEYMAP = {
    2: "tracking_toggle",  # Start/Stop
    3: "Besprechungen",
    4: "Projekt 1",
    5: "Projekt 2",
    6: "Projekt 3",
    7: "Support",
    8: "show_or_reset",
    9: "layer_toggle",
    1: "prevent_sleep",
}

CSV_FILE = "times.csv"

# ----- HILFSFUNKTIONEN FÜR SERIELL -----
def find_pico_port():
    candidates = sorted(
        glob.glob("/dev/tty.usbmodem*") + glob.glob("/dev/tty.usbserial*")
    )
    if not candidates:
        raise RuntimeError("Kein Pico gefunden (/dev/tty.usbmodem*).")

    import serial  # lokal, damit wir SerialException haben
    from serial.serialutil import SerialException

    # Wenn mehrere Ports gefunden, bevorzuge den höheren (meist data-Port)
    # Falls nur einer da ist, nimm den
    print(f"[INFO] Gefundene Ports: {candidates}")
    
    # Versuche zuerst den letzten Port (meist data-Port wenn beide aktiv)
    for port in reversed(candidates):
        try:
            # kurz testweise öffnen und sofort wieder schließen
            test = serial.Serial(port, 115200, timeout=0.1)
            test.close()
            print(f"[INFO] Verwende Port: {port}")
            return port
        except SerialException as e:
            print(f"[WARN] Port {port} nicht nutzbar: {e}")
    
    # Fallback: versuche alle in normaler Reihenfolge
    for port in candidates:
        try:
            test = serial.Serial(port, 115200, timeout=0.1)
            test.close()
            print(f"[INFO] Verwende Port (Fallback): {port}")
            return port
        except SerialException as e:
            print(f"[WARN] Port {port} nicht nutzbar: {e}")

    raise RuntimeError("Kein freier Pico-Serial-Port gefunden (alle busy?).")


def send_led_all(ser, r, g, b):
    ser.write(f"LED:ALL:{r},{g},{b}\n".encode("utf-8"))

def send_led(ser, idx, r, g, b):
    ser.write(f"LED:{idx}:{r},{g},{b}\n".encode("utf-8"))

# ----- TIME TRACKING LOGIK -----
class TimeTracker:
    def __init__(self, csv_file):
        self.csv_file = csv_file
        self.current_task = None
        self.current_start = None
        # CSV anlegen falls nicht da
        if not os.path.exists(csv_file):
            with open(csv_file, "w", newline="") as f:
                w = csv.writer(f)
                w.writerow(["start", "end", "label", "duration_seconds"])

    def start_task(self, label):
        # erst alten Task beenden
        self.stop_task()
        self.current_task = label
        self.current_start = time.time()
        print(f"[TRACK] gestartet: {label} @ {datetime.now().isoformat(timespec='seconds')}")

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
        print(f"[TRACK] gestoppt: {self.current_task} ({dur}s)")
        self.current_task = None
        self.current_start = None

    def show_today(self):
        # quick&dirty: CSV lesen und heute summieren
        today = datetime.now().date()
        per_label = {}
        with open(self.csv_file, newline="") as f:
            r = csv.DictReader(f)
            for row in r:
                start = datetime.fromisoformat(row["start"])
                if start.date() == today:
                    dur = int(row["duration_seconds"])
                    per_label[row["label"]] = per_label.get(row["label"], 0) + dur
        print("---- HEUTE ----")
        for label, secs in per_label.items():
            mins = secs // 60
            print(f"{label:15s} {mins:4d} min")
        print("---------------")

    def reset_today(self):
        # Minimalistisch: wir legen neue Datei an.
        # (man könnte auch filtern)
        backup = self.csv_file + ".bak"
        if os.path.exists(self.csv_file):
            os.rename(self.csv_file, backup)
        with open(self.csv_file, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["start", "end", "label", "duration_seconds"])
        print("[TRACK] heutige Datei zurückgesetzt (alte in .bak).")

def main():
    port = find_pico_port()
    print(f"[INFO] Verbinde zu {port}")
    ser = serial.Serial(port, 115200, timeout=0.1)
    
    # Warte kurz, damit Verbindung stabilisiert
    time.sleep(0.5)
    
    # Leere den Eingabepuffer
    ser.reset_input_buffer()
    ser.reset_output_buffer()
    
    print("[INFO] Verbindung hergestellt, warte auf Events...")
    print("[INFO] Drücke eine Taste auf dem Pico, um zu testen...")

    tracker = TimeTracker(CSV_FILE)

    prevent_sleep = False
    layer = 1
    last_btn8_time = 0

    # beim Start LEDs löschen
    send_led_all(ser, 0, 0, 0)
    ser.flush()  # Stelle sicher, dass Daten gesendet werden

    try:
        while True:
            line = ser.readline()
            if not line:
                time.sleep(0.01)
                continue

            line = line.decode("utf-8", errors="ignore").strip()
            
            # Debug: zeige alle empfangenen Zeilen
            if line:
                print(f"[DEBUG] Empfangen: {repr(line)}")
            
            if not line.startswith("BTN:"):
                continue

            btn_num = int(line.split(":")[1])
            action = KEYMAP.get(btn_num, None)
            print(f"[EVENT] Taste {btn_num} → {action}")

            if action == "prevent_sleep":
                # hier statt Maus-Jiggle einfach caffeinate starten/stoppen
                # super simpel: wir toggeln nur den Zustand und zeigen LED 0
                prevent_sleep = not prevent_sleep
                if prevent_sleep:
                    print("[SLEEP] Aktiv (bitte in echt: subprocess caffeinate)")
                    send_led(ser, 0, 0, 0, 255)  # blau
                else:
                    print("[SLEEP] Inaktiv")
                    send_led(ser, 0, 0, 0, 0)

            elif action == "tracking_toggle":
                if tracker.current_task:
                    tracker.stop_task()
                    send_led_all(ser, 0, 0, 0)
                else:
                    # ohne Label starten? dann "Allgemein"
                    tracker.start_task("Allgemein")
                    send_led_all(ser, 0, 255, 0)

            elif action in ("Besprechungen", "Support", "Projekt 1", "Projekt 2", "Projekt 3"):
                tracker.start_task(action)
                # zeig auf LED index 1..5
                send_led_all(ser, 0, 0, 0)
                # wähle LED nach Taste (nur Spielerei)
                idx = max(1, min(7, btn_num - 1))
                send_led(ser, idx, 0, 255, 0)

            elif action == "show_or_reset":
                now = time.time()
                # kurzer Druck → anzeigen
                if now - last_btn8_time < 1.5:
                    # zweiter Druck schnell hintereinander = reset
                    tracker.reset_today()
                    send_led_all(ser, 255, 0, 0)
                    time.sleep(0.3)
                    send_led_all(ser, 0, 0, 0)
                else:
                    tracker.show_today()
                last_btn8_time = now

            elif action == "layer_toggle":
                layer = 2 if layer == 1 else 1
                print(f"[LAYER] jetzt {layer}")
                # zeig layer auf LED 7
                if layer == 2:
                    send_led(ser, 7, 255, 255, 0)
                else:
                    send_led(ser, 7, 0, 0, 0)

    except KeyboardInterrupt:
        print("\n[INFO] Beende, stoppe evtl. laufenden Task…")
        tracker.stop_task()
        send_led_all(ser, 0, 0, 0)

if __name__ == "__main__":
    main()
