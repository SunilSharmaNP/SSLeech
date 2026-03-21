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
from bot.helper.ext_utils.bot_utils import new_task, is_url
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
        
        # Extract link from message
        reply_to = self.message.reply_to_message
        
        # Try to get link from command arguments
        link_parts = text[0].split(' ', 1)
        self.link = link_parts[1] if len(link_parts) > 1 else None
        
        # If no link in command, try reply message
        if not self.link and reply_to and reply_to.text:
            self.link = reply_to.text.split('\n', 1)[0].strip()
        
        # Validate link
        if not self.link or not is_url(self.link):
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
            # Extract filename from URL or use default
            try:
                self.name = self.link.split('/')[-1].split('?')[0] or 'video'
            except:
                self.name = 'video'
        
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
    await VidTools(_, message, isLeech=False).newEvent()


@new_task
async def leech_vidtools(_, message: Message):
    """Handle /vtl command (leech with video tools)"""
    await VidTools(_, message, isLeech=True).newEvent()


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
