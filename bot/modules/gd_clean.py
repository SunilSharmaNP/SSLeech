#!/usr/bin/env python3
from html import escape

from pyrogram.handlers import MessageHandler, CallbackQueryHandler
from pyrogram.filters import command, regex

from bot import bot, LOGGER, config_dict, categories_dict, user_data
from bot.helper.telegram_helper.message_utils import (
    sendMessage,
    editMessage,
)
from bot.helper.telegram_helper.filters import CustomFilters
from bot.helper.telegram_helper.bot_commands import BotCommands
from bot.helper.telegram_helper.button_build import ButtonMaker
from bot.helper.mirror_utils.upload_utils.gdriveTools import GoogleDriveHelper
from bot.helper.ext_utils.bot_utils import (
    sync_to_async,
    new_task,
    is_gdrive_link,
    get_readable_file_size,
    fetch_user_drive_categories,
)


# Destructive actions keep their state server-side instead of putting Drive IDs
# in callback data. This also keeps callbacks valid for long IDs and category
# names containing spaces.
_clean_sessions = {}


def _category_value(value):
    if isinstance(value, dict):
        return {
            "drive_id": str(value.get("drive_id", "")).strip(),
            "index_link": str(value.get("index_link", "")).strip(),
        }
    drive_id, _, index_link = str(value).partition("|")
    return {"drive_id": drive_id.strip(), "index_link": index_link.strip()}


async def _get_categories(user_id):
    settings = user_data.get(user_id, {})
    default_id = settings.get("GDRIVE_ID") or config_dict.get("GDRIVE_ID", "")
    default_index = settings.get("INDEX_URL") or config_dict.get("INDEX_URL", "")
    categories = {
        "Default": {"drive_id": default_id, "index_link": default_index}
    }
    for name, value in categories_dict.items():
        categories.setdefault(name, _category_value(value))
    user_categories = await fetch_user_drive_categories(user_id)
    for name, value in user_categories.items():
        categories[name] = _category_value(value)
    return {
        name: value
        for name, value in categories.items()
        if value.get("drive_id")
    }


async def _show_clean_prompt(message, drive_id, user_id, category_name=None):
    use_user_token = bool(
        category_name == "Default"
        and user_data.get(user_id, {}).get("GDRIVE_ID")
        or category_name
        and category_name in user_data.get(user_id, {}).get("DRIVE_CAT", {})
    )
    link = f"https://drive.google.com/drive/folders/{drive_id}"
    clean_msg = await sendMessage(message, "<i>𝐅ᴇᴛᴄʜɪɴɢ ...</i>")
    gd = GoogleDriveHelper(
        user_id=user_id if use_user_token else None,
        use_user_token=use_user_token,
    )
    name, mime_type, size, files, folders = await sync_to_async(gd.count, link)
    if mime_type is None:
        return await editMessage(clean_msg, name)

    _clean_sessions[clean_msg.id] = {
        "drive_id": drive_id,
        "user_id": user_id,
        "use_user_token": use_user_token,
    }
    buttons = ButtonMaker()
    buttons.ibutton(
        "🗑️ 𝐌ᴏᴠᴇ ᴛᴏ 𝐁ɪɴ",
        f"gdclean clear {clean_msg.id} trash",
    )
    buttons.ibutton(
        "🧹 𝐏ᴇʀᴍᴀɴᴇɴᴛ 𝐂ʟᴇᴀɴ",
        f"gdclean clear {clean_msg.id} delete",
    )
    buttons.ibutton(
        "🛑 𝐒ᴛᴏᴘ 𝐆ᴅʀɪᴠᴇ 𝐂ʟᴇᴀɴ",
        f"gdclean stop {clean_msg.id}",
        "footer",
    )
    await editMessage(
        clean_msg,
        f"""⌬ <b><i>𝐆ᴅʀɪᴠᴇ 𝐂ʟᴇᴀɴ / 𝐓ʀᴀsʜ:</i></b>

┎ <b>𝐍ᴀᴍᴇ:</b> {escape(str(name))}
┃ <b>𝐒ɪᴢᴇ:</b> {get_readable_file_size(size)}
┖ <b>𝐅ɪʟᴇs:</b> {files} | <b>𝐅ᴏʟᴅᴇʀs:</b> {folders}

<i>Permanent clean deletes files. Move to Bin keeps them restorable.</i>
<code>Choose the required action below.</code>""",
        buttons.build_menu(2),
    )


