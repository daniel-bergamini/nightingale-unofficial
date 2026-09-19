"""Constants for the Nightingale integration."""

DOMAIN = "nightingale"

CONF_ROOM_NAME = "room_name"
# Config entry data key: the address to one-time-copy settings from,
# per sync.py. Consumed and removed from entry.data after the first
# successful setup -- see __init__.py.
CONF_COPY_SETTINGS_FROM = "copy_settings_from"

# Manufacturer / model info surfaced on the HA device registry entry.
MANUFACTURER = "Cambridge Sound Management"
MODEL = "Nightingale NG2000"
