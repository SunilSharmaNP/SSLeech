#!/usr/bin/env python3
from random import choice
from pyrogram.handlers import MessageHandler, CallbackQueryHandler
from pyrogram.filters import command, regex

from bot import LOGGER, bot, config_dict
from bot.helper.mirror_utils.upload_utils.gdriveTools import GoogleDriveHelper
from bot.helper.telegram_helper.message_utils import (
    sendMessage,
    editMessage,
    delete_links,
)
from bot.helper.telegram_helper.filters import CustomFilters
from bot.helper.telegram_helper.bot_commands import BotCommands
from bot.helper.telegram_helper.button_build import ButtonMaker
from bot.helper.ext_utils.bot_utils import (
    sync_to_async,
    new_task,
    get_telegraph_list,
    checking_access,
)
from bot.helper.themes import BotTheme


async def list_buttons(user_id, isRecursive=True):
    buttons = ButtonMaker()
    buttons.ibutton("𝐎ɴʟʏ 𝐅ᴏʟᴅᴇʀs", f"list_types {user_id} folders {isRecursive}")
    buttons.ibutton("𝐎ɴʟʏ 𝐅ɪʟᴇs", f"list_types {user_id} files {isRecursive}")
    buttons.ibutton("𝐁ᴏᴛʜ", f"list_types {user_id} both {isRecursive}")
    buttons.ibutton(
        f"{'✅️' if isRecursive else ''} 𝐑ᴇᴄᴜʀsɪᴠᴇ",
        f"list_types {user_id} rec {isRecursive}",
    )
    buttons.ibutton("𝐂ᴀɴᴄᴇʟ", f"list_types {user_id} cancel")
    return buttons.build_menu(2)


async def _list_drive(key, message, user_id, item_type, isRecursive):
    LOGGER.info(f"GDrive List: {key}")
    gdrive = GoogleDriveHelper()
    telegraph_content, contents_no = await sync_to_async(
        gdrive.drive_list,
        key,
        isRecursive=isRecursive,
        itemType=item_type,
        userId=user_id,
    )
    if telegraph_content:
        try:
            button = await get_telegraph_list(telegraph_content)
        except Exception as e:
            await editMessage(message, e)
            return
        msg = BotTheme("LIST_FOUND", NO=contents_no, NAME=key)
        await editMessage(message, msg, button)
    else:
        await editMessage(message, BotTheme("LIST_NOT_FOUND", NAME=key))


@new_task
async def select_type(_, query):
    user_id = query.from_user.id
    message = query.message
    key = message.reply_to_message.text.split(maxsplit=1)[1].strip()
    data = query.data.split()
    if user_id != int(data[1]):
        return await query.answer(text="𝐍ᴏᴛ 𝐘ᴏᴜʀs!", show_alert=True)
    elif data[2] == "rec":
        await query.answer()
        isRecursive = not bool(eval(data[3]))
        buttons = await list_buttons(user_id, isRecursive)
        return await editMessage(message, "<b>𝐂ʜᴏᴏsᴇ ᴅʀɪᴠᴇ ʟɪsᴛ ᴏᴘᴛɪᴏɴs:</b>", buttons)
    elif data[2] == "cancel":
        await query.answer()
        return await editMessage(message, "<b>𝐋ɪsᴛ ʜᴀs ʙᴇᴇɴ ᴄᴀɴᴄᴇʟᴇᴅ!</b>")
    await query.answer()
    item_type = data[2]
    isRecursive = eval(data[3])
    await editMessage(message, BotTheme("LIST_SEARCHING", NAME=key))
    await _list_drive(key, message, user_id, item_type, isRecursive)

async def drive_list(_, message):
    args = message.text.split() if message.text else ["/cmd"]
    if len(args) == 1:
        return await sendMessage(message, "<i>𝐒ᴇɴᴅ ᴀ sᴇᴀʀᴄʜ ᴋᴇʏ ᴀʟᴏɴɢ ᴡɪᴛʜ ᴄᴏᴍᴍᴀɴᴅ</i>")
    user_id = message.from_user.id
    msg, btn = await checking_access(user_id)
    if msg is not None:
        await sendMessage(message, msg, btn.build_menu(1))
        return
    buttons = await list_buttons(user_id)
    await sendMessage(message, "<b>𝐂ʜᴏᴏsᴇ ᴅʀɪᴠᴇ ʟɪsᴛ ᴏᴘᴛɪᴏɴs:</b>", buttons, "IMAGES")

bot.add_handler(
    MessageHandler(
        drive_list,
        filters=command(BotCommands.ListCommand)
        & CustomFilters.authorized
        & ~CustomFilters.blacklisted,
    )
)
bot.add_handler(CallbackQueryHandler(select_type, filters=regex("^list_types")))
