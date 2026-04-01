#!/usr/bin/env python3
"""Video Processing Module - Handles all video encoding, compression, and transformations"""

import asyncio
from os import path as ospath
from asyncio import create_subprocess_exec
from aiofiles.os import remove as aioremove, path as aiopath
from aioshutil import move

from bot import LOGGER, download_dict, download_dict_lock
from bot.helper.ext_utils.bot_utils import sync_to_async, get_readable_file_size, get_path_size
from bot.helper.mirror_utils.status_utils.extract_status import ExtractStatus
from bot.helper.telegram_helper.message_utils import sendMessage, update_all_messages

# NEW: Video Merger Imports
from bot.helper.video_utils.merger import merge_videos, cancel_merge, is_merge_cancelled, active_merges


async def process_video(listener, video_mode_config, dl_path, up_path=None):
    """
    Process video based on selected mode (compress, convert, extract, etc.)
    
    Args:
        listener: MirrorLeechListener instance
        video_mode_config: tuple of (video_mode, rename_name, extra_data)
        dl_path: Download path
        up_path: Upload path (optional)
    
    Returns:
        Tuple of (proc_path, status) where status indicates processing success
    """
    if not video_mode_config:
        return up_path or dl_path, True
    
    proc_path = up_path or dl_path
    video_mode, rename_name, extra_data = video_mode_config[0], video_mode_config[1], video_mode_config[2]
    
    LOGGER.info(f"Starting video processing for task {listener.uid}: {video_mode}")
    
    try:
        # Check if the path is a file or directory
        if await aiopath.isfile(proc_path):
            # Single file video processing
            LOGGER.info(f"Video processing: {video_mode} for file: {proc_path}")
            
            # Update status to show video processing
            async with download_dict_lock:
                download_dict[listener.uid] = ExtractStatus(
                    ospath.basename(proc_path), 
                    await get_path_size(proc_path), 
                    listener.gid, 
                    listener
                )
            
            await update_all_messages()
            
            # Create output path for processed video
            base_name = ospath.basename(proc_path)
            name_without_ext = ospath.splitext(base_name)[0]
            ext = ospath.splitext(base_name)[1]
            output_path = f"{ospath.dirname(proc_path)}/{name_without_ext}_processed{ext}"
            
            # Build ffmpeg command based on video mode
            ffmpeg_cmd = None
            quality = extra_data.get('quality', '360p') if extra_data else '360p'
            
            if video_mode == 'compress':
                ffmpeg_cmd = await _build_compress_command(
                    proc_path, output_path, quality, extra_data
                )
            
            elif video_mode == 'convert':
                ffmpeg_cmd = await _build_convert_command(proc_path, output_path)
            
            elif video_mode == 'extract':
                ffmpeg_cmd = await _build_extract_command(
                    proc_path, name_without_ext, output_path
                )
                output_path = f"{ospath.dirname(proc_path)}/{name_without_ext}_audio.mp3"
            
            elif video_mode == 'trim':
                ffmpeg_cmd = await _build_trim_command(
                    proc_path, output_path, extra_data
                )
            
            elif video_mode == 'watermark':
                ffmpeg_cmd = await _build_watermark_command(
                    proc_path, output_path, extra_data
                )
            
            elif video_mode in ('vid_vid', 'vid_audio', 'vid_sub', 'zip_merge'):
                # NEW: Handle merge operations with multiple files
                LOGGER.info(f"Processing merge mode: {video_mode}")
                
                # Extract merge data from extra_data
                merge_data = {
                    'merge_type': video_mode,
                    'video_files': extra_data.get('video_files', []) if extra_data else [],
                    'output_filename': extra_data.get('output_filename') if extra_data else 'merged_video'
                }
                
                # Validate all merge files exist
                valid_files, invalid_files = await validate_merge_files(merge_data['video_files'])
                
                if invalid_files:
                    LOGGER.warning(f"Invalid merge files: {invalid_files}")
                    await sendMessage(
                        listener.message,
                        f"⚠️ <b>Merge Error:</b> {len(invalid_files)} file(s) not found"
                    )
                    return proc_path, False
                
                merge_data['video_files'] = valid_files
                
                # Execute merge with proper status tracking
                merged_file, merge_status = await handle_merge_operation(
                    listener, merge_data, None
                )
                
                if merge_status and merged_file:
                    return merged_file, True
                else:
                    return proc_path, False
            
            elif video_mode == 'rmstream':
                ffmpeg_cmd = await _build_rmstream_command(proc_path, output_path)
            
            elif video_mode in ('vid_sub', 'subsync'):
                ffmpeg_cmd = await _build_subsync_command(
                    proc_path, output_path, video_mode, extra_data
                )
            
            elif video_mode == 'rename':
                ffmpeg_cmd = None
            
            # Run ffmpeg if command was built
            if ffmpeg_cmd:
                LOGGER.info(f"Running ffmpeg: {' '.join(ffmpeg_cmd)}")
                await sendMessage(
                    listener.message, 
                    f"🎬 <b>Processing Video ({video_mode})</b>\n⏳ <i>Quality: {quality}</i>"
                )
                
                if listener.suproc == "cancelled":
                    return proc_path, False
                
                listener.suproc = await create_subprocess_exec(*ffmpeg_cmd)
                code = await listener.suproc.wait()
                
                if code == -9:
                    LOGGER.warning("Video processing cancelled")
                    return proc_path, False
                elif code == 0:
                    LOGGER.info(f"Video processing completed: {output_path}")
                    # Replace original with processed
                    try:
                        await aioremove(proc_path)
                        await sync_to_async(
                            __import__('shutil').move, 
                            output_path, 
                            proc_path
                        )
                    except Exception as e:
                        LOGGER.warning(f"Could not replace original: {e}")
                        proc_path = output_path
                    
                    await sendMessage(
                        listener.message, 
                        f"✅ <b>Video Processing Complete!</b>\n<b>Mode:</b> {video_mode}"
                    )
                else:
                    LOGGER.error(f"ffmpeg processing failed with code {code}")
                    await sendMessage(
                        listener.message, 
                        f"⚠️ <b>Processing warning:</b> ffmpeg returned error\n<i>Uploading original...</i>"
                    )
            else:
                LOGGER.info(f"No ffmpeg command for mode: {video_mode}")
                
        elif await aiopath.isdir(proc_path):
            LOGGER.info(f"Video processing: {video_mode} for directory: {proc_path}")
            await sendMessage(
                listener.message, 
                f"🎬 <b>Processing videos in directory...</b>\n<b>Mode:</b> {video_mode}"
            )
        
        # After video processing, recalculate file size
        if await aiopath.exists(proc_path):
            size = await get_path_size(proc_path)
            LOGGER.info(f"Updated file size after processing: {get_readable_file_size(size)}")
        
        return proc_path, True
        
    except Exception as e:
        LOGGER.error(f"Video processing error: {e}", exc_info=True)
        await sendMessage(
            listener.message, 
            f"⚠️ <b>Video processing warning:</b> {str(e)}\n<i>Continuing with upload...</i>"
        )
        return proc_path, False


