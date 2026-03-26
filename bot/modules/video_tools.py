from aiofiles.os import path as aiopath
from asyncio import sleep
from secrets import token_urlsafe
from time import time

from pyrogram.handlers import MessageHandler
from pyrogram.filters import command

from bot import bot, LOGGER, user_data, DOWNLOAD_DIR
from bot.helper.ext_utils.bot_utils import new_task, arg_parser
from bot.helper.ext_utils.links_utils import is_url, get_url_name, get_link
from bot.helper.telegram_helper.bot_commands import BotCommands
from bot.helper.telegram_helper.filters import CustomFilters
from bot.helper.telegram_helper.message_utils import sendMessage, editMessage, deleteMessage, auto_delete_message
from bot.helper.video_utils.selector import SelectMode


class VidTools:
    def __init__(self, client, message, isLeech=False, **kwargs):
        self.client = client
        self.message = message
        self.isLeech = isLeech
        # Set required attributes for SelectMode and VidEcxecutor
        self.user_id = message.from_user.id if message else None
        self.user_dict = user_data.get(self.user_id, {}) if self.user_id else {}
        self.mid = self.user_id  # Message unique identifier for tracking
        self.uid = f"{self.user_id}-{int(time())}"  # Unique task identifier
        self.dir = DOWNLOAD_DIR
        # TaskListener compatibility attributes
        self.suproc = None
        self.seed = False
        self.extensionFilter = ['!.txt', '!.nfo']  # Files to skip
        # Additional attributes for VidEcxecutor
        self.tag = f"VidTools_User_{self.user_id}"

    async def onDownloadStart(self):
        """Stub method for executor compatibility"""
        pass

    async def onDownloadError(self, error, button=None):
        """Handle download errors"""
        await editMessage(f'❌ <b>Error:</b> {error}', getattr(self, 'editable', self.message))

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
        
        # Just show SelectMode UI for now - get video processing options
        try:
            self.vidMode = await SelectMode(self, True).get_buttons()
            if not self.vidMode:
                await sendMessage('Request cancelled!', self.message)
                return
            
            self.name = get_url_name(self.link)
            mode_name = self.vidMode[0]
            rename_name = self.vidMode[1]
            extra_data = self.vidMode[2]
            
            # Success message showing what was selected
            msg = f"✅ <b>Selection Saved:</b>\n"
            msg += f"<b>Mode:</b> {mode_name}\n"
            if rename_name:
                msg += f"<b>Rename:</b> {rename_name}\n"
            if extra_data:
                msg += f"<b>Extra Options:</b> {extra_data}\n"
            msg += f"<b>Video:</b> {self.name}"
            
            await sendMessage(msg, self.message)
            LOGGER.info(f"VidTools: User {self.user_id} selected mode={mode_name}, rename={rename_name}")
            
        except Exception as e:
            LOGGER.error(f"VidTools SelectMode error: {e}", exc_info=True)
            await sendMessage(f'❌ <b>Error:</b> {str(e)}', self.message)


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
