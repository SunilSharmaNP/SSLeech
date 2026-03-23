#!/usr/bin/env python3
from pyrogram.handlers import MessageHandler, CallbackQueryHandler
from pyrogram.filters import command, regex, user
from asyncio import sleep, wait_for, Event, wrap_future
from aiohttp import ClientSession
from aiofiles.os import path as aiopath
from yt_dlp import YoutubeDL, DownloadError
from functools import partial
from time import time
from re import search as re_search
from secrets import token_hex
from os import path as ospath, listdir
from contextlib import suppress
from logging import getLogger

from bot import DOWNLOAD_DIR, bot, categories_dict, config_dict, user_data, LOGGER, download_dict_lock, download_dict, non_queued_dl, queue_dict_lock
from bot.helper.ext_utils.task_manager import task_utils, stop_duplicate_check, limit_checker, is_queued
from bot.helper.telegram_helper.message_utils import (
    sendMessage,
    editMessage,
    deleteMessage,
    auto_delete_message,
    delete_links,
    open_category_btns,
    open_dump_btns,
    sendStatusMessage,
)
from bot.helper.telegram_helper.button_build import ButtonMaker
from bot.helper.ext_utils.bot_utils import (
    get_readable_file_size,
    fetch_user_tds,
    fetch_user_dumps,
    is_url,
    is_gdrive_link,
    new_task,
    sync_to_async,
    new_task,
    is_rclone_path,
    new_thread,
    get_readable_time,
    arg_parser,
    async_to_sync,
)
from bot.helper.mirror_utils.rclone_utils.list import RcloneList
from bot.helper.telegram_helper.bot_commands import BotCommands
from bot.helper.mirror_utils.upload_utils.gdriveTools import GoogleDriveHelper
from bot.helper.telegram_helper.filters import CustomFilters
from bot.helper.listeners.tasks_listener import MirrorLeechListener
from bot.helper.ext_utils.help_messages import YT_HELP_MESSAGE
from bot.helper.ext_utils.bulk_links import extract_bulk_links
from bot.helper.mirror_utils.status_utils.yt_dlp_download_status import YtDlpDownloadStatus
from bot.helper.mirror_utils.status_utils.queue_status import QueueStatus

