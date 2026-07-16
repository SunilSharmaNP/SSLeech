#!/usr/bin/env python3
from re import search as re_search

from aiofiles.os import remove as aioremove
from pyrogram.handlers import MessageHandler
from pyrogram.filters import command
from pyrogram.errors import (
    PhotoInvalidDimensions,
    WebpageCurlFailed,
    MediaEmpty,
    MediaCaptionTooLong,
    DocumentInvalid,
)

try:
    from pyrogram.types import LinkPreviewOptions
except ImportError:
    LinkPreviewOptions = None

from bot import bot, LOGGER, config_dict
from bot.helper.telegram_helper.filters import CustomFilters
from bot.helper.telegram_helper.bot_commands import BotCommands
from bot.helper.telegram_helper.message_utils import sendMessage, editMessage
from bot.helper.ext_utils.bot_utils import new_task, download_image_url
from bot.helper.ext_utils.spidy_api import fetch_spidy_assets
from bot.helper.ext_utils.tmdb_api import fetch_tmdb_assets


async def _reply_photo_with_caption(message, photo, text):
    """reply_photo with caption above the image. Falls back gracefully if
    show_caption_above_media is not supported by this Pyrogram build."""
    try:
        return await message.reply_photo(
            photo=photo,
            caption=text,
            show_caption_above_media=True,
            disable_notification=True,
        )
    except TypeError:
        return await message.reply_photo(
            photo=photo,
            caption=text,
            disable_notification=True,
        )


async def _send_poster_message(message, text, hero_photo):
    """Send text + hero image as ONE message (photo + caption).
    Returns None only when caption is too long (>1024 chars) so caller
    can fall back to two messages."""
    try:
        return await _reply_photo_with_caption(message, hero_photo, text)
    except MediaCaptionTooLong:
        return None
    except (PhotoInvalidDimensions, WebpageCurlFailed, MediaEmpty, DocumentInvalid):
        # URL-based send occasionally fails — download locally and retry.
        des_dir = await download_image_url(hero_photo)
        try:
            return await _reply_photo_with_caption(message, des_dir, text)
        except MediaCaptionTooLong:
            return None
        finally:
            await aioremove(des_dir)


async def _send_hero_photo(chat_id, photo_url):
    """Send hero image as a standalone message — two-message fallback only."""
    try:
        await bot.send_photo(chat_id=chat_id, photo=photo_url, disable_notification=True)
    except (PhotoInvalidDimensions, WebpageCurlFailed, MediaEmpty, DocumentInvalid):
        des_dir = await download_image_url(photo_url)
        try:
            await bot.send_photo(chat_id=chat_id, photo=des_dir, disable_notification=True)
        finally:
            await aioremove(des_dir)


async def _send_with_blockquoted_preview(message, text, hero_photo):
    """Reference-bot look: one plain-text message where the hero image
    appears as a Telegram link-preview thumbnail pinned via
    link_preview_options. Raises if this Pyrogram build can't do it."""
    if LinkPreviewOptions is None:
        raise TypeError("LinkPreviewOptions not supported by this Pyrogram build")
    preview_text = text + f"<a href='{hero_photo}'>\u2063</a>"
    return await message.reply(
        preview_text,
        quote=True,
        disable_notification=True,
        link_preview_options=LinkPreviewOptions(
            url=hero_photo,
            show_above_text=False,
            prefer_large_media=True,
        ),
    )


