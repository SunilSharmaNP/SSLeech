#!/usr/bin/env python3
from pyrogram.handlers import MessageHandler, CallbackQueryHandler
from pyrogram.filters import command, regex

from bot import bot, LOGGER, OWNER_ID, config_dict
from bot.helper.telegram_helper.message_utils import (
    sendMessage,
    editMessage,
    auto_delete_message,
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
)


@new_task
async def driveclean(_, message):
    args = message.text.split()
    if len(args) > 1:
        link = args[1].strip()
    elif reply_to := message.reply_to_message:
        link = reply_to.text.split(maxsplit=1)[0].strip()
    else:
        link = f"https://drive.google.com/drive/folders/{config_dict['GDRIVE_ID']}"
    if not is_gdrive_link(link):
        return await sendMessage(message, "𝐍ᴏ 𝐆ᴅʀɪᴠᴇ 𝐋ɪɴᴋ 𝐏ʀᴏᴠɪᴅᴇᴅ")
    clean_msg = await sendMessage(message, "<i>𝐅ᴇᴛᴄʜɪɴɢ ...</i>")
    gd = GoogleDriveHelper()
    name, mime_type, size, files, folders = await sync_to_async(gd.count, link)
    try:
        drive_id = GoogleDriveHelper.getIdFromUrl(link)
    except (KeyError, IndexError):
        return await editMessage(
            clean_msg, "𝐆ᴏᴏɢʟᴇ 𝐃ʀɪᴠᴇ 𝐈ᴅ ᴄᴏᴜʟᴅ ɴᴏᴛ ʙᴇ ғᴏᴜɴᴅ ɪɴ ᴛʜᴇ ᴘʀᴏᴠɪᴅᴇᴅ ʟɪɴᴋ"
        )
    buttons = ButtonMaker()
    buttons.ibutton("𝐌ᴏᴠᴇ ᴛᴏ 𝐁ɪɴ", f"gdclean clear {drive_id} trash")
    buttons.ibutton("𝐏ᴇʀᴍᴀɴᴇɴᴛ 𝐂ʟᴇᴀɴ", f"gdclean clear {drive_id}")
    buttons.ibutton("𝐒ᴛᴏᴘ 𝐆ᴅʀɪᴠᴇ 𝐂ʟᴇᴀɴ", "gdclean stop", "footer")
    await editMessage(
        clean_msg,
        f"""⌬ <b><i>𝐆ᴅʀɪᴠᴇ 𝐂ʟᴇᴀɴ/𝐓ʀᴀsʜ :</i></b>
    
┎ <b>𝐍ᴀᴍᴇ:</b> {name}
┃ <b>𝐒ɪᴢᴇ:</b> {get_readable_file_size(size)}
┖ <b>𝐅ɪʟᴇs:</b> {files} | <b>𝐅ᴏʟᴅᴇʀs:</b> {folders}
    
<b>𝐍ᴏᴛᴇs:</b>
<i>1. 𝐀ʟʟ ғɪʟᴇs ᴀʀᴇ ᴘᴇʀᴍᴀɴᴇɴᴛʟʏ ᴅᴇʟᴇᴛᴇᴅ ɪғ 𝐏ᴇʀᴍᴀɴᴇɴᴛ 𝐃ᴇʟ, ɴᴏᴛ ᴍᴏᴠᴇᴅ ᴛᴏ ᴛʀᴀsʜ.
2. 𝐅ᴏʟᴅᴇʀ ᴅᴏᴇsɴ'ᴛ ɢᴇᴛs 𝐃ᴇʟᴇᴛᴇᴅ.
3. 𝐃ᴇʟᴇᴛᴇ ғɪʟᴇs ᴏғ ᴄᴜsᴛᴏᴍ ғᴏʟᴅᴇʀ ᴠɪᴀ ɢɪᴠɪɴɢ ʟɪɴᴋ ᴀʟᴏɴɢ ᴡɪᴛʜ ᴄᴍᴅ, ʙᴜᴛ ɪᴛ sʜᴏᴜʟᴅ ʜᴀᴠᴇ ᴅᴇʟᴇᴛᴇ ᴘᴇʀᴍɪssɪᴏɴs.
4. 𝐌ᴏᴠᴇ ᴛᴏ 𝐁ɪɴ 𝐌ᴏᴠᴇs ᴀʟʟ ʏᴏᴜʀ ғɪʟᴇs ᴛᴏ ᴛʀᴀsʜ ʙᴜᴛ ᴄᴀɴ ʙᴇ ʀᴇsᴛᴏʀᴇᴅ ᴀɢᴀɪɴ ɪғ ʜᴀᴠᴇ ᴘᴇʀᴍɪssɪᴏɴs.</i>
    
<code>𝐂ʜᴏᴏsᴇ ᴛʜᴇ 𝐑ᴇϙᴜɪʀᴇᴅ 𝐀ᴄᴛɪᴏɴ ʙᴇʟᴏᴡ ᴛᴏ 𝐂ʟᴇᴀɴ ʏᴏᴜʀ 𝐃ʀɪᴠᴇ!</code>""",
        buttons.build_menu(2),
    )

@new_task
async def drivecleancb(_, query):
    message = query.message
    user_id = query.from_user.id
    data = query.data.split()
    if user_id != OWNER_ID:
        await query.answer(text="𝐍ᴏᴛ 𝐎ᴡɴᴇʀ!", show_alert=True)
        return
    if data[1] == "clear":
        await query.answer()
        await editMessage(message, "<i>𝐏ʀᴏᴄᴇssɪɴɢ 𝐃ʀɪᴠᴇ 𝐂ʟᴇᴀɴ / 𝐓ʀᴀsʜ...</i>")
        drive = GoogleDriveHelper()
        msg = await sync_to_async(drive.driveclean, data[2], trash=len(data) == 4)
        await editMessage(message, msg)
    elif data[1] == "stop":
        await query.answer()
        await editMessage(message, "⌬ <b>𝐃ʀɪᴠᴇ𝐂ʟᴇᴀɴ 𝐒ᴛᴏᴘᴘᴇᴅ!</b>")
        await auto_delete_message(message, message)


bot.add_handler(
    MessageHandler(
        driveclean, filters=command(BotCommands.GDCleanCommand) & CustomFilters.owner
    )
)
bot.add_handler(CallbackQueryHandler(drivecleancb, filters=regex(r"^gdclean")))
