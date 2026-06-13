#!/usr/bin/env python3
"""
Merge Module — /startmerge{suffix}  |  /sm{suffix}

Uses the existing MirrorLeechListener + sameDir mechanism so every queued
download/merge/upload shows up in the standard /status progress UI — exactly
like a normal leech task.

Merge modes
-----------
  vv  → Video + Video   : concatenate via existing merge_video_files()
  va  → Video + Audio   : FFmpeg audio-mux  (new _do_audio_mux in tasks_listener)
  vs  → Video + Subs    : FFmpeg subtitle embed (new _do_subtitle_embed)
  zip → Zip Merge       : compress=True in listener → existing 7z logic

Flow
----
  1. /startmerge → check merge_video enabled → show mode menu
  2. User selects mode → collect phase (send files / links one by one)
  3. ⚡ Merge Now → ask output filename → dispatch all downloads with
     shared sameDir dict → existing download/merge/upload pipeline takes over
  4. Session auto-clears; merge_video auto-disabled after completion
"""

import re
from asyncio import sleep
from os import path as ospath

from pyrogram.handlers import MessageHandler, CallbackQueryHandler
from pyrogram.filters import command, regex, create as pyro_create

from bot import bot, DOWNLOAD_DIR, LOGGER, user_data
from bot.helper.telegram_helper.bot_commands import BotCommands
from bot.helper.telegram_helper.filters import CustomFilters
from bot.helper.telegram_helper.button_build import ButtonMaker
from bot.helper.telegram_helper.message_utils import sendMessage, editMessage, deleteMessage
from bot.helper.ext_utils.bot_utils import (
    new_task, is_url, is_magnet, is_mega_link, is_gdrive_link,
    is_telegram_link, is_rclone_path,
)
from bot.helper.listeners.tasks_listener import MirrorLeechListener
from bot.helper.mirror_utils.download_utils.aria2_download import add_aria2c_download
from bot.helper.mirror_utils.download_utils.telegram_download import TelegramDownloadHelper
from bot.helper.mirror_utils.download_utils.mega_download import add_mega_download
from bot.helper.mirror_utils.download_utils.gd_download import add_gd_download


# ── Per-user session state ────────────────────────────────────────────────────
# {
#   uid: {
#     "mode":     str,       "vv"|"va"|"vs"|"zip"
#     "queue":    list[dict] {"label":str, "type":"url"|"tgfile", "data":str, "msg":Message}
#     "menu_msg": Message,
#     "step":     str,       "mode"|"collect"|"await_name"
#     "chat_id":  int,
#     "orig_msg": Message,
#     "ask_msg":  Message|None,
#   }
# }
merge_sessions: dict = {}

# ── Mode labels & hints ───────────────────────────────────────────────────────
MODES = {
    "vv":  "🎬 𝐕ɪᴅᴇᴏ + 𝐕ɪᴅᴇᴏ",
    "va":  "🎵 𝐕ɪᴅᴇᴏ + 𝐀ᴜᴅɪᴏ",
    "vs":  "📝 𝐕ɪᴅᴇᴏ + 𝐒ᴜʙᴛɪᴛʟᴇs",
    "zip": "🗜️ 𝐙ɪᴘ 𝐌ᴇʀɢᴇ",
}

MODE_HINTS = {
    "vv":  "➲ 𝐒ᴇɴᴅ ᴠɪᴅᴇᴏ ʟɪɴᴋs/ғɪʟᴇs ᴏɴᴇ ʙʏ ᴏɴᴇ — ᴡɪʟʟ ʙᴇ ᴄᴏɴᴄᴀᴛᴇɴᴀᴛᴇᴅ ɪɴ ᴏʀᴅᴇʀ.",
    "va":  "➲ <b>𝐅ɪʀsᴛ</b> sᴇɴᴅ ᴠɪᴅᴇᴏ, <b>ᴛʜᴇɴ</b> ᴀᴜᴅɪᴏ ʟɪɴᴋ/ғɪʟᴇ (mp3, m4a…).",
    "vs":  "➲ <b>𝐅ɪʀsᴛ</b> sᴇɴᴅ ᴠɪᴅᴇᴏ, <b>ᴛʜᴇɴ</b> sᴜʙᴛɪᴛʟᴇ ʟɪɴᴋ/ғɪʟᴇ (.srt, .ass…).",
    "zip": "➲ 𝐒ᴇɴᴅ ᴀɴʏ ʟɪɴᴋs/ғɪʟᴇs — ᴀʟʟ ᴡɪʟʟ ʙᴇ ᴘᴀᴄᴋᴇᴅ ɪɴᴛᴏ ᴏɴᴇ ZIP.",
}


