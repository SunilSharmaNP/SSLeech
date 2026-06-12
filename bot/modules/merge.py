#!/usr/bin/env python3
"""
Merge Module — /startmerge{suffix} command
Supported modes:
  vv  → Video + Video   (concatenate multiple videos)
  va  → Video + Audio   (mux custom audio track into video)
  vs  → Video + Subs    (embed subtitle file into video)
  zip → Zip Merge       (combine files into a ZIP archive)

Flow:
  1. User enables "🎞️ Merge Video" in Leech Settings
  2. /startmerge → mode selection menu
  3. User selects mode → Done
  4. Bot prompts for files/links one by one → each added to queue
  5. User presses "⚡ Merge Now" → download → merge → ask filename → upload
  6. After completion → merge mode auto-exits
"""

import os
import zipfile
import shutil
from asyncio import sleep, create_subprocess_exec, wait_for, TimeoutError as ATimeoutError
from asyncio.subprocess import PIPE
from os import path as ospath, getcwd
from time import time

from pyrogram.handlers import MessageHandler, CallbackQueryHandler
from pyrogram.filters import command, regex, create as pyro_create
from aiofiles.os import makedirs as aio_makedirs, path as aiopath, remove as aioremove

from bot import (
    bot, DOWNLOAD_DIR, LOGGER, config_dict, user_data,
    RCLONE_PATH, BinConfig,
)
from bot.helper.telegram_helper.bot_commands import BotCommands
from bot.helper.telegram_helper.filters import CustomFilters
from bot.helper.telegram_helper.button_build import ButtonMaker
from bot.helper.telegram_helper.message_utils import sendMessage, editMessage, deleteMessage
from bot.helper.ext_utils.bot_utils import (
    new_task, sync_to_async, get_readable_file_size, is_url,
    is_telegram_link, is_rclone_path,
)
from bot.helper.ext_utils.video_merge import merge_video_files


# ── Per-user session state ────────────────────────────────────────────────────
# merge_sessions[user_id] = {
#   "mode":       str,     "vv" | "va" | "vs" | "zip"
#   "queue":      list,    [{"label": str, "type": "url"|"tgfile", "data": str|Message}]
#   "status_msg": Message,
#   "step":       str,     "select_mode" | "collect" | "await_name" | "processing"
#   "chat_id":    int,
#   "orig_msg":   Message,
# }
merge_sessions: dict = {}

# ── Mode metadata ─────────────────────────────────────────────────────────────
MODES = {
    "vv":  "🎬 𝐕ɪᴅᴇᴏ + 𝐕ɪᴅᴇᴏ",
    "va":  "🎵 𝐕ɪᴅᴇᴏ + 𝐀ᴜᴅɪᴏ",
    "vs":  "📝 𝐕ɪᴅᴇᴏ + 𝐒ᴜʙᴛɪᴛʟᴇs",
    "zip": "🗜️ 𝐙ɪᴘ 𝐌ᴇʀɢᴇ",
}

