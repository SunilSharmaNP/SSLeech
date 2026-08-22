#!/usr/bin/env python3
from ast import literal_eval
from datetime import datetime
from pyrogram.handlers import MessageHandler, CallbackQueryHandler
from pyrogram.filters import command, regex, create

from aiofiles import open as aiopen
from aiofiles.os import remove as aioremove, path as aiopath, mkdir, makedirs
from langcodes import Language
from os import path as ospath, getcwd
from PIL import Image
from time import time
from functools import partial
from html import escape

# Premium emoji tags must NOT be passed through html.escape() — it breaks <> into &lt;&gt;
_TICK  = '<emoji id=5206607081334906820>✔️</emoji>'
_CROSS = '<emoji id=5210952531676504517>❌</emoji>'
def _pesc(val):
    """escape() for HTML, but leave premium-emoji tags intact."""
    if val in (_TICK, _CROSS) or str(val).startswith('<emoji '):
        return val
    return escape(str(val))


def _setting_bool(value):
    """Normalize booleans loaded from env vars, JSON, or MongoDB."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().casefold() in {"1", "true", "yes", "on"}
    return bool(value)
from io import BytesIO
from asyncio import sleep
from cryptography.fernet import Fernet

import asyncio


from bot import (
    OWNER_ID,
    LOGGER,
    bot,
    user_data,
    config_dict,
    categories_dict,
    DATABASE_URL,
    IS_PREMIUM_USER,
    MAX_SPLIT_SIZE,
)
from bot.helper.telegram_helper.message_utils import (
    sendMessage,
    sendCustomMsg,
    editMessage,
    deleteMessage,
    sendFile,
    chat_info,
    user_info,
)
from bot.helper.telegram_helper.filters import CustomFilters
from bot.helper.telegram_helper.bot_commands import BotCommands
from bot.helper.telegram_helper.button_build import ButtonMaker
from bot.helper.mirror_utils.upload_utils.gdriveTools import GoogleDriveHelper
from bot.helper.ext_utils.db_handler import DbManger
from bot.helper.ext_utils.bot_utils import (
    getdailytasks,
    update_user_ldata,
    get_readable_file_size,
    sync_to_async,
    new_thread,
    is_gdrive_link,
)
from bot.helper.mirror_utils.upload_utils.ddlserver.gofile import Gofile
from bot.helper.themes import BotTheme


def _get_lang_name(lang_code: str) -> str:
    if not lang_code:
        return "N/A"
    try:
        return Language.get(lang_code).display_name()
    except Exception:
        return lang_code


handler_dict = {}
desp_dict = {
    "lprefix": [
        "𝐋ᴇᴇᴄʜ 𝐅ɪʟᴇɴᴀᴍᴇ 𝐏ʀᴇғɪx 𝐈s 𝐓ʜᴇ 𝐅ʀᴏɴᴛ 𝐏ᴀʀᴛ 𝐀ᴛᴛᴀᴄᴛᴇᴅ 𝐖ɪᴛʜ 𝐓ʜᴇ 𝐅ɪʟᴇɴᴀᴍᴇ 𝐎ғ 𝐓ʜᴇ 𝐋ᴇᴇᴄʜ 𝐅ɪʟᴇs.",
        '𝐒ᴇɴᴅ 𝐋ᴇᴇᴄʜ 𝐅ɪʟᴇɴᴀmě 𝐏ʀᴇғɪx. 𝐃ᴏᴄᴜᴍᴇɴᴛᴀᴛɪᴏɴ 𝐇ᴇʀᴇ : <a href="https://t.me/WZML_X/77">𝐂ʟɪᴄᴋ 𝐌ᴇ</a> \n<b>𝐓ɪᴍᴇᴏᴜᴛ:</b> 60 𝐒ᴇᴄ',
    ],
    "lsuffix": [
        "𝐋ᴇᴇᴄʜ 𝐅ɪʟᴇɴᴀᴍᴇ 𝐒ᴜғғɪx 𝐈s 𝐓ʜᴇ 𝐄ɴᴅ 𝐏ᴀʀᴛ 𝐀ᴛᴛᴀᴄʜᴇᴅ 𝐖ɪᴛʜ 𝐓ʜᴇ 𝐅ɪʟᴇɴᴀᴍᴇ 𝐎ғ 𝐓ʜᴇ 𝐋ᴇᴇᴄʜ 𝐅ɪʟᴇs",
        '𝐒ᴇɴᴅ 𝐋ᴇᴇᴄʜ 𝐅ɪʟᴇɴᴀᴍᴇ 𝐒ᴜғғɪx. 𝐃ᴏᴄᴜᴍᴇɴᴛᴀᴛɪᴏɴ 𝐇ᴇʀᴇ : <a href="https://t.me/WZML_X/77">𝐂ʟɪᴄᴋ 𝐌ᴇ</a> \n<b>𝐓ɪᴍᴇᴏᴜᴛ:</b> 60 𝐒ᴇᴄ',
    ],
    "lremname": [
        "𝐋ᴇᴇᴄʜ 𝐅ɪʟᴇɴᴀᴍᴇ 𝐑ᴇᴍɴᴀᴍᴇ 𝐈s 𝐂ᴏᴍʙɪɴᴀᴛɪᴏɴ 𝐎ғ 𝐑ᴇɢᴇx(s) 𝐔sᴇᴅ 𝐅ᴏʀ 𝐑ᴇᴍᴏᴠɪɴɢ 𝐎ʀ 𝐌ᴀɴɪᴘᴜʟᴀᴛɪɴɢ 𝐅ɪʟᴇɴᴀᴍᴇ 𝐎ғ 𝐓ʜᴇ 𝐋ᴇᴇᴄʜ 𝐅ɪʟᴇs",
        '𝐒ᴇɴᴅ 𝐋ᴇᴇᴄʜ 𝐅ɪʟᴇɴᴀᴍᴇ 𝐑ᴇᴍɴᴀᴍᴇ. 𝐃ᴏᴄᴜᴍᴇɴᴛᴀᴛɪᴏɴ 𝐇ᴇʀᴇ : <a href="https://t.me/WZML_X/77">𝐂ʟɪᴄᴋ 𝐌ᴇ</a> \n<b>𝐓ɪᴍᴇᴏᴜᴛ:</b> 60 𝐒ᴇᴄ',
    ],
    "lcaption": [
        "𝐋ᴇᴇᴄʜ 𝐂ᴀᴘᴛɪᴏɴ 𝐈s 𝐓ʜᴇ 𝐂ᴜsᴛᴏᴍ 𝐂ᴀᴘᴛɪᴏɴ 𝐎ɴ 𝐓ʜᴇ 𝐋ᴇᴇᴄʜ 𝐅ɪʟᴇs 𝐔ᴘʟᴏᴀᴅᴇᴅ 𝐁ʏ 𝐓ʜᴇ 𝐁ᴏᴛ",
        '𝐒ᴇɴᴅ 𝐋ᴇᴇᴄʜ 𝐂ᴀᴘᴛɪᴏɴ. 𝐘ᴏᴜ 𝐂ᴀɴ 𝐀ᴅᴅ 𝐇ᴛᴍʟ 𝐓ᴀɢs. 𝐃ᴏᴄᴜᴍᴇɴᴛᴀᴛɪᴏɴ 𝐇ᴇʀᴇ : <a href="https://t.me/WZML_X/77">𝐂ʟɪᴄᴋ 𝐌ᴇ</a> \n<b>𝐓ɪᴍᴇᴏᴜᴛ:</b> 60 𝐒ᴇᴄ',
    ],
    "ldump": [
        "𝐋ᴇᴇᴄʜ 𝐅ɪʟᴇs 𝐔sᴇʀ 𝐃ᴜᴍᴘ 𝐅ᴏʀ 𝐏ᴇʀsᴏɴᴀʟ 𝐔sᴇ 𝐀s 𝐀 𝐒ᴛᴏʀᴀɢᴇ.",
        "𝐒ᴇɴᴅ 𝐋ᴇᴇᴄʜ 𝐃ᴜᴍᴘ 𝐂ʜᴀɴɴᴇʟ 𝐈ᴅ\n➲ <b>𝐅ᴏʀᴍᴀᴛ:</b> \nᴛɪᴛʟᴇ ᴄʜᴀᴛ_ɪᴅ/@ᴜsᴇʀɴᴀᴍᴇ\nᴛɪᴛʟᴇ2 ᴄʜᴀᴛ_ɪᴅ2/@ᴜsᴇʀɴᴀᴍᴇ2. \n\n<b>𝐍ᴏᴛᴇ:</b>𝐌ᴀᴋᴇ 𝐁ᴏᴛ 𝐀ᴅᴍɪɴ 𝐈ɴ 𝐓ʜᴇ 𝐂ʜᴀɴɴᴇʟ 𝐄ʟsᴇ 𝐈ᴛ 𝐖ɪʟʟ 𝐍ᴏᴛ 𝐀ᴄᴄᴇᴘᴛ\n<b>𝐓ɪᴍᴇᴏᴜᴛ:</b> 60 𝐒ᴇᴄ",
    ],
    "mprefix": [
        "𝐌ɪʀʀᴏʀ 𝐅ɪʟᴇɴᴀᴍᴇ 𝐏ʀᴇғɪx 𝐈s 𝐓ʜᴇ 𝐅ʀᴏɴᴛ 𝐏ᴀʀᴛ 𝐀ᴛᴛᴀᴄᴛᴇᴅ 𝐖ɪᴛʜ 𝐓ʜᴇ 𝐅ɪʟᴇɴᴀᴍᴇ 𝐎ғ 𝐓ʜᴇ 𝐌ɪʀʀᴏʀᴇᴅ/𝐂ʟᴏɴᴇᴅ 𝐅ɪʟᴇs.",
        "𝐒ᴇɴᴅ 𝐌ɪʀʀᴏʀ 𝐅ɪʟᴇɴᴀᴍᴇ 𝐏ʀᴇғɪx. \n<b>𝐓ɪᴍᴇᴏᴜᴛ:</b> 60 𝐒ᴇᴄ",
    ],
    "msuffix": [
        "𝐌ɪʀʀᴏʀ 𝐅ɪʟᴇɴᴀᴍᴇ 𝐒ᴜғғɪx 𝐈s 𝐓ʜᴇ 𝐄ɴᴅ 𝐏ᴀʀᴛ 𝐀ᴛᴛᴀᴄʜᴇᴅ 𝐖ɪᴛʜ 𝐓ʜᴇ 𝐅ɪʟᴇɴᴀᴍᴇ 𝐎ғ 𝐓ʜᴇ 𝐌ɪʀʀᴏʀᴇᴅ/𝐂ʟᴏɴᴇᴅ 𝐅ɪʟᴇs",
        "𝐒ᴇɴᴅ 𝐌ɪʀʀᴏʀ 𝐅ɪʟᴇɴᴀᴍᴇ 𝐒ᴜғғɪx. \n<b>𝐓ɪᴍᴇᴏᴜᴛ:</b> 60 𝐒ᴇᴄ",
    ],
    "mremname": [
        "𝐌ɪʀʀᴏʀ 𝐅ɪʟᴇɴᴀᴍᴇ 𝐑ᴇᴍɴᴀᴍᴇ 𝐈s 𝐂ᴏᴍʙɪɴᴀᴛɪᴏɴ 𝐎ғ 𝐑ᴇɢᴇx(s) 𝐔sᴇᴅ 𝐅ᴏʀ 𝐑ᴇᴍᴏᴠɪɴɢ 𝐎ʀ 𝐌ᴀɴɪᴘᴜʟᴀᴛɪɴɢ 𝐅ɪʟᴇɴᴀᴍᴇ 𝐎ғ 𝐓ʜᴇ 𝐌ɪʀʀᴏʀᴇᴅ/𝐂ʟᴏɴᴇᴅ 𝐅ɪʟᴇs",
        "𝐒ᴇɴᴅ 𝐌ɪʀʀᴏʀ 𝐅ɪʟᴇɴᴀᴍᴇ 𝐑ᴇᴍɴᴀᴍᴇ. \n<b>𝐓ɪᴍᴇᴏᴜᴛ:</b> 60 𝐒ᴇᴄ",
    ],
    "thumb": [
        "𝐂ᴜsᴛᴏᴍ 𝐓ʜᴜᴍʙɴᴀɪʟ 𝐓ᴏ 𝐀ᴘᴘᴇᴀʀ 𝐎ɴ 𝐓ʜᴇ 𝐋ᴇᴇᴄʜᴇᴅ 𝐅ɪʟᴇs 𝐔ᴘʟᴏᴀᴅᴇᴅ 𝐁ʏ 𝐓ʜᴇ 𝐁ᴏᴛ",
        "𝐒ᴇɴᴅ 𝐀 𝐏ʜᴏᴛᴏ 𝐓ᴏ 𝐒ᴀᴠᴇ 𝐈ᴛ 𝐀s 𝐂ᴜsᴛᴏᴍ 𝐓ʜᴜᴍʙɴᴀɪʟ. \n<b>𝐀ʟᴛᴇʀɴᴀᴛɪᴠᴇʟʏ: </b><code>/cmd [photo] -s thumb</code> \n<b>𝐓ɪᴍᴇᴏᴜᴛ:</b> 60 𝐒ᴇᴄ",
    ],
    "yt_opt": [
        "𝐘ᴛ-𝐃ʟᴘ 𝐎ᴘᴛɪᴏɴs 𝐈s 𝐓ʜᴇ 𝐂ᴜsᴛᴏᴍ 𝐐ᴜᴀʟɪᴛʏ 𝐅ᴏʀ 𝐓ʜᴇ 𝐄xᴛʀᴀᴄᴛɪᴏɴ 𝐎ғ 𝐕ɪᴅᴇᴏs 𝐅ʀᴏᴍ 𝐓ʜᴇ 𝐘ᴛ-ᴅʟᴘ 𝐒ᴜᴘᴘᴏʀᴛᴇᴅ 𝐒ɪᴛᴇs.",
        '𝐒ᴇɴᴅ 𝐘ᴛ-𝐃ʟᴘ 𝐎ᴘᴛɪᴏɴs. 𝐓ɪᴍᴇᴏᴜᴛ: 60 𝐒ᴇᴄ\n𝐅ᴏʀᴍᴀᴛ: ᴋᴇʏ:ᴠᴀʟᴜᴇ|ᴋᴇʏ:ᴠᴀʟᴜᴇ|ᴋᴇʏ:ᴠᴀʟᴜᴇ.\n𝐄xᴀᴍᴘʟᴇ: ғᴏʀᴍᴀᴛ:ʙᴠ*+ᴍᴇʀɢᴇᴀʟʟ[ᴠᴄᴏᴅᴇᴄ=ɴᴏɴᴇ]|ɴᴏᴄʜᴇᴄᴋᴄᴇʀᴛɪғɪᴄᴀᴛᴇ:𝐓ʀᴜᴇ\n𝐂ʜᴇᴄᴋ 𝐀ʟʟ 𝐘ᴛ-ᴅʟᴘ 𝐀ᴘɪ 𝐎ᴘᴛɪᴏɴs 𝐅ʀᴏᴍ 𝐓ʜɪs <a href="https://github.com/yt-dlp/yt-dlp/blob/master/yt_dlp/YoutubeDL.py#L184">𝐅ɪʟᴇ</a> 𝐓ᴏ 𝐂ᴏɴᴠᴇʀᴛ 𝐂ʟɪ 𝐀ʀɢᴜᴍᴇɴᴛs 𝐓ᴏ 𝐀ᴘɪ 𝐎ᴘᴛɪᴏɴs.',
    ],
    "usess": [
        f'𝐔sᴇʀ 𝐒ᴇssɪᴏɴ 𝐈s 𝐓ᴇʟᴇɢʀᴀᴍ 𝐒ᴇssɪᴏɴ 𝐔sᴇᴅ 𝐓ᴏ 𝐃ᴏᴡɴʟᴏᴀᴅ 𝐏ʀɪᴠᴀᴛᴇ 𝐂ᴏɴᴛᴇɴᴛs 𝐅ʀᴏᴍ 𝐏ʀɪᴠᴀᴛᴇ 𝐂ʜᴀɴɴᴇʟs 𝐖ɪᴛʜ 𝐍ᴏ 𝐂ᴏᴍᴘʀᴏᴍɪsᴇ 𝐈ɴ 𝐏ʀɪᴠᴀᴄʏ, 𝐁ᴜɪʟᴅ 𝐖ɪᴛʜ 𝐄ɴᴄʀʏᴘᴛɪᴏɴ.\n{"<b>Warning:</b> This Bot is not secured. We recommend asking the group owner to set the Upstream repo to the Official repo. If it is not the official repo, then WZML-X is not responsible for any issues that may occur in your account." if config_dict["UPSTREAM_REPO"] != "https://github.com/weebzone/WZML-X" else "Bot is Secure. You can use the session securely."}',
        "𝐒ᴇɴᴅ 𝐘ᴏᴜʀ 𝐒ᴇssɪᴏɴ 𝐒ᴛʀɪɴɢ.\n<b>𝐓ɪᴍᴇᴏᴜᴛ:</b> 60 𝐒ᴇᴄ",
    ],
    "split_size": [
        "𝐋ᴇᴇᴄʜ 𝐒ᴘʟɪᴛs 𝐒ɪᴢᴇ 𝐈s 𝐓ʜᴇ 𝐒ɪᴢᴇ 𝐓ᴏ 𝐒ᴘʟɪᴛ 𝐓ʜᴇ 𝐋ᴇᴇᴄʜᴇᴅ 𝐅ɪʟᴇ 𝐁ᴇғᴏʀᴇ 𝐔ᴘʟᴏᴀᴅɪɴɢ",
        f"𝐒ᴇɴᴅ 𝐋ᴇᴇᴄʜ 𝐒ᴘʟɪᴛ 𝐒ɪᴢᴇ 𝐈ɴ 𝐀ɴʏ 𝐂ᴏᴍғᴏʀᴛᴀʙʟᴇ 𝐒ɪᴢᴇ, 𝐋ɪᴋᴇ 2𝐆ʙ, 500𝐌ʙ 𝐎ʀ 1.46ɢʙ. \n<b>𝐏ʀᴇᴍɪᴜᴍ 𝐀ᴄᴛɪᴠᴇ:</b> {IS_PREMIUM_USER}. \n<b>𝐓ɪᴍᴇᴏᴜᴛ:</b> 60 𝐒ᴇᴄ",
    ],
    "ddl_servers": [
        "𝐃ᴅʟ 𝐒ᴇʀᴠᴇʀs 𝐖ʜɪᴄʜ 𝐔ᴘʟᴏᴀᴅs 𝐘ᴏᴜʀ 𝐅ɪʟᴇ 𝐓ᴏ 𝐓ʜᴇɪʀ 𝐒ᴘᴇᴄɪғɪᴄ 𝐇ᴏsᴛɪɴɢ",
        "",
    ],
    "user_tds": [
        f'𝐔sᴇʀᴛᴅ 𝐇ᴇʟᴘs 𝐓ᴏ 𝐔ᴘʟᴏᴀᴅ 𝐅ɪʟᴇs 𝐕ɪᴀ 𝐁ᴏᴛ 𝐓ᴏ 𝐘ᴏᴜʀ 𝐂ᴜsᴛᴏᴍ 𝐃ʀɪᴠᴇ 𝐃ᴇsᴛɪɴᴀᴛɪᴏɴ 𝐕ɪᴀ 𝐆ʟᴏʙᴀʟ 𝐒ᴀ 𝐌ᴀɪʟ\n\n➲ <b>𝐒ᴀ 𝐌ᴀɪʟ :</b> {"Not Specified" if "USER_TD_SA" not in config_dict else config_dict["USER_TD_SA"]}',
        "𝐒ᴇɴᴅ 𝐔sᴇʀ 𝐓ᴅ 𝐃ᴇᴛᴀɪʟs 𝐅ᴏʀ 𝐔sᴇ 𝐖ʜɪʟᴇ 𝐌ɪʀʀᴏʀ/𝐂ʟᴏɴᴇ\n➲ <b>𝐅ᴏʀᴍᴀᴛ:</b>\nɴᴀᴍᴇ ɪᴅ/ʟɪɴᴋ ɪɴᴅᴇx(ᴏᴘᴛɪᴏɴᴀʟ)\nɴᴀᴍᴇ2 ʟɪɴᴋ2/ɪᴅ2 ɪɴᴅᴇx(ᴏᴘᴛɪᴏɴᴀʟ)\n\n<b>𝐍ᴏᴛᴇ:</b>\n<i>1. 𝐃ʀɪᴠᴇ 𝐈ᴅ 𝐌ᴜsᴛ 𝐁ᴇ 𝐕ᴀʟɪᴅ, 𝐓ʜᴇɴ 𝐎ɴʟʏ 𝐈ᴛ 𝐖ɪʟʟ 𝐀ᴄᴄᴇᴘᴛ\n2. 𝐍ᴀᴍᴇs 𝐂ᴀɴ 𝐇ᴀᴠᴇ 𝐒ᴘᴀᴄᴇs\n3. 𝐀ʟʟ 𝐔sᴇʀᴛᴅs 𝐀ʀᴇ 𝐔ᴘᴅᴀᴛᴇᴅ 𝐎ɴ 𝐄ᴠᴇʀʏ 𝐂ʜᴀɴɢᴇ\n4. 𝐓ᴏ 𝐃ᴇʟᴇᴛᴇ 𝐒ᴘᴇᴄɪғɪᴄ 𝐔sᴇʀᴛᴅ, 𝐆ɪᴠᴇ 𝐍ᴀᴍᴇ(s) 𝐒ᴇᴘᴀʀᴀᴛᴇᴅ 𝐁ʏ 𝐄ᴀᴄʜ 𝐋ɪɴᴇ</i>\n\n<b>𝐓ɪᴍᴇᴏᴜᴛ:</b> 60 𝐒ᴇᴄ",
    ],
    "gofile": [
        "𝐆ᴏғɪʟᴇ 𝐈s 𝐀 𝐅ʀᴇᴇ 𝐅ɪʟᴇ 𝐒ʜᴀʀɪɴɢ 𝐀ɴᴅ 𝐒ᴛᴏʀᴀɢᴇ 𝐏ʟᴀᴛғᴏʀᴍ. 𝐘ᴏᴜ 𝐂ᴀɴ 𝐒ᴛᴏʀᴇ 𝐀ɴᴅ 𝐒ʜᴀʀᴇ 𝐘ᴏᴜʀ 𝐂ᴏɴᴛᴇɴᴛ 𝐖ɪᴛʜᴏᴜᴛ 𝐀ɴʏ 𝐋ɪᴍɪᴛ.",
        "𝐒ᴇɴᴅ 𝐆ᴏ𝐅ɪʟᴇ's 𝐀ᴘɪ 𝐊ᴇʏ. 𝐆ᴇᴛ 𝐈ᴛ 𝐎ɴ ʜᴛᴛᴘs://ɢᴏғɪʟᴇ.ɪᴏ/ᴍʏ𝐏ʀᴏғɪʟᴇ, 𝐈ᴛ 𝐖ɪʟʟ 𝐍ᴏᴛ 𝐁ᴇ 𝐀ᴄᴄᴇᴘᴛᴇᴅ 𝐈ғ 𝐓ʜᴇ 𝐀ᴘɪ 𝐊ᴇʏ 𝐈s 𝐈ɴᴠᴀʟɪᴅ !!\n<b>𝐓ɪᴍᴇᴏᴜᴛ:</b> 60 𝐒ᴇᴄ",
    ],
    "streamtape": [
        "𝐒ᴛʀᴇᴀᴍᴛᴀᴘᴇ 𝐈s 𝐅ʀᴇᴇ 𝐕ɪᴅᴇᴏ 𝐒ᴛʀᴇᴀᴍɪɴɢ & 𝐒ʜᴀʀɪɴɢ 𝐇ᴏsᴛᴇʀ",
        "𝐒ᴇɴᴅ 𝐒ᴛʀᴇᴀᴍ𝐓ᴀᴘᴇ's 𝐋ᴏɢɪɴ 𝐀ɴᴅ 𝐊ᴇʏ\n<b>𝐅ᴏʀᴍᴀᴛ:</b> <code>user_login:pass_key</code>\n<b>𝐓ɪᴍᴇᴏᴜᴛ:</b> 60 𝐒ᴇᴄ",
    ],
    "lmeta": [
        "𝐘ᴏᴜʀ 𝐂ʜᴀɴɴᴇʟ 𝐍ᴀᴍᴇ 𝐓ʜᴀᴛ 𝐖ɪʟʟ 𝐁ᴇ 𝐔sᴇᴅ 𝐖ʜɪʟᴇ 𝐄ᴅɪᴛɪɴɢ 𝐌ᴇᴛᴀᴅᴀᴛᴀ 𝐎ғ 𝐓ʜᴇ 𝐕ɪᴅᴇᴏ 𝐅ɪʟᴇ",
        "𝐒ᴇɴᴅ 𝐌ᴇᴛᴀᴅᴀᴛᴀ 𝐓ᴇxᴛ 𝐅ᴏʀ 𝐋ᴇᴇᴄʜɪɴɢ 𝐅ɪʟᴇs.\n<b>𝐓ɪᴍᴇᴏᴜᴛ:</b> 60 𝐒ᴇᴄ.",
    ],
    "auto_rename_fmt": [
        "𝐂ᴜsᴛᴏᴍ 𝐀ᴜᴛᴏ 𝐑ᴇɴᴀᴍᴇ 𝐅ᴏʀᴍᴀᴛ — ᴜsᴇ ᴘʟᴀᴄᴇʜᴏʟᴅᴇʀs ᴛᴏ ʙᴜɪʟᴅ ʏᴏᴜʀ ᴏᴡɴ ғɪʟᴇɴᴀᴍᴇ ᴛᴇᴍᴘʟᴀᴛᴇ.",
        (
            "𝐒ᴇɴᴅ ʏᴏᴜʀ ғᴏʀᴍᴀᴛ sᴛʀɪɴɢ. <b>𝐓ɪᴍᴇᴏᴜᴛ:</b> 60 𝐒ᴇᴄ\n\n"
            "<b>𝐀ᴠᴀɪʟᴀʙʟᴇ ᴘʟᴀᴄᴇʜᴏʟᴅᴇʀs:</b>\n"
            "<code>{name}</code>  —  𝐓ɪᴛʟᴇ\n"
            "<code>{year}</code>  —  𝐘ᴇᴀʀ (ᴠɪᴀ ɪᴍᴅʙ ɪғ ɴᴏᴛ ɪɴ ғɪʟᴇ)\n"
            "<code>{quality}</code>  —  480ᴘ / 720ᴘ / 1080ᴘ\n"
            "<code>{resolution}</code>  —  1280x720\n"
            "<code>{rip}</code>  —  𝐇𝐃𝐑ɪᴘ / 𝐁ʟᴜ𝐑ᴀʏ\n"
            "<code>{season}</code>  —  𝐒01 (ᴇᴍᴘᴛʏ ғᴏʀ ᴍᴏᴠɪᴇs)\n"
            "<code>{episode}</code>  —  𝐄01\n"
            "<code>{audio}</code>  —  𝐅ᴜʟʟ ᴀᴜᴅɪᴏ ʟᴀʙᴇʟ\n"
            "<code>{shortlang}</code>  —  𝐃ᴜᴀʟ / 𝐇ɪɴᴅɪ / 𝐌ᴜʟᴛɪ\n"
            "<code>{lib}</code>  —  x264 / x265\n"
            "<code>{audiocodec}</code>  —  𝐀𝐀𝐂 / 𝐀𝐂3 / 𝐃𝐓𝐒\n"
            "<code>{shortsub}</code>  —  𝐄𝐒ᴜʙs / 𝐌𝐒ᴜʙs\n"
            "<code>{hevc}</code>  —  𝐇𝐄𝐕𝐂 (ᴇᴍᴘᴛʏ ɪғ ɴᴏᴛ x265)\n"
            "<code>{extension}</code>  —  .ᴍᴋᴠ / .ᴍᴘ4\n\n"
            "<b>𝐄xᴀᴍᴘʟᴇ:</b>\n"
            "<code>{name} ({year}) {quality} {hevc} {rip} {audio} {season} Complete Series {lib} {audiocodec} {shortsub}</code>"
        ),
    ],
}
desp_dict["ar_fmt"] = desp_dict["auto_rename_fmt"]

fname_dict = {
    "lprefix": "𝐏ʀᴇғɪx",
    "lsuffix": "𝐒ᴜғғɪx",
    "lremname": "𝐑ᴇᴍɴᴀᴍᴇ",
    "lmeta": "𝐌ᴇᴛᴀᴅᴀᴛᴀ",
    "mprefix": "𝐏ʀᴇғɪx",
    "msuffix": "𝐒ᴜғғɪx",
    "mremname": "𝐑ᴇᴍɴᴀᴍᴇ",
    "ldump": "𝐔sᴇʀ 𝐃ᴜᴍᴘ",
    "lcaption": "𝐂ᴀᴘᴛɪᴏɴ",
    "thumb": "𝐓ʜᴜᴍʙɴᴀɪʟ",
    "yt_opt": "𝐘ᴛ-𝐃ʟᴘ 𝐎ᴘᴛɪᴏɴs",
    "usess": "𝐔sᴇʀ 𝐒ᴇssɪᴏɴ",
    "split_size": "𝐋ᴇᴇᴄʜ 𝐒ᴘʟɪᴛs",
    "ddl_servers": "𝐃ᴅʟ 𝐒ᴇʀᴠᴇʀs",
    "user_tds": "𝐔sᴇʀ 𝐂ᴜsᴛᴏᴍ 𝐓ᴅs",
    "gofile": "𝐆ᴏ𝐅ɪʟᴇ",
    "streamtape": "𝐒ᴛʀᴇᴀᴍ𝐓ᴀᴘᴇ",
    "auto_rename_fmt": "𝐀ᴜᴛᴏ 𝐑ᴇɴᴀᴍᴇ 𝐅ᴏʀᴍᴀᴛ",
    "ar_fmt": "𝐅ᴏʀᴍᴀᴛ",
}


async def _usetting_photo(user_id: int) -> str:
    thumb_path = f"Thumbnails/{user_id}.jpg"
    if await aiopath.exists(thumb_path):
        return thumb_path
    return "IMAGES"


async def get_user_settings(from_user, key=None, edit_type=None, edit_mode=None):
    user_id = from_user.id
    name = from_user.mention(style="html")
    buttons = ButtonMaker()
    thumbpath = f"Thumbnails/{user_id}.jpg"
    user_dict = user_data.get(user_id, {})
    if key is None:
        buttons.ibutton("𝐔ɴɪᴠᴇʀsᴀʟ 𝐒ᴇᴛᴛɪɴɢs", f"userset {user_id} universal", icon_custom_emoji_id=5341715473882955310)
        buttons.ibutton("𝐌ɪʀʀᴏʀ 𝐒ᴇᴛᴛɪɴɢs", f"userset {user_id} mirror", icon_custom_emoji_id=5224450179368767019)
        buttons.ibutton("𝐋ᴇᴇᴄʜ 𝐒ᴇᴛᴛɪɴɢs", f"userset {user_id} leech", icon_custom_emoji_id=5443127283898405358)
        if user_dict and any(key in user_dict for key in list(fname_dict.keys())):
            buttons.ibutton("𝐑ᴇsᴇᴛ 𝐒ᴇᴛᴛɪɴɢ", f"userset {user_id} reset_all", icon_custom_emoji_id=5445267414562389170)
        buttons.ibutton("𝐂ʟᴏsᴇ", f"userset {user_id} close", icon_custom_emoji_id=5447644880824181073)

        text = BotTheme(
            "USER_SETTING",
            NAME=name,
            ID=user_id,
            USERNAME=f"@{from_user.username}",
            LANG=_get_lang_name(from_user.language_code),
            DC=from_user.dc_id,
        )

        button = buttons.build_menu(1)
    elif key == "universal":
        ytopt = (
            "<emoji id=5210952531676504517>❌</emoji>"
            if (val := user_dict.get("yt_opt", config_dict.get("YT_DLP_OPTIONS", "")))
            == ""
            else val
        )
        buttons.ibutton(
            f"{'' if ytopt != '<emoji id=5210952531676504517>❌</emoji>' else ''} 𝐘ᴛ-𝐃ʟᴘ 𝐎ᴘᴛɪᴏɴs",
            f"userset {user_id} yt_opt",
            icon_custom_emoji_id=5341715473882955310
        )
        u_sess = "<emoji id=5206607081334906820>✔️</emoji>" if user_dict.get("usess", False) else "<emoji id=5210952531676504517>❌</emoji>"
        buttons.ibutton(
            f"{'' if u_sess != '<emoji id=5210952531676504517>❌</emoji>' else ''} 𝐔sᴇʀ 𝐒ᴇssɪᴏɴ",
            f"userset {user_id} usess",
            icon_custom_emoji_id=5197288647275071607
        )
        bot_pm = (
            "<emoji id=5206607081334906820>✔️</emoji>" if user_dict.get("bot_pm", config_dict["BOT_PM"]) else "<emoji id=5210952531676504517>❌</emoji>"
        )
        buttons.ibutton(
            " 𝐃ɪsᴀʙʟᴇ 𝐁ᴏᴛ 𝐏ᴍ" if bot_pm == "<emoji id=5206607081334906820>✔️</emoji>" else " 𝐄ɴᴀʙʟᴇ 𝐁ᴏᴛ 𝐏ᴍ",
            f"userset {user_id} bot_pm",
            icon_custom_emoji_id=5424818078833715060
        )
        if config_dict["BOT_PM"]:
            bot_pm = "<emoji id=5206607081334906820>✔️</emoji> 𝐅ᴏʀᴄᴇ"
        mediainfo = (
            "<emoji id=5206607081334906820>✔️</emoji>"
            if user_dict.get("mediainfo", config_dict["SHOW_MEDIAINFO"])
            else "<emoji id=5210952531676504517>❌</emoji>"
        )
        buttons.ibutton(
            " 𝐃ɪsᴀʙʟᴇ 𝐌ᴇᴅɪᴀ𝐈ɴғᴏ" if mediainfo == "<emoji id=5206607081334906820>✔️</emoji>" else " 𝐄ɴᴀʙʟᴇ 𝐌ᴇᴅɪᴀ𝐈ɴғᴏ",
            f"userset {user_id} mediainfo",
            icon_custom_emoji_id=5334544901428229844
        )
        if config_dict["SHOW_MEDIAINFO"]:
            mediainfo = "<emoji id=5206607081334906820>✔️</emoji> 𝐅ᴏʀᴄᴇ"
        save_mode = "𝐒ᴀᴠᴇ 𝐀s 𝐃ᴜᴍᴘ" if user_dict.get("save_mode") else "𝐒ᴀᴠᴇ 𝐀s 𝐁ᴏᴛ𝐏ᴍ"
        buttons.ibutton(
            " 𝐒ᴀᴠᴇ 𝐀s 𝐁ᴏᴛ𝐏ᴍ" if save_mode == "𝐒ᴀᴠᴇ 𝐀s 𝐃ᴜᴍᴘ" else " 𝐒ᴀᴠᴇ 𝐀s 𝐃ᴜᴍᴘ",
            f"userset {user_id} save_mode",
            icon_custom_emoji_id=5443127283898405358
        )
        dailytl = config_dict["DAILY_TASK_LIMIT"] or "∞"
        dailytas = (
            user_dict.get("dly_tasks")[1]
            if user_dict
            and user_dict.get("dly_tasks")
            and user_id != OWNER_ID
            and config_dict["DAILY_TASK_LIMIT"]
            else config_dict["DAILY_TASK_LIMIT"] or "️∞" if user_id != OWNER_ID else "∞"
        )
        if user_dict.get("dly_tasks", False):
            t = str(datetime.now() - user_dict["dly_tasks"][0]).split(":")
            lastused = f"{t[0]}h {t[1]}m {t[2].split('.')[0]}s ago"
        else:
            lastused = "𝐁ᴏᴛ 𝐍ᴏᴛ 𝐔sᴇᴅ ʏᴇᴛ.."

        text = BotTheme(
            "UNIVERSAL",
            NAME=name,
            YT=_pesc(ytopt),
            DT=f"{dailytas} / {dailytl}",
            LAST_USED=lastused,
            BOT_PM=bot_pm,
            MEDIAINFO=mediainfo,
            SAVE_MODE=save_mode,
            USESS=u_sess,
        )
        buttons.ibutton(" 𝐁ᴀᴄᴋ", f"userset {user_id} back", "footer", icon_custom_emoji_id=5416117059207572332)
        buttons.ibutton(" 𝐂ʟᴏsᴇ", f"userset {user_id} close", "footer", icon_custom_emoji_id=5447644880824181073)
        button = buttons.build_menu(2)
    elif key == "mirror":
        buttons.ibutton(
            "☁️ 𝐆ᴅʀɪᴠᴇ 𝐓ᴏᴏʟs",
            f"userset {user_id} gdrive_tools",
            icon_custom_emoji_id=5224450179368767019,
        )
        buttons.ibutton(
            "🚀 𝐃𝐃𝐋 𝐒ᴇʀᴠᴇʀs",
            f"userset {user_id} ddl_servers",
            icon_custom_emoji_id=5193177581888755275,
        )
        dailytlup = (
            get_readable_file_size(config_dict["DAILY_MIRROR_LIMIT"] * 1024**3)
            if config_dict["DAILY_MIRROR_LIMIT"]
            else "∞"
        )
        dailyup = (
            get_readable_file_size(await getdailytasks(user_id, check_mirror=True))
            if config_dict["DAILY_MIRROR_LIMIT"] and user_id != OWNER_ID
            else "️∞"
        )
        text = BotTheme(
            "MIRROR",
            NAME=name,
            DM=f"{dailyup} / {dailytlup}",
        )

        buttons.ibutton("🔙 𝐁ᴀᴄᴋ", f"userset {user_id} back", "footer", icon_custom_emoji_id=5416117059207572332)
        buttons.ibutton("✖️ 𝐂ʟᴏsᴇ", f"userset {user_id} close", "footer", icon_custom_emoji_id=5447644880824181073)
        button = buttons.build_menu(2)
    elif key == "gdrive_tools":
        token_path = f"tokens/{user_id}.pickle"
        token_exists = await aiopath.exists(token_path)
        gdrive_id = user_dict.get("GDRIVE_ID") or config_dict.get("GDRIVE_ID") or "None"
        index_url = user_dict.get("INDEX_URL")
        if index_url is None:
            index_url = config_dict.get("INDEX_URL") or "None"
        stop_duplicate = _setting_bool(
            user_dict.get("STOP_DUPLICATE", config_dict.get("STOP_DUPLICATE", False))
        )
        drive_categories = user_dict.get("DRIVE_CAT") or {}
        category_lines = [
            f"┎ <emoji id=5190806721286657692>🗂️</emoji> "
            f"<b>𝐃ᴇғᴀᴜʟᴛ 𝐆ᴅʀɪᴠᴇ</b> : <code>{escape(str(gdrive_id))}</code>"
        ]
        if index_url != "None":
            category_lines[0] += f" | <code>{escape(str(index_url))}</code>"
        if isinstance(drive_categories, dict):
            for category_name, category in drive_categories.items():
                if isinstance(category, dict):
                    category_id = category.get("drive_id", "")
                    category_index = category.get("index_link", "")
                else:
                    category_id, _, category_index = str(category).partition("|")
                index_part = (
                    f" | <code>{escape(str(category_index))}</code>"
                    if category_index
                    else ""
                )
                category_lines.append(
                    f"┠ <emoji id=5379763379953803263>📁</emoji> "
                    f"<b>{escape(str(category_name))}</b> : "
                    f"<code>{escape(str(category_id))}</code>{index_part}"
                )

        buttons.ibutton(
            "📁 𝐔sᴇʀ 𝐃ʀɪᴠᴇ 𝐂ᴀᴛᴇɢᴏʀɪᴇs",
            f"userset {user_id} gdrive_menu DRIVE_CAT",
            "header",
            icon_custom_emoji_id=5190806721286657692,
        )
        buttons.ibutton(
            "🗂️ 𝐃ᴇғᴀᴜʟᴛ 𝐆ᴅʀɪᴠᴇ 𝐈𝐃",
            f"userset {user_id} gdrive_menu GDRIVE_ID",
            "f_body",
            icon_custom_emoji_id=5224450179368767019,
        )
        buttons.ibutton(
            "🔗 𝐃ᴇғᴀᴜʟᴛ 𝐈ɴᴅᴇx 𝐔𝐑𝐋",
            f"userset {user_id} gdrive_menu INDEX_URL",
            "f_body",
            icon_custom_emoji_id=5271604874419647061,
        )
        buttons.ibutton(
            "🗑️ 𝐑ᴇᴍᴏᴠᴇ 𝐭ᴏᴋᴇɴ.ᴘɪᴄᴋʟᴇ"
            if token_exists
            else "🔐 𝐔ᴘʟᴏᴀᴅ 𝐭ᴏᴋᴇɴ.ᴘɪᴄᴋʟᴇ",
            (
                f"userset {user_id} gdrive_remove TOKEN_PICKLE"
                if token_exists
                else f"userset {user_id} gdrive_file TOKEN_PICKLE"
            ),
            icon_custom_emoji_id=5197288647275071607,
        )
        buttons.ibutton(
            "🛡️ 𝐃ɪsᴀʙʟᴇ 𝐒ᴛᴏᴘ 𝐃ᴜᴘʟɪᴄᴀᴛᴇ"
            if stop_duplicate
            else "🛡️ 𝐄ɴᴀʙʟᴇ 𝐒ᴛᴏᴘ 𝐃ᴜᴘʟɪᴄᴀᴛᴇ",
            f"userset {user_id} gdrive_toggle STOP_DUPLICATE",
            icon_custom_emoji_id=5427168083074628963,
        )
        buttons.ibutton(
            "🔙 𝐁ᴀᴄᴋ",
            f"userset {user_id} mirror",
            "footer",
            icon_custom_emoji_id=5416117059207572332,
        )
        buttons.ibutton(
            "✖️ 𝐂ʟᴏsᴇ",
            f"userset {user_id} close",
            "footer",
            icon_custom_emoji_id=5447644880824181073,
        )
        joined_categories = "\n   ".join(category_lines)
        stop_status = f"{_TICK} 𝐄ɴᴀʙʟᴇᴅ" if stop_duplicate else f"{_CROSS} 𝐃ɪsᴀʙʟᴇᴅ"
        token_status = f"{_TICK} 𝐑ᴇᴀᴅʏ" if token_exists else f"{_CROSS} 𝐍ᴏᴛ 𝐒ᴇᴛ"
        text = f"""💠 <b><u>𝐆ᴅʀɪᴠᴇ 𝐓ᴏᴏʟs 𝐒ᴇᴛᴛɪɴɢs : {name}</u></b>