# ── UI helpers ────────────────────────────────────────────────────────────────

def _queue_menu(uid: int, mode: str, queue: list) -> tuple:
    lines = "\n".join(
        f"  {i}. <code>{it['label'][:65]}</code>"
        for i, it in enumerate(queue, 1)
    )
    text = (
        f"🎞️ <b><u>𝐌ᴇʀɢᴇ 𝐌ᴏᴅᴇ — {MODES[mode]}</u></b>\n\n"
        f"{MODE_HINTS[mode]}\n\n"
        f"📋 <b>𝐐ᴜᴇᴜᴇ ({len(queue)} ɪᴛᴇᴍ{'s' if len(queue) != 1 else ''}):</b>\n"
        + (lines if queue else "  <i>ᴇᴍᴘᴛʏ — sᴇɴᴅ ᴀ ʟɪɴᴋ ᴏʀ ᴜᴘʟᴏᴀᴅ ᴀ ғɪʟᴇ</i>")
        + "\n"
    )
    btns = ButtonMaker()
    if queue:
        btns.ibutton("⚡ 𝐌ᴇʀɢᴇ 𝐍ᴏᴡ", f"merge {uid} start")
        btns.ibutton("🗑 𝐑ᴇᴍᴏᴠᴇ 𝐋ᴀsᴛ", f"merge {uid} remove_last")
    btns.ibutton("❌ 𝐂ᴀɴᴄᴇʟ", f"merge {uid} cancel")
    return text, btns.build_menu(2)


async def _clear_session(uid: int):
    session = merge_sessions.pop(uid, None)
    if not session:
        return
    for key in ("menu_msg", "ask_msg"):
        if session.get(key):
            try:
                await deleteMessage(session[key])
            except Exception:
                pass


# ── /startmerge command ───────────────────────────────────────────────────────

@new_task
async def start_merge(client, message):
    uid = message.from_user.id
    user_dict = user_data.get(uid, {})

    if not user_dict.get("merge_video", False):
        return await sendMessage(
            message,
            "⚠️ <b>𝐌ᴇʀɢᴇ 𝐕ɪᴅᴇᴏ</b> ɪs ᴅɪsᴀʙʟᴇᴅ!\n\n"
            f"𝐄ɴᴀʙʟᴇ ɪᴛ: <code>/{BotCommands.UserSetCommand[0]}</code> "
            "→ 𝐋ᴇᴇᴄʜ 𝐒ᴇᴛᴛɪɴɢs → 🎞️ 𝐌ᴇʀɢᴇ 𝐕ɪᴅᴇᴏ ✅",
        )

    # Reset any stale session
    if uid in merge_sessions:
        await _clear_session(uid)

    btns = ButtonMaker()
    for k, label in MODES.items():
        btns.ibutton(label, f"merge {uid} mode {k}")
    btns.ibutton("❌ 𝐂ᴀɴᴄᴇʟ", f"merge {uid} cancel")

    text = (
        "🎞️ <b><u>𝐌ᴇʀɢᴇ 𝐌ᴏᴅᴇ — 𝐒ᴇʟᴇᴄᴛ 𝐓ʏᴘᴇ</u></b>\n\n"
        "🎬 <b>Video + Video</b> — ᴄᴏɴᴄᴀᴛᴇɴᴀᴛᴇ ᴍᴜʟᴛɪᴘʟᴇ ᴠɪᴅᴇᴏs\n"
        "🎵 <b>Video + Audio</b> — ᴍᴜx ᴀᴜᴅɪᴏ ᴛʀᴀᴄᴋ ɪɴᴛᴏ ᴠɪᴅᴇᴏ\n"
        "📝 <b>Video + Subtitles</b> — ᴇᴍʙᴇᴅ sᴜʙs ɪɴᴛᴏ ᴠɪᴅᴇᴏ\n"
        "🗜️ <b>Zip Merge</b> — ᴘᴀᴄᴋ ᴀʟʟ ғɪʟᴇs ɪɴᴛᴏ ᴀ ZIP"
    )
    menu = await sendMessage(message, text, btns.build_menu(2))
    merge_sessions[uid] = {
        "mode": None,
        "queue": [],
        "menu_msg": menu,
        "step": "mode",
        "chat_id": message.chat.id,
        "orig_msg": message,
        "ask_msg": None,
    }


