#!/usr/bin/env python3
"""Encoding settings UI selector for video compression"""

import asyncio
from time import time
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.handlers import CallbackQueryHandler
from pyrogram.filters import regex
from bot import LOGGER

# Global storage for encoding settings by user
encoding_settings_dict = {}

# Professional Encoding Presets - High-quality with optimization
PROFESSIONAL_PRESETS = {
    "h264_ultra": {
        "label": "🏆 H.264 Ultra (Best Quality)",
        "vcodec": "libx264",
        "crf": 18,
        "preset": "veryslow",
        "tune": "film",
        "profile": "high",
        "level": "4.1",
        "pix_fmt": "yuv420p",
        "acodec": "aac",
        "abitrate": "192k",
        "movflags": "+faststart",
    },
    "h264_professional": {
        "label": "💎 H.264 Professional",
        "vcodec": "libx264",
        "crf": 20,
        "preset": "slow",
        "tune": "film",
        "profile": "high",
        "level": "4.1",
        "pix_fmt": "yuv420p",
        "acodec": "aac",
        "abitrate": "160k",
        "movflags": "+faststart",
    },
    "h264_balanced": {
        "label": "⚖️ H.264 Balanced (Default)",
        "vcodec": "libx264",
        "crf": 23,
        "preset": "medium",
        "tune": "film",
        "profile": "high",
        "pix_fmt": "yuv420p",
        "acodec": "aac",
        "abitrate": "128k",
        "movflags": "+faststart",
    },
    "h265_professional": {
        "label": "🚀 H.265 Professional (Fast)",
        "vcodec": "libx265",
        "crf": 23,
        "preset": "medium",
        "tune": None,
        "pix_fmt": "yuv420p",
        "acodec": "aac",
        "abitrate": "160k",
        "movflags": "+faststart",
    },
    "h265_fast": {
        "label": "⚡ H.265 Fast",
        "vcodec": "libx265",
        "crf": 26,
        "preset": "fast",
        "tune": None,
        "pix_fmt": "yuv420p",
        "acodec": "aac",
        "abitrate": "128k",
        "movflags": "+faststart",
    },
    "mobile_480p": {
        "label": "📱 Mobile (480p)",
        "vcodec": "libx264",
        "crf": 25,
        "preset": "medium",
        "tune": "film",
        "profile": "main",
        "pix_fmt": "yuv420p",
        "acodec": "aac",
        "abitrate": "96k",
        "movflags": "+faststart",
        "resolution": "640x360",
    },
    "720p_professional": {
        "label": "🎬 720p Professional",
        "vcodec": "libx264",
        "crf": 22,
        "preset": "medium",
        "tune": "film",
        "profile": "high",
        "level": "4.0",
        "pix_fmt": "yuv420p",
        "acodec": "aac",
        "abitrate": "128k",
        "movflags": "+faststart",
        "resolution": "1280x720",
    },
    "1080p_professional": {
        "label": "📹 1080p Professional",
        "vcodec": "libx264",
        "crf": 20,
        "preset": "slow",
        "tune": "film",
        "profile": "high",
        "level": "4.1",
        "pix_fmt": "yuv420p",
        "acodec": "aac",
        "abitrate": "192k",
        "movflags": "+faststart",
        "resolution": "1920x1080",
    },
}


