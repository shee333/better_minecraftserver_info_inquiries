from __future__ import annotations

from pathlib import Path
from typing import Any

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register
from astrbot.core import AstrBotConfig

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

PLUGIN_NAME = "better_minecraftserver_info_inquiries"


@register(
    PLUGIN_NAME,
    "shee33",
    "查询 Minecraft CMI 玩家信息、排行榜和封禁状态。",
    "0.1.0",
)
class CMIQueryPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.context = context
        self.config = config

    async def initialize(self):
        logger.info("new_plugin CMI query plugin initialized")

    def _cfg(self, key: str, default: Any = None) -> Any:
        return self.config.get(key, default)

    def _db_path(self) -> Path:
        configured = Path(str(self._cfg("cmi_db_path", "") or ""))
        if configured.exists():
            return configured
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

    async def terminate(self):
        logger.info("new_plugin CMI query plugin terminated")
