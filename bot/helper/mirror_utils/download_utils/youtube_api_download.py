#!/usr/bin/env python3
"""Vercel YouTube direct-link API integration."""

from asyncio import Event, wait_for
from html import escape
from secrets import token_hex
from urllib.parse import urlparse
import aiohttp
from pyrogram.handlers import CallbackQueryHandler
from pyrogram.filters import regex
from bot import bot, LOGGER
from bot.helper.ext_utils.bot_utils import new_task
from bot.helper.telegram_helper.button_build import ButtonMaker
from bot.helper.telegram_helper.message_utils import (
    deleteMessage,
    editMessage,
    sendMessage,
)

YOUTUBE_API_URL = "https://ytdown-beta-ashen.vercel.app/api/youtube"
_SELECTION_TIMEOUT = 300
_pending_selections = {}


def is_youtube_url(value):
    """Return True only for YouTube watch/short/embed URLs."""
    if not isinstance(value, str) or not value.startswith(("http://", "https://")):
        return False
    try:
        hostname = (urlparse(value).hostname or "").lower().removeprefix("www.")
    except ValueError:
        return False
    return hostname in {
        "youtube.com",
        "youtu.be",
        "youtube-nocookie.com",
        "m.youtube.com",
    } or hostname.endswith(".youtube.com")


def _safe_filename(value):
    value = (value or "youtube_video").strip()
    for char in '/\\:*?"<>|':
        value = value.replace(char, "_")
    return value[:180].strip(" .") or "youtube_video"


def _extension_for_format(item):
    fmt = str(item.get("format", "")).lower()
    label = str(item.get("label", "")).lower()
    if fmt in {"mp3", "m4a", "aac", "flac", "opus", "ogg", "wav"}:
        return "ogg" if fmt == "ogg" else fmt
    if "audio" in str(item.get("type", "")).lower():
        return fmt or "mp3"
    if "webm" in label:
        return "webm"
    return "mp4"


def _sort_links(links):
    def sort_key(item):
        item_type = 0 if str(item.get("type", "")).lower() == "video" else 1
        fmt = str(item.get("format", ""))
        try:
            quality = int(fmt)
        except ValueError:
            quality = 0
        return item_type, quality, str(item.get("label", ""))

    return sorted(links, key=sort_key)


async def _fetch_download_links(source_url):
    timeout = aiohttp.ClientTimeout(total=150, connect=20, sock_read=140)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(YOUTUBE_API_URL, params={"url": source_url}) as response:
            response.raise_for_status()
            payload = await response.json(content_type=None)
    if not isinstance(payload, dict):
        raise ValueError("YouTube API returned an invalid response.")
    links = [
        item
        for item in payload.get("downloadLinks", [])
        if isinstance(item, dict) and item.get("downloadUrl")
    ]
    if not links:
        raise ValueError("The YouTube API did not return any download links.")
    return payload, _sort_links(links)


@new_task
async def _youtube_api_callback(_, query):
    data = query.data.split()
    if len(data) != 3:
        await query.answer("Invalid selection.", show_alert=True)
        return
    token, index_text = data[1], data[2]
    selection = _pending_selections.get(token)
    if selection is None:
        await query.answer("This quality menu has expired.", show_alert=True)
        return
    if query.from_user.id != selection["user_id"]:
        await query.answer("This menu is not for you.", show_alert=True)
        return
    if index_text == "cancel":
        selection["selected"] = None
        selection["event"].set()
        await query.answer("Cancelled.")
        await editMessage(query.message, "Quality selection cancelled.")
        return
    try:
        index = int(index_text)
        selected = selection["links"][index]
    except (ValueError, IndexError):
        await query.answer("Invalid quality.", show_alert=True)
        return
    selection["selected"] = selected
    selection["event"].set()
    await query.answer("Quality selected.")
    await editMessage(
        query.message,
        f"<b>Selected:</b> {selected.get('label', selected.get('format', 'quality'))}\n"
        "<i>Starting download...</i>",
    )


async def choose_youtube_download(message, source_url, custom_name=""):
    """Fetch Vercel API links and wait for the requesting user to choose one."""
    wait_message = await sendMessage(
        message,
        "<b>Processing YouTube link...</b>\n"
        "<i>The API is preparing all quality links. This can take 50–60 seconds.</i>",
    )
    try:
        payload, links = await _fetch_download_links(source_url)
    except Exception as error:
        LOGGER.warning(f"YouTube API request failed: {error}")
        await editMessage(
            wait_message,
            f"<b>YouTube API error:</b> {str(error).replace('<', ' ').replace('>', ' ')}",
        )
        return None
    title = payload.get("title") or "YouTube video"
    token = token_hex(8)
    selection = {
        "event": Event(),
        "links": links,
        "selected": None,
        "user_id": message.from_user.id,
    }
    _pending_selections[token] = selection
    buttons = ButtonMaker()
    for index, item in enumerate(links):
        label = item.get("label") or item.get("fullFormat") or item.get("format")
        buttons.ibutton(str(label)[:48], f"ytapi {token} {index}")
    buttons.ibutton("Cancel", f"ytapi {token} cancel", position="footer")
    available = payload.get("summary", {}).get("available", len(links))
    menu_message = await sendMessage(
        message,
        f"<b>{escape(_safe_filename(title))}</b>\n"
        f"<i>{available} direct qualities are ready. Choose a quality:</i>",
        buttons.build_menu(2),
    )
    await deleteMessage(wait_message)
    try:
        await wait_for(selection["event"].wait(), timeout=_SELECTION_TIMEOUT)
    except TimeoutError:
        await editMessage(menu_message, "Quality selection timed out. Task cancelled.")
    finally:
        _pending_selections.pop(token, None)
    selected = selection.get("selected")
    if selected is None:
        return None
    extension = _extension_for_format(selected)
    filename = _safe_filename(custom_name or title)
    return {
        "url": selected["downloadUrl"],
        "title": title,
        "format": selected.get("format", ""),
        "label": selected.get("label", ""),
        "filename": f"{filename}.{extension}",
        "source_url": source_url,
    }


bot.add_handler(
    CallbackQueryHandler(_youtube_api_callback, filters=regex(r"^ytapi "))
)