MODE_HINTS = {
    "vv":  (
        "➲ 𝐒ᴇɴᴅ ᴠɪᴅᴇᴏ ʟɪɴᴋs ᴏʀ ᴜᴘʟᴏᴀᴅ ᴠɪᴅᴇᴏs ᴏɴᴇ ʙʏ ᴏɴᴇ.\n"
        "➲ 𝐓ʜᴇʏ ᴡɪʟʟ ʙᴇ ᴄᴏɴᴄᴀᴛᴇɴᴀᴛᴇᴅ ɪɴ ᴏʀᴅᴇʀ."
    ),
    "va":  (
        "➲ <b>𝐅ɪʀsᴛ:</b> 𝐒ᴇɴᴅ ᴛʜᴇ 𝐯ɪᴅᴇᴏ ʟɪɴᴋ/ғɪʟᴇ.\n"
        "➲ <b>𝐓ʜᴇɴ:</b> 𝐒ᴇɴᴅ ᴛʜᴇ 𝐚ᴜᴅɪᴏ ʟɪɴᴋ/ғɪʟᴇ."
    ),
    "vs":  (
        "➲ <b>𝐅ɪʀsᴛ:</b> 𝐒ᴇɴᴅ ᴛʜᴇ 𝐯ɪᴅᴇᴏ ʟɪɴᴋ/ғɪʟᴇ.\n"
        "➲ <b>𝐓ʜᴇɴ:</b> 𝐒ᴇɴᴅ ᴛʜᴇ .srt / .ass ʟɪɴᴋ/ғɪʟᴇ."
    ),
    "zip": (
        "➲ 𝐒ᴇɴᴅ ᴀɴʏ ʟɪɴᴋs ᴏʀ ᴜᴘʟᴏᴀᴅ ғɪʟᴇs ᴏɴᴇ ʙʏ ᴏɴᴇ.\n"
        "➲ 𝐀ʟʟ ᴡɪʟʟ ʙᴇ ᴢɪᴘᴘᴇᴅ ᴛᴏɢᴇᴛʜᴇʀ."
    ),
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _collect_menu(user_id: int, mode: str, queue: list) -> tuple:
    """Build the file-collection menu text + buttons."""
    mode_label = MODES[mode]
    hint = MODE_HINTS[mode]

    queue_lines = ""
    for i, item in enumerate(queue, 1):
        queue_lines += f"\n  {i}. <code>{item['label'][:60]}</code>"

    text = (
        f"🎞️ <b><u>𝐌ᴇʀɢᴇ 𝐌ᴏᴅᴇ 𝐀ᴄᴛɪᴠᴇ — {mode_label}</u></b>\n\n"
        f"{hint}\n\n"
        f"📋 <b>𝐐ᴜᴇᴜᴇ ({len(queue)} ɪᴛᴇᴍ{'s' if len(queue) != 1 else ''}):</b>"
        + (queue_lines if queue else "\n  <i>ᴇᴍᴘᴛʏ — sᴇɴᴅ ʏᴏᴜʀ ғɪʟᴇs/ʟɪɴᴋs ɴᴏᴡ</i>")
        + "\n"
    )

    btns = ButtonMaker()
    if queue:
        btns.ibutton("⚡ 𝐌ᴇʀɢᴇ 𝐍ᴏᴡ", f"merge {user_id} start")
    if len(queue) > 0:
        btns.ibutton("🗑 𝐑ᴇᴍᴏᴠᴇ 𝐋ᴀsᴛ", f"merge {user_id} remove_last")
    btns.ibutton("❌ 𝐂ᴀɴᴄᴇʟ", f"merge {user_id} cancel")
    return text, btns.build_menu(2)


async def _end_session(user_id: int, reason: str = ""):
    """Clean up session and disable merge mode for the user."""
    session = merge_sessions.pop(user_id, None)
    if not session:
        return
    try:
        await deleteMessage(session["status_msg"])
    except Exception:
        pass

    if reason:
        try:
            await sendMessage(session["orig_msg"], reason)
        except Exception:
            pass

    # Auto-disable merge_video in user settings
    from bot.helper.ext_utils.bot_utils import update_user_ldata
    from bot import DATABASE_URL
    update_user_ldata(user_id, "merge_video", False)
    if DATABASE_URL:
        try:
            from bot.helper.ext_utils.db_handler import DbManger
            await DbManger().update_user_data(user_id)
        except Exception:
            pass


# ── /startmerge command ───────────────────────────────────────────────────────

@new_task
async def start_merge(client, message):
    user_id = message.from_user.id
    user_dict = user_data.get(user_id, {})

    if not user_dict.get("merge_video", False):
        return await sendMessage(
            message,
            "⚠️ <b>𝐌ᴇʀɢᴇ 𝐕ɪᴅᴇᴏ 𝐃ɪsᴀʙʟᴇᴅ!</b>\n\n"
            "𝐏ʟᴇᴀsᴇ ᴇɴᴀʙʟᴇ <b>🎞️ 𝐌ᴇʀɢᴇ 𝐕ɪᴅᴇᴏ</b> ɪɴ ʏᴏᴜʀ <b>𝐋ᴇᴇᴄʜ 𝐒ᴇᴛᴛɪɴɢs</b> ғɪʀsᴛ.\n\n"
            f"➲ 𝐔sᴇ: <code>/{BotCommands.UserSetCommand[0]}</code> → 𝐋ᴇᴇᴄʜ 𝐒ᴇᴛᴛɪɴɢs → 🎞️ 𝐌ᴇʀɢᴇ 𝐕ɪᴅᴇᴏ ✅"
        )

    # Clear any existing session
    if user_id in merge_sessions:
        old = merge_sessions.pop(user_id)
        try:
            await deleteMessage(old["status_msg"])
        except Exception:
            pass

    # Show mode selection
    btns = ButtonMaker()
    for key, label in MODES.items():
        btns.ibutton(label, f"merge {user_id} mode {key}")
    btns.ibutton("❌ 𝐂ᴀɴᴄᴇʟ", f"merge {user_id} cancel")

    text = (
        "🎞️ <b><u>𝐌ᴇʀɢᴇ 𝐌ᴏᴅᴇ — 𝐒ᴇʟᴇᴄᴛ 𝐓ʏᴘᴇ</u></b>\n\n"
        "𝐂ʜᴏᴏsᴇ ᴡʜᴀᴛ ʏᴏᴜ ᴡᴀɴᴛ ᴛᴏ ᴍᴇʀɢᴇ:\n\n"
        "🎬 <b>𝐕ɪᴅᴇᴏ + 𝐕ɪᴅᴇᴏ</b> — Cᴏɴᴄᴀᴛᴇɴᴀᴛᴇ ᴍᴜʟᴛɪᴘʟᴇ ᴠɪᴅᴇᴏs\n"
        "🎵 <b>𝐕ɪᴅᴇᴏ + 𝐀ᴜᴅɪᴏ</b> — Mᴇʀɢᴇ ᴀᴜᴅɪᴏ ᴛʀᴀᴄᴋ ɪɴᴛᴏ ᴠɪᴅᴇᴏ\n"
        "📝 <b>𝐕ɪᴅᴇᴏ + 𝐒ᴜʙᴛɪᴛʟᴇs</b> — Eᴍʙᴇᴅ sᴜʙᴛɪᴛʟᴇs ɪɴᴛᴏ ᴠɪᴅᴇᴏ\n"
        "🗜️ <b>𝐙ɪᴘ 𝐌ᴇʀɢᴇ</b> — Cᴏᴍʙɪɴᴇ ғɪʟᴇs ɪɴᴛᴏ ᴀ ZIP"
    )

    status_msg = await sendMessage(message, text, btns.build_menu(2))
    merge_sessions[user_id] = {
        "mode": None,
        "queue": [],
        "status_msg": status_msg,
        "step": "select_mode",
        "chat_id": message.chat.id,
        "orig_msg": message,
    }


# ── Callback handler ──────────────────────────────────────────────────────────

@new_task
async def merge_callback(client, query):
    data = query.data.split()
    # data: ["merge", user_id, action, ...]
    if len(data) < 3:
        return await query.answer()

    user_id = int(data[1])
    action = data[2]

    if query.from_user.id != user_id:
        return await query.answer("𝐍ᴏᴛ 𝐘ᴏᴜʀs!", show_alert=True)

    session = merge_sessions.get(user_id)
    if not session and action != "cancel":
        return await query.answer("𝐒ᴇssɪᴏɴ ᴇxᴘɪʀᴇᴅ!", show_alert=True)

    await query.answer()

    # ── Cancel ────────────────────────────────────────────────────────────────
    if action == "cancel":
        await _end_session(user_id)
        try:
            await deleteMessage(query.message)
        except Exception:
            pass
        return await sendMessage(
            session["orig_msg"] if session else query.message,
            "❌ <b>𝐌ᴇʀɢᴇ 𝐬ᴇssɪᴏɴ ᴄᴀɴᴄᴇʟʟᴇᴅ.</b>\n\n"
            "🎞️ 𝐌ᴇʀɢᴇ 𝐕ɪᴅᴇᴏ ʜᴀs ʙᴇᴇɴ 𝐚ᴜᴛᴏ-ᴅɪsᴀʙʟᴇᴅ ɪɴ ʏᴏᴜʀ Leech Settings."
        )

    # ── Mode selection ────────────────────────────────────────────────────────
    if action == "mode" and len(data) == 4:
        mode = data[3]
        if mode not in MODES:
            return
        session["mode"] = mode
        session["step"] = "collect"

        text, markup = _collect_menu(user_id, mode, session["queue"])
        await editMessage(query.message, text, markup)
        return

    # ── Remove last item ──────────────────────────────────────────────────────
    if action == "remove_last":
        if session["queue"]:
            removed = session["queue"].pop()
            text, markup = _collect_menu(user_id, session["mode"], session["queue"])
            await editMessage(query.message, text, markup)
        return

    # ── Start merge ───────────────────────────────────────────────────────────
    if action == "start":
        if not session["queue"]:
            return await query.answer("𝐐ᴜᴇᴜᴇ ɪs ᴇᴍᴘᴛʏ!", show_alert=True)
        if session["step"] == "processing":
            return await query.answer("𝐀ʟʀᴇᴀᴅʏ ᴘʀᴏᴄᴇssɪɴɢ!", show_alert=True)

        session["step"] = "processing"
        await editMessage(
            query.message,
            "⏳ <b>𝐈ɴɪᴛɪᴀᴛɪɴɢ 𝐌ᴇʀɢᴇ...</b>\n\n"
            f"➲ 𝐌ᴏᴅᴇ: {MODES[session['mode']]}\n"
            f"➲ 𝐅ɪʟᴇs: {len(session['queue'])}",
        )

        # Ask for output filename before processing
        session["step"] = "await_name"
        session["status_msg"] = query.message
        ask = await sendMessage(
            session["orig_msg"],
            "📝 <b>𝐄ɴᴛᴇʀ 𝐎ᴜᴛᴘᴜᴛ 𝐅ɪʟᴇɴᴀᴍᴇ</b>\n\n"
            "𝐒ᴇɴᴅ ᴛʜᴇ ᴅᴇsɪʀᴇᴅ ᴏᴜᴛᴘᴜᴛ ɴᴀᴍᴇ <i>(ᴡɪᴛʜᴏᴜᴛ ᴇxᴛᴇɴsɪᴏɴ)</i>.\n"
            "𝐎ʀ sᴇɴᴅ <code>skip</code> ᴛᴏ ᴜsᴇ ᴀᴜᴛᴏ ɴᴀᴍᴇ.\n\n"
            "<b>⏱ Tɪᴍᴇᴏᴜᴛ:</b> 60 𝐒ᴇᴄ"
        )
        session["ask_name_msg"] = ask
        return


# ── Message handler — collect files OR capture filename ────────────────────────

@new_task
async def merge_message_handler(client, message):
    user_id = message.from_user.id
    session = merge_sessions.get(user_id)
    if not session:
        return
    if message.chat.id != session["chat_id"]:
        return

    # ── Await output filename ─────────────────────────────────────────────────
    if session["step"] == "await_name":
        try:
            await deleteMessage(session.get("ask_name_msg"))
        except Exception:
            pass

        raw_name = (message.text or "").strip()
        if not raw_name or raw_name.lower() == "skip":
            out_name = f"merged_{int(time())}"
        else:
            # Sanitise filename
            import re
            out_name = re.sub(r'[\\/:*?"<>|]', "_", raw_name)

        await deleteMessage(message)
        session["step"] = "processing"
        session["out_name"] = out_name
        await _run_merge(client, user_id, session)
        return

    # ── Collect phase: accept URLs or forwarded/uploaded files ────────────────
    if session["step"] != "collect":
        return

    item = None

    if message.text:
        url = message.text.strip()
        if is_url(url) or is_telegram_link(url) or is_rclone_path(url):
            item = {"label": url, "type": "url", "data": url}
        else:
            return

    elif message.document or message.video or message.audio:
        media = message.document or message.video or message.audio
        fname = getattr(media, "file_name", None) or f"file_{int(time())}"
        item = {"label": fname, "type": "tgfile", "data": message}

    if item:
        session["queue"].append(item)
        await deleteMessage(message)
        text, markup = _collect_menu(user_id, session["mode"], session["queue"])
        await editMessage(session["status_msg"], text, markup)


# ── Core processing ───────────────────────────────────────────────────────────

async def _run_merge(client, user_id: int, session: dict):
    mode = session["mode"]
    queue = session["queue"]
    out_name = session.get("out_name", f"merged_{int(time())}")
    orig_msg = session["orig_msg"]
    status_msg = session["status_msg"]

    work_dir = ospath.join(DOWNLOAD_DIR, f"merge_{user_id}_{int(time())}")
    os.makedirs(work_dir, exist_ok=True)

    try:
        # ── Step 1: Status update ─────────────────────────────────────────────
        await editMessage(
            status_msg,
            f"📥 <b>𝐃ᴏᴡɴʟᴏᴀᴅɪɴɢ {len(queue)} ɪᴛᴇᴍ{'s' if len(queue) != 1 else ''}...</b>\n\n"
            f"➲ 𝐌ᴏᴅᴇ: {MODES[mode]}\n"
            "➲ 𝐏ʟᴇᴀsᴇ ᴡᴀɪᴛ..."
        )

        # ── Step 2: Download all items ─────────────────────────────────────────
        downloaded_paths = []
        for idx, item in enumerate(queue, 1):
            await editMessage(
                status_msg,
                f"📥 <b>𝐃ᴏᴡɴʟᴏᴀᴅɪɴɢ [{idx}/{len(queue)}]</b>\n\n"
                f"➲ <code>{item['label'][:80]}</code>"
            )
            local_path = await _download_item(item, work_dir, idx)
            if not local_path:
                raise ValueError(f"Failed to download item {idx}: {item['label']}")
            downloaded_paths.append(local_path)
            LOGGER.info(f"[MERGE] Downloaded [{idx}/{len(queue)}]: {local_path}")

        # ── Step 3: Merge ──────────────────────────────────────────────────────
        await editMessage(
            status_msg,
            f"⚙️ <b>𝐌ᴇʀɢɪɴɢ {len(downloaded_paths)} ɪᴛᴇᴍ{'s' if len(downloaded_paths) != 1 else ''}...</b>\n\n"
            f"➲ 𝐌ᴏᴅᴇ: {MODES[mode]}\n"
            f"➲ 𝐎ᴜᴛᴘᴜᴛ: <code>{out_name}</code>"
        )

        output_path = await _do_merge(mode, downloaded_paths, work_dir, out_name)
        if not output_path or not ospath.exists(output_path):
            raise ValueError("Merge failed — output file not created.")

        file_size = os.path.getsize(output_path)
        LOGGER.info(f"[MERGE] Output ready: {output_path} ({get_readable_file_size(file_size)})")

        # ── Step 4: Upload ─────────────────────────────────────────────────────
        await editMessage(
            status_msg,
            f"📤 <b>𝐔ᴘʟᴏᴀᴅɪɴɢ...</b>\n\n"
            f"➲ <code>{ospath.basename(output_path)}</code>\n"
            f"➲ 𝐒ɪᴢᴇ: {get_readable_file_size(file_size)}"
        )

        await _upload_result(client, orig_msg, user_id, output_path, status_msg)

    except Exception as e:
        LOGGER.error(f"[MERGE] Error for user {user_id}: {e}")
        await editMessage(
            status_msg,
            f"❌ <b>𝐌ᴇʀɢᴇ 𝐅ᴀɪʟᴇᴅ!</b>\n\n➲ <code>{e}</code>"
        )
    finally:
        # Cleanup temp dir
        try:
            shutil.rmtree(work_dir, ignore_errors=True)
        except Exception:
            pass

        # End session and auto-disable merge mode
        msg = (
            "✅ <b>𝐌ᴇʀɢᴇ 𝐂ᴏᴍᴘʟᴇᴛᴇᴅ!</b>\n\n"
            "🎞️ <b>𝐌ᴇʀɢᴇ 𝐕ɪᴅᴇᴏ</b> ʜᴀs ʙᴇᴇɴ <b>ᴀᴜᴛᴏ-ᴅɪsᴀʙʟᴇᴅ</b>.\n"
            "𝐘ᴏᴜ ᴄᴀɴ ɴᴏᴡ ᴜsᴇ ɴᴏʀᴍᴀʟ 𝐋ᴇᴇᴄʜ/𝐌ɪʀʀᴏʀ ᴄᴏᴍᴍᴀɴᴅs."
        )
        merge_sessions.pop(user_id, None)
        from bot.helper.ext_utils.bot_utils import update_user_ldata
        from bot import DATABASE_URL
        update_user_ldata(user_id, "merge_video", False)
        if DATABASE_URL:
            try:
                from bot.helper.ext_utils.db_handler import DbManger
                await DbManger().update_user_data(user_id)
            except Exception:
                pass
        try:
            await deleteMessage(status_msg)
        except Exception:
            pass
        await sendMessage(orig_msg, msg)


async def _download_item(item: dict, work_dir: str, idx: int) -> str | None:
    """Download a single queue item into work_dir. Returns local path or None."""
    try:
        if item["type"] == "tgfile":
            tg_message = item["data"]
            dest = ospath.join(work_dir, f"item_{idx:03d}_{_safe_fname(item['label'])}")
            path = await tg_message.download(file_name=dest)
            return path

        elif item["type"] == "url":
            url = item["data"]
            dest_name = f"item_{idx:03d}_{_url_filename(url)}"
            dest = ospath.join(work_dir, dest_name)
            cmd = [
                BinConfig.ARIA2_NAME,
                "--allow-overwrite=true",
                "--auto-file-renaming=false",
                "--max-connection-per-server=16",
                "--split=16",
                "--min-split-size=10M",
                f"--dir={work_dir}",
                f"--out={dest_name}",
                url,
            ]
            proc = await create_subprocess_exec(*cmd, stdout=PIPE, stderr=PIPE)
            await proc.communicate()
            if proc.returncode == 0 and ospath.exists(dest):
                return dest
            # Fallback: wget-style via aiohttp
            return await _aiohttp_download(url, dest)
    except Exception as e:
        LOGGER.error(f"[MERGE] Download failed for item {idx}: {e}")
        return None


async def _aiohttp_download(url: str, dest: str) -> str | None:
    """Simple streaming download fallback using aiohttp."""
    try:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=3600)) as resp:
                if resp.status != 200:
                    return None
                with open(dest, "wb") as f:
                    async for chunk in resp.content.iter_chunked(1024 * 1024):
                        f.write(chunk)
        return dest if ospath.exists(dest) else None
    except Exception as e:
        LOGGER.error(f"[MERGE] aiohttp download failed: {e}")
        return None


