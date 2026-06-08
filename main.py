from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from typing import Any
from uuid import uuid4

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, MessageChain, filter
from astrbot.api.star import Context, Star, register
from astrbot.core import AstrBotConfig
from astrbot.core.utils.astrbot_path import (
    get_astrbot_plugin_data_path,
    get_astrbot_temp_path,
)

from .cmi_repository import CMIRepository
from .formatting import (
    ban_status,
    clamp_limit,
    format_ban_entry,
    format_duration_ms,
    format_money,
    format_player_summary,
    format_timestamp_ms,
)
from .qq_feedback import react_received, send_forward_result
from .server_status import format_server_status, ping_java_server
from .status_image import render_status_image

PLUGIN_NAME = "better_minecraftserver_info_inquiries"

DEFAULT_SERVER_STATUS_TARGETS = [
    {
        "name": "轮换服",
        "host": "turbo1.yunmc.vip",
        "port": 30175,
        "aliases": ["轮换", "轮换服务器", "turbo", "turbo1"],
    },
    {
        "name": "C418",
        "host": "mc39.rhymc.com",
        "port": 24465,
        "aliases": ["c418", "C418服", "主服"],
    },
    {
        "name": "群组服",
        "host": "mc39.rhymc.com",
        "port": 24463,
        "aliases": ["群组", "群组服务器", "群组服", "全服", "velocity", "proxy"],
    },
    {
        "name": "ACT/0/",
        "host": "mc39.rhymc.com",
        "port": 24468,
        "aliases": ["act", "ACT", "ACT/0", "act0", "ACT0"],
    },
]

LEGACY_DEFAULT_STATUS_ENDPOINTS = {
    ("turbo1.yunmc.vip", 30175),
    ("mc39.rhymc.com", 24465),
    ("mc39.rhymc.com", 24463),
}


