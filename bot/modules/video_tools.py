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
from bot.helper.video_utils.selector import SelectMode, register_vidtools_handlers
from bot.helper.video_utils.encoding_selector import register_encoding_handlers
from bot.modules.mirror_leech import _mirror_leech


class VidTools:
    def __init__(self, client, message, isLeech=False, **kwargs):
        self.client = client
        self.message = message
        self.isLeech = isLeech
        # Set required attributes for SelectMode
        self.user_id = message.from_user.id if message else None
        self.user_dict = user_data.get(self.user_id, {}) if self.user_id else {}
        self.mid = self.user_id  # Message unique identifier for tracking
        self.uid = f"{self.user_id}-{int(time())}"  # Unique task identifier
        self.dir = DOWNLOAD_DIR

    @new_task
    async def newEvent(self):
        LOGGER.info(f"VidTools.newEvent started for user {self.user_id}")
        if not self.message:
            LOGGER.error("VidTools.newEvent called with no message")
            return

        raw_text = self.message.text or self.message.caption or (
            self.message.reply_to_message.text if self.message.reply_to_message else ""
        )
        if not raw_text:
            LOGGER.warning(f"No text found in message for user {self.user_id}")
            await sendMessage(self.message, 'Send command along with link or by reply to the link!')
            return
        text = raw_text.split('\n')
        input_list = text[0].split(' ')
        arg_base = {'link': ''}
        args = arg_parser(input_list[1:], arg_base)
        self.link = args['link'] or get_link(self.message)
        if not is_url(self.link):
            LOGGER.warning(f"Invalid URL: {self.link}")
            await sendMessage(self.message, 'Send command along with link or by reply to the link!')
            return
        
        LOGGER.info(f"VidTools: Creating SelectMode UI for user {self.user_id} with link {self.link}")
        # Show SelectMode UI to collect video processing settings
        try:
            self.vidMode = await SelectMode(self, True).get_buttons()
            LOGGER.info(f"VidTools: SelectMode.get_buttons() returned: {self.vidMode}")
            if not self.vidMode:
                LOGGER.info(f"VidTools: User {self.user_id} cancelled selection")
                await sendMessage(self.message, 'Request cancelled!')
                return
            
            # Store video settings in message for mirror_leech to use
            self.message.vidMode = self.vidMode
            LOGGER.info(f"VidTools: Video settings stored - {self.vidMode}")
            
            # Now trigger the actual download/processing using mirror_leech
            # Pass the message with vidMode embedded so mirror_leech can detect it
            await sendMessage(self.message, '🎬 <b>Starting Video Processing Task...</b>\n<i>Downloading and processing your video...</i>')
            
            # Call mirror_leech with the message that now contains video settings
            await _mirror_leech(self.client, self.message, isQbit=False, isLeech=self.isLeech)
            
        except Exception as e:
            LOGGER.error(f"VidTools SelectMode error for user {self.user_id}: {e}", exc_info=True)
            await sendMessage(self.message, f'❌ <b>Error:</b> {str(e)}')


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

# Register callback handler for SelectMode buttons
try:
    register_vidtools_handlers()
    LOGGER.info("VidTools callback handler registered successfully")
except Exception as e:
    LOGGER.error(f"Failed to register vidtools callback handler: {e}", exc_info=True)
