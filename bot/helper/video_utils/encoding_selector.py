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


class EncodingSelector:
    """Interactive UI for selecting encoding settings"""
    
    def __init__(self, message, is_compress=True):
        self.message = message
        self.user_id = message.from_user.id
        self.is_compress = is_compress
        self.message_obj = None  # Store the sent message object
        self.settings = {
            'preset': 'fast',
            'crf': '23',
            'vcodec': 'libx264',
            'acodec': 'aac',
            'resolution': 'original',
            'fps': 'original',
            'profile': None
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
    
    def _build_message(self):
        """Build settings display message"""
        msg = "🎬 <b>ENCODING SETTINGS</b>\n\n"
        msg += f"<b>Preset:</b> {self.settings['preset']} (speed vs quality)\n"
        msg += f"<b>CRF:</b> {self.settings['crf']} (quality 0-51, lower=better)\n"
        msg += f"<b>Video Codec:</b> {self.settings['vcodec']}\n"
        msg += f"<b>Audio Codec:</b> {self.settings['acodec']}\n"
        msg += f"<b>Resolution:</b> {self.settings['resolution']}\n"
        msg += f"<b>FPS:</b> {self.settings['fps']}\n\n"
        msg += "Select options below or use quick presets ⚙️"
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
        """Build quick encoding profiles"""
        from bot.helper.telegram_helper.button_build import ButtonMaker
        profiles = {
            'ultra_fast': '⚡ Ultra Fast',
            'fast': '🚀 Fast',
            'balanced': '⚖️ Balanced',
            'quality': '💎 Quality',
            'web': '🌐 Web (VP9)',
        }
        buttons = ButtonMaker()
        
        for profile_id, label in profiles.items():
            buttons.ibutton(label, f"enc encprof {profile_id}")
        
        buttons.ibutton("⬅️ Back", f"enc back")
        return buttons.build_menu(1)


def get_profile_settings(profile_id: str) -> dict:
    """Get settings for quick encoding profile"""
    profiles = {
        'ultra_fast': {
            'preset': 'ultrafast',
            'crf': '28',
            'vcodec': 'libx264',
            'acodec': 'aac',
            'resolution': '480p',
            'fps': 'original'
        },
        'fast': {
            'preset': 'fast',
            'crf': '23',
            'vcodec': 'libx264',
            'acodec': 'aac',
            'resolution': '720p',
            'fps': 'original'
        },
        'balanced': {
            'preset': 'medium',
            'crf': '23',
            'vcodec': 'libx265',
            'acodec': 'aac',
            'resolution': 'original',
            'fps': 'original'
        },
        'quality': {
            'preset': 'slow',
            'crf': '20',
            'vcodec': 'libx265',
            'acodec': 'aac',
            'resolution': 'original',
            'fps': 'original'
        },
        'web': {
            'preset': 'medium',
            'crf': '30',
            'vcodec': 'libvpx-vp9',
            'acodec': 'libopus',
            'resolution': '720p',
            'fps': 'original'
        }
    }
    return profiles.get(profile_id, profiles['balanced'])


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
                profile_settings = get_profile_settings(value)
                selector.settings.update(profile_settings)
                LOGGER.info(f"Applied profile: {value}")
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
