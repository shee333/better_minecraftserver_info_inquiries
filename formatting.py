from __future__ import annotations

import re
from datetime import datetime
from typing import Any


def strip_minecraft_colors(text: Any) -> str:
    if text is None:
        return ""
    return re.sub(r"§[0-9A-FK-ORa-fk-or]", "", str(text)).strip()


def format_money(value: Any) -> str:
    try:
        number = float(value or 0)
    except (TypeError, ValueError):
        number = 0.0
    return f"{number:,.2f}"


def format_timestamp_ms(value: Any) -> str:
    try:
        timestamp = int(value or 0)
    except (TypeError, ValueError):
        return "未知"
    if timestamp <= 0:
        return "未知"
    return datetime.fromtimestamp(timestamp / 1000).strftime("%Y-%m-%d %H:%M")


def format_duration_ms(value: Any) -> str:
    try:
        total_seconds = int(value or 0) // 1000
    except (TypeError, ValueError):
        total_seconds = 0
    days, rem = divmod(total_seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, _ = divmod(rem, 60)
    parts = []
    if days:
        parts.append(f"{days}天")
    if hours:
        parts.append(f"{hours}小时")
    if minutes or not parts:
        parts.append(f"{minutes}分钟")
    return "".join(parts)


def ban_status(player: dict[str, Any]) -> str:
    banned_until = player.get("BannedUntil")
    reason = strip_minecraft_colors(player.get("BanReason"))
    if banned_until is None and not reason:
        return "正常"
    try:
        until = int(banned_until)
    except (TypeError, ValueError):
        until = 0
    if until == -1:
        return "永久封禁"
    if until > 0:
        return f"封禁至 {format_timestamp_ms(until)}"
    return "有封禁记录"


def player_display_name(player: dict[str, Any]) -> str:
    username = player.get("username") or "未知玩家"
    display_name = strip_minecraft_colors(player.get("DisplayName"))
    nickname = strip_minecraft_colors(player.get("nickname"))
    if display_name and display_name.lower() != str(username).lower():
        return f"{username}（{display_name}）"
    if nickname and nickname.lower() != str(username).lower():
        return f"{username}（{nickname}）"
    return str(username)


def format_player_summary(player: dict[str, Any]) -> list[str]:
    lines = [f"玩家：{player_display_name(player)}"]
    rank = player.get("Rank")
    if rank:
        lines.append(f"称号/组：{rank}")
    lines.extend(
        [
            f"余额：{format_money(player.get('Balance'))}",
            f"总游玩时长：{format_duration_ms(player.get('TotalPlayTime'))}",
            f"最后上线：{format_timestamp_ms(player.get('LastLoginTime'))}",
            f"最后下线：{format_timestamp_ms(player.get('LastLogoffTime'))}",
            f"Home 数量：{int(player.get('home_count') or 0)}",
            f"状态：{ban_status(player)}",
        ]
    )
    reason = strip_minecraft_colors(player.get("BanReason"))
    if reason and ban_status(player) != "正常":
        lines.append(f"封禁原因：{reason}")
    return lines


def format_ban_entry(player: dict[str, Any], index: int) -> str:
    reason = strip_minecraft_colors(player.get("BanReason")) or "未记录"
    banned_by = player.get("BannedBy") or "未知"
    return "\n".join(
        [
            f"{index}. {player.get('username') or '未知玩家'}",
            f"状态：{ban_status(player)}",
            f"封禁时间：{format_timestamp_ms(player.get('BannedAt'))}",
            f"操作者：{banned_by}",
            f"原因：{reason}",
        ]
    )


def clamp_limit(limit: int, default: int, maximum: int) -> int:
    if limit <= 0:
        limit = default
    return max(1, min(limit, maximum))