# ── Callback query handler ────────────────────────────────────────────────────

@new_task
async def merge_callback(client, query):
    data = query.data.split()
    uid = int(data[1])
    action = data[2]

    if query.from_user.id != uid:
        return await query.answer("𝐍ᴏᴛ 𝐘ᴏᴜʀs!", show_alert=True)

    session = merge_sessions.get(uid)
    if not session and action != "cancel":
        return await query.answer("𝐒ᴇssɪᴏɴ ᴇxᴘɪʀᴇᴅ!", show_alert=True)

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
        text, markup = _queue_menu(uid, mode, session["queue"])
        await editMessage(query.message, text, markup)
        return

    # ── Remove last item ───────────────────────────────────────────────────
    if action == "remove_last":
        if session["queue"]:
            session["queue"].pop()
        text, markup = _queue_menu(uid, session["mode"], session["queue"])
        await editMessage(query.message, text, markup)
        return

    # ── Merge Now ──────────────────────────────────────────────────────────
    if action == "start":
        if not session["queue"]:
            return await query.answer("𝐐ᴜᴇᴜᴇ ɪs ᴇᴍᴘᴛʏ!", show_alert=True)
        if session["step"] == "await_name":
            return
        session["step"] = "await_name"
        ask = await sendMessage(
            session["orig_msg"],
            "📝 <b>𝐄ɴᴛᴇʀ 𝐎ᴜᴛᴘᴜᴛ 𝐅ɪʟᴇɴᴀᴍᴇ</b> <i>(ᴡɪᴛʜᴏᴜᴛ ᴇxᴛᴇɴsɪᴏɴ)</i>\n\n"
            "ᴏʀ sᴇɴᴅ <code>skip</code> ᴛᴏ ᴜsᴇ ᴀᴜᴛᴏ-ɴᴀᴍᴇ.\n\n"
            "⏱ <b>𝐓ɪᴍᴇᴏᴜᴛ: 60s</b>",
        )
        session["ask_msg"] = ask
        return


# ── Message handler — collect files/links or capture output filename ──────────

@new_task
async def merge_message_handler(client, message):
    uid = message.from_user.id
    session = merge_sessions.get(uid)
    if not session or message.chat.id != session["chat_id"]:
        return

    # ── Capture output filename ────────────────────────────────────────────
    if session["step"] == "await_name":
        raw = (message.text or "").strip()
        out_name = re.sub(r'[\\/:*?"<>|]', "_", raw) if raw and raw.lower() != "skip" else ""
        try:
            await deleteMessage(session.get("ask_msg"))
        except Exception:
            pass
        await deleteMessage(message)
        # Hand off to existing download infrastructure
        await _dispatch_all_downloads(client, uid, session, out_name)
        return

    # ── Collect files / links ──────────────────────────────────────────────
    if session["step"] != "collect":
        return

    item = None
    if message.text:
        url = message.text.strip()
        if (
            is_url(url)
            or is_magnet(url)
            or is_gdrive_link(url)
            or is_mega_link(url)
            or is_rclone_path(url)
            or is_telegram_link(url)
        ):
            item = {"label": url, "type": "url", "data": url, "msg": message}
    elif message.document or message.video or message.audio:
        media = message.document or message.video or message.audio
        fname = getattr(media, "file_name", None) or f"file_{message.id}"
        item = {"label": fname, "type": "tgfile", "data": fname, "msg": message}

    if item:
        session["queue"].append(item)
        await deleteMessage(message)
        text, markup = _queue_menu(uid, session["mode"], session["queue"])
        await editMessage(session["menu_msg"], text, markup)


