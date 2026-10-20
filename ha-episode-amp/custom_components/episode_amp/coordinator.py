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
#     │   file     : coordinator.py                          │
#     │   project  : Episode Response Amp – HA integration   │
#     │   author   : Patrick · Everest Smart Homes LLC       │
#     │   created  : 2026-10-20                              │
#     │   license  : MIT (Muscovy Integrity Treaty)          │
#     │   status   : no ducks were harmed, all were fed      │
#     │                                                      │
#     ╰──────────────────────────────────────────────────────╯
"""Coordinator: wraps the push-based client and adds a poll/keepalive."""

from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import AmpState, EpisodeAmpClient, EpisodeAmpError
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

type EpisodeAmpConfigEntry = ConfigEntry[EpisodeAmpCoordinator]


class EpisodeAmpCoordinator(DataUpdateCoordinator[AmpState]):
    """Holds the client; entities subscribe here."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: EpisodeAmpClient,
        poll_interval: int,
        volume_scale: int,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{entry.entry_id}",
            config_entry=entry,
            update_interval=timedelta(seconds=poll_interval),
        )
        self.client = client
        self.volume_scale = volume_scale
        self.entry = entry
        self._unsub_push = client.add_listener(self._handle_push)

    @callback
    def _handle_push(self) -> None:
        """Client got an unsolicited update (or a set completed)."""
        self.async_set_updated_data(self.client.state)

    async def _async_update_data(self) -> AmpState:
        if not self.client.connected:
            raise UpdateFailed("Amp is not connected")
        try:
            return await self.client.refresh_dynamic()
        except EpisodeAmpError as err:
            raise UpdateFailed(str(err)) from err

    async def async_shutdown(self) -> None:
        self._unsub_push()
        await self.client.disconnect()
        await super().async_shutdown()
