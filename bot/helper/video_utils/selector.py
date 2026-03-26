from __future__ import annotations
from aiofiles.os import path as aiopath, makedirs
from ast import literal_eval
from asyncio import Event, wait_for, gather, sleep as asyncio_sleep
from functools import partial
from os import path as ospath
from time import time
from PIL import Image
from pyrogram.filters import regex, user
from pyrogram.handlers import MessageHandler, CallbackQueryHandler
from pyrogram.types import Message, CallbackQuery

from bot import config_dict, VID_MODE, LOGGER
from bot.helper.ext_utils.bot_utils import new_task, new_thread, sync_to_async
from bot.helper.ext_utils.fs_utils import clean_target
from bot.helper.ext_utils.links_utils import is_media
from bot.helper.ext_utils.bot_utils import get_readable_time
from bot.helper.listeners import tasks_listener as task
from bot.helper.telegram_helper.button_build import ButtonMaker
from bot.helper.telegram_helper.filters import CustomFilters
from bot.helper.telegram_helper.message_utils import sendMessage, editMessage, deleteMessage

# Global dict to store SelectMode instances by user_id for callback access
vidtools_modes_dict = {}


class SelectMode:
    def __init__(self, listener: task.TaskListener, isLink=False):
        self._isLink = isLink
        self._time = 0
        self._reply = None
        self.listener = listener
        self.is_rename = False
        self.mode = ''
        self.extra_data = {}
        self.newname = ''
        self.event = Event()
        self.message_event = Event()
        self._event_ready = Event()
        self.is_cancelled = False

    @new_task
    async def _event_handler(self):
        try:
            LOGGER.info(f"SelectMode._event_handler started for user {self.listener.user_id}")
            # Store this SelectMode instance globally so callback can access it
            vidtools_modes_dict[self.listener.user_id] = self
            LOGGER.debug(f"VidTools SelectMode stored for user {self.listener.user_id}")
            # Small delay to ensure handler is fully registered
            await asyncio_sleep(0.1)
            self._event_ready.set()
            LOGGER.info(f"SelectMode._event_handler set _event_ready for user {self.listener.user_id}, waiting for event...")
            await wait_for(self.event.wait(), timeout=180)
            LOGGER.info(f"SelectMode._event_handler received event for user {self.listener.user_id}")
        except Exception as e:
            LOGGER.error(f"Event handler error: {e}", exc_info=True)
            self.mode = 'Task has been cancelled, time out!'
            self.is_cancelled = True
            self.event.set()
        finally:
            # Clean up
            if self.listener.user_id in vidtools_modes_dict:
                del vidtools_modes_dict[self.listener.user_id]
            LOGGER.debug(f"VidTools SelectMode cleaned up for user {self.listener.user_id}")

    @new_task
    async def message_event_handler(self, mode=''):
        pfunc = partial(message_handler, obj=self, is_sub=mode == 'subfile')
        handler = self.listener.client.add_handler(MessageHandler(pfunc, user(self.listener.user_id)), group=1)
        try:
            await wait_for(self.message_event.wait(), timeout=60)
        except Exception:
            self.message_event.set()
        finally:
            self.listener.client.remove_handler(*handler)
            self.message_event.clear()

    async def _send_message(self, text: str, buttons):
        LOGGER.info(f"SelectMode._send_message for user {self.listener.user_id}: {text[:50]}...")
        try:
            if not self._reply:
                self._reply = await sendMessage(self.listener.message, text, buttons)
                LOGGER.info(f"SelectMode UI message SENT for user {self.listener.user_id}")
            else:
                await editMessage(text, self._reply, buttons)
                LOGGER.info(f"SelectMode UI message EDITED for user {self.listener.user_id}")
        except Exception as e:
            LOGGER.error(f"Error in _send_message: {e}", exc_info=True)
            raise

    def _captions(self, mode: str = None):
        msg = ('<b>VIDEOS TOOL SETTINGS</b>'
               f'\nMode: <b>{VID_MODE.get(self.mode)}</b>' if (VID_MODE.get(self.mode)) else '')
        msg += f'\nName: <b>{self.newname or "Default"}</b>'
        if self.mode in ('vid_sub', 'watermark'):
            hardsub = self.extra_data.get('hardsub')
            msg += f"\nHardsub Mode: <b>{'Enable' if hardsub else 'Disable'}</b>"
            if hardsub:
                msg += f"\nBold Style: <b>{'Enable' if self.extra_data.get('boldstyle') else 'Disable'}</b>"
                if fontname := self.extra_data.get('fontname') or config_dict.get('HARDSUB_FONT_NAME'):
                    msg += f"\nFont Name: <b>{fontname.replace('_', ' ')}</b>"
                if fontsize := self.extra_data.get('fontsize') or config_dict.get('HARDSUB_FONT_SIZE'):
                    msg += f"\nFont Size: <b>{fontsize}</b>"
                if fontcolour := self.extra_data.get('fontcolour'):
                    msg += f"\nFont Colour: <b>{fontcolour}</b>"
        if quality := self.extra_data.get('quality'):
            msg += f"\nQuality: <b>{quality}</b>"
        if self.mode == 'watermark' and (wmsize := self.extra_data.get('wmsize')):
            msg += f"\nWM Size: <b>{wmsize}</b>"
            if wmsize and (wmposition := self.extra_data.get('wmposition')):
                pos_dict = {'5:5': 'Top Left', 'main_w-overlay_w-5:5': 'Top Right', '5:main_h-overlay_h': 'Bottom Left', 'w-overlay_w-5:main_h-overlay_h-5': 'Bottom Right'}
                msg += f"\nWM Position: <b>{pos_dict.get(wmposition)}</b>"
        if self.mode == 'subsync' and (typee := self.extra_data.get('type')):
            msg += f"\nSync Mode: <b>{typee.lstrip('sync_').title()}</b>"
        match mode:
            case 'rename':
                msg += '\n\n<i>Send valid name with extension...</i>'
            case 'watermark':
                msg += '\n\n<i>Send valid image to set as watermark...</i>'
            case 'subfile':
                msg += '\n\n<i>Send valid subtitle (.ass or .srt) for hardsub...</i>'
            case 'wmsize':
                msg += '\n\n<i>Choose watermark size</i>'
            case 'fontsize':
                msg += ('\n\n<i>Choose font size</i>\n<b>Recommended:</b>\n1080p: <b>21-26 </b>\n720p: <b>16-21</b>\n480p: <b>11-16</b>')
        msg += f"\n\n<i>Time Out: {get_readable_time(180 - (time() - self._time))}</i>"
        return msg

    async def list_buttons(self, mode: str = ''):
        buttons, bnum = ButtonMaker(), 2
        if not mode:
            vid_modes = dict(list(VID_MODE.items())[4:]) if self._isLink else VID_MODE
            for key, value in vid_modes.items():
                buttons.ibutton(f"{'🔥 ' if self.mode == key else ''}{value}", f'vidtool {key}')
            buttons.ibutton(f"{'🔥 ' if self.newname else ''}Rename", 'vidtool rename', 'header')
            buttons.ibutton('Cancel', 'vidtool cancel', 'footer')
            if self.mode:
                buttons.ibutton('Done', 'vidtool done', 'footer')
            if self.mode in ('vid_sub', 'watermark') and await CustomFilters.sudo('', self.listener.message):
                hardsub = self.extra_data.get('hardsub')
                buttons.ibutton(f"{'🔥 ' if hardsub else ''}Hardsub", 'vidtool hardsub', 'header')
                if hardsub:
                    if self.mode == 'watermark':
                        buttons.ibutton(f"{'🔥 ' if await aiopath.exists(self.extra_data.get('subfile', '')) else ''}Sub File", 'vidtool subfile', 'header')
                    buttons.ibutton('Font Style', 'vidtool fontstyle', 'header')
            if self.mode in ('compress', 'watermark') or self.extra_data.get('hardsub'):
                buttons.ibutton('Quality', 'vidtool quality', 'header')
            if self.mode == 'watermark':
                buttons.ibutton('Popup', 'vidtool popupwm', 'header')
        else:
            # mode-specific buttons
            if mode == 'quality':
                bnum = 3
                [buttons.ibutton(f"{'🔥 ' if self.extra_data.get('quality') == key else ''}{key}", f'vidtool quality {key}') for key in ['1080p', '720p', '540p', '480p', '360p']]
                buttons.ibutton('<<', 'vidtool back', 'footer')
                buttons.ibutton('Done', 'vidtool done', 'footer')
            elif mode == 'popupwm':
                bnum = 5
                popupwm = self.extra_data.get('popupwm', 0)
                if popupwm:
                    buttons.ibutton('Reset', 'vidtool popupwm 0', 'header')
                [buttons.ibutton(f"{'🔥 ' if popupwm == key else ''}{key}", f'vidtool popupwm {key}') for key in range(2, 21, 2)]
                buttons.ibutton('<<', 'vidtool back', 'footer')
                buttons.ibutton('Done', 'vidtool done', 'footer')
            elif mode == 'wmsize':
                bnum = 3
                [buttons.ibutton(str(btn), f'vidtool wmsize {btn}') for btn in [5, 10, 15, 20, 25, 30]]
            elif mode == 'fontstyle':
                bnum = 3
                buttons.ibutton('Font Name', 'vidtool fontstyle fontname', 'header')
                buttons.ibutton('Font Size', 'vidtool fontstyle fontsize', 'header')
                buttons.ibutton('Font Colour', 'vidtool fontstyle fontcolour', 'header')
                buttons.ibutton('<<', 'vidtool back', 'footer')
                buttons.ibutton('Done', 'vidtool done', 'footer')
        await self._send_message(self._captions(mode), buttons.build_menu(bnum, 3))

    async def get_buttons(self):
        self._time = time()
        LOGGER.info(f"SelectMode.get_buttons() started for user {self.listener.user_id}")
        future = self._event_handler()
        LOGGER.info(f"SelectMode._event_handler task created for user {self.listener.user_id}")
        await self._event_ready.wait()
        LOGGER.info(f"SelectMode._event_ready received for user {self.listener.user_id}, displaying buttons...")
        await gather(self.list_buttons(), future)
        LOGGER.info(f"SelectMode.gather completed for user {self.listener.user_id}, is_cancelled={self.is_cancelled}")
        if self.is_cancelled:
            await editMessage(self.mode, self._reply)
            return
        await deleteMessage(self._reply)
        return [self.mode, self.newname, self.extra_data]


