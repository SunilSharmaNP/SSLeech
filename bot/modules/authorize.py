#!/usr/bin/env python3
from pyrogram.handlers import MessageHandler
from pyrogram.filters import command, regex

from bot import user_data, DATABASE_URL, bot, LOGGER
from bot.helper.telegram_helper.message_utils import sendMessage
from bot.helper.telegram_helper.filters import CustomFilters
from bot.helper.telegram_helper.bot_commands import BotCommands
from bot.helper.ext_utils.db_handler import DbManger
from bot.helper.ext_utils.bot_utils import update_user_ldata


async def authorize(client, message):
    msg = message.text.split()
    tid_ = ""
    if len(msg) > 1:
        nid_ = msg[1].split(":")
        id_ = int(nid_[0])
        if len(nid_) > 1:
            tid_ = int(nid_[1])
    elif (reply_to := message.reply_to_message) and (
        reply_to.text is None and reply_to.caption is None
    ):
        id_ = message.chat.id
        tid_ = message.reply_to_message_id
    elif reply_to:
        id_ = reply_to.from_user.id
    else:
        id_ = message.chat.id
    if id_ in user_data and user_data[id_].get("is_auth"):
        msg = "𝐀ʟʀᴇᴀᴅʏ 𝐀ᴜᴛʜᴏʀɪᴢᴇᴅ!"
        if tid_:
            if tid_ not in (tids_ := user_data[id_].get("topic_ids", [])):
                tids_.append(tid_)
                update_user_ldata(id_, "topic_ids", tids_)
                if DATABASE_URL:
                    await DbManger().update_user_data(id_)
                msg = "𝐓ᴏᴘɪᴄ 𝐀ᴜᴛʜᴏʀɪᴢᴇᴅ!"
            else:
                msg = "𝐓ᴏᴘɪᴄ 𝐀ʟʀᴇᴀᴅʏ 𝐀ᴜᴛʜᴏʀɪᴢᴇᴅ!"
    else:
        update_user_ldata(id_, "is_auth", True)
        if tid_:
            update_user_ldata(id_, "topic_ids", [tid_])
            msg = "𝐓ᴏᴘɪᴄ 𝐀ᴜᴛʜᴏʀɪᴢᴇᴅ!"
        else:
            msg = "𝐀ᴜᴛʜᴏʀɪᴢᴇᴅ"
        if DATABASE_URL:
            await DbManger().update_user_data(id_)
    await sendMessage(message, msg)


async def unauthorize(client, message):
    msg = message.text.split()
    tid_ = ""
    if len(msg) > 1:
        nid_ = msg[1].split(":")
        id_ = int(nid_[0])
        if len(nid_) > 1:
            tid_ = int(nid_[1])
    elif (reply_to := message.reply_to_message) and (
        reply_to.text is None and reply_to.caption is None
    ):
        id_ = message.chat.id
        tid_ = message.reply_to_message_id
    elif reply_to := message.reply_to_message:
        id_ = reply_to.from_user.id
    else:
        id_ = message.chat.id
    tids_ = []
    if (
        tid_
        and id_ in user_data
        and tid_ in (tids_ := user_data[id_].get("topic_ids", []))
    ):
        tids_.remove(tid_)
        update_user_ldata(id_, "topic_ids", tids_)
    if id_ not in user_data or user_data[id_].get("is_auth"):
        if not tids_:
            update_user_ldata(id_, "is_auth", False)
        if DATABASE_URL:
            await DbManger().update_user_data(id_)
        msg = "𝐔ɴᴀᴜᴛʜᴏʀɪᴢᴇᴅ"
    else:
        msg = "𝐀ʟʀᴇᴀᴅʏ 𝐔ɴᴀᴜᴛʜᴏʀɪᴢᴇᴅ!"
    await sendMessage(message, msg)


async def addSudo(client, message):
    id_ = ""
    msg = message.text.split()
    if len(msg) > 1:
        id_ = int(msg[1].strip())
    elif reply_to := message.reply_to_message:
        id_ = reply_to.from_user.id
    if id_:
        if id_ in user_data and user_data[id_].get("is_sudo"):
            msg = "𝐀ʟʀᴇᴀᴅʏ 𝐒ᴜᴅᴏ!"
        else:
            update_user_ldata(id_, "is_sudo", True)
            if DATABASE_URL:
                await DbManger().update_user_data(id_)
            msg = "𝐏ʀᴏᴍᴏᴛᴇᴅ ᴀs 𝐒ᴜᴅᴏ"
    else:
        msg = "<i>𝐆ɪᴠᴇ 𝐔sᴇʀ's 𝐈ᴅ ᴏʀ 𝐑ᴇᴘʟʏ ᴛᴏ 𝐔sᴇʀ's ᴍᴇssᴀɢᴇ ᴏғ ᴡʜᴏᴍ ʏᴏᴜ ᴡᴀɴᴛ ᴛᴏ 𝐏ʀᴏᴍᴏᴛᴇ ᴀs 𝐒ᴜᴅᴏ</i>"
    await sendMessage(message, msg)


