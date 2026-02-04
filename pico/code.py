import time
import board
import digitalio
import neopixel
import usb_cdc

# -------- BUTTON REMAP --------
# Load key map from .key_map file if it exists
# Format: raw_button:logical_button (one per line)
# This allows each keypad to have its own button mapping
# regardless of how the buttons are wired.
BUTTON_REMAP = {}
try:
    with open("/.key_map", "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split(":")
            if len(parts) == 2:
                raw_btn = int(parts[0])
                logical_btn = int(parts[1])
                BUTTON_REMAP[raw_btn] = logical_btn
except OSError:
    pass  # File doesn't exist, no remap needed
except (ValueError, IndexError):
    pass  # Invalid file format, skip

def remap_button(btn_num):
    return BUTTON_REMAP.get(btn_num, btn_num)

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
# Track when each button was pressed (for long-press detection)
press_times = [0.0] * len(buttons)
# Track if we already sent a LONG event for this press
long_sent = [False] * len(buttons)
LONG_PRESS_DURATION = 5.0  # seconds

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

# Animation state
animating = False
anim_color = (0, 0, 0)
anim_led = 0
anim_start_time = 0

def start_pulse_animation(led_idx, r, g, b):
    global animating, anim_color, anim_led, anim_start_time
    animating = True
    anim_color = (r, g, b)
    anim_led = led_idx
    anim_start_time = time.monotonic()

def stop_animation():
    global animating
    animating = False

def update_animation():
    global animating, anim_color, anim_led, anim_start_time
    if not animating:
        return
    
    # Pulse animation: fade in and out
    elapsed = time.monotonic() - anim_start_time
    # 2 second cycle (1 second fade in, 1 second fade out)
    cycle = elapsed % 2.0
    if cycle < 1.0:
        # Fade in
        brightness = cycle
    else:
        # Fade out
        brightness = 2.0 - cycle
    
    r = int(anim_color[0] * brightness)
    g = int(anim_color[1] * brightness)
    b = int(anim_color[2] * brightness)
    set_pixel(anim_led, r, g, b)

DEVICE_ID = "PICO-KEYPAD-V1"

def parse_host_command(line: str):
    line = line.strip()
    parts = line.split(":")

    # Handle PING command for device identification
    if parts[0] == "PING":
        send_event(f"PONG:{DEVICE_ID}")
        return

    if not parts or parts[0] != "LED":
        return

    if parts[1] == "ALL":
        try:
            r, g, b = map(int, parts[2].split(","))
            pixels.fill((r, g, b))
            stop_animation()  # Stop animation when ALL is used
        except Exception as e:
            pass
    elif parts[1] == "ANIM":
        # LED:ANIM:led_idx:r,g,b - Start pulse animation on specific LED
        try:
            led_idx = int(parts[2])
            r, g, b = map(int, parts[3].split(","))
            start_pulse_animation(led_idx, r, g, b)
        except Exception as e:
            pass
    elif parts[1] == "STOP":
        # LED:STOP - Stop any running animation
        stop_animation()
    else:
        try:
            idx = int(parts[1])
            r, g, b = map(int, parts[2].split(","))
            set_pixel(idx, r, g, b)
            # Stop animation if we're setting the animated LED
            if animating and anim_led == idx:
                stop_animation()
        except Exception as e:
            pass

buf = b""

while True:
    # 1. Query buttons
    now = time.monotonic()
    for i, btn in enumerate(buttons):
        cur = btn.value  # False = not pressed, True = pressed (due to Pull.DOWN + 3V3)
        if cur != last_states[i]:
            # "Click" = edge from False -> True
            if (not last_states[i]) and cur:
                send_event(f"BTN:{remap_button(i+1)}")
                press_times[i] = now
                long_sent[i] = False
            # Button released - reset
            elif last_states[i] and (not cur):
                press_times[i] = 0.0
                long_sent[i] = False
        # Check for long press (button still held)
        elif cur and press_times[i] > 0 and not long_sent[i]:
            if now - press_times[i] >= LONG_PRESS_DURATION:
                send_event(f"BTN:{remap_button(i+1)}:LONG")
                long_sent[i] = True
        last_states[i] = cur

    # 2. Update animations
    update_animation()

    # 3. Read host commands
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