┎ <emoji id=5190806721286657692>🗂️</emoji> <b>𝐃ᴇғᴀᴜʟᴛ 𝐆ᴅʀɪᴠᴇ 𝐈𝐃</b> : <code>{escape(str(gdrive_id))}</code>
┠ <emoji id=5271604874419647061>🔗</emoji> <b>𝐃ᴇғᴀᴜʟᴛ 𝐈ɴᴅᴇx 𝐔𝐑𝐋</b> : <code>{escape(str(index_url))}</code>
┠ <emoji id=5445284980978621387>🛡️</emoji> <b>𝐒ᴛᴏᴘ 𝐃ᴜᴘʟɪᴄᴀᴛᴇ</b> : {stop_status}
┠ <emoji id=5291873529464122510>🔐</emoji> <b>𝐭ᴏᴋᴇɴ.ᴘɪᴄᴋʟᴇ</b> : {token_status}

┠ <emoji id=5379748618268510153>📁</emoji> <b>𝐃ʀɪᴠᴇ 𝐂ᴀᴛᴇɢᴏʀɪᴇs</b> :
{joined_categories}

<i>💡 𝐒ᴇʟᴇᴄᴛ ᴀɴ ᴏᴘᴛɪᴏɴ ʙᴇʟᴏᴡ ᴛᴏ ᴜᴘᴅᴀᴛᴇ ʏᴏᴜʀ 𝐆ᴅʀɪᴠᴇ ᴘʀᴇғᴇʀᴇɴᴄᴇs.</i>"""
        button = buttons.build_menu(1, fb_cols=2, f_cols=2)
    elif key == "leech":
        if (
            user_dict.get("as_doc", False)
            or "as_doc" not in user_dict
            and config_dict["AS_DOCUMENT"]
        ):
            ltype = "𝐃ᴏᴄᴜᴍᴇɴᴛ"
            buttons.ibutton("𝐒ᴇɴᴅ 𝐀s 𝐌ᴇᴅɪᴀ", f"userset {user_id} doc", icon_custom_emoji_id=5445355530111437729)
        else:
            ltype = "𝐌ᴇᴅɪᴀ"
            buttons.ibutton("𝐒ᴇɴᴅ 𝐀s 𝐃ᴏᴄᴜᴍᴇɴᴛ", f"userset {user_id} doc", icon_custom_emoji_id=5445355530111437729)

        dailytlle = (
            get_readable_file_size(config_dict["DAILY_LEECH_LIMIT"] * 1024**3)
            if config_dict["DAILY_LEECH_LIMIT"]
            else "️∞"
        )
        dailyll = (
            get_readable_file_size(await getdailytasks(user_id, check_leech=True))
            if config_dict["DAILY_LEECH_LIMIT"] and user_id != OWNER_ID
            else "∞"
        )

        thumbmsg = "<emoji id=5206607081334906820>✔️</emoji>" if await aiopath.exists(thumbpath) else "<emoji id=5210952531676504517>❌</emoji> 𝐍ᴏᴛ 𝐒ᴇᴛ"
        buttons.ibutton(
            f"{'' if thumbmsg == '<emoji id=5206607081334906820>✔️</emoji>' else ''} 𝐓ʜᴜᴍʙɴᴀɪʟ",
            f"userset {user_id} thumb",
            icon_custom_emoji_id=5210956306952758910
        )

        split_size = (
            get_readable_file_size(config_dict["LEECH_SPLIT_SIZE"]) + " (𝐃ᴇғᴀᴜʟᴛ)"
            if user_dict.get("split_size", "") == ""
            else get_readable_file_size(user_dict["split_size"])
        )
        equal_splits = (
            "<emoji id=5206607081334906820>✔️</emoji>"
            if user_dict.get("equal_splits", config_dict.get("EQUAL_SPLITS"))
            else "<emoji id=5210952531676504517>❌</emoji>"
        )
        media_group = (
            "<emoji id=5206607081334906820>✔️</emoji>"
            if user_dict.get("media_group", config_dict.get("MEDIA_GROUP"))
            else "<emoji id=5210952531676504517>❌</emoji>"
        )
        buttons.ibutton(
            f"{'' if user_dict.get('split_size') else ''} 𝐋ᴇᴇᴄʜ 𝐒ᴘʟɪᴛs",
            f"userset {user_id} split_size",
            icon_custom_emoji_id=5190806721286657692
        )

        lcaption = (
            "<emoji id=5210952531676504517>❌</emoji>"
            if (
                val := user_dict.get(
                    "lcaption", config_dict.get("LEECH_FILENAME_CAPTION", "")
                )
            )
            == ""
            else val
        )
        buttons.ibutton(
            f"{'' if lcaption != '<emoji id=5210952531676504517>❌</emoji>' else ''} 𝐋ᴇᴇᴄʜ 𝐂ᴀᴘᴛɪᴏɴ",
            f"userset {user_id} lcaption",
            icon_custom_emoji_id=5334544901428229844
        )

        lprefix = (
            "<emoji id=5210952531676504517>❌</emoji>"
            if (
                val := user_dict.get(
                    "lprefix", config_dict.get("LEECH_FILENAME_PREFIX", "")
                )
            )
            == ""
            else val
        )
        buttons.ibutton(
            f"{'' if lprefix != '<emoji id=5210952531676504517>❌</emoji>' else ''} 𝐋ᴇᴇᴄʜ 𝐏ʀᴇғɪx",
            f"userset {user_id} lprefix",
            icon_custom_emoji_id=5271604874419647061
        )

        lsuffix = (
            "<emoji id=5210952531676504517>❌</emoji>"
            if (
                val := user_dict.get(
                    "lsuffix", config_dict.get("LEECH_FILENAME_SUFFIX", "")
                )
            )
            == ""
            else val
        )
        buttons.ibutton(
            f"{'' if lsuffix != '<emoji id=5210952531676504517>❌</emoji>' else ''} 𝐋ᴇᴇᴄʜ 𝐒ᴜғғɪx",
            f"userset {user_id} lsuffix",
            icon_custom_emoji_id=5397916757333654639
        )

        lremname = (
            "<emoji id=5210952531676504517>❌</emoji>"
            if (
                val := user_dict.get(
                    "lremname", config_dict.get("LEECH_FILENAME_REMNAME", "")
                )
            )
            == ""
            else val
        )
        buttons.ibutton(
            f"{'' if lremname != '<emoji id=5210952531676504517>❌</emoji>' else ''} 𝐋ᴇᴇᴄʜ 𝐑ᴇᴍɴᴀᴍᴇ",
            f"userset {user_id} lremname",
            icon_custom_emoji_id=5429651785352501917
        )

        buttons.ibutton(
            " 𝐋ᴇᴇᴄʜ 𝐃ᴜᴍᴘ",
            f"userset {user_id} ldump",
            icon_custom_emoji_id=5445355530111437729
        )
        ldump = "<emoji id=5210952531676504517>❌</emoji>" if (val := user_dict.get("ldump", "")) == "" else len(val)

        lmeta = (
            "<emoji id=5210952531676504517>❌</emoji>"
            if (val := user_dict.get("lmeta", config_dict.get("METADATA", ""))) == ""
            else val
        )
        buttons.ibutton(
            f"{'' if lmeta != '<emoji id=5210952531676504517>❌</emoji>' else ''} 𝐌ᴇᴛᴀᴅᴀᴛᴀ",
            f"userset {user_id} lmeta",
            icon_custom_emoji_id=5294339927318739359
        )

        _ar_mode = user_dict.get("auto_rename", False)
        if _ar_mode is True:
            _ar_mode = "auto"
        _ar_label = (
            " 𝐀ᴜᴛᴏ 𝐑ᴇɴᴀᴍᴇ " if _ar_mode == "auto" else
            " 𝐀ᴜᴛᴏ 𝐑ᴇɴᴀᴍᴇ " if _ar_mode == "custom" else
            " 𝐀ᴜᴛᴏ 𝐑ᴇɴᴀᴍᴇ"
        )
        buttons.ibutton(_ar_label, f"userset {user_id} auto_rename", icon_custom_emoji_id=5341715473882955310)

        auto_poster = user_dict.get("auto_poster", False)
        buttons.ibutton(
            f"{'' if auto_poster else ''}  𝐀ᴜᴛᴏ 𝐏ᴏsᴛᴇʀ",
            f"userset {user_id} auto_poster",
            icon_custom_emoji_id=5294339927318739359
        )

        buttons.ibutton(
            " 𝐌ᴇʀɢᴇ 𝐕ɪᴅᴇᴏ",
            f"userset {user_id} merge_video_menu",
            icon_custom_emoji_id=5449683594425410231
        )

        _ar_display = (
            " 𝐀ᴜᴛᴏ"    if _ar_mode == "auto"   else
            " 𝐂ᴜsᴛᴏᴍ" if _ar_mode == "custom" else
            "<emoji id=5210952531676504517>❌</emoji>"
        )
        text = BotTheme(
            "LEECH",
            NAME=name,
            DL=f"{dailyll} / {dailytlle}",
            LTYPE=ltype,
            THUMB=thumbmsg,
            SPLIT_SIZE=split_size,
            EQUAL_SPLIT=equal_splits,
            MEDIA_GROUP=media_group,
            LCAPTION=_pesc(lcaption),
            LPREFIX=_pesc(lprefix),
            LSUFFIX=_pesc(lsuffix),
            LDUMP=ldump,
            LREMNAME=_pesc(lremname),
            LMETA=_pesc(lmeta),
            AUTO_RENAME=_ar_display,
            AUTO_POSTER="<emoji id=5206607081334906820>✔️</emoji>" if auto_poster else "<emoji id=5210952531676504517>❌</emoji>",
        )

        buttons.ibutton("𝐁ᴀᴄᴋ", f"userset {user_id} back", "footer", icon_custom_emoji_id=5416117059207572332)
        buttons.ibutton("𝐂ʟᴏsᴇ", f"userset {user_id} close", "footer", icon_custom_emoji_id=5447644880824181073)
        button = buttons.build_menu(2)
    elif key == "auto_rename":
        _ar_mode = user_dict.get("auto_rename", False)
        if _ar_mode is True:
            _ar_mode = "auto"
        _ar_fmt  = user_dict.get("auto_rename_fmt", "")
        _ar_fmt_preview = (
            f"<code>{escape(_ar_fmt[:80])}{'…' if len(_ar_fmt) > 80 else ''}</code>"
            if _ar_fmt else "<i>𝐍ᴏᴛ 𝐒ᴇᴛ</i>"
        )
        _mode_label = (
            " 𝐀ᴜᴛᴏ (𝐒ᴍᴀʀᴛ)" if _ar_mode == "auto"   else
            " 𝐂ᴜsᴛᴏᴍ 𝐅ᴏʀᴍᴀᴛ" if _ar_mode == "custom" else
            " 𝐎ғғ"
        )
        text = (
            f"⚙️ <b><u>𝐀ᴜᴛᴏ 𝐑ᴇɴᴀᴍᴇ 𝐒ᴇᴛᴛɪɴɢs</u></b>\n\n"
            f"➲ <b>𝐌ᴏᴅᴇ :</b> {_mode_label}\n"
            f"➲ <b>𝐂ᴜsᴛᴏᴍ 𝐅ᴏʀᴍᴀᴛ :</b> {_ar_fmt_preview}\n\n"
            f"<b> 𝐀ᴜᴛᴏ 𝐌ᴏᴅᴇ</b> — 𝐁ᴏᴛ ᴀᴜᴛᴏ-ᴅᴇᴛᴇᴄᴛs ᴛɪᴛʟᴇ, ʏᴇᴀʀ, ϙᴜᴀʟɪᴛʏ, ᴀᴜᴅɪᴏ & sᴜʙs ᴠɪᴀ ᴍᴇᴛᴀᴅᴀᴛᴀ.\n"
            f"<b> 𝐂ᴜsᴛᴏᴍ 𝐌ᴏᴅᴇ</b> — ʏᴏᴜ sᴇᴛ ʏᴏᴜʀ ᴏᴡɴ ᴛᴇᴍᴘʟᴀᴛᴇ ᴜsɪɴɢ ᴘʟᴀᴄᴇʜᴏʟᴅᴇʀs."
        )
        buttons.ibutton(
            f"{' ' if _ar_mode == 'auto' else ''} 𝐀ᴜᴛᴏ 𝐌ᴏᴅᴇ",
            f"userset {user_id} ar_auto",
            icon_custom_emoji_id=5341715473882955310
        )
        buttons.ibutton(
            f"{' ' if _ar_mode == 'custom' else ''} 𝐒ᴇᴛ 𝐂ᴜsᴛᴏᴍ 𝐅ᴏʀᴍᴀᴛ",
            f"userset {user_id} ar_fmt",
            icon_custom_emoji_id=5334544901428229844
        )
        if _ar_mode:
            buttons.ibutton("𝐃ɪsᴀʙʟᴇ", f"userset {user_id} ar_off", icon_custom_emoji_id=5447644880824181073)
        if _ar_fmt:
            buttons.ibutton(" 𝐂ʟᴇᴀʀ 𝐅ᴏʀᴍᴀᴛ", f"userset {user_id} dar_fmt", icon_custom_emoji_id=5445267414562389170)
        buttons.ibutton("𝐁ᴀᴄᴋ", f"userset {user_id} back leech", "footer", icon_custom_emoji_id=5416117059207572332)
        buttons.ibutton("𝐂ʟᴏsᴇ", f"userset {user_id} close", "footer", icon_custom_emoji_id=5447644880824181073)
        button = buttons.build_menu(2)
    elif key == "merge_video_menu":
        merge_cmd  = BotCommands.StartMergeCommand[0]
        merge_cmd2 = BotCommands.StartMergeCommand[1]
        text = (
            f"🎞️ <b><u>𝐌ᴇʀɢᴇ 𝐕ɪᴅᴇᴏ</u></b>\n\n"
            f"<b>📋 𝐌ᴇʀɢᴇ 𝐓ᴏᴏʟ 𝐂ᴏᴍᴍᴀɴᴅ :</b>\n"
            f"  ➤ <code>/{merge_cmd}</code>\n"
            f"    <i>𝐎ʀ ᴀʟᴛᴇʀɴᴀᴛɪᴠᴇ: <code>/{merge_cmd2}</code></i>\n\n"
            f"<b>ℹ️ 𝐇ᴏᴡ 𝐈ᴛ 𝐖ᴏʀᴋs :</b>\n"
            f"  • ᴜsᴇ /<code>{merge_cmd}</code> ᴛᴏ ᴏᴘᴇɴ ᴛʜᴇ ᴍᴇʀɢᴇ ᴛᴏᴏʟ ᴍᴇɴᴜ\n"
            f"  • ϙᴜᴇᴜᴇ ᴠɪᴅᴇᴏs/ʟɪɴᴋs ᴛʜᴇɴ ᴄʟɪᴄᴋ 🔀 𝐌ᴇʀɢᴇ 𝐍ᴏᴡ"
        )
        buttons.ibutton(" 𝐁ᴀᴄᴋ", f"userset {user_id} mv_back", "footer", icon_custom_emoji_id=5416117059207572332)
        button = buttons.build_menu(2)
    elif key == "ddl_servers":
        ddl_serv, serv_list = 0, []
        if ddl_dict := user_dict.get("ddl_servers", False):
            for serv, (enabled, _) in ddl_dict.items():
                if enabled:
                    serv_list.append(serv)
                    ddl_serv += 1
        text = (
            f"㊂ <b><u>{fname_dict[key]} 𝐒ᴇᴛᴛɪɴɢs :</u></b>\n\n"
            f"➲ <b>𝐄ɴᴀʙʟᴇᴅ 𝐃ᴅʟ 𝐒ᴇʀᴠᴇʀ(s) :</b> <i>{ddl_serv}</i>\n\n"
            f"➲ <b>𝐃ᴇsᴄʀɪᴘᴛɪᴏɴ :</b> <i>{desp_dict[key][0]}</i>"
        )
        for btn in ["gofile", "streamtape"]:
            buttons.ibutton(
                f"{'' if btn in serv_list else ''} {fname_dict[btn]}",
                f"userset {user_id} {btn}",
                icon_custom_emoji_id=5193177581888755275
            )
        buttons.ibutton("𝐁ᴀᴄᴋ", f"userset {user_id} back mirror", "footer", icon_custom_emoji_id=5416117059207572332)
        buttons.ibutton("𝐂ʟᴏsᴇ", f"userset {user_id} close", "footer", icon_custom_emoji_id=5447644880824181073)
        button = buttons.build_menu(2)
    elif edit_type:
        text = f"㊂ <b><u>{fname_dict[key]} 𝐒ᴇᴛᴛɪɴɢs :</u></b>\n\n"
        if key == "thumb":
            set_exist = await aiopath.exists(thumbpath)
            text += f"➲ <b>𝐂ᴜsᴛᴏᴍ 𝐓ʜᴜᴍʙɴᴀɪʟ :</b> <i>{'' if set_exist else '𝐍ᴏᴛ '} 𝐄xɪsᴛs</i>\n\n"
        elif key == "yt_opt":
            set_exist = (
                "𝐍ᴏᴛ 𝐄xɪsᴛs"
                if (
                    val := user_dict.get(
                        "yt_opt", config_dict.get("YT_DLP_OPTIONS", "")
                    )
                )
                == ""
                else val
            )
            text += f"➲ <b>𝐘ᴛ-𝐃ʟᴘ 𝐎ᴘᴛɪᴏɴs :</b> {_pesc(set_exist)}\n\n"
        elif key == "usess":
            set_exist = "<emoji id=5206607081334906820>✔️</emoji>" if user_dict.get("usess") else "<emoji id=5210952531676504517>❌</emoji>"
            text += f"➲ <b>{fname_dict[key]} :</b> {set_exist}\n➲ <b>𝐄ɴᴄʀʏᴘᴛɪᴏɴ :</b> {'🔐' if set_exist == _TICK else '🔓'}\n\n"
        elif key == "split_size":
            set_exist = (
                get_readable_file_size(config_dict["LEECH_SPLIT_SIZE"]) + " (𝐃ᴇғᴀᴜʟᴛ)"
                if user_dict.get("split_size", "") == ""
                else get_readable_file_size(user_dict["split_size"])
            )
            text += f"➲ <b>𝐋ᴇᴇᴄʜ 𝐒ᴘʟɪᴛ 𝐒ɪᴢᴇ :</b> <i>{set_exist}</i>\n\n"
            if user_dict.get("equal_splits", False) or (
                "equal_splits" not in user_dict and config_dict["EQUAL_SPLITS"]
            ):
                buttons.ibutton(
                    "𝐃ɪsᴀʙʟᴇ 𝐄ϙᴜᴀʟ 𝐒ᴘʟɪᴛs", f"userset {user_id} esplits", "header", icon_custom_emoji_id=5190806721286657692
                )
            else:
                buttons.ibutton(
                    "𝐄ɴᴀʙʟᴇ 𝐄ϙᴜᴀʟ 𝐒ᴘʟɪᴛs", f"userset {user_id} esplits", "header", icon_custom_emoji_id=5190806721286657692
                )
            if user_dict.get("media_group", False) or (
                "media_group" not in user_dict and config_dict["MEDIA_GROUP"]
            ):
                buttons.ibutton(
                    "𝐃ɪsᴀʙʟᴇ 𝐌ᴇᴅɪᴀ 𝐆ʀᴏᴜᴘ", f"userset {user_id} mgroup", "header", icon_custom_emoji_id=5190806721286657692
                )
            else:
                buttons.ibutton(
                    "𝐄ɴᴀʙʟᴇ 𝐌ᴇᴅɪᴀ 𝐆ʀᴏᴜᴘ", f"userset {user_id} mgroup", "header", icon_custom_emoji_id=5190806721286657692
                )
        elif key == "ar_fmt":
            _ar_fmt_val = user_dict.get("auto_rename_fmt", "")
            set_exist   = escape(_ar_fmt_val) if _ar_fmt_val else "𝐍ᴏᴛ 𝐄xɪsᴛs"
            _fmt_display = f"<code>{set_exist}</code>" if _ar_fmt_val else f"<i>{set_exist}</i>"
            text = (
                f"⚙️ <b><u>𝐀ᴜᴛᴏ 𝐑ᴇɴᴀᴍᴇ 𝐅ᴏʀᴍᴀᴛ 𝐒ᴇᴛᴛɪɴɢs</u></b>\n\n"
                f"➲ <b>𝐂ᴜʀʀᴇɴᴛ 𝐅ᴏʀᴍᴀᴛ :</b>\n{_fmt_display}\n\n"
            )
        elif key in ["lprefix", "lremname", "lsuffix", "lcaption", "ldump", "lmeta"]:
            set_exist = (
                "𝐍ᴏᴛ 𝐄xɪsᴛs"
                if (
                    val := user_dict.get(
                        key, config_dict.get(f"LEECH_FILENAME_{key[1:].upper()}", "")
                    )
                )
                == ""
                else val
            )
            if set_exist != "𝐍ᴏᴛ 𝐄xɪsᴛs" and key == "ldump":
                set_exist = "\n\n" + "\n".join(
                    [
                        f"{index}. <b>{dump}</b> : <code>{ids}</code>"
                        for index, (dump, ids) in enumerate(val.items(), start=1)
                    ]
                )
            text += f"➲ <b>𝐋ᴇᴇᴄʜ 𝐅ɪʟᴇɴᴀᴍᴇ {fname_dict[key]} :</b> {set_exist}\n\n"
        elif key in ["mprefix", "mremname", "msuffix"]:
            set_exist = (
                "𝐍ᴏᴛ 𝐄xɪsᴛs"
                if (
                    val := user_dict.get(
                        key, config_dict.get(f"MIRROR_FILENAME_{key[1:].upper()}", "")
                    )
                )
                == ""
                else val
            )
            text += f"➲ <b>𝐌ɪʀʀᴏʀ 𝐅ɪʟᴇɴᴀᴍᴇ {fname_dict[key]} :</b> {set_exist}\n\n"
        elif key in ["gofile", "streamtape"]:
            set_exist = (
                "<emoji id=5206607081334906820>✔️</emoji>"
                if key in (ddl_dict := user_dict.get("ddl_servers", {}))
                and ddl_dict[key][1]
                and ddl_dict[key][1] != ""
                else "<emoji id=5210952531676504517>❌</emoji>"
            )
            ddl_mode = (
                "<emoji id=5206607081334906820>✔️</emoji>"
                if key in (ddl_dict := user_dict.get("ddl_servers", {}))
                and ddl_dict[key][0]
                else "<emoji id=5210952531676504517>❌</emoji>"
            )
            text = (
                f"➲ <b>𝐔ᴘʟᴏᴀᴅ {fname_dict[key]} :</b> {ddl_mode}\n"
                f"➲ <b>{fname_dict[key]}'s 𝐀ᴘɪ 𝐊ᴇʏ :</b> {set_exist}\n\n"
            )
            buttons.ibutton(
                "𝐃ɪsᴀʙʟᴇ 𝐃ᴅʟ" if ddl_mode == "<emoji id=5206607081334906820>✔️</emoji>" else "𝐄ɴᴀʙʟᴇ 𝐃ᴅʟ",
                f"userset {user_id} s{key}",
                "header",
                icon_custom_emoji_id=5193177581888755275
            )
        elif key == "user_tds":
            set_exist = len(val) if (val := user_dict.get(key, False)) else "<emoji id=5210952531676504517>❌</emoji>"
            tds_mode = "<emoji id=5206607081334906820>✔️</emoji>" if user_dict.get("td_mode", False) else "<emoji id=5210952531676504517>❌</emoji>"
            buttons.ibutton(
                "𝐃ɪsᴀʙʟᴇ 𝐔sᴇʀ𝐓ᴅs" if tds_mode == "<emoji id=5206607081334906820>✔️</emoji>" else "𝐄ɴᴀʙʟᴇ 𝐔sᴇʀ𝐓ᴅs",
                f"userset {user_id} td_mode",
                "header",
                icon_custom_emoji_id=5427168083074628963
            )
            if not config_dict["USER_TD_MODE"]:
                tds_mode = "<emoji id=5210952531676504517>❌</emoji> 𝐅ᴏʀᴄᴇ"
            text += f"➲ <b>𝐔sᴇʀ 𝐓ᴅ 𝐌ᴏᴅᴇ :</b> {tds_mode}\n"
            text += f"➲ <b>{fname_dict[key]} :</b> {set_exist}\n\n"
        else:
            return
        text += f"➲ <b>𝐃ᴇsᴄʀɪᴘᴛɪᴏɴ :</b> <i>{desp_dict[key][0]}</i>"
        if not edit_mode:
            buttons.ibutton(
                (
                    f"𝐂ʜᴀɴɢᴇ {fname_dict[key]}"
                    if set_exist
                    and set_exist not in ["𝐄xɪsᴛs", "𝐍ᴏᴛ 𝐄xɪsᴛs"]
                    and (
                        set_exist
                        != get_readable_file_size(config_dict["LEECH_SPLIT_SIZE"])
                        + " (𝐃ᴇғᴀᴜʟᴛ)"
                    )
                    else f"𝐒ᴇᴛ {fname_dict[key]}"
                ),
                f"userset {user_id} {key} edit",
                icon_custom_emoji_id=5206607081334906820
            )
        else:
            text += "\n\n" + desp_dict[key][1]
            buttons.ibutton("𝐒ᴛᴏᴘ 𝐂ʜᴀɴɢᴇ", f"userset {user_id} {key}", icon_custom_emoji_id=5447644880824181073)
        if (
            set_exist
            and set_exist not in ["𝐄xɪsᴛs", "𝐍ᴏᴛ 𝐄xɪsᴛs"]
            and (
                set_exist
                != get_readable_file_size(config_dict["LEECH_SPLIT_SIZE"])
                + " (𝐃ᴇғᴀᴜʟᴛ)"
            )
        ):
            if key == "thumb":
                buttons.ibutton("𝐕ɪᴇᴡ 𝐓ʜᴜᴍʙɴᴀɪʟ", f"userset {user_id} vthumb", "header", icon_custom_emoji_id=5210956306952758910)
            elif key == "user_tds":
                buttons.ibutton("𝐒ʜᴏᴡ 𝐔sᴇʀ𝐓ᴅs", f"userset {user_id} show_tds", "header", icon_custom_emoji_id=5210956306952758910)
            buttons.ibutton("↻ 𝐃ᴇʟᴇᴛᴇ", f"userset {user_id} d{key}", icon_custom_emoji_id=5445267414562389170)
        buttons.ibutton("𝐁ᴀᴄᴋ", f"userset {user_id} back {edit_type}", "footer", icon_custom_emoji_id=5416117059207572332)
        buttons.ibutton("𝐂ʟᴏsᴇ", f"userset {user_id} close", "footer", icon_custom_emoji_id=5447644880824181073)
        button = buttons.build_menu(2)
    return text, button

async def update_user_settings(
    query, key=None, edit_type=None, edit_mode=None, msg=None, sdirect=False
):
    from_user = msg.from_user if sdirect else query.from_user
    msg, button = await get_user_settings(from_user, key, edit_type, edit_mode)
    photo = await _usetting_photo(from_user.id)
    await editMessage(query if sdirect else query.message, msg, button, photo)


async def user_settings(client, message):
    if len(message.command) > 1 and (
        message.command[1] == "-s" or message.command[1] == "-set"
    ):
        set_arg = message.command[2].strip() if len(message.command) > 2 else None
        msg = await sendMessage(message, "<i>𝐅ᴇᴛᴄʜɪɴɢ 𝐒ᴇᴛᴛɪɴɢs...</i>", photo="IMAGES")
        if set_arg and (reply_to := message.reply_to_message):
            if message.from_user.id != reply_to.from_user.id:
                return await editMessage(
                    msg,
                    "<i>𝐑ᴇᴘʟʏ 𝐓ᴏ 𝐘ᴏᴜʀ 𝐎ᴡɴ 𝐌ᴇssᴀɢᴇ 𝐅ᴏʀ 𝐒ᴇᴛᴛɪɴɢ 𝐕ɪᴀ 𝐀ʀɢs 𝐃ɪʀᴇᴄᴛʟʏ</i>",
                )
            if (
                set_arg
                in [
                    "lprefix",
                    "lsuffix",
                    "lremname",
                    "lcaption",
                    "ldump",
                    "yt_opt",
                    "lmeta",
                ]
                and reply_to.text
            ):
                return await set_custom(client, reply_to, msg, set_arg, True)
            elif set_arg == "thumb" and reply_to.media:
                return await set_thumb(client, reply_to, msg, set_arg, True)
        await editMessage(
            msg,
            """㊂ <b><u>𝐀ᴠᴀɪʟᴀʙʟᴇ 𝐅ʟᴀɢs :</u></b>