async def removeSudo(client, message):
    id_ = ""
    msg = message.text.split()
    if len(msg) > 1:
        id_ = int(msg[1].strip())
    elif reply_to := message.reply_to_message:
        id_ = reply_to.from_user.id
    if id_:
        if id_ in user_data and not user_data[id_].get("is_sudo"):
            msg = "𝐍ᴏᴛ ᴀ 𝐒ᴜᴅᴏ 𝐔sᴇʀ, 𝐀ʟʀᴇᴀᴅʏ 𝐃ᴇᴍᴏᴛᴇᴅ"
        else:
            update_user_ldata(id_, "is_sudo", False)
            if DATABASE_URL:
                await DbManger().update_user_data(id_)
            msg = "𝐃ᴇᴍᴏᴛᴇᴅ"
    else:
        msg = "<i>𝐆ɪᴠᴇ 𝐔sᴇʀ's 𝐈ᴅ ᴏʀ 𝐑ᴇᴘʟʏ ᴛᴏ 𝐔sᴇʀ's ᴍᴇssᴀɢᴇ ᴏғ ᴡʜᴏᴍ ʏᴏᴜ ᴡᴀɴᴛ ᴛᴏ 𝐃ᴇᴍᴏᴛᴇ</i>"
    await sendMessage(message, msg)


async def addBlackList(_, message):
    id_ = ""
    msg = message.text.split()
    if len(msg) > 1:
        id_ = int(msg[1].strip())
    elif reply_to := message.reply_to_message:
        id_ = reply_to.from_user.id
    if id_:
        if id_ in user_data and user_data[id_].get("is_blacklist"):
            msg = "𝐔sᴇʀ 𝐀ʟʀᴇᴀᴅʏ 𝐁ʟᴀᴄᴋʟɪsᴛᴇᴅ!"
        else:
            update_user_ldata(id_, "is_blacklist", True)
            if DATABASE_URL:
                await DbManger().update_user_data(id_)
            msg = "𝐔sᴇʀ 𝐁ʟᴀᴄᴋʟɪsᴛᴇᴅ"
    else:
        msg = "𝐆ɪᴠᴇ 𝐈ᴅ ᴏʀ 𝐑ᴇᴘʟʏ 𝐓ᴏ ᴍᴇssᴀɢᴇ ᴏғ ᴡʜᴏᴍ ʏᴏᴜ ᴡᴀɴᴛ ᴛᴏ ʙʟᴀᴄᴋʟɪsᴛ."
    await sendMessage(message, msg)


async def rmBlackList(_, message):
    id_ = ""
    msg = message.text.split()
    if len(msg) > 1:
        id_ = int(msg[1].strip())
    elif reply_to := message.reply_to_message:
        id_ = reply_to.from_user.id
    if id_:
        if id_ in user_data and not user_data[id_].get("is_blacklist"):
            msg = "<i>𝐔sᴇʀ 𝐀ʟʀᴇᴀᴅʏ 𝐅ʀᴇᴇᴅ</i>"
        else:
            update_user_ldata(id_, "is_blacklist", False)
            if DATABASE_URL:
                await DbManger().update_user_data(id_)
            msg = "<i>𝐔sᴇʀ 𝐒ᴇᴛ 𝐅ʀᴇᴇ 𝐀s 𝐁ɪʀᴅ!</i>"
    else:
        msg = "𝐆ɪᴠᴇ 𝐈ᴅ 𝐎ʀ 𝐑ᴇᴘʟʏ 𝐓ᴏ 𝐌ᴇssᴀɢᴇ 𝐎ғ 𝐖ʜᴏᴍ 𝐘ᴏᴜ 𝐖ᴀɴᴛ 𝐓ᴏ 𝐑ᴇᴍᴏᴠᴇ 𝐅ʀᴏᴍ 𝐁ʟᴀᴄᴋʟɪsᴛᴇᴅ"
    await sendMessage(message, msg)


async def black_listed(_, message):
    await sendMessage(message, "<i>𝐁ʟᴀᴄᴋʟɪsᴛᴇᴅ 𝐃ᴇᴛᴇᴄᴛᴇᴅ, 𝐑ᴇsᴛʀɪᴄᴛᴇᴅ 𝐅ʀᴏᴍ 𝐁ᴏᴛ</i>")


bot.add_handler(
    MessageHandler(
        authorize, filters=command(BotCommands.AuthorizeCommand) & CustomFilters.sudo
    )
)
bot.add_handler(
    MessageHandler(
        unauthorize,
        filters=command(BotCommands.UnAuthorizeCommand) & CustomFilters.sudo,
    )
)
bot.add_handler(
    MessageHandler(
        addSudo, filters=command(BotCommands.AddSudoCommand) & CustomFilters.sudo
    )
)
bot.add_handler(
    MessageHandler(
        removeSudo, filters=command(BotCommands.RmSudoCommand) & CustomFilters.sudo
    )
)
bot.add_handler(
    MessageHandler(
        addBlackList,
        filters=command(BotCommands.AddBlackListCommand) & CustomFilters.sudo,
    )
)
bot.add_handler(
    MessageHandler(
        rmBlackList,
        filters=command(BotCommands.RmBlackListCommand) & CustomFilters.sudo,
    )
)
bot.add_handler(
    MessageHandler(
        black_listed,
        filters=regex(r"^/") & CustomFilters.authorized & CustomFilters.blacklisted,
    )
)
