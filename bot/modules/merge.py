#!/usr/bin/env python3
"""
Merge Module — /startmerge  |  /sm

Uses the existing MirrorLeechListener + sameDir mechanism so every queued
download / merge / upload appears in the standard /status progress UI.

Font: Bold-Math for UPPERCASE letters, Small-Caps for lowercase letters.
      This matches the 'Custom Thumbnail' / SSLeech-style throughout.
"""

import re
from asyncio import create_task
from os import path as ospath

from pyrogram.handlers import MessageHandler, CallbackQueryHandler
from pyrogram.filters import command, regex, create as pyro_create

from bot import bot, DOWNLOAD_DIR, LOGGER, user_data
from bot.helper.telegram_helper.bot_commands import BotCommands
from bot.helper.telegram_helper.filters import CustomFilters
from bot.helper.telegram_helper.button_build import ButtonMaker
from bot.helper.telegram_helper.message_utils import (
    sendMessage, editMessage, deleteMessage,
)
from bot.helper.ext_utils.bot_utils import (
    new_task, is_url, is_magnet, is_mega_link, is_gdrive_link,
    is_telegram_link, is_rclone_path,
)
from bot.helper.listeners.tasks_listener import MirrorLeechListener
from bot.helper.mirror_utils.download_utils.aria2_download import add_aria2c_download
from bot.helper.mirror_utils.download_utils.telegram_download import TelegramDownloadHelper
from bot.helper.mirror_utils.download_utils.mega_download import add_mega_download
from bot.helper.mirror_utils.download_utils.gd_download import add_gd_download


# ── SSLeech font converter ─────────────────────────────────────────────────────
# UPPERCASE → Unicode Mathematical Bold  (𝐀𝐁𝐂…)
# lowercase → Unicode Small Caps          (ᴀʙᴄ…) where available, else unchanged

_BOLD = {chr(ord('A') + i): chr(0x1D400 + i) for i in range(26)}
_SCAP = {
    'a': 'ᴀ', 'b': 'ʙ', 'c': 'ᴄ', 'd': 'ᴅ', 'e': 'ᴇ', 'f': 'ꜰ',
    'g': 'ɢ', 'h': 'ʜ', 'i': 'ɪ', 'j': 'ᴊ', 'k': 'ᴋ', 'l': 'ʟ',
    'm': 'ᴍ', 'n': 'ɴ', 'o': 'ᴏ', 'p': 'ᴘ', 'r': 'ʀ',
    't': 'ᴛ', 'u': 'ᴜ', 'v': 'ᴠ', 'w': 'ᴡ', 'y': 'ʏ', 'z': 'ᴢ',
    # q, s, x have no standard small-caps → stay as-is
}

def _t(text: str) -> str:
    """Convert plain text to SSLeech Bold-Math + Small-Caps font."""
    return ''.join(_BOLD.get(c, _SCAP.get(c, c)) for c in text)


# ── Constants ──────────────────────────────────────────────────────────────────
_DIV  = "━━━━━━━━━━━━━━━━━━━━━━"
_THIN = "┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄"

# TG media attrs that carry downloadable files
_TG_MEDIA_ATTRS = (
    "document", "video", "audio", "animation",
    "voice", "video_note", "photo",
)

# Per-user session state
merge_sessions: dict = {}

# Mode meta  {key: (emoji, display_name, short_hint)}
MODES = {
    "vv":  ("🎬", _t("Video + Video"),
            _t("Send video files/links one by one. They will be concatenated in order.")),
    "va":  ("🎵", _t("Video + Audio"),
            _t("Send video first, then audio file (mp3, m4a, flac). Audio will be muxed in.")),
    "vs":  ("📝", _t("Video + Subtitles"),
            _t("Send video first, then subtitle file (.srt, .ass). Subs will be embedded.")),
    "zip": ("📦", _t("Zip/Archive") + " → " + _t("Merge"),
            _t("Send ZIP/RAR archives. Episodes will be extracted, selected and merged.")),
}


# ── Helpers ────────────────────────────────────────────────────────────────────

def _user_thumb(uid: int) -> str | None:
    path = user_data.get(uid, {}).get("thumb", "")
    return path if path and ospath.exists(path) else None