async def message_handler(_, message: Message, obj: SelectMode, is_sub=False):
    if obj.is_rename and message.text:
        obj.newname = message.text.strip().replace('/', '')
        obj.is_rename = False
    elif obj.mode == 'watermark' and (media := is_media(message)):
        if is_sub:
            if message.document and not media.file_name.lower().endswith(('.ass', '.srt')):
                await sendMessage(message, 'Only .ass or .srt allowed!')
                return
            obj.extra_data['subfile'] = await message.download(ospath.join('watermark', media.file_id))
        else:
            if message.document and 'image' not in getattr(media, 'mime_type', 'None'):
                await sendMessage(message, 'Only image document allowed!')
                return
            fpath = await message.download(ospath.join('watermark', media.file_id))
            await sync_to_async(Image.open(fpath).convert('RGBA').save, ospath.join('watermark', f'{obj.listener.mid}.png'), 'PNG')
            await clean_target(fpath)
            obj.extra_data['subfile'] = ospath.join('watermark', f'{obj.listener.mid}.png')
    elif obj.mode == 'trim' and message.text:
        import re
        if match := re.match(r'(\d{2}:\d{2}:\d{2})\s(\d{2}:\d{2}:\d{2})', message.text.strip()):
            obj.extra_data.update({'start_time': match.group(1), 'end_time': match.group(2)})
        else:
            await sendMessage(message, 'Invalid trim duration format!')
            return
    obj.message_event.set()
    await gather(obj.list_buttons(), deleteMessage(message))