@new_task
async def driveclean(_, message):
    args = message.text.split() if message.text else []
    user_id = message.from_user.id
    category_name = None
    link = ""
    if "-gc" in args:
        category_index = args.index("-gc")
        category_name = " ".join(args[category_index + 1 :]).strip()
        if not category_name:
            return await sendMessage(
                message, "Use <code>-gc category_name</code> with a Drive category."
            )
    elif len(args) > 1:
        link = args[1].strip()
    elif reply_to := message.reply_to_message:
        reply_text = reply_to.text or reply_to.caption or ""
        link = reply_text.split(maxsplit=1)[0].strip() if reply_text else ""

    if category_name:
        categories = await _get_categories(user_id)
        selected = next(
            (
                value
                for name, value in categories.items()
                if name.casefold() == category_name.replace("_", " ").casefold()
            ),
            None,
        )
        if selected is None:
            return await sendMessage(
                message, f"Category <code>{escape(category_name)}</code> not found."
            )
        return await _show_clean_prompt(
            message,
            selected["drive_id"],
            user_id,
            next(
                name
                for name, value in categories.items()
                if value is selected
            ),
        )

    if link:
        if not is_gdrive_link(link):
            return await sendMessage(message, "𝐍ᴏ 𝐆ᴅʀɪᴠᴇ 𝐋ɪɴᴋ 𝐏ʀᴏᴠɪᴅᴇᴅ")
        try:
            drive_id = GoogleDriveHelper.getIdFromUrl(link)
        except (KeyError, IndexError, ValueError):
            return await sendMessage(
                message,
                "𝐆ᴏᴏɢʟᴇ 𝐃ʀɪᴠᴇ 𝐈ᴅ ᴄᴏᴜʟᴅ ɴᴏᴛ ʙᴇ ғᴏᴜɴᴅ.",
            )
        return await _show_clean_prompt(message, drive_id, user_id)

    categories = await _get_categories(user_id)
    if not categories:
        return await sendMessage(
            message,
            "No Drive category is configured. Use a Drive link or configure one in User Settings.",
        )
    picker = await sendMessage(message, "<b>Select a Drive category to clean:</b>")
    if not hasattr(picker, "id"):
        return
    _clean_sessions[picker.id] = {"user_id": user_id, "categories": categories}
    buttons = ButtonMaker()
    for index, name in enumerate(categories):
        buttons.ibutton(
            name,
            f"gdclean category {picker.id} {index}",
        )
    buttons.ibutton("❌ Cancel", f"gdclean stop {picker.id}", "footer")
    await editMessage(
        picker,
        "<b>Select a Drive category to clean:</b>",
        buttons.build_menu(2),
    )


@new_task
async def drivecleancb(_, query):
    data = query.data.split()
    if len(data) < 3:
        return await query.answer("Invalid clean session.", show_alert=True)
    session_id = int(data[2])
    session = _clean_sessions.get(session_id)
    if not session:
        return await query.answer("Clean session expired.", show_alert=True)
    if query.from_user.id != session["user_id"]:
        return await query.answer("Not yours!", show_alert=True)

    action = data[1]
    if action == "category":
        categories = session.get("categories", {})
        try:
            category_name = list(categories)[int(data[3])]
            selected = categories[category_name]
        except (IndexError, ValueError):
            return await query.answer("Invalid category.", show_alert=True)
        await query.answer()
        _clean_sessions.pop(session_id, None)
        return await _show_clean_prompt(
            query.message,
            selected["drive_id"],
            session["user_id"],
            category_name,
        )

    if action == "stop":
        _clean_sessions.pop(session_id, None)
        await query.answer()
        return await editMessage(
            query.message, "⌬ <b>𝐃ʀɪᴠᴇ 𝐂ʟᴇᴀɴ sᴛᴏᴘᴘᴇᴅ!</b>"
        )

    if action != "clear" or len(data) < 4:
        return await query.answer("Invalid clean action.", show_alert=True)
    mode = data[3]
    await query.answer()
    await editMessage(query.message, "<i>𝐏ʀᴏᴄᴇssɪɴɢ 𝐃ʀɪᴠᴇ 𝐂ʟᴇᴀɴ...</i>")
    drive = GoogleDriveHelper(
        user_id=session["user_id"] if session["use_user_token"] else None,
        use_user_token=session["use_user_token"],
    )
    result = await sync_to_async(
        drive.driveclean,
        session["drive_id"],
        trash=mode == "trash",
    )
    _clean_sessions.pop(session_id, None)
    await editMessage(query.message, result)


bot.add_handler(
    MessageHandler(
        driveclean,
        filters=command(BotCommands.GDCleanCommand)
        & CustomFilters.authorized
        & ~CustomFilters.blacklisted,
    )
)
bot.add_handler(CallbackQueryHandler(drivecleancb, filters=regex(r"^gdclean")))