async def _build_compress_command(proc_path, output_path, quality, extra_data):
    """Build ffmpeg command for video compression"""
    preset = extra_data.get('preset', 'fast') if extra_data else 'fast'
    crf = extra_data.get('crf', '23') if extra_data else '23'
    vcodec = extra_data.get('vcodec', 'libx264') if extra_data else 'libx264'
    acodec = extra_data.get('acodec', 'aac') if extra_data else 'aac'
    abitrate = extra_data.get('abitrate', '128k') if extra_data else '128k'
    profile = extra_data.get('profile') if extra_data else None
    level = extra_data.get('level') if extra_data else None
    tune = extra_data.get('tune') if extra_data else None
    pix_fmt = extra_data.get('pix_fmt', 'yuv420p') if extra_data else 'yuv420p'
    movflags = extra_data.get('movflags', '+faststart') if extra_data else '+faststart'
    
    # Resolution mapping
    quality_map = {
        '1080p': '1920x1080',
        '720p': '1280x720',
        '540p': '960x540',
        '480p': '854x480',
        '360p': '640x360',
        'original': '-1:-1'
    }
    scale_res = quality_map.get(quality, '640x360')
    
    ffmpeg_cmd = [
        'ffmpeg',
        '-i', proc_path,
    ]
    
    # Video filter (scale)
    if scale_res != '-1:-1':
        # Use -2 for height to keep aspect ratio and ensure divisibility
        ffmpeg_cmd.extend(['-vf', f'scale={scale_res}'])
    
    # Video codec settings
    ffmpeg_cmd.extend(['-c:v', vcodec])
    
    # Profile and level for libx264 only
    if vcodec == 'libx264':
        if profile:
            ffmpeg_cmd.extend(['-profile:v', profile])
        if level:
            ffmpeg_cmd.extend(['-level', level])
    
    # Tune (only for libx264, not libx265)
    if vcodec == 'libx264' and tune:
        ffmpeg_cmd.extend(['-tune', tune])
    
    # Pixel format
    ffmpeg_cmd.extend(['-pix_fmt', pix_fmt])
    
    # CRF/quality settings
    if vcodec in ['libx264', 'libx265']:
        ffmpeg_cmd.extend(['-crf', str(crf)])
        ffmpeg_cmd.extend(['-preset', preset])
    elif vcodec == 'libvpx-vp9':
        ffmpeg_cmd.extend(['-crf', str(crf), '-b:v', '0'])
    
    # mov flags for MP4 optimization
    ffmpeg_cmd.extend(['-movflags', movflags])
    
    # Audio codec
    ffmpeg_cmd.extend(['-c:a', acodec])
    ffmpeg_cmd.extend(['-b:a', abitrate])
    
    # Copy subtitles
    ffmpeg_cmd.extend(['-c:s', 'copy'])
    
    ffmpeg_cmd.extend(['-y', output_path])
    
    return ffmpeg_cmd


