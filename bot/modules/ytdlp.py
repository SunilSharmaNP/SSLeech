#!/usr/bin/env python3
from pyrogram.handlers import MessageHandler, CallbackQueryHandler
from pyrogram.filters import command, regex, user
from asyncio import sleep, wait_for, Event, wrap_future
from aiohttp import ClientSession
from aiofiles.os import path as aiopath
from yt_dlp import YoutubeDL
from yt_dlp.networking.impersonate import ImpersonateTarget
from functools import partial
from time import time

from bot import DOWNLOAD_DIR, bot, categories_dict, config_dict, user_data, LOGGER
from bot.helper.ext_utils.task_manager import task_utils
from bot.helper.telegram_helper.message_utils import (
    sendMessage,
    editMessage,
    deleteMessage,
    auto_delete_message,
    delete_links,
    open_category_btns,
    open_dump_btns,
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
)
from bot.helper.mirror_utils.download_utils.yt_dlp_download import YoutubeDLHelper
from bot.helper.mirror_utils.download_utils.direct_link_generator import (
    direct_link_generator,
    user_agent as _dlg_user_agent,
)
from bot.helper.ext_utils.exceptions import DirectDownloadLinkException
from bot.helper.mirror_utils.rclone_utils.list import RcloneList
from bot.helper.telegram_helper.bot_commands import BotCommands
from bot.helper.mirror_utils.upload_utils.gdriveTools import GoogleDriveHelper
from bot.helper.telegram_helper.filters import CustomFilters
from bot.helper.listeners.tasks_listener import MirrorLeechListener
from bot.helper.ext_utils.help_messages import YT_HELP_MESSAGE
from bot.helper.ext_utils.bulk_links import extract_bulk_links


@new_task
async def select_format(_, query, obj):
    data = query.data.split()
    message = query.message
    await query.answer()

    if data[1] == "dict":
        b_name = data[2]
        await obj.qual_subbuttons(b_name)
    elif data[1] == "mp3":
        await obj.mp3_subbuttons()
    elif data[1] == "audio":
        await obj.audio_format()
    elif data[1] == "aq":
        if data[2] == "back":
            await obj.audio_format()
        else:
            await obj.audio_quality(data[2])
    elif data[1] == "back":
        await obj.back_to_main()
    elif data[1] == "cancel":
        await editMessage(message, "Task has been cancelled.")
        obj.qual = None
        obj.is_cancelled = True
        obj.event.set()
    else:
        if data[1] == "sub":
            obj.qual = obj.formats[data[2]][data[3]][1]
        elif "|" in data[1]:
            obj.qual = obj.formats[data[1]]
        else:
            obj.qual = data[1]
        obj.event.set()


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
            buttons.ibutton("❌ Cancel", "ytq cancel", "footer")
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
            buttons.ibutton("❌ Cancel", "ytq cancel", "footer")
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
        buttons.ibutton("🔙 Back", "ytq back", "footer")
        buttons.ibutton("❌ Cancel", "ytq cancel", "footer")
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
        buttons.ibutton("🔙 Back", "ytq back")
        buttons.ibutton("❌ Cancel", "ytq cancel")
        subbuttons = buttons.build_menu(3)
        msg = f"Choose mp3 Audio{i} Bitrate:\nTimeout: {get_readable_time(self.__timeout-(time()-self.__time))}"
        await editMessage(self.__reply_to, msg, subbuttons)

    async def audio_format(self):
        i = "s" if self.__is_playlist else ""
        buttons = ButtonMaker()
        for frmt in ["aac", "alac", "flac", "m4a", "opus", "vorbis", "wav"]:
            audio_format = f"ba/b-{frmt}-"
            buttons.ibutton(frmt, f"ytq aq {audio_format}")
        buttons.ibutton("🔙 Back", "ytq back", "footer")
        buttons.ibutton("❌ Cancel", "ytq cancel", "footer")
        subbuttons = buttons.build_menu(3)
        msg = f"Choose Audio{i} Format:\nTimeout: {get_readable_time(self.__timeout-(time()-self.__time))}"
        await editMessage(self.__reply_to, msg, subbuttons)

    async def audio_quality(self, format):
        i = "s" if self.__is_playlist else ""
        buttons = ButtonMaker()
        for qual in range(11):
            audio_format = f"{format}{qual}"
            buttons.ibutton(qual, f"ytq {audio_format}")
        buttons.ibutton("🔙 Back", "ytq aq back")
        buttons.ibutton("❌ Cancel", "ytq aq cancel")
        subbuttons = buttons.build_menu(5)
        msg = f"Choose Audio{i} Quality:\n0 is best and 10 is worst\nTimeout: {get_readable_time(self.__timeout-(time()-self.__time))}"
        await editMessage(self.__reply_to, msg, subbuttons)


