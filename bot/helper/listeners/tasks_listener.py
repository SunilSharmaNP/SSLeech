#!/usr/bin/env python3



from random import choice
from time import time
from copy import deepcopy
from pytz import timezone
from datetime import datetime
from urllib.parse import unquote, quote
from requests import utils as rutils
from aiofiles.os import path as aiopath, remove as aioremove, listdir, makedirs
from os import walk, path as ospath
from html import escape
from aioshutil import move
from asyncio import create_subprocess_exec, sleep, Event, wait_for, TimeoutError as ATimeoutError
from asyncio.subprocess import PIPE
from pyrogram.enums import ChatType
from pyrogram.handlers import MessageHandler, CallbackQueryHandler
from pyrogram.filters import create as pyrogram_create_filter

from bot import (
    OWNER_ID,
    Interval,
    aria2,
    DOWNLOAD_DIR,
    download_dict,
    download_dict_lock,
    LOGGER,
    bot_name,
    DATABASE_URL,
    MAX_SPLIT_SIZE,
    config_dict,
    status_reply_dict_lock,
    user_data,
    non_queued_up,
    non_queued_dl,
    queued_up,
    queued_dl,
    queue_dict_lock,
    bot,
    GLOBAL_EXTENSION_FILTER,
    same_directory_lock,
)
from bot.helper.ext_utils.bot_utils import (
    extra_btns,
    sync_to_async,
    get_readable_file_size,
    get_readable_time,
    is_mega_link,
    is_gdrive_link,
)
from bot.helper.ext_utils.fs_utils import (
    get_base_name,
    get_path_size,
    clean_download,
    clean_target,
    is_first_archive_split,
    is_archive,
    is_archive_split,
    join_files,
    edit_metadata,
    MetaProgress,
)
from bot.helper.ext_utils.leech_utils import (
    split_file,
    format_filename,
    get_document_type,
)
from bot.helper.ext_utils.exceptions import NotSupportedExtractionArchive
from bot.helper.ext_utils.task_manager import start_from_queued
from bot.helper.mirror_utils.status_utils.extract_status import ExtractStatus
from bot.helper.mirror_utils.status_utils.zip_status import ZipStatus
from bot.helper.mirror_utils.status_utils.split_status import SplitStatus
from bot.helper.mirror_utils.status_utils.gdrive_status import GdriveStatus
from bot.helper.mirror_utils.status_utils.telegram_status import TelegramStatus
from bot.helper.mirror_utils.status_utils.ddl_status import DDLStatus
from bot.helper.mirror_utils.status_utils.rclone_status import RcloneStatus
from bot.helper.mirror_utils.status_utils.queue_status import QueueStatus
from bot.helper.mirror_utils.upload_utils.gdriveTools import GoogleDriveHelper
from bot.helper.mirror_utils.upload_utils.pyrogramEngine import TgUploader
from bot.helper.mirror_utils.upload_utils.ddlEngine import DDLUploader
from bot.helper.mirror_utils.rclone_utils.transfer import RcloneTransferHelper
from bot.helper.mirror_utils.status_utils.metadata_status import MetadataStatus
from bot.helper.mirror_utils.status_utils.merge_status import MergeStatus
from bot.helper.ext_utils.video_merge import (
    merge_video_files,
    get_video_files_sorted,
    parse_episode_selection,
)
from bot.helper.telegram_helper.message_utils import (
    sendCustomMsg,
    sendMessage,
    editMessage,
    deleteMessage,
    delete_all_messages,
    delete_links,
    sendMultiMessage,
    update_all_messages,
)
from bot.helper.telegram_helper.button_build import ButtonMaker
from bot.helper.ext_utils.db_handler import DbManger
from bot.helper.themes import BotTheme
from bot.helper.ext_utils.emojis import E