async def _build_convert_command(proc_path, output_path):
    """Build ffmpeg command for video format conversion"""
    return [
        'ffmpeg',
        '-i', proc_path,
        '-c:v', 'libx264',
        '-preset', 'fast',
        '-c:a', 'aac',
        '-y',
        output_path
    ]


async def _build_extract_command(proc_path, name_without_ext, output_path):
    """Build ffmpeg command for audio extraction"""
    return [
        'ffmpeg',
        '-i', proc_path,
        '-q:a', '0',
        '-map', 'a',
        '-y',
        output_path
    ]


async def _build_trim_command(proc_path, output_path, extra_data):
    """Build ffmpeg command for video trimming"""
    start_time = extra_data.get('start_time', '00:00:00') if extra_data else '00:00:00'
    end_time = extra_data.get('end_time') if extra_data else None
    
    if end_time:
        return [
            'ffmpeg',
            '-i', proc_path,
            '-ss', start_time,
            '-to', end_time,
            '-c', 'copy',
            '-y',
            output_path
        ]
    return None


async def _build_watermark_command(proc_path, output_path, extra_data):
    """Build ffmpeg command for watermark overlay"""
    watermark_path = extra_data.get('subfile') if extra_data else None
    if watermark_path and await aiopath.exists(watermark_path):
        return [
            'ffmpeg',
            '-i', proc_path,
            '-i', watermark_path,
            '-filter_complex', '[0:v][1:v] overlay=10:10',
            '-c:a', 'copy',
            '-y',
            output_path
        ]
    return None


async def _build_rmstream_command(proc_path, output_path):
    """Build ffmpeg command for removing audio stream"""
    return [
        'ffmpeg',
        '-i', proc_path,
        '-c:v', 'copy',
        '-an',  # Remove audio
        '-y',
        output_path
    ]


