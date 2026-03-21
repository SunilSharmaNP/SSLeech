"""
Interactive Video Tools Selector - Anime-Leech Style
Provides button-based UI for selecting video tools and configuring settings
"""

from __future__ import annotations
from asyncio import Event, gather, wait_for, wrap_future
from functools import partial
from os import path as ospath
from pyrogram.filters import text, document, photo
from pyrogram.handlers import MessageHandler, CallbackQueryHandler
from pyrogram.types import Message, CallbackQuery
from time import time
from logging import getLogger

from bot import config_dict, VID_MODE
from bot.helper.ext_utils.bot_utils import new_task, new_thread, sync_to_async
from bot.helper.ext_utils.files_utils import clean_target
from bot.helper.ext_utils.links_utils import is_media
from bot.helper.ext_utils.status_utils import get_readable_time
from bot.helper.telegram_helper.button_build import ButtonMaker
from bot.helper.telegram_helper.filters import CustomFilters
from bot.helper.telegram_helper.message_utils import sendMessage, editMessage, deleteMessage

LOGGER = getLogger(__name__)


class SelectMode:
    """Interactive selector for video tools - Anime-Leech style"""
    
    def __init__(self, listener, is_link=False):
        """Initialize selector with listener and link status"""
        self.listener = listener
        self.message = listener.message
        self._isLink = is_link
        self.event = Event()
        self.message_event = None
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

    @new_thread
    def _event_handler(self, *args):
        """Wait for message event with timeout"""
        try:
            self.message_event = Event()
            wait_time = 600  # 10 minutes timeout
            return wait_for(self.message_event.wait(), timeout=wait_time)
        except Exception as e:
            LOGGER.error(f"Event handler error: {e}")
            return None

    def message_event_handler(self, *args):
        """Create message event handler for user input"""
        return self._event_handler(*args)

    async def get_buttons(self):
        """Get initial video tools menu buttons"""
        buttons = ButtonMaker()
        
        # Show appropriate vid modes
        vid_modes = dict(list(VID_MODE.items())[4:]) if self._isLink else VID_MODE

        # Create main menu with 10 video tools
        for key, value in vid_modes.items():
            buttons.button_data(f"{'🔥 ' if self.mode == key else ''}{value}", f'vidtool {key}')

        # Add rename option
        buttons.button_data(f"{'🔥 ' if self.is_rename else ''}✏️ Rename", 'vidtool rename', 'header')
        
        # Add cancel button
        buttons.button_data('❌ Cancel', 'vidtool cancel', 'footer')
        
        # Add proceed button if mode selected
        if self.mode:
            buttons.button_data('✅ Configure', 'vidtool configure', 'footer')

        # Send main menu
        reply_markup = buttons.build_menu(2)
        menu_text = """🎬 <b>Video Tools Menu</b>

Select the tool you want to use, then click <b>Configure</b> to adjust settings.

<b>Available Tools:</b>
1️⃣ Merge Videos (video + video)
2️⃣ Merge Audio (video + audio)
3️⃣ Add Subtitles (video + subtitle)
4️⃣ Compress Video (HEVC codec)
5️⃣ Convert Resolution (1080p-360p)
6️⃣ Add Watermark
7️⃣ Extract Streams (v/a/s)
8️⃣ Trim Video (cut duration)
9️⃣ Sync Subtitles (auto-sync)
🔟 Remove Streams (delete tracks)"""

        self._message = await sendMessage(menu_text, self.message, reply_markup)
        
        # Wait for user to make selections
        timeout_count = 0
        while not self.event.is_set() and timeout_count < 2:
            try:
                await wait_for(self.event.wait(), timeout=600)
            except:
                timeout_count += 1
                if timeout_count < 2:
                    buttons.button_data('⏰ Timeout - Retry', 'vidtool refresh')
                    await editMessage(menu_text, self._message, buttons.build_menu(2))
                    self.event.clear()

        if self.is_cancelled:
            await deleteMessage(self._message)
            return None

        # Return tuple: (mode, name, kwargs)
        kwargs = self.extra_data.copy()
        if self.is_rename:
            kwargs['name'] = self.newname
        
        return (self.mode, self.newname, kwargs)

    async def list_buttons(self, mode=''):
        """Display settings menu for selected tool"""
        if not mode:
            mode = self.mode

        buttons = ButtonMaker()
        
        match mode:
            case 'compress':
                # Compression preset selector
                buttons.button_data('⚡ Faster (Quick, Large)', 'vidtool preset faster', 'header')
                buttons.button_data('🔥 Fast (Balanced)', 'vidtool preset fast')
                buttons.button_data('⏱️ Medium (Standard)', 'vidtool preset medium')
                buttons.button_data('🐢 Slow (Small, Slow)', 'vidtool preset slow')

            case 'convert':
                # Resolution selector
                buttons.button_data('Resolution:', 'vidtool back', 'header')
                for res in ['1080p', '720p', '540p', '480p', '360p']:
                    marker = '🔥 ' if self.extra_data.get('resolution') == res else ''
                    buttons.button_data(f"{marker}{res}", f'vidtool resolution {res}')

            case 'watermark':
                # Watermark position
                buttons.button_data('Position:', 'vidtool back', 'header')
                positions = {'tl': '↖️ TL', 'tr': '↗️ TR', 'bl': '↙️ BL', 'br': '↘️ BR'}
                for key, val in positions.items():
                    marker = '🔥 ' if self.extra_data.get('position') == key else ''
                    buttons.button_data(f"{marker}{val}", f'vidtool position {key}')

            case 'trim':
                buttons.button_data('Format: 00:00:00 - 00:02:30', 'vidtool back', 'header')
                buttons.button_data('📝 Send Trim Time', 'vidtool back')

            case 'extract':
                buttons.button_data('Stream Type:', 'vidtool back', 'header')
                for stype in ['Video', 'Audio', 'Subtitle', 'All']:
                    marker = '🔥 ' if self.extra_data.get('stream_type') == stype.lower() else ''
                    buttons.button_data(f"{marker}{stype}", f'vidtool stream {stype.lower()}')

            case 'subsync':
                buttons.button_data('🤖 Auto Sync', 'vidtool sync_mode auto')
                buttons.button_data('👤 Manual Sync', 'vidtool sync_mode manual')

            case 'rmstream':
                buttons.button_data('Remove:', 'vidtool back', 'header')
                for stype in ['Video', 'Audio', 'Subtitle']:
                    marker = '🔥 ' if self.extra_data.get('remove_type') == stype.lower() else ''
                    buttons.button_data(f"{marker}{stype}", f'vidtool remove_type {stype.lower()}')

            case 'vid_sub':
                buttons.button_data('Subtitle Mode:', 'vidtool back', 'header')
                buttons.button_data('📄 Softcopy', 'vidtool submode softcopy')
                buttons.button_data('🔥 Hardsub (Sudo)', 'vidtool submode hardsub')

            case 'rename':
                buttons.button_data('Send new filename:', 'vidtool back', 'header')

        # Navigation buttons
        if mode:
            buttons.button_data('◀️ Back', 'vidtool back', 'footer')
        
        buttons.button_data('✅ Start Task', 'vidtool done', 'footer')

        caption = self._get_menu_caption(mode)
        if self._message:
            await editMessage(caption, self._message, buttons.build_menu(2))

    def _get_menu_caption(self, mode):
        """Generate menu caption based on mode"""
        captions = {
            'compress': '⚙️ <b>Compress Settings</b>\n\nSelect compression preset.\nFaster = Quick, bigger file\nSlow = Smaller file, takes longer',
            'convert': '📐 <b>Convert Resolution</b>\n\n• 1080p (1920x1080) - Full HD\n• 720p (1280x720) - HD\n• 540p (960x540) - Standard\n• 480p (854x480) - Mobile\n• 360p (640x360) - Low',
            'watermark': '🎨 <b>Watermark Settings</b>\n\nSelect position for your watermark image.',
            'trim': '✂️ <b>Trim Video</b>\n\nSend time range in format:\n<code>start time - end time</code>\nExample: <code>00:30 - 02:45</code>',
            'extract': '📤 <b>Extract Streams</b>\n\nSelect which streams to extract separately.',
            'subsync': '🔄 <b>Sync Subtitles</b>\n\nAuto: AI auto-sync\nManual: Manual adjustment',
            'rmstream': '🗑️ <b>Remove Streams</b>\n\nRemove unwanted audio/subtitle tracks',
            'vid_sub': '📝 <b>Add Subtitles</b>\n\nSoftcopy: Keep as separate stream\nHardsub: Burn into video permanently',
           'rename': '✏️ <b>Rename File</b>\n\nSend new filename (without extension)',
        }
        return captions.get(mode, f'⚙️ <b>{VID_MODE.get(mode, mode)} Settings</b>')


