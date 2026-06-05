#!/usr/bin/env python3

from bot import LOGGER
from bot.helper.ext_utils.bot_utils import (
    EngineStatus,
    get_readable_file_size,
    get_readable_time,
    MirrorStatus,
)


class MetadataStatus:
    def __init__(self, name, size, gid, listener):
        self.__name = name
        self.__gid = gid
        self.__size = size
        self.__listener = listener
        self.upload_details = listener.upload_details
        self.message = listener.message

    def gid(self):
        return self.__gid

    def progress(self):
        try:
            mp = getattr(self.__listener, "meta_progress", None)
            if mp is not None and mp.progress_raw > 0:
                return f"{round(mp.progress_raw, 2)}%"
        except Exception:
            pass
        return "0%"

    def speed(self):
        try:
            mp = getattr(self.__listener, "meta_progress", None)
            if mp is not None and mp.speed_raw > 0:
                return f"{get_readable_file_size(mp.speed_raw)}/s"
        except Exception:
            pass
        return "0 B/s"

    def processed_bytes(self):
        try:
            mp = getattr(self.__listener, "meta_progress", None)
            if mp is not None and mp.processed_bytes > 0:
                return get_readable_file_size(mp.processed_bytes)
        except Exception:
            pass
        return "0 B"

    def name(self):
        return self.__name

    def size(self):
        return get_readable_file_size(self.__size)

    def eta(self):
        try:
            mp = getattr(self.__listener, "meta_progress", None)
            if mp is not None and mp.eta_raw > 0:
                return get_readable_time(mp.eta_raw)
        except Exception:
            pass
        return "-"

    def status(self):
        return MirrorStatus.STATUS_METADATA

    def download(self):
        return self

    async def cancel_download(self):
        LOGGER.info(f"Cancelling metadata edit: {self.__name}")
        if self.__listener.suproc is not None:
            try:
                self.__listener.suproc.kill()
            except Exception:
                pass
        self.__listener.suproc = "cancelled"
        await self.__listener.onUploadError("Metadata edit stopped by user!")

    def eng(self):
        return EngineStatus().STATUS_SPLIT_MERGE
