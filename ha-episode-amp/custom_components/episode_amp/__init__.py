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
#     │   file     : __init__.py                             │
#     │   project  : Episode Response Amp – HA integration   │
#     │   author   : Patrick · Everest Smart Homes LLC       │
#     │   created  : 2026-10-20                              │
#     │   license  : MIT (Muscovy Integrity Treaty)          │
#     │   status   : no ducks were harmed, all were fed      │
#     │                                                      │
#     ╰──────────────────────────────────────────────────────╯
"""Episode Response Series amplifier integration for Home Assistant."""

from __future__ import annotations

import logging

from homeassistant.const import (
    CONF_HOST,
    CONF_PASSWORD,
    CONF_PORT,
    CONF_USERNAME,
    Platform,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady

from .api import (
    EpisodeAmpAuthError,
    EpisodeAmpClient,
    EpisodeAmpConnectionError,
    EpisodeAmpError,
)
from .const import (
    CONF_MODEL,
    CONF_POLL_INTERVAL,
    CONF_VOLUME_SCALE,
    DEFAULT_POLL_INTERVAL,
    DEFAULT_VOLUME_SCALE,
    MODELS,
)
from .coordinator import EpisodeAmpConfigEntry, EpisodeAmpCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.MEDIA_PLAYER, Platform.SELECT, Platform.NUMBER]


async def async_setup_entry(hass: HomeAssistant, entry: EpisodeAmpConfigEntry) -> bool:
    """Connect, authenticate, pull initial state, spin up platforms."""
    channels = MODELS[entry.data[CONF_MODEL]]
    client = EpisodeAmpClient(
        host=entry.data[CONF_HOST],
        port=entry.data[CONF_PORT],
        username=entry.data[CONF_USERNAME],
        password=entry.data[CONF_PASSWORD],
        num_outputs=channels // 2,
    )

    try:
        await client.connect()
        await client.refresh_all()
    except EpisodeAmpAuthError as err:
        raise ConfigEntryAuthFailed(str(err)) from err
    except (EpisodeAmpConnectionError, EpisodeAmpError) as err:
        await client.disconnect()
        raise ConfigEntryNotReady(str(err)) from err

    coordinator = EpisodeAmpCoordinator(
        hass,
        entry,
        client,
        poll_interval=entry.options.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL),
        volume_scale=entry.options.get(CONF_VOLUME_SCALE, DEFAULT_VOLUME_SCALE),
    )
    coordinator.async_set_updated_data(client.state)
    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def _async_update_listener(hass: HomeAssistant, entry: EpisodeAmpConfigEntry) -> None:
    """Options changed – reload so new scale/poll interval take effect."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: EpisodeAmpConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        await entry.runtime_data.async_shutdown()
    return unload_ok
