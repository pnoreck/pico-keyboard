import usb_cdc

# Console = REPL / Debug
# Data    = Kanal für dein Mac-Tool (tracker.py)
usb_cdc.enable(console=True, data=True)