# -------------------------------------------------------------------
# -------------------- YT-DLP Helper (adapted from wzv3) --------------------
# -------------------------------------------------------------------
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
        self._last_downloaded = 0
        self._size = 0
        self._progress = 0
        self._downloaded_bytes = 0
        self._download_speed = 0
        self._eta = "-"
        self._listener = listener
        self._gid = ""
        self._ext = ""
        self.name = ""
        self.is_playlist = False
        self.playlist_count = 0
        self.keep_thumb = False

        # Cookie handling
        user_dict = user_data.get(listener.uid, {})
        cookie_to_use = (
            user_dict.get("USER_COOKIE_FILE", "")
            if not user_dict.get("USE_DEFAULT_COOKIE", False)
            and user_dict.get("USER_COOKIE_FILE")
            and ospath.exists(user_dict.get("USER_COOKIE_FILE", ""))
            else "cookies.txt"
        )
        self.opts = {
            "progress_hooks": [self._on_download_progress],
            "logger": MyLogger(self, self._listener),
            "usenetrc": True,
            "cookiefile": cookie_to_use,
            "allow_multiple_video_streams": True,
            "allow_multiple_audio_streams": True,
            "noprogress": True,
            "allow_playlist_files": True,
            "overwrites": True,
            "writethumbnail": True,
            "trim_file_name": 220,
            # ffmpeg_location can be set from config if needed, but default is fine
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
            f"Using cookies.txt file: {cookie_to_use} | User ID : {listener.uid}"
        )

    @property
    def download_speed(self):
        return self._download_speed

    @property
    def downloaded_bytes(self):
        return self._downloaded_bytes

    @property
    def size(self):
        return self._size

    @property
    def progress(self):
        return self._progress

    @property
    def eta(self):
        return self._eta

    def _on_download_progress(self, d):
        if self._listener.is_cancelled:
            raise ValueError("Cancelling...")
        if d["status"] == "finished":
            if self.is_playlist:
                self._last_downloaded = 0
        elif d["status"] == "downloading":
            self._download_speed = d["speed"] or 0
            if self.is_playlist:
                downloadedBytes = d["downloaded_bytes"] or 0
                chunk_size = downloadedBytes - self._last_downloaded
                self._last_downloaded = downloadedBytes
                self._downloaded_bytes += chunk_size
            else:
                if d.get("total_bytes"):
                    self._size = d["total_bytes"] or 0
                elif d.get("total_bytes_estimate"):
                    self._size = d["total_bytes_estimate"] or 0
                self._downloaded_bytes = d["downloaded_bytes"] or 0
                self._eta = d.get("eta", "-") or "-"
            try:
                self._progress = (self._downloaded_bytes / self._size) * 100
            except ZeroDivisionError:
                pass

    async def _on_download_start(self, from_queue=False):
        async with download_dict_lock:
            download_dict[self._listener.uid] = YtDlpDownloadStatus(
                self, self._listener, self._gid
            )
        if not from_queue:
            await self._listener.on_download_start()
            if self._listener.multi <= 1:
                await sendStatusMessage(self._listener.message)

    def _on_download_error(self, error):
        self._listener.is_cancelled = True
        async_to_sync(self._listener.on_download_error, error)

    def _extract_meta_data(self):
        if self._listener.link.startswith(("rtmp", "mms", "rstp", "rtmps")):
            self.opts["external_downloader"] = "ffmpeg"
        with YoutubeDL(self.opts) as ydl:
            try:
                result = ydl.extract_info(self._listener.link, download=False)
                if result is None:
                    raise ValueError("Info result is None")
            except Exception as e:
                return self._on_download_error(str(e))
            if self.is_playlist:
                self.playlist_count = result.get("playlist_count", 0)
            if "entries" in result:
                for entry in result["entries"]:
                    if not entry:
                        continue
                    elif "filesize_approx" in entry:
                        self._size += entry.get("filesize_approx", 0) or 0
                    elif "filesize" in entry:
                        self._size += entry.get("filesize", 0) or 0
                    if not self.name:
                        outtmpl_ = "%(series,playlist_title,channel)s%(season_number& |)s%(season_number&S|)s%(season_number|)02d.%(ext)s"
                        self.name, ext = ospath.splitext(
                            ydl.prepare_filename(entry, outtmpl=outtmpl_)
                        )
                        if not self._ext:
                            self._ext = ext
            else:
                outtmpl_ = "%(title,fulltitle,alt_title)s%(season_number& |)s%(season_number&S|)s%(season_number|)02d%(episode_number&E|)s%(episode_number|)02d%(height& |)s%(height|)s%(height&p|)s%(fps|)s%(fps&fps|)s%(tbr& |)s%(tbr|)d.%(ext)s"
                realName = ydl.prepare_filename(result, outtmpl=outtmpl_)
                ext = ospath.splitext(realName)[-1]
                self.name = f"{self._listener.name}{ext}" if self._listener.name else realName
                if not self._ext:
                    self._ext = ext
                if result.get("filesize"):
                    self._size = result["filesize"]
                elif result.get("filesize_approx"):
                    self._size = result["filesize_approx"]

    def _download(self, path):
        with suppress(Exception):
            with YoutubeDL(self.opts) as ydl:
                try:
                    ydl.download([self._listener.link])
                except DownloadError as e:
                    if not self._listener.is_cancelled:
                        self._on_download_error(str(e))
                    return
            if self.is_playlist and (
                not ospath.exists(path) or len(listdir(path)) == 0
            ):
                self._on_download_error(
                    "No video available to download from this playlist. Check logs for more details"
                )
                return
            if self._listener.is_cancelled:
                return
            async_to_sync(self._listener.on_download_complete)

    async def add_download(self, path, qual, playlist, options):
        if playlist:
            self.opts["ignoreerrors"] = True
            self.is_playlist = True

        self._gid = token_hex(5)
        await self._on_download_start()

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
                self._ext = ".ogg"
            elif audio_format == "alac":
                self._ext = ".m4a"
            else:
                self._ext = f".{audio_format}"

        if not self._listener.is_leech or getattr(self._listener, "thumbnail_layout", False):
            self.opts["writethumbnail"] = False

        self.opts["format"] = qual

        if options:
            self._set_options(options)

        await sync_to_async(self._extract_meta_data)
        if self._listener.is_cancelled:
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
            self.name = f"{base_name}{self._ext}"

        if self.opts["writethumbnail"]:
            self.opts["postprocessors"].append(
                {
                    "format": "jpg",
                    "key": "FFmpegThumbnailsConvertor",
                    "when": "before_dl",
                }
            )
        if self._ext in [
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

        # Duplicate and limit checks
        msg, button = await stop_duplicate_check(self.name, self._listener)
        if msg:
            await self._listener.on_download_error(msg, button)
            return

        if limit_exceeded := await limit_checker(
            self._size, self._listener, isYtdlp=True, isPlayList=self.playlist_count
        ):
            await self._listener.on_download_error(limit_exceeded)
            return

        added_to_queue, event = await is_queued(self._listener.uid)
        if added_to_queue:
            LOGGER.info(f"Added to Queue/Download: {self.name}")
            async with download_dict_lock:
                download_dict[self._listener.uid] = QueueStatus(
                    self.name, self._size, self._gid, self._listener, "dl"
                )
            await event.wait()
            async with download_dict_lock:
                if self._listener.uid not in download_dict:
                    return
            LOGGER.info(f"Start Queued Download from YT_DLP: {self.name}")
            await self._on_download_start(True)
        else:
            LOGGER.info(f"Download with YT_DLP: {self.name}")

        async with queue_dict_lock:
            non_queued_dl.add(self._listener.uid)

        await sync_to_async(self._download, path)

    async def cancel_task(self):
        self._listener.is_cancelled = True
        LOGGER.info(f"Cancelling Download: {self.name}")
        await self._listener.on_download_error("Stopped by User!")

    def _set_options(self, options):
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


# -------------------------------------------------------------------
# -------------------- YT Selection (from master) --------------------
# -------------------------------------------------------------------
class YtSelection:
    def __init__(self, client, message):
        self.__message = message
        self.__user_id = message.from_user.id
        self.__client = client
        self.__is_m4a = False
        self.__reply_to = None
        self.__time = time()
        self.__timeout = 120
        self.__is_playlist = False
        self.is_cancelled = False
        self.__main_buttons = None
        self.event = Event()
        self.formats = {}
        self.qual = None

    @new_thread
    async def __event_handler(self):
        pfunc = partial(select_format, obj=self)
        handler = self.__client.add_handler(
            CallbackQueryHandler(pfunc, filters=regex("^ytq") & user(self.__user_id)),
            group=-1,
        )
        try:
            await wait_for(self.event.wait(), timeout=self.__timeout)
        except Exception:
            await editMessage(self.__reply_to, "Timed Out. Task has been cancelled!")
            self.qual = None
            self.is_cancelled = True
            self.event.set()
        finally:
            self.__client.remove_handler(*handler)

    async def get_quality(self, result):
        future = self.__event_handler()
        buttons = ButtonMaker()
        if "entries" in result:
            self.__is_playlist = True
            for i in ["144", "240", "360", "480", "720", "1080", "1440", "2160"]:
                video_format = f"bv*[height<=?{i}][ext=mp4]+ba[ext=m4a]/b[height<=?{i}]"
                b_data = f"{i}|mp4"
                self.formats[b_data] = video_format
                buttons.ibutton(f"{i}-mp4", f"ytq {b_data}")
                video_format = f"bv*[height<=?{i}][ext=webm]+ba/b[height<=?{i}]"
                b_data = f"{i}|webm"
                self.formats[b_data] = video_format
                buttons.ibutton(f"{i}-webm", f"ytq {b_data}")
            buttons.ibutton("MP3", "ytq mp3")
            buttons.ibutton("Audio Formats", "ytq audio")
            buttons.ibutton("Best Videos", "ytq bv*+ba/b")
            buttons.ibutton("Best Audios", "ytq ba/b")
            buttons.ibutton("Cancel", "ytq cancel", "footer")
            self.__main_buttons = buttons.build_menu(3)
            msg = f"Choose Playlist Videos Quality:\nTimeout: {get_readable_time(self.__timeout-(time()-self.__time))}"
        else:
            format_dict = result.get("formats")
            if format_dict is not None:
                for item in format_dict:
                    if item.get("tbr"):
                        format_id = item["format_id"]

                        if item.get("filesize"):
                            size = item["filesize"]
                        elif item.get("filesize_approx"):
                            size = item["filesize_approx"]
                        else:
                            size = 0

                        if (
                            item.get("video_ext") == "none"
                            and item.get("acodec") != "none"
                        ):
                            if item.get("audio_ext") == "m4a":
                                self.__is_m4a = True
                            b_name = f"{item['acodec']}-{item['ext']}"
                            v_format = format_id
                        elif item.get("height"):
                            height = item["height"]
                            ext = item["ext"]
                            fps = item["fps"] if item.get("fps") else ""
                            b_name = f"{height}p{fps}-{ext}"
                            ba_ext = (
                                "[ext=m4a]" if self.__is_m4a and ext == "mp4" else ""
                            )
                            v_format = f"{format_id}+ba{ba_ext}/b[height=?{height}]"
                        else:
                            continue

                        self.formats.setdefault(b_name, {})[f"{item['tbr']}"] = [
                            size,
                            v_format,
                        ]

                for b_name, tbr_dict in self.formats.items():
                    if len(tbr_dict) == 1:
                        tbr, v_list = next(iter(tbr_dict.items()))
                        buttonName = f"{b_name} ({get_readable_file_size(v_list[0])})"
                        buttons.ibutton(buttonName, f"ytq sub {b_name} {tbr}")
                    else:
                        buttons.ibutton(b_name, f"ytq dict {b_name}")
            buttons.ibutton("MP3", "ytq mp3")
            buttons.ibutton("Audio Formats", "ytq audio")
            buttons.ibutton("Best Video", "ytq bv*+ba/b")
            buttons.ibutton("Best Audio", "ytq ba/b")
            buttons.ibutton("Cancel", "ytq cancel", "footer")
            self.__main_buttons = buttons.build_menu(2)
            msg = f"Choose Video Quality:\nTimeout: {get_readable_time(self.__timeout-(time()-self.__time))}"
        self.__reply_to = await sendMessage(self.__message, msg, self.__main_buttons)
        await wrap_future(future)
        if not self.is_cancelled:
            await deleteMessage(self.__reply_to)
        return self.qual

    async def back_to_main(self):
        if self.__is_playlist:
            msg = f"Choose Playlist Videos Quality:\nTimeout: {get_readable_time(self.__timeout-(time()-self.__time))}"
        else:
            msg = f"Choose Video Quality:\nTimeout: {get_readable_time(self.__timeout-(time()-self.__time))}"
        await editMessage(self.__reply_to, msg, self.__main_buttons)

    async def qual_subbuttons(self, b_name):
        buttons = ButtonMaker()
        tbr_dict = self.formats[b_name]
        for tbr, d_data in tbr_dict.items():
            button_name = f"{tbr}K ({get_readable_file_size(d_data[0])})"
            buttons.ibutton(button_name, f"ytq sub {b_name} {tbr}")
        buttons.ibutton("Back", "ytq back", "footer")
        buttons.ibutton("Cancel", "ytq cancel", "footer")
        subbuttons = buttons.build_menu(2)
        msg = f"Choose Bit rate for <b>{b_name}</b>:\nTimeout: {get_readable_time(self.__timeout-(time()-self.__time))}"
        await editMessage(self.__reply_to, msg, subbuttons)

    async def mp3_subbuttons(self):
        i = "s" if self.__is_playlist else ""
        buttons = ButtonMaker()
        audio_qualities = [64, 128, 320]
        for q in audio_qualities:
            audio_format = f"ba/b-mp3-{q}"
            buttons.ibutton(f"{q}K-mp3", f"ytq {audio_format}")
        buttons.ibutton("Back", "ytq back")
        buttons.ibutton("Cancel", "ytq cancel")
        subbuttons = buttons.build_menu(3)
        msg = f"Choose mp3 Audio{i} Bitrate:\nTimeout: {get_readable_time(self.__timeout-(time()-self.__time))}"
        await editMessage(self.__reply_to, msg, subbuttons)

    async def audio_format(self):
        i = "s" if self.__is_playlist else ""
        buttons = ButtonMaker()
        for frmt in ["aac", "alac", "flac", "m4a", "opus", "vorbis", "wav"]:
            audio_format = f"ba/b-{frmt}-"
            buttons.ibutton(frmt, f"ytq aq {audio_format}")
        buttons.ibutton("Back", "ytq back", "footer")
        buttons.ibutton("Cancel", "ytq cancel", "footer")
        subbuttons = buttons.build_menu(3)
        msg = f"Choose Audio{i} Format:\nTimeout: {get_readable_time(self.__timeout-(time()-self.__time))}"
        await editMessage(self.__reply_to, msg, subbuttons)

    async def audio_quality(self, format):
        i = "s" if self.__is_playlist else ""
        buttons = ButtonMaker()
        for qual in range(11):
            audio_format = f"{format}{qual}"
            buttons.ibutton(qual, f"ytq {audio_format}")
        buttons.ibutton("Back", "ytq aq back")
        buttons.ibutton("Cancel", "ytq aq cancel")
        subbuttons = buttons.build_menu(5)
        msg = f"Choose Audio{i} Quality:\n0 is best and 10 is worst\nTimeout: {get_readable_time(self.__timeout-(time()-self.__time))}"
        await editMessage(self.__reply_to, msg, subbuttons)


# -------------------------------------------------------------------
# -------------------- Main Command Handlers ------------------------
# -------------------------------------------------------------------
def extract_info(link, options):
    with YoutubeDL(options) as ydl:
        result = ydl.extract_info(link, download=False)
        if result is None:
            raise ValueError("Info result is None")
        return result


async def _mdisk(link, name):
    key = link.split("/")[-1]
    async with ClientSession() as session:
        async with session.get(
            f"https://diskuploader.entertainvideo.com/v1/file/cdnurl?param={key}"
        ) as resp:
            if resp.status == 200:
                resp_json = await resp.json()
                link = resp_json["source"]
                if not name:
                    name = resp_json["filename"]
            return name, link


@new_task
async def _ytdl(client, message, isLeech=False, sameDir=None, bulk=[]):
    text = message.text.split("\n")
    input_list = text[0].split(" ")
    qual = ""
    arg_base = {
        "link": "",
        "-i": 0,
        "-m": "",
        "-sd": "",
        "-samedir": "",
        "-s": False,
        "-select": False,
        "-opt": "",
        "-options": "",
        "-b": False,
        "-bulk": False,
        "-n": "",
        "-name": "",
        "-z": False,
        "-zip": False,
        "-up": "",
        "-upload": False,
        "-rcf": "",
        "-id": "",
        "-index": "",
        "-c": "",
        "-category": "",
        "-ud": "",
        "-dump": "",
        "-ss": "0",
        "-screenshots": "",
        "-t": "",
        "-thumb": "",
    }

    args = arg_parser(input_list[1:], arg_base)
    cmd = input_list[0].split("@")[0]

    try:
        multi = int(args["-i"])
    except Exception:
        multi = 0

    select = args["-s"] or args["-select"]
    isBulk = args["-b"] or args["-bulk"]
    opt = args["-opt"] or args["-options"]
    folder_name = args["-m"] or args["-sd"] or args["-samedir"]
    name = args["-n"] or args["-name"]
    up = args["-up"] or args["-upload"]
    rcf = args["-rcf"]
    link = args["link"]
    compress = args["-z"] or args["-zip"] or "z" in cmd or "zip" in cmd
    drive_id = args["-id"]
    index_link = args["-index"]
    gd_cat = args["-c"] or args["-category"]
    user_dump = args["-ud"] or args["-dump"]
    bulk_start = 0
    bulk_end = 0
    thumb = args["-t"] or args["-thumb"]
    sshots = int(ss) if (ss := (args["-ss"] or args["-screenshots"])).isdigit() else 0

    if not isinstance(isBulk, bool):
        dargs = isBulk.split(":")
        bulk_start = dargs[0] or None
        if len(dargs) == 2:
            bulk_end = dargs[1] or None
        isBulk = True

    if drive_id and is_gdrive_link(drive_id):
        drive_id = GoogleDriveHelper.getIdFromUrl(drive_id)

    if folder_name and not isBulk:
        folder_name = f"/{folder_name}"
        if sameDir is None:
            sameDir = {"total": multi, "tasks": set(), "name": folder_name}
        sameDir["tasks"].add(message.id)

    if isBulk:
        try:
            bulk = await extract_bulk_links(message, bulk_start, bulk_end)
            if len(bulk) == 0:
                raise ValueError("Bulk Empty!")
        except Exception:
            await sendMessage(
                message,
                "Reply to text file or tg message that have links seperated by new line!",
            )
            return
        b_msg = input_list[:1]
        b_msg.append(f"{bulk[0]} -i {len(bulk)}")
        nextmsg = await sendMessage(message, " ".join(b_msg))
        nextmsg = await client.get_messages(
            chat_id=message.chat.id, message_ids=nextmsg.id
        )
        nextmsg.from_user = message.from_user
        _ytdl(client, nextmsg, isLeech, sameDir, bulk)
        return

    if len(bulk) != 0:
        del bulk[0]

    @new_task
    async def __run_multi():
        if multi <= 1:
            return
        await sleep(5)
        if len(bulk) != 0:
            msg = input_list[:1]
            msg.append(f"{bulk[0]} -i {multi - 1}")
            nextmsg = await sendMessage(message, " ".join(msg))
        else:
            msg = [s.strip() for s in input_list]
            index = msg.index("-i")
            msg[index + 1] = f"{multi - 1}"
            nextmsg = await client.get_messages(
                chat_id=message.chat.id, message_ids=message.reply_to_message_id + 1
            )
            nextmsg = await sendMessage(nextmsg, " ".join(msg))
        nextmsg = await client.get_messages(
            chat_id=message.chat.id, message_ids=nextmsg.id
        )
        if folder_name:
            sameDir["tasks"].add(nextmsg.id)
        nextmsg.from_user = message.from_user
        await sleep(5)
        _ytdl(client, nextmsg, isLeech, sameDir, bulk)

    path = f"{DOWNLOAD_DIR}{message.id}{folder_name}"

    if len(text) > 1 and text[1].startswith("Tag: "):
        tag, id_ = text[1].split("Tag: ")[1].split()
        message.from_user = await client.get_users(id_)
        try:
            await message.unpin()
        except Exception:
            pass
    elif sender_chat := message.sender_chat:
        tag = sender_chat.title

    user_id = message.from_user.id

    user_dict = user_data.get(user_id, {})

    opt = opt or user_dict.get("yt_opt") or config_dict["YT_DLP_OPTIONS"]

    if username := message.from_user.username:
        tag = f"@{username}"
    else:
        tag = message.from_user.mention

    if not link and (reply_to := message.reply_to_message) and reply_to.text:
        link = reply_to.text.split("\n", 1)[0].strip()

    if not is_url(link):
        btn = ButtonMaker()
        btn.ibutton(
            "Cʟɪᴄᴋ Hᴇʀᴇ Tᴏ Rᴇᴀᴅ Mᴏʀᴇ ...", f"wzmlx {message.from_user.id} help YT"
        )
        await sendMessage(message, YT_HELP_MESSAGE[0], btn.build_menu(1))
        await delete_links(message)
        return

    error_msg = []
    error_button = None
    task_utilis_msg, error_button = await task_utils(message)
    if task_utilis_msg:
        error_msg.extend(task_utilis_msg)

    if error_msg:
        final_msg = f"Hey, <b>{tag}</b>,\n"
        for __i, __msg in enumerate(error_msg, 1):
            final_msg += f"\n<b>{__i}</b>: {__msg}\n"
        if error_button is not None:
            error_button = error_button.build_menu(2)
        await sendMessage(message, final_msg, error_button)
        await delete_links(message)
        return

    if not isLeech:
        if config_dict["DEFAULT_UPLOAD"] == "rc" and not up or up == "rc":
            up = config_dict["RCLONE_PATH"]
        elif config_dict["DEFAULT_UPLOAD"] == "ddl" and not up or up == "ddl":
            up = "ddl"
        if not up and config_dict["DEFAULT_UPLOAD"] == "gd":
            up = "gd"
            user_tds = await fetch_user_tds(message.from_user.id)
            if not drive_id and gd_cat:
                merged_dict = {**categories_dict, **user_tds}
                for drive_name, drive_dict in merged_dict.items():
                    if drive_name.casefold() == gd_cat.replace("_", " ").casefold():
                        drive_id, index_link = (
                            drive_dict["drive_id"],
                            drive_dict["index_link"],
                        )
                        break
            if not drive_id and len(user_tds) == 1:
                drive_id, index_link = next(iter(user_tds.values())).values()
            elif not drive_id and (
                len(categories_dict) > 1
                and len(user_tds) == 0
                or len(categories_dict) >= 1
                and len(user_tds) > 1
            ):
                drive_id, index_link, is_cancelled = await open_category_btns(message)
                if is_cancelled:
                    await delete_links(message)
                    return
            if drive_id and not await sync_to_async(
                GoogleDriveHelper().getFolderData, drive_id
            ):
                return await sendMessage(message, "Google Drive ID validation failed!!")
        if up == "gd" and not config_dict["GDRIVE_ID"] and not drive_id:
            await sendMessage(message, "GDRIVE_ID not Provided!")
            await delete_links(message)
            return
        elif not up:
            await sendMessage(message, "No Rclone Destination!")
            await delete_links(message)
            return
        elif up not in ["rcl", "gd", "ddl"]:
            if up.startswith("mrcc:"):
                config_path = f"rclone/{message.from_user.id}.conf"
            else:
                config_path = "rclone.conf"
            if not await aiopath.exists(config_path):
                await sendMessage(message, f"Rclone Config: {config_path} not Exists!")
                await delete_links(message)
                return
        if up != "gd" and up != "ddl" and not is_rclone_path(up):
            await sendMessage(message, "Wrong Rclone Upload Destination!")
            await delete_links(message)
            return
    else:
        if user_dump and (user_dump.isdigit() or user_dump.startswith("-")):
            up = int(user_dump)
        elif user_dump and user_dump.startswith("@"):
            up = user_dump
        elif ldumps := await fetch_user_dumps(message.from_user.id):
            if user_dump and user_dump.casefold() == "all":
                up = [dump_id for dump_id in ldumps.values()]
            elif user_dump:
                up = next(
                    (
                        dump_id
                        for name_, dump_id in ldumps.items()
                        if user_dump.casefold() == name_.casefold()
                    ),
                    "",
                )
            if not up and len(ldumps) == 1:
                up = next(iter(ldumps.values()))
            elif not up:
                up, is_cancelled = await open_dump_btns(message)
                if is_cancelled:
                    await delete_links(message)
                    return

    if up == "rcl" and not isLeech:
        up = await RcloneList(client, message).get_rclone_path("rcu")
        if not is_rclone_path(up):
            await sendMessage(message, up)
            await delete_links(message)
            return

    # Create listener
    listener = MirrorLeechListener(
        message,
        compress,
        isLeech=isLeech,
        tag=tag,
        sameDir=sameDir,
        rcFlags=rcf,
        upPath=up,
        drive_id=drive_id,
        index_link=index_link,
        isYtdlp=True,
        source_url=link,
        leech_utils={"screenshots": sshots, "thumb": thumb},
    )
    listener.link = link
    listener.name = name
    listener.multi = multi

    if "mdisk.me" in link:
        name, link = await _mdisk(link, name)
        listener.link = link
        listener.name = name

    # Build yt-dlp options
    options = {"usenetrc": True}
    if opt:
        yt_opt = opt.split("|")
        for ytopt in yt_opt:
            key, value = map(str.strip, ytopt.split(":", 1))
            if key == "format":
                if select:
                    qual = ""
                elif value.startswith("ba/b-"):
                    qual = value
                    continue
            if value.startswith("^"):
                if "." in value or value == "^inf":
                    value = float(value.split("^")[1])
                else:
                    value = int(value.split("^")[1])
            elif value.lower() == "true":
                value = True
            elif value.lower() == "false":
                value = False
            elif value.startswith(("{", "[", "(")) and value.endswith(("}", "]", ")")):
                value = eval(value)
            options[key] = value

        options["playlist_items"] = "0"

    try:
        result = await sync_to_async(extract_info, link, options)
    except Exception as e:
        msg = str(e).replace("<", " ").replace(">", " ")
        await sendMessage(message, f"{tag} {msg}")
        __run_multi()
        await delete_links(message)
        return

    __run_multi()

    if not select and (not qual and "format" in options):
        qual = options["format"]

    if not qual:
        qual = await YtSelection(client, message).get_quality(result)
        if qual is None:
            return

    await delete_links(message)
    LOGGER.info(f"Downloading with YT-DLP: {link}")
    playlist = "entries" in result
    ydl = YoutubeDLHelper(listener)
    await ydl.add_download(path, qual, playlist, options)


async def ytdl(client, message):
    _ytdl(client, message)


async def ytdlleech(client, message):
    _ytdl(client, message, isLeech=True)


bot.add_handler(
    MessageHandler(
        ytdl,
        filters=command(BotCommands.YtdlCommand)
        & CustomFilters.authorized
        & ~CustomFilters.blacklisted,
    )
)
bot.add_handler(
    MessageHandler(
        ytdlleech,
        filters=command(BotCommands.YtdlLeechCommand)
        & CustomFilters.authorized
        & ~CustomFilters.blacklisted,
    )
)
