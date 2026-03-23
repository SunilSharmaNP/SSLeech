#!/usr/bin/env python3
from os import path as ospath, listdir
from secrets import token_hex
from logging import getLogger
from yt_dlp import YoutubeDL, DownloadError
from re import search as re_search
from contextlib import suppress

from bot import task_dict_lock, task_dict, user_data
from bot.helper.ext_utils.bot_utils import sync_to_async, async_to_sync
from bot.helper.ext_utils.task_manager import (
    check_running_tasks,
    stop_duplicate_check,
    limit_checker,
)
from bot.helper.telegram_helper.message_utils import send_status_message
from ..status_utils.yt_dlp_download_status import YtDlpDownloadStatus
from bot.helper.mirror_utils.status_utils.queue_status import QueueStatus
from bot.core.config_manager import BinConfig

LOGGER = getLogger(__name__)


class MyLogger:
    def __init__(self, obj, listener):
        self.obj = obj
        self._listener = listener

    def debug(self, msg):
        # Hack to fix changing extension
        if not self.obj.is_playlist:
            if match := re_search(
                r".Merger..Merging formats into..(.*?).$", msg
            ) or re_search(r".ExtractAudio..Destination..(.*?)$", msg):
                LOGGER.info(msg)
                newname = match.group(1)
                newname = newname.rsplit("/", 1)[-1]
                self.obj.name = newname

    @staticmethod
    def warning(msg):
        LOGGER.warning(msg)

    @staticmethod
    def error(msg):
        if msg != "ERROR: Cancelling...":
            LOGGER.error(msg)


