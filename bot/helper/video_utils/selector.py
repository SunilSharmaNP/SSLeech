"""
Video Tools Selector - Interactive button-based UI
Based on Anime-Leech implementation
"""

from __future__ import annotations
from asyncio import Event, wait_for, gather, wrap_future
from functools import partial
from os.path import join as osjoin
from pyrogram.filters import text, document, photo, user, regex
from pyrogram.handlers import MessageHandler, CallbackQueryHandler
from pyrogram.types import Message, CallbackQuery
from time import time
from logging import getLogger

from bot import config_dict, VID_MODE
from bot.helper.ext_utils.bot_utils import new_task, new_thread, sync_to_async
from bot.helper.ext_utils.fs_utils import clean_target
from bot.helper.telegram_helper.button_build import ButtonMaker
from bot.helper.telegram_helper.filters import CustomFilters
from bot.helper.telegram_helper.message_utils import sendMessage, editMessage, deleteMessage

LOGGER = getLogger(__name__)


class SelectMode:
    """Interactive video tools selector"""
    
    def __init__(self, listener, is_link=False):
        """Initialize selector"""
        self.listener = listener
        self.message = listener.message
        self._isLink = is_link
        self.event = Event()
        self.mode = None
        self.newname = ''
        self.extra_data = {}
        self.is_rename = False
        self.is_cancelled = False
        self._message = None
        self._start_time = time()
        
        # Quality mappings
        self._qual = {
            '1080p': '1920',
            '720p': '1280',
            '540p': '960',
            '480p': '854',
            '360p': '640'
        }
    
    async def get_buttons(self):
        """Show main video tools menu"""
        buttons = ButtonMaker()
        
        # Filter video modes based on link status
        vid_modes = dict(list(VID_MODE.items())[4:]) if self._isLink else VID_MODE
        
        # Create menu with video tools (2-column layout)
        for key, value in vid_modes.items():
            marker = '🔥 ' if self.mode == key else ''
            buttons.button_data(f"{marker}{value}", f'vidtool {key}')
        
        # Add action buttons
        buttons.button_data(f"{'🔥 ' if self.is_rename else ''}✏️ Rename", 'vidtool rename', 'header')
        buttons.button_data('❌ Cancel', 'vidtool cancel', 'footer')
        
        if self.mode:
            buttons.button_data('✅ Configure', 'vidtool configure', 'footer')
        
        # Menu text
        menu_text = """🎬 <b>VIDEO TOOLS</b>

Select a tool and configure settings:

<b>Available Tools:</b>
1️⃣ Merge Videos
2️⃣ Merge Audio
3️⃣ Add Subtitles
4️⃣ Compress Video
5️⃣ Convert Resolution
6️⃣ Add Watermark
7️⃣ Extract Streams
8️⃣ Trim Video
9️⃣ Sync Subtitles
🔟 Remove Streams"""
        
        self._message = await sendMessage(menu_text, self.message, buttons.build_menu(2))
        
        # Register callback handler
        pfunc = partial(cb_vidtools, obj=self)
        self._handler = self.listener.client.add_handler(
            CallbackQueryHandler(pfunc, filters=regex('^vidtool') & user(self.listener.message.from_user.id)),
            group=-1
        )
        
        # Wait for user selection
        try:
            await wait_for(self.event.wait(), timeout=180)
        except:
            self.mode = 'Task cancelled - timeout!'
            self.is_cancelled = True
        finally:
            # Remove callback handler
            if hasattr(self, '_handler'):
                self.listener.client.remove_handler(*self._handler)
        
        if self.is_cancelled:
            await deleteMessage(self._message)
            return None
        
        return (self.mode, self.newname, self.extra_data)
    
    async def list_buttons(self, mode=''):
        """Show settings menu for selected tool"""
        if not mode:
            mode = self.mode
        
        buttons = ButtonMaker()
        
        if mode == 'compress':
            buttons.button_data('⚡ Faster (Quick)', 'vidtool preset faster', 'header')
            buttons.button_data('🔥 Fast (Balanced)', 'vidtool preset fast')
            buttons.button_data('⏱️ Medium (Std)', 'vidtool preset medium')
            buttons.button_data('🐢 Slow (Small)', 'vidtool preset slow')
        
        elif mode == 'convert':
            buttons.button_data('Select Resolution:', 'vidtool none', 'header')
            for res in ['1080p', '720p', '540p', '480p', '360p']:
                marker = '🔥 ' if self.extra_data.get('resolution') == res else ''
                buttons.button_data(f"{marker}{res}", f'vidtool resolution {res}')
        
        elif mode == 'watermark':
            buttons.button_data('Position:', 'vidtool none', 'header')
            positions = {'tl': '↖️ TL', 'tr': '↗️ TR', 'bl': '↙️ BL', 'br': '↘️ BR'}
            for key, val in positions.items():
                marker = '🔥 ' if self.extra_data.get('position') == key else ''
                buttons.button_data(f"{marker}{val}", f'vidtool position {key}')
        
        elif mode == 'trim':
            buttons.button_data('Format: 00:00:00 - 00:02:30', 'vidtool none', 'header')
            buttons.button_data('📝 Send Time Range', 'vidtool back')
        
        elif mode == 'extract':
            buttons.button_data('Stream Type:', 'vidtool none', 'header')
            for stype in ['Video', 'Audio', 'Subtitle', 'All']:
                marker = '🔥 ' if self.extra_data.get('stream_type') == stype.lower() else ''
                buttons.button_data(f"{marker}{stype}", f'vidtool stream {stype.lower()}')
        
        elif mode == 'subsync':
            buttons.button_data('🤖 Auto Sync', 'vidtool sync_mode auto')
            buttons.button_data('👤 Manual Sync', 'vidtool sync_mode manual')
        
        elif mode == 'rmstream':
            buttons.button_data('Remove:', 'vidtool none', 'header')
            for stype in ['Video', 'Audio', 'Subtitle']:
                marker = '🔥 ' if self.extra_data.get('remove_type') == stype.lower() else ''
                buttons.button_data(f"{marker}{stype}", f'vidtool remove_type {stype.lower()}')
        
        elif mode == 'vid_sub':
            buttons.button_data('Subtitle Mode:', 'vidtool none', 'header')
            buttons.button_data('📄 Softcopy', 'vidtool submode softcopy')
            buttons.button_data('🔥 Hardsub', 'vidtool submode hardsub')
        
        elif mode == 'rename':
            buttons.button_data('Send new filename:', 'vidtool none', 'header')
        
        # Navigation
        buttons.button_data('◀️ Back', 'vidtool back', 'footer')
        buttons.button_data('✅ Start', 'vidtool done', 'footer')
        
        caption = self._get_caption(mode)
        
        if self._message:
            await editMessage(caption, self._message, buttons.build_menu(2))
    
    def _get_caption(self, mode):
        """Get mode-specific caption"""
        captions = {
            'compress': '⚙️ <b>Compress Settings</b>\n\nSelect compression level.',
            'convert': '📐 <b>Convert Resolution</b>\n\nSelect target resolution.',
            'watermark': '🎨 <b>Add Watermark</b>\n\nSelect position.',
            'trim': '✂️ <b>Trim Video</b>\n\nSend start and end time.',
            'extract': '📤 <b>Extract Streams</b>\n\nSelect stream type.',
            'subsync': '🔄 <b>Sync Subtitles</b>\n\nChoose sync method.',
            'rmstream': '🗑️ <b>Remove Streams</b>\n\nSelect stream to remove.',
            'vid_sub': '📝 <b>Add Subtitles</b>\n\nChoose subtitle mode.',
            'rename': '✏️ <b>Rename</b>\n\nSend new filename.',
        }
        return captions.get(mode, f'⚙️ <b>{VID_MODE.get(mode, mode)} Settings</b>')


