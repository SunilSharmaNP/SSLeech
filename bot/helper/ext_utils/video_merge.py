#!/usr/bin/env python3
"""
Video Merge Utilities — FFmpeg-based engine for merging video files.
Ported and enhanced from vm-sunil Merger Bot.
"""

import os
import json
from asyncio import create_subprocess_exec
from asyncio.subprocess import PIPE
from collections import Counter
from natsort import natsorted

from bot import LOGGER

VIDEO_EXTENSIONS = {
    ".mp4", ".mkv", ".avi", ".mov", ".flv", ".wmv", ".webm",
    ".m4v", ".ts", ".m2ts", ".mpg", ".mpeg", ".3gp", ".rmvb",
}


async def get_video_info(filepath):
    """
    Analyze a video file using ffprobe.
    Returns dict with width, height, fps, codecs, duration — or None on failure.
    """
    cmd = [
        "ffprobe", "-v", "quiet",
        "-print_format", "json",
        "-show_streams", "-show_format",
        filepath,
    ]
    try:
        proc = await create_subprocess_exec(*cmd, stdout=PIPE, stderr=PIPE)
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            LOGGER.warning(f"ffprobe failed for {filepath}: {stderr.decode()[:200]}")
            return None
        data = json.loads(stdout.decode())
    except Exception as e:
        LOGGER.error(f"ffprobe exception for {filepath}: {e}")
        return None

    streams = data.get("streams", [])
    fmt = data.get("format", {})

    video_stream = next(
        (s for s in streams if s.get("codec_type") == "video"), None
    )
    if not video_stream:
        return None

    fps_str = video_stream.get("r_frame_rate", "24/1")
    try:
        num, den = fps_str.split("/")
        fps = round(float(num) / float(den), 3)
    except Exception:
        fps = 24.0

    audio_stream = next(
        (s for s in streams if s.get("codec_type") == "audio"), None
    )

    return {
        "width": int(video_stream.get("width", 0)),
        "height": int(video_stream.get("height", 0)),
        "fps": fps,
        "video_codec": video_stream.get("codec_name", ""),
        "audio_codec": audio_stream.get("codec_name", "") if audio_stream else "",
        "pix_fmt": video_stream.get("pix_fmt", "yuv420p"),
        "audio_sample_rate": audio_stream.get("sample_rate", "48000") if audio_stream else "48000",
        "duration": float(fmt.get("duration", 0)),
    }


def videos_are_compatible(infos):
    """
    Returns True if all videos can be fast-merged (concat copy without re-encoding).
    Checks: resolution and fps match.
    """
    if not infos or len(infos) < 2:
        return True
    first = infos[0]
    for info in infos[1:]:
        if (
            info["width"] != first["width"]
            or info["height"] != first["height"]
            or abs(info["fps"] - first["fps"]) > 0.5
        ):
            return False
    return True


async def fast_concat(input_files, output_path, listener=None):
    """
    FFmpeg concat demuxer — no re-encoding, extremely fast.
    Requires all input files to have identical stream parameters.
    Returns True on success.
    """
    concat_list = output_path + ".concat_list.txt"
    try:
        with open(concat_list, "w", encoding="utf-8") as f:
            for fp in input_files:
                safe = fp.replace("\\", "/").replace("'", "\\'")
                f.write(f"file '{safe}'\n")

        cmd = [
            "ffmpeg", "-hide_banner", "-ignore_unknown", "-y",
            "-f", "concat", "-safe", "0",
            "-i", concat_list,
            "-map", "0",
            "-c", "copy",
            "-f", "matroska",
            output_path,
        ]
        proc = await create_subprocess_exec(*cmd, stdout=PIPE, stderr=PIPE)
        if listener:
            listener.suproc = proc
        _, stderr = await proc.communicate()

        if listener and listener.suproc == "cancelled":
            return False

        if proc.returncode == 0:
            LOGGER.info(f"Fast concat success → {output_path}")
            return True
        LOGGER.error(f"Fast concat failed: {stderr.decode()[-500:]}")
        return False
    finally:
        try:
            os.remove(concat_list)
        except Exception:
            pass


