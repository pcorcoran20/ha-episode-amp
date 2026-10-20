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
#     │   file     : number.py                               │
#     │   project  : Episode Response Amp – HA integration   │
#     │   author   : Patrick · Everest Smart Homes LLC       │
#     │   created  : 2026-10-20                              │
#     │   license  : MIT (Muscovy Integrity Treaty)          │
#     │   status   : no ducks were harmed, all were fed      │
#     │                                                      │
#     ╰──────────────────────────────────────────────────────╯
"""Per-zone numbers: max volume and turn-on volume (in raw amp units)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from homeassistant.components.number import (
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import AmpState, EpisodeAmpClient, EpisodeAmpError
from .coordinator import EpisodeAmpConfigEntry, EpisodeAmpCoordinator
from .entity import EpisodeAmpEntity


@dataclass(frozen=True, kw_only=True)
class EpisodeNumberDescription(NumberEntityDescription):
    get_value: Callable[[AmpState, int], int | None]
    set_value: Callable[[EpisodeAmpClient, int, int], Awaitable[None]]


DESCRIPTIONS: tuple[EpisodeNumberDescription, ...] = (
    EpisodeNumberDescription(
        key="max_volume",
        translation_key="max_volume",
        icon="mdi:volume-high",
        entity_category=EntityCategory.CONFIG,
        mode=NumberMode.SLIDER,
        native_step=1,
        get_value=lambda st, o: st.output_max_volume.get(o),
        set_value=lambda c, o, v: c.set_max_volume(o, v),
    ),
    EpisodeNumberDescription(
        key="turn_on_volume",
        translation_key="turn_on_volume",
        icon="mdi:volume-medium",
        entity_category=EntityCategory.CONFIG,
        mode=NumberMode.SLIDER,
        native_step=1,
        get_value=lambda st, o: st.output_turn_on_volume.get(o),
        set_value=lambda c, o, v: c.set_turn_on_volume(o, v),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EpisodeAmpConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        EpisodeAmpNumber(coordinator, output, desc)
        for output in range(coordinator.client.num_outputs)
        for desc in DESCRIPTIONS
    )


class EpisodeAmpNumber(EpisodeAmpEntity, NumberEntity):
    entity_description: EpisodeNumberDescription

    def __init__(
        self,
        coordinator: EpisodeAmpCoordinator,
        output: int,
        description: EpisodeNumberDescription,
    ) -> None:
        super().__init__(coordinator, output)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{output}_{description.key}"
        self._attr_translation_placeholders = {"zone": self.zone_name}
        self._attr_native_min_value = 0
        self._attr_native_max_value = coordinator.volume_scale

    @property
    def native_value(self) -> float | None:
        return self.entity_description.get_value(self.coordinator.client.state, self.output)

    async def async_set_native_value(self, value: float) -> None:
        try:
            await self.entity_description.set_value(
                self.coordinator.client, self.output, int(round(value))
            )
        except EpisodeAmpError as err:
            raise HomeAssistantError(str(err)) from err