@new_task
async def poster_cmd(_, message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2 or not args[1].strip():
        await sendMessage(
            message,
            "<b>𝐔sᴀɢᴇ:</b> <code>/{0} movie name [year]</code>\n"
            "<b>𝐄x:</b> <code>/{0} pk 2014</code>".format(
                BotCommands.PosterCommand
            ),
        )
        return

    query = args[1].strip()
    year = None
    year_match = re_search(r"\b(19|20)\d{2}\b$", query)
    title = query
    if year_match:
        year = year_match.group(0)
        title = query[: year_match.start()].strip()

    status = await sendMessage(message, "<i>𝐒ᴇᴀʀᴄʜɪɴɢ 𝐏ᴏsᴛᴇʀs...</i>")

    # ── Spidy ────────────────────────────────────────────────────────────
    api_key = config_dict.get("SPIDY_API_KEY", "")
    try:
        assets = await fetch_spidy_assets(title, api_key, year=year)
    except Exception as e:
        LOGGER.error(f"Poster Command: Spidy API error for '{title}': {e}")
        assets = None

    # ── TMDB ─────────────────────────────────────────────────────────────
    tmdb_key = config_dict.get("TMDB_API_KEY", "")
    tmdb_result = None
    if tmdb_key:
        try:
            tmdb_result = await fetch_tmdb_assets(title, tmdb_key, year=year)
        except Exception as e:
            LOGGER.error(f"Poster Command: TMDB API error for '{title}': {e}")
            tmdb_result = None
    else:
        LOGGER.warning(
            "Poster Command: TMDB_API_KEY not configured — "
            "RAW Landscape, Logos Png and Portrait Posters (TMDB) will be empty."
        )

    # ── Collect assets per section ────────────────────────────────────────
    # Section 1 — Landscape Poster: Spidy thumbnails (logo already overlaid
    # by Spidy, so these are the "stylised" landscape images).
    landscape_poster = assets["landscape"] if assets else []

    # Section 2 — RAW Landscape: TMDB backdrops only (no logo/text overlay).
    raw_landscape = tmdb_result["backdrops"] if tmdb_result else []

    # Section 3 — Logos Png: TMDB clear logos (PNG + SVG).
    logos = tmdb_result["logos"] if tmdb_result else []

    # Section 4 — Portrait Poster: TMDB posters first, then Spidy portrait
    # (Spidy rarely has portrait; TMDB usually has several).
    portrait_posters = list(tmdb_result["posters"] if tmdb_result else [])
    for url in (assets["poster"] if assets else []):
        if url not in portrait_posters:
            portrait_posters.append(url)

    # Nothing at all → tell the user and stop.
    if not any([landscape_poster, raw_landscape, logos, portrait_posters]):
        await editMessage(
            status,
            f"<b>❌ 𝐍ᴏ 𝐏ᴏsᴛᴇʀs 𝐅ᴏᴜɴᴅ ғᴏʀ:</b> <i>{title}{f' ({year})' if year else ''}</i>",
        )
        return

    # ── Display title ─────────────────────────────────────────────────────
    display_title = (assets or tmdb_result)["title"]
    disp_year = (assets or tmdb_result).get("year") if assets else (tmdb_result or {}).get("year")
    if disp_year:
        display_title += f" ({disp_year})"

    tag = message.from_user.mention

    # ── Build message text ────────────────────────────────────────────────
    text = (
        "<blockquote>"
        f"<b>🎬 𝐌ᴏᴠɪᴇ:</b> {display_title}"
        "</blockquote>\n\n"
    )

    # Section 1 — Landscape Poster (Spidy, logo overlaid)
    if landscape_poster:
        text += "<b>🖼 𝐋ᴀɴᴅsᴄᴀᴘᴇ 𝐏ᴏsᴛᴇʀ:</b>\n<blockquote expandable>"
        for i, url in enumerate(landscape_poster, 1):
            text += f"{i}. <a href='{url}'>Click Here</a>\n"
        text += "</blockquote>\n"

    # Section 2 — RAW Landscape (TMDB, no logo)
    if raw_landscape:
        text += "<b>🌄 𝐑𝐀𝐖 𝐋ᴀɴᴅsᴄᴀᴘᴇ:</b>\n<blockquote expandable>"
        for i, url in enumerate(raw_landscape, 1):
            text += f"{i}. <a href='{url}'>Click Here</a>\n"
        text += "</blockquote>\n"

    # Section 3 — Logos Png
    if logos:
        text += "<b>🎨 𝐋ᴏɢᴏs 𝐏ɴɢ:</b>\n<blockquote expandable>"
        for i, url in enumerate(logos, 1):
            text += f"{i}. <a href='{url}'>Click Here</a>\n"
        text += "</blockquote>\n"

    # Section 4 — Portrait Poster (TMDB + Spidy)
    if portrait_posters:
        text += "<b>📸 𝐏ᴏʀᴛʀᴀɪᴛ 𝐏ᴏsᴛᴇʀ:</b>\n<blockquote expandable>"
        for i, url in enumerate(portrait_posters, 1):
            text += f"{i}. <a href='{url}'>Click Here</a>\n"
        text += "</blockquote>\n"

    text += (
        "<blockquote>"
        f"👑 <b>𝐑ᴇQᴜᴇsᴛᴇᴅ 𝐁ʏ:</b> {tag}"
        "</blockquote>\n"
    )

    # ── Hero photo: Spidy landscape first, then TMDB backdrop, portrait, logo
    if landscape_poster:
        hero_photo = landscape_poster[0]
    elif raw_landscape:
        hero_photo = raw_landscape[0]
    elif portrait_posters:
        hero_photo = portrait_posters[0]
    else:
        hero_photo = logos[0]

    # ── Send ──────────────────────────────────────────────────────────────
    try:
        await _send_with_blockquoted_preview(message, text, hero_photo)
        await status.delete()
    except Exception as e:
        LOGGER.error(f"Poster Command: blockquoted preview failed, falling back — {e}")
        try:
            sent = await _send_poster_message(message, text, hero_photo)
            await status.delete()
            if sent is None:
                await sendMessage(message, text)
                try:
                    await _send_hero_photo(message.chat.id, hero_photo)
                except Exception as e2:
                    LOGGER.error(f"Poster Command: Failed to send hero photo — {e2}")
        except Exception as e2:
            LOGGER.error(f"Poster Command: Failed to send result — {e2}")
            await editMessage(status, text)


bot.add_handler(
    MessageHandler(
        poster_cmd,
        filters=command(BotCommands.PosterCommand)
        & CustomFilters.authorized
        & ~CustomFilters.blacklisted,
    )
)