def _safe_fname(name: str) -> str:
    import re
    return re.sub(r'[\\/:*?"<>|\s]+', "_", name)[:80]


def _url_filename(url: str) -> str:
    from urllib.parse import urlparse, unquote
    path = urlparse(url).path
    name = unquote(ospath.basename(path)) or "file"
    return _safe_fname(name)


async def _do_merge(mode: str, paths: list, work_dir: str, out_name: str) -> str | None:
    """Perform the actual merge operation. Returns output file path."""

    if mode == "vv":
        # Video + Video: concatenate
        ext = ".mkv"
        output = ospath.join(work_dir, f"{out_name}{ext}")
        ok = await merge_video_files(paths, output)
        return output if ok else None

    elif mode == "va":
        # Video + Audio: mux first two items
        if len(paths) < 2:
            raise ValueError("𝐍ᴇᴇᴅ ᴀᴛ ʟᴇᴀsᴛ 1 ᴠɪᴅᴇᴏ + 1 ᴀᴜᴅɪᴏ ғɪʟᴇ.")
        video = paths[0]
        audio = paths[1]
        output = ospath.join(work_dir, f"{out_name}.mkv")
        cmd = [
            BinConfig.FFMPEG_NAME, "-y",
            "-i", video,
            "-i", audio,
            "-map", "0:v:0",
            "-map", "1:a:0",
            "-c:v", "copy",
            "-c:a", "aac",
            "-shortest",
            output,
        ]
        proc = await create_subprocess_exec(*cmd, stdout=PIPE, stderr=PIPE)
        _, stderr = await proc.communicate()
        if proc.returncode == 0:
            return output
        LOGGER.error(f"[MERGE] VA merge error: {stderr.decode()[-500:]}")
        return None

    elif mode == "vs":
        # Video + Subtitles: embed subs
        if len(paths) < 2:
            raise ValueError("𝐍ᴇᴇᴅ ᴀᴛ ʟᴇᴀsᴛ 1 ᴠɪᴅᴇᴏ + 1 sᴜʙᴛɪᴛʟᴇ ғɪʟᴇ.")
        video = paths[0]
        sub = paths[1]
        output = ospath.join(work_dir, f"{out_name}.mkv")
        cmd = [
            BinConfig.FFMPEG_NAME, "-y",
            "-i", video,
            "-i", sub,
            "-map", "0",
            "-map", "1",
            "-c", "copy",
            "-c:s", "ass",
            output,
        ]
        proc = await create_subprocess_exec(*cmd, stdout=PIPE, stderr=PIPE)
        _, stderr = await proc.communicate()
        if proc.returncode == 0:
            return output
        LOGGER.error(f"[MERGE] VS merge error: {stderr.decode()[-500:]}")
        return None

    elif mode == "zip":
        # Zip merge: pack everything into one ZIP
        output = ospath.join(work_dir, f"{out_name}.zip")
        await sync_to_async(_zip_files, paths, output)
        return output if ospath.exists(output) else None

    return None


