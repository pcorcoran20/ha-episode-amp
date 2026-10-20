#     ╭──────────────────────────────────────────────────────╮
#     │                                                      │
#     │          __                                          │
#     │        <(o )___           ✦ EVEREST SMART HOMES ✦    │
#     │         ( ._> /           quack-powered code         │
#     │          `---'            handcrafted by Patrick     │
#     │      __       __       __                            │
#     │    <(o )__  <(o )__  <(o )__    (the interns)        │
#     │     (._>/    (._>/    (._>/                          │
#     │  ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~  │
#     │                                                      │
#     │   file     : const.py                                │
#     │   project  : Episode Response Amp – HA integration   │
#     │   author   : Patrick · Everest Smart Homes LLC       │
#     │   created  : 2026-10-20                              │
#     │   license  : MIT (Muscovy Integrity Treaty)          │
#     │   status   : no ducks were harmed, all were fed      │
#     │                                                      │
#     ╰──────────────────────────────────────────────────────╯
"""Constants for the Episode Response Amp integration."""

from __future__ import annotations

DOMAIN = "episode_amp"

CONF_MODEL = "model"
CONF_VOLUME_SCALE = "volume_scale"
CONF_POLL_INTERVAL = "poll_interval"

DEFAULT_PORT = 8080
DEFAULT_USERNAME = "episode"
DEFAULT_VOLUME_SCALE = 100
DEFAULT_POLL_INTERVAL = 30  # seconds – doubles as a TCP keepalive

# Model -> number of channels. Outputs (zones) = channels / 2 per the spec.
MODELS: dict[str, int] = {
    "2D": 2,
    "8D": 8,
    "12D": 12,
    "16D": 16,
}

DSP_PRESETS: dict[int, str] = {0: "Flat", 1: "Classic", 2: "Pop"}
STEREO_MONO: dict[int, str] = {0: "Stereo", 1: "Mono"}
OUTPUT_GROUPS: dict[int, str] = {0: "Group A", 1: "Group B", 2: "Group C", 3: "Group D"}

MANUFACTURER = "Snap One (Episode)"
