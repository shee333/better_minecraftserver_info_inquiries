from __future__ import annotations

from pathlib import Path
from textwrap import shorten

from PIL import Image, ImageDraw, ImageFont

from .server_status import MinecraftServerStatus

WIDTH = 760
PADDING = 28
CARD_PADDING = 18
BACKGROUND = (23, 24, 27)
CARD_BACKGROUND = (34, 36, 41)
CARD_BORDER = (57, 61, 69)
TEXT = (238, 242, 247)
MUTED = (154, 163, 176)
DIM = (112, 122, 138)
GREEN = (77, 255, 99)
YELLOW = (255, 197, 61)
RED = (255, 99, 99)
CYAN = (86, 211, 255)


def _font_candidates() -> list[str]:
    return [
        "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/simhei.ttf",
        "C:/Windows/Fonts/simsun.ttc",
        "C:/Windows/Fonts/consola.ttf",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]


def _load_font(
    size: int, bold: bool = False
) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = _font_candidates()
    if bold:
        candidates = [
            "C:/Windows/Fonts/msyhbd.ttc",
            "C:/Windows/Fonts/simhei.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            *candidates,
        ]
    for font_path in candidates:
        if Path(font_path).exists():
            return ImageFont.truetype(font_path, size=size)
    return ImageFont.load_default()


TITLE_FONT = _load_font(34, bold=True)
NAME_FONT = _load_font(24, bold=True)
BODY_FONT = _load_font(17)
SMALL_FONT = _load_font(15)
MONO_FONT = _load_font(16)


def _text_width(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont) -> int:
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0]


def _wrap_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.ImageFont,
    max_width: int,
    max_lines: int,
) -> list[str]:
    if not text:
        return []
    lines: list[str] = []
    current = ""
    for character in text:
        candidate = current + character
        if _text_width(draw, candidate, font) <= max_width:
            current = candidate
            continue
        if current:
            lines.append(current)
        current = character
        if len(lines) >= max_lines:
            break
    if current and len(lines) < max_lines:
        lines.append(current)
    if len(lines) == max_lines and _text_width(draw, lines[-1], font) > max_width:
        lines[-1] = shorten(
            lines[-1], width=max(8, len(lines[-1]) - 2), placeholder="..."
        )
    return lines[:max_lines]


def _fit_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.ImageFont,
    max_width: int,
) -> str:
    if _text_width(draw, text, font) <= max_width:
        return text
    ellipsis = "..."
    available_width = max(0, max_width - _text_width(draw, ellipsis, font))
    current = ""
    for character in text:
        candidate = current + character
        if _text_width(draw, candidate, font) > available_width:
            break
        current = candidate
    return f"{current}{ellipsis}" if current else ellipsis


def _players_text(status: MinecraftServerStatus) -> str:
    if status.online_players is None or status.max_players is None:
        return "未知"
    return f"{status.online_players}/{status.max_players}"


def _latency_text(status: MinecraftServerStatus) -> str:
    if status.latency_ms is None:
        return "--ms"
    return f"{status.latency_ms:.0f}ms"


def _draw_icon(
    draw: ImageDraw.ImageDraw,
    left: int,
    top: int,
    name: str,
    online: bool,
) -> None:
    colors = [(64, 168, 255), (255, 184, 77), (156, 108, 255), (87, 216, 136)]
    color = colors[sum(ord(character) for character in name) % len(colors)]
    if not online:
        color = (88, 93, 104)
    draw.rounded_rectangle((left, top, left + 58, top + 58), radius=8, fill=color)
    draw.rectangle((left + 8, top + 8, left + 24, top + 24), fill=(255, 255, 255, 70))
    draw.rectangle((left + 30, top + 12, left + 48, top + 28), fill=(0, 0, 0, 45))
    draw.rectangle((left + 12, top + 34, left + 46, top + 48), fill=(0, 0, 0, 55))


