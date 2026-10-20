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
#     │   file     : entity.py                               │
#     │   project  : Episode Response Amp – HA integration   │
#     │   author   : Patrick · Everest Smart Homes LLC       │
#     │   created  : 2026-10-20                              │
#     │   license  : MIT (Muscovy Integrity Treaty)          │
#     │   status   : no ducks were harmed, all were fed      │
#     │                                                      │
#     ╰──────────────────────────────────────────────────────╯
"""Shared base entity."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER
from .coordinator import EpisodeAmpCoordinator


class EpisodeAmpEntity(CoordinatorEntity[EpisodeAmpCoordinator]):
    """One amp = one device; every zone entity hangs off it."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: EpisodeAmpCoordinator, output: int) -> None:
        super().__init__(coordinator)
        self.output = output
        entry = coordinator.entry
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=coordinator.client.state.amp_name or entry.title,
            manufacturer=MANUFACTURER,
            model=f"Response {entry.data['model']}",
            configuration_url=f"http://{entry.data['host']}",
        )

    @property
    def available(self) -> bool:
        return self.coordinator.client.connected and super().available

    @property
    def zone_name(self) -> str:
        name = self.coordinator.client.state.output_names.get(self.output)
        return name or f"Zone {self.output + 1}"