def extract_info(link, options):
    with YoutubeDL(options) as ydl:
        result = ydl.extract_info(link, download=False)
        if result is None:
            raise ValueError("Info result is None")
        return result


async def _parse_luluvdo_m3u8(url, headers):
    """
    Fetch HLS master playlist and return yt-dlp format dicts (one per quality variant).
    Also returns estimated total duration in seconds (from media playlist EXTINF tags).
    Falls back to a single best-quality entry on any error.

    Uses curl_cffi with Chrome impersonation so tnmr.org CDN TLS-fingerprint checks
    pass (aiohttp/Python-SSL gets HTTP 403 from tnmr.org just like yt-dlp does).
    """
    import re
    import asyncio
    from urllib.parse import urljoin as _urljoin

    # Use m3u8_native so yt-dlp's Python HTTP client (with impersonate="chrome")
    # downloads every segment — never falls back to ffmpeg's own HTTP stack which
    # also gets blocked by the CDN TLS fingerprint check.
    _PROTO = "m3u8_native"

    _fallback = (
        [{
            "format_id": "hls-best",
            "url": url,
            "ext": "mp4",
            "protocol": _PROTO,
            "vcodec": "h264",
            "acodec": "mp4a.40.2",
            "height": None,
            "tbr": None,
            "filesize": None,
            "filesize_approx": None,
            "http_headers": headers,
        }],
        0,
    )

    # curl_cffi impersonates Chrome TLS — required to avoid 403 from tnmr.org CDN
    try:
        from curl_cffi import requests as _curl_req
    except ImportError:
        return _fallback

    loop = asyncio.get_event_loop()

    try:
        resp = await loop.run_in_executor(
            None,
            lambda: _curl_req.get(url, headers=headers, impersonate="chrome", timeout=15),
        )
        if resp.status_code != 200:
            return _fallback
        content = resp.text
    except Exception:
        return _fallback

    # Not a master playlist — single media playlist; estimate duration from EXTINF
    if "#EXT-X-STREAM-INF" not in content:
        duration = sum(
            float(ln.split(":")[1].split(",")[0])
            for ln in content.splitlines()
            if ln.startswith("#EXTINF:")
        )
        fmt = _fallback[0][0].copy()
        fmt["url"] = url
        return [fmt], duration

    # Master playlist — parse variants
    formats = []
    lines = content.strip().splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith("#EXT-X-STREAM-INF"):
            bw, height = 0, 0
            bw_m = re.search(r"BANDWIDTH=(\d+)", line)
            res_m = re.search(r"RESOLUTION=\d+x(\d+)", line)
            if bw_m:
                bw = int(bw_m.group(1))
            if res_m:
                height = int(res_m.group(1))
            j = i + 1
            while j < len(lines) and lines[j].strip().startswith("#"):
                j += 1
            if j < len(lines):
                vurl = lines[j].strip()
                if not vurl.startswith("http"):
                    vurl = _urljoin(url, vurl)
                fmt_id = f"hls-{height}p" if height else f"hls-{bw // 1000}k"
                formats.append({
                    "format_id": fmt_id,
                    "url": vurl,
                    "ext": "mp4",
                    "protocol": _PROTO,
                    "vcodec": "h264",
                    "acodec": "mp4a.40.2",
                    "height": height or None,
                    "tbr": round(bw / 1000) if bw else None,
                    "filesize": None,
                    "filesize_approx": None,
                    "http_headers": headers,
                })
            i = j + 1
        else:
            i += 1

    if not formats:
        return _fallback

    formats = sorted(formats, key=lambda x: x.get("height") or 0)

    # Try to estimate duration from the highest-quality variant's media playlist
    best_url = formats[-1]["url"]
    best_tbr = formats[-1].get("tbr") or 0
    duration = 0.0
    try:
        resp2 = await loop.run_in_executor(
            None,
            lambda: _curl_req.get(best_url, headers=headers, impersonate="chrome", timeout=15),
        )
        if resp2.status_code == 200:
            mpls = resp2.text
            duration = sum(
                float(ln.split(":")[1].split(",")[0])
                for ln in mpls.splitlines()
                if ln.startswith("#EXTINF:")
            )
    except Exception:
        pass

    # Seed filesize_approx for each variant using duration × bitrate
    if duration > 0:
        for fmt in formats:
            tbr = fmt.get("tbr") or best_tbr
            if tbr:
                fmt["filesize_approx"] = int(duration * tbr * 1000 / 8)

    return formats, duration


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

    if config_dict.get("DISABLE_YTDLP"):
        await sendMessage(
            message,
            "<b>❌ YT-DLP Disabled!</b>\n\nyt-dlp (YouTube/media URL) downloads are currently disabled by the admin.",
        )
        await delete_links(message)
        return

    try:
        multi = int(args["-i"])
    except Exception:
        multi = 0

    # FIX: quality buttons ON by default — user was expecting this behaviour
    # -s / -select still works; -ns / -noselect skips the quality menu
    select = True
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

    if "mdisk.me" in link:
        name, link = await _mdisk(link, name)

    # ── luluvdo.com / lulustream.com ────────────────────────────────────────────
    # yt-dlp has NO extractor for luluvdo. The m3u8 URL is CDN-protected and
    # tnmr.org blocks requests at the TLS fingerprint level — both Python-SSL
    # (urllib/aiohttp) AND the new ffmpeg build get HTTP 403.
    #
    # Solution: skip extract_info → build a synthetic info_dict with protocol
    # "m3u8_native" → yt-dlp uses its own Python HTTP client + impersonate="chrome"
    # (curl_cffi under the hood) for every manifest and segment request so
    # tnmr.org sees a real Chrome TLS fingerprint.
    _is_luluvdo = False
    _lulu_info_dict = None

    if any(h in link for h in ("luluvdo.com", "lulustream.com")):
        _is_luluvdo = True
        try:
            resolved = await sync_to_async(direct_link_generator, link)
            _lulu_page_title = None
            if isinstance(resolved, tuple):
                if len(resolved) == 3:
                    stream_url, ref_header, _lulu_page_title = resolved
                else:
                    stream_url, ref_header = resolved
                ref_val = ref_header.split(": ", 1)[-1]
            else:
                stream_url, ref_val = resolved, "https://luluvdo.com/"
            LOGGER.info(f"luluvdo resolved → {stream_url[:80]}… title={_lulu_page_title!r}")
            link = stream_url
            from urllib.parse import urlparse as _up
            _parsed = _up(ref_val)
            _origin = f"{_parsed.scheme}://{_parsed.netloc}"
            _lulu_http_headers = {
                "Referer": ref_val,
                "Origin": _origin,
                "User-Agent": _dlg_user_agent,
            }
            # Parse m3u8 master playlist for quality variants + size estimation
            # (_parse_luluvdo_m3u8 uses curl_cffi internally for the same reason)
            _lulu_formats, _lulu_duration = await _parse_luluvdo_m3u8(
                stream_url, _lulu_http_headers
            )
            _lulu_filesize = 0
            if _lulu_duration and _lulu_formats:
                # Use best-quality format bitrate for top-level size hint
                best_fmt = max(_lulu_formats, key=lambda f: f.get("tbr") or 0)
                if best_fmt.get("tbr"):
                    _lulu_filesize = int(_lulu_duration * best_fmt["tbr"] * 1000 / 8)

            _lulu_info_dict = {
                "id": "luluvdo",
                "title": name or _lulu_page_title or "luluvdo_video",
                "webpage_url": stream_url,
                "original_url": stream_url,
                "extractor": "generic",
                "extractor_key": "Generic",
                "http_headers": _lulu_http_headers,
                "formats": _lulu_formats,
                "filesize_approx": _lulu_filesize or None,
                "duration": _lulu_duration or None,
            }
            options = {"usenetrc": True, "cookiefile": "cookies.txt"}
        except DirectDownloadLinkException as e:
            await sendMessage(message, f"{tag} {e}")
            await delete_links(message)
            return
    else:
        options = {"usenetrc": True, "cookiefile": "cookies.txt"}
    # ────────────────────────────────────────────────────────────────────────────
    ydl_opts = {}
    if opt:
        if opt.strip().startswith("{"):
            try:
                ydl_opts = eval(opt)
                if not isinstance(ydl_opts, dict):
                    raise ValueError
            except Exception:
                ydl_opts = {}
        if ydl_opts:
            for key, value in ydl_opts.items():
                if key in ["postprocessors", "download_ranges"]:
                    continue
                if key == "format":
                    if select:
                        qual = ""
                    elif value.startswith("ba/b-"):
                        qual = value
                        continue
                    else:
                        qual = value
                options[key] = value
        else:
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
                ydl_opts[key] = value

        options["playlist_items"] = "0"

    # ── luluvdo: skip extract_info entirely, use process_ie_result via info_dict ─
    # extract_info on the m3u8 URL 403s ("Downloading webpage" phase) and
    # external ffmpeg also 403s (new base image TLS fingerprint blocked by CDN).
    # Solution: m3u8_native protocol + impersonate="chrome" → yt-dlp uses
    # curl_cffi for all manifest and segment fetches, passing Chrome TLS.
    if _is_luluvdo and _lulu_info_dict is not None:
        _lulu_title = name or _lulu_page_title or _lulu_info_dict.get("title", "luluvdo_video")
        # Use yt-dlp's native m3u8_native downloader with Chrome impersonation so
        # every segment request goes through curl_cffi — bypasses tnmr.org CDN TLS
        # fingerprint check that blocks both Python-SSL and the new ffmpeg build.
        # ImpersonateTarget object required — plain string causes AssertionError in yt-dlp.
        ydl_opts["impersonate"] = ImpersonateTarget.from_str("chrome")
        ydl_opts["http_headers"] = _lulu_http_headers

        # Quality selection — show buttons when multiple variants are available
        _lulu_fmts = _lulu_info_dict.get("formats", [])
        _lulu_sel_qual = "best"
        if len(_lulu_fmts) > 1:
            _lulu_qual_str = await YtSelection(client, message).get_quality(_lulu_info_dict)
            if _lulu_qual_str is None:
                return  # user cancelled
            # qual string is e.g. "hls-720p+ba/b[height=?720]" — extract format_id
            _sel_fmt_id = _lulu_qual_str.split("+")[0].strip()
            _sel_fmt = next(
                (f for f in _lulu_fmts if f["format_id"] == _sel_fmt_id), None
            )
            if _sel_fmt:
                # Narrow info_dict to exactly the chosen variant so yt-dlp can't
                # silently fall back to a different quality
                _lulu_info_dict["formats"] = [_sel_fmt]
                _lulu_info_dict["filesize_approx"] = (
                    _sel_fmt.get("filesize_approx") or _lulu_info_dict.get("filesize_approx")
                )
                _lulu_sel_qual = _sel_fmt["format_id"]
            else:
                _lulu_sel_qual = _lulu_qual_str

        __run_multi()
        await delete_links(message)
        LOGGER.info(f"luluvdo: process_ie_result+ffmpeg → {link[:80]}… qual={_lulu_sel_qual}")
        ydl = YoutubeDLHelper(listener)
        await ydl.add_download(
            link, path, _lulu_title, _lulu_sel_qual,
            False, ydl_opts, info_dict=_lulu_info_dict,
        )
        return
    # ──────────────────────────────────────────────────────────────────────────

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
    await ydl.add_download(link, path, name, qual, playlist, ydl_opts or opt)


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