def _queue_text(uid: int, mode: str, queue: list) -> str:
    emoji, mname, hint = MODES[mode]
    cnt   = len(queue)
    items = "\n".join(
        f"  <b>{i}.</b> <code>{it['label'][:68]}</code>"
        for i, it in enumerate(queue, 1)
    )
    empty_line = f"  <i>{_t('Empty')} — {_t('send a file or link')}</i>"
    return (
        f"<b>{emoji} {_t('Merge')} — {mname}</b>\n"
        f"{_DIV}\n"
        f"<b>ℹ️ {_t('How')}:</b> {hint}\n\n"
        f"<b>📋 {_t('Queue')} ({cnt} {_t('item') if cnt == 1 else _t('items')}):</b>\n"
        + (items if queue else empty_line)
        + "\n"
    )


def _queue_buttons(uid: int, has_items: bool):
    btns = ButtonMaker()
    if has_items:
        btns.ibutton(f"⚡ {_t('Merge Now')}",     f"merge {uid} start")
        btns.ibutton(f"🗑 {_t('Remove Last')}",   f"merge {uid} remove_last")
    btns.ibutton(f"❌ {_t('Cancel Session')}",    f"merge {uid} cancel")
    return btns.build_menu(2)


async def _clear_session(uid: int):
    session = merge_sessions.pop(uid, None)
    if not session:
        return
    for key in ("menu_msg", "ask_msg"):
        msg = session.get(key)
        if msg:
            try:
                await deleteMessage(msg)
            except Exception:
                pass


def _get_tg_media(message):
    for attr in _TG_MEDIA_ATTRS:
        m = getattr(message, attr, None)
        if m is not None:
            return m
    return None


def _get_tg_filename(message) -> str:
    media = _get_tg_media(message)
    if media is None:
        return f"file_{message.id}"
    return (
        getattr(media, "file_name", None)
        or f"{type(media).__name__}_{getattr(media, 'file_unique_id', message.id)}"
    )


# ── /startmerge command ────────────────────────────────────────────────────────

@new_task
async def start_merge(client, message):
    uid      = message.from_user.id
    udict    = user_data.get(uid, {})

    if not udict.get("merge_video", False):
        return await sendMessage(
            message,
            f"<b>⚙️ {_t('Merge Video Disabled')}!</b>\n"
            f"{_DIV}\n"
            f"{_t('Enable it from')}:\n"
            f"<code>/{BotCommands.UserSetCommand[0]}</code> "
            f"→ {_t('Leech Settings')} → 🎞 {_t('Merge Video')} ✅",
        )

    if uid in merge_sessions:
        await _clear_session(uid)

    # Mode selection menu
    btns = ButtonMaker()
    for k, (emoji, label, _) in MODES.items():
        btns.ibutton(f"{emoji} {label}", f"merge {uid} mode {k}")
    btns.ibutton(f"❌ {_t('Cancel')}", f"merge {uid} cancel")

    text = (
        f"<b>🎞 {_t('Merge Tool')} — {_t('Select Mode')}</b>\n"
        f"{_DIV}\n\n"
        f"🎬 <b>{_t('Video + Video')}</b>\n"
        f"  ↳ {_t('Concatenate multiple videos into one')}\n\n"
        f"🎵 <b>{_t('Video + Audio')}</b>\n"
        f"  ↳ {_t('Mux audio track into existing video')}\n\n"
        f"📝 <b>{_t('Video + Subtitles')}</b>\n"
        f"  ↳ {_t('Embed subs into video container')}\n\n"
        f"📦 <b>{_t('Zip/Archive')} → {_t('Merge')}</b>\n"
        f"  ↳ {_t('Extract archives and merge episodes')}"
    )

    thumb = _user_thumb(uid)
    menu  = await sendMessage(message, text, btns.build_menu(2), photo=thumb)
    merge_sessions[uid] = {
        "mode":     None,
        "queue":    [],
        "menu_msg": menu,
        "step":     "mode",
        "chat_id":  message.chat.id,
        "orig_msg": message,
        "ask_msg":  None,
    }


# ── Callback handler ───────────────────────────────────────────────────────────