@new_task
async def cb_vidtools(_, query: CallbackQuery, obj: SelectMode):
    """Handle video tools button callbacks"""
    data = query.data.split()
    
    if data[1] in config_dict.get('DISABLE_VIDTOOLS', []):
        await query.answer(f'{VID_MODE.get(data[1], data[1])} is disabled!', True)
        return

    await query.answer()

    match data[1]:
        case 'done':
            obj.event.set()

        case 'cancel':
            obj.mode = 'Task cancelled!'
            obj.is_cancelled = True
            obj.event.set()

        case 'back':
            if obj.message_event:
                obj.message_event.set()
            await obj.list_buttons()

        case 'configure':
            await obj.list_buttons()

        case 'refresh':
            await obj.get_buttons()

        case 'preset':
            if len(data) > 2:
                obj.extra_data['preset'] = data[2]
            await obj.list_buttons('compress')

        case 'resolution':
            if len(data) > 2:
                obj.extra_data['resolution'] = data[2]
            await obj.list_buttons('convert')

        case 'position':
            if len(data) > 2:
                obj.extra_data['position'] = data[2]
            await obj.list_buttons('watermark')

        case 'stream':
            if len(data) > 2:
                obj.extra_data['stream_type'] = data[2]
            await obj.list_buttons('extract')

        case 'sync_mode':
            if len(data) > 2:
                obj.extra_data['sync_mode'] = data[2]
            await obj.list_buttons('subsync')

        case 'remove_type':
            if len(data) > 2:
                obj.extra_data['remove_type'] = data[2]
            await obj.list_buttons('rmstream')

        case 'submode':
            if len(data) > 2:
                obj.extra_data['submode'] = data[2]
            await obj.list_buttons('vid_sub')

        case 'rename':
            obj.is_rename = True
            future = obj.message_event_handler('rename')
            await gather(obj.list_buttons('rename'), wrap_future(future))

        case _:
            if data[1] in VID_MODE:
                obj.mode = data[1]
                obj.extra_data.clear()
                obj.is_rename = False
                await obj.list_buttons()
