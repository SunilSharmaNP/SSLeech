"""
Video Tools - Anime-Leech style implementation
Handles /vtl and /vtm commands for video processing
"""

from pyrogram import Client
from pyrogram.filters import command
from pyrogram.handlers import MessageHandler
from pyrogram.types import Message
from secrets import token_urlsafe
from time import sleep

from bot import bot, config_dict, LOGGER
from bot.helper.ext_utils.bot_utils import new_task, arg_parser
from bot.helper.ext_utils.commons_check import UseCheck
from bot.helper.ext_utils.links_utils import is_url, get_url_name, get_link
from bot.helper.listeners.tasks_listener import TaskListener
from bot.helper.telegram_helper.bot_commands import BotCommands
from bot.helper.telegram_helper.filters import CustomFilters
from bot.helper.telegram_helper.message_utils import (
    sendMessage, editMessage, deleteMessage, auto_delete_message
)
from bot.helper.video_utils.selector import SelectMode
from bot.helper.video_utils.executor import VidExecutor, get_metavideo


class VidTools(TaskListener):
    """Video Tools handler - processes videos with user-selected operations"""
    
    def __init__(self, client: Client, message: Message, isLeech=False):
        self.message = message
        self.client = client
        self.isLeech = isLeech
        super().__init__()
    
    @new_task
    async def newEvent(self):
        """Main entry point for video tools operation"""
        text = self.message.text.split('\n')
        await self.getTag(text)
        
        # Check user permissions
        if fmsg := await UseCheck(self.message, self.isLeech).run(True, daily=True, ml_chek=True, session=True, send_pm=True):
            await auto_delete_message(self.message, fmsg, self.message.reply_to_message)
            return
        
        # Parse command arguments
        arg_base = {
            '-i': 0,
            '-sp': 0,
            '-b': False,
            '-gf': False,
            '-sv': False,
            '-z': False,
            '-n': '',
            '-rcf': '',
            '-t': '',
            '-up': '',
            'link': ''
        }
        
        input_list = text[0].split(' ')
        args = arg_parser(input_list[1:], arg_base)
        
        # Extract basic info
        self.link = args['link'] or get_link(self.message)
        self.name = args['-n'].replace('/', '')
        self.compress = args['-z']
        self.isGofile = args['-gf']
        self.rcFlags = args['-rcf']
        self.splitSize = args['-sp']
        self.thumb = args['-t']
        self.upDest = args['-up']
        self.sampleVideo = args['-sv']
        
        # Validate link
        if not is_url(self.link):
            msg = await sendMessage('❌ Send link or use command with link!', self.message)
            await auto_delete_message(self.message, msg)
            return
        
        # Get video metadata
        metadata = await get_metavideo(self.link)
        if not metadata or not metadata[0]:
            msg = await sendMessage('❌ Failed getting video metadata!', self.message)
            await auto_delete_message(self.message, msg)
            return
        
        # Show video tools menu
        self.editable = await sendMessage('🎬 <b>Loading Video Tools Menu...</b>', self.message)
        
        selector = SelectMode(self, is_link=True)
        vidMode = await selector.get_buttons()
        
        if not vidMode:
            await deleteMessage(self.editable)
            msg = await sendMessage('❌ Video tools selection cancelled', self.message)
            await auto_delete_message(self.message, msg)
            return
        
        # Update name if renamed in selector
        if vidMode[1]:
            self.name = vidMode[1]
        elif not self.name:
            self.name = get_url_name(self.link)
        
        await editMessage('⏳ <b>Processing video...</b>', self.editable)
        
        try:
            # Execute video processing
            gid = token_urlsafe(12)
            executor = VidExecutor(self, self.link, gid, metadata)
            executor.mode = vidMode[0]
            executor.extra_data = vidMode[2]
            
            out_path = await executor.execute()
            
            if not out_path:
                await editMessage('❌ Video processing failed!', self.editable)
                return
            
            await deleteMessage(self.editable)
            await self.onDownloadComplete()
            
        except Exception as e:
            LOGGER.error(f"Video tools error: {str(e)}", exc_info=True)
            await editMessage(f'❌ Error: {str(e)}', self.editable)


@new_task
async def mirror_vidtools(_, message: Message):
    """Handle /vtm command (mirror with video tools)"""
    VidTools(_, message, isLeech=False).newEvent()


@new_task
async def leech_vidtools(_, message: Message):
    """Handle /vtl command (leech with video tools)"""
    VidTools(_, message, isLeech=True).newEvent()


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