@new_task
async def merge_callback(client, query):
    data   = query.data.split()
    uid    = int(data[1])
    action = data[2]

    if query.from_user.id != uid:
        return await query.answer(f"⚠️ {_t('Not Yours')}!", show_alert=True)

    session = merge_sessions.get(uid)
    if not session and action != "cancel":
        return await query.answer(f"⌛ {_t('Session Expired')}!", show_alert=True)

    await query.answer()

    # ── Cancel ─────────────────────────────────────────────────────────────
    if action == "cancel":
        await _clear_session(uid)
        try:
            await deleteMessage(query.message)
        except Exception:
            pass
        return

    # ── Mode selection ─────────────────────────────────────────────────────
    if action == "mode":
        mode = data[3]
        if mode not in MODES:
            return
        session["mode"] = mode
        session["step"] = "collect"
        text   = _queue_text(uid, mode, session["queue"])
        markup = _queue_buttons(uid, bool(session["queue"]))
        thumb  = _user_thumb(uid)
        await editMessage(query.message, text, markup, photo=thumb)
        return

    # ── Remove last ────────────────────────────────────────────────────────
    if action == "remove_last":
        if session["queue"]:
            removed = session["queue"].pop()
            await query.answer(
                f"🗑 {_t('Removed')}: {removed['label'][:30]}", show_alert=False
            )
        text   = _queue_text(uid, session["mode"], session["queue"])
        markup = _queue_buttons(uid, bool(session["queue"]))
        await editMessage(query.message, text, markup)
        return

    # ── Merge Now → filename prompt ────────────────────────────────────────
    if action == "start":
        if not session["queue"]:
            return await query.answer(
                f"📋 {_t('Queue is Empty')}!", show_alert=True
            )
        if session["step"] == "await_name":
            return
        session["step"] = "await_name"
        cnt            = len(session["queue"])
        emoji, mname, _ = MODES[session["mode"]]

        btns = ButtonMaker()
        btns.ibutton(f"⏭ {_t('Skip')} ({_t('Use Auto-Name')})", f"merge {uid} skip_name")
        btns.ibutton(f"◀ {_t('Back to Queue')}",               f"merge {uid} back_to_collect")
        btns.ibutton(f"❌ {_t('Cancel')}",                     f"merge {uid} cancel")

        thumb = _user_thumb(uid)
        ask   = await sendMessage(
            session["orig_msg"],
            f"<b>{emoji} {_t('Ready to Merge')} — {mname}</b>\n"
            f"{_DIV}\n"
            f"<b>📂 {_t('Queued Files')}:</b> {cnt}\n\n"
            f"{_THIN}\n"
            f"<b>📝 {_t('Output Filename')}</b>\n"
            f"{_t('Type a name')} <i>({_t('without extension')})</i> "
            f"{_t('or use a button below')}:\n\n"
            f"  ⏭ <b>{_t('Skip')}</b>  →  {_t('Bot will auto-name the file')}\n"
            f"  ◀ <b>{_t('Back')}</b>  →  {_t('Return to queue')}\n\n"
            f"⏱ <i>{_t('Auto-skips in 60s if no input')}</i>",
            btns.build_menu(2),
            photo=thumb,
        )
        session["ask_msg"] = ask
        return

    # ── Skip filename ──────────────────────────────────────────────────────
    if action == "skip_name":
        if session["step"] != "await_name":
            return
        try:
            await deleteMessage(session.get("ask_msg"))
        except Exception:
            pass
        session["ask_msg"] = None
        await _dispatch_all_downloads(client, uid, session, "")
        return

    # ── Back to collect phase ──────────────────────────────────────────────
    if action == "back_to_collect":
        if session["step"] != "await_name":
            return
        try:
            await deleteMessage(session.get("ask_msg"))
        except Exception:
            pass
        session["ask_msg"] = None
        session["step"]    = "collect"
        text   = _queue_text(uid, session["mode"], session["queue"])
        markup = _queue_buttons(uid, bool(session["queue"]))
        await editMessage(session["menu_msg"], text, markup)
        return


# ── Message handler — collect OR capture filename ──────────────────────────────

@new_task
async def merge_message_handler(client, message):
    uid     = message.from_user.id
    session = merge_sessions.get(uid)
    if not session or message.chat.id != session["chat_id"]:
        return

    # ── Filename capture ───────────────────────────────────────────────────
    if session["step"] == "await_name":
        if not message.text:
            return
        raw      = message.text.strip()
        out_name = re.sub(r'[\\/:*?"<>|]', "_", raw) if raw else ""
        try:
            await deleteMessage(session.get("ask_msg"))
        except Exception:
            pass
        await deleteMessage(message)
        await _dispatch_all_downloads(client, uid, session, out_name)
        return

    # ── File / link collection ─────────────────────────────────────────────
    if session["step"] != "collect":
        return

    item = None

    if message.text:
        url = message.text.strip()
        if any([
            is_url(url), is_magnet(url), is_gdrive_link(url),
            is_mega_link(url), is_rclone_path(url), is_telegram_link(url),
        ]):
            item = {"label": url, "type": "url", "data": url, "msg": message}
    else:
        media = _get_tg_media(message)
        if media is not None:
            fname = _get_tg_filename(message)
            item  = {"label": fname, "type": "tgfile", "data": fname, "msg": message}

    if item:
        session["queue"].append(item)
        await deleteMessage(message)
        text   = _queue_text(uid, session["mode"], session["queue"])
        markup = _queue_buttons(uid, True)
        await editMessage(session["menu_msg"], text, markup)