# ── Core: dispatch all downloads via existing MirrorLeechListener pipeline ─────

async def _dispatch_all_downloads(client, uid: int, session: dict, out_name: str):
    """
    Creates a shared sameDir dict and one MirrorLeechListener per queued item,
    then dispatches each to the appropriate existing downloader.

    The existing onDownloadComplete logic in tasks_listener will:
      - Move files from each completed task into the last task's directory
      - When all tasks finish → call _do_folder_merge (vv/va/vs) or compress (zip)
      - Upload via existing TgUploader / rclone pipeline
      - Show progress in /status
    """
    mode = session["mode"]
    queue = session["queue"]
    orig_msg = session["orig_msg"]

    # Clear menu before dispatching
    try:
        await deleteMessage(session["menu_msg"])
    except Exception:
        pass
    merge_sessions.pop(uid, None)

    # Auto-disable merge_video after session ends
    from bot.helper.ext_utils.bot_utils import update_user_ldata
    from bot import DATABASE_URL
    update_user_ldata(uid, "merge_video", False)
    if DATABASE_URL:
        try:
            from bot.helper.ext_utils.db_handler import DbManger
            await DbManger().update_user_data(uid)
        except Exception:
            pass

    total = len(queue)
    is_zip = (mode == "zip")

    # folder_name is a subdirectory under each task's DOWNLOAD_DIR/{uid}/
    # For zip, use out_name as the folder so 7z names the archive correctly.
    if is_zip and out_name:
        folder_name = f"/{out_name}"
    else:
        folder_name = f"/merge_{orig_msg.id}"

    # shared_sameDir ties all listeners together (same object reference)
    shared_sameDir = {
        "total": total,
        "tasks": {item["msg"].id for item in queue},
        "name": folder_name,
        "merge_mode": mode,       # read by _do_folder_merge in tasks_listener
    }

    tag = (
        f"@{orig_msg.from_user.username}"
        if orig_msg.from_user.username
        else orig_msg.from_user.mention
    )

    for item in queue:
        msg = item["msg"]
        # path INCLUDES folder_name → files land in the correct sameDir subfolder
        path = f"{DOWNLOAD_DIR}{msg.id}{folder_name}"

        listener = MirrorLeechListener(
            msg,
            compress=is_zip,       # zip mode → existing 7z logic
            isLeech=True,
            tag=tag,
            sameDir=shared_sameDir,
            merge_video=(not is_zip),   # vv/va/vs → _do_folder_merge
            merge_output_name=(out_name if not is_zip else ""),
        )

        if item["type"] == "tgfile":
            # msg itself IS the Telegram file message
            await TelegramDownloadHelper(listener).add_download(
                msg, f"{path}/", "", "", None
            )
        else:
            url = item["data"]
            if is_gdrive_link(url):
                await add_gd_download(url, path, listener, "", url)
            elif is_mega_link(url):
                await add_mega_download(url, f"{path}/", listener, "")
            else:
                # http URLs, magnets, direct links → aria2c
                await add_aria2c_download(url, path, listener, "", "", None, None)

        LOGGER.info(f"[MERGE] Dispatched item: {item['label'][:60]} (uid={msg.id})")


# ── Dynamic filter: catch messages only from users in active merge session ─────

async def _is_merge_user(_, __, message):
    if not message.from_user:
        return False
    uid = message.from_user.id
    s = merge_sessions.get(uid)
    if not s:
        return False
    if message.chat.id != s["chat_id"]:
        return False
    return s["step"] in ("collect", "await_name")


merge_user_filter = pyro_create(_is_merge_user)


# ── Handler registration (called from bot/__main__.py) ────────────────────────

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
