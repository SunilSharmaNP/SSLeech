#!/usr/bin/env python3
from logging import getLogger, ERROR
from time import time
from os import (
    open as osopen,
    close as osclose,
    O_CREAT,
    O_WRONLY,
    pwrite,
    ftruncate,
    makedirs,
)
from os.path import dirname
from asyncio import Lock, gather, to_thread
from pyrogram import Client
from aiohttp import ClientSession, ClientTimeout

from bot import (
    LOGGER,
    download_dict,
    download_dict_lock,
    non_queued_dl,
    queue_dict_lock,
    bot,
    user,
    IS_PREMIUM_USER,
    FAST_TG_DOWNLOAD,
)
from bot.helper.mirror_utils.download_utils.tg_stream_server import (
    register_stream,
    unregister_stream,
)
from bot.helper.mirror_utils.status_utils.telegram_status import TelegramStatus
from bot.helper.mirror_utils.status_utils.queue_status import QueueStatus
from bot.helper.telegram_helper.message_utils import (
    sendStatusMessage,
    sendMessage,
    delete_links,
)
from bot.helper.ext_utils.task_manager import (
    is_queued,
    limit_checker,
    stop_duplicate_check,
)

global_lock = Lock()
GLOBAL_GID = set()
getLogger("pyrogram").setLevel(ERROR)