class YoutubeDLHelper:
    def __init__(self, listener):
        self.__last_downloaded = 0
        self.__size = 0
        self.__progress = 0
        self.__downloaded_bytes = 0
        self.__download_speed = 0
        self.__eta = "-"
        self.__listener = listener
        self.__gid = ""
        self.__is_cancelled = False
        self.__downloading = False
        self.__ext = ""
        self.name = ""
        self.is_playlist = False
        self.playlist_count = 0
        self.keep_thumb = False

        # Cookie handling
        user_dict = user_data.get(self.__listener.uid, {})
        cookie_to_use = (
            user_dict.get("USER_COOKIE_FILE", "")
            if not user_dict.get("USE_DEFAULT_COOKIE", False)
            and ospath.exists(user_dict.get("USER_COOKIE_FILE", ""))
            else "cookies.txt"
        )

        self.opts = {
            "progress_hooks": [self.__onDownloadProgress],
            "logger": MyLogger(self, self.__listener),
            "usenetrc": True,
            "cookiefile": cookie_to_use,
            "allow_multiple_video_streams": True,
            "allow_multiple_audio_streams": True,
            "noprogress": True,
            "allow_playlist_files": True,
            "overwrites": True,
            "writethumbnail": True,
            "trim_file_name": 220,
            "ffmpeg_location": f"/bin/{BinConfig.FFMPEG_NAME}",
            "fragment_retries": 10,
            "retries": 10,
            "retry_sleep_functions": {
                "http": lambda n: 3,
                "fragment": lambda n: 3,
                "file_access": lambda n: 3,
                "extractor": lambda n: 3,
            },
        }
        LOGGER.info(
            f"Using cookies.txt file: {cookie_to_use} | User ID : {self.__listener.uid}"
        )

    @property
    def download_speed(self):
        return self.__download_speed

    @property
    def downloaded_bytes(self):
        return self.__downloaded_bytes

    @property
    def size(self):
        return self.__size

    @property
    def progress(self):
        return self.__progress

    @property
    def eta(self):
        return self.__eta

    def __onDownloadProgress(self, d):
        self.__downloading = True
        if self.__is_cancelled:
            raise ValueError("Cancelling...")
        if d["status"] == "finished":
            if self.is_playlist:
                self.__last_downloaded = 0
        elif d["status"] == "downloading":
            self.__download_speed = d["speed"] or 0
            if self.is_playlist:
                downloadedBytes = d["downloaded_bytes"] or 0
                chunk_size = downloadedBytes - self.__last_downloaded
                self.__last_downloaded = downloadedBytes
                self.__downloaded_bytes += chunk_size
            else:
                if d.get("total_bytes"):
                    self.__size = d["total_bytes"] or 0
                elif d.get("total_bytes_estimate"):
                    self.__size = d["total_bytes_estimate"] or 0
                self.__downloaded_bytes = d["downloaded_bytes"] or 0
                self.__eta = d.get("eta", "-") or "-"
            try:
                self.__progress = (self.__downloaded_bytes / self.__size) * 100
            except ZeroDivisionError:
                pass

    async def __onDownloadStart(self, from_queue=False):
        async with task_dict_lock:
            task_dict[self.__listener.mid] = YtDlpDownloadStatus(
                self, self.__listener, self.__gid
            )
        if not from_queue:
            await self.__listener.onDownloadStart()
            if self.__listener.multi <= 1:
                await send_status_message(self.__listener.message)

    def __onDownloadError(self, error):
        self.__is_cancelled = True
        async_to_sync(self.__listener.onDownloadError, error)

    def extractMetaData(self, link):
        if link.startswith(("rtmp", "mms", "rstp", "rtmps")):
            self.opts["external_downloader"] = BinConfig.FFMPEG_NAME
        with YoutubeDL(self.opts) as ydl:
            try:
                result = ydl.extract_info(link, download=False)
                if result is None:
                    raise ValueError("Info result is None")
            except Exception as e:
                return self.__onDownloadError(str(e))
            if self.is_playlist:
                self.playlist_count = result.get("playlist_count", 0)
            if "entries" in result:
                for entry in result["entries"]:
                    if not entry:
                        continue
                    elif "filesize_approx" in entry:
                        self.__size += entry.get("filesize_approx", 0) or 0
                    elif "filesize" in entry:
                        self.__size += entry.get("filesize", 0) or 0
                    if not self.name:
                        outtmpl_ = "%(series,playlist_title,channel)s%(season_number& |)s%(season_number&S|)s%(season_number|)02d.%(ext)s"
                        self.name, ext = ospath.splitext(
                            ydl.prepare_filename(entry, outtmpl=outtmpl_)
                        )
                        if not self.__ext:
                            self.__ext = ext
            else:
                outtmpl_ = "%(title,fulltitle,alt_title)s%(season_number& |)s%(season_number&S|)s%(season_number|)02d%(episode_number&E|)s%(episode_number|)02d%(height& |)s%(height|)s%(height&p|)s%(fps|)s%(fps&fps|)s%(tbr& |)s%(tbr|)d.%(ext)s"
                realName = ydl.prepare_filename(result, outtmpl=outtmpl_)
                ext = ospath.splitext(realName)[-1]
                self.name = f"{self.__listener.name}{ext}" if self.__listener.name else realName
                if not self.__ext:
                    self.__ext = ext
                if result.get("filesize"):
                    self.__size = result["filesize"]
                elif result.get("filesize_approx"):
                    self.__size = result["filesize_approx"]

    def __download(self, link, path):
        try:
            with suppress(Exception):
                with YoutubeDL(self.opts) as ydl:
                    try:
                        ydl.download([link])
                    except DownloadError as e:
                        if not self.__is_cancelled:
                            self.__onDownloadError(str(e))
                        return
                if self.is_playlist and (
                    not ospath.exists(path) or len(listdir(path)) == 0
                ):
                    self.__onDownloadError(
                        "No video available to download from this playlist. Check logs for more details"
                    )
                    return
                if self.__is_cancelled:
                    return
                async_to_sync(self.__listener.onDownloadComplete)
        except ValueError:
            self.__onDownloadError("Download Stopped by User!")

    async def add_download(self, link, path, qual, playlist, options):
        if playlist:
            self.opts["ignoreerrors"] = True
            self.is_playlist = True

        self.__gid = token_hex(5)
        await self.__onDownloadStart()

        self.opts["postprocessors"] = [
            {
                "add_chapters": True,
                "add_infojson": "if_exists",
                "add_metadata": True,
                "key": "FFmpegMetadata",
            }
        ]

        if qual.startswith("ba/b-"):
            audio_info = qual.split("-")
            qual = audio_info[0]
            audio_format = audio_info[1]
            rate = audio_info[2]
            self.opts["postprocessors"].append(
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": audio_format,
                    "preferredquality": rate,
                }
            )
            if audio_format == "vorbis":
                self.__ext = ".ogg"
            elif audio_format == "alac":
                self.__ext = ".m4a"
            else:
                self.__ext = f".{audio_format}"

        if not self.__listener.isLeech or getattr(self.__listener, "thumbnail_layout", False):
            self.opts["writethumbnail"] = False

        self.opts["format"] = qual

        if options:
            self.__set_options(options)

        await sync_to_async(self.extractMetaData, link)
        if self.__is_cancelled:
            return

        base_name, ext = ospath.splitext(self.name)
        trim_name = self.name if self.is_playlist else base_name
        if len(trim_name.encode()) > 200:
            self.name = (
                self.name[:200] if self.is_playlist else f"{base_name[:200]}{ext}"
            )
            base_name = ospath.splitext(self.name)[0]

        start_path = path if self.keep_thumb else f"{path}/yt-dlp-thumb"
        if self.is_playlist:
            self.opts["outtmpl"] = {
                "default": f"{path}/{self.name}/%(title,fulltitle,alt_title)s%(season_number& |)s%(season_number&S|)s%(season_number|)02d%(episode_number&E|)s%(episode_number|)02d%(height& |)s%(height|)s%(height&p|)s%(fps|)s%(fps&fps|)s%(tbr& |)s%(tbr|)d.%(ext)s",
                "thumbnail": f"{start_path}/%(title,fulltitle,alt_title)s%(season_number& |)s%(season_number&S|)s%(season_number|)02d%(episode_number&E|)s%(episode_number|)02d%(height& |)s%(height|)s%(height&p|)s%(fps|)s%(fps&fps|)s%(tbr& |)s%(tbr|)d.%(ext)s",
            }
        elif "download_ranges" in options:
            self.opts["outtmpl"] = {
                "default": f"{path}/{base_name}/%(section_number|)s%(section_number&.|)s%(section_title|)s%(section_title&-|)s%(title,fulltitle,alt_title)s %(section_start)s to %(section_end)s.%(ext)s",
                "thumbnail": f"{start_path}/%(section_number|)s%(section_number&.|)s%(section_title|)s%(section_title&-|)s%(title,fulltitle,alt_title)s %(section_start)s to %(section_end)s.%(ext)s",
            }
        elif any(
            key in options
            for key in [
                "writedescription",
                "writeinfojson",
                "writeannotations",
                "writedesktoplink",
                "writewebloclink",
                "writeurllink",
                "writesubtitles",
                "write_all_thumbnails",
            ]
        ):
            self.opts["outtmpl"] = {
                "default": f"{path}/{base_name}/{self.name}",
                "thumbnail": f"{start_path}/{base_name}.%(ext)s",
            }
        else:
            self.opts["outtmpl"] = {
                "default": f"{path}/{self.name}",
                "thumbnail": f"{start_path}/{base_name}.%(ext)s",
            }

        if qual.startswith("ba/b"):
            self.name = f"{base_name}{self.__ext}"

        if self.opts["writethumbnail"]:
            self.opts["postprocessors"].append(
                {
                    "format": "jpg",
                    "key": "FFmpegThumbnailsConvertor",
                    "when": "before_dl",
                }
            )
        if self.__ext in [
            ".mp3",
            ".mkv",
            ".mka",
            ".ogg",
            ".opus",
            ".flac",
            ".m4a",
            ".mp4",
            ".mov",
            ".m4v",
        ]:
            self.opts["postprocessors"].append(
                {
                    "already_have_thumbnail": self.opts["writethumbnail"],
                    "key": "EmbedThumbnail",
                }
            )

        msg, button = await stop_duplicate_check(self.__listener)
        if msg:
            await self.__listener.onDownloadError(msg, button)
            return

        if limit_exceeded := await limit_checker(self.__listener, self.playlist_count):
            await self.__listener.onDownloadError(limit_exceeded, is_limit=True)
            return

        add_to_queue, event = await check_running_tasks(self.__listener)
        if add_to_queue:
            LOGGER.info(f"Added to Queue/Download: {self.name}")
            async with task_dict_lock:
                task_dict[self.__listener.mid] = QueueStatus(
                    self.name, self.__size, self.__gid, self.__listener, "dl"
                )
            await event.wait()
            if self.__is_cancelled:
                return
            LOGGER.info(f"Start Queued Download from YT_DLP: {self.name}")
            await self.__onDownloadStart(True)

        if not add_to_queue:
            LOGGER.info(f"Download with YT_DLP: {self.name}")

        await sync_to_async(self.__download, link, path)

    async def cancel_download(self):
        self.__is_cancelled = True
        self.__listener.is_cancelled = True
        LOGGER.info(f"Cancelling Download: {self.name}")
        if not self.__downloading:
            await self.__listener.onDownloadError("Download Cancelled by User!")

    def __set_options(self, options):
        for key, value in options.items():
            if key == "postprocessors":
                if isinstance(value, list):
                    self.opts[key].extend(tuple(value))
                elif isinstance(value, dict):
                    self.opts[key].append(value)
            elif key == "download_ranges":
                if isinstance(value, list):
                    self.opts[key] = lambda info, ytdl: value
            else:
                if key == "writethumbnail" and value is True:
                    self.keep_thumb = True
                self.opts[key] = value
