"""
Video Tools - Main command handler for /vtl (leech) and /vtm (mirror) commands
Handles video processing with multiple modes: merge, compress, convert, watermark, etc.
"""

import asyncio
import re
from pathlib import Path
from time import time, sleep
from logging import getLogger

from pyrogram import Client
from pyrogram.handlers import MessageHandler, CallbackQueryHandler
from pyrogram.filters import command, private, regex, user
from pyrogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from bot import config_dict
from bot.helper.ext_utils.bot_utils import get_readable_time, new_task
from bot.helper.telegram_helper.message_utils import sendMessage, editMessage
from bot.helper.telegram_helper.button_build import ButtonMaker
from bot.helper.telegram_helper.bot_commands import BotCommands
from bot.helper.telegram_helper.filters import CustomFilters
from bot.helper.video_utils import VidExecutor, SelectMode

LOGGER = getLogger(__name__)


class VidTools:
    """Video Tools handler class"""
    
    def __init__(self, client, message, is_leech=False, bulk=None, options=''):
        """Initialize Video Tools handler
        
        Args:
            client: Pyrogram client
            message: User message
            is_leech: If True, leech to Telegram; if False, mirror to cloud
            bulk: Bulk operation info
            options: Command line options
        """
        self.client = client
        self.message = message
        self.is_leech = is_leech
        self.bulk = bulk
        self.options = options
        
        # Video tool settings
        self.link = None
        self.file_path = None
        self.mode = None
        self.preset = None
        self.resolution = None
        self.position = 'br'  # watermark position
        self.stream_type = None
        self.start_time = None
        self.end_time = None
        
        # Parse options from message
        self._parse_options()
    
    def _parse_options(self):
        """Parse command options from message text"""
        text = self.message.text or ''
        
        # Extract link/file path
        parts = text.split()
        if len(parts) > 1:
            self.link = parts[1]
        
        # Look for specific flags
        if '-vt' in text:
            vt_match = re.search(r'-vt\s+(\w+)', text)
            if vt_match:
                self.mode = vt_match.group(1)
    
    async def process(self):
        """Main processing function"""
        try:
            # Show mode selection menu
            await self._show_mode_menu()
            
        except Exception as e:
            LOGGER.error(f"Error in video tools: {str(e)}")
            await sendMessage(self.message, f"❌ Error: {str(e)}")
    
    async def _show_mode_menu(self):
        """Display video mode selection menu"""
        caption = SelectMode.get_menu_caption()
        buttons = SelectMode.get_mode_buttons()
        
        await sendMessage(
            self.message,
            caption,
            buttons
        )
    
    async def _handle_mode_selection(self, mode):
        """Handle selected video mode"""
        if mode == 'cancel':
            await editMessage(self.message, "❌ Video tools cancelled")
            return
        
        self.mode = mode
        
        # Route to specific handler
        if mode == 'convert':
            await self._handle_convert()
        elif mode == 'compress':
            await self._handle_compress()
        elif mode == 'watermark':
            await self._handle_watermark()
        elif mode == 'extract':
            await self._handle_extract()
        elif mode == 'trim':
            await self._handle_trim()
        elif mode == 'vid_vid':
            await self._handle_merge_videos()
        elif mode == 'vid_aud':
            await self._handle_merge_audio()
        elif mode == 'vid_sub':
            await self._handle_merge_subtitle()
        elif mode == 'subsync':
            await self._handle_subsync()
        elif mode == 'rmstream':
            await self._handle_remove_stream()
    
    async def _handle_convert(self):
        """Handle resolution conversion"""
        caption = SelectMode.get_confirmation_caption('convert')
        buttons = SelectMode.get_resolution_buttons()
        
        await editMessage(
            self.message,
            caption,
            buttons
        )
    
    async def _execute_convert(self, resolution):
        """Execute resolution conversion"""
        await editMessage(self.message, f"🔄 Converting to {resolution}...")
        
        try:
            executor = VidExecutor(self.file_path, config_dict)
            output = await executor.convert_resolution(resolution)
            
            if output:
                await editMessage(
                    self.message,
                    f"✅ <b>Conversion Complete!</b>\n\n"
                    f"📐 Resolution: {resolution}\n"
                    f"📁 Output: <code>{output}</code>"
                )
            else:
                await editMessage(self.message, "❌ Conversion failed")
                
        except Exception as e:
            await editMessage(self.message, f"❌ Error: {str(e)}")
    
    async def _handle_compress(self):
        """Handle video compression"""
        caption = SelectMode.get_confirmation_caption('compress')
        buttons = SelectMode.get_compress_preset_buttons()
        
        await editMessage(
            self.message,
            caption,
            buttons
        )
    
    async def _execute_compress(self, preset):
        """Execute video compression"""
        await editMessage(self.message, f"🔄 Compressing with preset: {preset}...")
        
        try:
            executor = VidExecutor(self.file_path, config_dict)
            output = await executor.compress_video(preset=preset)
            
            if output:
                # Get file sizes for comparison
                import os
                original_size = os.path.getsize(self.file_path)
                compressed_size = os.path.getsize(output)
                reduction = ((original_size - compressed_size) / original_size) * 100
                
                await editMessage(
                    self.message,
                    f"✅ <b>Compression Complete!</b>\n\n"
                    f"📦 Preset: {preset}\n"
                    f"📊 Original: {original_size / (1024**2):.2f} MB\n"
                    f"📊 Compressed: {compressed_size / (1024**2):.2f} MB\n"
                    f"📉 Reduction: {reduction:.1f}%\n"
                    f"📁 Output: <code>{output}</code>"
                )
            else:
                await editMessage(self.message, "❌ Compression failed")
                
        except Exception as e:
            await editMessage(self.message, f"❌ Error: {str(e)}")
    
    async def _handle_watermark(self):
        """Handle watermark addition"""
        caption = SelectMode.get_confirmation_caption('watermark')
        buttons = SelectMode.get_position_buttons()
        
        await editMessage(
            self.message,
            caption,
            buttons
        )
    
    async def _execute_watermark(self, position):
        """Execute watermark addition"""
        # Position mapping from selector keys to full names
        position_map = {'tl': 'top-left', 'tr': 'top-right', 'bl': 'bottom-left', 'br': 'bottom-right'}
        position_name = position_map.get(position, 'bottom-right')
        
        await editMessage(self.message, f"🔄 Adding watermark at {position_name}...")
        
        try:
            # Note: This requires watermark file as input
            executor = VidExecutor(self.file_path, config_dict)
            # watermark_file would need to be provided
            # For now, this is a placeholder
            
            await editMessage(
                self.message,
                f"⚠️ <b>Watermark Addition</b>\n\n"
                f"Position: {position_name}\n\n"
                f"<i>Please provide watermark image file</i>"
            )
                
        except Exception as e:
            await editMessage(self.message, f"❌ Error: {str(e)}")
    
    async def _handle_extract(self):
        """Handle stream extraction"""
        caption = SelectMode.get_confirmation_caption('extract')
        buttons = SelectMode.get_stream_type_buttons()
        
        await editMessage(
            self.message,
            caption,
            buttons
        )
    
    async def _execute_extract(self, stream_type):
        """Execute stream extraction"""
        await editMessage(self.message, f"🔄 Extracting {stream_type} streams...")
        
        try:
            executor = VidExecutor(self.file_path, config_dict)
            outputs = await executor.extract_streams(stream_type)
            
            if outputs:
                output_list = "\n".join([f"📁 <code>{os.path.basename(f)}</code>" for f in outputs])
                await editMessage(
                    self.message,
                    f"✅ <b>Extraction Complete!</b>\n\n"
                    f"🎬 Type: {stream_type}\n"
                    f"📁 Files:\n{output_list}"
                )
            else:
                await editMessage(self.message, "❌ Extraction failed")
                
        except Exception as e:
            await editMessage(self.message, f"❌ Error: {str(e)}")
    
    async def _handle_trim(self):
        """Handle video trimming"""
        caption = SelectMode.get_confirmation_caption('trim')
        
        await editMessage(
            self.message,
            caption,
            InlineKeyboardMarkup([[InlineKeyboardButton('⬅️ Back', callback_data='vidmode_back')]])
        )
    
    async def _execute_trim(self, times):
        """Execute video trimming
        
        Args:
            times: "HH:MM:SS HH:MM:SS" format (start end)
        """
        try:
            start_str, end_str = times.split()
            await editMessage(self.message, f"🔄 Trimming video from {start_str} to {end_str}...")
            
            executor = VidExecutor(self.file_path, config_dict)
            output = await executor.trim_video(start_str, end_str)
            
            if output:
                await editMessage(
                    self.message,
                    f"✅ <b>Trim Complete!</b>\n\n"
                    f"⏱️ Start: {start_str}\n"
                    f"⏱️ End: {end_str}\n"
                    f"📁 Output: <code>{output}</code>"
                )
            else:
                await editMessage(self.message, "❌ Trim failed")
                
        except Exception as e:
            await editMessage(self.message, f"❌ Error: {str(e)}")
    
    async def _handle_merge_videos(self):
        """Handle video merging"""
        await editMessage(
            self.message,
            "🎬 <b>Merge Videos</b>\n\n"
            "Send multiple video file links or attach files\n"
            "<i>Use flag: -m (same folder) for multiple files</i>"
        )
    
    async def _handle_merge_audio(self):
        """Handle audio merging"""
        await editMessage(
            self.message,
            "🎵 <b>Merge Video + Audio</b>\n\n"
            "Send video link/file, then audio file links\n"
            "<i>Audio files will be merged as separate tracks</i>"
        )
    
    async def _handle_merge_subtitle(self):
        """Handle subtitle merging"""
        caption = ("📝 <b>Merge Video + Subtitle</b>\n\n"
                  "Choose subtitle merge type:\n"
                  "1. <b>Softcopy:</b> Subtitle as separate stream\n"
                  "2. <b>Hardsub:</b> Burn subtitle into video")
        
        buttons = InlineKeyboardMarkup([
            [
                InlineKeyboardButton('Softcopy', callback_data='vidsub_soft'),
                InlineKeyboardButton('Hardsub', callback_data='vidsub_hard'),
            ],
            [InlineKeyboardButton('⬅️ Back', callback_data='vidmode_back')]
        ])
        
        await editMessage(self.message, caption, buttons)
    
    async def _handle_subsync(self):
        """Handle subtitle synchronization"""
        caption = ("🔄 <b>Synchronize Subtitles</b>\n\n"
                  "Choose sync method:\n"
                  "1. <b>Auto (alass):</b> Automatic synchronization\n"
                  "2. <b>Manual:</b> Manual time adjustment")
        
        buttons = InlineKeyboardMarkup([
            [
                InlineKeyboardButton('Auto Sync', callback_data='vidsync_alass'),
                InlineKeyboardButton('Manual', callback_data='vidsync_manual'),
            ],
            [InlineKeyboardButton('⬅️ Back', callback_data='vidmode_back')]
        ])
        
        await editMessage(self.message, caption, buttons)
    
    async def _handle_remove_stream(self):
        """Handle stream removal"""
        caption = ("🗑️ <b>Remove Stream</b>\n\n"
                  "Choose stream to remove:")
        
        buttons = SelectMode.get_stream_type_buttons()
        
        await editMessage(self.message, caption, buttons)
    
    async def _execute_remove_stream(self, stream_type):
        """Execute stream removal"""
        if stream_type == 'all':
            await editMessage(self.message, "⚠️ Cannot remove all streams")
            return
        
        await editMessage(self.message, f"🔄 Removing {stream_type} stream...")
        
        try:
            executor = VidExecutor(self.file_path, config_dict)
            output = await executor.remove_stream(stream_type)
            
            if output:
                await editMessage(
                    self.message,
                    f"✅ <b>Removal Complete!</b>\n\n"
                    f"🗑️ Removed: {stream_type}\n"
                    f"📁 Output: <code>{output}</code>"
                )
            else:
                await editMessage(self.message, "❌ Removal failed")
                
        except Exception as e:
            await editMessage(self.message, f"❌ Error: {str(e)}")


