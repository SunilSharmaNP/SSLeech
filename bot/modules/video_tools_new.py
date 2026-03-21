"""
Video Tools Module - Interactive interface for video processing
Integrates with existing download/upload pipeline
"""

from pyrogram import Client
from pyrogram.types import Message
from pyrogram.filters import command
from pyrogram.handlers import MessageHandler
from asyncio import sleep
from os import path as ospath

from bot import bot, config_dict, LOGGER
from bot.helper.ext_utils.bot_utils import new_task, arg_parser
from bot.helper.ext_utils.commons_check import UseCheck
from bot.helper.ext_utils.links_utils import is_url, get_url_name, get_link
from bot.helper.listeners.tasks_listener import TaskListener
from bot.helper.telegram_helper.bot_commands import BotCommands
from bot.helper.telegram_helper.filters import CustomFilters
from bot.helper.telegram_helper.message_utils import sendMessage, deleteMessage, auto_delete_message
from bot.helper.video_utils.selector import SelectMode


class VidTools(TaskListener):
    """Video Tools task listener - processes video with selected tools"""
    
    def __init__(self, client: Client, message: Message, isLeech=False):
        """Initialize video tools handler"""
        self.message = message
        self.client = client
        self.isLeech = isLeech
        self.vidMode = None
        self.link = ''
        self.name = ''
        super().__init__()

    @new_task
    async def newEvent(self):
        """Handle video tools command"""
        text = self.message.text.split('\n')
        await self.getTag(text)

        # Validate user permissions
        if fmsg := await UseCheck(self.message, self.isLeech).run(True, daily=True, ml_chek=True, send_pm=True):
            await auto_delete_message(self.message, fmsg, self.message.reply_to_message)
            return

        # Parse arguments
        arg_base = {
            '-n': '',
            '-z': False,
            '-t': '',
            '-up': '',
            '-rcf': '',
            '-b': False,
            '-i': 0,
            '-sp': 0,
            '-ss': False,
            '-sv': False,
            'link': ''
        }
        
        input_list = text[0].split(' ')
        args = arg_parser(input_list[1:], arg_base)

        self.link = args.get('link', '') or get_link(self.message)
        self.name = args.get('-n', '').replace('/', '')
        self.compress = args.get('-z', '')
        self.thumb = args.get('-t', '')
        self.upDest = args.get('-up', '')
        self.rcFlags = args.get('-rcf', '')

        # Validate link
        if not is_url(self.link):
            msg = await sendMessage('❌ Send link or reply to link!\n\n<code>/vtm link</code> or <code>/vtl link</code>', self.message)
            await auto_delete_message(self.message, msg)
            return

        # Get video tool selection from user
        selector = SelectMode(self, is_link=True)
        self.vidMode = await selector.get_buttons()

        if not self.vidMode:
            return

        # Update name if provided
        if self.name and not self.vidMode[1]:
            self.vidMode = (self.vidMode[0], self.name, self.vidMode[2])

        # Set other task properties
        self.compress = self.compress
        self.isSuperGroup = self.message.chat.type in ['supergroup', 'channel']
        
        # Start download with video tools
        editable = await sendMessage('⏳ Preparing video tools task...', self.message)
        await sleep(1)

        try:
            # Trigger mirror/leech with video tools
            # The download will complete, then we run video processing
            await self.beforeStart()
        except Exception as e:
            await sendMessage(f'❌ Error: {str(e)}', self.message)
            await deleteMessage(editable)
            return

        await deleteMessage(editable)
        
        # Call existing download handler based on isLeech
        self.run_task()

    def run_task(self):
        """Start download task"""
        # This will integrate with existing mirror/leech handlers
        # The video processing happens after download completes
        pass


@new_task
async def mirror_vidtools(client: Client, message: Message):
    """Mirror command with video tools"""
    VidTools(client, message, isLeech=False).newEvent()


@new_task
async def leech_vidtools(client: Client, message: Message):
    """Leech command with video tools"""
    VidTools(client, message, isLeech=True).newEvent()


# Register handlers
bot.add_handler(
    MessageHandler(
        mirror_vidtools,
        filters=command(BotCommands.MVidCommand) & CustomFilters.authorized
    )
)

bot.add_handler(
    MessageHandler(
        leech_vidtools,
        filters=command(BotCommands.LVidCommand) & CustomFilters.authorized
    )
)

LOGGER.info("Video Tools module loaded")