class EncodingSelector:
    """Interactive UI for selecting encoding settings"""
    
    def __init__(self, message, is_compress=True):
        self.message = message
        self.user_id = message.from_user.id
        self.is_compress = is_compress
        self.message_obj = None  # Store the sent message object
        
        # Initialize with professional preset defaults
        default_preset = PROFESSIONAL_PRESETS["h264_balanced"]
        self.settings = {
            'preset_id': 'h264_balanced',  # Track which preset is selected
            'preset': default_preset.get('preset', 'medium'),
            'crf': str(default_preset.get('crf', 23)),
            'vcodec': default_preset.get('vcodec', 'libx264'),
            'acodec': default_preset.get('acodec', 'aac'),
            'abitrate': default_preset.get('abitrate', '128k'),
            'resolution': default_preset.get('resolution', 'original'),
            'profile': default_preset.get('profile'),
            'level': default_preset.get('level'),
            'tune': default_preset.get('tune'),
            'pix_fmt': default_preset.get('pix_fmt', 'yuv420p'),
            'movflags': default_preset.get('movflags', '+faststart'),
        }
        self.event = None
        self.is_cancelled = False
    
    async def get_buttons(self):
        """Show UI and get user selection"""
        self.event = asyncio.Event()
        encoding_settings_dict[self.user_id] = self
        
        msg_text = self._build_message()
        buttons = self._build_main_menu()
        
        try:
            self.message_obj = await self.message.reply(msg_text, reply_markup=buttons)
            LOGGER.info(f"EncodingSelector: Message sent for user {self.user_id}")
        except Exception as e:
            LOGGER.error(f"Error sending encoding settings UI: {e}")
            return None
        
        # Wait for selection
        try:
            await asyncio.wait_for(self.event.wait(), timeout=180)
        except asyncio.TimeoutError:
            LOGGER.warning(f"Encoding settings timeout for user {self.user_id}")
            self.is_cancelled = True
        
        if self.user_id in encoding_settings_dict:
            del encoding_settings_dict[self.user_id]
        
        return None if self.is_cancelled else self.settings
    
    async def _send_message(self, text: str, buttons):
        """Send or edit the encoding selector message"""
        from bot.helper.telegram_helper.message_utils import editMessage
        try:
            if self.message_obj:
                await editMessage(self.message_obj, text, buttons)
            else:
                self.message_obj = await self.message.reply(text, reply_markup=buttons)
        except Exception as e:
            LOGGER.error(f"Error in _send_message: {e}", exc_info=True)
            raise
    
    def _build_message(self):
        """Build settings display message"""
        preset_label = PROFESSIONAL_PRESETS.get(self.settings.get('preset_id'), {}).get('label', 'Custom')
        msg = "🎬 <b>PROFESSIONAL ENCODING SETTINGS</b>\n\n"
        msg += f"<b>Preset:</b> {preset_label}\n"
        msg += f"<b>Video Codec:</b> {self.settings['vcodec']}\n"
        msg += f"<b>Quality (CRF):</b> {self.settings['crf']} (lower=better)\n"
        msg += f"<b>Speed (Preset):</b> {self.settings['preset']}\n"
        if self.settings.get('profile'):
            msg += f"<b>Profile:</b> {self.settings['profile']}\n"
        if self.settings.get('tune'):
            msg += f"<b>Tune:</b> {self.settings['tune']}\n"
        msg += f"<b>Audio:</b> {self.settings['acodec']} ({self.settings['abitrate']})\n"
        msg += f"<b>Resolution:</b> {self.settings['resolution']}\n\n"
        msg += "⚙️ Click presets for quick professional settings!"
        return msg
    
    def _build_main_menu(self):
        """Build main encoding menu buttons"""
        from bot.helper.telegram_helper.button_build import ButtonMaker
        buttons = ButtonMaker()
        
        buttons.ibutton(f"⚙️ Preset: {self.settings['preset']}", f"enc preset")
        buttons.ibutton(f"📊 CRF: {self.settings['crf']}", f"enc crf")
        
        buttons.ibutton(f"🎥 Codec: {self.settings['vcodec']}", f"enc vcodec")
        buttons.ibutton(f"🔊 Audio: {self.settings['acodec']}", f"enc acodec")
        
        buttons.ibutton(f"📐 Res: {self.settings['resolution']}", f"enc res")
        buttons.ibutton(f"⏱️ FPS: {self.settings['fps']}", f"enc fps")
        
        buttons.ibutton("⚡ Profiles", f"enc profile")
        
        buttons.ibutton("✅ Apply", f"enc apply")
        buttons.ibutton("❌ Cancel", f"enc cancel")
        
        return buttons.build_menu(2)
    
    def _build_preset_menu(self):
        """Build preset selection menu"""
        from bot.helper.telegram_helper.button_build import ButtonMaker
        presets = ['ultrafast', 'superfast', 'veryfast', 'faster', 'fast', 'medium', 'slow', 'slower', 'veryslow']
        buttons = ButtonMaker()
        
        for preset in presets:
            label = f"✅ {preset}" if self.settings['preset'] == preset else preset
            buttons.ibutton(label, f"enc encpreset {preset}")
        
        buttons.ibutton("⬅️ Back", f"enc back")
        return buttons.build_menu(3)
    
    def _build_crf_menu(self):
        """Build CRF (quality) selection menu"""
        from bot.helper.telegram_helper.button_build import ButtonMaker
        crf_values = ['18', '20', '23', '25', '28']
        buttons = ButtonMaker()
        
        for crf in crf_values:
            label = f"✅ {crf}" if self.settings['crf'] == crf else crf
            buttons.ibutton(label, f"enc enccrf {crf}")
        
        buttons.ibutton("⬅️ Back", f"enc back")
        return buttons.build_menu(3)
    
    def _build_vcodec_menu(self):
        """Build video codec selection menu"""
        from bot.helper.telegram_helper.button_build import ButtonMaker
        codecs = {
            'libx264': 'H.264 (Fast)',
            'libx265': 'HEVC (Better)',
            'libvpx-vp9': 'VP9 (Web)',
        }
        buttons = ButtonMaker()
        
        for codec, label in codecs.items():
            display = f"✅ {label}" if self.settings['vcodec'] == codec else label
            buttons.ibutton(display, f"enc encvcodec {codec}")
        
        buttons.ibutton("⬅️ Back", f"enc back")
        return buttons.build_menu(1)
    
    def _build_acodec_menu(self):
        """Build audio codec selection menu"""
        from bot.helper.telegram_helper.button_build import ButtonMaker
        codecs = {
            'aac': 'AAC (MP4)',
            'libopus': 'Opus (Modern)',
            'libmp3lame': 'MP3 (Compat)',
        }
        buttons = ButtonMaker()
        
        for codec, label in codecs.items():
            display = f"✅ {label}" if self.settings['acodec'] == codec else label
            buttons.ibutton(display, f"enc encacodec {codec}")
        
        buttons.ibutton("⬅️ Back", f"enc back")
        return buttons.build_menu(1)
    
    def _build_resolution_menu(self):
        """Build resolution selection menu"""
        from bot.helper.telegram_helper.button_build import ButtonMaker
        resolutions = [
            ('360p', '640x360'),
            ('480p', '854x480'),
            ('720p', '1280x720'),
            ('1080p', '1920x1080'),
            ('Original', 'original'),
        ]
        buttons = ButtonMaker()
        
        for name, res in resolutions:
            label = f"✅ {name}" if (self.settings['resolution'] == name or self.settings['resolution'] == res) else name
            buttons.ibutton(label, f"enc encres {res}")
        
        buttons.ibutton("⬅️ Back", f"enc back")
        return buttons.build_menu(3)
    
    def _build_fps_menu(self):
        """Build FPS selection menu"""
        from bot.helper.telegram_helper.button_build import ButtonMaker
        fps_options = [
            ('24 FPS', '24'),
            ('30 FPS', '30'),
            ('60 FPS', '60'),
            ('Original', 'original'),
        ]
        buttons = ButtonMaker()
        
        for name, fps in fps_options:
            label = f"✅ {name}" if (self.settings['fps'] == fps or self.settings['fps'] == name.split()[0]) else name
            buttons.ibutton(label, f"enc encfps {fps}")
        
        buttons.ibutton("⬅️ Back", f"enc back")
        return buttons.build_menu(2)
    
    def _build_profile_menu(self):
        """Build quick encoding profiles from professional presets"""
        from bot.helper.telegram_helper.button_build import ButtonMaker
        buttons = ButtonMaker()
        
        for preset_id, preset_info in PROFESSIONAL_PRESETS.items():
            label = preset_info.get('label', preset_id)
            is_selected = (self.settings.get('preset_id') == preset_id)
            display = f"✅ {label}" if is_selected else label
            buttons.ibutton(display, f"enc encprof {preset_id}")
        
        buttons.ibutton("⬅️ Back", f"enc back")
        return buttons.build_menu(1)