class TelegramDownloadHelper:

    def __init__(self, listener):
        self.name = ""
        self.__processed_bytes = 0
        self.__start_time = time()
        self.__listener = listener
        self.__client = bot
        self.__decrypter = None
        self.__id = ""
        self.__is_cancelled = False

    @property
    def speed(self):
        return self.__processed_bytes / (time() - self.__start_time)

    @property
    def processed_bytes(self):
        return self.__processed_bytes

    async def __onDownloadStart(self, name, size, file_id, from_queue):
        async with global_lock:
            GLOBAL_GID.add(file_id)
        self.name = name
        self.__id = file_id
        async with download_dict_lock:
            download_dict[self.__listener.uid] = TelegramStatus(
                self,
                size,
                self.__listener.message,
                file_id[:12],
                "dl",
                self.__listener.upload_details,
            )
        async with queue_dict_lock:
            non_queued_dl.add(self.__listener.uid)
        if not from_queue:
            await self.__listener.onDownloadStart()
            await sendStatusMessage(self.__listener.message)
            LOGGER.info(f"Download from Telegram: {name}")
        else:
            LOGGER.info(f"Start Queued Download from Telegram: {name}")

    async def __onDownloadProgress(self, current, total):
        if self.__is_cancelled:
            self.__client.stop_transmission()
        self.__processed_bytes = current

    async def __onDownloadError(self, error):
        async with global_lock:
            try:
                GLOBAL_GID.remove(self.__id)
            except Exception:
                pass
        await self.__listener.onDownloadError(error)

    async def __onDownloadComplete(self):
        await self.__listener.onDownloadComplete()
        async with global_lock:
            GLOBAL_GID.remove(self.__id)

    async def __fast_stream_download(self, message, path):
        """Convert the message's media into a local, loopback-only HTTP
        direct link (see tg_stream_server.py, adapted from fyaz05/FileToLink)
        and pull it with several concurrent byte-range requests instead of
        one serial Pyrogram download_media() stream. Falls back to the
        caller on any error so the classic path always still works."""
        info = register_stream(message, client=self.__client)
        url = info["url"]
        file_size = info["file_size"]

        target_path = path
        if target_path.endswith("/"):
            target_path = target_path + info["file_name"]

        # 1 connection per ~4MB of file, capped between 1 and 16.
        num_conn = max(1, min(16, file_size // (4 * 1024 * 1024) or 1))
        part = file_size // num_conn

        parent_dir = dirname(target_path)
        if parent_dir:
            makedirs(parent_dir, exist_ok=True)
        fd = osopen(target_path, O_CREAT | O_WRONLY)
        progress_lock = Lock()

        async def fetch_range(start, end):
            timeout = ClientTimeout(total=None, sock_connect=30, sock_read=120)
            async with ClientSession(timeout=timeout) as session:
                async with session.get(
                    url, headers={"Range": f"bytes={start}-{end}"}
                ) as resp:
                    if resp.status not in (200, 206):
                        raise RuntimeError(
                            f"local stream server returned status {resp.status}"
                        )
                    offset = start
                    async for chunk in resp.content.iter_chunked(256 * 1024):
                        if self.__is_cancelled:
                            raise RuntimeError("Cancelled by user!")
                        await to_thread(pwrite, fd, chunk, offset)
                        offset += len(chunk)
                        async with progress_lock:
                            self.__processed_bytes += len(chunk)

        try:
            ftruncate(fd, file_size)
            ranges = []
            pos = 0
            for i in range(num_conn):
                start = pos
                end = file_size - 1 if i == num_conn - 1 else pos + part - 1
                ranges.append((start, end))
                pos = end + 1
            await gather(*(fetch_range(s, e) for s, e in ranges))
        finally:
            osclose(fd)
            unregister_stream(url)
        return target_path

    async def __download(self, message, path):
        try:
            if self.__client is None and self.__decrypter is not None:
                try:
                    async with Client(
                        str(self.__listener.user_id),
                        session_string=self.__decrypter.decrypt(
                            self.__listener.user_dict.get("usess")
                        ).decode(),
                        in_memory=True,
                        no_updates=True,
                    ) as self.__client:
                        download = await self.__client.download_media(
                            message=message,
                            file_name=path,
                            progress=self.__onDownloadProgress,
                        )
                except Exception as e:
                    if not self.__is_cancelled:
                        await self.__onDownloadError(f"ERROR: {e}")
                        return
            elif FAST_TG_DOWNLOAD:
                try:
                    download = await self.__fast_stream_download(message, path)
                except Exception as e:
                    if self.__is_cancelled:
                        await self.__onDownloadError("Cancelled by user!")
                        return
                    LOGGER.warning(
                        f"Fast TG-to-link download failed ({e}), falling back to direct download_media()"
                    )
                    download = await self.__client.download_media(
                        message=message, file_name=path, progress=self.__onDownloadProgress
                    )
            else:
                download = await self.__client.download_media(
                    message=message, file_name=path, progress=self.__onDownloadProgress
                )
            if self.__is_cancelled:
                await self.__onDownloadError("Cancelled by user!")
                return
        except Exception as e:
            LOGGER.error(str(e))
            await self.__onDownloadError(str(e))
            return
        if download is not None:
            await self.__onDownloadComplete()
        elif not self.__is_cancelled:
            await self.__onDownloadError("Internal Error occurred")

    async def add_download(self, message, path, filename, session, decrypter):
        if session == "user":
            self.__client = user
            if not self.__listener.isSuperGroup:
                await sendMessage(
                    message, "Use SuperGroup to download this Link with User!"
                )
                return
        elif session == "user_sess":
            self.__client = None
            self.__decrypter = decrypter

        media = getattr(message, message.media.value) if message.media else None

        if media is not None:
            async with global_lock:
                download = media.file_unique_id not in GLOBAL_GID

            if download:
                if filename == "":
                    name = media.file_name if hasattr(media, "file_name") else "None"
                else:
                    name = filename
                    path = path + name
                size = media.file_size
                gid = media.file_unique_id

                msg, button = await stop_duplicate_check(name, self.__listener)
                if msg:
                    await sendMessage(self.__listener.message, msg, button)
                    await delete_links(self.__listener.message)
                    return
                if limit_exceeded := await limit_checker(size, self.__listener):
                    await sendMessage(self.__listener.message, limit_exceeded)
                    await delete_links(self.__listener.message)
                    return
                added_to_queue, event = await is_queued(self.__listener.uid)
                if added_to_queue:
                    LOGGER.info(f"Added to Queue/Download: {name}")
                    async with download_dict_lock:
                        download_dict[self.__listener.uid] = QueueStatus(
                            name, size, gid, self.__listener, "dl"
                        )
                    await self.__listener.onDownloadStart()
                    await sendStatusMessage(self.__listener.message)
                    await event.wait()
                    async with download_dict_lock:
                        if self.__listener.uid not in download_dict:
                            return
                    from_queue = True
                else:
                    from_queue = False
                await self.__onDownloadStart(name, size, gid, from_queue)
                await self.__download(message, path)
            else:
                await self.__onDownloadError("File already being downloaded!")
        else:
            await self.__onDownloadError("No valid media type in the replied message")

    async def cancel_download(self):
        self.__is_cancelled = True
        LOGGER.info(
            f"Cancelling download via User: [ Name: {self.name} ID: {self.__id} ]"
        )
