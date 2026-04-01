"""
Professional Merge Type Selector
- Merge Type Selection UI
- User-friendly merge workflow
- Integration with video merger
"""

from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import logging

logger = logging.getLogger(__name__)


def get_merge_type_keyboard() -> InlineKeyboardMarkup:
    """
    Get merge type selection keyboard
    Returns professional UI for selecting merge operation type
    """
    buttons = [
        [InlineKeyboardButton("🎬 Video + Video", callback_data="merge_type_video_video")],
        [InlineKeyboardButton("🎵 Video + Audio", callback_data="merge_type_video_audio")],
        [InlineKeyboardButton("📝 Video + Subtitle", callback_data="merge_type_video_subtitle")],
        [InlineKeyboardButton("📦 ZIP Merge", callback_data="merge_type_zip")],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel_merge_setup")]
    ]
    return InlineKeyboardMarkup(buttons)


def get_merge_video_video_ui() -> str:
    """Video + Video merge UI text"""
    return (
        "🎬 **Video + Video Merge**\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "**How it works:**\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "1️⃣ Send **minimum 2 videos** (Telegram or direct links)\n"
        "   • Videos can be different sizes/formats\n"
        "   • Same resolution = faster merge (no re-encode)\n"
        "   • Different resolution = auto re-encode & standardize\n\n"
        "2️⃣ After sending videos, click **Merge Now**\n\n"
        "3️⃣ Bot **combines videos** into one file\n\n"
        "4️⃣ Bot **uploads result** (Telegram or GoFile)\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "**Supported Formats:**\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "📹 MP4, MKV, AVI, MOV, FLV, WMV, WebM, M3U8\n\n"
        "⏳ **Ready to receive videos...**"
    )


def get_merge_video_audio_ui() -> str:
    """Video + Audio merge UI text"""
    return (
        "🎵 **Video + Audio Merge**\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "**How it works:**\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "1️⃣ Send **1 VIDEO** file\n"
        "   • Telegram file or direct link\n\n"
        "2️⃣ Send **1 AUDIO** file\n"
        "   • Telegram file or direct link\n"
        "   • Formats: MP3, AAC, WAV, FLAC, M4A, OGG\n\n"
        "3️⃣ Click **Merge Now**\n\n"
        "4️⃣ Bot **combines video with audio**\n"
        "   • Audio synced to video length (uses shortest)\n"
        "   • Re-encoded for best compatibility\n\n"
        "5️⃣ Bot **uploads result**\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "**Queue limits:**\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "• **Maximum 1 video** + **1 audio** = 2 files total\n\n"
        "⏳ **Ready to receive video + audio...**"
    )


def get_merge_video_subtitle_ui() -> str:
    """Video + Subtitle merge UI text"""
    return (
        "📝 **Video + Subtitle Merge**\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "**How it works:**\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "1️⃣ Send **1 VIDEO** file\n"
        "   • Telegram file or direct link\n\n"
        "2️⃣ Send **1 SUBTITLE** file\n"
        "   • Formats: SRT, VTT, SUB, ASS\n"
        "   • Telegram file or direct link\n\n"
        "3️⃣ Click **Merge Now**\n\n"
        "4️⃣ Bot **embeds subtitle as track**\n"
        "   • Subtitle saved as separate stream (not burned)\n"
        "   • Video and audio copied (no re-encoding)\n"
        "   • MediaInfo will show subtitle track ✅\n\n"
        "5️⃣ Bot **uploads result** (MKV format)\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "**Queue limits:**\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "• **Maximum 1 video** + **1 subtitle** = 2 files total\n\n"
        "⏳ **Ready to receive video + subtitle...**"
    )


def get_merge_zip_ui() -> str:
    """ZIP Merge UI text"""
    return (
        "📦 **ZIP Episode Merge**\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "**How it works:**\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "1️⃣ Send **ZIP file** containing video episodes\n"
        "   • Upload from Telegram\n"
        "   • Or send a direct download link\n\n"
        "2️⃣ Bot **extracts** and **lists** all episodes\n"
        "   • Shows file names and sizes\n"
        "   • Click 'Merge All' or send custom selection\n\n"
        "3️⃣ **Select episodes** to merge\n"
        "   Examples:\n"
        "   • `1` — Only episode 1\n"
        "   • `1,2,3` — Episodes 1, 2, 3\n"
        "   • `1-5` — Episodes 1 to 5\n"
        "   • `1,3-5,7` — Mix of singles and ranges\n\n"
        "4️⃣ Bot **merges** selected episodes\n"
        "   • Combines into one video\n"
        "   • Only same-resolution files merged\n"
        "   • Others skipped (no re-encoding)\n\n"
        "5️⃣ Bot **uploads** final video\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "**Supported Formats:**\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "📹 MP4, MKV, AVI, MOV, FLV, WMV, WebM\n\n"
        "⏳ **Ready to receive ZIP file...**"
    )


def get_merge_queue_ui(current_count: int, merge_type: str) -> str:
    """Get queue status UI"""
    queue_displays = {
        'video_video': f"🎬 **Queue Status**\n\n📊 Videos: `{current_count}`\n\n⏳ Send more videos or click Merge buttons below",
        'video_audio': (
            f"🎵 **Queue Status**\n\n"
            f"📊 Queue: `{current_count}/2`\n\n"
            f"{'✅ Video added' if current_count >= 1 else '❌ Waiting for video'}\n"
            f"{'✅ Audio added' if current_count >= 2 else '❌ Waiting for audio'}\n\n"
            f"{'🚀 Ready to merge!' if current_count == 2 else '⏳ Send next file'}"
        ),
        'video_subtitle': (
            f"📝 **Queue Status**\n\n"
            f"📊 Queue: `{current_count}/2`\n\n"
            f"{'✅ Video added' if current_count >= 1 else '❌ Waiting for video'}\n"
            f"{'✅ Subtitle added' if current_count >= 2 else '❌ Waiting for subtitle'}\n\n"
            f"{'🚀 Ready to embed!' if current_count == 2 else '⏳ Send next file'}"
        ),
    }
    return queue_displays.get(merge_type, f"📊 Queue: {current_count} file(s)")


def get_merge_ready_keyboard() -> InlineKeyboardMarkup:
    """Get keyboard for merge ready state"""
    buttons = [
        [InlineKeyboardButton("🚀 Merge Now", callback_data="start_merge")],
        [InlineKeyboardButton("❌ Clear Queue", callback_data="clear_queue")],
    ]
    return InlineKeyboardMarkup(buttons)


def get_merge_setup_keyboard() -> InlineKeyboardMarkup:
    """Get keyboard during merge setup"""
    buttons = [
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel_merge_setup")],
    ]
    return InlineKeyboardMarkup(buttons)
