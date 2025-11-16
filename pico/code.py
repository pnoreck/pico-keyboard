import time
import board
import digitalio
import neopixel
import usb_cdc

# -------- PIN-KONFIG --------
BUTTON_PINS = [
    board.GP11,  # Taste 1
    board.GP3,   # Taste 2
    board.GP4,   # Taste 3
    board.GP5,   # Taste 4
    board.GP6,   # Taste 5
    board.GP7,   # Taste 6
    board.GP8,   # Taste 7
    board.GP9,   # Taste 8
    board.GP10,  # Taste 9
]

NEOPIXEL_PIN = board.GP22
NUM_PIXELS = 8
BRIGHTNESS = 0.2

console = usb_cdc.console
evt_ser = usb_cdc.data if usb_cdc.data is not None else usb_cdc.console

def dbg(msg):
    try:
        print(msg)
    except Exception:
        pass

dbg("code.py: startet...")

if usb_cdc.data is None:
    dbg("Hinweis: usb_cdc.data NICHT verfügbar, Events laufen über console.")
else:
    dbg("usb_cdc.data ist aktiv, Events laufen über data-Port.")

# -------- BUTTONS --------
buttons = []
for idx, pin in enumerate(BUTTON_PINS, start=1):
    btn = digitalio.DigitalInOut(pin)
    # Taster an 3.3V -> interner PULL_DOWN
    btn.switch_to_input(pull=digitalio.Pull.DOWN)
    buttons.append(btn)
    dbg(f"Taste {idx} auf Pin {pin}")

# Startzustand: alle nicht gedrückt
last_states = [False] * len(buttons)

# -------- NEOPIXEL --------
pixels = neopixel.NeoPixel(
    NEOPIXEL_PIN,
    NUM_PIXELS,
    brightness=BRIGHTNESS,
    auto_write=True,
)
pixels.fill((0, 0, 0))

# kleiner Startup-Effekt
for i in range(NUM_PIXELS):
    pixels[i] = (0, 0, 40)
    time.sleep(0.05)
pixels.fill((0, 0, 0))

dbg("NeoPixel initialisiert, Hauptloop startet.")

def send_event(msg: str):
    if evt_ser is not None:
        try:
            # Versuche immer zu senden, auch wenn connected=False
            # (connected kann bei pyserial-Verbindungen unzuverlässig sein)
            evt_ser.write((msg + "\n").encode("utf-8"))
            evt_ser.flush()  # Stelle sicher, dass Daten sofort gesendet werden
        except Exception as e:
            dbg(f"Fehler beim Senden von '{msg}': {e}")
    else:
        dbg(f"Konnte Event nicht senden (kein evt_ser): {msg}")

def set_pixel(i, r, g, b):
    if 0 <= i < NUM_PIXELS:
        pixels[i] = (r, g, b)

def parse_host_command(line: str):
    line = line.strip()
    dbg(f"Host-Command empfangen: '{line}'")
    parts = line.split(":")
    if not parts or parts[0] != "LED":
        dbg("Unbekanntes Kommando, ignoriere.")
        return

    if parts[1] == "ALL":
        try:
            r, g, b = map(int, parts[2].split(","))
            pixels.fill((r, g, b))
        except Exception as e:
            dbg(f"Fehler beim LED:ALL-Parsing: {e}")
    else:
        try:
            idx = int(parts[1])
            r, g, b = map(int, parts[2].split(","))
            set_pixel(idx, r, g, b)
        except Exception as e:
            dbg(f"Fehler beim LED:i-Parsing: {e}")

buf = b""

while True:
    # 1. Buttons abfragen
    for i, btn in enumerate(buttons):
        cur = btn.value  # False = nicht gedrückt, True = gedrückt (wegen Pull.DOWN + 3V3)
        if cur != last_states[i]:
            dbg(f"Button {i+1} state change: {last_states[i]} -> {cur}")
            # "Klick" = Flanke von False -> True
            if (not last_states[i]) and cur:
                dbg(f"Taste {i+1} gedrückt (Flanke erkannt)")
                send_event(f"BTN:{i+1}")
        last_states[i] = cur

    # 2. Host-Kommandos lesen
    if evt_ser is not None:
        try:
            if evt_ser.in_waiting > 0:
                incoming = evt_ser.read(evt_ser.in_waiting)
                if incoming:
                    buf += incoming
                    while b"\n" in buf:
                        line, buf = buf.split(b"\n", 1)
                        try:
                            parse_host_command(line.decode("utf-8"))
                        except Exception as e:
                            dbg(f"Fehler beim Verarbeiten einer Zeile: {e}")
        except (AttributeError, OSError) as e:
            # Ignoriere Fehler wenn Port nicht verfügbar
            pass

    time.sleep(0.01)
