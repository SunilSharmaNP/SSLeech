#!/usr/bin/env python3
from os import walk, path as ospath
from aiofiles.os import remove as aioremove, path as aiopath, listdir, rmdir, makedirs
from aioshutil import rmtree as aiormtree, move
from asyncio import create_subprocess_exec, gather as asyncio_gather
from asyncio.subprocess import PIPE
from time import time as _time
from shutil import rmtree, disk_usage
from magic import Magic
from re import split as re_split, I, search as re_search
from subprocess import run as srun
from sys import exit as sexit
from bot import bot_cache, threads

from .exceptions import NotSupportedExtractionArchive


from bot import aria2, LOGGER, DOWNLOAD_DIR, get_client, GLOBAL_EXTENSION_FILTER, BinConfig, DISABLE_TORRENTS
from bot.helper.ext_utils.bot_utils import sync_to_async, cmd_exec


class MetaProgress:
    """Live progress tracker attached to listener.meta_progress during metadata edit."""
    __slots__ = ("progress_raw", "speed_raw", "processed_bytes", "eta_raw")

    def __init__(self):
        self.progress_raw: float = 0.0
        self.speed_raw: int = 0
        self.processed_bytes: int = 0
        self.eta_raw: float = 0.0

ARCH_EXT = [
    ".tar.bz2",
    ".tar.gz",
    ".bz2",
    ".gz",
    ".tar.xz",
    ".tar",
    ".tbz2",
    ".tgz",
    ".lzma2",
    ".zip",
    ".7z",
    ".z",
    ".rar",
    ".iso",
    ".wim",
    ".cab",
    ".apm",
    ".arj",
    ".chm",
    ".cpio",
    ".cramfs",
    ".deb",
    ".dmg",
    ".fat",
    ".hfs",
    ".lzh",
    ".lzma",
    ".mbr",
    ".msi",
    ".mslz",
    ".nsis",
    ".ntfs",
    ".rpm",
    ".squashfs",
    ".udf",
    ".vhd",
    ".xar",
]

FIRST_SPLIT_REGEX = r"(\.|_)part0*1\.rar$|(\.|_)7z\.0*1$|(\.|_)zip\.0*1$|^(?!.*(\.|_)part\d+\.rar$).*\.rar$"

SPLIT_REGEX = r"\.r\d+$|\.7z\.\d+$|\.z\d+$|\.zip\.\d+$"


def is_first_archive_split(file):
    return bool(re_search(FIRST_SPLIT_REGEX, file))


def is_archive(file):
    return file.endswith(tuple(ARCH_EXT))


def is_archive_split(file):
    return bool(re_search(SPLIT_REGEX, file))


async def clean_target(path):
    if await aiopath.exists(path):
        LOGGER.info(f"Cleaning Target: {path}")
        if await aiopath.isdir(path):
            try:
                await aiormtree(path)
            except Exception:
                pass
        elif await aiopath.isfile(path):
            try:
                await aioremove(path)
            except Exception:
                pass


async def clean_download(path):
    if await aiopath.exists(path):
        LOGGER.info(f"Cleaning Download: {path}")
        try:
            await aiormtree(path)
        except Exception:
            pass


async def start_cleanup():
    if not DISABLE_TORRENTS:
        try:
            get_client().torrents_delete(torrent_hashes="all")
        except Exception:
            pass
        try:
            aria2.remove_all(True)
        except Exception:
            pass
    try:
        await aiormtree(DOWNLOAD_DIR)
    except Exception:
        pass
    await makedirs(DOWNLOAD_DIR, exist_ok=True)


def clean_all():
    if not DISABLE_TORRENTS:
        try:
            aria2.remove_all(True)
        except Exception:
            pass
        try:
            get_client().torrents_delete(torrent_hashes="all")
        except Exception:
            pass
    try:
        rmtree(DOWNLOAD_DIR)
    except Exception:
        pass


def exit_clean_up(signal, frame):
    try:
        LOGGER.info("Please wait, while we clean up and stop the running downloads")
        clean_all()
        srun(["pkill", "-9", "-f", f"gunicorn|{BinConfig.ARIA2_NAME}|{BinConfig.QBIT_NAME}|{BinConfig.FFMPEG_NAME}"])
        sexit(0)
    except KeyboardInterrupt:
        LOGGER.warning("Force Exiting before the cleanup finishes!")
        sexit(1)


async def clean_unwanted(path):
    LOGGER.info(f"Cleaning unwanted files/folders: {path}")
    for dirpath, _, files in await sync_to_async(walk, path, topdown=False):
        for filee in files:
            if (
                filee.endswith(".!qB")
                or filee.endswith(".parts")
                and filee.startswith(".")
            ):
                await aioremove(ospath.join(dirpath, filee))
        if dirpath.endswith((".unwanted", "splited_files_mltb", "copied_mltb")):
            await aiormtree(dirpath)
    for dirpath, _, files in await sync_to_async(walk, path, topdown=False):
        if not await listdir(dirpath):
            await rmdir(dirpath)


async def get_path_size(path):
    if await aiopath.isfile(path):
        return await aiopath.getsize(path)
    total_size = 0
    for root, dirs, files in await sync_to_async(walk, path):
        for f in files:
            abs_path = ospath.join(root, f)
            total_size += await aiopath.getsize(abs_path)
    return total_size