async def cb_vidtools(client, query: CallbackQuery):
    """Callback for video tools buttons. Retrieves SelectMode from global dict."""
    try:
        user_id = query.from_user.id
        LOGGER.info(f"cb_vidtools callback received from user {user_id} with data: {query.data}")
        obj = vidtools_modes_dict.get(user_id)
        
        if not obj:
            LOGGER.warning(f"No SelectMode found for user {user_id} (dict has: {list(vidtools_modes_dict.keys())})")
            await query.answer("Session expired. Please try again.", True)
            return
        
        LOGGER.debug(f"VidTools callback received: {query.data} from user {user_id}")
        data = query.data.split()
        if len(data) < 2:
            LOGGER.warning(f"Invalid callback data format: {query.data}")
            await query.answer("Invalid button!", True)
            return
        if data[1] in config_dict.get('DISABLE_VIDTOOLS', ''):
            await query.answer(f"{VID_MODE[data[1]]} has been disabled!", True)
            return
        await query.answer()
        if data[1] == obj.mode:
            return
        LOGGER.info(f"Processing vidtool action: {data[1]}")
        match data[1]:
            case 'done':
                LOGGER.info(f"User {user_id} clicked Done")
                obj.event.set()
            case 'back':
                LOGGER.info(f"User {user_id} clicked Back")
                if obj.message_event:
                    obj.message_event.set()
                await obj.list_buttons()
            case 'cancel':
                LOGGER.info(f"User {user_id} clicked Cancel")
                obj.mode = 'Task has been cancelled!'
                obj.is_cancelled = True
                obj.event.set()
            case 'quality' | 'popupwm' as value:
                LOGGER.info(f"User {user_id} clicked {value}")
                if len(data) == 3:
                    obj.extra_data[value] = data[2] if value == 'quality' else int(data[2])
                await obj.list_buttons(value)
            case 'hardsub':
                LOGGER.info(f"User {user_id} clicked Hardsub")
                hmode = not bool(obj.extra_data.get('hardsub'))
                if not hmode and obj.mode == 'vid_sub':
                    obj.extra_data.clear()
                obj.extra_data['hardsub'] = hmode
                await obj.list_buttons()
            case 'subfile':
                LOGGER.info(f"User {user_id} clicked Subfile")
                future = obj.message_event_handler('subfile')
                await gather(obj.list_buttons('subfile'), future)
            case 'fontstyle':
                LOGGER.info(f"User {user_id} clicked Fontstyle")
                mode = 'fontstyle'
                if len(data) > 2:
                    mode = data[2]
                    is_bold = mode == 'boldstyle'
                    if len(data) == 4:
                        if not is_bold and obj.extra_data.get(mode) == data[3]:
                            return
                        obj.extra_data[mode] = not literal_eval(data[3]) if is_bold else data[3]
                        if is_bold:
                            mode = 'fontstyle'
                    await obj.list_buttons(mode)
            case 'sync_manual' | 'sync_auto' as value:
                LOGGER.info(f"User {user_id} clicked {value}")
                obj.extra_data['type'] = value
                await obj.list_buttons()
            case 'wmsize' | 'wmposition' as value:
                LOGGER.info(f"User {user_id} clicked {value}")
                obj.extra_data[value] = data[2]
                await obj.list_buttons('wmposition' if value == 'wmsize' else None)
            case value:
                LOGGER.info(f"User {user_id} clicked mode: {value}")
                if value == 'rename':
                    obj.is_rename = True
                else:
                    obj.mode = value
                    obj.extra_data.clear()
                if value in ['watermark', 'rename', 'trim']:
                    LOGGER.info(f"User {user_id}: registering message handler for {value}")
                    future = obj.message_event_handler(value)
                    await gather(obj.list_buttons(value), future)
                    return
                LOGGER.info(f"User {user_id}: updating list_buttons for mode {value}")
                await obj.list_buttons('subsync' if value == 'subsync' else '')
    except Exception as e:
        LOGGER.error(f"Error in cb_vidtools: {e}", exc_info=True)
        try:
            await query.answer(f"Error: {str(e)}", True)
        except Exception as ans_error:
            LOGGER.error(f"Error answering query: {ans_error}")


# Register the callback handler at module level (like in users_settings.py)
# This must be imported at module level to register the handler
def register_vidtools_handlers():
    """Register vidtools callback handler with bot"""
    from bot import bot as bot_instance
    bot_instance.add_handler(CallbackQueryHandler(cb_vidtools, filters=regex("^vidtool")))
    LOGGER.debug("VidTools callback handler registered at module level")

# NOTE: Handler registration is deferred - done in video_tools.py instead