async def cb_encoding(client, query):
    """Callback for encoding selector buttons"""
    try:
        user_id = query.from_user.id
        data = query.data.split()
        
        if len(data) < 2:
            await query.answer("Invalid button", True)
            return
        
        selector = encoding_settings_dict.get(user_id)
        if not selector:
            await query.answer("Settings expired", True)
            return
        
        action = data[1]
        value = data[2] if len(data) > 2 else None
        
        LOGGER.info(f"Encoding callback: action={action}, value={value}, user={user_id}")
        await query.answer()
        
        match action:
            case 'preset':
                await selector._send_message(
                    "⚙️ <b>Select Encoding Preset</b>\n(Faster = lower quality loss)",
                    selector._build_preset_menu()
                )
            case 'encpreset':
                selector.settings['preset'] = value
                LOGGER.info(f"Set preset to: {value}")
                await selector._send_message(selector._build_message(), selector._build_main_menu())
            
            case 'crf':
                await selector._send_message(
                    "📊 <b>Select Quality (CRF)</b>\n18=Best, 28=Fast",
                    selector._build_crf_menu()
                )
            case 'enccrf':
                selector.settings['crf'] = value
                LOGGER.info(f"Set CRF to: {value}")
                await selector._send_message(selector._build_message(), selector._build_main_menu())
            
            case 'vcodec':
                await selector._send_message(
                    "🎥 <b>Select Video Codec</b>",
                    selector._build_vcodec_menu()
                )
            case 'encvcodec':
                selector.settings['vcodec'] = value
                LOGGER.info(f"Set video codec to: {value}")
                await selector._send_message(selector._build_message(), selector._build_main_menu())
            
            case 'acodec':
                await selector._send_message(
                    "🔊 <b>Select Audio Codec</b>",
                    selector._build_acodec_menu()
                )
            case 'encacodec':
                selector.settings['acodec'] = value
                LOGGER.info(f"Set audio codec to: {value}")
                await selector._send_message(selector._build_message(), selector._build_main_menu())
            
            case 'res':
                await selector._send_message(
                    "📐 <b>Select Resolution</b>",
                    selector._build_resolution_menu()
                )
            case 'encres':
                res_map = {'640x360': '360p', '854x480': '480p', '1280x720': '720p', '1920x1080': '1080p', 'original': 'Original'}
                selector.settings['resolution'] = res_map.get(value, value)
                LOGGER.info(f"Set resolution to: {value}")
                await selector._send_message(selector._build_message(), selector._build_main_menu())
            
            case 'fps':
                await selector._send_message(
                    "⏱️ <b>Select Frame Rate</b>",
                    selector._build_fps_menu()
                )
            case 'encfps':
                selector.settings['fps'] = value
                LOGGER.info(f"Set FPS to: {value}")
                await selector._send_message(selector._build_message(), selector._build_main_menu())
            
            case 'profile':
                await selector._send_message(
                    "⚡ <b>Quick Encoding Profiles</b>",
                    selector._build_profile_menu()
                )
            case 'encprof':
                # Apply professional preset
                if value in PROFESSIONAL_PRESETS:
                    preset_data = PROFESSIONAL_PRESETS[value]
                    selector.settings['preset_id'] = value
                    selector.settings['preset'] = preset_data.get('preset', 'medium')
                    selector.settings['crf'] = str(preset_data.get('crf', 23))
                    selector.settings['vcodec'] = preset_data.get('vcodec', 'libx264')
                    selector.settings['acodec'] = preset_data.get('acodec', 'aac')
                    selector.settings['abitrate'] = preset_data.get('abitrate', '128k')
                    selector.settings['profile'] = preset_data.get('profile')
                    selector.settings['level'] = preset_data.get('level')
                    selector.settings['tune'] = preset_data.get('tune')
                    selector.settings['pix_fmt'] = preset_data.get('pix_fmt', 'yuv420p')
                    selector.settings['movflags'] = preset_data.get('movflags', '+faststart')
                    selector.settings['resolution'] = preset_data.get('resolution', 'original')
                    LOGGER.info(f"Applied professional preset: {value}")
                await selector._send_message(selector._build_message(), selector._build_main_menu())
            
            case 'back':
                await selector._send_message(selector._build_message(), selector._build_main_menu())
            
            case 'apply':
                selector.event.set()
            
            case 'cancel':
                selector.is_cancelled = True
                selector.event.set()
    
    except Exception as e:
        LOGGER.error(f"Encoding callback error: {e}", exc_info=True)
        try:
            await query.answer(f"Error: {str(e)}", True)
        except:
            pass


def register_encoding_handlers():
    """Register encoding selector callback handler"""
    from bot import bot as bot_instance
    bot_instance.add_handler(CallbackQueryHandler(cb_encoding, filters=regex("^enc ")))
    LOGGER.info("Encoding selector handler registered")