async def count_files_and_folders(path):
    total_files = 0
    total_folders = 0
    for _, dirs, files in await sync_to_async(walk, path):
        total_files += len(files)
        for f in files:
            if f.endswith(tuple(GLOBAL_EXTENSION_FILTER)):
                total_files -= 1
        total_folders += len(dirs)
    return total_folders, total_files


def get_base_name(orig_path):
    extension = next((ext for ext in ARCH_EXT if orig_path.lower().endswith(ext)), "")
    if extension != "":
        return re_split(f"{extension}$", orig_path, maxsplit=1, flags=I)[0]
    else:
        raise NotSupportedExtractionArchive("File format not supported for extraction")


def get_mime_type(file_path):
    mime = Magic(mime=True)
    mime_type = mime.from_file(file_path)
    mime_type = mime_type or "text/plain"
    return mime_type


def check_storage_threshold(size, threshold, arch=False, alloc=False):
    free = disk_usage(DOWNLOAD_DIR).free
    if not alloc:
        if (
            not arch
            and free - size < threshold
            or arch
            and free - (size * 2) < threshold
        ):
            return False
    elif not arch:
        if free < threshold:
            return False
    elif free - size < threshold:
        return False
    return True


async def join_files(path):
    files = await listdir(path)
    results = []
    for file_ in files:
        if (
            re_search(r"\.0+2$", file_)
            and await sync_to_async(get_mime_type, f"{path}/{file_}")
            == "application/octet-stream"
        ):
            final_name = file_.rsplit(".", 1)[0]
            cmd = f"cat {path}/{final_name}.* > {path}/{final_name}"
            _, stderr, code = await cmd_exec(cmd, True)
            if code != 0:
                LOGGER.error(f"Failed to join {final_name}, stderr: {stderr}")
            else:
                results.append(final_name)
        else:
            LOGGER.warning("No Binary files to join!")
    if results:
        LOGGER.info("Join Completed!")
        for res in results:
            for file_ in files:
                if re_search(rf"{res}\.0[0-9]+$", file_):
                    await aioremove(f"{path}/{file_}")


async def edit_metadata(
    listener, base_dir: str, media_file: str, outfile: str, metadata: str = ""
):
    """Edit file metadata using ffmpeg.

    Progress is tracked via listener.meta_progress (MetaProgress instance).
    """
    from bot.helper.ext_utils.leech_utils import get_media_info

    total_dur, *_ = await get_media_info(media_file)
    total_dur = float(total_dur or 0)

    cmd = [
        bot_cache["pkgs"][2],
        "-hide_banner",
        "-loglevel", "error",
        "-threads", str(threads),
        "-ignore_unknown",
        "-i", media_file,
        "-metadata", f"title={metadata}",
        "-metadata:s:v", f"title={metadata}",
        "-metadata", "Comment=",
        "-metadata", "Copyright=",
        "-metadata", f"AUTHOR=Zyradaex",
        "-metadata", "Encoded by=",
        "-metadata", "SYNOPSIS=",
        "-metadata", "ARTIST=",
        "-metadata", "PURL=",
        "-metadata", "Encoded_by=",
        "-metadata", "Description=",
        "-metadata", "description=",
        "-metadata", "SUMMARY=",
        "-metadata", "WEBSITE=",
        "-metadata:s:a", f"title={metadata}",
        "-metadata:s:s", f"title={metadata}",
        "-map", "0:v:0?",
        "-map", "0:a:?",
        "-map", "0:s:?",
        "-c:v", "copy",
        "-c:a", "copy",
        "-c:s", "copy",
        "-progress", "pipe:1",
        outfile,
        "-y",
    ]

    mp: MetaProgress | None = getattr(listener, "meta_progress", None)
    t0 = _time()

    proc = await create_subprocess_exec(*cmd, stdout=PIPE, stderr=PIPE)
    listener.suproc = proc

    async def _track_progress():
        async for raw in proc.stdout:
            if mp is None:
                continue
            line = raw.decode().strip()
            k, _, v = line.partition("=")
            k, v = k.strip(), v.strip()
            if not k or not v:
                continue
            if k == "out_time_ms" and total_dur > 0:
                try:
                    elapsed_media = int(v) / 1_000_000
                    mp.progress_raw = min(elapsed_media / total_dur * 100, 100)
                    wall = _time() - t0
                    if wall > 0 and elapsed_media > 0:
                        mp.eta_raw = max(0.0, (total_dur - elapsed_media) / (elapsed_media / wall))
                except Exception:
                    pass
            elif k == "total_size":
                try:
                    mp.processed_bytes = max(int(v), 0)
                    wall = _time() - t0
                    if wall > 0:
                        mp.speed_raw = int(mp.processed_bytes / wall)
                except Exception:
                    pass

    await asyncio_gather(proc.wait(), _track_progress())
    code = proc.returncode

    if code == 0:
        listener.seed = False
        await clean_target(media_file)
        await move(outfile, base_dir)
    else:
        await clean_target(outfile)
        stderr_out = b""
        try:
            stderr_out = await proc.stderr.read()
        except Exception:
            pass
        LOGGER.error(
            "%s. Changing metadata failed, Path %s",
            stderr_out.decode().strip(),
            media_file,
        )
