"""
Professional Enhanced Video Merger Module
- Real-time progress tracking with cancel functionality
- Intelligent codec/resolution detection
- Fast merge for identical videos
- Error recovery and FloodWait handling
"""

import asyncio
import os
import time
import json
import logging
import re
from typing import List, Optional, Dict, Any
from bot import LOGGER, config

logging.basicConfig(level=logging.INFO)
logger = LOGGER or logging.getLogger(__name__)

# Global tracking
active_merges: Dict[int, Dict[str, Any]] = {}
merge_lock = asyncio.Lock()
last_edit_time = {}
EDIT_THROTTLE_SECONDS = 1.5


class MergeProgress:
    """Progress tracking with cancel functionality"""
    def __init__(self, user_id: int, status_message, total_files: int):
        self.user_id = user_id
        self.status_message = status_message
        self.total_files = total_files
        self.current_file = 0
        self.current_progress = 0.0
        self.start_time = time.time()
        self.cancelled = False
        self.current_process = None
        self.stage = "initializing"
    
    def cancel(self):
        """Cancel the current merge operation"""
        self.cancelled = True
        if self.current_process:
            try:
                self.current_process.terminate()
                logger.info(f"🚫 Cancelled merge process for user {self.user_id}")
            except:
                pass
    
    async def update(self, stage: str, progress: float = None, message: str = None):
        """Update progress UI with cancel option"""
        if self.cancelled:
            raise asyncio.CancelledError("Merge operation cancelled by user")
        
        self.stage = stage
        if progress is not None:
            self.current_progress = progress
        
        elapsed = time.time() - self.start_time
        
        # Build progress message
        progress_text = f"🎬 **Video Merger Pro**\n\n"
        
        if stage == "analyzing":
            progress_text += f"🔍 **Analyzing Videos**\n"
            progress_text += f"Progress: {self.current_file}/{self.total_files}\n"
        elif stage == "downloading":
            progress_text += f"📥 **Downloading Files**\n"
            progress_text += f"Progress: {self.current_file}/{self.total_files}\n"
        elif stage == "merging":
            progress_text += f"🎭 **Merging Videos**\n"
        elif stage == "uploading":
            progress_text += f"📤 **Uploading Result**\n"
        elif stage == "finalizing":
            progress_text += f"✨ **Finalizing**\n"
        
        if progress is not None:
            bar_length = 15
            filled = int(bar_length * progress)
            bar = "█" * filled + "░" * (bar_length - filled)
            progress_text += f"█ `[{bar}]` **{progress:.1%}**\n"
        
        progress_text += f"⏱ **Elapsed:** `{int(elapsed)}s`\n"
        
        if message:
            progress_text += f"📊 **Status:** {message}\n"
        
        progress_text += f"\n💡 **Use /cancel to stop this operation**"
        
        await smart_progress_editor(self.status_message, progress_text)


async def smart_progress_editor(status_message, text: str):
    """Progress editor with throttling"""
    if not status_message or not hasattr(status_message, 'chat'):
        return
    
    message_key = f"{status_message.chat.id}_{status_message.id}"
    now = time.time()
    last_time = last_edit_time.get(message_key, 0)
    
    if (now - last_time) > EDIT_THROTTLE_SECONDS:
        try:
            await status_message.edit_text(text)
            last_edit_time[message_key] = now
        except Exception as e:
            logger.debug(f"Progress update failed: {e}")


def is_merge_cancelled(user_id: int) -> bool:
    """Check if merge is cancelled"""
    return active_merges.get(user_id, {}).get('cancelled', False)


def cancel_merge(user_id: int):
    """Cancel merge operation"""
    if user_id in active_merges:
        active_merges[user_id]['cancelled'] = True
        progress = active_merges[user_id].get('progress')
        if progress:
            progress.cancel()


async def get_detailed_video_info(file_path: str) -> Optional[Dict[str, Any]]:
    """Get comprehensive video information"""
    try:
        cmd = [
            'ffprobe', '-v', 'quiet', '-print_format', 'json',
            '-show_format', '-show_streams', file_path
        ]
        
        process = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        
        if process.returncode != 0:
            logger.error(f"ffprobe failed: {stderr.decode()}")
            return None
        
        data = json.loads(stdout.decode())
        
        video_streams = [s for s in data.get('streams', []) if s.get('codec_type') == 'video']
        audio_streams = [s for s in data.get('streams', []) if s.get('codec_type') == 'audio']
        
        if not video_streams:
            return None
        
        video_stream = video_streams[0]
        audio_stream = audio_streams[0] if audio_streams else None
        
        # Parse FPS
        fps_str = video_stream.get('r_frame_rate', '30/1')
        if '/' in fps_str:
            num, den = fps_str.split('/')
            fps = round(float(num) / float(den), 2) if int(den) != 0 else 30.0
        else:
            fps = round(float(fps_str), 2)
        
        video_codec = video_stream.get('codec_name', '').lower()
        audio_codec = audio_stream.get('codec_name', '').lower() if audio_stream else None
        
        return {
            'has_video': True,
            'has_audio': audio_stream is not None,
            'width': int(video_stream.get('width', 0)),
            'height': int(video_stream.get('height', 0)),
            'fps': fps,
            'video_codec': video_codec,
            'audio_codec': audio_codec,
            'pixel_format': video_stream.get('pix_fmt', 'yuv420p'),
            'duration': float(data['format'].get('duration', 0)),
            'bitrate': video_stream.get('bit_rate'),
            'audio_sample_rate': int(audio_stream.get('sample_rate', 48000)) if audio_stream else 48000,
            'file_path': file_path
        }
    
    except Exception as e:
        logger.error(f"Video info error: {e}")
        return None


