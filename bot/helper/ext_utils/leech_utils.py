from hashlib import md5
from time import strftime, gmtime, time
from re import sub as re_sub, search as re_search, compile as re_compile, IGNORECASE
from shlex import split as ssplit
from natsort import natsorted
from os import path as ospath
from aiofiles.os import remove as aioremove, path as aiopath, mkdir, makedirs, listdir
from aioshutil import rmtree as aiormtree
from contextlib import suppress
from asyncio import create_subprocess_exec, create_task, gather, Semaphore, wait_for, TimeoutError as AsyncTimeoutError, sleep as asyncio_sleep, CancelledError
from asyncio.subprocess import PIPE
from telegraph import upload_file
from langcodes import Language
from time import time as _time

from bot import LOGGER, MAX_SPLIT_SIZE, config_dict, user_data, threads
from bot.modules.mediainfo import parseinfo
from bot.helper.ext_utils.bot_utils import (
    cmd_exec,
    sync_to_async,
    get_readable_file_size,
    get_readable_time,
)
from bot.helper.ext_utils.fs_utils import ARCH_EXT, get_mime_type
from bot.helper.ext_utils.telegraph_helper import telegraph
from bot import BinConfig


async def is_multi_streams(path):
    try:
        result = await cmd_exec(
            [
                "ffprobe",
                "-hide_banner",
                "-loglevel",
                "error",
                "-print_format",
                "json",
                "-show_streams",
                path,
            ]
        )
        if res := result[1]:
            LOGGER.warning(f"Get Video Streams: {res}")
    except Exception as e:
        LOGGER.error(f"Get Video Streams: {e}. Mostly File not found!")
        return False
    fields = eval(result[0]).get("streams")
    if fields is None:
        LOGGER.error(f"get_video_streams: {result}")
        return False
    videos = 0
    audios = 0
    for stream in fields:
        if stream.get("codec_type") == "video":
            videos += 1
        elif stream.get("codec_type") == "audio":
            audios += 1
    return videos > 1 or audios > 1


async def get_media_info(path, metadata=False):
    try:
        result = await cmd_exec(
            [
                "ffprobe",
                "-hide_banner",
                "-loglevel",
                "error",
                "-print_format",
                "json",
                "-show_format",
                "-show_streams",
                path,
            ]
        )
        if res := result[1]:
            LOGGER.warning(f"Media Info FF: {res}")
    except Exception as e:
        LOGGER.error(f"Media Info: {e}. Mostly File not found!")
        return (0, "", "", "") if metadata else (0, None, None)
    ffresult = eval(result[0])
    fields = ffresult.get("format")
    if fields is None:
        LOGGER.error(f"Media Info Sections: {result}")
        return (0, "", "", "") if metadata else (0, None, None)
    duration = round(float(fields.get("duration", 0)))
    if metadata:
        lang, qual, stitles = "", "", ""
        if (streams := ffresult.get("streams")) and streams[0].get(
            "codec_type"
        ) == "video":
            qual = int(streams[0].get("height"))
            qual = f"{480 if qual <= 480 else 540 if qual <= 540 else 720 if qual <= 720 else 1080 if qual <= 1080 else 2160 if qual <= 2160 else 4320 if qual <= 4320 else 8640}p"
            for stream in streams:
                if stream.get("codec_type") == "audio" and (
                    lc := stream.get("tags", {}).get("language")
                ):
                    with suppress(Exception):
                        lc = Language.get(lc).display_name()
                    if lc not in lang:
                        lang += f"{lc}, "
                if stream.get("codec_type") == "subtitle" and (
                    st := stream.get("tags", {}).get("language")
                ):
                    with suppress(Exception):
                        st = Language.get(st).display_name()
                    if st not in stitles:
                        stitles += f"{st}, "
        return duration, qual, lang[:-2], stitles[:-2]
    tags = fields.get("tags", {})
    artist = tags.get("artist") or tags.get("ARTIST") or tags.get("Artist")
    title = tags.get("title") or tags.get("TITLE") or tags.get("Title")
    return duration, artist, title


async def get_document_type(path):
    is_video, is_audio, is_image = False, False, False
    if path.endswith(tuple(ARCH_EXT)) or re_search(
        r".+(\.|_)(rar|7z|zip|bin)(\.0*\d+)?$", path
    ):
        return is_video, is_audio, is_image
    mime_type = await sync_to_async(get_mime_type, path)
    if mime_type.startswith("audio"):
        return False, True, False
    if mime_type.startswith("image"):
        return False, False, True
    if not mime_type.startswith("video") and not mime_type.endswith("octet-stream"):
        return is_video, is_audio, is_image
    try:
        result = await cmd_exec(
            [
                "ffprobe",
                "-hide_banner",
                "-loglevel",
                "error",
                "-print_format",
                "json",
                "-show_streams",
                path,
            ]
        )
        if res := result[1]:
            LOGGER.warning(f"Get Document Type: {res}")
    except Exception as e:
        LOGGER.error(f"Get Document Type: {e}. Mostly File not found!")
        return is_video, is_audio, is_image
    fields = eval(result[0]).get("streams")
    if fields is None:
        LOGGER.error(f"get_document_type: {result}")
        return is_video, is_audio, is_image
    for stream in fields:
        if stream.get("codec_type") == "video":
            is_video = True
        elif stream.get("codec_type") == "audio":
            is_audio = True
    return is_video, is_audio, is_image