class MirrorLeechListener:
    def __init__(
        self,
        message,
        compress=False,
        extract=False,
        isQbit=False,
        isLeech=False,
        tag=None,
        select=False,
        seed=False,
        sameDir=None,
        rcFlags=None,
        upPath=None,
        isClone=False,
        join=False,
        drive_id=None,
        index_link=None,
        isYtdlp=False,
        source_url=None,
        logMessage=None,
        leech_utils={},
        merge_video=False,
        merge_output_name="",
    ):
        if sameDir is None:
            sameDir = {}
        self.message = message
        self.uid = message.id
        self.excep_chat = bool(
            str(message.chat.id) in config_dict["EXCEP_CHATS"].split()
        )
        self.extract = extract
        self.compress = compress
        self.isQbit = isQbit
        self.isLeech = isLeech
        self.isClone = isClone
        self.isMega = is_mega_link(source_url) if source_url else False
        self.isGdrive = is_gdrive_link(source_url) if source_url else False
        self.isYtdlp = isYtdlp
        self.tag = tag
        self.seed = seed
        self.newDir = ""
        self.dir = f"{DOWNLOAD_DIR}{self.uid}"
        self.select = select
        self.isSuperGroup = message.chat.type in [ChatType.SUPERGROUP, ChatType.CHANNEL]
        self.isPrivate = message.chat.type == ChatType.BOT
        self.user_id = self.message.from_user.id
        self.user_dict = user_data.get(self.user_id, {})
        self.isPM = config_dict["BOT_PM"] or self.user_dict.get("bot_pm")
        self.suproc = None
        self.sameDir = sameDir
        self.rcFlags = rcFlags
        self.upPath = upPath
        self.random_pic = "IMAGES" if config_dict["IMAGES"] else None
        self.join = join
        self.drive_id = drive_id
        self.index_link = index_link
        self.logMessage = logMessage
        self.linkslogmsg = None
        self.botpmmsg = None
        self.upload_details = {}
        self.leech_utils = leech_utils
        self.merge_video = merge_video
        self.merge_output_name = merge_output_name
        self.source_url = (
            source_url
            if source_url and source_url.startswith("http")
            else (
                f"https://t.me/share/url?url={source_url}"
                if source_url
                else message.link
            )
        )
        self.source_msg = ""
        self.__setModeEng()
        self.__parseSource()

    async def clean(self):
        try:
            async with status_reply_dict_lock:
                if Interval:
                    Interval[0].cancel()
                    Interval.clear()
            await sync_to_async(aria2.purge)
            await delete_all_messages()
        except Exception:
            pass

    def __setModeEng(self):
        mode = f" #{'Leech' if self.isLeech else 'Clone' if self.isClone else 'RClone' if self.upPath not in ['gd', 'ddl'] else 'DDL' if self.upPath != 'gd' else 'GDrive'}"
        mode += " (Zip)" if self.compress else " (Unzip)" if self.extract else ""
        mode += f" | #{'qBit' if self.isQbit else 'ytdlp' if self.isYtdlp else 'GDrive' if (self.isClone or self.isGdrive) else 'Mega' if self.isMega else 'Aria2' if self.source_url and self.source_url != self.message.link else 'Tg'}"
        self.upload_details["mode"] = mode

    def __parseSource(self):
        if self.source_url == self.message.link:
            file = self.message.reply_to_message
            if file:
                self.source_url = file.link
            if file is not None and file.media is not None:
                mtype = file.media.value
                media = getattr(file, mtype)
                self.source_msg = f'┎ <b>Name:</b> <i>{media.file_name if hasattr(media, "file_name") else f"{mtype}_{media.file_unique_id}"}</i>\n┠ <b>Type:</b> {media.mime_type if hasattr(media, "mime_type") else "image/jpeg" if mtype == "photo" else "text/plain"}\n┠ <b>Size:</b> {get_readable_file_size(media.file_size)}\n┠ <b>Created Date:</b> {media.date}\n┖ <b>Media Type:</b> {mtype.capitalize()}'
            else:
                reply_text = (
                    getattr(self.message.reply_to_message, "text", None)
                    or getattr(self.message.reply_to_message, "caption", None)
                    if self.message.reply_to_message
                    else None
                )
                self.source_msg = f"<code>{reply_text or 'N/A'}</code>"
        elif self.source_url.startswith("https://t.me/share/url?url="):
            msg = self.source_url.replace("https://t.me/share/url?url=", "")
            if msg.startswith("magnet"):
                mag = unquote(msg).split("&")
                tracCount, name, amper = 0, "", False
                for check in mag:
                    if check.startswith("tr="):
                        tracCount += 1
                    elif check.startswith("magnet:?xt=urn:btih:"):
                        hashh = check.replace("magnet:?xt=urn:btih:", "")
                    else:
                        name += ("&" if amper else "") + check.replace(
                            "dn=", ""
                        ).replace("+", " ")
                        amper = True
                self.source_msg = f"┎ <b>Name:</b> <i>{name}</i>\n┠ <b>Magnet Hash:</b> <code>{hashh}</code>\n┠ <b>Total Trackers:</b> {tracCount} \n┖ <b>Share:</b> <a href='https://t.me/share/url?url={quote(msg)}'>Share To Telegram</a>"
            else:
                self.source_msg = f"<code>{msg}</code>"
        else:
            self.source_msg = f"<code>{self.source_url}</code>"

    async def onDownloadStart(self):
        if config_dict["LINKS_LOG_ID"] and not self.excep_chat:
            dispTime = datetime.now(timezone(config_dict["TIMEZONE"])).strftime(
                "%d/%m/%y, %I:%M:%S %p"
            )
            self.linkslogmsg = await sendCustomMsg(
                config_dict["LINKS_LOG_ID"],
                BotTheme("LINKS_START", Mode=self.upload_details["mode"], Tag=self.tag)
                + BotTheme("LINKS_SOURCE", On=dispTime, Source=self.source_msg),
            )
        if self.isPM and self.isSuperGroup:
            self.botpmmsg = await sendCustomMsg(
                self.message.from_user.id,
                BotTheme("PM_START", msg_link=self.source_url),
            )
        if (
            self.isSuperGroup
            and config_dict["INCOMPLETE_TASK_NOTIFIER"]
            and DATABASE_URL
        ):
            await DbManger().add_incomplete_task(
                self.message.chat.id,
                self.message.link,
                self.tag,
                self.source_url,
                self.message.text,
            )

    _MERGE_CANCEL_MSG = (
        "❌ 𝐌ᴇʀɢᴇ 𝐁ᴀᴛᴄʜ 𝐂ᴀɴᴄᴇʟʟᴇᴅ — 𝐀 𝐟ɪʟᴇ ᴅᴏᴡɴʟᴏᴀᴅ 𝐟ᴀɪʟᴇᴅ/𝐜ᴀɴᴄᴇʟʟᴇᴅ. "
        "𝐀ʟʟ 𝐟ɪʟᴇs 𝐦ᴜsᴛ 𝐜𝐨𝐦𝐩ʟᴇᴛᴇ 𝐛𝐞𝐟𝐨ʀᴇ 𝐦𝐞𝐫𝐠𝐞."
    )

    async def onDownloadComplete(self):
        multi_links = False
        while True:
            if self.sameDir:
                # If any file in this merge batch failed, abort immediately.
                # (Only triggered for merge batches — merge_mode key is set.)
                if self.sameDir.get("failed"):
                    LOGGER.warning(
                        f"[MERGE] Aborting task {self.uid} — "
                        f"batch failed: {self.sameDir['failed']}"
                    )
                    await self.onUploadError(self._MERGE_CANCEL_MSG)
                    return
                if (
                    self.sameDir["total"] in [1, 0]
                    or self.sameDir["total"] > 1
                    and len(self.sameDir["tasks"]) > 1
                ):
                    break
            else:
                break
            await sleep(0.2)
        async with same_directory_lock:
            # Atomic re-check inside the lock so no failed file slips through
            # between the wait loop and the actual merge/move decision.
            if self.sameDir and self.sameDir.get("failed"):
                LOGGER.warning(
                    f"[MERGE] Last task {self.uid} aborting inside lock — "
                    f"batch had a failed file"
                )
                await self.onUploadError(self._MERGE_CANCEL_MSG)
                return
            async with download_dict_lock:
                if self.sameDir and self.sameDir["total"] > 1:
                    self.sameDir["tasks"].remove(self.uid)
                    self.sameDir["total"] -= 1
                    folder_name = self.sameDir["name"]
                    spath = f"{self.dir}/{folder_name}"
                    des_path = (
                        f"{DOWNLOAD_DIR}{list(self.sameDir['tasks'])[0]}/{folder_name}"
                    )
                    await makedirs(des_path, exist_ok=True)
                    for item in await listdir(spath):
                        if item.endswith((".aria2", ".!qB")):
                            continue
                        item_path = f"{self.dir}/{folder_name}/{item}"
                        if item in await listdir(des_path):
                            await move(item_path, f"{des_path}/{self.uid}-{item}")
                        else:
                            await move(item_path, f"{des_path}/{item}")
                    multi_links = True
                download = download_dict[self.uid]
                name = str(download.name()).replace("/", "")
                gid = download.gid()
        LOGGER.info(f"Download Completed: {name}")
        if multi_links:
            await self.onUploadError(f"{E.done} 𝐏𝐚𝐫𝐭 𝐑𝐞𝐚𝐝𝐲 — 𝐰𝐚𝐢𝐭𝐢𝐧𝐠 𝐟𝐨𝐫 𝐫𝐞𝐦𝐚𝐢𝐧𝐢𝐧𝐠 𝐩𝐚𝐫𝐭𝐬 𝐭𝐨 𝐜𝐨𝐦𝐩𝐥𝐞𝐭𝐞…")
            return
        if (
            name == "None"
            or self.isQbit
            or not await aiopath.exists(f"{self.dir}/{name}")
        ):
            try:
                files = await listdir(self.dir)
            except Exception as e:
                await self.onUploadError(str(e))
                return
            name = files[-1]
            if name == "yt-dlp-thumb":
                name = files[0]

        dl_path = f"{self.dir}/{name}"
        up_path = ""
        size = await get_path_size(dl_path)
        async with queue_dict_lock:
            if self.uid in non_queued_dl:
                non_queued_dl.remove(self.uid)
        await start_from_queued()
        user_dict = user_data.get(self.message.from_user.id, {})

        if self.join and await aiopath.isdir(dl_path):
            await join_files(dl_path)

        if self.merge_video and not self.extract and await aiopath.isdir(dl_path):
            merged = await self._do_folder_merge(dl_path, name, size, gid)
            if merged is None:
                return
            up_path = merged

        if self.extract:
            pswd = self.extract if isinstance(self.extract, str) else ""
            try:
                if await aiopath.isfile(dl_path):
                    up_path = get_base_name(dl_path)
                LOGGER.info(f"Extracting: {name}")
                async with download_dict_lock:
                    download_dict[self.uid] = ExtractStatus(name, size, gid, self)
                if await aiopath.isdir(dl_path):
                    if self.seed:
                        self.newDir = f"{self.dir}10000"
                        up_path = f"{self.newDir}/{name}"
                    else:
                        up_path = dl_path
                    for dirpath, _, files in await sync_to_async(
                        walk, dl_path, topdown=False
                    ):
                        for file_ in files:
                            if (
                                is_first_archive_split(file_)
                                or is_archive(file_)
                                and not file_.endswith(".rar")
                            ):
                                f_path = ospath.join(dirpath, file_)
                                t_path = (
                                    dirpath.replace(self.dir, self.newDir)
                                    if self.seed
                                    else dirpath
                                )
                                cmd = [
                                    "7z",
                                    "x",
                                    f"-p{pswd}",
                                    f_path,
                                    f"-o{t_path}",
                                    "-aot",
                                    "-xr!@PaxHeader",
                                ]
                                if not pswd:
                                    del cmd[2]
                                if (
                                    self.suproc == "cancelled"
                                    or self.suproc is not None
                                    and self.suproc.returncode == -9
                                ):
                                    return
                                self.suproc = await create_subprocess_exec(*cmd)
                                code = await self.suproc.wait()
                                if code == -9:
                                    return
                                elif code != 0:
                                    LOGGER.error("Unable to extract archive splits!")
                        if (
                            not self.seed
                            and self.suproc is not None
                            and self.suproc.returncode == 0
                        ):
                            for file_ in files:
                                if is_archive_split(file_) or is_archive(file_):
                                    del_path = ospath.join(dirpath, file_)
                                    try:
                                        await aioremove(del_path)
                                    except Exception:
                                        return
                else:
                    if self.seed:
                        self.newDir = f"{self.dir}10000"
                        up_path = up_path.replace(self.dir, self.newDir)
                    cmd = [
                        "7z",
                        "x",
                        f"-p{pswd}",
                        dl_path,
                        f"-o{up_path}",
                        "-aot",
                        "-xr!@PaxHeader",
                    ]
                    if not pswd:
                        del cmd[2]
                    if self.suproc == "cancelled":
                        return
                    self.suproc = await create_subprocess_exec(*cmd)
                    code = await self.suproc.wait()
                    if code == -9:
                        return
                    elif code == 0:
                        LOGGER.info(f"Extracted Path: {up_path}")
                        if not self.seed:
                            try:
                                await aioremove(dl_path)
                            except Exception:
                                return
                    else:
                        LOGGER.error("Unable to extract archive! Uploading anyway")
                        self.newDir = ""
                        up_path = dl_path
            except NotSupportedExtractionArchive:
                LOGGER.info("Not any valid archive, uploading file as it is.")
                self.newDir = ""
                up_path = dl_path

        if self.merge_video and self.extract and await aiopath.isdir(up_path or dl_path):
            _extract_dir = up_path if (up_path and up_path != dl_path) else dl_path
            merged = await self._do_zip_merge(_extract_dir, name, size, gid)
            if merged is None:
                return
            up_path = merged

        if metadata := self.user_dict.get("lmeta") or config_dict["METADATA"]:
            meta_path = up_path or dl_path
            self.newDir = f"{self.dir}10000"
            await makedirs(self.newDir, exist_ok=True)
            self.meta_progress = MetaProgress()
            async with download_dict_lock:
                download_dict[self.uid] = MetadataStatus(name, size, gid, self)
            if (
                await aiopath.isfile(meta_path)
                and (await get_document_type(meta_path))[0]
            ):
                base_dir, file_name = ospath.split(meta_path)
                outfile = ospath.join(self.newDir, file_name)
                await edit_metadata(self, base_dir, meta_path, outfile, metadata)
                if self.suproc == "cancelled":
                    return
            elif await aiopath.isdir(meta_path):
                for dirpath, _, files in await sync_to_async(walk, meta_path):
                    for file in files:
                        if self.suproc == "cancelled":
                            return
                        video_file = ospath.join(dirpath, file)
                        if (await get_document_type(video_file))[0]:
                            outfile = ospath.join(self.newDir, file)
                            await edit_metadata(
                                self, dirpath, video_file, outfile, metadata
                            )

        if self.compress:
            pswd = self.compress if isinstance(self.compress, str) else ""
            if up_path:
                dl_path = up_path
                up_path = f"{up_path}.zip"
            elif self.seed and self.isLeech:
                self.newDir = f"{self.dir}10000"
                up_path = f"{self.newDir}/{name}.zip"
            else:
                up_path = f"{dl_path}.zip"
            async with download_dict_lock:
                download_dict[self.uid] = ZipStatus(name, size, gid, self)
            LEECH_SPLIT_SIZE = (
                user_dict.get("split_size", False) or config_dict["LEECH_SPLIT_SIZE"]
            )
            cmd = [
                "7z",
                f"-v{LEECH_SPLIT_SIZE}b",
                "a",
                "-mx=0",
                f"-p{pswd}",
                up_path,
                dl_path,
            ]
            for ext in GLOBAL_EXTENSION_FILTER:
                ex_ext = f"-xr!*.{ext}"
                cmd.append(ex_ext)
            if self.isLeech and int(size) > LEECH_SPLIT_SIZE:
                if not pswd:
                    del cmd[4]
                LOGGER.info(f"Zip: orig_path: {dl_path}, zip_path: {up_path}.0*")
            else:
                del cmd[1]
                if not pswd:
                    del cmd[3]
                LOGGER.info(f"Zip: orig_path: {dl_path}, zip_path: {up_path}")
            if self.suproc == "cancelled":
                return
            self.suproc = await create_subprocess_exec(*cmd)
            code = await self.suproc.wait()
            if code == -9:
                return
            elif not self.seed:
                await clean_target(dl_path)

        if not self.compress and not self.extract and not up_path:
            up_path = dl_path

        up_dir, up_name = up_path.rsplit("/", 1)
        size = await get_path_size(up_dir)
        if self.isLeech:
            m_size = []
            o_files = []
            if not self.compress:
                LEECH_SPLIT_SIZE = (
                    user_dict.get("split_size", False)
                    or config_dict["LEECH_SPLIT_SIZE"]
                )
                # --- Pre-scan: collect every file that needs splitting ---
                # We do this BEFORE splitting so we can set split_current_total
                # once to the combined size of all files. Previously total/done
                # were reset per-file, making progress jump back to 0% for each
                # new file and confusing users into thinking the split restarted.
                files_to_split = []
                for dirpath, _, files in await sync_to_async(
                    walk, up_dir, topdown=False
                ):
                    for file_ in files:
                        f_path = ospath.join(dirpath, file_)
                        f_size = await aiopath.getsize(f_path)
                        if f_size > LEECH_SPLIT_SIZE:
                            files_to_split.append((dirpath, file_, f_path, f_size))

                if files_to_split:
                    from time import time as _split_time
                    async with download_dict_lock:
                        download_dict[self.uid] = SplitStatus(
                            up_name, size, gid, self
                        )
                    LOGGER.info(f"Splitting: {up_name}")
                    # Set grand-total ONCE so progress never resets between files
                    self.split_current_total = sum(f[3] for f in files_to_split)
                    self.split_current_done = 0
                    self.split_elapsed = 0
                    self._split_start = _split_time()
                    # split_base_offset = bytes already finished in previous files
                    # leech_utils reads this to keep progress globally cumulative
                    self.split_base_offset = 0

                    for dirpath, file_, f_path, f_size in files_to_split:
                        res = await split_file(
                            f_path, f_size, file_, dirpath, LEECH_SPLIT_SIZE, self
                        )
                        # Advance global offset by what leech_utils actually wrote
                        self.split_base_offset = self.split_current_done

                        if not res:
                            return
                        if res == "errored":
                            if f_size <= MAX_SPLIT_SIZE:
                                continue
                            try:
                                await aioremove(f_path)
                            except Exception:
                                return
                        elif not self.seed or self.newDir:
                            try:
                                await aioremove(f_path)
                            except Exception:
                                return
                        else:
                            m_size.append(f_size)
                            o_files.append(file_)

        up_limit = config_dict["QUEUE_UPLOAD"]
        all_limit = config_dict["QUEUE_ALL"]
        added_to_queue = False
        async with queue_dict_lock:
            dl = len(non_queued_dl)
            up = len(non_queued_up)
            if (
                all_limit and dl + up >= all_limit and (not up_limit or up >= up_limit)
            ) or (up_limit and up >= up_limit):
                added_to_queue = True
                LOGGER.info(f"Added to Queue/Upload: {name}")
                event = Event()
                queued_up[self.uid] = event
        if added_to_queue:
            async with download_dict_lock:
                download_dict[self.uid] = QueueStatus(name, size, gid, self, "Up")
            await event.wait()
            async with download_dict_lock:
                if self.uid not in download_dict:
                    return
            LOGGER.info(f"Start from Queued/Upload: {name}")
        async with queue_dict_lock:
            non_queued_up.add(self.uid)
        if self.isLeech:
            size = await get_path_size(up_dir)
            for s in m_size:
                size = size - s
            LOGGER.info(f"Leech Name: {up_name}")
            tg = TgUploader(up_name, up_dir, self)
            tg_upload_status = TelegramStatus(
                tg, size, self.message, gid, "up", self.upload_details
            )
            async with download_dict_lock:
                download_dict[self.uid] = tg_upload_status
            await update_all_messages()
            await tg.upload(o_files, m_size, size)
        elif self.upPath == "gd":
            size = await get_path_size(up_path)
            LOGGER.info(f"Upload Name: {up_name}")
            drive = GoogleDriveHelper(up_name, up_dir, self)
            upload_status = GdriveStatus(
                drive, size, self.message, gid, "up", self.upload_details
            )
            async with download_dict_lock:
                download_dict[self.uid] = upload_status
            await update_all_messages()

            await sync_to_async(drive.upload, up_name, size, self.drive_id)
        elif self.upPath == "ddl":
            size = await get_path_size(up_path)
            LOGGER.info(f"Upload Name: {up_name} via DDL")
            ddl = DDLUploader(self, up_name, up_dir)
            ddl_upload_status = DDLStatus(
                ddl, size, self.message, gid, self.upload_details
            )
            async with download_dict_lock:
                download_dict[self.uid] = ddl_upload_status
            await update_all_messages()
            await ddl.upload(up_name, size)
        else:
            size = await get_path_size(up_path)
            LOGGER.info(f"Upload Name: {up_name} via RClone")
            RCTransfer = RcloneTransferHelper(self, up_name)
            async with download_dict_lock:
                download_dict[self.uid] = RcloneStatus(
                    RCTransfer, self.message, gid, "up", self.upload_details
                )
            await update_all_messages()
            await RCTransfer.upload(up_path, size)

    def _get_merge_output_path(self):
        output_name = self.merge_output_name or f"Merged_{self.uid}.mkv"
        if not output_name.lower().endswith((".mkv", ".mp4", ".avi", ".mov")):
            output_name += ".mkv"
        return ospath.join(self.dir, output_name)

    async def _do_folder_merge(self, folder_path, name, size, gid):
        # Dispatch based on merge_mode stored in sameDir by the merge module
        merge_mode = (self.sameDir or {}).get("merge_mode", "vv")
        if merge_mode == "va":
            return await self._do_audio_mux(folder_path, name, size, gid)
        if merge_mode == "vs":
            return await self._do_subtitle_embed(folder_path, name, size, gid)
        # Default: vv — concatenate video files (original logic)
        LOGGER.info(f"Starting folder merge [vv]: {folder_path}")
        video_files = await sync_to_async(get_video_files_sorted, folder_path)
        if not video_files:
            await self.onUploadError(
                f"{E.error} 𝐍𝐨 𝐯𝐢𝐝𝐞𝐨 𝐟𝐢𝐥𝐞𝐬 𝐟𝐨𝐮𝐧𝐝 𝐢𝐧 𝐝𝐨𝐰𝐧𝐥𝐨𝐚𝐝𝐞𝐝 𝐟𝐨𝐥𝐝𝐞𝐫!"
            )
            return None
        if len(video_files) == 1:
            LOGGER.info("Only one video, skipping merge — using as-is.")
            return video_files[0]
        output_path = self._get_merge_output_path()
        async with download_dict_lock:
            download_dict[self.uid] = MergeStatus(name, size, gid, self)
        await update_all_messages()
        LOGGER.info(
            f"Merging {len(video_files)} videos → {ospath.basename(output_path)}"
        )
        success = await merge_video_files(video_files, output_path, self)
        if self.suproc == "cancelled":
            return None
        if not success:
            await self.onUploadError(f"{E.error} 𝐌𝐞𝐫𝐠𝐞 𝐅𝐚𝐢𝐥𝐞𝐝! 𝐂𝐡𝐞𝐜𝐤 𝐥𝐨𝐠𝐬.")
            return None
        LOGGER.info(f"Merge done: {output_path}")
        try:
            await clean_target(folder_path)
        except Exception:
            pass
        return output_path

    async def _do_audio_mux(self, folder_path, name, size, gid):
        """Video + Audio mode: FFmpeg mux audio track into video."""
        LOGGER.info(f"Starting audio mux [va]: {folder_path}")
        VIDEO_EXT = {".mp4", ".mkv", ".avi", ".mov", ".flv", ".wmv", ".webm", ".m4v", ".ts"}
        AUDIO_EXT = {".mp3", ".m4a", ".aac", ".flac", ".wav", ".ogg", ".opus", ".ac3", ".eac3"}

        video_file = None
        audio_file = None
        for root, _, files in await sync_to_async(walk, folder_path):
            for f in sorted(files):
                ext = ospath.splitext(f)[1].lower()
                fp = ospath.join(root, f)
                if ext in VIDEO_EXT and video_file is None:
                    video_file = fp
                elif ext in AUDIO_EXT and audio_file is None:
                    audio_file = fp

        if not video_file or not audio_file:
            await self.onUploadError(
                f"{E.error} 𝐕ɪᴅᴇᴏ+𝐀ᴜᴅɪᴏ ᴍᴜx ɴᴇᴇᴅs ᴏɴᴇ ᴠɪᴅᴇᴏ ᴀɴᴅ ᴏɴᴇ ᴀᴜᴅɪᴏ ғɪʟᴇ!"
            )
            return None

        output_path = self._get_merge_output_path()
        async with download_dict_lock:
            download_dict[self.uid] = MergeStatus(name, size, gid, self)
        await update_all_messages()
        LOGGER.info(
            f"Audio mux: video={ospath.basename(video_file)} "
            f"audio={ospath.basename(audio_file)} → {ospath.basename(output_path)}"
        )
        cmd = [
            "ffmpeg", "-y",
            "-i", video_file,
            "-i", audio_file,
            "-map", "0:v:0",
            "-map", "1:a:0",
            "-c:v", "copy",
            "-c:a", "copy",
            "-shortest",
            output_path,
        ]
        self.suproc = await create_subprocess_exec(*cmd, stdout=PIPE, stderr=PIPE)
        _, stderr = await self.suproc.communicate()
        if self.suproc == "cancelled" or self.suproc.returncode == -9:
            return None
        if self.suproc.returncode != 0:
            err_msg = stderr.decode(errors="replace")[-300:]
            await self.onUploadError(f"{E.error} 𝐀ᴜᴅɪᴏ 𝐌ᴜx 𝐅ᴀɪʟᴇᴅ!\n<code>{err_msg}</code>")
            return None
        LOGGER.info(f"Audio mux done: {output_path}")
        try:
            await clean_target(folder_path)
        except Exception:
            pass
        return output_path

    async def _do_subtitle_embed(self, folder_path, name, size, gid):
        """Video + Subtitles mode: FFmpeg embed subtitle stream into video."""
        LOGGER.info(f"Starting subtitle embed [vs]: {folder_path}")
        VIDEO_EXT = {".mp4", ".mkv", ".avi", ".mov", ".flv", ".wmv", ".webm", ".m4v", ".ts"}
        SUB_EXT   = {".srt", ".ass", ".ssa", ".vtt", ".sub"}

        video_file = None
        sub_file   = None
        for root, _, files in await sync_to_async(walk, folder_path):
            for f in sorted(files):
                ext = ospath.splitext(f)[1].lower()
                fp = ospath.join(root, f)
                if ext in VIDEO_EXT and video_file is None:
                    video_file = fp
                elif ext in SUB_EXT and sub_file is None:
                    sub_file = fp

        if not video_file or not sub_file:
            await self.onUploadError(
                f"{E.error} 𝐕ɪᴅᴇᴏ+𝐒ᴜʙs ɴᴇᴇᴅs ᴏɴᴇ ᴠɪᴅᴇᴏ ᴀɴᴅ ᴏɴᴇ sᴜʙᴛɪᴛʟᴇ ғɪʟᴇ!"
            )
            return None

        output_path = self._get_merge_output_path()
        async with download_dict_lock:
            download_dict[self.uid] = MergeStatus(name, size, gid, self)
        await update_all_messages()
        LOGGER.info(
            f"Subtitle embed: video={ospath.basename(video_file)} "
            f"sub={ospath.basename(sub_file)} → {ospath.basename(output_path)}"
        )
        cmd = [
            "ffmpeg", "-y",
            "-i", video_file,
            "-i", sub_file,
            "-map", "0",
            "-map", "1",
            "-c", "copy",
            "-c:s", "copy",
            output_path,
        ]
        self.suproc = await create_subprocess_exec(*cmd, stdout=PIPE, stderr=PIPE)
        _, stderr = await self.suproc.communicate()
        if self.suproc == "cancelled" or self.suproc.returncode == -9:
            return None
        if self.suproc.returncode != 0:
            err_msg = stderr.decode(errors="replace")[-300:]
            await self.onUploadError(f"{E.error} 𝐒ᴜʙᴛɪᴛʟᴇ 𝐄ᴍʙᴇᴅ 𝐅ᴀɪʟᴇᴅ!\n<code>{err_msg}</code>")
            return None
        LOGGER.info(f"Subtitle embed done: {output_path}")
        try:
            await clean_target(folder_path)
        except Exception:
            pass
        return output_path

    async def _do_zip_merge(self, extracted_dir, name, size, gid):
        LOGGER.info(f"Starting ZIP merge from: {extracted_dir}")
        video_files = await sync_to_async(get_video_files_sorted, extracted_dir)
        if not video_files:
            await self.onUploadError(f"{E.error} 𝐍ᴏ 𝐕ɪᴅᴇᴏs 𝐅ᴏᴜɴᴅ 𝐀ꜰᴛᴇʀ 𝐄xᴛʀᴀᴄᴛɪᴏɴ!")
            return None
        if len(video_files) == 1:
            LOGGER.info("Only one video after extract, skipping merge.")
            return video_files[0]

        ep_lines = "\n".join(
            f"  <b>{i}.</b> <code>{ospath.basename(ep)}</code>"
            for i, ep in enumerate(video_files, 1)
        )
        btns = ButtonMaker()
        btns.ibutton(f"{E.get('download', plain=True)} 𝐀ʟʟ 𝐄ᴘɪsᴏᴅᴇs", f"zipep {self.uid} all")
        btns.ibutton(f"{E.get('cancel', plain=True)} 𝐂ᴀɴᴄᴇʟ 𝐌ᴇʀɢᴇ", f"zipep {self.uid} cancel")
        markup = btns.build_menu(2)

        prompt = await sendMessage(
            self.message,
            f"{self.tag}\n"
            f"<b>{E.zip} 𝐙ɪᴘ 𝐌ᴇʀɢᴇ — 𝐄ᴘɪsᴏᴅᴇ 𝐒ᴇʟᴇᴄᴛɪᴏɴ</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"<b>{E.video} 𝐅ᴏᴜɴᴅ {len(video_files)} 𝐕ɪᴅᴇᴏs:</b>\n{ep_lines}\n\n"
            f"<b>{E.note} 𝐒ᴇʟᴇᴄᴛɪᴏɴ 𝐅ᴏʀᴍᴀᴛ:</b>\n"
            f"  • 𝐀ʟʟ    → <code>all</code>\n"
            f"  • 𝐑ᴀɴɢᴇ  → <code>1-5</code>\n"
            f"  • 𝐏ɪᴄᴋ   → <code>1,3,7</code>\n"
            f"  • 𝐒ɪɴɢʟᴇ → <code>4</code>\n\n"
            f"{E.clock} <i>𝐓ʏᴘᴇ ʏᴏᴜʀ sᴇʟᴇᴄᴛɪᴏɴ ᴏʀ ᴜsᴇ ʙᴜᴛᴛᴏɴs ʙᴇʟᴏᴡ — 𝐓ɪᴍᴇᴏᴜᴛ: 120s</i>",
            markup,
        )

        user_id = self.message.from_user.id
        chat_id = self.message.chat.id
        reply_event = Event()
        result_holder = {}

        async def _ep_text_filter(_, __, msg):
            u = msg.from_user or msg.sender_chat
            return bool(
                u
                and getattr(u, "id", None) == user_id
                and msg.chat.id == chat_id
                and msg.text
            )

        async def _ep_text_handler(_, msg):
            result_holder["text"] = msg.text.strip()
            result_holder["msg"] = msg
            result_holder["is_button"] = False
            reply_event.set()

        async def _ep_btn_handler(_, query):
            if query.from_user.id != user_id:
                await query.answer("𝐍𝐨𝐭 𝐘𝐨𝐮𝐫𝐬!", show_alert=True)
                return
            await query.answer()
            result_holder["text"] = query.data.split()[-1]  # "all" or "cancel"
            result_holder["is_button"] = True
            reply_event.set()

        msg_entry = bot.add_handler(
            MessageHandler(_ep_text_handler, filters=pyrogram_create_filter(_ep_text_filter)),
            group=-1,
        )
        btn_entry = bot.add_handler(
            CallbackQueryHandler(
                _ep_btn_handler,
                filters=pyrogram_create_filter(
                    lambda _, __, q: q.data.startswith(f"zipep {self.uid}")
                ),
            ),
            group=-1,
        )

        timed_out = False
        try:
            await wait_for(reply_event.wait(), timeout=120)
        except ATimeoutError:
            LOGGER.info("Episode selection timed out — merging all episodes")
            timed_out = True
        finally:
            bot.remove_handler(*msg_entry)
            bot.remove_handler(*btn_entry)

        try:
            await deleteMessage(prompt)
        except Exception:
            pass

        if timed_out:
            selected_indices = list(range(len(video_files)))
        else:
            if not result_holder.get("is_button"):
                try:
                    await deleteMessage(result_holder.get("msg"))
                except Exception:
                    pass

            raw_text = result_holder.get("text", "all")
            if raw_text == "cancel":
                await self.onUploadError(f"{E.cancel} 𝐌ᴇʀɢᴇ 𝐂ᴀɴᴄᴇʟʟᴇᴅ 𝐁ʏ 𝐔sᴇʀ!")
                return None
            selected_indices = parse_episode_selection(raw_text, len(video_files))
            if selected_indices is None:
                await sendMessage(
                    self.message,
                    f"{E.warning} <b>𝐈ɴᴠᴀʟɪᴅ 𝐒ᴇʟᴇᴄᴛɪᴏɴ</b> — 𝐌ᴇʀɢɪɴɢ ᴀʟʟ ᴇᴘɪsᴏᴅᴇs.",
                )
                selected_indices = list(range(len(video_files)))

        selected_files = [video_files[i] for i in selected_indices]
        LOGGER.info(f"Merging {len(selected_files)} episode(s) → {self.merge_output_name}")
        output_path = self._get_merge_output_path()
        async with download_dict_lock:
            download_dict[self.uid] = MergeStatus(name, size, gid, self)
        await update_all_messages()
        success = await merge_video_files(selected_files, output_path, self)
        if self.suproc == "cancelled":
            return None
        if not success:
            await self.onUploadError(f"{E.error} 𝐌ᴇʀɢᴇ 𝐅ᴀɪʟᴇᴅ! 𝐂ʜᴇᴄᴋ 𝐋ᴏɢs.")
            return None
        LOGGER.info(f"ZIP merge done: {output_path}")
        try:
            await clean_target(extracted_dir)
        except Exception:
            pass
        return output_path

    async def onUploadComplete(
        self, link, size, files, folders, mime_type, name, rclonePath="", private=False
    ):
        if (
            self.isSuperGroup
            and config_dict["INCOMPLETE_TASK_NOTIFIER"]
            and DATABASE_URL
        ):
            await DbManger().rm_complete_task(self.message.link)
        user_id = self.message.from_user.id
        name, _ = await format_filename(name, user_id, isMirror=not self.isLeech)
        user_dict = user_data.get(user_id, {})
        msg = BotTheme(
            "NAME",
            Name=(
                "Task has been Completed!"
                if config_dict["SAFE_MODE"] and self.isSuperGroup
                else escape(name)
            ),
        )
        msg += BotTheme("SIZE", Size=get_readable_file_size(size))
        msg += BotTheme(
            "ELAPSE", Time=get_readable_time(time() - self.message.date.timestamp())
        )
        msg += BotTheme("MODE", Mode=self.upload_details["mode"])
        LOGGER.info(f"Task Done: {name}")

        buttons = ButtonMaker()
        if self.isLeech:
            msg += BotTheme("L_TOTAL_FILES", Files=folders)
            if mime_type != 0:
                msg += BotTheme("L_CORRUPTED_FILES", Corrupt=mime_type)
            msg += BotTheme("L_CC", Tag=self.tag)
            msg += BotTheme("CREDIT")
            btn_added = False

            if not files:
                await sendMessage(self.message, msg, photo=self.random_pic)
            else:
                btn = ButtonMaker()
                saved = False
                if self.source_url and config_dict["SOURCE_LINK"]:
                    btn.ubutton(BotTheme("SOURCE_URL"), self.source_url)
                if self.isSuperGroup:
                    btn = extra_btns(btn)[0]
                message = msg
                btns = btn.build_menu(2)
                buttons = btn
                if self.isSuperGroup and not self.isPM:
                    message += BotTheme("L_LL_MSG")
                elif self.isSuperGroup and self.isPM:
                    message += BotTheme("L_BOT_MSG")
                    buttons.ibutton(
                        BotTheme("CHECK_PM"), f"wzmlx {user_id} botpm", "header",
                        icon_custom_emoji_id=5443127283898405358
                    )
                if config_dict["SAFE_MODE"] and self.isSuperGroup:
                    await sendMessage(
                        self.message,
                        message,
                        buttons.build_menu(2),
                        photo=self.random_pic,
                    )
                _BQ_OPEN  = "\n<blockquote expandable>"
                _BQ_CLOSE = "</blockquote>"
                fmsg = _BQ_OPEN
                for index, (link, name) in enumerate(files.items(), start=1):
                    fmsg += f"{index}. <a href='{link}'>{name}</a>\n"
                    if len(message.encode() + (fmsg + _BQ_CLOSE).encode()) > (
                        4000 if len(config_dict["IMAGES"]) == 0 else 1000
                    ):
                        chunk = fmsg + _BQ_CLOSE
                        if config_dict["SAFE_MODE"]:
                            if self.isSuperGroup:
                                await sendMessage(
                                    self.botpmmsg,
                                    msg + BotTheme("L_LL_MSG") + chunk,
                                    btns,
                                    photo=self.random_pic,
                                )
                            else:
                                await sendMessage(
                                    self.message,
                                    message + chunk,
                                    buttons.build_menu(2),
                                    photo=self.random_pic,
                                )
                        else:
                            if (
                                config_dict["SAVE_MSG"]
                                and not saved
                                and self.isSuperGroup
                            ):
                                saved = True
                                buttons.ibutton(BotTheme("SAVE_MSG"), "save", "footer")
                            await sendMessage(
                                self.message,
                                message + chunk,
                                buttons.build_menu(2),
                                photo=self.random_pic,
                            )
                        await sleep(1.5)
                        fmsg = _BQ_OPEN

                if fmsg != _BQ_OPEN:
                    chunk = fmsg + _BQ_CLOSE
                    if config_dict["SAFE_MODE"]:
                        if self.isSuperGroup:
                            await sendMessage(
                                self.botpmmsg,
                                msg + BotTheme("L_LL_MSG") + chunk,
                                btns,
                                photo=self.random_pic,
                            )
                        else:
                            await sendMessage(
                                self.message,
                                message + chunk,
                                buttons.build_menu(2),
                                photo=self.random_pic,
                            )
                    else:
                        if config_dict["SAVE_MSG"] and not saved and self.isSuperGroup:
                            saved = True
                            buttons.ibutton(BotTheme("SAVE_MSG"), "save", "footer")
                        await sendMessage(
                            self.message,
                            message + chunk,
                            buttons.build_menu(2),
                            photo=self.random_pic,
                        )

            if self.seed:
                if self.newDir:
                    await clean_target(self.newDir)
                async with queue_dict_lock:
                    if self.uid in non_queued_up:
                        non_queued_up.remove(self.uid)
                await start_from_queued()
                return
        else:
            msg += BotTheme("M_TYPE", Mimetype=mime_type)
            if mime_type == "Folder":
                msg += BotTheme("M_SUBFOLD", Folder=folders)
                msg += BotTheme("TOTAL_FILES", Files=files)
            if link or rclonePath and config_dict["RCLONE_SERVE_URL"] and not private:
                if is_DDL := isinstance(link, dict):
                    for dlup, dlink in link.items():
                        buttons.ubutton(BotTheme("DDL_LINK", Serv=dlup), dlink)
                elif link and (
                    user_id == OWNER_ID or not config_dict["DISABLE_DRIVE_LINK"]
                ):
                    buttons.ubutton(BotTheme("CLOUD_LINK"), link)
                else:
                    msg += BotTheme("RCPATH", RCpath=rclonePath)
                if rclonePath and (RCLONE_SERVE_URL := config_dict["RCLONE_SERVE_URL"]):
                    remote, path = rclonePath.split(":", 1)
                    url_path = rutils.quote(f"{path}")
                    share_url = f"{RCLONE_SERVE_URL}/{remote}/{url_path}"
                    if mime_type == "Folder":
                        share_url += "/"
                    buttons.ubutton(BotTheme("RCLONE_LINK"), share_url)
                elif not rclonePath and not is_DDL:
                    INDEX_URL = (
                        self.index_link if self.drive_id else config_dict["INDEX_URL"]
                    )
                    if INDEX_URL:
                        url_path = rutils.quote(f"{name}")
                        share_url = f"{INDEX_URL}/{url_path}"
                        if mime_type == "Folder":
                            share_url += "/"
                            buttons.ubutton(BotTheme("INDEX_LINK_F"), share_url)
                        else:
                            buttons.ubutton(BotTheme("INDEX_LINK_D"), share_url)
                            if mime_type.startswith(("image", "video", "audio")):
                                share_urls = f"{INDEX_URL}/{url_path}?a=view"
                                buttons.ubutton(BotTheme("VIEW_LINK"), share_urls)

            else:
                msg += BotTheme("RCPATH", RCpath=rclonePath)
            msg += BotTheme("M_CC", Tag=self.tag)
            message = msg

            btns = ButtonMaker()
            # <Section : MIRROR LOGS>
            if config_dict["MIRROR_LOG_ID"] and not self.excep_chat:
                m_btns = deepcopy(buttons)
                if self.source_url and config_dict["SOURCE_LINK"]:
                    m_btns.ubutton(BotTheme("SOURCE_URL"), self.source_url)
                if config_dict["SAVE_MSG"]:
                    m_btns.ibutton(BotTheme("SAVE_MSG"), "save", "footer")
                log_msg = list(
                    (
                        await sendMultiMessage(
                            config_dict["MIRROR_LOG_ID"],
                            message,
                            m_btns.build_menu(2),
                            self.random_pic,
                        )
                    ).values()
                )[0]
                if self.linkslogmsg:
                    dispTime = datetime.now(timezone(config_dict["TIMEZONE"])).strftime(
                        "%d/%m/%y, %I:%M:%S %p"
                    )
                    _btns = ButtonMaker()
                    if config_dict["SAVE_MSG"]:
                        _btns.ibutton(BotTheme("SAVE_MSG"), "save", "footer")
                    await editMessage(
                        self.linkslogmsg,
                        (
                            msg
                            + BotTheme(
                                "LINKS_SOURCE", On=dispTime, Source=self.source_msg
                            )
                            + BotTheme("L_LL_MSG")
                            + f"\n\n<a href='{log_msg.link}'>{escape(name)}</a>\n"
                        ),
                        _btns.build_menu(1),
                    )

            # <Section : MESSAGE LOGS>
            if self.isPM and self.isSuperGroup:
                message += BotTheme("M_BOT_MSG")
            buttons = extra_btns(buttons)[0]
            btns = extra_btns(btns)[0]
            if self.isPM:
                if self.isSuperGroup:
                    s_btn = (
                        deepcopy(btns)
                        if config_dict["MIRROR_LOG_ID"]
                        else deepcopy(buttons)
                    )
                    if self.source_url and config_dict["SOURCE_LINK"]:
                        buttons.ubutton(BotTheme("SOURCE_URL"), self.source_url)
                        if not config_dict["SAFE_MODE"]:
                            s_btn.ubutton(BotTheme("SOURCE_URL"), self.source_url)
                    if self.botpmmsg:
                        await sendMessage(
                            self.botpmmsg,
                            message,
                            buttons.build_menu(2),
                            photo=self.random_pic,
                        )
                        if config_dict["SAVE_MSG"]:
                            s_btn.ibutton(BotTheme("SAVE_MSG"), "save", "footer")
                        s_btn.ibutton(
                            BotTheme("CHECK_PM"), f"wzmlx {user_id} botpm", "header"
                        )
                        await sendMessage(
                            self.message,
                            message,
                            s_btn.build_menu(2),
                            photo=self.random_pic,
                        )
                else:
                    if self.source_url and config_dict["SOURCE_LINK"]:
                        buttons.ubutton(BotTheme("SOURCE_URL"), self.source_url)
                    await sendMessage(
                        self.message,
                        message,
                        buttons.build_menu(2),
                        photo=self.random_pic,
                    )
            else:
                if (
                    self.source_url
                    and config_dict["SOURCE_LINK"]
                    and (not self.isSuperGroup or not config_dict["SAFE_MODE"])
                ):
                    buttons.ubutton(BotTheme("SOURCE_URL"), self.source_url)
                if config_dict["SAVE_MSG"] and self.isSuperGroup:
                    buttons.ibutton(BotTheme("SAVE_MSG"), "save", "footer")
                await sendMessage(
                    self.message, message, buttons.build_menu(2), photo=self.random_pic
                )

            if self.seed:
                if self.newDir:
                    await clean_target(self.newDir)
                elif self.compress:
                    await clean_target(f"{self.dir}/{name}")
                async with queue_dict_lock:
                    if self.uid in non_queued_up:
                        non_queued_up.remove(self.uid)
                await start_from_queued()
                return

        if self.botpmmsg and (
            not config_dict["DELETE_LINKS"] or config_dict["CLEAN_LOG_MSG"]
        ):
            await deleteMessage(self.botpmmsg)

        await clean_download(self.dir)
        async with download_dict_lock:
            if self.uid in download_dict.keys():
                del download_dict[self.uid]
            count = len(download_dict)
        if count == 0:
            await self.clean()
        else:
            await update_all_messages()

        async with queue_dict_lock:
            if self.uid in non_queued_up:
                non_queued_up.remove(self.uid)

        await start_from_queued()
        await delete_links(self.message)

    async def onDownloadError(self, error, button=None):
        async with download_dict_lock:
            if self.uid in download_dict.keys():
                del download_dict[self.uid]
            count = len(download_dict)
            if self.sameDir and self.uid in self.sameDir["tasks"]:
                self.sameDir["tasks"].remove(self.uid)
                self.sameDir["total"] -= 1
                # Mark merge batch as failed so waiting tasks abort.
                # Only propagate for true merge batches (merge_mode key present),
                # not for ordinary folder/multi grouped downloads.
                if self.sameDir.get("merge_mode") and not self.sameDir.get("failed"):
                    self.sameDir["failed"] = error
        msg = (
            f"<b>{E.stop} 𝐃𝐨𝐰𝐧𝐥𝐨𝐚𝐝 𝐒𝐭𝐨𝐩𝐩𝐞𝐝!</b>\n"
            f"┠ {E.user} 𝐓𝐚𝐬𝐤 𝐅𝐨𝐫  : {self.tag}\n"
            f"┠ {E.alarm} 𝐑𝐞𝐚𝐬𝐨𝐧    : <i>{escape(error)}</i>\n"
            f"┠ {E.gear} 𝐌𝐨𝐝𝐞      : {self.upload_details['mode']}\n"
            f"┖ {E.timer} 𝐄𝐥𝐚𝐩𝐬𝐞𝐝   : {get_readable_time(time() - self.message.date.timestamp())}"
        )
        await sendMessage(self.message, msg, button)
        if count == 0:
            await self.clean()
        else:
            await update_all_messages()

        if (
            self.isSuperGroup
            and config_dict["INCOMPLETE_TASK_NOTIFIER"]
            and DATABASE_URL
        ):
            await DbManger().rm_complete_task(self.message.link)

        async with queue_dict_lock:
            if self.uid in queued_dl:
                queued_dl[self.uid].set()
                del queued_dl[self.uid]
            if self.uid in queued_up:
                queued_up[self.uid].set()
                del queued_up[self.uid]
            if self.uid in non_queued_dl:
                non_queued_dl.remove(self.uid)
            if self.uid in non_queued_up:
                non_queued_up.remove(self.uid)

        await start_from_queued()
        await sleep(3)
        await clean_download(self.dir)
        if self.newDir:
            await clean_download(self.newDir)

    async def onUploadError(self, error):
        async with download_dict_lock:
            if self.uid in download_dict.keys():
                del download_dict[self.uid]
            count = len(download_dict)
        msg = (
            f"<b>{E.warning} 𝐓𝐚𝐬𝐤 𝐒𝐭𝐨𝐩𝐩𝐞𝐝!</b>\n"
            f"┠ {E.user} 𝐓𝐚𝐬𝐤 𝐅𝐨𝐫  : {self.tag}\n"
            f"┠ {E.alarm} 𝐑𝐞𝐚𝐬𝐨𝐧    : <i>{escape(error)}</i>\n"
            f"┠ {E.gear} 𝐌𝐨𝐝𝐞      : {self.upload_details['mode']}\n"
            f"┖ {E.timer} 𝐄𝐥𝐚𝐩𝐬𝐞𝐝   : {get_readable_time(time() - self.message.date.timestamp())}"
        )
        await sendMessage(self.message, msg)
        if count == 0:
            await self.clean()
        else:
            await update_all_messages()

        if (
            self.isSuperGroup
            and config_dict["INCOMPLETE_TASK_NOTIFIER"]
            and DATABASE_URL
        ):
            await DbManger().rm_complete_task(self.message.link)

        async with queue_dict_lock:
            if self.uid in queued_dl:
                queued_dl[self.uid].set()
                del queued_dl[self.uid]
            if self.uid in queued_up:
                queued_up[self.uid].set()
                del queued_up[self.uid]
            if self.uid in non_queued_dl:
                non_queued_dl.remove(self.uid)
            if self.uid in non_queued_up:
                non_queued_up.remove(self.uid)

        await start_from_queued()
        await sleep(3)
        await clean_download(self.dir)
        if self.newDir:
            await clean_download(self.newDir)
