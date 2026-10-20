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
#     │   file     : api.py                                  │
#     │   project  : Episode Response Amp – HA integration   │
#     │   author   : Patrick · Everest Smart Homes LLC       │
#     │   created  : 2026-10-20                              │
#     │   license  : MIT (Muscovy Integrity Treaty)          │
#     │   status   : no ducks were harmed, all were fed      │
#     │                                                      │
#     ╰──────────────────────────────────────────────────────╯
"""Async TCP client for the Episode Response Series amplifier JSON API.

Protocol (per Snap One "Response-Amp-API" rev A):
  * Plain TCP, default port 8080, up to 10 concurrent clients.
  * Each message is a UTF-8 JSON object, NULL-terminated (C-style string).
  * Every connection must authenticate first with {"type":"login",...}.
  * Replies echo the request "type" and carry an integer "status".
  * The amp pushes unsolicited "get_*" messages whenever state changes,
    using the exact same layout as the matching GET reply.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

_LOGGER = logging.getLogger(__name__)

DEFAULT_PORT = 8080
COMMAND_TIMEOUT = 5.0
RECONNECT_MIN = 5
RECONNECT_MAX = 60

# Status codes from the spec
STATUS_OK = 200
STATUS_REPEAT = 300  # "repeat operation" – value already set, treat as OK
STATUS_BAD_CREDENTIALS = 400
STATUS_ILLEGAL = 401
STATUS_LOGIN_FIRST = 402
STATUS_DEFAULT_PASSWORD = 403
STATUS_SIGNED_OUT = 405
STATUS_LOCKED_OUT = 406
STATUS_BAD_RANGE = 410
STATUS_STANDBY = 700

OK_STATUSES = {STATUS_OK, STATUS_REPEAT}


class EpisodeAmpError(Exception):
    """Base error."""


class EpisodeAmpConnectionError(EpisodeAmpError):
    """Could not reach the amp."""


class EpisodeAmpAuthError(EpisodeAmpError):
    """Bad username/password."""


class EpisodeAmpDefaultPasswordError(EpisodeAmpAuthError):
    """Amp still has the factory password – API refuses until it is changed."""


class EpisodeAmpLockedOutError(EpisodeAmpAuthError):
    """Too many bad logins."""


class EpisodeAmpCommandError(EpisodeAmpError):
    """Amp returned a non-success status."""

    def __init__(self, msg_type: str, status: int) -> None:
        super().__init__(f"{msg_type} failed with status {status}")
        self.msg_type = msg_type
        self.status = status


def _as_int(value: Any, default: int = 0) -> int:
    """Amp sends most numbers as strings ("0", "35") – coerce safely."""
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


@dataclass
class AmpState:
    """Snapshot of everything we track on the amp."""

    amp_name: str = ""
    input_names: dict[int, str] = field(default_factory=dict)
    output_names: dict[int, str] = field(default_factory=dict)
    output_volume: dict[int, int] = field(default_factory=dict)
    output_mute: dict[int, bool] = field(default_factory=dict)
    output_source1: dict[int, int] = field(default_factory=dict)
    output_source2: dict[int, int] = field(default_factory=dict)
    output_dsp_preset: dict[int, int] = field(default_factory=dict)
    output_stereo_mono: dict[int, int] = field(default_factory=dict)  # 0 stereo, 1 mono
    output_max_volume: dict[int, int] = field(default_factory=dict)
    output_turn_on_volume: dict[int, int] = field(default_factory=dict)
    output_group: dict[int, int] = field(default_factory=dict)


class EpisodeAmpClient:
    """Persistent, auto-reconnecting client for one amplifier."""

    def __init__(
        self,
        host: str,
        port: int,
        username: str,
        password: str,
        num_outputs: int,
    ) -> None:
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.num_outputs = num_outputs

        self.state = AmpState()
        self.connected = False

        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._reader_task: asyncio.Task | None = None
        self._reconnect_task: asyncio.Task | None = None
        self._closing = False
        self._send_lock = asyncio.Lock()
        self._pending: dict[str, list[asyncio.Future]] = {}
        self._listeners: list[Callable[[], None]] = []
        self._auth_error: Exception | None = None

    # ------------------------------------------------------------------ #
    # Listener plumbing
    # ------------------------------------------------------------------ #
    def add_listener(self, cb: Callable[[], None]) -> Callable[[], None]:
        self._listeners.append(cb)

        def _remove() -> None:
            if cb in self._listeners:
                self._listeners.remove(cb)

        return _remove

    def _notify(self) -> None:
        for cb in list(self._listeners):
            try:
                cb()
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Listener raised")

    # ------------------------------------------------------------------ #
    # Connection lifecycle
    # ------------------------------------------------------------------ #
    async def connect(self) -> None:
        """Open TCP, authenticate, start reader. Raises on failure."""
        self._closing = False
        try:
            self._reader, self._writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port), COMMAND_TIMEOUT
            )
        except (OSError, asyncio.TimeoutError) as err:
            raise EpisodeAmpConnectionError(
                f"Cannot connect to {self.host}:{self.port}: {err}"
            ) from err

        self._reader_task = asyncio.create_task(self._read_loop())
        try:
            await self._login()
        except Exception:
            await self._teardown()
            raise

        self.connected = True
        _LOGGER.debug("Connected and authenticated to %s", self.host)

    async def disconnect(self) -> None:
        self._closing = True
        if self._reconnect_task:
            self._reconnect_task.cancel()
            self._reconnect_task = None
        await self._teardown()
        self.connected = False
        self._notify()

    async def _teardown(self) -> None:
        if self._reader_task:
            self._reader_task.cancel()
            try:
                await self._reader_task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
            self._reader_task = None
        if self._writer:
            try:
                self._writer.close()
                await asyncio.wait_for(self._writer.wait_closed(), 2)
            except Exception:  # noqa: BLE001
                pass
        self._reader = None
        self._writer = None
        # Fail anything still waiting
        for futs in self._pending.values():
            for fut in futs:
                if not fut.done():
                    fut.set_exception(EpisodeAmpConnectionError("Connection closed"))
        self._pending.clear()

    def _on_connection_lost(self) -> None:
        if self._closing:
            return
        was_connected = self.connected
        self.connected = False
        if was_connected:
            _LOGGER.warning("Lost connection to Episode amp at %s", self.host)
            self._notify()
        if not self._reconnect_task or self._reconnect_task.done():
            self._reconnect_task = asyncio.create_task(self._reconnect_loop())

    async def _reconnect_loop(self) -> None:
        delay = RECONNECT_MIN
        while not self._closing:
            await asyncio.sleep(delay)
            try:
                await self._teardown()
                await self.connect()
                await self.refresh_all()
                _LOGGER.info("Reconnected to Episode amp at %s", self.host)
                self._notify()
                return
            except EpisodeAmpAuthError as err:
                # Don't hammer a locked/bad account – back off to max.
                _LOGGER.error("Auth failed while reconnecting: %s", err)
                delay = RECONNECT_MAX
            except EpisodeAmpError as err:
                _LOGGER.debug("Reconnect attempt failed: %s", err)
                delay = min(delay * 2, RECONNECT_MAX)

    async def _login(self) -> None:
        resp = await self._request(
            {"type": "login", "username": self.username, "password": self.password},
            expect="login",
        )
        status = _as_int(resp.get("status"), -1)
        if status in OK_STATUSES:
            return
        if status == STATUS_DEFAULT_PASSWORD:
            raise EpisodeAmpDefaultPasswordError(
                "Amp is using the factory default password; change it in the amp web UI first"
            )
        if status == STATUS_LOCKED_OUT:
            raise EpisodeAmpLockedOutError("Account locked out after too many bad passwords")
        if status == STATUS_BAD_CREDENTIALS:
            raise EpisodeAmpAuthError("Invalid username or password")
        raise EpisodeAmpAuthError(f"Login rejected with status {status}")

    # ------------------------------------------------------------------ #
    # Wire I/O
    # ------------------------------------------------------------------ #
    async def _read_loop(self) -> None:
        assert self._reader is not None
        decoder = json.JSONDecoder()
        buf = b""
        try:
            while True:
                chunk = await self._reader.read(4096)
                if not chunk:
                    raise EpisodeAmpConnectionError("EOF from amp")
                buf += chunk
                # Messages are NULL-terminated, but be tolerant: pull out every
                # complete JSON object we can find regardless of terminator.
                while True:
                    buf = buf.lstrip(b"\x00 \r\n\t")
                    if not buf:
                        break
                    try:
                        text = buf.decode("utf-8")
                    except UnicodeDecodeError:
                        break  # partial multibyte char – wait for more
                    try:
                        obj, end = decoder.raw_decode(text)
                    except json.JSONDecodeError:
                        break  # incomplete object – wait for more
                    buf = text[end:].encode("utf-8")
                    if isinstance(obj, dict):
                        self._handle_message(obj)
        except asyncio.CancelledError:
            raise
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("Reader loop ended: %s", err)
            self._on_connection_lost()

    async def _request(
        self, payload: dict[str, Any], expect: str, timeout: float = COMMAND_TIMEOUT
    ) -> dict[str, Any]:
        """Send one JSON message and wait for the reply with matching type."""
        if self._writer is None:
            raise EpisodeAmpConnectionError("Not connected")

        loop = asyncio.get_running_loop()
        fut: asyncio.Future = loop.create_future()
        self._pending.setdefault(expect, []).append(fut)

        raw = json.dumps(payload, separators=(",", ":")).encode("utf-8") + b"\x00"
        try:
            async with self._send_lock:
                self._writer.write(raw)
                await self._writer.drain()
            return await asyncio.wait_for(fut, timeout)
        except asyncio.TimeoutError as err:
            raise EpisodeAmpConnectionError(f"Timeout waiting for {expect}") from err
        except (OSError, ConnectionError) as err:
            raise EpisodeAmpConnectionError(str(err)) from err
        finally:
            futs = self._pending.get(expect)
            if futs and fut in futs:
                futs.remove(fut)

    def _handle_message(self, msg: dict[str, Any]) -> None:
        msg_type = str(msg.get("type", ""))
        _LOGGER.debug("RX %s", msg)

        # Update state for any get_* message – solicited or unsolicited.
        if msg_type.startswith("get_"):
            if self._apply_get(msg_type, msg):
                self._notify()

        # Resolve the oldest waiter for this type, if any.
        futs = self._pending.get(msg_type)
        if futs:
            for fut in futs:
                if not fut.done():
                    fut.set_result(msg)
                    break

    # ------------------------------------------------------------------ #
    # State parsing
    # ------------------------------------------------------------------ #
    @staticmethod
    def _rows(msg: dict[str, Any]) -> list[dict[str, Any]]:
        # Spec is inconsistent: get_outputname returns "result", others "value".
        rows = msg.get("value")
        if rows is None:
            rows = msg.get("result")
        return rows if isinstance(rows, list) else []

    def _apply_get(self, msg_type: str, msg: dict[str, Any]) -> bool:
        st = self.state
        changed = False

        if msg_type == "get_ampname":
            name = str(msg.get("value", "")) or st.amp_name
            changed = name != st.amp_name
            st.amp_name = name
            return changed

        int_maps: dict[str, dict[int, int]] = {
            "get_outputvol": st.output_volume,
            "get_outputsource1": st.output_source1,
            "get_outputsource2": st.output_source2,
            "get_dsppreset": st.output_dsp_preset,
            "get_stereomono": st.output_stereo_mono,
            "get_maxvol": st.output_max_volume,
            "get_turnonvol": st.output_turn_on_volume,
            "get_outputgroup": st.output_group,
        }
        if msg_type in int_maps:
            target = int_maps[msg_type]
            for row in self._rows(msg):
                idx = _as_int(row.get("index"), -1)
                if idx < 0:
                    continue
                val = _as_int(row.get("value"))
                if target.get(idx) != val:
                    target[idx] = val
                    changed = True
            return changed

        if msg_type == "get_muteoutput":
            for row in self._rows(msg):
                idx = _as_int(row.get("index"), -1)
                if idx < 0:
                    continue
                val = _as_int(row.get("value")) == 1
                if st.output_mute.get(idx) != val:
                    st.output_mute[idx] = val
                    changed = True
            return changed

        if msg_type in ("get_inputname", "get_outputname"):
            target = st.input_names if msg_type == "get_inputname" else st.output_names
            for row in self._rows(msg):
                idx = _as_int(row.get("index"), -1)
                if idx < 0:
                    continue
                # input rows use "name", output rows use "value"
                name = row.get("name", row.get("value"))
                name = str(name) if name is not None else ""
                if target.get(idx) != name:
                    target[idx] = name
                    changed = True
            return changed

        return False

    # ------------------------------------------------------------------ #
    # Public GET helpers
    # ------------------------------------------------------------------ #
    @property
    def _all_outputs(self) -> list[int]:
        return list(range(self.num_outputs))

    async def _get(self, msg_type: str, indexed: bool = True) -> None:
        payload: dict[str, Any] = {"type": msg_type}
        if indexed:
            payload["value"] = self._all_outputs
        resp = await self._request(payload, expect=msg_type)
        status = _as_int(resp.get("status"), STATUS_OK)  # some GETs omit status
        if status not in OK_STATUSES and status != STATUS_STANDBY:
            raise EpisodeAmpCommandError(msg_type, status)

    async def refresh_all(self) -> AmpState:
        """Pull every tracked attribute. Used on startup and as a poll/keepalive."""
        await self._get("get_ampname", indexed=False)
        for t in (
            "get_inputname",
            "get_outputname",
            "get_outputvol",
            "get_muteoutput",
            "get_outputsource1",
            "get_outputsource2",
            "get_dsppreset",
            "get_stereomono",
            "get_maxvol",
            "get_turnonvol",
            "get_outputgroup",
        ):
            try:
                await self._get(t)
            except EpisodeAmpCommandError as err:
                # Not every firmware/model supports every call – log and move on.
                _LOGGER.debug("Skipping %s: %s", t, err)
        return self.state

    async def refresh_dynamic(self) -> AmpState:
        """Cheap poll of the things that actually change during normal use."""
        for t in ("get_outputvol", "get_muteoutput", "get_outputsource1"):
            await self._get(t)
        return self.state

    # ------------------------------------------------------------------ #
    # Public SET helpers
    # ------------------------------------------------------------------ #
    async def _set_indexed(self, msg_type: str, index: int, value: Any) -> None:
        resp = await self._request(
            {"type": msg_type, "value": [{"index": index, "value": str(value)}]},
            expect=msg_type,
        )
        status = _as_int(resp.get("status"), -1)
        if status not in OK_STATUSES:
            raise EpisodeAmpCommandError(msg_type, status)

    async def set_volume(self, output: int, volume: int) -> None:
        await self._set_indexed("set_outputvol", output, volume)
        self.state.output_volume[output] = volume
        self._notify()

    async def set_mute(self, output: int, mute: bool) -> None:
        await self._set_indexed("set_muteoutput", output, 1 if mute else 0)
        self.state.output_mute[output] = mute
        self._notify()

    async def set_source1(self, output: int, input_index: int) -> None:
        await self._set_indexed("set_outputsource1", output, input_index)
        self.state.output_source1[output] = input_index
        self._notify()

    async def set_source2(self, output: int, input_index: int) -> None:
        await self._set_indexed("set_outputsource2", output, input_index)
        self.state.output_source2[output] = input_index
        self._notify()

    async def set_dsp_preset(self, output: int, preset: int) -> None:
        await self._set_indexed("set_dsppreset", output, preset)
        self.state.output_dsp_preset[output] = preset
        self._notify()

    async def set_stereo_mono(self, output: int, mono: bool) -> None:
        await self._set_indexed("set_stereomono", output, 1 if mono else 0)
        self.state.output_stereo_mono[output] = 1 if mono else 0
        self._notify()

    async def set_max_volume(self, output: int, volume: int) -> None:
        await self._set_indexed("set_maxvol", output, volume)
        self.state.output_max_volume[output] = volume
        self._notify()

    async def set_turn_on_volume(self, output: int, volume: int) -> None:
        await self._set_indexed("set_turnonvol", output, volume)
        self.state.output_turn_on_volume[output] = volume
        self._notify()

    async def set_output_group(self, output: int, group: int) -> None:
        await self._set_indexed("set_outputgroup", output, group)
        self.state.output_group[output] = group
        self._notify()

    async def set_output_name(self, output: int, name: str) -> None:
        await self._set_indexed("set_outputname", output, name)
        self.state.output_names[output] = name
        self._notify()
