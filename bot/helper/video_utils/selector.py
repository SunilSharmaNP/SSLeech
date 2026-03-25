from __future__ import annotations
from aiofiles.os import path as aiopath, makedirs
from ast import literal_eval
from asyncio import Event, wait_for, gather
from functools import partial
from os import path as ospath
from PIL import Image
from pyrogram.filters import regex, user
from pyrogram.handlers import MessageHandler, CallbackQueryHandler
from pyrogram.types import Message, CallbackQuery

from bot import config_dict, VID_MODE
from bot.helper.ext_utils.bot_utils import new_task, new_thread, sync_to_async
from bot.helper.ext_utils.fs_utils import clean_target
from bot.helper.ext_utils.links_utils import is_media
from bot.helper.ext_utils.bot_utils import get_readable_time
from bot.helper.listeners import tasks_listener as task
from bot.helper.telegram_helper.button_build import ButtonMaker
from bot.helper.telegram_helper.filters import CustomFilters
from bot.helper.telegram_helper.message_utils import sendMessage, editMessage, deleteMessage


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
        self.is_cancelled = False

    @new_task
    async def _event_handler(self):
        pfunc = partial(cb_vidtools, obj=self)
        handler = self.listener.client.add_handler(CallbackQueryHandler(pfunc, filters=regex('^vidtool') & user(self.listener.user_id)), group=-1)
        try:
            await wait_for(self.event.wait(), timeout=180)
        except Exception:
            self.mode = 'Task has been cancelled, time out!'
            self.is_cancelled = True
            self.event.set()
        finally:
            self.listener.client.remove_handler(*handler)

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
        if not self._reply:
            self._reply = await sendMessage(text, self.listener.message, buttons)
        else:
            await editMessage(text, self._reply, buttons)

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
                buttons.button_data(f"{'🔥 ' if self.mode == key else ''}{value}", f'vidtool {key}')
            buttons.button_data(f"{'🔥 ' if self.newname else ''}Rename", 'vidtool rename', 'header')
            buttons.button_data('Cancel', 'vidtool cancel', 'footer')
            if self.mode:
                buttons.button_data('Done', 'vidtool done', 'footer')
            if self.mode in ('vid_sub', 'watermark') and await CustomFilters.sudo('', self.listener.message):
                hardsub = self.extra_data.get('hardsub')
                buttons.button_data(f"{'🔥 ' if hardsub else ''}Hardsub", 'vidtool hardsub', 'header')
                if hardsub:
                    if self.mode == 'watermark':
                        buttons.button_data(f"{'🔥 ' if await aiopath.exists(self.extra_data.get('subfile', '')) else ''}Sub File", 'vidtool subfile', 'header')
                    buttons.button_data('Font Style', 'vidtool fontstyle', 'header')
            if self.mode in ('compress', 'watermark') or self.extra_data.get('hardsub'):
                buttons.button_data('Quality', 'vidtool quality', 'header')
            if self.mode == 'watermark':
                buttons.button_data('Popup', 'vidtool popupwm', 'header')
        else:
            # mode-specific buttons
            if mode == 'quality':
                bnum = 3
                [buttons.button_data(f"{'🔥 ' if self.extra_data.get('quality') == key else ''}{key}", f'vidtool quality {key}') for key in ['1080p', '720p', '540p', '480p', '360p']]
                buttons.button_data('<<', 'vidtool back', 'footer')
                buttons.button_data('Done', 'vidtool done', 'footer')
            elif mode == 'popupwm':
                bnum = 5
                popupwm = self.extra_data.get('popupwm', 0)
                if popupwm:
                    buttons.button_data('Reset', 'vidtool popupwm 0', 'header')
                [buttons.button_data(f"{'🔥 ' if popupwm == key else ''}{key}", f'vidtool popupwm {key}') for key in range(2, 21, 2)]
                buttons.button_data('<<', 'vidtool back', 'footer')
                buttons.button_data('Done', 'vidtool done', 'footer')
            elif mode == 'wmsize':
                bnum = 3
                [buttons.button_data(str(btn), f'vidtool wmsize {btn}') for btn in [5, 10, 15, 20, 25, 30]]
            elif mode == 'fontstyle':
                bnum = 3
                buttons.button_data('Font Name', 'vidtool fontstyle fontname', 'header')
                buttons.button_data('Font Size', 'vidtool fontstyle fontsize', 'header')
                buttons.button_data('Font Colour', 'vidtool fontstyle fontcolour', 'header')
                buttons.button_data('<<', 'vidtool back', 'footer')
                buttons.button_data('Done', 'vidtool done', 'footer')
        await self._send_message(self._captions(mode), buttons.build_menu(bnum, 3))

    async def get_buttons(self):
        future = self._event_handler()
        await gather(self.list_buttons(), future)
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
                await sendMessage('Only .ass or .srt allowed!', message)
                return
            obj.extra_data['subfile'] = await message.download(ospath.join('watermark', media.file_id))
        else:
            if message.document and 'image' not in getattr(media, 'mime_type', 'None'):
                await sendMessage('Only image document allowed!', message)
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
            await sendMessage('Invalid trim duration format!', message)
            return
    obj.message_event.set()
    await gather(obj.list_buttons(), deleteMessage(message))


@new_task
async def cb_vidtools(_, query: CallbackQuery, obj: SelectMode):
    data = query.data.split()
    if data[1] in config_dict.get('DISABLE_VIDTOOLS', ''):
        await query.answer(f"{VID_MODE[data[1]]} has been disabled!", True)
        return
    await query.answer()
    if data[1] == obj.mode:
        return
    match data[1]:
        case 'done':
            obj.event.set()
        case 'back':
            if obj.message_event:
                obj.message_event.set()
            await obj.list_buttons()
        case 'cancel':
            obj.mode = 'Task has been cancelled!'
            obj.is_cancelled = True
            obj.event.set()
        case 'quality' | 'popupwm' as value:
            if len(data) == 3:
                obj.extra_data[value] = data[2] if value == 'quality' else int(data[2])
            await obj.list_buttons(value)
        case 'hardsub':
            hmode = not bool(obj.extra_data.get('hardsub'))
            if not hmode and obj.mode == 'vid_sub':
                obj.extra_data.clear()
            obj.extra_data['hardsub'] = hmode
            await obj.list_buttons()
        case 'subfile':
            future = obj.message_event_handler('subfile')
            await gather(obj.list_buttons('subfile'), future)
        case 'fontstyle':
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
            obj.extra_data['type'] = value
            await obj.list_buttons()
        case 'wmsize' | 'wmposition' as value:
            obj.extra_data[value] = data[2]
            await obj.list_buttons('wmposition' if value == 'wmsize' else None)
        case value:
            if value == 'rename':
                obj.is_rename = True
            else:
                obj.mode = value
                obj.extra_data.clear()
            if value in ['watermark', 'rename', 'trim']:
                future = obj.message_event_handler(value)
                await gather(obj.list_buttons(value), future)
                return
            await obj.list_buttons('subsync' if value == 'subsync' else '')