# ── Dispatch all downloads simultaneously ──────────────────────────────────────

async def _dispatch_all_downloads(client, uid: int, session: dict, out_name: str):
    mode     = session["mode"]
    queue    = session["queue"]
    orig_msg = session["orig_msg"]

    try:
        await deleteMessage(session["menu_msg"])
    except Exception:
        pass
    merge_sessions.pop(uid, None)

    # Auto-disable merge_video when session ends
    from bot.helper.ext_utils.bot_utils import update_user_ldata
    from bot import DATABASE_URL
    update_user_ldata(uid, "merge_video", False)
    if DATABASE_URL:
        try:
            from bot.helper.ext_utils.db_handler import DbManger
            await DbManger().update_user_data(uid)
        except Exception:
            pass

    total  = len(queue)
    is_zip = (mode == "zip")

    shared_sameDir = {
        "total":      total,
        "tasks":      {item["msg"].id for item in queue},
        "name":       f"/merge_{orig_msg.id}",
        "merge_mode": mode,
    }

    tag = (
        f"@{orig_msg.from_user.username}"
        if orig_msg.from_user.username
        else orig_msg.from_user.mention
    )

    for item in queue:
        msg  = item["msg"]
        path = f"{DOWNLOAD_DIR}{msg.id}/merge_{orig_msg.id}"

        src_url = (
            getattr(msg, "link", None) or f"tg_merge_{msg.id}"
            if item["type"] == "tgfile"
            else item["data"]
        )

        listener = MirrorLeechListener(
            msg,
            compress=False,
            extract=is_zip,          # True for zip → _do_zip_merge in tasks_listener
            isLeech=True,
            tag=tag,
            sameDir=shared_sameDir,
            merge_video=True,
            merge_output_name=out_name,   # user's name applied to ALL modes
            source_url=src_url,
            leech_utils={"screenshots": 0, "thumb": ""},
        )

        # All downloads start simultaneously via create_task.
        # TelegramDownloadHelper.add_download() blocks → MUST be a task.
        if item["type"] == "tgfile":
            create_task(
                TelegramDownloadHelper(listener).add_download(
                    msg, f"{path}/", "", "", None
                )
            )
        else:
            url = item["data"]
            if is_gdrive_link(url):
                create_task(add_gd_download(url, path, listener, "", url))
            elif is_mega_link(url):
                create_task(add_mega_download(url, f"{path}/", listener, ""))
            else:
                create_task(
                    add_aria2c_download(url, path, listener, "", "", None, None)
                )

        LOGGER.info(f"[MERGE] Dispatched: {item['label'][:60]} (msg_id={msg.id})")

    LOGGER.info(
        f"[MERGE] {total} task(s) dispatched — mode={mode} "
        f"name='{out_name or 'auto'}'"
    )


# ── Dynamic filter ─────────────────────────────────────────────────────────────

async def _is_merge_user(_, __, message):
    if not message.from_user:
        return False
    uid = message.from_user.id
    s   = merge_sessions.get(uid)
    return bool(
        s
        and message.chat.id == s["chat_id"]
        and s["step"] in ("collect", "await_name")
    )


merge_user_filter = pyro_create(_is_merge_user)


# ── Handler registration ───────────────────────────────────────────────────────

def register_handlers(app):
    app.add_handler(
        MessageHandler(
            start_merge,
            filters=(
                command(BotCommands.StartMergeCommand)
                & CustomFilters.authorized
                & ~CustomFilters.blacklisted
            ),
        )
    )
    app.add_handler(
        CallbackQueryHandler(merge_callback, filters=regex(r"^merge"))
    )
    app.add_handler(
        MessageHandler(merge_message_handler, filters=merge_user_filter),
        group=1,
    )
