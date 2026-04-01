import re
from time import time
from datetime import timedelta

from bot import LOGGER, VID_MODE
from bot.helper.ext_utils.bot_utils import async_to_sync
from bot.helper.ext_utils.fs_utils import get_path_size
from bot.helper.ext_utils.bot_utils import get_readable_file_size, MirrorStatus, get_readable_time


class FFMpegStatus:
    def __init__(self, listener, obj, gid, status):
        self._gid = gid
        self._obj = obj
        self._status = status
        self._time = time()
        self.listener = listener
        
        # FFmpeg progress tracking
        self.current_frame = 0
        self.current_fps = 0.0
        self.current_bitrate = ''
        self.current_speed = 0.0
        self.total_frames = 0
        self.video_duration = 0  # in seconds
        self.encoding_started = False

    @staticmethod
    def engine():
        return 'FFmpeg'

    def elapsed(self):
        return get_readable_time(time() - self._time)

    def processed_bytes(self):
        return get_readable_file_size(self._obj.processed_bytes)

    def gid(self):
        return self._gid

    def progress(self):
        if self._status != 'direct':
            return self._obj.percentage
        try:
            progress_raw = self._obj.processed_bytes / self._obj.size * 100
        except:
            progress_raw = 0
        return f'{round(progress_raw, 2)}%'

    def speed(self):
        return f'{get_readable_file_size(self._obj.speed)}/s'

    def name(self):
        return self._obj.name if self._obj else self.listener.name

    def size(self):
        size = self._obj.size if self._obj else async_to_sync(get_path_size, self.listener.dir)
        return get_readable_file_size(size)

    def timeout(self):
        return get_readable_time(180 - (time() - self._time))

    def eta(self):
        if self._status != 'direct':
            return get_readable_time(self._obj.eta)
        try:
            return get_readable_time((self._obj.size - self._obj.processed_bytes) / self._obj.speed)
        except:
            return '~'

    def status(self):
        match self._status:
            case 'meta':
                return MirrorStatus.STATUS_METADATA
            case 'sv':
                return MirrorStatus.STATUS_SAMVID
            case 'wait':
                return MirrorStatus.STATUS_WAIT

        match self._obj.mode:
            case 'vid_vid' | 'vid_aud' | 'vid_sub':
                return MirrorStatus.STATUS_MERGING
            case 'convert':
                return MirrorStatus.STATUS_CONVERT
            case 'subsync':
                return MirrorStatus.STATUS_SUBSYNC
            case 'compress':
                return MirrorStatus.STATUS_COMPRESS
            case 'trim':
                return MirrorStatus.STATUS_TRIM
            case 'watermark':
                return MirrorStatus.STATUS_WATERMARK
            case 'rmstream':
                return MirrorStatus.STATUS_RMSTREAM
            case _:
                return MirrorStatus.STATUS_EXTRACTING

    def task(self):
        return self

    @staticmethod
    def parse_ffmpeg_progress(output_line):
        """
        Parse ffmpeg progress output line
        Example: frame=1234 fps=25.5 time=00:05:30 bitrate=2500k speed=1.05x
        
        Returns: Dict with parsed values
        """
        result = {}
        try:
            # Frame number
            frame_match = re.search(r'frame=\s*(\d+)', output_line)
            if frame_match:
                result['frame'] = int(frame_match.group(1))
            
            # FPS
            fps_match = re.search(r'fps=\s*([\d.]+)', output_line)
            if fps_match:
                result['fps'] = float(fps_match.group(1))
            
            # Bitrate
            bitrate_match = re.search(r'bitrate=\s*([\d.]+[kmg])', output_line, re.IGNORECASE)
            if bitrate_match:
                result['bitrate'] = bitrate_match.group(1)
            
            # Speed
            speed_match = re.search(r'speed=\s*([\d.]+)x', output_line)
            if speed_match:
                result['speed'] = float(speed_match.group(1))
            
            # Time
            time_match = re.search(r'time=(\d{1,2}):(\d{2}):(\d{2})(?:\.(\d+))?', output_line)
            if time_match:
                h = int(time_match.group(1))
                m = int(time_match.group(2))
                s = int(time_match.group(3))
                result['time'] = h * 3600 + m * 60 + s
        except Exception as e:
            LOGGER.debug(f"Failed to parse ffmpeg line: {e}")
        
        return result
    
    def update_ffmpeg_progress(self, output_line):
        """Update progress from ffmpeg output line"""
        parsed = self.parse_ffmpeg_progress(output_line)
        if not parsed:
            return False
        
        if 'frame' in parsed:
            self.current_frame = parsed['frame']
            self.encoding_started = True
        if 'fps' in parsed:
            self.current_fps = parsed['fps']
        if 'bitrate' in parsed:
            self.current_bitrate = parsed['bitrate']
        if 'speed' in parsed:
            self.current_speed = parsed['speed']
        
        return True
    
    def get_encoding_progress(self):
        """Calculate encoding progress percentage"""
        if self.total_frames <= 0:
            return 0
        
        progress = (self.current_frame / self.total_frames) * 100
        return min(progress, 100)
    
    def get_encoding_eta(self):
        """Calculate remaining encoding time"""
        if self.current_fps <= 0.1:
            return 0
        
        remaining_frames = max(0, self.total_frames - self.current_frame)
        eta_seconds = remaining_frames / self.current_fps if self.current_fps > 0.1 else 0
        return max(eta_seconds, 0)
        match self._status:
            case 'sv':
                info = 'Creating sample video'
            case 'meta':
                info = 'Edit metadata'
            case _:
                info = VID_MODE[self._obj.mode]

        LOGGER.info('Cancelling %s: %s', info, self.name())
        if self.listener.suproc and self.listener.suproc.returncode is None:
            self.listener.suproc.kill()
        else:
            self.listener.suproc = 'cancelled'
        await self.listener.onUploadError(f'{info} stopped by user!')
