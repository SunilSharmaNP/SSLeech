"""
Video Mode Selector - Interactive UI for selecting video processing modes
"""

from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from logging import getLogger

LOGGER = getLogger(__name__)


class SelectMode:
    """Interactive mode selection UI for video tools"""
    
    MODES = {
        'vid_vid': '🎬 Merge Videos',
        'vid_aud': '🎵 Merge Video + Audio',
        'vid_sub': '📝 Merge Video + Subtitle',
        'subsync': '🔄 Synchronize Subtitles',
        'compress': '📦 Compress Video',
        'convert': '📐 Convert Resolution',
        'watermark': '🎨 Add Watermark',
        'extract': '📂 Extract Streams',
        'trim': '✂️ Trim Video',
        'rmstream': '🗑️ Remove Stream',
    }
    
    RESOLUTIONS = {
        '1080p': '1920x1080 - Full HD',
        '720p': '1280x720 - HD',
        '540p': '960x540 - Standard',
        '480p': '854x480 - Mobile',
        '360p': '640x360 - Low',
    }
    
    POSITIONS = {
        'tl': '↖️ Top-Left',
        'tr': '↗️ Top-Right',
        'bl': '↙️ Bottom-Left',
        'br': '↘️ Bottom-Right',
    }
    
    COMPRESS_PRESETS = {
        'faster': '⚡ Faster (Low compression)',
        'fast': '🔥 Fast (Medium compression)',
        'medium': '⚖️ Medium (Balanced)',
        'slow': '🐢 Slow (High compression)',
    }
    
    STREAM_TYPES = {
        'video': '🎬 Video Stream',
        'audio': '🔊 Audio Stream',
        'subtitle': '📝 Subtitle Stream',
        'all': '📦 All Streams',
    }
    
    @staticmethod
    def get_mode_buttons(disabled_modes=None):
        """Get inline buttons for mode selection"""
        disabled_modes = disabled_modes or []
        buttons = InlineKeyboardMarkup([])
        
        mode_list = list(SelectMode.MODES.items())
        
        # Arrange in 2 columns
        for i in range(0, len(mode_list), 2):
            row = []
            mode1_key, mode1_name = mode_list[i]
            
            # Check if mode is disabled
            if mode1_key not in disabled_modes:
                row.append(
                    InlineKeyboardButton(
                        mode1_name,
                        callback_data=f'vidmode_{mode1_key}'
                    )
                )
            
            if i + 1 < len(mode_list):
                mode2_key, mode2_name = mode_list[i + 1]
                if mode2_key not in disabled_modes:
                    row.append(
                        InlineKeyboardButton(
                            mode2_name,
                            callback_data=f'vidmode_{mode2_key}'
                        )
                    )
            
            if row:
                buttons.inline_keyboard.append(row)
        
        # Add cancel button
        buttons.inline_keyboard.append([
            InlineKeyboardButton('❌ Cancel', callback_data='vidmode_cancel')
        ])
        
        return buttons
    
    @staticmethod
    def get_resolution_buttons():
        """Get buttons for resolution selection"""
        buttons = InlineKeyboardMarkup([])
        
        res_list = list(SelectMode.RESOLUTIONS.items())
        
        for i in range(0, len(res_list), 2):
            row = []
            res1_key, res1_name = res_list[i]
            row.append(
                InlineKeyboardButton(
                    res1_name,
                    callback_data=f'vidres_{res1_key}'
                )
            )
            
            if i + 1 < len(res_list):
                res2_key, res2_name = res_list[i + 1]
                row.append(
                    InlineKeyboardButton(
                        res2_name,
                        callback_data=f'vidres_{res2_key}'
                    )
                )
            
            buttons.inline_keyboard.append(row)
        
        buttons.inline_keyboard.append([
            InlineKeyboardButton('⬅️ Back', callback_data='vidmode_back')
        ])
        
        return buttons
    
    @staticmethod
    def get_position_buttons():
        """Get buttons for watermark position selection"""
        buttons = InlineKeyboardMarkup([])
        
        pos_list = list(SelectMode.POSITIONS.items())
        
        # 2x2 grid
        for i in range(0, len(pos_list), 2):
            row = []
            key1, name1 = pos_list[i]
            row.append(
                InlineKeyboardButton(
                    name1,
                    callback_data=f'vidpos_{key1}'
                )
            )
            
            if i + 1 < len(pos_list):
                key2, name2 = pos_list[i + 1]
                row.append(
                    InlineKeyboardButton(
                        name2,
                        callback_data=f'vidpos_{key2}'
                    )
                )
            
            buttons.inline_keyboard.append(row)
        
        buttons.inline_keyboard.append([
            InlineKeyboardButton('⬅️ Back', callback_data='vidmode_back')
        ])
        
        return buttons
    
    @staticmethod
    def get_compress_preset_buttons():
        """Get buttons for compression preset selection"""
        buttons = InlineKeyboardMarkup([])
        
        preset_list = list(SelectMode.COMPRESS_PRESETS.items())
        
        for key, name in preset_list:
            buttons.inline_keyboard.append([
                InlineKeyboardButton(
                    name,
                    callback_data=f'vidpreset_{key}'
                )
            ])
        
        buttons.inline_keyboard.append([
            InlineKeyboardButton('⬅️ Back', callback_data='vidmode_back')
        ])
        
        return buttons
    
    @staticmethod
    def get_stream_type_buttons():
        """Get buttons for stream type selection"""
        buttons = InlineKeyboardMarkup([])
        
        for key, name in SelectMode.STREAM_TYPES.items():
            buttons.inline_keyboard.append([
                InlineKeyboardButton(
                    name,
                    callback_data=f'vidstream_{key}'
                )
            ])
        
        buttons.inline_keyboard.append([
            InlineKeyboardButton('⬅️ Back', callback_data='vidmode_back')
        ])
        
        return buttons
    
    @staticmethod
    def get_menu_caption(config=None):
        """Get caption for video tools menu"""
        config = config or {}
        
        caption = "🎬 <b>Video Tools Menu</b>\n\n"
        caption += "<b>Available Operations:</b>\n"
        
        for key, name in SelectMode.MODES.items():
            caption += f"• {name}\n"
        
        if config:
            caption += "\n<b>Current Settings:</b>\n"
            if config.get('mode'):
                caption += f"• Mode: {SelectMode.MODES.get(config['mode'], config['mode'])}\n"
            if config.get('resolution'):
                caption += f"• Resolution: {config['resolution']}\n"
            if config.get('preset'):
                caption += f"• Preset: {config['preset']}\n"
        
        caption += "\n<i>Select an operation below:</i>"
        
        return caption
    
    @staticmethod
    def get_confirmation_caption(mode, config=None):
        """Get confirmation message for selected mode"""
        config = config or {}
        
        caption = f"✅ <b>Selected: {SelectMode.MODES.get(mode, mode)}</b>\n\n"
        
        if mode == 'convert':
            caption += "📐 <b>Resolution Selection</b>\n"
            caption += "Choose target resolution:\n"
        elif mode == 'compress':
            caption += "📦 <b>Compression Settings</b>\n"
            caption += "Choose compression preset:\n"
            caption += "• <b>Faster:</b> Quicker encoding, larger file\n"
            caption += "• <b>Fast:</b> Balanced speed and compression\n"
            caption += "• <b>Medium:</b> Standard compression\n"
            caption += "• <b>Slow:</b> Maximum compression, slower\n"
        elif mode == 'watermark':
            caption += "🎨 <b>Watermark Position</b>\n"
            caption += "Choose watermark placement:\n"
        elif mode == 'extract':
            caption += "📂 <b>Stream Extraction</b>\n"
            caption += "Choose which streams to extract:\n"
        elif mode == 'trim':
            caption += "✂️ <b>Video Trimming</b>\n"
            caption += "<i>Send start and end time in format:</i> <code>HH:MM:SS HH:MM:SS</code>\n"
            caption += "<i>Example:</i> <code>00:00:10 00:02:30</code>\n"
        else:
            caption += f"Processing video with {SelectMode.MODES.get(mode, mode)} mode...\n"
        
        return caption
    
    @staticmethod
    def get_help_text():
        """Get comprehensive help text"""
        help_text = """
<b>🎬 Video Tools Help</b>

<b>Available Commands:</b>

1. <b>Merge Videos</b> - Combine multiple video files
2. <b>Merge Video + Audio</b> - Add audio tracks to video
3. <b>Merge Video + Subtitle</b> - Add subtitle files (softcopy or hardsub)
4. <b>Compress Video</b> - Reduce video size using HEVC codec
5. <b>Convert Resolution</b> - Scale to 1080p, 720p, 540p, 480p, 360p
6. <b>Add Watermark</b> - Place watermark image on video
7. <b>Extract Streams</b> - Export video, audio, or subtitle streams
8. <b>Trim Video</b> - Cut video to specific duration
9. <b>Sync Subtitles</b> - Auto-synchronize subtitle timing
10. <b>Remove Stream</b> - Delete audio/video/subtitle tracks

<b>Usage:</b>
/vtl <link/file> -vt <mode> <options>
/vtm <link/file> -vt <mode> <options>

<b>Supported Flags:</b>
• <code>-n</code> - Rename output
• <code>-z</code> - Compress with password
• <code>-t</code> - Custom thumbnail
• <code>-sp</code> - Split size (500mb, 2gb)
• <code>-up</code> - Upload destination
• <code>-b</code> - Bulk download
• <code>-sv</code> - Create sample video
• <code>-ss</code> - Generate screenshots

<b>Note:</b>
• Merge operations require multiple files/links
• Compression is slow but reduces file size significantly
• All timestamps in HH:MM:SS or MM:SS format
"""
        return help_text.strip()