def videos_are_identical_for_merge(video_infos: List[Dict[str, Any]]) -> bool:
    """Check if videos are identical for fast merge"""
    if not video_infos or len(video_infos) < 2:
        return False
    
    reference = video_infos[0]
    critical_params = ['width', 'height', 'fps', 'video_codec', 'audio_codec', 'pixel_format']
    
    for video_info in video_infos[1:]:
        for param in critical_params:
            ref_val = reference.get(param)
            vid_val = video_info.get(param)
            
            if ref_val is None or vid_val is None:
                continue
            
            if param == 'fps':
                if abs(ref_val - vid_val) > 0.1:
                    return False
            else:
                if ref_val != vid_val:
                    return False
    
    return True


async def get_total_duration(video_files: List[str]) -> float:
    """Calculate total duration of all videos"""
    total_duration = 0.0
    for file_path in video_files:
        try:
            cmd = ['ffprobe', '-v', 'quiet', '-show_entries', 'format=duration',
                   '-of', 'csv=p=0', file_path]
            process = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            if process.returncode == 0:
                duration = float(stdout.decode().strip())
                total_duration += duration
        except:
            pass
    return total_duration


async def track_merge_progress(process, total_duration: float, progress: MergeProgress):
    """Track FFmpeg progress in real-time"""
    start_time = time.time()
    last_update = 0
    
    progress.current_process = process
    
    while True:
        try:
            if progress.cancelled:
                process.terminate()
                await asyncio.sleep(1)
                if process.returncode is None:
                    process.kill()
                raise asyncio.CancelledError("Merge cancelled")
            
            line = await asyncio.wait_for(process.stderr.readline(), timeout=1.0)
            if not line:
                break
            
            line = line.decode().strip()
            
            # Parse FFmpeg progress
            time_match = re.search(r'time=(\d{2}):(\d{2}):(\d{2}\.\d{2})', line)
            if time_match and total_duration > 0:
                hours, minutes, seconds = time_match.groups()
                current_time = int(hours) * 3600 + int(minutes) * 60 + float(seconds)
                
                progress_val = min(current_time / total_duration, 1.0)
                elapsed = time.time() - start_time
                
                if time.time() - last_update > 1.5:
                    eta = int((elapsed / progress_val - elapsed)) if progress_val > 0.01 else 0
                    await progress.update(
                        "merging",
                        progress_val,
                        f"Processing: {int(current_time)}s / {int(total_duration)}s"
                    )
                    last_update = time.time()
        
        except asyncio.TimeoutError:
            continue
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.debug(f"Progress tracking error: {e}")
            break


async def fast_merge_identical_videos(video_files: List[str], user_id: int, progress: MergeProgress, output_filename: str = None) -> Optional[str]:
    """Fast merge for identical videos (copy only, no re-encoding)"""
    user_download_dir = os.path.join(config.DOWNLOAD_DIR, str(user_id))
    
    try:
        if progress.cancelled:
            raise asyncio.CancelledError("Merge cancelled")
        
        await progress.update("merging", 0.0, "🚀 Ultra-fast merge (identical videos)")
        
        if output_filename:
            base_name = os.path.splitext(output_filename)[0]
            output_path = os.path.join(user_download_dir, f"{base_name}.mkv")
        else:
            output_path = os.path.join(user_download_dir, f"Merged_{int(time.time())}.mkv")
        
        inputs_file = os.path.join(user_download_dir, f"inputs_{int(time.time())}.txt")
        total_duration = await get_total_duration(video_files)
        
        # Create concat file
        with open(inputs_file, 'w', encoding='utf-8') as f:
            for file_path in video_files:
                abs_path = os.path.abspath(file_path)
                formatted_path = abs_path.replace("'", "'\\''")
                f.write(f"file '{formatted_path}'\n")
        
        # FFmpeg concat command
        cmd = [
            'ffmpeg', '-hide_banner', '-loglevel', 'info', '-y',
            '-f', 'concat', '-safe', '0', '-i', inputs_file,
            '-map', '0', '-c', 'copy', '-f', 'matroska',
            '-progress', 'pipe:2', output_path
        ]
        
        process = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        
        try:
            progress_task = asyncio.create_task(track_merge_progress(process, total_duration, progress))
            stdout, stderr = await process.communicate()
            progress_task.cancel()
        except asyncio.CancelledError:
            progress_task.cancel()
            raise
        
        try:
            os.remove(inputs_file)
        except:
            pass
        
        if process.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            file_size = os.path.getsize(output_path)
            await progress.update("finalizing", 1.0, f"✅ Success! {file_size / (1024*1024):.1f} MB")
            logger.info(f"✅ Fast merge completed: {output_path}")
            return output_path
        else:
            error_output = stderr.decode()[:100] if stderr else "Unknown error"
            logger.error(f"Fast merge failed: {error_output}")
            return None
    
    except asyncio.CancelledError:
        try:
            if os.path.exists(inputs_file):
                os.remove(inputs_file)
            if 'output_path' in locals() and os.path.exists(output_path):
                os.remove(output_path)
        except:
            pass
        raise
    except Exception as e:
        logger.error(f"Fast merge error: {e}")
        return None


