#!/usr/bin/env python3
"""Encoding settings UI selector for video compression"""

import asyncio
from time import time
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
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
        buttons = [
            [
                InlineKeyboardButton(f"⚙️ Preset: {self.settings['preset']}", 
                                    callback_data=f"enc_preset_{self.user_id}"),
                InlineKeyboardButton(f"📊 CRF: {self.settings['crf']}", 
                                    callback_data=f"enc_crf_{self.user_id}"),
            ],
            [
                InlineKeyboardButton(f"🎥 Codec: {self.settings['vcodec']}", 
                                    callback_data=f"enc_vcodec_{self.user_id}"),
                InlineKeyboardButton(f"🔊 Audio: {self.settings['acodec']}", 
                                    callback_data=f"enc_acodec_{self.user_id}"),
            ],
            [
                InlineKeyboardButton(f"📐 Res: {self.settings['resolution']}", 
                                    callback_data=f"enc_res_{self.user_id}"),
                InlineKeyboardButton(f"⏱️ FPS: {self.settings['fps']}", 
                                    callback_data=f"enc_fps_{self.user_id}"),
            ],
            [
                InlineKeyboardButton("⚡ Profiles", callback_data=f"enc_profile_{self.user_id}"),
            ],
            [
                InlineKeyboardButton("✅ Apply Settings", callback_data=f"enc_apply_{self.user_id}"),
                InlineKeyboardButton("❌ Cancel", callback_data=f"enc_cancel_{self.user_id}"),
            ],
        ]
        return InlineKeyboardMarkup(buttons)
    
    def _build_preset_menu(self):
        """Build preset selection menu"""
        presets = ['ultrafast', 'superfast', 'veryfast', 'faster', 'fast', 'medium', 'slow', 'slower', 'veryslow']
        buttons = []
        row = []
        
        for preset in presets:
            label = preset
            if self.settings['preset'] == preset:
                label = f"✅ {preset}"
            
            row.append(InlineKeyboardButton(label, callback_data=f"encpreset_{preset}_{self.user_id}"))
            if len(row) == 3:
                buttons.append(row)
                row = []
        
        if row:
            buttons.append(row)
        
        buttons.append([InlineKeyboardButton("⬅️ Back", callback_data=f"enc_main_{self.user_id}")])
        return InlineKeyboardMarkup(buttons)
    
    def _build_crf_menu(self):
        """Build CRF (quality) selection menu"""
        # CRF: 18-28 is useful range (lower = better, slower)
        crf_values = ['18', '20', '23', '25', '28']
        buttons = []
        row = []
        
        for crf in crf_values:
            label = crf
            if self.settings['crf'] == crf:
                label = f"✅ {crf}"
            
            row.append(InlineKeyboardButton(label, callback_data=f"enccrf_{crf}_{self.user_id}"))
            if len(row) == 3:
                buttons.append(row)
                row = []
        
        if row:
            buttons.append(row)
        
        buttons.append([InlineKeyboardButton("⬅️ Back", callback_data=f"enc_main_{self.user_id}")])
        return InlineKeyboardMarkup(buttons)
    
    def _build_vcodec_menu(self):
        """Build video codec selection menu"""
        codecs = {
            'libx264': 'H.264 (Fast)',
            'libx265': 'HEVC (Better)',
            'libvpx-vp9': 'VP9 (Web)',
        }
        buttons = []
        
        for codec, label in codecs.items():
            display = label
            if self.settings['vcodec'] == codec:
                display = f"✅ {label}"
            
            buttons.append([InlineKeyboardButton(display, callback_data=f"encvcodec_{codec}_{self.user_id}")])
        
        buttons.append([InlineKeyboardButton("⬅️ Back", callback_data=f"enc_main_{self.user_id}")])
        return InlineKeyboardMarkup(buttons)
    
    def _build_acodec_menu(self):
        """Build audio codec selection menu"""
        codecs = {
            'aac': 'AAC (MP4)',
            'libopus': 'Opus (Modern)',
            'libmp3lame': 'MP3 (Compat)',
        }
        buttons = []
        
        for codec, label in codecs.items():
            display = label
            if self.settings['acodec'] == codec:
                display = f"✅ {label}"
            
            buttons.append([InlineKeyboardButton(display, callback_data=f"encacodec_{codec}_{self.user_id}")])
        
        buttons.append([InlineKeyboardButton("⬅️ Back", callback_data=f"enc_main_{self.user_id}")])
        return InlineKeyboardMarkup(buttons)
    
    def _build_resolution_menu(self):
        """Build resolution selection menu"""
        resolutions = [
            ('360p', '640x360'),
            ('480p', '854x480'),
            ('720p', '1280x720'),
            ('1080p', '1920x1080'),
            ('Original', 'original'),
        ]
        buttons = []
        row = []
        
        for name, res in resolutions:
            label = name
            if self.settings['resolution'] == name or self.settings['resolution'] == res:
                label = f"✅ {name}"
            
            row.append(InlineKeyboardButton(label, callback_data=f"encres_{res}_{self.user_id}"))
            if len(row) == 3:
                buttons.append(row)
                row = []
        
        if row:
            buttons.append(row)
        
        buttons.append([InlineKeyboardButton("⬅️ Back", callback_data=f"enc_main_{self.user_id}")])
        return InlineKeyboardMarkup(buttons)
    
    def _build_fps_menu(self):
        """Build FPS selection menu"""
        fps_options = [
            ('24 FPS', '24'),
            ('30 FPS', '30'),
            ('60 FPS', '60'),
            ('Original', 'original'),
        ]
        buttons = []
        
        for name, fps in fps_options:
            label = name
            if self.settings['fps'] == fps or self.settings['fps'] == name.split()[0]:
                label = f"✅ {name}"
            
            buttons.append([InlineKeyboardButton(label, callback_data=f"encfps_{fps}_{self.user_id}")])
        
        buttons.append([InlineKeyboardButton("⬅️ Back", callback_data=f"enc_main_{self.user_id}")])
        return InlineKeyboardMarkup(buttons)
    
    def _build_profile_menu(self):
        """Build quick encoding profiles"""
        profiles = {
            'ultra_fast': ('⚡ Ultra Fast', 'ultrafast', '28', 'libx264', 'aac', '480p'),
            'fast': ('🚀 Fast', 'fast', '23', 'libx264', 'aac', '720p'),
            'balanced': ('⚖️ Balanced', 'medium', '23', 'libx265', 'aac', 'original'),
            'quality': ('💎 Quality', 'slow', '20', 'libx265', 'aac', 'original'),
            'web': ('🌐 Web (VP9)', 'medium', '30', 'libvpx-vp9', 'libopus', '720p'),
        }
        
        buttons = []
        for profile_id, (label, preset, crf, vcodec, acodec, res) in profiles.items():
            buttons.append([InlineKeyboardButton(label, callback_data=f"encprof_{profile_id}_{self.user_id}")])
        
        buttons.append([InlineKeyboardButton("⬅️ Back", callback_data=f"enc_main_{self.user_id}")])
        return InlineKeyboardMarkup(buttons)


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