async def _build_subsync_command(proc_path, output_path, video_mode, extra_data):
    """Build ffmpeg command for subtitle handling"""
    sub_file = extra_data.get('subfile') if extra_data else None
    if video_mode == 'subsync' and sub_file and await aiopath.exists(sub_file):
        # Hardsub - embed subtitles
        return [
            'ffmpeg',
            '-i', proc_path,
            '-vf', f"subtitles={sub_file}",
            '-c:a', 'copy',
            '-y',
            output_path
        ]
    return None


# ====== NEW: VIDEO MERGER INTEGRATION ====== #

async def handle_merge_operation(listener, merge_data, status_message):
    """
    Handle video merge operations
    
    Args:
        listener: MirrorLeechListener instance
        merge_data: Dict with merge operation details
        status_message: Telegram message object for progress updates
    
    Returns:
        Tuple of (merged_file_path, status) - path to merged video or original path
    """
    try:
        merge_type = merge_data.get('merge_type')
        video_files = merge_data.get('video_files', [])
        output_filename = merge_data.get('output_filename', 'merged_video')
        
        if not video_files or len(video_files) < 2:
            LOGGER.warning(f"Merge requires at least 2 files, got {len(video_files)}")
            await sendMessage(
                listener.message,
                "⚠️ <b>Merge Error:</b> Requires at least 2 files"
            )
            return video_files[0] if video_files else None, False
        
        # Check if merge cancelled by user
        if is_merge_cancelled(listener.uid):
            await sendMessage(listener.message, "🚫 Merge cancelled")
            return video_files[0], False
        
        # Call merge_videos with progress tracking
        LOGGER.info(f"Starting merge for user {listener.uid}: {merge_type} with {len(video_files)} files")
        await sendMessage(
            listener.message,
            f"🎬 <b>Merging {len(video_files)} videos...</b>\n"
            f"<i>Type: {merge_type}</i>\n"
            f"⏳ Please wait..."
        )
        
        merged_path = await merge_videos(
            video_files,
            listener.uid,
            status_message,
            output_filename
        )
        
        if merged_path and await aiopath.exists(merged_path):
            size = await get_path_size(merged_path)
            LOGGER.info(f"✅ Merge completed: {merged_path} ({get_readable_file_size(size)})")
            await sendMessage(
                listener.message,
                f"✅ <b>Merge Complete!</b>\n"
                f"<b>Output:</b> {ospath.basename(merged_path)}\n"
                f"<b>Size:</b> {get_readable_file_size(size)}"
            )
            return merged_path, True
        else:
            LOGGER.error(f"Merge failed for user {listener.uid}")
            await sendMessage(
                listener.message,
                "❌ <b>Merge failed:</b> FFmpeg error\n"
                "<i>Uploading original...</i>"
            )
            return video_files[0] if video_files else None, False
    
    except Exception as e:
        LOGGER.error(f"Merge operation error for user {listener.uid}: {e}", exc_info=True)
        await sendMessage(
            listener.message,
            f"⚠️ <b>Merge error:</b> {str(e)}\n<i>Uploading original...</i>"
        )
        return None, False


async def validate_merge_files(video_files):
    """
    Validate that all files exist and are readable
    
    Args:
        video_files: List of file paths to validate
    
    Returns:
        Tuple of (valid_files, invalid_files)
    """
    valid_files = []
    invalid_files = []
    
    for file_path in video_files:
        if await aiopath.isfile(file_path):
            valid_files.append(file_path)
        else:
            invalid_files.append(file_path)
            LOGGER.warning(f"Video file not found: {file_path}")
    
    return valid_files, invalid_files


async def get_merge_output_path(input_files, output_dir):
    """
    Generate output path for merged video
    
    Args:
        input_files: List of input video files
        output_dir: Directory where merged video should be saved
    
    Returns:
        Path for merged video (MKV format)
    """
    base_name = ospath.basename(input_files[0]) if input_files else "merged"
    name_without_ext = ospath.splitext(base_name)[0]
    return f"{output_dir}/{name_without_ext}_merged.mkv"


def get_merge_status(user_id):
    """
    Get current merge status for a user
    
    Returns:
        Merge progress info or None if not merging
    """
    return active_merges.get(user_id)