async def mirror_vidtools(client: Client, message: Message):
    """Handler for /vtm command (mirror with video tools)"""
    try:
        vid_tool = VidTools(client, message, is_leech=False)
        await vid_tool.process()
    except Exception as e:
        LOGGER.error(f"Error in mirror_vidtools: {str(e)}")
        await sendMessage(message, f"❌ Error: {str(e)}")


async def leech_vidtools(client: Client, message: Message):
    """Handler for /vtl command (leech with video tools)"""
    try:
        vid_tool = VidTools(client, message, is_leech=True)
        await vid_tool.process()
    except Exception as e:
        LOGGER.error(f"Error in leech_vidtools: {str(e)}")
        await sendMessage(message, f"❌ Error: {str(e)}")


async def vidtools_mode_callback(client: Client, query: CallbackQuery):
    """Callback handler for video tools mode selection"""
    try:
        data = query.data.split('_', 1)
        if len(data) > 1:
            mode = data[1]
            
            # Get the VidTools instance (would need to be stored somewhere)
            # For now, we'll create a temporary one
            # In real implementation, store instances in a dict
            
            if mode == 'back':
                # Go back to mode menu
                caption = SelectMode.get_menu_caption()
                buttons = SelectMode.get_mode_buttons()
                await editMessage(query.message, caption, buttons)
            else:
                # Route to mode handler
                await query.message.reply_text(f"Mode {mode} selected")
                
    except Exception as e:
        LOGGER.error(f"Error in vidtools_mode_callback: {str(e)}")


# Import bot instance for handler registration
from bot import bot


# Register message handlers
bot.add_handler(
    MessageHandler(
        leech_vidtools,
        filters=command(BotCommands.LVidCommand)
        & CustomFilters.authorized
        & ~CustomFilters.blacklisted,
    )
)
bot.add_handler(
    MessageHandler(
        mirror_vidtools,
        filters=command(BotCommands.MVidCommand)
        & CustomFilters.authorized
        & ~CustomFilters.blacklisted,
    )
)

# Register callback handlers
bot.add_handler(CallbackQueryHandler(vidtools_mode_callback, filters=regex(r"^vid")))