>> 𝐑ᴇᴘʟʏ 𝐓ᴏ 𝐓ʜᴇ 𝐕ᴀʟᴜᴇ 𝐖ɪᴛʜ 𝐀ᴘᴘʀᴏᴘʀɪᴀᴛᴇ 𝐀ʀɢ 𝐑ᴇsᴘᴇᴄᴛɪᴠᴇʟʏ 𝐓ᴏ 𝐒ᴇᴛ 𝐃ɪʀᴇᴄᴛʟʏ 𝐖ɪᴛʜᴏᴜᴛ 𝐎ᴘᴇɴɪɴɢ 𝐔𝐒ᴇᴛ.

➲ <b>𝐂ᴜsᴛᴏᴍ 𝐓ʜᴜᴍʙɴᴀɪʟ :</b>
    /cmd -s thumb
➲ <b>𝐋ᴇᴇᴄʜ 𝐅ɪʟᴇɴᴀᴍᴇ 𝐏ʀᴇғɪx :</b>
    /cmd -s lprefix
➲ <b>𝐋ᴇᴇᴄʜ 𝐅ɪʟᴇɴᴀᴍᴇ 𝐒ᴜғғɪx :</b>
    /cmd -s lsuffix
➲ <b>𝐋ᴇᴇᴄʜ 𝐅ɪʟᴇɴᴀᴍᴇ 𝐑ᴇᴍɴᴀᴍᴇ :</b>
    /cmd -s lremname
