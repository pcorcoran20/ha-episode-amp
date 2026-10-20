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
#     │   file     : select.py                               │
#     │   project  : Episode Response Amp – HA integration   │
#     │   author   : Patrick · Everest Smart Homes LLC       │
#     │   created  : 2026-10-20                              │
#     │   license  : MIT (Muscovy Integrity Treaty)          │
#     │   status   : no ducks were harmed, all were fed      │
#     │                                                      │
#     ╰──────────────────────────────────────────────────────╯
"""Per-zone selects: DSP preset, stereo/mono, source 2 input, output group."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import AmpState, EpisodeAmpClient, EpisodeAmpError
from .const import DSP_PRESETS, OUTPUT_GROUPS, STEREO_MONO
from .coordinator import EpisodeAmpConfigEntry, EpisodeAmpCoordinator
from .entity import EpisodeAmpEntity


@dataclass(frozen=True, kw_only=True)
class EpisodeSelectDescription(SelectEntityDescription):
    options_map: dict[int, str]
    get_value: Callable[[AmpState, int], int | None]
    set_value: Callable[[EpisodeAmpClient, int, int], Awaitable[None]]


DESCRIPTIONS: tuple[EpisodeSelectDescription, ...] = (
    EpisodeSelectDescription(
        key="dsp_preset",
        translation_key="dsp_preset",
        icon="mdi:equalizer",
        entity_category=EntityCategory.CONFIG,
        options_map=DSP_PRESETS,
        get_value=lambda st, o: st.output_dsp_preset.get(o),
        set_value=lambda c, o, v: c.set_dsp_preset(o, v),
    ),
    EpisodeSelectDescription(
        key="stereo_mono",
        translation_key="stereo_mono",
        icon="mdi:speaker-multiple",
        entity_category=EntityCategory.CONFIG,
        options_map=STEREO_MONO,
        get_value=lambda st, o: st.output_stereo_mono.get(o),
        set_value=lambda c, o, v: c.set_stereo_mono(o, v == 1),
    ),
    EpisodeSelectDescription(
        key="output_group",
        translation_key="output_group",
        icon="mdi:group",
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
        options_map=OUTPUT_GROUPS,
        get_value=lambda st, o: st.output_group.get(o),
        set_value=lambda c, o, v: c.set_output_group(o, v),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EpisodeAmpConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    entities: list[SelectEntity] = []
    for output in range(coordinator.client.num_outputs):
        for desc in DESCRIPTIONS:
            entities.append(EpisodeAmpSelect(coordinator, output, desc))
        entities.append(EpisodeAmpSource2Select(coordinator, output))
    async_add_entities(entities)


class EpisodeAmpSelect(EpisodeAmpEntity, SelectEntity):
    entity_description: EpisodeSelectDescription

    def __init__(
        self,
        coordinator: EpisodeAmpCoordinator,
        output: int,
        description: EpisodeSelectDescription,
    ) -> None:
        super().__init__(coordinator, output)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{output}_{description.key}"
        self._attr_translation_placeholders = {"zone": self.zone_name}
        self._attr_options = list(description.options_map.values())

    @property
    def current_option(self) -> str | None:
        val = self.entity_description.get_value(self.coordinator.client.state, self.output)
        return self.entity_description.options_map.get(val) if val is not None else None

    async def async_select_option(self, option: str) -> None:
        for k, v in self.entity_description.options_map.items():
            if v == option:
                try:
                    await self.entity_description.set_value(
                        self.coordinator.client, self.output, k
                    )
                except EpisodeAmpError as err:
                    raise HomeAssistantError(str(err)) from err
                return
        raise HomeAssistantError(f"Invalid option {option}")


class EpisodeAmpSource2Select(EpisodeAmpEntity, SelectEntity):
    """Source 2 input (the amp mixes/ducks it per its Source2 mode setting)."""

    _attr_translation_key = "source2"
    _attr_icon = "mdi:audio-input-rca"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator: EpisodeAmpCoordinator, output: int) -> None:
        super().__init__(coordinator, output)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{output}_source2"
        self._attr_translation_placeholders = {"zone": self.zone_name}

    def _label(self, idx: int) -> str:
        return self.coordinator.client.state.input_names.get(idx) or f"Input {idx + 1}"

    @property
    def options(self) -> list[str]:
        return [self._label(i) for i in range(self.coordinator.client.num_outputs)]

    @property
    def current_option(self) -> str | None:
        idx = self.coordinator.client.state.output_source2.get(self.output)
        return None if idx is None else self._label(idx)

    async def async_select_option(self, option: str) -> None:
        for i in range(self.coordinator.client.num_outputs):
            if self._label(i) == option:
                try:
                    await self.coordinator.client.set_source2(self.output, i)
                except EpisodeAmpError as err:
                    raise HomeAssistantError(str(err)) from err
                return
        raise HomeAssistantError(f"Unknown input {option}")
