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
#     │   file     : media_player.py                         │
#     │   project  : Episode Response Amp – HA integration   │
#     │   author   : Patrick · Everest Smart Homes LLC       │
#     │   created  : 2026-10-20                              │
#     │   license  : MIT (Muscovy Integrity Treaty)          │
#     │   status   : no ducks were harmed, all were fed      │
#     │                                                      │
#     ╰──────────────────────────────────────────────────────╯
"""One media_player per amp output zone: volume, mute, source."""

from __future__ import annotations

from homeassistant.components.media_player import (
    MediaPlayerDeviceClass,
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import EpisodeAmpError
from .coordinator import EpisodeAmpConfigEntry, EpisodeAmpCoordinator
from .entity import EpisodeAmpEntity

VOLUME_STEP_UNITS = 2  # amp units per volume_up/down press


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EpisodeAmpConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        EpisodeAmpZone(coordinator, i) for i in range(coordinator.client.num_outputs)
    )


class EpisodeAmpZone(EpisodeAmpEntity, MediaPlayerEntity):
    """A single stereo (or bridged/mono) output pair."""

    _attr_device_class = MediaPlayerDeviceClass.SPEAKER
    _attr_supported_features = (
        MediaPlayerEntityFeature.VOLUME_SET
        | MediaPlayerEntityFeature.VOLUME_MUTE
        | MediaPlayerEntityFeature.VOLUME_STEP
        | MediaPlayerEntityFeature.SELECT_SOURCE
    )

    def __init__(self, coordinator: EpisodeAmpCoordinator, output: int) -> None:
        super().__init__(coordinator, output)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_zone_{output}"

    # -- naming ----------------------------------------------------------
    @property
    def name(self) -> str:
        # Follow the name set in the amp's web UI so HA matches the install docs.
        return self.zone_name

    # -- state -----------------------------------------------------------
    @property
    def state(self) -> MediaPlayerState:
        return MediaPlayerState.ON

    @property
    def volume_level(self) -> float | None:
        vol = self.coordinator.client.state.output_volume.get(self.output)
        if vol is None:
            return None
        return max(0.0, min(1.0, vol / self.coordinator.volume_scale))

    @property
    def volume_step(self) -> float:
        return VOLUME_STEP_UNITS / self.coordinator.volume_scale

    @property
    def is_volume_muted(self) -> bool | None:
        return self.coordinator.client.state.output_mute.get(self.output)

    @property
    def source_list(self) -> list[str]:
        return [self._input_label(i) for i in range(self.coordinator.client.num_outputs)]

    @property
    def source(self) -> str | None:
        idx = self.coordinator.client.state.output_source1.get(self.output)
        return None if idx is None else self._input_label(idx)

    @property
    def extra_state_attributes(self) -> dict[str, int | str | None]:
        st = self.coordinator.client.state
        return {
            "output_index": self.output,
            "volume_raw": st.output_volume.get(self.output),
            "max_volume_raw": st.output_max_volume.get(self.output),
            "source2_input": st.output_source2.get(self.output),
        }

    def _input_label(self, idx: int) -> str:
        name = self.coordinator.client.state.input_names.get(idx)
        return name or f"Input {idx + 1}"

    def _input_index_from_label(self, label: str) -> int:
        for i in range(self.coordinator.client.num_outputs):
            if self._input_label(i) == label:
                return i
        raise HomeAssistantError(f"Unknown source '{label}'")

    # -- commands --------------------------------------------------------
    async def async_set_volume_level(self, volume: float) -> None:
        raw = round(max(0.0, min(1.0, volume)) * self.coordinator.volume_scale)
        maxvol = self.coordinator.client.state.output_max_volume.get(self.output)
        if maxvol:
            raw = min(raw, maxvol)
        await self._call(self.coordinator.client.set_volume(self.output, raw))

    async def async_volume_up(self) -> None:
        cur = self.coordinator.client.state.output_volume.get(self.output, 0)
        await self.async_set_volume_level(
            (cur + VOLUME_STEP_UNITS) / self.coordinator.volume_scale
        )

    async def async_volume_down(self) -> None:
        cur = self.coordinator.client.state.output_volume.get(self.output, 0)
        await self.async_set_volume_level(
            (cur - VOLUME_STEP_UNITS) / self.coordinator.volume_scale
        )

    async def async_mute_volume(self, mute: bool) -> None:
        await self._call(self.coordinator.client.set_mute(self.output, mute))

    async def async_select_source(self, source: str) -> None:
        idx = self._input_index_from_label(source)
        await self._call(self.coordinator.client.set_source1(self.output, idx))

    async def _call(self, coro) -> None:
        try:
            await coro
        except EpisodeAmpError as err:
            raise HomeAssistantError(f"Episode amp command failed: {err}") from err