async def standardize_video(input_path, output_path, target_w, target_h, listener=None):
    """
    Re-encode a single video to standardized parameters so it can be concat'd.
    Target: libx264 + aac, yuv420p, 30fps, forced resolution.
    Returns True on success.
    """
    vf = (
        f"scale={target_w}:{target_h}:force_original_aspect_ratio=decrease,"
        f"pad={target_w}:{target_h}:(ow-iw)/2:(oh-ih)/2,"
        f"fps=30,format=yuv420p"
    )
    cmd = [
        "ffmpeg", "-hide_banner", "-ignore_unknown", "-y",
        "-i", input_path,
        "-vf", vf,
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-c:a", "aac", "-ar", "48000", "-ac", "2", "-b:a", "128k",
        "-f", "matroska", output_path,
    ]
    proc = await create_subprocess_exec(*cmd, stdout=PIPE, stderr=PIPE)
    if listener:
        listener.suproc = proc
    _, stderr = await proc.communicate()

    if listener and listener.suproc == "cancelled":
        return False

    if proc.returncode == 0:
        return True
    LOGGER.error(f"Standardize failed for {input_path}: {stderr.decode()[-500:]}")
    return False


async def merge_video_files(input_files, output_path, listener=None):
    """
    Main entry point for merging multiple video files.

    Always uses FFmpeg concat demuxer with stream copy (no re-encoding).
    Videos are joined at their original framerate and resolution — no quality
    loss, no encoding delay, regardless of whether resolutions differ.

    Returns True on success, False on failure or cancellation.
    """
    if not input_files:
        LOGGER.error("merge_video_files: no input files provided")
        return False

    if len(input_files) == 1:
        import shutil
        shutil.copy2(input_files[0], output_path)
        return True

    LOGGER.info(f"Merging {len(input_files)} videos → {output_path} (concat copy, no re-encode)")
    return await fast_concat(input_files, output_path, listener)


def _file_is_video(fname):
    """
    Check if a filename is a video file.
    Handles filenames with trailing CLI-flag-like tokens (e.g. 'movie.mkv -vm').
    """
    import re as _re
    clean = _re.sub(r'(\s+-\w+)+\s*$', '', fname).strip()
    ext = os.path.splitext(clean)[1].lower()
    if ext in VIDEO_EXTENSIONS:
        return True
    raw_ext = os.path.splitext(fname)[1].lower()
    for ve in VIDEO_EXTENSIONS:
        if raw_ext.lower().startswith(ve):
            return True
    return False


def get_video_files_sorted(path):
    """
    Return a naturally-sorted list of all video files under `path`.
    Works for both a single file and a directory tree.
    Handles filenames with trailing CLI-flag-like tokens (e.g. 'movie.mkv -vm').
    """
    if os.path.isfile(path):
        return [path] if _file_is_video(os.path.basename(path)) else []

    result = []
    for dirpath, _, filenames in os.walk(path):
        for fname in natsorted(filenames):
            if _file_is_video(fname):
                result.append(os.path.join(dirpath, fname))
    return result


def parse_episode_selection(text, total):
    """
    Parse user's episode selection string.
    Supported formats:
      - "all"           → [0 .. total-1]
      - "1-5"           → [0,1,2,3,4]
      - "1,3,5"         → [0,2,4]
      - "1-3,5,7-9"     → mixed
    Returns list of 0-based indices, or None on parse error.
    """
    text = text.strip().lower()
    if text == "all":
        return list(range(total))

    indices = []
    try:
        for part in text.replace(" ", "").split(","):
            part = part.strip()
            if not part:
                continue
            if "-" in part:
                parts = part.split("-", 1)
                start = int(parts[0]) - 1
                end = int(parts[1]) - 1
                if start < 0 or end >= total or start > end:
                    return None
                indices.extend(range(start, end + 1))
            else:
                idx = int(part) - 1
                if idx < 0 or idx >= total:
                    return None
                indices.append(idx)
        # Deduplicate, preserve order
        seen = set()
        unique = []
        for i in indices:
            if i not in seen:
                seen.add(i)
                unique.append(i)
        return unique if unique else None
    except (ValueError, IndexError):
        return None
