from aiofiles.os import path as aiopath
from asyncio import sleep
from secrets import token_urlsafe
from time import time

from pyrogram.handlers import MessageHandler
from pyrogram.filters import command

from bot import bot, LOGGER, user_data, DOWNLOAD_DIR
from bot.helper.ext_utils.bot_utils import new_task, arg_parser
from bot.helper.ext_utils.links_utils import is_url, get_url_name, get_link
from bot.helper.listeners.tasks_listener import TaskListener
from bot.helper.telegram_helper.bot_commands import BotCommands
from bot.helper.telegram_helper.filters import CustomFilters
from bot.helper.telegram_helper.message_utils import sendMessage, editMessage, deleteMessage, auto_delete_message
from bot.helper.video_utils.executor import VidEcxecutor
from bot.helper.video_utils.selector import SelectMode


class VidTools(TaskListener):
    def __init__(self, client, message, isLeech=False, **kwargs):
        # Call parent init with message to properly initialize TaskListener
        super().__init__(message, isLeech=isLeech)
        # Set client and additional attributes
        self.client = client
        self.isLeech = isLeech

    @new_task
    async def newEvent(self):
        if not self.message:
            LOGGER.error("VidTools.newEvent called with no message")
            return

        raw_text = self.message.text or self.message.caption or (
            self.message.reply_to_message.text if self.message.reply_to_message else ""
        )
        if not raw_text:
            await sendMessage('Send command along with link or by reply to the link!', self.message)
            return
        text = raw_text.split('\n')
        input_list = text[0].split(' ')
        arg_base = {'link': ''}
        args = arg_parser(input_list[1:], arg_base)
        self.link = args['link'] or get_link(self.message)
        if not is_url(self.link):
            await sendMessage('Send command along with link or by reply to the link!', self.message)
            return
        self.vidMode = await SelectMode(self, True).get_buttons()
        if not self.vidMode:
            return
        self.name = get_url_name(self.link)
        self.editable = await sendMessage('<i>Checking request, please wait...</i>', self.message)
        await sleep(1)
        # Skip beforeStart() / onDownloadComplete() - just process video
        gid = token_urlsafe(12)
        out_path = await VidEcxecutor(self, self.link, gid, False).execute()
        if not out_path:
            await editMessage('<i>Processing failed!</i>', self.editable)
            return
        if not await aiopath.exists(str(out_path)):
            self.name = self.vidMode[1] or self.name
            await editMessage(f'❌ No file(s) to process', self.editable)
            return
        await deleteMessage(self.editable)
        # Simple completion message
        await sendMessage(f'✅ <b>Processing Complete:</b>\n<code>{self.name}</code>', self.message)


async def mirror_vidtools(client, message):
    if not message:
        LOGGER.error("mirror_vidtools: received None message")
        return
    LOGGER.info(f"mirror_vidtools: processing message from {message.from_user.id}")
    await VidTools(client, message).newEvent()


async def leech_vidtools(client, message):
    if not message:
        LOGGER.error("leech_vidtools: received None message")
        return
    LOGGER.info(f"leech_vidtools: processing message from {message.from_user.id}")
    await VidTools(client, message, isLeech=True).newEvent()


bot.add_handler(MessageHandler(mirror_vidtools, filters=command(BotCommands.MVidCommand) & CustomFilters.authorized))
bot.add_handler(MessageHandler(leech_vidtools, filters=command(BotCommands.LVidCommand) & CustomFilters.authorized))
