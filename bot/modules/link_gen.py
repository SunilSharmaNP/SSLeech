#!/usr/bin/env python3
from pyrogram.handlers import MessageHandler
from pyrogram.filters import command

from bot import bot, LOGGER
from bot.helper.telegram_helper.filters import CustomFilters
from bot.helper.telegram_helper.bot_commands import BotCommands
from bot.helper.telegram_helper.button_build import ButtonMaker
from bot.helper.telegram_helper.message_utils import sendMessage, editMessage
from bot.helper.ext_utils.bot_utils import new_task, get_readable_file_size
from bot.helper.mirror_utils.download_utils.tg_stream_server import (
    register_link,
    get_media,
)


@new_task
async def link_cmd(client, message):
    reply = message.reply_to_message
    if not reply or not get_media(reply):
        await sendMessage(
            message,
            f"<b>Reply to a media message (video/file) with /{BotCommands.LinkCommand} "
            "to generate a direct download link.</b>",
        )
        return

    status = await sendMessage(message, "<i>Generating Direct Link...</i>")
    try:
        result = await register_link(reply, primary_client=client)
    except Exception as e:
        LOGGER.error(f"Link Command: {e}")
        await editMessage(status, f"<b>❌ Could not generate link:</b> <i>{e}</i>")
        return

    tag = message.from_user.mention
    text = (
        f"✦ <b>Fɪʟᴇ ɴᴀᴍᴇ :</b> {result['file_name']}\n\n"
        f"┏◈ <b>Fɪʟᴇ ꜱɪᴢᴇ :</b> {get_readable_file_size(result['file_size'])}\n"
        f"┠◈ <b>ғɪʟᴇ ᴛʏᴘᴇ :</b> {result['mime_type']}\n"
        f"┖◈ <b>ᴜꜱᴇʀ :</b> {tag}"
    )

    buttons = ButtonMaker()
    buttons.ubutton("📥 Download", result["url"])

    try:
        await sendMessage(message, text, buttons.build_menu(1))
        await status.delete()
    except Exception as e:
        LOGGER.error(f"Link Command: failed to send result — {e}")
        await editMessage(status, text)


bot.add_handler(
    MessageHandler(
        link_cmd,
        filters=command(BotCommands.LinkCommand)
        & CustomFilters.authorized
        & ~CustomFilters.blacklisted,
    )
)
