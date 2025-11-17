import usb_cdc

# Console = REPL / Debug
# Data    = Channel for your Mac tool (tracker.py)
usb_cdc.enable(console=True, data=True)
