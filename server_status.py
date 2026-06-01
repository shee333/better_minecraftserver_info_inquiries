from __future__ import annotations

import asyncio
import json
import socket
import struct
import time
from dataclasses import dataclass
from typing import Any

from .formatting import strip_minecraft_colors


class MinecraftStatusError(Exception):
    pass


@dataclass(slots=True)
class MinecraftServerStatus:
    host: str
    port: int
    online: bool
    latency_ms: float | None = None
    version_name: str = "未知"
    protocol: int | None = None
    online_players: int | None = None
    max_players: int | None = None
    motd: str = ""
    sample_players: list[str] | None = None
    error: str = ""


def _pack_varint(value: int) -> bytes:
    data = bytearray()
    value &= 0xFFFFFFFF
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            data.append(byte | 0x80)
        else:
            data.append(byte)
            break
    return bytes(data)


async def _read_exact(reader: asyncio.StreamReader, length: int) -> bytes:
    try:
        return await reader.readexactly(length)
    except asyncio.IncompleteReadError as exc:
        raise MinecraftStatusError("服务器返回的数据不完整") from exc


async def _read_varint(reader: asyncio.StreamReader) -> int:
    value = 0
    for index in range(5):
        byte = (await _read_exact(reader, 1))[0]
        value |= (byte & 0x7F) << (7 * index)
        if not byte & 0x80:
            return value
    raise MinecraftStatusError("服务器返回了无效的 VarInt")


def _pack_string(value: str) -> bytes:
    encoded = value.encode("utf-8")
    return _pack_varint(len(encoded)) + encoded


def _pack_packet(packet_id: int, payload: bytes = b"") -> bytes:
    body = _pack_varint(packet_id) + payload
    return _pack_varint(len(body)) + body


def _parse_legacy_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return strip_minecraft_colors(value)
    if isinstance(value, list):
        return strip_minecraft_colors(
            "".join(_parse_legacy_text(item) for item in value)
        )
    if isinstance(value, dict):
        parts = []
        text = value.get("text")
        if text:
            parts.append(str(text))
        translate = value.get("translate")
        if translate and not parts:
            parts.append(str(translate))
        extra = value.get("extra")
        if isinstance(extra, list):
            parts.extend(_parse_legacy_text(item) for item in extra)
        return strip_minecraft_colors("".join(parts))
    return strip_minecraft_colors(str(value))


async def ping_java_server(
    host: str,
    port: int,
    timeout_seconds: float,
) -> MinecraftServerStatus:
    started = time.perf_counter()
    try:
        address = await asyncio.wait_for(
            asyncio.to_thread(socket.gethostbyname, host),
            timeout=timeout_seconds,
        )
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(address, port),
            timeout=timeout_seconds,
        )
    except Exception as exc:
        return MinecraftServerStatus(
            host=host,
            port=port,
            online=False,
            error=str(exc) or exc.__class__.__name__,
        )

    try:
        handshake_payload = b"".join(
            [
                _pack_varint(-1),
                _pack_string(host),
                struct.pack(">H", port),
                _pack_varint(1),
            ]
        )
        writer.write(_pack_packet(0, handshake_payload))
        writer.write(_pack_packet(0))
        await asyncio.wait_for(writer.drain(), timeout=timeout_seconds)

        await asyncio.wait_for(_read_varint(reader), timeout=timeout_seconds)
        packet_id = await asyncio.wait_for(
            _read_varint(reader), timeout=timeout_seconds
        )
        if packet_id != 0:
            raise MinecraftStatusError("服务器返回了意外的数据包")
        payload_length = await asyncio.wait_for(
            _read_varint(reader), timeout=timeout_seconds
        )
        payload = await asyncio.wait_for(
            _read_exact(reader, payload_length), timeout=timeout_seconds
        )
        raw_status = json.loads(payload.decode("utf-8"))

        ping_payload = struct.pack(">Q", int(time.time() * 1000))
        writer.write(_pack_packet(1, ping_payload))
        await asyncio.wait_for(writer.drain(), timeout=timeout_seconds)
        try:
            await asyncio.wait_for(_read_varint(reader), timeout=timeout_seconds)
            pong_packet_id = await asyncio.wait_for(
                _read_varint(reader), timeout=timeout_seconds
            )
            if pong_packet_id == 1:
                await asyncio.wait_for(_read_exact(reader, 8), timeout=timeout_seconds)
        except Exception:
            pass

        latency_ms = (time.perf_counter() - started) * 1000
        version = raw_status.get("version") or {}
        players = raw_status.get("players") or {}
        sample = players.get("sample") or []
        sample_names = [
            strip_minecraft_colors(player.get("name"))
            for player in sample
            if isinstance(player, dict) and player.get("name")
        ]
        return MinecraftServerStatus(
            host=host,
            port=port,
            online=True,
            latency_ms=latency_ms,
            version_name=str(version.get("name") or "未知"),
            protocol=version.get("protocol"),
            online_players=players.get("online"),
            max_players=players.get("max"),
            motd=_parse_legacy_text(raw_status.get("description")),
            sample_players=sample_names,
        )
    except Exception as exc:
        return MinecraftServerStatus(
            host=host,
            port=port,
            online=False,
            error=str(exc) or exc.__class__.__name__,
        )
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass


def format_server_status(
    status: MinecraftServerStatus,
    server_name: str,
    show_sample_players: bool,
) -> list[str]:
    address = f"{status.host}:{status.port}"
    if not status.online:
        return [
            "\n".join(
                [
                    f"服务器：{server_name}",
                    f"地址：{address}",
                    "状态：离线或无法连接",
                    f"错误：{status.error or '连接超时'}",
                ]
            )
        ]

    players = "未知"
    if status.online_players is not None and status.max_players is not None:
        players = f"{status.online_players}/{status.max_players}"
    latency = "未知"
    if status.latency_ms is not None:
        latency = f"{status.latency_ms:.0f} ms"

    lines = [
        f"服务器：{server_name}",
        f"地址：{address}",
        "状态：在线",
        f"延迟：{latency}",
        f"版本：{status.version_name}",
        f"在线人数：{players}",
    ]
    if status.motd:
        lines.append(f"MOTD：{status.motd}")
    if show_sample_players and status.sample_players:
        lines.append("玩家样本：" + "、".join(status.sample_players[:12]))
    return ["\n".join(lines)]