def _draw_card(
    draw: ImageDraw.ImageDraw,
    top: int,
    name: str,
    status: MinecraftServerStatus,
    show_sample_players: bool,
) -> int:
    card_left = PADDING
    card_right = WIDTH - PADDING
    card_height = 132
    if status.motd:
        card_height += 24 * min(len(status.motd) // 38 + 1, 2)
    if show_sample_players and status.sample_players:
        card_height += 24

    draw.rounded_rectangle(
        (card_left, top, card_right, top + card_height),
        radius=10,
        fill=CARD_BACKGROUND,
        outline=CARD_BORDER,
        width=1,
    )
    icon_left = card_left + CARD_PADDING
    icon_top = top + CARD_PADDING
    _draw_icon(draw, icon_left, icon_top, name, status.online)

    text_left = icon_left + 74
    status_color = GREEN if status.online else RED
    status_text = "在线" if status.online else "离线"
    draw.text((text_left, top + 15), name, fill=TEXT, font=NAME_FONT)
    draw.text(
        (card_right - 145, top + 18),
        _players_text(status),
        fill=status_color,
        font=NAME_FONT,
    )
    draw.text(
        (card_right - 116, top + 51),
        _latency_text(status),
        fill=status_color,
        font=BODY_FONT,
    )
    draw.text(
        (text_left, top + 48), f"状态：{status_text}", fill=status_color, font=BODY_FONT
    )
    draw.text(
        (text_left + 92, top + 48),
        f"版本：{status.version_name}",
        fill=MUTED,
        font=BODY_FONT,
    )
    draw.text(
        (text_left, top + 74),
        f"地址：{status.host}:{status.port}",
        fill=CYAN,
        font=MONO_FONT,
    )

    line_top = top + 100
    if status.online:
        motd_lines = _wrap_text(
            draw, status.motd, SMALL_FONT, card_right - text_left - 18, 2
        )
        for line in motd_lines:
            draw.text(
                (text_left, line_top), f"MOTD：{line}", fill=MUTED, font=SMALL_FONT
            )
            line_top += 22
        if show_sample_players and status.sample_players:
            sample_text = "、".join(status.sample_players[:12])
            sample_prefix = "玩家样本："
            sample_width = (
                card_right
                - text_left
                - 18
                - _text_width(draw, sample_prefix, SMALL_FONT)
            )
            fitted_sample = _fit_text(draw, sample_text, SMALL_FONT, sample_width)
            draw.text(
                (text_left, line_top),
                f"{sample_prefix}{fitted_sample}",
                fill=YELLOW,
                font=SMALL_FONT,
            )
    else:
        error = status.error or "连接超时"
        draw.text((text_left, line_top), f"错误：{error}", fill=RED, font=SMALL_FONT)

    return top + card_height + 16


def render_status_image(
    items: list[tuple[str, MinecraftServerStatus]],
    output_path: Path,
    show_sample_players: bool,
) -> Path:
    probe = Image.new("RGB", (WIDTH, 1), BACKGROUND)
    probe_draw = ImageDraw.Draw(probe)
    total_height = 92
    for name, status in items:
        card_height = 132
        if status.motd:
            card_height += 24 * min(len(status.motd) // 38 + 1, 2)
        if show_sample_players and status.sample_players:
            card_height += 24
        total_height += card_height + 16
    total_height += 36

    image = Image.new("RGB", (WIDTH, total_height), BACKGROUND)
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, WIDTH, 76), fill=(29, 31, 36))
    title = "Minecraft Server Status"
    title_left = (WIDTH - _text_width(probe_draw, title, TITLE_FONT)) // 2
    draw.text((title_left, 20), title, fill=TEXT, font=TITLE_FONT)

    top = 92
    for name, status in items:
        top = _draw_card(draw, top, name, status, show_sample_players)

    footer = "Rendered locally by AstrBot"
    draw.text((PADDING, total_height - 28), footer, fill=DIM, font=SMALL_FONT)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path, format="PNG")
    return output_path