@new_task
async def cb_vidtools(client, query: CallbackQuery, obj: SelectMode):
    """Handle video tools button callbacks"""
    data = query.data.split()
    
    if len(data) < 2:
        await query.answer()
        return
    
    tool = data[1]
    
    # Check if tool is disabled
    if tool in config_dict.get('DISABLE_VIDTOOLS', []):
        await query.answer(f'{VID_MODE.get(tool, tool)} is disabled!', True)
        return
    
    await query.answer()
    
    if tool == 'done':
        obj.event.set()
    
    elif tool == 'cancel':
        obj.is_cancelled = True
        obj.event.set()
    
    elif tool == 'back':
        await obj.list_buttons()
    
    elif tool == 'configure':
        await obj.list_buttons()
    
    elif tool == 'preset' and len(data) > 2:
        obj.extra_data['preset'] = data[2]
        await obj.list_buttons('compress')
    
    elif tool == 'resolution' and len(data) > 2:
        obj.extra_data['resolution'] = data[2]
        await obj.list_buttons('convert')
    
    elif tool == 'position' and len(data) > 2:
        obj.extra_data['position'] = data[2]
        await obj.list_buttons('watermark')
    
    elif tool == 'stream' and len(data) > 2:
        obj.extra_data['stream_type'] = data[2]
        await obj.list_buttons('extract')
    
    elif tool == 'sync_mode' and len(data) > 2:
        obj.extra_data['sync_mode'] = data[2]
        await obj.list_buttons('subsync')
    
    elif tool == 'remove_type' and len(data) > 2:
        obj.extra_data['remove_type'] = data[2]
        await obj.list_buttons('rmstream')
    
    elif tool == 'submode' and len(data) > 2:
        obj.extra_data['submode'] = data[2]
        await obj.list_buttons('vid_sub')
    
    elif tool == 'rename':
        obj.is_rename = True
        await obj.list_buttons('rename')
    
    elif tool == 'none':
        pass
    
    elif tool in VID_MODE:
        obj.mode = tool
        obj.extra_data.clear()
        obj.is_rename = False
        await obj.list_buttons()


async def message_handler(client, message: Message, obj: SelectMode):
    """Handle user text input (rename, trim times, etc.)"""
    if not message.text:
        return
    
    if obj.is_rename:
        obj.newname = message.text.strip().replace('/', '')
        obj.is_rename = False
    
    elif obj.mode == 'trim':
        obj.extra_data['trim_time'] = message.text.strip()
    
    await obj.list_buttons()

