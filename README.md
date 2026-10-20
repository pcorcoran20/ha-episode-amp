# Episode Response Amp — Home Assistant integration

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://hacs.xyz/docs/faq/custom_repositories)
[![Validate](https://github.com/pcorcoran20/ha-episode-amp/actions/workflows/validate.yml/badge.svg)](https://github.com/pcorcoran20/ha-episode-amp/actions/workflows/validate.yml)
[![Release](https://img.shields.io/github/v/release/pcorcoran20/ha-episode-amp)](https://github.com/pcorcoran20/ha-episode-amp/releases)

Local, push-based control of Snap One **Episode Response Series** amplifiers
(EA-AMP-RSP 2D / 8D / 12D / 16D) over the amp's TCP JSON API. No cloud, no OvrC.

## What you get

| Entity | Per zone | What it does |
|---|---|---|
| `media_player` | ✅ | Volume, mute, vol up/down, Source 1 select (uses the input names from the amp's web UI) |
| `select` DSP preset | ✅ | Flat / Classic / Pop |
| `select` Stereo/Mono | ✅ | Stereo / Mono output |
| `select` Source 2 | ✅ (disabled by default) | Second input for that output |
| `select` Output group | ✅ (disabled by default) | Group A–D |
| `number` Max volume | ✅ | Per-zone volume ceiling |
| `number` Turn-on volume | ✅ | Per-zone power-on volume |

State updates arrive instantly via the amp's unsolicited push messages; a light
poll (default 30 s) keeps the TCP session alive and backfills anything missed.
Auto-reconnects with backoff if the amp reboots or the link drops.

## Before you install

1. Log into the amp's web UI (`http://<amp-ip>`, default `episode` / `episode`).
2. **Change the password.** The API returns status `403` and refuses everything
   until the factory password is gone.
3. Note the API port (default `8080`, configurable in the web UI).
4. Name your inputs and outputs in the web UI — HA will use those names.

## Install

**HACS (custom repo):** HACS → Integrations → ⋮ → Custom repositories → add
`https://github.com/pcorcoran20/ha-episode-amp` as *Integration* → install → restart HA.

**Manual:** copy `custom_components/episode_amp` into your HA `config/custom_components/`
and restart.

Then: Settings → Devices & services → Add integration → **Episode Response Amp**.

## Options

Settings → Devices & services → Episode Response Amp → Configure:

* **Volume scale** — highest raw value the amp accepts for `set_outputvol`.
  Defaults to `100`. If your amp's web UI shows a different max, set it here.
* **Poll interval** — seconds between keepalive polls.

## Notes / gotchas

* The amp allows 10 simultaneous TCP clients, so this coexists fine with a
  Control4 driver or the web UI.
* Index rule from the spec: outputs and inputs are numbered `0 … (channels/2 − 1)`.
* Sections of the API marked *Local Configuration Tool Only* (reboot, factory
  reset, crossovers, limiter, delay, bridge mode) are intentionally **not**
  exposed — they're install-time settings, not daily-driver controls.
* Status `300` ("repeat operation") is treated as success.

## Debug logging

```yaml
logger:
  logs:
    custom_components.episode_amp: debug
```

## Releasing

Bump `version` in `custom_components/episode_amp/manifest.json` (and add a
`CHANGELOG.md` entry), then push to `main`. The Release workflow sees the new
version, creates the matching `v*` tag and publishes a GitHub release, which is
what HACS offers as an update.