async def get_audio_thumb(audio_file):
    des_dir = "Thumbnails"
    if not await aiopath.exists(des_dir):
        await mkdir(des_dir)
    des_dir = ospath.join(des_dir, f"{time()}.jpg")
    cmd = [
        BinConfig.FFMPEG_NAME,
        "-hide_banner",
        "-loglevel",
        "error",
        "-threads",
        str(threads),
        "-i",
        audio_file,
        "-an",
        "-vcodec",
        "copy",
        des_dir,
    ]
    try:
        status = await create_subprocess_exec(*cmd, stderr=PIPE)
    except FileNotFoundError:
        LOGGER.error(
            f"Audio thumb failed: binary '{BinConfig.FFMPEG_NAME}' not found. "
            f"Check Dockerfile symlink. Name: {audio_file}"
        )
        return None
    await status.wait()
    if status.returncode != 0 or not await aiopath.exists(des_dir):
        err = (await status.stderr.read()).decode().strip()
        LOGGER.error(
            f"Error while extracting thumbnail from audio. Name: {audio_file} stderr: {err}"
        )
        return None
    return des_dir


async def take_ss(video_file, duration=None, total=1, gen_ss=False):
    des_dir = ospath.join("Thumbnails", f"{time()}")
    await makedirs(des_dir, exist_ok=True)
    if duration is None:
        duration = (await get_media_info(video_file))[0]
    if duration == 0:
        duration = 3
    duration = duration - (duration * 2 / 100)
    cmd = [
        BinConfig.FFMPEG_NAME,
        "-hide_banner",
        "-loglevel",
        "error",
        "-threads",
        str(threads),
        "-ss",
        "",
        "-i",
        video_file,
        "-vf",
        "thumbnail",
        "-frames:v",
        "1",
        des_dir,
    ]
    tstamps = {}
    thumb_sem = Semaphore(3)

    async def extract_ss(eq_thumb):
        async with thumb_sem:
            # cmd[7] is the -ss value (seek time). cmd[5] is -threads — do NOT overwrite it.
            cmd[7] = str((duration // total) * eq_thumb)
            tstamps[f"wz_thumb_{eq_thumb}.jpg"] = strftime(
                "%H:%M:%S", gmtime(float(cmd[7]))
            )
            cmd[-1] = ospath.join(des_dir, f"wz_thumb_{eq_thumb}.jpg")
            task = await create_subprocess_exec(*cmd, stderr=PIPE)
            return (task, await task.wait(), eq_thumb)

    tasks = [extract_ss(eq_thumb) for eq_thumb in range(1, total + 1)]
    try:
        status = await gather(*tasks)
    except FileNotFoundError:
        LOGGER.error(
            f"take_ss failed: binary '{BinConfig.FFMPEG_NAME}' not found. "
            f"Check Dockerfile symlink — likely 'ln -sf /usr/bin/ffmpeg' path is wrong. "
            f"File: {video_file}"
        )
        await aiormtree(des_dir)
        return None
    except Exception as e:
        LOGGER.error(f"take_ss unexpected error: {e}. File: {video_file}")
        await aiormtree(des_dir)
        return None

    for task, rtype, eq_thumb in status:
        if rtype != 0 or not await aiopath.exists(
            ospath.join(des_dir, f"wz_thumb_{eq_thumb}.jpg")
        ):
            err = (await task.stderr.read()).decode().strip()
            LOGGER.error(
                f"Error while extracting thumbnail no. {eq_thumb} from video. Name: {video_file} stderr: {err}"
            )
            await aiormtree(des_dir)
            return None
    return (des_dir, tstamps) if gen_ss else ospath.join(des_dir, "wz_thumb_1.jpg")


async def split_file(
    path,
    size,
    file_,
    dirpath,
    split_size,
    listener,
    start_time=0,
    i=1,
    inLoop=False,
    multi_streams=True,
):
    if (
        listener.suproc == "cancelled"
        or listener.suproc is not None
        and listener.suproc.returncode == -9
    ):
        return False
    if listener.seed and not listener.newDir:
        dirpath = f"{dirpath}/splited_files_mltb"
        if not await aiopath.exists(dirpath):
            await mkdir(dirpath)
    user_id = listener.message.from_user.id
    user_dict = user_data.get(user_id, {})
    leech_split_size = user_dict.get("split_size") or config_dict["LEECH_SPLIT_SIZE"]
    parts = -(-size // leech_split_size)
    if (
        user_dict.get("equal_splits")
        or config_dict["EQUAL_SPLITS"]
        and "equal_splits" not in user_dict
    ) and not inLoop:
        split_size = ((size + parts - 1) // parts) + 1000

    split_size -= 5000000

    if (await get_document_type(path))[0]:
        if multi_streams:
            multi_streams = await is_multi_streams(path)
        duration = (await get_media_info(path))[0]
        base_name, extension = ospath.splitext(file_)

        # Cumulative bytes of all successfully written parts (for overall progress)
        completed_bytes = 0

        while i <= parts or start_time < duration - 4:
            parted_name = f"{base_name}.part{i:03}{extension}"
            out_path = ospath.join(dirpath, parted_name)
            # cmd index map (with -threads at 4-5):
            #  0:FFMPEG  1:-hide_banner  2:-loglevel  3:error
            #  4:-threads  5:threads  6:-ss  7:start_time  8:-i  9:path
            #  10:-fs  11:split_size  12:-map  13:0  14:-map_chapters ...
            cmd = [
                BinConfig.FFMPEG_NAME,
                "-hide_banner",
                "-loglevel",
                "error",
                "-threads",
                str(threads),
                "-ss",
                str(start_time),
                "-i",
                path,
                "-fs",
                str(split_size),
                "-map",
                "0",
                "-map_chapters",
                "-1",
                "-async",
                "1",
                "-strict",
                "-2",
                "-c",
                "copy",
                out_path,
            ]
            if not multi_streams:
                # Remove -map 0 (indices 12 & 13) NOT -fs (indices 10 & 11).
                # Original WZML-X had no -threads so -map was at index 10.
                # With -threads added at 4-5, -map shifted to index 12.
                del cmd[12]
                del cmd[12]
            if (
                listener.suproc == "cancelled"
                or listener.suproc is not None
                and listener.suproc.returncode == -9
            ):
                return False

            listener.suproc = await create_subprocess_exec(*cmd, stderr=PIPE)

            # Poll the growing output-part file every 2 s so the status bar
            # shows live bytes-written instead of staying frozen at 0%.
            # global_offset = bytes finished in all PREVIOUS files (set by tasks_listener)
            # completed_bytes = bytes finished in previous PARTS of THIS file
            # part_bytes = bytes written so far in the CURRENT part (live)
            # Together they give a continuously rising global progress.
            async def _poll_part_size(part_path: str, base_done: int):
                global_offset = getattr(listener, "split_base_offset", 0)
                try:
                    while True:
                        await asyncio_sleep(2)
                        if await aiopath.exists(part_path):
                            try:
                                part_bytes = await aiopath.getsize(part_path)
                                listener.split_current_done = global_offset + base_done + part_bytes
                                t0 = getattr(listener, "_split_start", None)
                                if t0 is not None:
                                    listener.split_elapsed = max(_time() - t0, 0.001)
                            except Exception:
                                pass
                except CancelledError:
                    pass

            poll_task = create_task(_poll_part_size(out_path, completed_bytes))

            # Wait for ffmpeg with a 1-hour timeout per part
            try:
                code = await wait_for(listener.suproc.wait(), timeout=3600)
            except AsyncTimeoutError:
                LOGGER.error(
                    f"ffmpeg split timed out after 3600s on part {i}. Killing. Path: {path}"
                )
                try:
                    listener.suproc.kill()
                except Exception:
                    pass
                poll_task.cancel()
                try:
                    await poll_task
                except CancelledError:
                    pass
                try:
                    await aioremove(out_path)
                except Exception:
                    pass
                return "errored"
            finally:
                poll_task.cancel()
                try:
                    await poll_task
                except CancelledError:
                    pass

            if code == -9:
                return False
            elif code != 0:
                err = (await listener.suproc.stderr.read()).decode().strip()
                try:
                    await aioremove(out_path)
                except Exception:
                    pass
                if multi_streams:
                    LOGGER.warning(
                        f"{err}. Retrying without map, -map 0 not working in all situations. Path: {path}"
                    )
                    return await split_file(
                        path,
                        size,
                        file_,
                        dirpath,
                        split_size,
                        listener,
                        start_time,
                        i,
                        True,
                        False,
                    )
                else:
                    LOGGER.warning(
                        f"{err}. Unable to split this video, if it's size less than {MAX_SPLIT_SIZE} will be uploaded as it is. Path: {path}"
                    )
                return "errored"
            out_size = await aiopath.getsize(out_path)
            if out_size > MAX_SPLIT_SIZE:
                dif = out_size - MAX_SPLIT_SIZE
                split_size -= dif + 5000000
                await aioremove(out_path)
                return await split_file(
                    path,
                    size,
                    file_,
                    dirpath,
                    split_size,
                    listener,
                    start_time,
                    i,
                    True,
                )
            # Part done — lock in cumulative progress (global_offset + this-file's bytes)
            completed_bytes += out_size
            try:
                global_offset = getattr(listener, "split_base_offset", 0)
                listener.split_current_done = global_offset + completed_bytes
                t0 = getattr(listener, "_split_start", None)
                if t0 is not None:
                    listener.split_elapsed = max(_time() - t0, 0.001)
            except Exception:
                pass
            lpd = (await get_media_info(out_path))[0]
            if lpd == 0:
                LOGGER.error(
                    f"Something went wrong while splitting, mostly file is corrupted. Path: {path}"
                )
                break
            elif duration == lpd:
                LOGGER.warning(
                    f"This file has been splitted with default stream and audio, so you will only see one part with less size from orginal one because it doesn't have all streams and audios. This happens mostly with MKV videos. Path: {path}"
                )
                break
            elif lpd <= 3:
                await aioremove(out_path)
                break
            start_time += lpd - 3
            i += 1
    else:
        out_path = ospath.join(dirpath, f"{file_}.")
        listener.suproc = await create_subprocess_exec(
            "split",
            "--numeric-suffixes=1",
            "--suffix-length=3",
            f"--bytes={split_size}",
            path,
            out_path,
            stderr=PIPE,
        )
        # FIX 3 (non-video): timeout for large binary splits too
        try:
            code = await wait_for(listener.suproc.wait(), timeout=7200)
        except AsyncTimeoutError:
            LOGGER.error(f"Binary split timed out after 7200s. Killing. Path: {path}")
            try:
                listener.suproc.kill()
            except Exception:
                pass
            return "errored"
        if code == -9:
            return False
        elif code != 0:
            err = (await listener.suproc.stderr.read()).decode().strip()
            LOGGER.error(err)
    return True


_SITE_TAGS_RE = re_compile(
    r'(?i)\b('
    r'SkymoviesHD|Skymovies|YTS(?:\.MX|\.AM|\.LT)?|YIFY|'
    r'TamilRockers|TamilBlasters|TamilMV|TamilGun|'
    r'Moviesda|MoviesBay|MoviesCounter|MoviesWood|'
    r'Bolly4u|Bolly4ufree|Filmywap|Filmyzilla|Filmy4wap|'
    r'WorldFree4u|World4ufree|Khatrimaza|Katmovie|KatMovieHD|'
    r'MKVCinemas|MKVCage|MkvHub|'
    r'1337x|RARBG|TGx|EZTV|Nyaa|'
    r'HDHub4u|HubHD|JalshaMoviez|DownloadHub|'
    r'7StarHD|9xMovies|9xmovie|300MB|'
    r'SSMovies|SSLeech|'
    r'PikaHD|CineVood|UHDMovies|RipMovies'
    r')\b',
    0,
)

_AUDIO_CODEC_MAP = {
    "aac":    "AAC",
    "ac3":    "AC3",
    "eac3":   "EAC3",
    "dts":    "DTS",
    "mp3":    "MP3",
    "flac":   "FLAC",
    "opus":   "OPUS",
    "vorbis": "OGG",
    "pcm_s16le": "PCM",
}


async def _imdb_year_lookup(title: str) -> str:
    """Query IMDB suggestion endpoint to get release year for a title."""
    try:
        from urllib.request import urlopen
        from urllib.parse import quote
        import json as _json
        clean = re_sub(r'[^a-zA-Z0-9 ]', '', title).strip()
        url = f"https://v3.sg.media-imdb.com/suggestion/x/{quote(clean)}.json"
        with urlopen(url, timeout=5) as resp:
            data = _json.loads(resp.read())
        for entry in data.get("d", []):
            if entry.get("qid") in ("movie", "tvSeries", "tvMiniSeries", "tvMovie"):
                yr = entry.get("y") or entry.get("yr", "")
                if yr:
                    yr_str = str(yr).split("-")[0]
                    if re_search(r'^(?:19|20)\d{2}$', yr_str):
                        return f"({yr_str})"
    except Exception as e:
        LOGGER.warning(f"auto_rename IMDB lookup failed: {e}")
    return ""


_RIP_PATTERNS = [
    (r'blu[.\-\s]?ray|bluray|bdrip',  'BluRay'),
    (r'web[.\-\s]?dl',                'HDRip'),
    (r'web[.\-\s]?rip|webrip',        'HDRip'),
    (r'hdrip|hd[.\-\s]?rip',          'HDRip'),
    (r'dvdrip|dvd[.\-\s]?scr',        'DVDRip'),
    (r'hdtv',                          'HDTV'),
    (r'camrip|cam',                    'CAMRip'),
]

_CODEC_PATTERNS = [
    (r'(?i)\bx\.?265\b|\bh\.?265\b', 'x265'),
    (r'(?i)\bHEVC\b',                 'x265'),
    (r'(?i)\bx\.?264\b|\bh\.?264\b', 'x264'),
    (r'(?i)\bAVC\b',                  'x264'),
    (r'(?i)\bAV1\b',                  'AV1'),
    (r'(?i)\bVP9\b',                  'VP9'),
    (r'(?i)\bXviD\b|\bDivX\b',        'XviD'),
]

_TITLE_STRIP_AT = [
    r'[\(\[]?(?:19|20)\d{2}[\)\]]?',
    r'(?i)\b[Ss]\d{1,2}(?:[Ee]\d{1,2})?\b',
    r'(?i)\b[Ss]eason\s*\d{1,2}\b',
    r'(?i)\b(?:480|540|720|1080|2160|4320)p\b',
    r'(?i)\bblu[.\-\s]?ray\b',
    r'(?i)\bbdrip\b',
    r'(?i)\bweb[.\-\s]?dl\b',
    r'(?i)\bweb[.\-\s]?rip\b',
    r'(?i)\bwebrip\b',
    r'(?i)\bhdrip\b',
    r'(?i)\bdvdrip\b',
    r'(?i)\bhdtv\b',
    r'(?i)\bx\.?264\b',
    r'(?i)\bx\.?265\b',
    r'(?i)\bh\.?264\b',
    r'(?i)\bh\.?265\b',
    r'(?i)\bhevc\b',
    r'(?i)\bav1\b',
    r'(?i)\bvp9\b',
    r'(?i)\bxvid\b',
]


_MEDIA_EXTS = {'.mkv', '.mp4', '.avi', '.mov', '.flv', '.wmv', '.webm',
               '.ts', '.m4v', '.mpg', '.mpeg', '.3gp', '.rmvb', '.m2ts'}


def _clean_media_filename(name: str) -> str:
    """Strip trailing CLI-flag-like tokens (e.g. ' -vm', ' -abc') from a filename."""
    import re as _re
    cleaned = _re.sub(r'(\s+-\w+)+\s*$', '', name).strip()
    return cleaned if cleaned else name


def _get_media_ext(name: str) -> str:
    """
    Extract the real media extension from a filename that may contain
    trailing CLI-flag-like tokens.
    e.g. 'merge.mkv -vm' → '.mkv'
    """
    clean = _clean_media_filename(name)
    _, ext = ospath.splitext(clean)
    if ext.lower() in _MEDIA_EXTS:
        return ext
    _, raw_ext = ospath.splitext(name)
    for ve in _MEDIA_EXTS:
        if raw_ext.lower().startswith(ve):
            return ve
    return ext


async def _collect_rename_meta(file_path: str, original_name: str) -> dict:
    """
    Shared metadata collector for both Auto and Custom rename modes.
    Runs ffprobe on file_path and parses original_name.
    Returns a dict with all values needed to fill any rename template.
    """
    original_name = _clean_media_filename(original_name)
    ext  = _get_media_ext(original_name)
    base = ospath.splitext(_clean_media_filename(original_name))[0]

    quality       = ""
    resolution    = ""
    ffprobe_codec = ""
    audio_codec   = ""
    audio_langs   = []
    audio_count   = 0
    sub_count     = 0

    try:
        result = await cmd_exec([
            "ffprobe", "-hide_banner", "-loglevel", "error",
            "-print_format", "json", "-show_streams", file_path,
        ])
        if result[1]:
            LOGGER.warning(f"rename ffprobe stderr: {result[1]}")
        streams = eval(result[0]).get("streams", [])
        for stream in streams:
            ctype = stream.get("codec_type", "")
            if ctype == "video" and not quality:
                w = int(stream.get("width",  0))
                h = int(stream.get("height", 0))
                if w and h:
                    resolution = f"{w}x{h}"
                quality = (
                    "480p"  if h <= 480  else
                    "720p"  if h <= 540  else
                    "720p"  if h <= 720  else
                    "1080p" if h <= 1080 else
                    "2160p" if h <= 2160 else "4320p"
                )
                cn = stream.get("codec_name", "").lower()
                if cn in ("h264", "avc", "avc1"):
                    ffprobe_codec = "x264"
                elif cn in ("hevc", "h265", "hvc1"):
                    ffprobe_codec = "x265"
                elif cn == "av1":
                    ffprobe_codec = "AV1"
                elif cn == "vp9":
                    ffprobe_codec = "VP9"
                elif cn == "mpeg4":
                    ffprobe_codec = "XviD"
                elif cn:
                    ffprobe_codec = cn.upper()
            elif ctype == "audio":
                audio_count += 1
                if not audio_codec:
                    ac = stream.get("codec_name", "").lower()
                    audio_codec = _AUDIO_CODEC_MAP.get(ac, ac.upper() if ac else "")
                lang_tag = stream.get("tags", {}).get("language", "")
                if lang_tag and lang_tag.lower() not in ("und", ""):
                    with suppress(Exception):
                        lang_tag = Language.get(lang_tag).display_name()
                    if lang_tag not in audio_langs:
                        audio_langs.append(lang_tag)
            elif ctype == "subtitle":
                sub_count += 1
    except Exception as e:
        LOGGER.warning(f"rename metadata extraction failed: {e}")

    name = base

    season_match  = re_search(r'(?i)[Ss](\d{1,2})(?:[Ee]\d{1,2})?', name)
    episode_match = re_search(r'(?i)[Ss]\d{1,2}[Ee](\d{1,2})', name)
    is_series  = bool(season_match)
    season_str = f"S{int(season_match.group(1)):02d}"  if season_match  else ""
    episode_str= f"E{int(episode_match.group(1)):02d}" if episode_match else ""

    year_match = re_search(r'[\(\[]?((?:19|20)\d{2})[\)\]]?', name)
    year_raw   = year_match.group(1) if year_match else ""
    year_str   = f"({year_raw})"     if year_raw   else ""

    rip_type = ""
    for pattern, label in _RIP_PATTERNS:
        if re_search(pattern, name, IGNORECASE):
            rip_type = label
            break

    filename_codec = ""
    for pattern, label in _CODEC_PATTERNS:
        if re_search(pattern, name):
            filename_codec = label
            break
    codec_str = filename_codec if filename_codec else ffprobe_codec
    LOGGER.info(f"rename codec: filename='{filename_codec}' ffprobe='{ffprobe_codec}' → '{codec_str}'")

    title    = name
    earliest = len(title)
    for pat in _TITLE_STRIP_AT:
        m = re_search(pat, title)
        if m and m.start() < earliest:
            earliest = m.start()
    title = title[:earliest]
    title = _SITE_TAGS_RE.sub('', title)
    title = re_sub(r'[._\-]+', ' ', title).strip()
    title = re_sub(r'\s+', ' ', title).strip()

    if not year_str and title:
        year_str = await _imdb_year_lookup(title)
        year_raw = year_str[1:-1] if year_str else ""
        if year_str:
            LOGGER.info(f"rename IMDB year: {title} → {year_str}")

    if audio_count == 0:
        audio_str = ""
        shortlang = ""
    elif audio_count == 1:
        audio_str = audio_langs[0] if audio_langs else ""
        shortlang = audio_str
    elif audio_count == 2:
        if len(audio_langs) >= 2:
            audio_str = f"ORG. [Dual Audio] [{' - '.join(audio_langs[:2])}]"
        else:
            audio_str = "Dual Audio"
        shortlang = "Dual"
    else:
        if audio_langs:
            audio_str = f"Multi Audio [{' - '.join(audio_langs[:3])}]"
        else:
            audio_str = "Multi Audio"
        shortlang = "Multi"

    sub_str = "MSubs" if sub_count > 1 else ("ESubs" if sub_count == 1 else "")

    return {
        "ext":         ext,
        "title":       title,
        "year":        year_str,
        "year_raw":    year_raw,
        "quality":     quality,
        "resolution":  resolution,
        "rip":         rip_type,
        "season":      season_str,
        "episode":     episode_str,
        "is_series":   is_series,
        "audio_str":   audio_str,
        "audio_count": audio_count,
        "audio_langs": audio_langs,
        "shortlang":   shortlang,
        "codec":       codec_str,
        "hevc":        "HEVC" if codec_str == "x265" else "",
        "audio_codec": audio_codec,
        "sub_str":     sub_str,
        "sub_count":   sub_count,
    }


async def auto_rename_by_metadata(file_path: str, original_name: str) -> str:
    """
    Auto-rename using fixed smart format based on file metadata.

    Movie  : Title (Year) Quality RipType Audio  VideoCodec AudioCodec ESubs/MSubs
    Series : Title (Year) Quality HEVC RipType Audio S01 Complete Series VideoCodec AudioCodec ESubs/MSubs
    """
    meta = await _collect_rename_meta(file_path, original_name)
    if not meta["title"]:
        LOGGER.warning(f"auto_rename: no title from '{original_name}', skipping")
        return original_name

    parts = [meta["title"]]
    if meta["year"]:        parts.append(meta["year"])
    if meta["quality"]:     parts.append(meta["quality"])
    if meta["hevc"]:        parts.append(meta["hevc"])
    if meta["rip"]:         parts.append(meta["rip"])
    if meta["audio_str"]:   parts.append(meta["audio_str"])
    if meta["is_series"] and meta["season"]:
        parts.append(meta["season"])
        parts.append("Complete Series")
    if meta["codec"]:       parts.append(meta["codec"])
    if meta["audio_codec"]: parts.append(meta["audio_codec"])
    if meta["sub_str"]:     parts.append(meta["sub_str"])

    new_name = " ".join(parts) + meta["ext"]
    LOGGER.info(f"auto_rename: '{original_name}' → '{new_name}'")
    return new_name


async def apply_custom_rename_format(fmt_str: str, file_path: str, original_name: str) -> str:
    """
    Apply user-defined format template to generate filename.

    Supported placeholders:
      {name}       → Clean title
      {year}       → Year digits (e.g. 2026)
      {quality}    → 480p / 720p / 1080p
      {resolution} → 1280x720
      {rip}        → HDRip / BluRay
      {season}     → S01  (empty for movies)
      {episode}    → E01  (empty if not episode)
      {audio}      → Full audio label (Hindi / Dual Audio / Multi Audio […])
      {shortlang}  → Dual / Hindi / Multi
      {lib}        → x264 / x265
      {audiocodec} → AAC / AC3 / DTS
      {shortsub}   → ESubs / MSubs
      {hevc}       → HEVC  (empty if not x265)
      {extension}  → .mkv / .mp4
    """
    meta = await _collect_rename_meta(file_path, original_name)
    if not meta["title"]:
        LOGGER.warning(f"custom_rename: no title from '{original_name}', skipping")
        return original_name

    result = fmt_str
    result = result.replace("{name}",       meta["title"])
    result = result.replace("{year}",       meta["year_raw"])
    result = result.replace("{quality}",    meta["quality"])
    result = result.replace("{resolution}", meta["resolution"])
    result = result.replace("{rip}",        meta["rip"])
    result = result.replace("{season}",     meta["season"])
    result = result.replace("{episode}",    meta["episode"])
    result = result.replace("{audio}",      meta["audio_str"])
    result = result.replace("{shortlang}",  meta["shortlang"])
    result = result.replace("{lib}",        meta["codec"])
    result = result.replace("{audiocodec}", meta["audio_codec"])
    result = result.replace("{shortsub}",   meta["sub_str"])
    result = result.replace("{hevc}",       meta["hevc"])
    result = result.replace("{extension}",  meta["ext"])

    result = re_sub(r' {2,}', ' ', result).strip()
    result = re_sub(r'^[\s._\-]+|[\s._\-]+$', '', result)

    new_name = result + meta["ext"]
    LOGGER.info(f"custom_rename: '{original_name}' → '{new_name}'")
    return new_name


async def format_filename(file_, user_id, dirpath=None, isMirror=False):
    user_dict = user_data.get(user_id, {})
    ftag, ctag = ("m", "MIRROR") if isMirror else ("l", "LEECH")

    disk_file_ = file_
    file_ = _clean_media_filename(file_)

    _auto_rename = user_dict.get("auto_rename", False)
    if _auto_rename is True:
        _auto_rename = "auto"
    if not isMirror and _auto_rename and dirpath:
        file_path = ospath.join(dirpath, disk_file_)
        if ospath.isfile(file_path):
            if _auto_rename == "auto":
                renamed = await auto_rename_by_metadata(file_path, file_)
            elif _auto_rename == "custom":
                ar_fmt = user_dict.get("auto_rename_fmt", "")
                renamed = await apply_custom_rename_format(ar_fmt, file_path, file_) if ar_fmt else file_
            else:
                renamed = file_
            if renamed != file_:
                file_ = renamed

    prefix = (
        config_dict[f"{ctag}_FILENAME_PREFIX"]
        if (val := user_dict.get(f"{ftag}prefix", "")) == ""
        else val
    )
    remname = (
        config_dict[f"{ctag}_FILENAME_REMNAME"]
        if (val := user_dict.get(f"{ftag}remname", "")) == ""
        else val
    )
    suffix = (
        config_dict[f"{ctag}_FILENAME_SUFFIX"]
        if (val := user_dict.get(f"{ftag}suffix", "")) == ""
        else val
    )
    lcaption = (
        config_dict["LEECH_FILENAME_CAPTION"]
        if (val := user_dict.get("lcaption", "")) == ""
        else val
    )

    prefile_ = file_
    file_ = re_sub(r"www\S+", "", file_)

    if remname:
        if not remname.startswith("|"):
            remname = f"|{remname}"
        remname = remname.replace("\\s", " ")
        slit = remname.split("|")
        __newFileName = ospath.splitext(file_)[0]
        for rep in range(1, len(slit)):
            args = slit[rep].split(":")
            if len(args) == 3:
                __newFileName = re_sub(args[0], args[1], __newFileName, int(args[2]))
            elif len(args) == 2:
                __newFileName = re_sub(args[0], args[1], __newFileName)
            elif len(args) == 1:
                __newFileName = re_sub(args[0], "", __newFileName)
        file_ = __newFileName + ospath.splitext(file_)[1]
        LOGGER.info(f"New Remname : {file_}")

    nfile_ = file_
    if prefix:
        nfile_ = prefix.replace("\\s", " ") + file_
        prefix = re_sub(r"<.*?>", "", prefix).replace("\\s", " ")
        if not file_.startswith(prefix):
            file_ = f"{prefix}{file_}"

    if suffix and not isMirror:
        suffix = suffix.replace("\\s", " ")
        sufLen = len(suffix)
        fileDict = file_.split(".")
        _extIn = 1 + len(fileDict[-1])
        _extOutName = ".".join(fileDict[:-1]).replace(".", " ").replace("-", " ")
        _newExtFileName = f"{_extOutName}{suffix}.{fileDict[-1]}"
        if len(_extOutName) > (64 - (sufLen + _extIn)):
            _newExtFileName = (
                _extOutName[: 64 - (sufLen + _extIn)] + f"{suffix}.{fileDict[-1]}"
            )
        file_ = _newExtFileName
    elif suffix:
        suffix = suffix.replace("\\s", " ")
        file_ = (
            f"{ospath.splitext(file_)[0]}{suffix}{ospath.splitext(file_)[1]}"
            if "." in file_
            else f"{file_}{suffix}"
        )

    cap_mono = (
        f"<{config_dict['CAP_FONT']}>{nfile_}</{config_dict['CAP_FONT']}>"
        if config_dict["CAP_FONT"]
        else nfile_
    )
    if lcaption and dirpath and not isMirror:

        def lowerVars(match):
            return f"{{{match.group(1).lower()}}}"

        lcaption = (
            lcaption.replace("\\|", "%%")
            .replace("\\{", "&%&")
            .replace("\\}", "$%$")
            .replace("\\s", " ")
        )
        slit = lcaption.split("|")
        slit[0] = re_sub(r"\{([^}]+)\}", lowerVars, slit[0])
        up_path = ospath.join(dirpath, disk_file_)
        dur, qual, lang, subs = await get_media_info(up_path, True)
        cap_mono = slit[0].format(
            filename=nfile_,
            size=get_readable_file_size(await aiopath.getsize(up_path)),
            duration=get_readable_time(dur),
            quality=qual,
            languages=lang,
            subtitles=subs,
            md5_hash=get_md5_hash(up_path),
        )
        if len(slit) > 1:
            for rep in range(1, len(slit)):
                args = slit[rep].split(":")
                if len(args) == 3:
                    cap_mono = cap_mono.replace(args[0], args[1], int(args[2]))
                elif len(args) == 2:
                    cap_mono = cap_mono.replace(args[0], args[1])
                elif len(args) == 1:
                    cap_mono = cap_mono.replace(args[0], "")
        cap_mono = cap_mono.replace("%%", "|").replace("&%&", "{").replace("$%$", "}")
    return file_, cap_mono


async def get_ss(up_path, ss_no):
    thumbs_path, tstamps = await take_ss(up_path, total=min(ss_no, 250), gen_ss=True)
    th_html = f"📌 <h4>{ospath.basename(up_path)}</h4><br>📇 <b>Total Screenshots:</b> {ss_no}<br><br>"
    up_sem = Semaphore(25)

    async def telefile(thumb):
        async with up_sem:
            tele_id = await sync_to_async(upload_file, ospath.join(thumbs_path, thumb))
            return tele_id[0], tstamps[thumb]

    tasks = [telefile(thumb) for thumb in natsorted(await listdir(thumbs_path))]
    results = await gather(*tasks)
    th_html += "".join(
        f'<img src="https://graph.org{tele_id}"><br><pre>Screenshot at {stamp}</pre>'
        for tele_id, stamp in results
    )
    await aiormtree(thumbs_path)
    link_id = (await telegraph.create_page(title="ScreenShots X", content=th_html))[
        "path"
    ]
    return f"https://graph.org/{link_id}"


async def get_mediainfo_link(up_path):
    stdout, __, _ = await cmd_exec(ssplit(f'mediainfo "{up_path}"'))
    tc = f"📌 <h4>{ospath.basename(up_path)}</h4><br><br>"
    if len(stdout) != 0:
        tc += parseinfo(stdout)
    link_id = (await telegraph.create_page(title="MediaInfo X", content=tc))["path"]
    return f"https://graph.org/{link_id}"


def get_md5_hash(up_path):
    md5_hash = md5()
    with open(up_path, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            md5_hash.update(byte_block)
        return md5_hash.hexdigest()