async def register_encoding_handlers(client):
    """Register encoding selector callback handlers"""
    from pyrogram.handlers import CallbackQueryHandler
    from pyrogram.filters import regex
    
    async def encoding_callback_handler(client, callback_query):
        data = callback_query.data
        
        # Extract user_id from the end of callback data (after last _)
        try:
            last_underscore = data.rfind('_')
            user_id = int(data[last_underscore+1:])
        except (ValueError, IndexError):
            await callback_query.answer("Invalid callback data", show_alert=True)
            return
        
        LOGGER.info(f"Encoding callback: data={data}, user_id={user_id}")
        
        selector = encoding_settings_dict.get(user_id)
        if not selector:
            LOGGER.warning(f"Selector not found for user {user_id}")
            await callback_query.answer("Settings expired", show_alert=True)
            return
        
        try:
            # Check which callback format this is
            if data.startswith('enc_'):
                # Menu navigation callbacks: enc_preset_, enc_crf_, etc.
                parts = data[4:-len(str(user_id))-1].split('_')  # Remove 'enc_' prefix and user_id suffix
                action = parts[0] if parts else ''
                
                LOGGER.info(f"Menu action: {action}")
                
                if action == 'main':
                    buttons = selector._build_main_menu()
                    msg = selector._build_message()
                    await callback_query.edit_message_text(msg, reply_markup=buttons)
                    await callback_query.answer()
                
                elif action == 'preset':
                    buttons = selector._build_preset_menu()
                    await callback_query.edit_message_text(
                        "⚙️ <b>Select Encoding Preset</b>\n(Faster = lower quality loss)",
                        reply_markup=buttons
                    )
                    await callback_query.answer()
                
                elif action == 'crf':
                    buttons = selector._build_crf_menu()
                    await callback_query.edit_message_text(
                        "📊 <b>Select Quality (CRF)</b>\n18=Best, 28=Fast",
                        reply_markup=buttons
                    )
                    await callback_query.answer()
                
                elif action == 'vcodec':
                    buttons = selector._build_vcodec_menu()
                    await callback_query.edit_message_text(
                        "🎥 <b>Select Video Codec</b>",
                        reply_markup=buttons
                    )
                    await callback_query.answer()
                
                elif action == 'acodec':
                    buttons = selector._build_acodec_menu()
                    await callback_query.edit_message_text(
                        "🔊 <b>Select Audio Codec</b>",
                        reply_markup=buttons
                    )
                    await callback_query.answer()
                
                elif action == 'res':
                    buttons = selector._build_resolution_menu()
                    await callback_query.edit_message_text(
                        "📐 <b>Select Resolution</b>",
                        reply_markup=buttons
                    )
                    await callback_query.answer()
                
                elif action == 'fps':
                    buttons = selector._build_fps_menu()
                    await callback_query.edit_message_text(
                        "⏱️ <b>Select Frame Rate</b>",
                        reply_markup=buttons
                    )
                    await callback_query.answer()
                
                elif action == 'profile':
                    buttons = selector._build_profile_menu()
                    await callback_query.edit_message_text(
                        "⚡ <b>Quick Encoding Profiles</b>",
                        reply_markup=buttons
                    )
                    await callback_query.answer()
                
                elif action == 'apply':
                    selector.event.set()
                    await callback_query.answer("✅ Settings applied!")
                
                elif action == 'cancel':
                    selector.is_cancelled = True
                    selector.event.set()
                    await callback_query.answer("❌ Cancelled")
                    
            # Selection callbacks: encpreset_, enccrf_, etc.
            elif data.startswith('encpreset_'):
                # Format: encpreset_VALUE_userid
                preset = data[len('encpreset_'):-len(str(user_id))-1]
                LOGGER.info(f"Selected preset: {preset}")
                selector.settings['preset'] = preset
                buttons = selector._build_main_menu()
                msg = selector._build_message()
                await callback_query.edit_message_text(msg, reply_markup=buttons)
                await callback_query.answer(f"✅ Preset: {preset}")
            
            elif data.startswith('enccrf_'):
                # Format: enccrf_VALUE_userid
                crf = data[len('enccrf_'):-len(str(user_id))-1]
                LOGGER.info(f"Selected CRF: {crf}")
                selector.settings['crf'] = crf
                buttons = selector._build_main_menu()
                msg = selector._build_message()
                await callback_query.edit_message_text(msg, reply_markup=buttons)
                await callback_query.answer(f"✅ CRF: {crf}")
            
            elif data.startswith('encvcodec_'):
                # Format: encvcodec_VALUE_userid
                codec = data[len('encvcodec_'):-len(str(user_id))-1]
                LOGGER.info(f"Selected video codec: {codec}")
                selector.settings['vcodec'] = codec
                buttons = selector._build_main_menu()
                msg = selector._build_message()
                await callback_query.edit_message_text(msg, reply_markup=buttons)
                await callback_query.answer(f"✅ Codec: {codec}")
            
            elif data.startswith('encacodec_'):
                # Format: encacodec_VALUE_userid
                codec = data[len('encacodec_'):-len(str(user_id))-1]
                LOGGER.info(f"Selected audio codec: {codec}")
                selector.settings['acodec'] = codec
                buttons = selector._build_main_menu()
                msg = selector._build_message()
                await callback_query.edit_message_text(msg, reply_markup=buttons)
                await callback_query.answer(f"✅ Audio: {codec}")
            
            elif data.startswith('encres_'):
                # Format: encres_VALUE_userid
                res = data[len('encres_'):-len(str(user_id))-1]
                LOGGER.info(f"Selected resolution: {res}")
                res_map = {'640x360': '360p', '854x480': '480p', '1280x720': '720p', '1920x1080': '1080p', 'original': 'Original'}
                selector.settings['resolution'] = res_map.get(res, res)
                buttons = selector._build_main_menu()
                msg = selector._build_message()
                await callback_query.edit_message_text(msg, reply_markup=buttons)
                await callback_query.answer(f"✅ Resolution: {res}")
            
            elif data.startswith('encfps_'):
                # Format: encfps_VALUE_userid
                fps = data[len('encfps_'):-len(str(user_id))-1]
                LOGGER.info(f"Selected FPS: {fps}")
                selector.settings['fps'] = fps
                buttons = selector._build_main_menu()
                msg = selector._build_message()
                await callback_query.edit_message_text(msg, reply_markup=buttons)
                await callback_query.answer(f"✅ FPS: {fps}")
            
            elif data.startswith('encprof_'):
                # Format: encprof_PROFILE_ID_userid
                profile_id = data[len('encprof_'):-len(str(user_id))-1]
                LOGGER.info(f"Selected profile: {profile_id}")
                profile_settings = get_profile_settings(profile_id)
                selector.settings.update(profile_settings)
                buttons = selector._build_main_menu()
                msg = selector._build_message()
                await callback_query.edit_message_text(msg, reply_markup=buttons)
                await callback_query.answer(f"✅ Profile applied!")
            
            else:
                LOGGER.warning(f"Unknown callback format: {data}")
                await callback_query.answer("Unknown button", show_alert=True)
        
        except Exception as e:
            LOGGER.error(f"Encoding callback error: {e}", exc_info=True)
            await callback_query.answer(f"Error: {str(e)}", show_alert=True)
    
    # Register the handler using add_handler
    handler = CallbackQueryHandler(encoding_callback_handler, filters=regex("^enc"))
    client.add_handler(handler)
    LOGGER.info("Encoding selector handler registered successfully")
