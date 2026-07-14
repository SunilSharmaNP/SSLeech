#!/usr/bin/env python3
from re import search as re_search

from aiofiles.os import remove as aioremove
from pyrogram.handlers import MessageHandler
from pyrogram.filters import command
from pyrogram.errors import PhotoInvalidDimensions, WebpageCurlFailed, MediaEmpty

from bot import bot, LOGGER, config_dict
from bot.helper.telegram_helper.filters import CustomFilters
from bot.helper.telegram_helper.bot_commands import BotCommands
from bot.helper.telegram_helper.message_utils import sendMessage, editMessage
from bot.helper.ext_utils.bot_utils import new_task, download_image_url
from bot.helper.ext_utils.spidy_api import fetch_spidy_assets
from bot.helper.ext_utils.tmdb_api import fetch_tmdb_logo


async def _send_hero_photo(chat_id, photo_url):
    """Send the hero image as a plain, independent message — no reply/quote
    to any earlier message — so it visually stacks right under the text
    message like a normal consecutive bot message, instead of showing a
    separate 'replying to ...' bubble."""
    try:
        await bot.send_photo(chat_id=chat_id, photo=photo_url, disable_notification=True)
    except (PhotoInvalidDimensions, WebpageCurlFailed, MediaEmpty):
        # TMDB/landscape URLs occasionally fail Telegram's direct-URL fetch
        # (bad dimensions, curl error, etc.) — download locally and resend
        # as a real photo instead of letting Telegram fall back to sending
        # it as a generic file/document (which shows a "289.5 KB ..." file
        # header instead of a clean photo).
        des_dir = await download_image_url(photo_url)
        try:
            await bot.send_photo(chat_id=chat_id, photo=des_dir, disable_notification=True)
        finally:
            await aioremove(des_dir)


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

    api_key = config_dict.get("SPIDY_API_KEY", "")
    try:
        assets = await fetch_spidy_assets(title, api_key, year=year)
    except Exception as e:
        LOGGER.error(f"Poster Command: Spidy API error for '{title}': {e}")
        assets = None

    tmdb_key = config_dict.get("TMDB_API_KEY", "")
    tmdb_result = None
    if tmdb_key:
        try:
            tmdb_result = await fetch_tmdb_logo(title, tmdb_key, year=year)
        except Exception as e:
            LOGGER.error(f"Poster Command: TMDB API error for '{title}': {e}")
            tmdb_result = None

    # ALL PNG clear logos TMDB has (every language) — not just one.
    logos = tmdb_result["logos"] if tmdb_result else []

    if not assets and not logos:
        await editMessage(
            status,
            f"<b>❌ 𝐍ᴏ 𝐏ᴏsᴛᴇʀs 𝐅ᴏᴜɴᴅ ғᴏʀ:</b> <i>{title}{f' ({year})' if year else ''}</i>",
        )
        return

    if not assets:
        assets = {
            "title": tmdb_result["title"],
            "year": tmdb_result["year"],
            "landscape": [],
            "poster": [],
        }

    tag = message.from_user.mention
    display_title = assets["title"]
    if assets.get("year"):
        display_title += f" ({assets['year']})"

    text = (
        "<b><emoji id=5424818078833715060>🎬</emoji> 𝐌ᴏᴠɪᴇ:</b>"
        f"<blockquote>{display_title}</blockquote>\n\n"
    )

    if assets["landscape"]:
        text += "<b><emoji id=5334544901428229844>🖼</emoji> 𝐄ɴɢʟɪsʜ 𝐋ᴀɴᴅsᴄᴀᴘᴇ:</b>\n<blockquote expandable>"
        for i, url in enumerate(assets["landscape"], 1):
            text += f"{i}. <a href='{url}'>Click Here</a>\n"
        text += "</blockquote>\n"

    # Only added when TMDB actually has PNG clear logo(s) for this title —
    # never a placeholder/broken link when none is found. Every language
    # TMDB has a logo for is listed, matching how other bots present it.
    if logos:
        text += "<b><emoji id=5427168083074628963>🎨</emoji> 𝐋ᴏɢᴏs 𝐏ɴɢ:</b>\n<blockquote expandable>"
        for i, url in enumerate(logos, 1):
            text += f"{i}. <a href='{url}'>Click Here</a>\n"
        text += "</blockquote>\n"

    if assets["poster"]:
        text += "<b><emoji id=5190806721286657692>📸</emoji> 𝐏ᴏʀᴛʀᴀɪᴛ 𝐏ᴏsᴛᴇʀs:</b>\n"
        for i, url in enumerate(assets["poster"], 1):
            text += f"{i}. <a href='{url}'>Click Here</a>\n"
        text += "\n"

    text += (
        "<blockquote>"
        f"<emoji id=5217822164362739968>👑</emoji> <b>𝐑ᴇQᴜᴇsᴛᴇᴅ 𝐁ʏ:</b> {tag}\n"
        "</blockquote>\n"
        "<blockquote>"
        "<emoji id=5445355530111437729>📤</emoji> <b><i>𝐏ᴏᴡᴇʀᴇᴅ 𝐁ʏ 𝐒𝐒𝐋ᴇᴇᴄʜ 𝐏ᴏsᴛᴇʀ</i></b>"
        "</blockquote>"
    )

    if assets["landscape"]:
        hero_photo = assets["landscape"][0]
    elif assets["poster"]:
        hero_photo = assets["poster"][0]
    else:
        hero_photo = logos[0]

    try:
        # Sent as plain text (not a photo caption) so the full list of
        # thumbnails/logos is never silently truncated by Telegram's
        # 1024-char photo-caption limit — the hero image below is sent as
        # its own independent message (no reply/quote), so it visually
        # stacks right under this one like the reference bot's UI.
        await sendMessage(message, text)
        await status.delete()
        try:
            await _send_hero_photo(message.chat.id, hero_photo)
        except Exception as e:
            LOGGER.error(f"Poster Command: Failed to send hero photo — {e}")
    except Exception as e:
        LOGGER.error(f"Poster Command: Failed to send result — {e}")
        await editMessage(status, text)


bot.add_handler(
    MessageHandler(
        poster_cmd,
        filters=command(BotCommands.PosterCommand)
        & CustomFilters.authorized
        & ~CustomFilters.blacklisted,
    )
)
