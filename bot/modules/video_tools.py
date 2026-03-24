from aiofiles.os import path as aiopath
from asyncio import sleep
from secrets import token_urlsafe

from pyrogram.handlers import MessageHandler
from pyrogram.filters import command

from bot import bot, LOGGER
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
        self.message = message
        self.client = client
        self.isLeech = isLeech
        super().__init__()

    @new_task
    async def newEvent(self):
        text = self.message.text.split('\n')
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
        try:
            await self.beforeStart()
        except Exception as e:
            await editMessage(str(e), self.editable)
            return
        await deleteMessage(self.editable)
        gid = token_urlsafe(12)
        out_pah = await VidEcxecutor(self, self.link, gid, False).execute()
        if not out_pah:
            return
        if not await aiopath.exists(str(out_pah)):
            self.name = self.vidMode[1] or self.name
            await self.onUploadError('No file(s) to upload')
            return
        await self.onDownloadComplete()


async def mirror_vidtools(client, message):
    VidTools(client, message).newEvent()


async def leech_vidtools(client, message):
    VidTools(client, message, isLeech=True).newEvent()


bot.add_handler(MessageHandler(mirror_vidtools, filters=command(BotCommands.MVidCommand) & CustomFilters.authorized))
bot.add_handler(MessageHandler(leech_vidtools, filters=command(BotCommands.LVidCommand) & CustomFilters.authorized))