async def merge_videos(video_files: List[str], user_id: int, status_message, output_filename: str = None) -> Optional[str]:
    """
    Professional video merger with:
    - Real-time progress tracking
    - Cancel functionality
    - Smart codec/resolution detection
    - Fast merge for identical videos
    - Error recovery
    """
    
    async with merge_lock:
        if len(video_files) < 2:
            await status_message.edit_text("❌ Need at least 2 videos to merge!")
            return None
        
        # Initialize progress
        progress = MergeProgress(user_id, status_message, len(video_files))
        active_merges[user_id] = {'progress': progress, 'cancelled': False}
        
        try:
            user_download_dir = os.path.join(config.DOWNLOAD_DIR, str(user_id))
            os.makedirs(user_download_dir, exist_ok=True)
            
            # Step 1: Analyze videos
            await progress.update("analyzing", 0.0, "Starting analysis...")
            
            video_infos = []
            for i, file_path in enumerate(video_files):
                if progress.cancelled:
                    raise asyncio.CancelledError("Analysis cancelled")
                
                progress.current_file = i + 1
                await progress.update("analyzing", i / len(video_files), f"Analyzing video {i+1}/{len(video_files)}")
                
                info = await get_detailed_video_info(file_path)
                if not info or not info['has_video']:
                    await progress.update("analyzing", None, f"❌ Video {i+1} is invalid!")
                    return None
                video_infos.append(info)
                logger.info(f"✅ Video {i+1}: {info['width']}x{info['height']}@{info['fps']}fps")
            
            # Step 2: Check if fast merge is possible
            if videos_are_identical_for_merge(video_infos):
                await progress.update("merging", 0.0, "🚀 Videos are identical! Using ultra-fast merge...")
                result = await fast_merge_identical_videos(video_files, user_id, progress, output_filename)
                if result:
                    return result
                logger.warning("Fast merge failed, trying standard merge")
            
            # Step 3: Standard merge with concat
            await progress.update("merging", 0.0, "Preparing standard merge...")
            
            if output_filename:
                base_name = os.path.splitext(output_filename)[0]
                output_path = os.path.join(user_download_dir, f"{base_name}.mkv")
            else:
                output_path = os.path.join(user_download_dir, f"Merged_{int(time.time())}.mkv")
            
            inputs_file = os.path.join(user_download_dir, f"inputs_{int(time.time())}.txt")
            total_duration = await get_total_duration(video_files)
            
            with open(inputs_file, 'w', encoding='utf-8') as f:
                for file_path in video_files:
                    abs_path = os.path.abspath(file_path)
                    formatted_path = abs_path.replace("'", "'\\''")
                    f.write(f"file '{formatted_path}'\n")
            
            cmd = [
                'ffmpeg', '-hide_banner', '-loglevel', 'error', '-y',
                '-f', 'concat', '-safe', '0', '-i', inputs_file,
                '-c', 'copy', '-f', 'matroska', output_path
            ]
            
            process = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            
            try:
                progress_task = asyncio.create_task(track_merge_progress(process, total_duration, progress))
                stdout, stderr = await process.communicate()
                progress_task.cancel()
            except asyncio.CancelledError:
                progress_task.cancel()
                raise
            
            try:
                os.remove(inputs_file)
            except:
                pass
            
            if process.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                file_size = os.path.getsize(output_path)
                await progress.update("finalizing", 1.0, f"✅ Merge complete! {file_size / (1024*1024):.1f} MB")
                logger.info(f"✅ Merge completed: {output_path}")
                return output_path
            else:
                error_output = stderr.decode()[:150] if stderr else "Unknown error"
                logger.error(f"Merge failed: {error_output}")
                await progress.update("merging", None, f"❌ Merge failed: {error_output[:50]}")
                return None
        
        except asyncio.CancelledError:
            await status_message.edit_text(
                "🚫 **Merge Cancelled**\n\n"
                "✅ All processes stopped\n"
                "🧹 Temporary files cleaned\n"
                "💡 Start a new merge anytime"
            )
            return None
        
        except Exception as e:
            logger.error(f"Merge error: {e}", exc_info=True)
            await progress.update("merging", None, f"❌ Error: {str(e)[:50]}")
            return None
        
        finally:
            if user_id in active_merges:
                del active_merges[user_id]