def _zip_files(file_paths: list, output_zip: str):
    """Create a ZIP archive from a list of file paths (sync, run in executor)."""
    with zipfile.ZipFile(output_zip, "w", zipfile.ZIP_DEFLATED, allowZip64=True) as zf:
        for fp in file_paths:
            zf.write(fp, arcname=ospath.basename(fp))
    LOGGER.info(f"[MERGE] ZIP created: {output_zip}")


async def _upload_result(client, orig_msg, user_id: int, file_path: str, status_msg):
    """
    Upload the merged file.
    - If user has rclone config → upload via rclone to their configured path.
    - Otherwise → upload to Telegram (as document or video).
    """
    user_dict = user_data.get(user_id, {})
    rclone_conf = f"rclone/{user_id}.conf"
    # Prefer user's custom rclone destination, fall back to global RCLONE_PATH
    rclone_dest = user_dict.get("rclone_path", "") or config_dict.get("RCLONE_PATH", "") or RCLONE_PATH
    thumb_path = f"Thumbnails/{user_id}.jpg"
    has_thumb = ospath.exists(thumb_path)
    fname = ospath.basename(file_path)
    fsize = os.path.getsize(file_path)

    # ── Try rclone upload if configured ──────────────────────────────────────
    if ospath.exists(rclone_conf) and rclone_dest:
        await editMessage(
            status_msg,
            f"☁️ <b>𝐔ᴘʟᴏᴀᴅɪɴɢ ᴠɪᴀ 𝐑ᴄʟᴏɴᴇ...</b>\n➲ <code>{fname}</code>"
        )
        cmd = [
            BinConfig.RCLONE_NAME,
            f"--config={rclone_conf}",
            "copy",
            file_path,
            rclone_dest,
            "--progress",
        ]
        proc = await create_subprocess_exec(*cmd, stdout=PIPE, stderr=PIPE)
        _, stderr = await proc.communicate()
        if proc.returncode == 0:
            return await sendMessage(
                orig_msg,
                f"☁️ <b>𝐔ᴘʟᴏᴀᴅᴇᴅ ᴠɪᴀ 𝐑ᴄʟᴏɴᴇ!</b>\n\n"
                f"➲ <b>𝐅ɪʟᴇ:</b> <code>{fname}</code>\n"
                f"➲ <b>𝐒ɪᴢᴇ:</b> {get_readable_file_size(fsize)}\n"
                f"➲ <b>𝐃ᴇsᴛ:</b> <code>{rclone_dest}</code>"
            )
        LOGGER.warning(f"[MERGE] rclone upload failed: {stderr.decode()[-300:]}")

    # ── Telegram upload ───────────────────────────────────────────────────────
    send_as_doc = user_dict.get("as_doc", False)
    ext = ospath.splitext(fname)[1].lower()
    is_video = ext in {".mp4", ".mkv", ".avi", ".mov", ".flv", ".webm", ".m4v", ".ts"}

    thumb = thumb_path if has_thumb else None

    # Build caption with user prefix/suffix
    lprefix = user_dict.get("lprefix", "") or ""
    lsuffix = user_dict.get("lsuffix", "") or ""
    caption = f"{lprefix}{fname}{lsuffix}"
    if user_dict.get("lcaption"):
        caption = user_dict["lcaption"].format(filename=fname, size=get_readable_file_size(fsize))

    try:
        if not send_as_doc and is_video:
            await orig_msg.reply_video(
                file_path,
                caption=caption,
                thumb=thumb,
                supports_streaming=True,
            )
        else:
            await orig_msg.reply_document(
                file_path,
                caption=caption,
                thumb=thumb,
            )
        LOGGER.info(f"[MERGE] Telegram upload done: {fname}")
    except Exception as e:
        LOGGER.error(f"[MERGE] TG upload error: {e}")
        # If file is too large, try sending as document forcefully
        try:
            await orig_msg.reply_document(file_path, caption=caption, thumb=thumb)
        except Exception as e2:
            await sendMessage(
                orig_msg,
                f"⚠️ <b>𝐔ᴘʟᴏᴀᴅ 𝐅ᴀɪʟᴇᴅ!</b>\n\n➲ {e2}\n\n"
                f"𝐅ɪʟᴇ: <code>{fname}</code> ({get_readable_file_size(fsize)})"
            )


# ── Dynamic filter for message collection ─────────────────────────────────────

async def _is_merge_user(_, __, message):
    """Pyrogram create-filter: True if user has an active merge session."""
    if not message.from_user:
        return False
    uid = message.from_user.id
    session = merge_sessions.get(uid)
    if not session:
        return False
    if message.chat.id != session["chat_id"]:
        return False
    if session["step"] not in ("collect", "await_name"):
        return False
    return True


merge_user_filter = pyro_create(_is_merge_user)


# ── Module registration (called from __main__.py) ─────────────────────────────

def register_handlers(app):
    """Register all merge handlers. Called from bot/__main__.py."""
    app.add_handler(
        MessageHandler(
            start_merge,
            filters=command(BotCommands.StartMergeCommand) & CustomFilters.authorized & ~CustomFilters.blacklisted,
        )
    )
    app.add_handler(
        CallbackQueryHandler(merge_callback, filters=regex(r"^merge"))
    )
    app.add_handler(
        MessageHandler(merge_message_handler, filters=merge_user_filter),
        group=1,
    )
