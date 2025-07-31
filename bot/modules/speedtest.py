#!/usr/bin/env python3
from speedtest import Speedtest, ConfigRetrievalError
from pyrogram.handlers import MessageHandler
from pyrogram.filters import command

from bot import bot, LOGGER
from bot.helper.telegram_helper.filters import CustomFilters
from bot.helper.telegram_helper.bot_commands import BotCommands
from bot.helper.telegram_helper.message_utils import (
    sendMessage,
    deleteMessage,
    editMessage,
)
from bot.helper.ext_utils.bot_utils import get_readable_file_size, new_task


@new_task
async def speedtest(_, message):
    speed = await sendMessage(message, "<i>𝐈ɴɪᴛɪᴀᴛɪɴɢ 𝐒ᴘᴇᴇᴅᴛᴇsᴛ...</i>")
    try:
        test = Speedtest()
    except ConfigRetrievalError:
        await editMessage(
            speed,
            "<b>𝐄ʀʀᴏʀ:</b> <i>𝐂ᴀɴ'ᴛ ᴄᴏɴɴᴇᴄᴛ ᴛᴏ 𝐒ᴇʀᴠᴇʀ ᴀᴛ ᴛʜᴇ 𝐌ᴏᴍᴇɴᴛ, 𝐓ʀʏ 𝐀ɢᴀɪɴ 𝐋ᴀᴛᴇʀ !</i>",
        )
        return
    test.get_best_server()
    test.download()
    test.upload()
    test.results.share()
    result = test.results.dict()
    path = result["share"]
    string_speed = f"""
➲ <b><i>𝐒ᴘᴇᴇᴅᴛᴇsᴛ 𝐈ɴғᴏ</i></b>
┠ <b>𝐔ᴘʟᴏᴀᴅ:</b> <code>{get_readable_file_size(result['upload'] / 8)}/s</code>
┠ <b>𝐃ᴏᴡɴʟᴏᴀᴅ:</b>  <code>{get_readable_file_size(result['download'] / 8)}/s</code>
┠ <b>𝐏ɪɴɢ:</b> <code>{result['ping']} ms</code>
┠ <b>𝐓ɪᴍᴇ:</b> <code>{result['timestamp']}</code>
┠ <b>𝐃ᴀᴛᴀ 𝐒ᴇɴᴛ:</b> <code>{get_readable_file_size(int(result['bytes_sent']))}</code>
┖ <b>𝐃ᴀᴛᴀ 𝐑ᴇᴄᴇɪᴠᴇᴅ:</b> <code>{get_readable_file_size(int(result['bytes_received']))}</code>

➲ <b><i>𝐒ᴘᴇᴇᴅᴛᴇsᴛ 𝐒ᴇʀᴠᴇʀ</i></b>
┠ <b>𝐍ᴀᴍᴇ:</b> <code>{result['server']['name']}</code>
┠ <b>𝐂ᴏᴜɴᴛʀʏ:</b> <code>{result['server']['country']}, {result['server']['cc']}</code>
┠ <b>𝐒ᴘᴏɴsᴏʀ:</b> <code>{result['server']['sponsor']}</code>
┠ <b>𝐋ᴀᴛᴇɴᴄʏ:</b> <code>{result['server']['latency']}</code>
┠ <b>𝐋ᴀᴛɪᴛᴜᴅᴇ:</b> <code>{result['server']['lat']}</code>
┖ <b>𝐋ᴏɴɢɪᴛᴜᴅᴇ:</b> <code>{result['server']['lon']}</code>

➲ <b><i>𝐂ʟɪᴇɴᴛ 𝐃ᴇᴛᴀɪʟs</i></b>
┠ <b>𝐈ᴘ 𝐀ᴅᴅʀᴇss:</b> <code>{result['client']['ip']}</code>
┠ <b>𝐋ᴀᴛɪᴛᴜᴅᴇ:</b> <code>{result['client']['lat']}</code>
┠ <b>𝐋ᴏɴɢɪᴛᴜᴅᴇ:</b> <code>{result['client']['lon']}</code>
┠ <b>𝐂ᴏᴜɴᴛʀʏ:</b> <code>{result['client']['country']}</code>
┠ <b>𝐈sᴘ:</b> <code>{result['client']['isp']}</code>
┖ <b>𝐈sᴘ 𝐑ᴀᴛɪɴɢ:</b> <code>{result['client']['isprating']}</code>
"""
    try:
        pho = await sendMessage(message, string_speed, photo=path)
        await deleteMessage(speed)
    except Exception as e:
        LOGGER.error(str(e))
        await editMessage(speed, string_speed)


bot.add_handler(
    MessageHandler(
        speedtest,
        filters=command(BotCommands.SpeedCommand)
        & CustomFilters.authorized
        & ~CustomFilters.blacklisted,
    )
)
