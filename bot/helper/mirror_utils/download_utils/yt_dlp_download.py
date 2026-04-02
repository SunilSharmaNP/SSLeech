#!/usr/bin/env python3
from os import path as ospath, listdir
from secrets import token_hex
from logging import getLogger
from time import sleep
from urllib.parse import urlparse
from yt_dlp import YoutubeDL, DownloadError
from re import search as re_search

from bot import download_dict_lock, download_dict, non_queued_dl, queue_dict_lock
from bot.helper.telegram_helper.message_utils import sendStatusMessage
from ..status_utils.yt_dlp_download_status import YtDlpDownloadStatus
from bot.helper.mirror_utils.status_utils.queue_status import QueueStatus
from bot.helper.ext_utils.bot_utils import sync_to_async, async_to_sync
from bot.helper.ext_utils.task_manager import (
    is_queued,
    stop_duplicate_check,
    limit_checker,
)

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

        # Base options (similar to wzv3 but keep original cookie file)
        self.opts = {
            "progress_hooks": [self.__onDownloadProgress],
            "logger": MyLogger(self, self.__listener),
            "usenetrc": True,
            "cookiefile": "cookies.txt",  # Always set cookies file
            "allow_multiple_video_streams": True,
            "allow_multiple_audio_streams": True,
            "noprogress": True,
            "allow_playlist_files": True,
            "overwrites": True,
            "writethumbnail": True,
            "trim_file_name": 220,
            "fragment_retries": 10,
            "retries": 10,
            "retry_sleep_functions": {
                "http": lambda n: min(5 * (n + 1), 30),  # Progressive backoff: 5s, 10s, 15s... capped at 30s
                "fragment": lambda n: min(3 * (n + 1), 20),
                "file_access": lambda n: min(3 * (n + 1), 20),
                "extractor": lambda n: min(5 * (n + 1), 30),
            },
            # YouTube authentication and SABR bypass
            "socket_timeout": 60,  # Increased from 30s for heavy gzip/CDN operations
            "call_home": False,
            "no_check_certificate": True,
            "hls_prefer_native": True,  # Use native HLS (respects http_headers; FFmpeg has TLS issues)
            "hls_use_mpegts": False,  # Standard MP4 container
            "youtube_include_dash_manifest": False,  # Disable - can trigger SABR
            "youtube_include_hls_manifest": True,
            # HTTP options for better connection handling
            "http_headers": {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept-Encoding": "gzip, deflate",  # Removed brotli - causes decompression issues on some CDNs
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "none",
                "Sec-Fetch-User": "?1",
                "Upgrade-Insecure-Requests": "1",
                # Note: Referer and Origin are set dynamically per link
            },
            # Extractor args for YouTube authentication and SABR bypass
            "extractor_args": {
                "youtube": [
                    "player_skip=configs,js",  # Skip JS validation
                    "player=null",  # Use null player
                    "skip=webpage_url",  # Skip webpage validation
                    "raise_for_unavailable_formats=false",  # Don't fail on format issues
                    "player_client=android",  # Bypass web_safari n-challenge
                    "po_token_provider=java",  # SABR bypass token provider
                ]
            },
            # JavaScript runtime configuration
            "js_runtimes": {"deno": {}},  # Deno for JS challenges
        }

        # Add ffmpeg_location if BinConfig exists
        try:
            from bot.core.config_manager import BinConfig
            self.opts["ffmpeg_location"] = f"/bin/{BinConfig.FFMPEG_NAME}"
        except (ModuleNotFoundError, ImportError, AttributeError):
            pass
        
        # Log cookie usage
        LOGGER.info(f"Using cookies file: cookies.txt")

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
        async with download_dict_lock:
            download_dict[self.__listener.uid] = YtDlpDownloadStatus(
                self, self.__listener, self.__gid
            )
        if not from_queue:
            await self.__listener.onDownloadStart()
            await sendStatusMessage(self.__listener.message)

    def __onDownloadError(self, error):
        self.__is_cancelled = True
        async_to_sync(self.__listener.onDownloadError, error)

    def _get_referer_for_link(self, link):
        """Extract referer URL from link"""
        if "luluvid.com" in link:
            # For luluvid, use the main domain
            return "https://luluvid.com/"
        elif "youtube.com" in link or "youtu.be" in link:
            return "https://www.youtube.com/"
        else:
            # Generic: use domain only
            parsed = urlparse(link)
            return f"{parsed.scheme}://{parsed.netloc}/"

    def extractMetaData(self, link, name):
        if link.startswith(("rtmp", "mms", "rstp", "rtmps")):
            self.opts["external_downloader"] = "ffmpeg"
        
        # Use custom extractMetaData with retry logic
        max_retries = 3
        retry_count = 0
        referer = self._get_referer_for_link(link)
        
        while retry_count < max_retries:
            try:
                with YoutubeDL(self.opts) as ydl:
                    try:
                        result = ydl.extract_info(link, download=False)
                        if result is None:
                            raise ValueError("Info result is None")
                    except Exception as extract_e:
                        error_msg = str(extract_e).lower()
                        
                        # NEW: Handle HTTP 403 Forbidden errors (CDN denying access)
                        if "http error 403" in error_msg or "403" in error_msg:
                            retry_count += 1
                            if retry_count < max_retries:
                                # Longer wait for CDN rate-limiting
                                wait_times = [30, 60]  # 30s, 60s waits
                                wait_time = wait_times[min(retry_count - 1, len(wait_times) - 1)]
                                LOGGER.warning(f"⚠️ HTTP 403 in metadata (retry {retry_count}/{max_retries}), waiting {wait_time}s...")
                                # Retry with explicit referer headers
                                retry_opts = self.opts.copy()
                                retry_opts["http_headers"] = self.opts["http_headers"].copy()
                                retry_opts["http_headers"]["Referer"] = referer
                                retry_opts["http_headers"]["Origin"] = referer.rstrip('/').rsplit('/', 1)[0] if referer.count('/') > 2 else referer
                                self.opts = retry_opts
                                sleep(wait_time)
                                continue  # Retry
                            else:
                                LOGGER.error(f"❌ HTTP 403 metadata extraction failed after {max_retries} retries")
                        
                        # NEW: Handle gzip/decompression errors in metadata extraction
                        if "decompressing" in error_msg or "inconsistent stream" in error_msg or "failed to decode" in error_msg:
                            retry_count += 1
                            if retry_count < max_retries:
                                LOGGER.warning(f"⚠️ Gzip decompression error in metadata (retry {retry_count}/{max_retries}), using gzip-safe headers...")
                                retry_opts = self.opts.copy()
                                retry_opts["socket_timeout"] = 90
                                retry_opts["http_headers"] = self.opts["http_headers"].copy()
                                retry_opts["http_headers"]["Referer"] = referer
                                # Force gzip only, disable brotli
                                retry_opts["http_headers"]["Accept-Encoding"] = "gzip"
                                self.opts = retry_opts
                                sleep(5)  # Brief wait before retry
                                continue  # Retry
                            else:
                                LOGGER.error(f"❌ Gzip decompression failed after {max_retries} retries")
                        
                        # NEW: Handle HTTP 522 errors in metadata extraction
                        if "http error 522" in error_msg or "500 server error" in error_msg:
                            retry_count += 1
                            if retry_count < max_retries:
                                # Longer wait for CDN blocking (522 = connection timeout at CDN)
                                wait_times = [15, 30]  # 15s, 30s waits
                                wait_time = wait_times[min(retry_count - 1, len(wait_times) - 1)]
                                LOGGER.warning(f"⚠️ HTTP 522 in metadata (retry {retry_count}/{max_retries}), waiting {wait_time}s...")
                                # Retry with safe decompression settings
                                retry_opts = self.opts.copy()
                                retry_opts["socket_timeout"] = 90  # Very long timeout for slow CDN
                                retry_opts["http_headers"] = self.opts["http_headers"].copy()
                                retry_opts["http_headers"]["Referer"] = referer
                                # Remove brotli from encoding to avoid decompression issues
                                retry_opts["http_headers"]["Accept-Encoding"] = "gzip, deflate"
                                self.opts = retry_opts
                                sleep(wait_time)
                                continue  # Retry
                            else:
                                LOGGER.error(f"❌ HTTP 522 metadata extraction failed after {max_retries} retries")
                        
                        # Retry on decompression/connection errors
                        if any(err in error_msg for err in ["inconsistent stream", "failed to decode", "connection", "timeout"]):
                            retry_count += 1
                            if retry_count < max_retries:
                                LOGGER.warning(f"⚠️ extractMetaData error (retry {retry_count}/{max_retries}): {error_msg[:100]}")
                                continue  # Retry
                            else:
                                LOGGER.error(f"❌ extractMetaData failed after {max_retries} retries")
                        
                        LOGGER.error(f"extractMetaData error: {str(extract_e)[:200]}")
                        return self.__onDownloadError(str(extract_e))
                    
                    # Success - process results
                    if self.is_playlist:
                        self.playlist_count = result.get("playlist_count", 0)
                    if "entries" in result:
                        self.name = name
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
                        self.name = f"{name}{ext}" if name else realName
                        if not self.__ext:
                            self.__ext = ext
                        if result.get("filesize"):
                            self.__size = result["filesize"]
                        elif result.get("filesize_approx"):
                            self.__size = result["filesize_approx"]
                    
                    return  # Success
                    
            except Exception as e:
                retry_count += 1
                if retry_count < max_retries:
                    LOGGER.warning(f"⚠️ Unexpected error in extractMetaData (retry {retry_count}): {str(e)[:100]}")
                else:
                    return self.__onDownloadError(f"Failed to extract metadata: {str(e)}")

    def __download(self, link, path):
        try:
            referer = self._get_referer_for_link(link)
            with YoutubeDL(self.opts) as ydl:
                try:
                    ydl.download([link])
                except DownloadError as e:
                    error_msg = str(e).lower()
                    
                    # NEW: Handle HTTP 403 Forbidden errors (CDN rate-limiting or authentication)
                    if "http error 403" in error_msg or "403" in error_msg:
                        LOGGER.warning(f"⚠️ HTTP 403 error detected (CDN rate-limit or blocking), retrying with longer delays...")
                        # CDN is likely rate-limiting - use MUCH longer waits
                        wait_times = [30, 60, 90]  # 30s, 60s, 90s waits for rate-limited CDN
                        for attempt in range(1, 4):
                            try:
                                # Progressive wait times - long delays for rate-limited CDN
                                if attempt > 1:
                                    wait_time = wait_times[attempt - 2]
                                    LOGGER.info(f"⏳ CDN 403 rate-limit: Waiting {wait_time}s before retry {attempt}/3...")
                                    sleep(wait_time)
                                
                                retry_opts = self.opts.copy()
                                retry_opts["socket_timeout"] = 60  # Longer timeout for slow CDN
                                retry_opts["retries"] = 25  # More retries for fragments
                                retry_opts["fragment_retries"] = 25
                                retry_opts["hls_prefer_native"] = False  # Use FFmpeg (more compatible)
                                retry_opts["hls_use_mpegts"] = True
                                
                                # Set proper referer and origin headers for CDN
                                retry_opts["http_headers"] = self.opts["http_headers"].copy()
                                retry_opts["http_headers"]["Referer"] = referer
                                retry_opts["http_headers"]["Origin"] = referer.rstrip('/').rsplit('/', 1)[0] if referer.count('/') > 2 else referer
                                # Add connection persistence headers
                                retry_opts["http_headers"]["Connection"] = "keep-alive"
                                retry_opts["http_headers"]["Cache-Control"] = "no-cache"
                                
                                with YoutubeDL(retry_opts) as ydl_retry:
                                    LOGGER.info(f"🔄 HTTP 403 retry {attempt}/3 with FFmpeg + rate-limit backoff...")
                                    ydl_retry.download([link])
                                return  # Success on retry
                            except Exception as retry_e:
                                retry_msg = str(retry_e).lower()
                                if "403" in retry_msg or "forbidden" in retry_msg:
                                    if attempt < 3:
                                        LOGGER.warning(f"⚠️ Retry {attempt} still getting 403, will wait longer and retry...")
                                        continue
                                    else:
                                        LOGGER.error(f"❌ HTTP 403 all retries exhausted after {sum(wait_times[:2])}s total wait")
                                        break
                                else:
                                    # Different error, not just 403
                                    if attempt < 3:
                                        LOGGER.warning(f"⚠️ Retry {attempt} different error: {str(retry_e)[:80]}")
                                        continue
                                    else:
                                        LOGGER.error(f"❌ Retry failed with: {str(retry_e)[:100]}")
                    
                    # NEW: Handle HTTP 522 Cloudflare errors (CDN blocking) - RETRY with backoff
                    if "http error 522" in error_msg or "500 server error" in error_msg or "failed to download m3u8" in error_msg:
                        LOGGER.warning(f"⚠️ HTTP 522/5XX error detected (CDN blocking), retrying with aggressive backoff...")
                        # Use longer waits for rate-limited/blocked CDN
                        wait_times = [30, 60]  # 30s, 60s waits for persistent CDN blocking
                        for attempt in range(1, 4):
                            try:
                                retry_opts = self.opts.copy()
                                retry_opts["socket_timeout"] = 90  # Very long timeout
                                retry_opts["retries"] = 30  # Many fragment retries
                                retry_opts["fragment_retries"] = 30
                                # Use gzip-safe headers (no brotli)
                                retry_opts["http_headers"] = self.opts["http_headers"].copy()
                                retry_opts["http_headers"]["Referer"] = referer
                                retry_opts["http_headers"]["Accept-Encoding"] = "gzip, deflate"
                                retry_opts["http_headers"]["Origin"] = referer.rstrip('/').rsplit('/', 1)[0] if referer.count('/') > 2 else referer
                                
                                # Progressive backoff: wait before retry
                                if attempt > 1:
                                    wait_time = wait_times[min(attempt - 2, len(wait_times) - 1)]
                                    LOGGER.info(f"⏳ Waiting {wait_time}s before retry {attempt}/3 (CDN blocking backoff)...")
                                    sleep(wait_time)
                                
                                with YoutubeDL(retry_opts) as ydl_retry:
                                    LOGGER.info(f"🔄 HTTP 522 retry {attempt}/3 with gzip-safe headers...")
                                    ydl_retry.download([link])
                                return  # Success on retry
                            except Exception as retry_e:
                                retry_msg = str(retry_e).lower()
                                if attempt < 3:
                                    LOGGER.warning(f"⚠️ Retry {attempt} failed, trying again...")
                                    continue
                                else:
                                    LOGGER.error(f"❌ HTTP 522 all retries exhausted: {str(retry_e)[:100]}")
                                    break
                    
                    # NEW: Handle gzip/brotli decompression errors - RETRY with gzip-only
                    if "inconsistent stream state" in error_msg or "error -2 while decompressing" in error_msg or "failed to decode" in error_msg:
                        LOGGER.warning(f"🔄 Gzip decompression error detected, retrying with gzip-only headers...")
                        # Retry with modified options - force gzip only
                        for attempt in range(1, 3):  # 2 attempts for decompression
                            try:
                                retry_opts = self.opts.copy()
                                retry_opts["http_headers"] = self.opts["http_headers"].copy()
                                # CRITICAL: Use gzip only, no brotli
                                retry_opts["http_headers"]["Accept-Encoding"] = "gzip"
                                retry_opts["http_headers"]["Referer"] = referer
                                retry_opts["socket_timeout"] = 90  # Very long timeout
                                retry_opts["retries"] = 20
                                
                                if attempt > 1:
                                    sleep(5)  # Brief wait
                                
                                with YoutubeDL(retry_opts) as ydl_retry:
                                    LOGGER.info(f"🔄 Gzip retry {attempt}/2 (gzip-only mode)...")
                                    ydl_retry.download([link])
                                return  # Success on retry
                            except Exception as retry_e:
                                if attempt < 2:
                                    LOGGER.warning(f"⚠️ Gzip retry {attempt} failed, trying once more...")
                                    continue
                                else:
                                    LOGGER.error(f"❌ Gzip retry failed: {str(retry_e)[:100]}")
                    
                    # Handle SABR + n-challenge (only images available)
                    if "only images" in error_msg or "requested format is not available" in error_msg:
                        LOGGER.warning(f"⚠️ SABR/n-challenge detected, trying fallback format...")
                        fallback_opts = self.opts.copy()
                        fallback_opts["format"] = "best"
                        try:
                            with YoutubeDL(fallback_opts) as ydl_fallback:
                                ydl_fallback.download([link])
                            return  # Success with fallback
                        except Exception as fallback_e:
                            LOGGER.error(f"❌ Fallback failed: {str(fallback_e)}")
                    
                    # Handle TLS connection errors (FFmpeg or network issues)
                    if "tls" in error_msg or "error in the pull function" in error_msg or "input/output error" in error_msg or "certificate" in error_msg:
                        LOGGER.warning(f"⚠️ TLS/connection error detected, retrying with native HLS + longer timeout...")
                        tls_opts = self.opts.copy()
                        tls_opts["socket_timeout"] = 60  # Longer timeout for TLS handshake
                        tls_opts["retries"] = 30  # More retries
                        tls_opts["fragment_retries"] = 30
                        tls_opts["hls_prefer_native"] = True  # Use native HLS (better TLS handling)
                        tls_opts["hls_use_mpegts"] = False
                        tls_opts["http_headers"] = self.opts["http_headers"].copy()
                        tls_opts["http_headers"]["Referer"] = referer
                        # Add connection persistence headers
                        tls_opts["http_headers"]["Connection"] = "keep-alive"
                        try:
                            with YoutubeDL(tls_opts) as ydl_tls:
                                LOGGER.info(f"🔄 Retry with native HLS (TLS fix)...")
                                ydl_tls.download([link])
                            return
                        except Exception as tls_e:
                            LOGGER.error(f"❌ TLS retry failed: {str(tls_e)[:100]}")
                    
                    # Handle HLS-specific errors - we're using native HLS, but try with more aggressive settings
                    if "hls" in error_msg or "m3u8" in error_msg or ("http error" in error_msg and "fragment" in error_msg):
                        LOGGER.warning(f"⚠️ HLS error detected, retrying with more aggressive settings...")
                        hls_opts = self.opts.copy()
                        hls_opts["socket_timeout"] = 60
                        hls_opts["retries"] = 30
                        hls_opts["fragment_retries"] = 30
                        hls_opts["hls_prefer_native"] = True  # Use native HLS
                        hls_opts["hls_use_mpegts"] = False
                        hls_opts["http_headers"] = self.opts["http_headers"].copy()
                        hls_opts["http_headers"]["Referer"] = referer
                        try:
                            with YoutubeDL(hls_opts) as ydl_hls:
                                LOGGER.info(f"🔄 HLS retry with aggressive settings (native HLS)...")
                                ydl_hls.download([link])
                            return
                        except Exception as hls_e:
                            LOGGER.error(f"❌ HLS native retry also failed: {str(hls_e)[:100]}")
                    
                    # Handle brotli errors
                    if "brotli" in error_msg or "decoder failed" in error_msg or "unknown compression" in error_msg:
                        LOGGER.error("❌ brotli decoder error. Admin must fix:\n  apt-get install -y python3-brotli\n  pip install --upgrade brotli")
                    
                    # Handle n-challenge JS errors
                    if "n challenge" in error_msg or "javascript" in error_msg or "js runtime" in error_msg:
                        LOGGER.error("❌ n-challenge JS solving failed.\n  Admin setup: apt-get install -y nodejs npm && npm install -g deno")
                    
                    # Handle connection timeout errors - retry once more
                    if "timeout" in error_msg or "connection reset" in error_msg or "connection refused" in error_msg:
                        LOGGER.warning(f"⚠️ Connection timeout, retrying...")
                        timeout_opts = self.opts.copy()
                        timeout_opts["socket_timeout"] = 60
                        timeout_opts["retries"] = 20
                        try:
                            with YoutubeDL(timeout_opts) as ydl_timeout:
                                ydl_timeout.download([link])
                            return
                        except Exception:
                            pass  # Continue to error reporting
                    
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
                raise ValueError
            async_to_sync(self.__listener.onDownloadComplete)
        except ValueError:
            self.__onDownloadError("Download Stopped by User!")

    async def add_download(self, link, path, name, qual, playlist, options):
        if playlist:
            self.opts["ignoreerrors"] = True
            self.is_playlist = True

        self.__gid = token_hex(5)
        await self.__onDownloadStart()

        # Set postprocessors
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

        self.opts["format"] = qual

        # Process user options (string)
        if options:
            self.__set_options(options)

        await sync_to_async(self.extractMetaData, link, name)
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
            # This case may not be used in original, but kept for compatibility
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
                "writeautomaticsub",
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

        if self.__listener.isLeech:
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
                    "already_have_thumbnail": self.__listener.isLeech,
                    "key": "EmbedThumbnail",
                }
            )
        elif not self.__listener.isLeech:
            self.opts["writethumbnail"] = False

        msg, button = await stop_duplicate_check(self.name, self.__listener)
        if msg:
            await self.__listener.onDownloadError(msg, button)
            return
        if limit_exceeded := await limit_checker(
            self.__size, self.__listener, isYtdlp=True, isPlayList=self.playlist_count
        ):
            await self.__listener.onDownloadError(limit_exceeded)
            return
        added_to_queue, event = await is_queued(self.__listener.uid)
        if added_to_queue:
            LOGGER.info(f"Added to Queue/Download: {self.name}")
            async with download_dict_lock:
                download_dict[self.__listener.uid] = QueueStatus(
                    self.name, self.__size, self.__gid, self.__listener, "dl"
                )
            await event.wait()
            async with download_dict_lock:
                if self.__listener.uid not in download_dict:
                    return
            LOGGER.info(f"Start Queued Download from YT_DLP: {self.name}")
            await self.__onDownloadStart(True)
        else:
            LOGGER.info(f"Download with YT_DLP: {self.name}")

        async with queue_dict_lock:
            non_queued_dl.add(self.__listener.uid)

        await sync_to_async(self.__download, link, path)

    async def cancel_download(self):
        self.__is_cancelled = True
        LOGGER.info(f"Cancelling Download: {self.name}")
        if not self.__downloading:
            await self.__listener.onDownloadError("Download Cancelled by User!")

    def __set_options(self, options):
        options = options.split("|")
        for opt in options:
            key, value = map(str.strip, opt.split(":", 1))
            if key == "format" and value.startswith("ba/b-"):
                continue
            if value.startswith("^"):
                if "." in value or value == "^inf":
                    value = float(value.split("^", 1)[1])
                else:
                    value = int(value.split("^", 1)[1])
            elif value.lower() == "true":
                value = True
            elif value.lower() == "false":
                value = False
            elif value.startswith(("{", "[", "(")) and value.endswith(("}", "]", ")")):
                value = eval(value)

            if key == "postprocessors":
                if isinstance(value, list):
                    self.opts[key].extend(tuple(value))
                elif isinstance(value, dict):
                    self.opts[key].append(value)
            else:
                if key == "writethumbnail" and value is True:
                    self.keep_thumb = True
                self.opts[key] = value
