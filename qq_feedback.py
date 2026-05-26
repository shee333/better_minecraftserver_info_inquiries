from __future__ import annotations

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent


async def react_received(event: AstrMessageEvent, emoji_id: str, enabled: bool) -> None:
    if not enabled:
        return
    bot = getattr(event, "bot", None)
    message_id = getattr(event.message_obj, "message_id", None)
    if not bot or not message_id:
        return
    try:
        await bot.set_msg_emoji_like(
            message_id=int(message_id),
            emoji_id=str(emoji_id),
            set=True,
        )
    except Exception as exc:
        logger.debug("设置消息表情回应失败: %s", exc)


async def send_forward_result(
    event: AstrMessageEvent,
    *,
    title: str,
    sections: list[str],
    sender_name: str,
) -> None:
    if not sections:
        sections = ["没有查询到结果。"]
    group_id = event.get_group_id()
    bot = getattr(event, "bot", None)
    if not bot or not group_id:
        await event.send(event.plain_result(f"{title}\n\n" + "\n\n".join(sections)))
        return

    uin = event.get_self_id() or "10000"
    nodes = [
        {
            "type": "node",
            "data": {
                "name": sender_name,
                "uin": uin,
                "content": title,
            },
        }
    ]
    nodes.extend(
        {
            "type": "node",
            "data": {
                "name": sender_name,
                "uin": uin,
                "content": section,
            },
        }
        for section in sections
    )

    for action_name in ("send_group_forward_msg", "send_forward_msg"):
        try:
            action = getattr(bot, action_name)
            await action(group_id=int(group_id), messages=nodes)
            return
        except Exception as exc:
            logger.debug("合并转发 action %s 失败: %s", action_name, exc)

    await event.send(event.plain_result(f"{title}\n\n" + "\n\n".join(sections)))