➲ <b>𝐋ᴇᴇᴄʜ 𝐅ɪʟᴇɴᴀᴍᴇ 𝐂ᴀᴘᴛɪᴏɴ :</b>
    /cmd -s lcaption
➲ <b>𝐋ᴇᴇᴄʜ 𝐌ᴇᴛᴀᴅᴀᴛᴀ 𝐓ᴇxᴛ :</b>
    /cmd -s lmeta
➲ <b>𝐘ᴛ-𝐃ʟᴘ 𝐎ᴘᴛɪᴏɴs :</b>
    /cmd -s yt_opt
➲ <b>𝐋ᴇᴇᴄʜ 𝐔sᴇʀ 𝐃ᴜᴍᴘ :</b>
    /cmd -s ldump""",
        )
    else:
        from_user = message.from_user
        handler_dict[from_user.id] = False
        msg, button = await get_user_settings(from_user)
        photo = await _usetting_photo(from_user.id)
        await sendMessage(message, msg, button, photo)

async def set_custom(client, message, pre_event, key, direct=False):
    user_id = message.from_user.id
    handler_dict[user_id] = False
    value = message.text
    return_key = "leech"
    n_key = key
    user_dict = user_data.get(user_id, {})
    if key == "ar_fmt":
        n_key = "auto_rename_fmt"
        update_user_ldata(user_id, "auto_rename_fmt", value)
        update_user_ldata(user_id, "auto_rename", "custom")
        await deleteMessage(message)
        await update_user_settings(pre_event, "ar_fmt", "auto_rename", msg=message, sdirect=direct)
        if DATABASE_URL:
            await DbManger().update_user_data(user_id)
        return
    elif key == "GDRIVE_ID":
        value = value.strip()
        if is_gdrive_link(value):
            try:
                value = GoogleDriveHelper.getIdFromUrl(value)
            except (IndexError, KeyError, ValueError):
                await sendMessage(message, "Invalid Google Drive link.")
                await update_user_settings(pre_event, "gdrive_tools")
                return
        if not value:
            await sendMessage(message, "Google Drive ID cannot be empty.")
            await update_user_settings(pre_event, "gdrive_tools")
            return
        return_key = "gdrive_tools"
    elif key == "INDEX_URL":
        value = value.strip().rstrip("/")
        return_key = "gdrive_tools"
    elif key == "DRIVE_CAT":
        try:
            parsed = literal_eval(value.strip())
            if not isinstance(parsed, dict):
                raise ValueError("It must be a dictionary.")
            categories = {}
            for category_name, category_value in parsed.items():
                category_name = str(category_name).strip()
                if not category_name:
                    raise ValueError("Category name cannot be empty.")
                if category_name.casefold() == "default":
                    raise ValueError('"Default" is reserved for the default Drive.')
                if isinstance(category_value, dict):
                    drive_id = str(category_value.get("drive_id", "")).strip()
                    index_link = str(category_value.get("index_link", "")).strip().rstrip("/")
                else:
                    parts = str(category_value).split("|", 1)
                    drive_id = parts[0].strip()
                    index_link = parts[1].strip().rstrip("/") if len(parts) > 1 else ""
                if is_gdrive_link(drive_id):
                    drive_id = GoogleDriveHelper.getIdFromUrl(drive_id)
                if not drive_id:
                    raise ValueError(f"Drive ID is missing for {category_name}.")
                categories[category_name] = {
                    "drive_id": drive_id,
                    "index_link": index_link,
                }
            value = categories
        except Exception as err:
            await sendMessage(message, f"Invalid Drive Categories: {err}")
            await update_user_settings(pre_event, "gdrive_tools")
            return
        return_key = "gdrive_tools"
    elif key in ["gofile", "streamtape"]:
        ddl_dict = user_dict.get("ddl_servers", {})
        mode, api = ddl_dict.get(key, [False, ""])
        if key == "gofile" and not await Gofile.is_goapi(value):
            value = ""
        ddl_dict[key] = [mode, value]
        value = ddl_dict
        n_key = "ddl_servers"
        return_key = "ddl_servers"
    elif key == "user_tds":
        user_tds = user_dict.get(key, {})
        for td_item in value.split("\n"):
            if td_item == "":
                continue
            split_ck = td_item.split()
            td_details = td_item.rsplit(
                maxsplit=(
                    2
                    if split_ck[-1].startswith("http")
                    and not is_gdrive_link(split_ck[-1])
                    else 1 if len(split_ck[-1]) > 15 else 0
                )
            )
            if td_details[0] in list(categories_dict.keys()):
                continue
            for title in list(user_tds.keys()):
                if td_details[0].casefold() == title.casefold():
                    del user_tds[title]
            if len(td_details) > 1:
                if is_gdrive_link(td_details[1].strip()):
                    td_details[1] = GoogleDriveHelper.getIdFromUrl(td_details[1])
                if await sync_to_async(
                    GoogleDriveHelper().getFolderData, td_details[1]
                ):
                    user_tds[td_details[0]] = {
                        "drive_id": td_details[1],
                        "index_link": (
                            td_details[2].rstrip("/") if len(td_details) > 2 else ""
                        ),
                    }
        value = user_tds
        return_key = "mirror"
    elif key == "ldump":
        ldumps = user_dict.get(key, {})
        for dump_item in value.split("\n"):
            if dump_item == "":
                continue
            dump_info = dump_item.rsplit(
                maxsplit=(1 if dump_item.split()[-1].startswith(("-100", "@")) else 0)
            )
            if dump_info[0] in list(ldumps.keys()):
                continue
            for title in list(ldumps.keys()):
                if dump_info[0].casefold() == title.casefold():
                    del ldumps[title]
            if len(dump_info) > 1 and (dump_chat := await chat_info(dump_info[1])):
                ldumps[dump_info[0]] = dump_chat.id
        value = ldumps
    elif key in ["yt_opt", "usess"]:
        if key == "usess":
            password = Fernet.generate_key()
            try:
                await deleteMessage(
                    await (
                        await sendCustomMsg(
                            message.from_user.id,
                            f"<u><b>𝐃ᴇᴄʀʏᴘᴛɪᴏɴ 𝐊ᴇʏ:</b></u> \n┃\n┃ <code>{password.decode()}</code>\n┃\n┖ <b>𝐍ᴏᴛᴇ:</b> <i>𝐊ᴇᴇᴘ ᴛʜɪs 𝐊ᴇʏ 𝐒ᴇᴄᴜʀᴇʟʏ, ᴛʜɪs ɪs ɴᴏᴛ 𝐒ᴛᴏʀᴇᴅ ɪɴ 𝐁ᴏᴛ ᴀɴᴅ 𝐀ᴄᴄᴇss 𝐊ᴇʏ ᴛᴏ ᴜsᴇ ʏᴏᴜʀ 𝐒ᴇssɪᴏɴ...</i>",
                        )
                    ).pin(both_sides=True)
                )
                encrypt_sess = Fernet(password).encrypt(value.encode())
                value = encrypt_sess.decode()
            except Exception:
                value = ""
        return_key = "universal"
    update_user_ldata(user_id, n_key, value)
    await deleteMessage(message)
    # GDrive fields use a dedicated settings screen.  Rendering the raw
    # field key here makes get_user_settings() treat it like a legacy
    # setting and look it up in fname_dict/desp_dict, which do not contain
    # GDRIVE_ID, INDEX_URL, or DRIVE_CAT.
    display_key = (
        "gdrive_tools"
        if key in {"GDRIVE_ID", "INDEX_URL", "DRIVE_CAT"}
        else key
    )
    await update_user_settings(
        pre_event, display_key, return_key, msg=message, sdirect=direct
    )
    if DATABASE_URL:
        await DbManger().update_user_data(user_id)


async def set_thumb(client, message, pre_event, key, direct=False):
    user_id = message.from_user.id
    handler_dict[user_id] = False
    path = "Thumbnails/"
    if not await aiopath.isdir(path):
        await mkdir(path)
    photo_dir = await message.download()
    des_dir = ospath.join(path, f"{user_id}.jpg")
    await sync_to_async(Image.open(photo_dir).convert("RGB").save, des_dir, "JPEG")
    await aioremove(photo_dir)
    update_user_ldata(user_id, "thumb", des_dir)
    await deleteMessage(message)
    await update_user_settings(pre_event, key, "leech", msg=message, sdirect=direct)
    if DATABASE_URL:
        await DbManger().update_user_doc(user_id, "thumb", des_dir)


async def add_token_pickle(client, message, pre_event):
    user_id = message.from_user.id
    handler_dict[user_id] = False
    token_dir = f"{getcwd()}/tokens"
    await makedirs(token_dir, exist_ok=True)
    token_path = ospath.join(token_dir, f"{user_id}.pickle")
    await message.download(file_name=token_path)
    update_user_ldata(user_id, "TOKEN_PICKLE", token_path)
    await deleteMessage(message)
    await update_user_settings(pre_event, "gdrive_tools")
    if DATABASE_URL:
        await DbManger().update_user_doc(user_id, "TOKEN_PICKLE", token_path)


async def add_drive_category(client, message, pre_event):
    user_id = message.from_user.id
    handler_dict[user_id] = False
    raw_value = message.text.strip()
    try:
        if ":" in raw_value:
            category_name, raw_value = raw_value.split(":", 1)
            category_name = category_name.strip()
            drive_id, _, index_link = raw_value.strip().partition("|")
        else:
            parts = raw_value.split(maxsplit=2)
            if len(parts) < 2:
                raise ValueError("Use: <name> <drive_id> [index_url]")
            category_name, drive_id = parts[:2]
            index_link = parts[2] if len(parts) == 3 else ""
        category_name = category_name.strip()
        drive_id = drive_id.strip()
        index_link = index_link.strip().rstrip("/")
        if not category_name or category_name.casefold() == "default":
            raise ValueError("Category name is empty or reserved.")
        if is_gdrive_link(drive_id):
            drive_id = GoogleDriveHelper.getIdFromUrl(drive_id)
        if not drive_id:
            raise ValueError("Drive ID is missing.")
        categories = user_data.get(user_id, {}).get("DRIVE_CAT", {}).copy()
        categories[category_name] = {
            "drive_id": drive_id,
            "index_link": index_link,
        }
        update_user_ldata(user_id, "DRIVE_CAT", categories)
        if DATABASE_URL:
            await DbManger().update_user_data(user_id)
        await deleteMessage(message)
    except Exception as err:
        await sendMessage(message, f"Invalid Drive Category: {err}")
    await update_user_settings(pre_event, "gdrive_tools")


async def remove_drive_category(client, message, pre_event):
    user_id = message.from_user.id
    handler_dict[user_id] = False
    category_name = message.text.strip().casefold()
    categories = user_data.get(user_id, {}).get("DRIVE_CAT", {}).copy()
    category_key = next(
        (key for key in categories if str(key).casefold() == category_name), None
    )
    if category_key is None:
        await sendMessage(message, "That Drive category was not found.")
    else:
        categories.pop(category_key)
        update_user_ldata(user_id, "DRIVE_CAT", categories)
        if DATABASE_URL:
            await DbManger().update_user_data(user_id)
        await deleteMessage(message)
    await update_user_settings(pre_event, "gdrive_tools")


async def leech_split_size(client, message, pre_event):
    user_id = message.from_user.id
    handler_dict[user_id] = False
    sdic = ["b", "kb", "mb", "gb"]
    value = message.text.strip()
    slice = -2 if value[-2].lower() in ["k", "m", "g"] else -1
    out = value[slice:].strip().lower()
    if out in sdic:
        value = min(
            (float(value[:slice].strip()) * 1024 ** sdic.index(out)), MAX_SPLIT_SIZE
        )
    update_user_ldata(user_id, "split_size", int(round(value)))
    await deleteMessage(message)
    await update_user_settings(pre_event, "split_size", "leech")
    if DATABASE_URL:
        await DbManger().update_user_data(user_id)


async def event_handler(client, query, pfunc, rfunc, photo=False, document=False):
    user_id = query.from_user.id
    handler_dict[user_id] = True
    start_time = time()

    async def event_filter(_, __, event):
        if photo:
            mtype = event.photo
        elif document:
            mtype = event.document
        else:
            mtype = event.text
        user = event.from_user or event.sender_chat
        return bool(
            user.id == user_id and event.chat.id == query.message.chat.id and mtype
        )

    handler = client.add_handler(
        MessageHandler(pfunc, filters=create(event_filter)), group=-1
    )
    while handler_dict[user_id]:
        await sleep(0.5)
        if time() - start_time > 60:
            handler_dict[user_id] = False
            await rfunc()
    client.remove_handler(*handler)


@new_thread
async def edit_user_settings(client, query):
    from_user = query.from_user
    user_id = from_user.id
    message = query.message
    data = query.data.split()
    thumb_path = f"Thumbnails/{user_id}.jpg"
    token_path = f"tokens/{user_id}.pickle"
    user_dict = user_data.get(user_id, {})
    if user_id != int(data[1]):
        await query.answer("𝐍ᴏᴛ 𝐘ᴏᴜʀs!", show_alert=True)
    elif data[2] in ["universal", "mirror", "leech"]:
        await query.answer()
        await update_user_settings(query, data[2])
    elif data[2] == "gdrive_tools":
        handler_dict[user_id] = False
        await query.answer()
        await update_user_settings(query, "gdrive_tools")
    elif data[2] == "gdrive_cancel":
        handler_dict[user_id] = False
        await query.answer()
        await update_user_settings(query, "gdrive_tools")
    elif data[2] == "gdrive_toggle":
        handler_dict[user_id] = False
        current = _setting_bool(
            user_dict.get("STOP_DUPLICATE", config_dict.get("STOP_DUPLICATE", False))
        )
        update_user_ldata(user_id, "STOP_DUPLICATE", not current)
        await query.answer()
        await update_user_settings(query, "gdrive_tools")
        if DATABASE_URL:
            await DbManger().update_user_data(user_id)
    elif data[2] == "gdrive_menu":
        handler_dict[user_id] = False
        option = data[3]
        await query.answer()
        if option == "DRIVE_CAT" and len(data) == 4:
            categories = user_dict.get("DRIVE_CAT") or {}
            category_text = "\n".join(
                f"• <b>{escape(str(category_name))}</b>"
                for category_name in categories
            ) or "• No user categories configured."
            buttons = ButtonMaker()
            buttons.ibutton("📝 𝐒ᴇᴛ / 𝐑ᴇᴘʟᴀᴄᴇ 𝐀ʟʟ", f"userset {user_id} gdrive_menu DRIVE_CAT set")
            buttons.ibutton("➕ 𝐀ᴅᴅ 𝐂ᴀᴛᴇɢᴏʀʏ", f"userset {user_id} gdrive_menu DRIVE_CAT add")
            buttons.ibutton("➖ 𝐑ᴇᴍᴏᴠᴇ 𝐂ᴀᴛᴇɢᴏʀʏ", f"userset {user_id} gdrive_menu DRIVE_CAT remove")
            buttons.ibutton("♻️ 𝐑ᴇsᴇᴛ 𝐂ᴀᴛᴇɢᴏʀɪᴇs", f"userset {user_id} gdrive_reset DRIVE_CAT")
            buttons.ibutton("🔙 𝐁ᴀᴄᴋ", f"userset {user_id} gdrive_tools", "footer")
            buttons.ibutton("✖️ 𝐂ʟᴏsᴇ", f"userset {user_id} close", "footer")
            await editMessage(
                message,
                f"📁 <b><u>𝐔sᴇʀ 𝐃ʀɪᴠᴇ 𝐂ᴀᴛᴇɢᴏʀɪᴇs</u></b>\n\n{category_text}",
                buttons.build_menu(1),
            )
            return
        mode = data[4] if len(data) > 4 else "set"
        prompt = {
            "GDRIVE_ID": (
                "<b>Send the default Google Drive folder/Team Drive ID.</b>\n"
                "You may also send a Google Drive folder URL."
            ),
            "INDEX_URL": (
                "<b>Send the default Google Drive Index URL.</b>\n"
                "Send an empty value only if you want to clear it."
            ),
            "DRIVE_CAT": (
                (
                    "<b>Send categories as a Python dictionary:</b>\n"
                    "<code>{'Movies': 'drive_id|https://index.example/'}</code>"
                    if mode == "set"
                    else (
                        "<b>Send one category as:</b>\n"
                        "<code>Name drive_id https://index.example/</code>"
                    )
                )
            ),
        }.get(option)
        if not prompt:
            await update_user_settings(query, "gdrive_tools")
            return
        buttons = ButtonMaker()
        buttons.ibutton("🛑 𝐒ᴛᴏᴘ", f"userset {user_id} gdrive_cancel")
        if option in ["GDRIVE_ID", "INDEX_URL"] or (
            option == "DRIVE_CAT" and mode == "set"
        ):
            buttons.ibutton("Reset", f"userset {user_id} gdrive_reset {option}")
        buttons.ibutton("🔙 𝐁ᴀᴄᴋ", f"userset {user_id} gdrive_tools", "footer")
        buttons.ibutton("✖️ 𝐂ʟᴏsᴇ", f"userset {user_id} close", "footer")
        await editMessage(
            message,
            f"⚙️ <b><u>𝐆ᴅʀɪᴠᴇ 𝐓ᴏᴏʟs • {option.replace('_', ' ').title()}</u></b>\n\n{prompt}\n\n"
            "⏱️ <b>𝐓ɪᴍᴇ 𝐋ᴇғᴛ :</b> <code>60 sec</code>",
            buttons.build_menu(1),
        )
        if option == "DRIVE_CAT" and mode == "add":
            pfunc = partial(add_drive_category, pre_event=query)
        elif option == "DRIVE_CAT" and mode == "remove":
            pfunc = partial(remove_drive_category, pre_event=query)
        else:
            pfunc = partial(set_custom, pre_event=query, key=option)
        rfunc = partial(update_user_settings, query, "gdrive_tools")
        await event_handler(client, query, pfunc, rfunc)
    elif data[2] == "gdrive_file":
        handler_dict[user_id] = False
        await query.answer()
        buttons = ButtonMaker()
        buttons.ibutton("🛑 𝐒ᴛᴏᴘ", f"userset {user_id} gdrive_cancel")
        buttons.ibutton("🔙 𝐁ᴀᴄᴋ", f"userset {user_id} gdrive_tools", "footer")
        buttons.ibutton("✖️ 𝐂ʟᴏsᴇ", f"userset {user_id} close", "footer")
        await editMessage(
            message,
            "🔐 <b>𝐔ᴘʟᴏᴀᴅ 𝐘ᴏᴜʀ 𝐓ᴏᴋᴇɴ.ᴘɪᴄᴋʟᴇ</b> ᴀs ᴀ ᴅᴏᴄᴜᴍᴇɴᴛ.\n\n"
            "<i>💡 𝐓ʜɪs ᴛᴏᴋᴇɴ ɪs sᴛᴏʀᴇᴅ sᴇᴘᴀʀᴀᴛᴇʟʏ ᴀɴᴅ ᴜsᴇᴅ ғᴏʀ ʏᴏᴜʀ "
            "𝐆ᴏᴏɢʟᴇ 𝐃ʀɪᴠᴇ ᴏᴘᴇʀᴀᴛɪᴏɴs.</i>\n\n"
            "⏱️ <b>𝐓ɪᴍᴇ 𝐋ᴇғᴛ :</b> <code>60 sec</code>",
            buttons.build_menu(1),
        )
        pfunc = partial(add_token_pickle, pre_event=query)
        rfunc = partial(update_user_settings, query, "gdrive_tools")
        await event_handler(client, query, pfunc, rfunc, document=True)
    elif data[2] == "gdrive_remove":
        handler_dict[user_id] = False
        option = data[3]
        if option == "TOKEN_PICKLE" and await aiopath.exists(token_path):
            await aioremove(token_path)
            update_user_ldata(user_id, "TOKEN_PICKLE", "")
            if DATABASE_URL:
                await DbManger().update_user_doc(user_id, "TOKEN_PICKLE")
            await query.answer("Token.pickle removed.")
        else:
            await query.answer("Token.pickle is not uploaded.", show_alert=True)
        await update_user_settings(query, "gdrive_tools")
    elif data[2] == "gdrive_reset":
        handler_dict[user_id] = False
        option = data[3]
        if option == "TOKEN_PICKLE":
            if await aiopath.exists(token_path):
                await aioremove(token_path)
            update_user_ldata(user_id, "TOKEN_PICKLE", "")
            if DATABASE_URL:
                await DbManger().update_user_doc(user_id, "TOKEN_PICKLE")
        else:
            user_data.setdefault(user_id, {}).pop(option, None)
            if DATABASE_URL:
                await DbManger().update_user_data(user_id)
        await query.answer("Setting reset.")
        await update_user_settings(query, "gdrive_tools")
    elif data[2] == "doc":
        update_user_ldata(user_id, "as_doc", not user_dict.get("as_doc", False))
        await query.answer()
        await update_user_settings(query, "leech")
        if DATABASE_URL:
            await DbManger().update_user_data(user_id)
    elif data[2] == "vthumb":
        handler_dict[user_id] = False
        await query.answer()
        buttons = ButtonMaker()
        buttons.ibutton("❌ 𝐂ʟᴏsᴇ", f"wzmlx {user_id} close", icon_custom_emoji_id=5447644880824181073)
        await sendMessage(message, from_user.mention, buttons.build_menu(1), thumb_path)
        await update_user_settings(query, "thumb", "leech")
    elif data[2] == "show_tds":
        handler_dict[user_id] = False
        user_tds = user_dict.get("user_tds", {})
        msg = f"➲ <b><u>𝐔sᴇʀ 𝐓ᴅ(s) 𝐃ᴇᴛᴀɪʟs</u></b>\n\n<b>𝐓ᴏᴛᴀʟ 𝐔sᴇʀ𝐓ᴅ(s) :</b> {len(user_tds)}\n\n"
        for index_no, (drive_name, drive_dict) in enumerate(user_tds.items(), start=1):
            msg += f"{index_no}: <b>𝐍ᴀᴍᴇ:</b> <code>{drive_name}</code>\n"
            msg += f"  <b>𝐃ʀɪᴠᴇ 𝐈ᴅ:</b> <code>{drive_dict['drive_id']}</code>\n"
            msg += f"  <b>𝐈ɴᴅᴇx 𝐋ɪɴᴋ:</b> <code>{ind_url if (ind_url := drive_dict['index_link']) else '𝐍ᴏᴛ 𝐏ʀᴏᴠɪᴅᴇᴅ'}</code>\n\n"
        try:
            await sendCustomMsg(user_id, msg)
            await query.answer("𝐔sᴇʀ 𝐓ᴅs 𝐒ᴜᴄᴄᴇssғᴜʟʟʏ 𝐒ᴇɴᴅ ɪɴ ʏᴏᴜʀ 𝐏ᴍ", show_alert=True)
        except Exception:
            await query.answer(
                "𝐒ᴛᴀʀᴛ ᴛʜᴇ 𝐁ᴏᴛ ɪɴ 𝐏ᴍ (𝐏ʀɪᴠᴀᴛᴇ) ᴀɴᴅ 𝐓ʀʏ 𝐀ɢᴀɪɴ", show_alert=True
            )
        await update_user_settings(query, "user_tds", "mirror")
    elif data[2] == "dthumb":
        handler_dict[user_id] = False
        if await aiopath.exists(thumb_path):
            await query.answer()
            await aioremove(thumb_path)
            update_user_ldata(user_id, "thumb", "")
            await update_user_settings(query, "thumb", "leech")
            if DATABASE_URL:
                await DbManger().update_user_doc(user_id, "thumb")
        else:
            await query.answer("𝐎ʟᴅ 𝐒ᴇᴛᴛɪɴɢs", show_alert=True)
            await update_user_settings(query, "leech")
    elif data[2] == "thumb":
        await query.answer()
        edit_mode = len(data) == 4
        await update_user_settings(query, data[2], "leech", edit_mode)
        if not edit_mode:
            return
        pfunc = partial(set_thumb, pre_event=query, key=data[2])
        rfunc = partial(update_user_settings, query, data[2], "leech")
        await event_handler(client, query, pfunc, rfunc, True)
    elif data[2] in ["yt_opt", "usess"]:
        await query.answer()
        edit_mode = len(data) == 4
        await update_user_settings(query, data[2], "universal", edit_mode)
        if not edit_mode:
            return
        pfunc = partial(set_custom, pre_event=query, key=data[2])
        rfunc = partial(update_user_settings, query, data[2], "universal")
        await event_handler(client, query, pfunc, rfunc)
    elif data[2] in ["dyt_opt", "dusess"]:
        handler_dict[user_id] = False
        await query.answer()
        update_user_ldata(user_id, data[2][1:], "")
        await update_user_settings(query, data[2][1:], "universal")
        if DATABASE_URL:
            await DbManger().update_user_data(user_id)
    elif data[2] in ["bot_pm", "mediainfo", "save_mode", "td_mode"]:
        handler_dict[user_id] = False
        if (
            data[2] == "save_mode"
            and not user_dict.get(data[2], False)
            and not user_dict.get("ldump")
        ):
            return await query.answer(
                "𝐒ᴇᴛ 𝐔sᴇʀ 𝐃ᴜᴍᴘ ғɪʀsᴛ ᴛᴏ 𝐂ʜᴀɴɢᴇ 𝐒ᴀᴠᴇ 𝐌sɢ 𝐌ᴏᴅᴇ !", show_alert=True
            )
        elif (
            data[2] == "bot_pm"
            and (config_dict["BOT_PM"] or config_dict["SAFE_MODE"])
            or data[2] == "mediainfo"
            and config_dict["SHOW_MEDIAINFO"]
            or data[2] == "td_mode"
            and not config_dict["USER_TD_MODE"]
        ):
            mode_up = "𝐃ɪsᴀʙʟᴇᴅ" if data[2] == "td_mode" else "𝐄ɴᴀʙʟᴇᴅ"
            return await query.answer(
                f"𝐅ᴏʀᴄᴇ {mode_up}! 𝐂ᴀɴ'ᴛ 𝐀ʟᴛᴇʀ 𝐒ᴇᴛᴛɪɴɢs", show_alert=True
            )
        if data[2] == "td_mode" and not user_dict.get("user_tds", False):
            return await query.answer(
                "𝐒ᴇᴛ 𝐔sᴇʀ𝐓ᴅ ғɪʀsᴛ ᴛᴏ 𝐄ɴᴀʙʟᴇ 𝐔sᴇʀ 𝐓ᴅ 𝐌ᴏᴅᴇ !", show_alert=True
            )
        await query.answer()
        update_user_ldata(user_id, data[2], not user_dict.get(data[2], False))
        if data[2] in ["td_mode"]:
            await update_user_settings(query, "user_tds", "mirror")
        else:
            await update_user_settings(query, "universal")
        if DATABASE_URL:
            await DbManger().update_user_data(user_id)
    elif data[2] == "split_size":
        await query.answer()
        edit_mode = len(data) == 4
        await update_user_settings(query, data[2], "leech", edit_mode)
        if not edit_mode:
            return
        pfunc = partial(leech_split_size, pre_event=query)
        rfunc = partial(update_user_settings, query, data[2], "leech")
        await event_handler(client, query, pfunc, rfunc)
    elif data[2] == "dsplit_size":
        handler_dict[user_id] = False
        await query.answer()
        update_user_ldata(user_id, "split_size", "")
        await update_user_settings(query, "split_size", "leech")
        if DATABASE_URL:
            await DbManger().update_user_data(user_id)
    elif data[2] == "esplits":
        handler_dict[user_id] = False
        await query.answer()
        update_user_ldata(
            user_id, "equal_splits", not user_dict.get("equal_splits", False)
        )
        await update_user_settings(query, "leech")
        if DATABASE_URL:
            await DbManger().update_user_data(user_id)
    elif data[2] == "mgroup":
        handler_dict[user_id] = False
        await query.answer()
        update_user_ldata(
            user_id, "media_group", not user_dict.get("media_group", False)
        )
        await update_user_settings(query, "leech")
        if DATABASE_URL:
            await DbManger().update_user_data(user_id)
    elif data[2] == "auto_poster":
        handler_dict[user_id] = False
        await query.answer()
        update_user_ldata(
            user_id, "auto_poster", not user_dict.get("auto_poster", False)
        )
        await update_user_settings(query, "leech")
        if DATABASE_URL:
            await DbManger().update_user_data(user_id)
    elif data[2] == "merge_video_menu":
        handler_dict[user_id] = False
        await query.answer()
        await update_user_settings(query, "merge_video_menu")
    elif data[2] == "mv_back":
        handler_dict[user_id] = False
        await query.answer()
        await update_user_settings(query, "leech")
    elif data[2] == "auto_rename":
        handler_dict[user_id] = False
        await query.answer()
        await update_user_settings(query, "auto_rename")
    elif data[2] == "ar_auto":
        handler_dict[user_id] = False
        await query.answer()
        current = user_dict.get("auto_rename", False)
        if current is True:
            current = "auto"
        new_mode = "" if current == "auto" else "auto"
        update_user_ldata(user_id, "auto_rename", new_mode)
        await update_user_settings(query, "auto_rename")
        if DATABASE_URL:
            await DbManger().update_user_data(user_id)
    elif data[2] == "ar_off":
        handler_dict[user_id] = False
        await query.answer()
        update_user_ldata(user_id, "auto_rename", "")
        await update_user_settings(query, "auto_rename")
        if DATABASE_URL:
            await DbManger().update_user_data(user_id)
    elif data[2] == "ar_fmt":
        handler_dict[user_id] = False
        await query.answer()
        edit_mode = len(data) == 4
        await update_user_settings(query, "ar_fmt", "auto_rename", edit_mode)
        if not edit_mode:
            return
        pfunc = partial(set_custom, pre_event=query, key="ar_fmt")
        rfunc  = partial(update_user_settings, query, "ar_fmt", "auto_rename")
        await event_handler(client, query, pfunc, rfunc)
    elif data[2] == "dar_fmt":
        handler_dict[user_id] = False
        await query.answer()
        update_user_ldata(user_id, "auto_rename_fmt", "")
        _ar = user_dict.get("auto_rename", "")
        if _ar == "custom":
            update_user_ldata(user_id, "auto_rename", "")
        await update_user_settings(query, "auto_rename")
        if DATABASE_URL:
            await DbManger().update_user_data(user_id)
    elif data[2] in ["sgofile", "sstreamtape", "dgofile", "dstreamtape"]:
        handler_dict[user_id] = False
        ddl_dict = user_dict.get("ddl_servers", {})
        key = data[2][1:]
        mode, api = ddl_dict.get(key, [False, ""])
        if data[2][0] == "s":
            if not mode and api == "":
                return await query.answer(
                    "𝐒ᴇᴛ 𝐀ᴘɪ ᴛᴏ 𝐄ɴᴀʙʟᴇ 𝐃ᴅʟ 𝐒ᴇʀᴠᴇʀ", show_alert=True
                )
            ddl_dict[key] = [not mode, api]
        elif data[2][0] == "d":
            ddl_dict[key] = [mode, ""]
        await query.answer()
        update_user_ldata(user_id, "ddl_servers", ddl_dict)
        await update_user_settings(query, key, "ddl_servers")
        if DATABASE_URL:
            await DbManger().update_user_data(user_id)
    elif data[2] in ["ddl_servers", "user_tds", "gofile", "streamtape"]:
        handler_dict[user_id] = False
        await query.answer()
        edit_mode = len(data) == 4
        await update_user_settings(
            query,
            data[2],
            "mirror" if data[2] in ["ddl_servers", "user_tds"] else "ddl_servers",
            edit_mode,
        )
        if not edit_mode:
            return
        pfunc = partial(set_custom, pre_event=query, key=data[2])
        rfunc = partial(
            update_user_settings,
            query,
            data[2],
            "mirror" if data[2] in ["ddl_servers", "user_tds"] else "ddl_servers",
        )
        await event_handler(client, query, pfunc, rfunc)
    elif data[2] in [
        "lprefix",
        "lsuffix",
        "lremname",
        "lcaption",
        "ldump",
        "mprefix",
        "msuffix",
        "mremname",
        "lmeta",
    ]:
        handler_dict[user_id] = False
        await query.answer()
        edit_mode = len(data) == 4
        return_key = "leech" if data[2][0] == "l" else "mirror"
        await update_user_settings(query, data[2], return_key, edit_mode)
        if not edit_mode:
            return
        pfunc = partial(set_custom, pre_event=query, key=data[2])
        rfunc = partial(update_user_settings, query, data[2], return_key)
        await event_handler(client, query, pfunc, rfunc)
    elif data[2] in [
        "dlprefix",
        "dlsuffix",
        "dlremname",
        "dlcaption",
        "dldump",
        "dlmeta",
    ]:
        handler_dict[user_id] = False
        await query.answer()
        update_user_ldata(user_id, data[2][1:], {} if data[2] == "dldump" else "")
        await update_user_settings(query, data[2][1:], "leech")
        if DATABASE_URL:
            await DbManger().update_user_data(user_id)
    elif data[2] in ["dmprefix", "dmsuffix", "dmremname", "duser_tds"]:
        handler_dict[user_id] = False
        await query.answer()
        update_user_ldata(user_id, data[2][1:], {} if data[2] == "duser_tds" else "")
        if data[2] == "duser_tds":
            update_user_ldata(user_id, "td_mode", False)
        await update_user_settings(query, data[2][1:], "mirror")
        if DATABASE_URL:
            await DbManger().update_user_data(user_id)
    elif data[2] == "back":
        handler_dict[user_id] = False
        await query.answer()
        setting = data[3] if len(data) == 4 else None
        await update_user_settings(query, setting)
    elif data[2] == "reset_all":
        handler_dict[user_id] = False
        await query.answer()
        buttons = ButtonMaker()
        buttons.ibutton("𝐘ᴇs", f"userset {user_id} reset_now y", icon_custom_emoji_id=5206607081334906820)
        buttons.ibutton("𝐍ᴏ", f"userset {user_id} reset_now n", icon_custom_emoji_id=5447644880824181073)
        buttons.ibutton("𝐂ʟᴏsᴇ", f"userset {user_id} close", "footer", icon_custom_emoji_id=5447644880824181073)
        await editMessage(
            message, "𝐃ᴏ ʏᴏᴜ ᴡᴀɴᴛ ᴛᴏ 𝐑ᴇsᴇᴛ 𝐒ᴇᴛᴛɪɴɢs ?", buttons.build_menu(2)
        )
    elif data[2] == "reset_now":
        handler_dict[user_id] = False
        if data[3] == "n":
            return await update_user_settings(query)
        if await aiopath.exists(thumb_path):
            await aioremove(thumb_path)
        if await aiopath.exists(token_path):
            await aioremove(token_path)
        await query.answer()
        update_user_ldata(user_id, None, None)
        await update_user_settings(query)
        if DATABASE_URL:
            await DbManger().update_user_data(user_id)
            await DbManger().update_user_doc(user_id, "thumb")
            await DbManger().update_user_doc(user_id, "TOKEN_PICKLE")
    elif data[2] == "user_del":
        user_id = int(data[3])
        await query.answer()
        thumb_path = f"Thumbnails/{user_id}.jpg"
        if await aiopath.exists(thumb_path):
            await aioremove(thumb_path)
        if await aiopath.exists(token_path):
            await aioremove(token_path)
        update_user_ldata(user_id, None, None)
        if DATABASE_URL:
            await DbManger().update_user_data(user_id)
            await DbManger().update_user_doc(user_id, "thumb")
            await DbManger().update_user_doc(user_id, "TOKEN_PICKLE")
        await editMessage(message, f"𝐃ᴀᴛᴀ 𝐑ᴇsᴇᴛ ғᴏʀ {user_id}")
    else:
        handler_dict[user_id] = False
        await query.answer()
        await deleteMessage(message.reply_to_message)
        await deleteMessage(message)

async def send_users_settings(client, message):
    text = message.text.split(maxsplit=1)
    userid = text[1] if len(text) > 1 else None
    if userid and not userid.isdigit():
        userid = None
    elif (
        (reply_to := message.reply_to_message)
        and reply_to.from_user
        and not reply_to.from_user.is_bot
    ):
        userid = reply_to.from_user.id
    if not userid:
        msg = f"<u><b>𝐓ᴏᴛᴀʟ 𝐔sᴇʀs / 𝐂ʜᴀᴛs 𝐃ᴀᴛᴀ 𝐒ᴀᴠᴇᴅ :</b> {len(user_data)}</u>"
        buttons = ButtonMaker()
        buttons.ibutton("❌ 𝐂ʟᴏsᴇ", f"userset {message.from_user.id} close", icon_custom_emoji_id=5447644880824181073)
        button = buttons.build_menu(1)
        for user, data in user_data.items():
            msg += f"\n\n<code>{user}</code>:"
            if data:
                for key, value in data.items():
                    if key in ["token", "time", "ddl_servers", "usess"]:
                        continue
                    msg += f"\n<b>{key}</b>: <code>{escape(str(value))}</code>"
            else:
                msg += "\n𝐔sᴇʀ's 𝐃ᴀᴛᴀ ɪs 𝐄ᴍᴘᴛʏ!"
        if len(msg.encode()) > 4000:
            with BytesIO(str.encode(msg)) as ofile:
                ofile.name = "users_settings.txt"
                await sendFile(message, ofile)
        else:
            await sendMessage(message, msg, button)
    elif int(userid) in user_data:
        msg = f'{(await user_info(userid)).mention(style="html")} ( <code>{userid}</code> ):'
        if data := user_data[int(userid)]:
            buttons = ButtonMaker()
            buttons.ibutton(
                "🗑️ 𝐃ᴇʟᴇᴛᴇ 𝐃ᴀᴛᴀ", f"userset {message.from_user.id} user_del {userid}",
                icon_custom_emoji_id=5445267414562389170
            )
            buttons.ibutton("❌ 𝐂ʟᴏsᴇ", f"userset {message.from_user.id} close", icon_custom_emoji_id=5447644880824181073)
            button = buttons.build_menu(1)
            for key, value in data.items():
                if key in ["token", "time", "ddl_servers", "usess"]:
                    continue
                msg += f"\n<b>{key}</b>: <code>{escape(str(value))}</code>"
        else:
            msg += "\n𝐓ʜɪs 𝐔sᴇʀ ʜᴀs ɴᴏᴛ 𝐒ᴀᴠᴇᴅ ᴀɴʏᴛʜɪɴɢ."
            button = None
        await sendMessage(message, msg, button)
    else:
        await sendMessage(message, f"{userid} 𝐇ᴀᴠᴇ 𝐍ᴏᴛ 𝐒ᴀᴠᴇᴅ 𝐀ɴʏᴛʜɪɴɢ..")

bot.add_handler(
    MessageHandler(
        send_users_settings,
        filters=command(BotCommands.UsersCommand) & CustomFilters.sudo,
    )
)
bot.add_handler(
    MessageHandler(
        user_settings,
        filters=command(BotCommands.UserSetCommand) & CustomFilters.authorized_uset,
    )
)
bot.add_handler(CallbackQueryHandler(edit_user_settings, filters=regex("^userset")))
