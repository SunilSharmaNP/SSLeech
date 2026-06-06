#!/usr/bin/env python3
from bot import LOGGER
from bot.helper.ext_utils.bot_utils import (
    EngineStatus,
    get_readable_file_size,
    get_readable_time,
    MirrorStatus,
)


class SplitStatus:
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
            total = getattr(self.__listener, "split_current_total", 0)
            done = getattr(self.__listener, "split_current_done", 0)
            if total > 0 and done > 0:
                return f"{round(done / total * 100, 2)}%"
        except Exception:
            pass
        return "0%"

    def speed(self):
        try:
            done = getattr(self.__listener, "split_current_done", 0)
            elapsed = getattr(self.__listener, "split_elapsed", 1)
            if done > 0 and elapsed > 0:
                return f"{get_readable_file_size(int(done / elapsed))}/s"
        except Exception:
            pass
        return "0 B/s"

    def processed_bytes(self):
        try:
            done = getattr(self.__listener, "split_current_done", 0)
            if done > 0:
                return get_readable_file_size(done)
        except Exception:
            pass
        return "0 B"

    def name(self):
        return self.__name

    def size(self):
        return get_readable_file_size(self.__size)

    def eta(self):
        try:
            total = getattr(self.__listener, "split_current_total", 0)
            done = getattr(self.__listener, "split_current_done", 0)
            elapsed = getattr(self.__listener, "split_elapsed", 1)
            if done > 0 and elapsed > 0 and total > done:
                speed = done / elapsed
                return get_readable_time((total - done) / speed)
        except Exception:
            pass
        return "-"

    def status(self):
        return MirrorStatus.STATUS_SPLITTING

    def download(self):
        return self

    async def cancel_download(self):
        LOGGER.info(f"Cancelling Split: {self.__name}")
        if self.__listener.suproc is not None:
            self.__listener.suproc.kill()
        else:
            self.__listener.suproc = "cancelled"
        await self.__listener.onUploadError("splitting stopped by user!")

    def eng(self):
        return EngineStatus().STATUS_SPLIT_MERGE