@register(
    PLUGIN_NAME,
    "shee33",
    "查询 Minecraft CMI 玩家信息、排行榜、封禁状态和服务器在线状态。",
    "0.4.0",
)
class CMIQueryPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.context = context
        self.config = config
        self._pending_delete_targets: dict[str, dict[str, Any]] = {}

    async def initialize(self):
        logger.info("new_plugin CMI query plugin initialized")

    def _cfg(self, key: str, default: Any = None) -> Any:
        return self.config.get(key, default)

    def _db_path(self) -> Path:
        configured = Path(str(self._cfg("cmi_db_path", "") or ""))
        if configured.exists():
            return configured
        if configured.name and not configured.name.endswith(".db"):
            configured_db = configured.with_name(f"{configured.name}.db")
            if configured_db.exists():
                return configured_db
        local_sample = Path(__file__).parent / "cmi.sqlite.db"
        if local_sample.exists():
            return local_sample
        return configured

    def _repo(self) -> CMIRepository:
        return CMIRepository(self._db_path())

    def _default_limit(self) -> int:
        return int(self._cfg("default_rank_limit", 10) or 10)

    def _max_limit(self) -> int:
        return int(self._cfg("max_rank_limit", 20) or 20)

    def _server_store_path(self) -> Path:
        return (
            Path(get_astrbot_plugin_data_path())
            / PLUGIN_NAME
            / "server_status_targets.json"
        )

    def _load_server_store(self) -> dict[str, Any]:
        path = self._server_store_path()
        if not path.exists():
            return {"custom_targets": [], "disabled_endpoints": []}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("读取服务器状态目标存储失败，使用空存储: %s", exc)
            return {"custom_targets": [], "disabled_endpoints": []}
        if not isinstance(data, dict):
            return {"custom_targets": [], "disabled_endpoints": []}
        data.setdefault("custom_targets", [])
        data.setdefault("disabled_endpoints", [])
        return data

    def _save_server_store(self, data: dict[str, Any]) -> None:
        path = self._server_store_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _endpoint_key(self, host: str, port: int) -> str:
        return f"{str(host).strip().lower()}:{int(port)}"

    def _target_endpoint_key(self, target: dict[str, Any]) -> str:
        return self._endpoint_key(str(target["host"]), int(target["port"]))

    def _normalize_server_target(self, target: dict[str, Any]) -> dict[str, Any] | None:
        name = str(target.get("name") or "").strip()
        host = str(target.get("host") or "").strip()
        port = target.get("port")
        address = str(target.get("address") or "").strip()
        if address and not host:
            host, _, port_text = address.rpartition(":")
            if port_text:
                port = port_text
            else:
                host = address
        if not name or not host:
            return None
        try:
            port_int = int(port or 25565)
        except (TypeError, ValueError):
            port_int = 25565
        aliases = target.get("aliases") or []
        if isinstance(aliases, str):
            aliases = [item.strip() for item in aliases.split(",") if item.strip()]
        if not isinstance(aliases, list):
            aliases = []
        return {
            "name": name,
            "host": host,
            "port": port_int,
            "aliases": [str(alias).strip() for alias in aliases if str(alias).strip()],
        }

    def _apply_server_store(
        self, targets: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        store = self._load_server_store()
        disabled = {
            str(endpoint).strip().lower()
            for endpoint in store.get("disabled_endpoints", [])
            if str(endpoint).strip()
        }
        custom_targets = []
        for raw_target in store.get("custom_targets", []):
            if isinstance(raw_target, dict):
                normalized = self._normalize_server_target(raw_target)
                if normalized:
                    custom_targets.append(normalized)
        custom_targets_by_endpoint = {
            self._target_endpoint_key(target): target for target in custom_targets
        }

        merged_targets = []
        seen_endpoints = set()
        for target in targets:
            endpoint = self._target_endpoint_key(target)
            if endpoint in disabled or endpoint in seen_endpoints:
                continue
            target = custom_targets_by_endpoint.pop(endpoint, target)
            if self._target_endpoint_key(target) in disabled:
                continue
            merged_targets.append(target)
            seen_endpoints.add(endpoint)
        for endpoint, target in custom_targets_by_endpoint.items():
            if endpoint in disabled or endpoint in seen_endpoints:
                continue
            merged_targets.append(target)
            seen_endpoints.add(endpoint)
        return merged_targets

    def _server_status_targets(self) -> list[dict[str, Any]]:
        raw_targets = self._cfg("server_status_servers", None)
        parsed_targets: Any = None
        if isinstance(raw_targets, str) and raw_targets.strip():
            try:
                parsed_targets = json.loads(raw_targets)
            except json.JSONDecodeError:
                logger.warning(
                    "server_status_servers 不是合法 JSON，使用默认服务器列表"
                )
        elif isinstance(raw_targets, list):
            parsed_targets = raw_targets

        if not parsed_targets:
            parsed_targets = DEFAULT_SERVER_STATUS_TARGETS

        targets = []
        if isinstance(parsed_targets, dict):
            parsed_targets = [parsed_targets]
        if isinstance(parsed_targets, list):
            for target in parsed_targets:
                if isinstance(target, dict):
                    normalized = self._normalize_server_target(target)
                    if normalized:
                        targets.append(normalized)

        if targets:
            return self._apply_server_store(self._with_default_server_updates(targets))

        single_target = self._normalize_server_target(
            {
                "name": self._cfg("server_status_name", "C418"),
                "host": self._cfg("server_status_host", "127.0.0.1"),
                "port": self._cfg("server_status_port", 25565),
            }
        )
        fallback_targets = (
            [single_target] if single_target else DEFAULT_SERVER_STATUS_TARGETS
        )
        return self._apply_server_store(fallback_targets)

    def _with_default_server_updates(
        self, targets: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        endpoints = {(target["host"], int(target["port"])) for target in targets}
        if not LEGACY_DEFAULT_STATUS_ENDPOINTS.issubset(endpoints):
            return targets
        updated_targets = [*targets]
        for default_target in DEFAULT_SERVER_STATUS_TARGETS:
            endpoint = (default_target["host"], int(default_target["port"]))
            if endpoint not in endpoints:
                updated_targets.append(default_target)
                endpoints.add(endpoint)
        return updated_targets

    def _match_server_status_target(
        self, server_name: str = ""
    ) -> dict[str, Any] | None:
        query = str(server_name or "").strip().lower()
        if not query or query in {"全部", "所有", "all", "服务器", "mc", "minecraft"}:
            return None
        for target in self._server_status_targets():
            names = [target["name"], *target.get("aliases", [])]
            lowered_names = [str(name).lower() for name in names if str(name).strip()]
            if query in lowered_names:
                return target
            if any(name and name in query for name in lowered_names):
                return target
        return None

    def _server_target_labels(self) -> str:
        return "、".join(target["name"] for target in self._server_status_targets())

    def _parse_server_address(
        self, host: str = "", port: int | str = 0, address: str = ""
    ) -> tuple[str, int]:
        raw_host = str(address or host or "").strip()
        raw_host = re.sub(r"^minecraft://", "", raw_host, flags=re.IGNORECASE)
        raw_host = re.sub(r"^mc://", "", raw_host, flags=re.IGNORECASE)
        parsed_port = 0
        try:
            parsed_port = int(port or 0)
        except (TypeError, ValueError):
            parsed_port = 0
        if raw_host.count(":") == 1:
            host_part, port_part = raw_host.rsplit(":", 1)
            if host_part and port_part.isdigit():
                raw_host = host_part.strip()
                parsed_port = int(port_part)
        return raw_host, parsed_port

    def _normalize_aliases(self, aliases: str | list[str] = "") -> list[str]:
        if isinstance(aliases, list):
            return [str(alias).strip() for alias in aliases if str(alias).strip()]
        return [
            alias.strip()
            for alias in re.split(r"[,，、\s]+", str(aliases or ""))
            if alias.strip()
        ]

    def _pending_delete_key(self, event: AstrMessageEvent) -> str:
        return f"{event.get_platform_name()}:{event.get_session_id()}:{event.get_sender_id()}"

    def _add_server_status_target(
        self,
        server_name: str,
        host: str,
        port: int,
        aliases: str | list[str] = "",
    ) -> str:
        target = self._normalize_server_target(
            {
                "name": server_name,
                "host": host,
                "port": port,
                "aliases": self._normalize_aliases(aliases),
            }
        )
        if not target:
            return "服务器信息格式不正确，请重新提供服务器名称、地址和端口。"
        if not 1 <= int(target["port"]) <= 65535:
            return "服务器端口必须在 1 到 65535 之间，请重新提供端口。"

        store = self._load_server_store()
        endpoint = self._target_endpoint_key(target)
        custom_targets = []
        replaced = False
        for raw_target in store.get("custom_targets", []):
            if not isinstance(raw_target, dict):
                continue
            normalized = self._normalize_server_target(raw_target)
            if not normalized:
                continue
            if self._target_endpoint_key(normalized) == endpoint:
                custom_targets.append(target)
                replaced = True
            else:
                custom_targets.append(normalized)
        if not replaced:
            custom_targets.append(target)

        disabled = [
            str(item).strip().lower()
            for item in store.get("disabled_endpoints", [])
            if str(item).strip().lower() != endpoint
        ]
        store["custom_targets"] = custom_targets
        store["disabled_endpoints"] = disabled
        self._save_server_store(store)
        action = "更新" if replaced else "添加"
        return f"已{action}服务器 {target['name']}：{target['host']}:{target['port']}。"

    def _delete_server_status_target(self, target: dict[str, Any]) -> str:
        endpoint = self._target_endpoint_key(target)
        store = self._load_server_store()
        custom_targets = []
        for raw_target in store.get("custom_targets", []):
            if not isinstance(raw_target, dict):
                continue
            normalized = self._normalize_server_target(raw_target)
            if normalized and self._target_endpoint_key(normalized) != endpoint:
                custom_targets.append(normalized)
        disabled = {
            str(item).strip().lower()
            for item in store.get("disabled_endpoints", [])
            if str(item).strip()
        }
        disabled.add(endpoint)
        store["custom_targets"] = custom_targets
        store["disabled_endpoints"] = sorted(disabled)
        self._save_server_store(store)
        return f"已删除服务器 {target['name']}：{target['host']}:{target['port']}。"

    def _server_status_timeout(self) -> float:
        try:
            return float(self._cfg("server_status_timeout_seconds", 3) or 3)
        except (TypeError, ValueError):
            return 3.0

    async def _ack(self, event: AstrMessageEvent) -> None:
        await react_received(
            event,
            str(self._cfg("ack_emoji_id", "124") or "124"),
            bool(self._cfg("ack_emoji_enabled", True)),
        )

    async def _send(
        self, event: AstrMessageEvent, title: str, sections: list[str]
    ) -> None:
        await send_forward_result(
            event,
            title=title,
            sections=sections,
            sender_name=str(self._cfg("forward_sender_name", "C418 查询助手")),
        )

    async def _query_player(self, event: AstrMessageEvent, username: str) -> str:
        player = self._repo().find_player(username)
        if not player:
            await self._send(event, "玩家查询", [f"没有找到玩家：{username}"])
            return f"没有找到玩家：{username}"
        await self._send(event, "玩家查询", ["\n".join(format_player_summary(player))])
        return f"已通过合并转发发送 {player.get('username')} 的玩家信息。"

    async def _query_home_count(self, event: AstrMessageEvent, username: str) -> str:
        player = self._repo().find_player(username)
        if not player:
            await self._send(event, "Home 数量查询", [f"没有找到玩家：{username}"])
            return f"没有找到玩家：{username}"
        count = int(player.get("home_count") or 0)
        section = f"玩家：{player.get('username')}\nHome 数量：{count}\n\n普通成员只能查询 Home 数量，不能查询 Home 名称或坐标。"
        await self._send(event, "Home 数量查询", [section])
        return f"已通过合并转发发送 {player.get('username')} 的 Home 数量。"

    async def _playtime_rank(self, event: AstrMessageEvent, limit: int) -> str:
        limit = clamp_limit(limit, self._default_limit(), self._max_limit())
        players = self._repo().playtime_rank(limit)
        sections = [
            f"{index}. {player.get('username')}\n总游玩时长：{format_duration_ms(player.get('TotalPlayTime'))}\n最后上线：{format_timestamp_ms(player.get('LastLoginTime'))}"
            for index, player in enumerate(players, start=1)
        ]
        await self._send(event, f"游玩时长排行 TOP {limit}", sections)
        return f"已通过合并转发发送游玩时长排行 TOP {limit}。"

    async def _balance_rank(self, event: AstrMessageEvent, limit: int) -> str:
        limit = clamp_limit(limit, self._default_limit(), self._max_limit())
        players = self._repo().balance_rank(limit)
        sections = [
            f"{index}. {player.get('username')}\n余额：{format_money(player.get('Balance'))}\n总游玩时长：{format_duration_ms(player.get('TotalPlayTime'))}"
            for index, player in enumerate(players, start=1)
        ]
        await self._send(event, f"余额排行 TOP {limit}", sections)
        return f"已通过合并转发发送余额排行 TOP {limit}。"

    async def _recent_players(self, event: AstrMessageEvent, limit: int) -> str:
        limit = clamp_limit(limit, self._default_limit(), self._max_limit())
        players = self._repo().recent_players(limit)
        sections = [
            f"{index}. {player.get('username')}\n最后上线：{format_timestamp_ms(player.get('LastLoginTime'))}\n最后下线：{format_timestamp_ms(player.get('LastLogoffTime'))}\n总游玩时长：{format_duration_ms(player.get('TotalPlayTime'))}"
            for index, player in enumerate(players, start=1)
        ]
        await self._send(event, f"最近上线玩家 TOP {limit}", sections)
        return f"已通过合并转发发送最近上线玩家 TOP {limit}。"

    async def _list_banned_players(self, event: AstrMessageEvent) -> str:
        players = self._repo().banned_players()
        if not players:
            await self._send(event, "封禁列表", ["当前没有查询到封禁玩家。"])
            return "当前没有查询到封禁玩家。"
        sections = [
            format_ban_entry(player, index)
            for index, player in enumerate(players, start=1)
        ]
        await self._send(event, f"封禁列表：共 {len(players)} 名玩家", sections)
        return f"已通过合并转发发送 {len(players)} 名封禁玩家。"

    async def _query_ban_status(self, event: AstrMessageEvent, username: str) -> str:
        player = self._repo().find_player(username)
        if not player:
            await self._send(event, "封禁状态查询", [f"没有找到玩家：{username}"])
            return f"没有找到玩家：{username}"
        section = "\n".join(
            [
                f"玩家：{player.get('username')}",
                f"状态：{ban_status(player)}",
                f"封禁时间：{format_timestamp_ms(player.get('BannedAt'))}",
                f"操作者：{player.get('BannedBy') or '未知'}",
                f"原因：{player.get('BanReason') or '未记录'}",
            ]
        )
        await self._send(event, "封禁状态查询", [section])
        return f"已通过合并转发发送 {player.get('username')} 的封禁状态。"

    async def _query_server_status(
        self, event: AstrMessageEvent, server_name: str = ""
    ) -> str:
        matched_target = self._match_server_status_target(server_name)
        targets = [matched_target] if matched_target else self._server_status_targets()
        show_sample_players = bool(self._cfg("server_status_show_sample_players", True))
        timeout_seconds = self._server_status_timeout()
        results = await asyncio.gather(
            *(
                ping_java_server(target["host"], int(target["port"]), timeout_seconds)
                for target in targets
            )
        )
        sections = []
        for target, status in zip(targets, results, strict=False):
            sections.extend(
                format_server_status(status, target["name"], show_sample_players)
            )
        image_sent = False
        if bool(self._cfg("server_status_render_image", True)):
            try:
                output_path = (
                    Path(get_astrbot_temp_path())
                    / f"minecraft_status_{uuid4().hex}.png"
                )
                render_status_image(
                    [
                        (target["name"], status)
                        for target, status in zip(targets, results, strict=False)
                    ],
                    output_path,
                    show_sample_players,
                )
                await event.send(MessageChain().file_image(str(output_path)))
                image_sent = True
            except Exception as exc:
                logger.warning("服务器状态图片渲染或发送失败，回退到合并转发: %s", exc)
        if not image_sent:
            await self._send(event, "Minecraft 服务器状态", sections)
        online_count = sum(1 for status in results if status.online)
        if matched_target:
            status = results[0]
            if status.online:
                return f"服务器 {matched_target['name']} 在线，在线人数 {status.online_players}/{status.max_players}。"
            return f"服务器 {matched_target['name']} 离线或无法连接：{status.error or '连接超时'}"
        return f"已查询 {len(results)} 个服务器，其中 {online_count} 个在线。"

    @filter.command("查询玩家")
    @filter.platform_adapter_type(filter.PlatformAdapterType.AIOCQHTTP)
    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE)
    async def query_player_command(self, event: AstrMessageEvent, username: str = ""):
        await self._ack(event)
        if not username:
            await self._send(event, "玩家查询", ["请提供玩家名，例如：查询玩家 shee33"])
            return
        await self._query_player(event, username)

    @filter.command("游玩排行")
    @filter.platform_adapter_type(filter.PlatformAdapterType.AIOCQHTTP)
    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE)
    async def playtime_rank_command(self, event: AstrMessageEvent, limit: int = 0):
        await self._ack(event)
        await self._playtime_rank(event, limit)

    @filter.command("余额排行")
    @filter.platform_adapter_type(filter.PlatformAdapterType.AIOCQHTTP)
    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE)
    async def balance_rank_command(self, event: AstrMessageEvent, limit: int = 0):
        await self._ack(event)
        await self._balance_rank(event, limit)

    @filter.command("最近上线")
    @filter.platform_adapter_type(filter.PlatformAdapterType.AIOCQHTTP)
    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE)
    async def recent_players_command(self, event: AstrMessageEvent, limit: int = 0):
        await self._ack(event)
        await self._recent_players(event, limit)

    @filter.command("查询home数量")
    @filter.platform_adapter_type(filter.PlatformAdapterType.AIOCQHTTP)
    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE)
    async def home_count_command(self, event: AstrMessageEvent, username: str = ""):
        await self._ack(event)
        if not username:
            await self._send(
                event, "Home 数量查询", ["请提供玩家名，例如：查询home数量 shee33"]
            )
            return
        await self._query_home_count(event, username)

    @filter.command("封禁列表")
    @filter.platform_adapter_type(filter.PlatformAdapterType.AIOCQHTTP)
    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE)
    async def banned_list_command(self, event: AstrMessageEvent):
        await self._ack(event)
        await self._list_banned_players(event)

    @filter.command("封禁状态")
    @filter.platform_adapter_type(filter.PlatformAdapterType.AIOCQHTTP)
    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE)
    async def ban_status_command(self, event: AstrMessageEvent, username: str = ""):
        await self._ack(event)
        if not username:
            await self._send(
                event, "封禁状态查询", ["请提供玩家名，例如：封禁状态 ceester"]
            )
            return
        await self._query_ban_status(event, username)

    @filter.command("服务器状态")
    @filter.platform_adapter_type(filter.PlatformAdapterType.AIOCQHTTP)
    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE)
    async def server_status_command(
        self, event: AstrMessageEvent, server_name: str = ""
    ):
        await self._ack(event)
        await self._query_server_status(event, server_name)

    @filter.command("MC状态")
    @filter.platform_adapter_type(filter.PlatformAdapterType.AIOCQHTTP)
    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE)
    async def mc_status_command(self, event: AstrMessageEvent, server_name: str = ""):
        await self._ack(event)
        await self._query_server_status(event, server_name)

    @filter.llm_tool(name="shee33_mc_query_player")
    async def shee33_mc_query_player(
        self, event: AstrMessageEvent, username: str
    ) -> str:
        """查询一个 Minecraft 玩家的公开基础信息，包括余额、游玩时长、最后上线、最后下线、Home 数量和封禁状态。

        Args:
            username(string): Minecraft 玩家名。
        """
        await self._ack(event)
        return await self._query_player(event, username)

    @filter.llm_tool(name="shee33_mc_query_home_count")
    async def shee33_mc_query_home_count(
        self, event: AstrMessageEvent, username: str
    ) -> str:
        """查询一个 Minecraft 玩家的 Home 数量。普通成员只能查询数量，不能查询 Home 名称或坐标。

        Args:
            username(string): Minecraft 玩家名。
        """
        await self._ack(event)
        return await self._query_home_count(event, username)

    @filter.llm_tool(name="shee33_mc_rank_playtime")
    async def shee33_mc_rank_playtime(
        self, event: AstrMessageEvent, limit: int = 0
    ) -> str:
        """查询 Minecraft 服务器游玩时长排行榜。

        Args:
            limit(number): 返回排行榜数量；小于等于 0 时使用默认数量。
        """
        await self._ack(event)
        return await self._playtime_rank(event, int(limit or 0))

    @filter.llm_tool(name="shee33_mc_rank_balance")
    async def shee33_mc_rank_balance(
        self, event: AstrMessageEvent, limit: int = 0
    ) -> str:
        """查询 Minecraft 服务器余额排行榜。

        Args:
            limit(number): 返回排行榜数量；小于等于 0 时使用默认数量。
        """
        await self._ack(event)
        return await self._balance_rank(event, int(limit or 0))

    @filter.llm_tool(name="shee33_mc_recent_players")
    async def shee33_mc_recent_players(
        self, event: AstrMessageEvent, limit: int = 0
    ) -> str:
        """查询 Minecraft 服务器最近上线玩家列表。

        Args:
            limit(number): 返回玩家数量；小于等于 0 时使用默认数量。
        """
        await self._ack(event)
        return await self._recent_players(event, int(limit or 0))

    @filter.llm_tool(name="shee33_mc_list_banned_players")
    async def shee33_mc_list_banned_players(self, event: AstrMessageEvent) -> str:
        """查询当前所有被封禁的 Minecraft 玩家列表，可展示封禁时间、操作者和原因。"""
        await self._ack(event)
        return await self._list_banned_players(event)

    @filter.llm_tool(name="shee33_mc_query_ban_status")
    async def shee33_mc_query_ban_status(
        self, event: AstrMessageEvent, username: str
    ) -> str:
        """查询一个 Minecraft 玩家的封禁状态，可展示封禁时间、操作者和原因。

        Args:
            username(string): Minecraft 玩家名。
        """
        await self._ack(event)
        return await self._query_ban_status(event, username)

    @filter.llm_tool(name="shee33_mc_server_status")
    async def shee33_mc_server_status(
        self, event: AstrMessageEvent, server_name: str = ""
    ) -> None:
        """查询 Minecraft Java 服务器当前在线状态，包括是否在线、延迟、版本、MOTD 和在线人数。可查询全部服务器，也可指定轮换服、C418、群组服或 ACT/0/。

        Args:
            server_name(string): 服务器名称或别名，可填“轮换服”、“C418”、“群组服”、“ACT/0/”；留空时查询全部服务器。
        """
        await self._ack(event)
        await self._query_server_status(event, server_name)
        return None

    @filter.llm_tool(name="shee33_mc_add_status_server")
    async def shee33_mc_add_status_server(
        self,
        event: AstrMessageEvent,
        server_name: str = "",
        host: str = "",
        port: int = 0,
        address: str = "",
        aliases: str = "",
    ) -> str:
        """把一个 Minecraft Java 服务器加入状态查询列表。必须提供服务器名称、地址和端口；如果用户没有提供名称、地址或端口，请不要猜测，返回缺失字段并继续追问用户。

        Args:
            server_name(string): 服务器显示名称，例如“温馨小服”。
            host(string): 服务器域名或 IP，不包含端口也可以。
            port(number): 服务器端口。缺少端口时必须追问用户。
            address(string): 可选，完整地址，例如“127.0.0.1:25565”。如果 address 已包含端口，可以不填 host/port。
            aliases(string): 可选别名，多个别名用逗号、空格或顿号分隔。
        """
        await self._ack(event)
        parsed_host, parsed_port = self._parse_server_address(host, port, address)
        missing_fields = []
        if not str(server_name or "").strip():
            missing_fields.append("服务器名称")
        if not parsed_host:
            missing_fields.append("服务器地址/IP")
        if parsed_port <= 0:
            missing_fields.append("端口")
        if missing_fields:
            return "缺少" + "、".join(missing_fields) + "，请继续向用户追问这些字段。"

        return self._add_server_status_target(
            server_name=server_name,
            host=parsed_host,
            port=parsed_port,
            aliases=aliases,
        )

    @filter.llm_tool(name="shee33_mc_delete_status_server")
    async def shee33_mc_delete_status_server(
        self,
        event: AstrMessageEvent,
        server_name: str = "",
        confirmed: bool = False,
    ) -> str:
        """删除一个 Minecraft 状态查询服务器。第一次调用必须 confirmed=false，只返回确认问题；用户明确确认后，第二次调用 confirmed=true 才会真正删除。

        Args:
            server_name(string): 要删除的服务器名称或别名。
            confirmed(boolean): 用户是否已经明确二次确认删除。第一次请求删除时必须为 false；只有用户再次确认后才能为 true。
        """
        await self._ack(event)
        if not str(server_name or "").strip():
            return "缺少要删除的服务器名称，请询问用户要删除哪个服务器。"

        target = self._match_server_status_target(server_name)
        if not target:
            return f"没有找到服务器 {server_name}。当前可删除的服务器有：{self._server_target_labels()}。"

        pending_key = self._pending_delete_key(event)
        endpoint = self._target_endpoint_key(target)
        pending_target = self._pending_delete_targets.get(pending_key)
        if not confirmed:
            self._pending_delete_targets[pending_key] = target
            return (
                f"请向用户确认是否删除服务器 {target['name']} "
                f"({target['host']}:{target['port']})。用户明确确认后，"
                "再调用本工具并设置 confirmed=true。"
            )

        if not pending_target or self._target_endpoint_key(pending_target) != endpoint:
            self._pending_delete_targets[pending_key] = target
            return (
                f"尚未确认删除服务器 {target['name']} "
                f"({target['host']}:{target['port']})。请先向用户确认；"
                "用户明确确认后，再调用本工具并设置 confirmed=true。"
            )

        self._pending_delete_targets.pop(pending_key, None)
        return self._delete_server_status_target(target)

    async def terminate(self):
        logger.info("new_plugin CMI query plugin terminated")
