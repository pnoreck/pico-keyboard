import time
import board
import digitalio
import neopixel
import usb_cdc

# -------- PIN CONFIG --------
BUTTON_PINS = [
    board.GP11,  # Button 1
    board.GP3,   # Button 2
    board.GP4,   # Button 3
    board.GP5,   # Button 4
    board.GP6,   # Button 5
    board.GP7,   # Button 6
    board.GP8,   # Button 7
    board.GP9,   # Button 8
    board.GP10,  # Button 9
]

NEOPIXEL_PIN = board.GP22
NUM_PIXELS = 8
BRIGHTNESS = 0.2

console = usb_cdc.console
evt_ser = usb_cdc.data if usb_cdc.data is not None else usb_cdc.console

# -------- BUTTONS --------
buttons = []
for idx, pin in enumerate(BUTTON_PINS, start=1):
    btn = digitalio.DigitalInOut(pin)
    # Button at 3.3V -> internal PULL_DOWN
    btn.switch_to_input(pull=digitalio.Pull.DOWN)
    buttons.append(btn)

# Initial state: all not pressed
last_states = [False] * len(buttons)

# -------- NEOPIXEL --------
pixels = neopixel.NeoPixel(
    NEOPIXEL_PIN,
    NUM_PIXELS,
    brightness=BRIGHTNESS,
    auto_write=True,
)
pixels.fill((0, 0, 0))

# small startup effect
for i in range(NUM_PIXELS):
    pixels[i] = (0, 0, 40)
    time.sleep(0.05)
pixels.fill((0, 0, 0))

def send_event(msg: str):
    if evt_ser is not None:
        try:
            # Always try to send, even if connected=False
            # (connected can be unreliable with pyserial connections)
            evt_ser.write((msg + "\n").encode("utf-8"))
            evt_ser.flush()  # Ensure data is sent immediately
        except Exception as e:
            pass
    else:
        pass

def set_pixel(i, r, g, b):
    if 0 <= i < NUM_PIXELS:
        pixels[i] = (r, g, b)

def parse_host_command(line: str):
    line = line.strip()
    parts = line.split(":")
    if not parts or parts[0] != "LED":
        return

    if parts[1] == "ALL":
        try:
            r, g, b = map(int, parts[2].split(","))
            pixels.fill((r, g, b))
        except Exception as e:
            pass
    else:
        try:
            idx = int(parts[1])
            r, g, b = map(int, parts[2].split(","))
            set_pixel(idx, r, g, b)
        except Exception as e:
            pass

buf = b""

while True:
    # 1. Query buttons
    for i, btn in enumerate(buttons):
        cur = btn.value  # False = not pressed, True = pressed (due to Pull.DOWN + 3V3)
        if cur != last_states[i]:
            # "Click" = edge from False -> True
            if (not last_states[i]) and cur:
                send_event(f"BTN:{i+1}")
        last_states[i] = cur

    # 2. Read host commands
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
                            pass
        except (AttributeError, OSError) as e:
            pass

    time.sleep(0.01)
