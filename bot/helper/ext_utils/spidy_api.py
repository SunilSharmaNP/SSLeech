#!/usr/bin/env python3
import re
import aiohttp
from os import path as ospath
from time import time
from PIL import Image
from io import BytesIO
from aiofiles.os import makedirs, path as aiopath
from logging import getLogger

LOGGER = getLogger(__name__)
SPIDY_API_BASE = "https://poster-api.ispidy.com/v1/fetch"

_BOT_PREFIX_RE = re.compile(
    r'^(?:[\[\(][A-Za-z0-9@_\-]{1,20}[\]\)]\s*(?:[\|\-:]\s*)?'
    r'|[A-Za-z0-9@_\-]{1,20}\s*[\|\-:]\s*)',
    re.IGNORECASE,
)

_QUALITY_TAGS = [
    r'[Ss]\d{1,2}[Ee]\d{1,2}',
    r'[Ss]eason[\s._-]*\d{1,2}',
    r'(19|20)\d{2}',
    r'\d{3,4}p',
    r'BluRay', r'Blu[-.]?Ray',
    r'WEBRip', r'WEB[-.]DL', r'WEBDL',
    r'AMZN', r'NF', r'DSNP', r'ATVP', r'HMAX',
    r'HDTV', r'HDRip', r'DVDRip', r'BDRip',
    r'x264', r'x265', r'HEVC', r'AVC', r'H\.264', r'H\.265',
    r'AAC', r'DD[+\.]?5', r'DTS', r'Atmos', r'TrueHD',
    r'CVBR', r'ESub', r'MSub', r'Multi',
]


def parse_filename_for_search(filename):
    """Extract title, year and season from filename for Spidy API search."""
    name = ospath.splitext(ospath.basename(filename))[0]

    name = _BOT_PREFIX_RE.sub('', name).strip()

    year_match = re.search(r'(19|20)\d{2}', name)
    year = year_match.group(0) if year_match else None

    season_match = re.search(
        r'[Ss](\d{1,2})[Ee]\d|[Ss]eason[\s._-]*(\d{1,2})',
        name,
        re.IGNORECASE,
    )
    season = None
    if season_match:
        season = (season_match.group(1) or season_match.group(2)).lstrip('0') or '1'

    earliest_pos = len(name)
    for pattern in _QUALITY_TAGS:
        m = re.search(pattern, name, re.IGNORECASE)
        if m and m.start() < earliest_pos:
            earliest_pos = m.start()

    title_part = name[:earliest_pos]

    title = re.sub(r'[._\-\+]', ' ', title_part).strip()
    title = re.sub(r'\s+', ' ', title).strip()
    title = re.sub(r'[\[\(\]\)]', '', title).strip()

    return title, year, season


async def fetch_spidy_assets(title, api_key, year=None, season=None, limit=6):
    """
    Fetch ALL available poster assets (landscape + portrait) for a title from
    Spidy API, for use by the /poster command.

    Note: as of the live API, results only ever contain "landscape" and
    (rarely) "poster" (portrait) keys — there is no logo/PNG asset in the
    Spidy API response, so this never returns logos.

    Returns a dict: {"title": str, "year": str|None, "landscape": [urls],
    "poster": [urls]} or None on failure / no results.
    """
    if not api_key:
        LOGGER.warning("Spidy API: No API key configured")
        return None
    if not title:
        return None

    params = {"api_key": api_key, "title": title}
    if year:
        params["year"] = year
    if season:
        params["season"] = season

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                SPIDY_API_BASE,
                params=params,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status == 401:
                    LOGGER.error("Spidy API: Invalid API key (401)")
                    return None
                if resp.status == 404:
                    return None
                if resp.status == 429:
                    LOGGER.warning("Spidy API: Rate limit hit (429)")
                    return None
                if resp.status != 200:
                    LOGGER.warning(f"Spidy API: Unexpected status {resp.status}")
                    return None
                data = await resp.json()

        results = data.get("results", [data]) if data.get("results") is not None else [data]
        if not results:
            return None

        landscape_urls, poster_urls = [], []
        resolved_title, resolved_year = title, year
        for r in results:
            if r.get("title"):
                resolved_title = r["title"]
            if r.get("year") and not resolved_year:
                resolved_year = r["year"]
            if r.get("landscape") and r["landscape"] not in landscape_urls:
                landscape_urls.append(r["landscape"])
            if r.get("poster") and r["poster"] not in poster_urls:
                poster_urls.append(r["poster"])

        if not landscape_urls and not poster_urls:
            return None

        return {
            "title": resolved_title,
            "year": resolved_year,
            "landscape": landscape_urls[:limit],
            "poster": poster_urls[:limit],
        }

    except aiohttp.ClientConnectorError as e:
        LOGGER.error(f"Spidy API: Connection error — {e}")
        return None
    except Exception as e:
        LOGGER.error(f"Spidy API: Unexpected error fetching assets for '{title}': {e}", exc_info=True)
        return None


async def fetch_spidy_poster(filename, api_key):
    """
    Fetch a landscape poster from Spidy API using the leech filename.
    Returns local JPEG file path of downloaded poster, or None on failure.
    """
    if not api_key:
        LOGGER.warning("Spidy API: No API key configured")
        return None

    title, year, season = parse_filename_for_search(filename)
    LOGGER.info(f"Spidy API: Parsed — title='{title}' year={year} season={season} from '{ospath.basename(filename)}'")

    if not title:
        LOGGER.info(f"Spidy API: Could not parse title from '{filename}', skipping")
        return None

    params = {"api_key": api_key, "title": title}
    if year:
        params["year"] = year
    if season:
        params["season"] = season

    LOGGER.info(f"Spidy API: Requesting with params {params}")

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                SPIDY_API_BASE,
                params=params,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status == 401:
                    LOGGER.error("Spidy API: Invalid API key (401)")
                    return None
                if resp.status == 429:
                    LOGGER.warning("Spidy API: Rate limit hit (429)")
                    return None
                if resp.status != 200:
                    LOGGER.warning(f"Spidy API: Unexpected status {resp.status}")
                    return None

                data = await resp.json()
                LOGGER.info(f"Spidy API: Raw response: {str(data)[:300]}")

            landscape_url = None
            results = data.get("results", [])
            if results:
                for result in results:
                    if result.get("landscape"):
                        landscape_url = result["landscape"]
                        break
            elif data.get("landscape"):
                landscape_url = data["landscape"]

            if not landscape_url:
                LOGGER.info(f"Spidy API: No landscape poster in response for title='{title}'")
                if not results and year:
                    LOGGER.info("Spidy API: Retrying without year...")
                    params_no_year = {"api_key": api_key, "title": title}
                    if season:
                        params_no_year["season"] = season
                    async with session.get(
                        SPIDY_API_BASE,
                        params=params_no_year,
                        timeout=aiohttp.ClientTimeout(total=15),
                    ) as resp2:
                        if resp2.status == 200:
                            data2 = await resp2.json()
                            results2 = data2.get("results", [])
                            for r in results2:
                                if r.get("landscape"):
                                    landscape_url = r["landscape"]
                                    break
                            if not landscape_url and data2.get("landscape"):
                                landscape_url = data2["landscape"]

            if not landscape_url:
                LOGGER.info(f"Spidy API: No poster found for '{title}'")
                return None

            LOGGER.info(f"Spidy API: Downloading poster from {landscape_url}")

            async with session.get(
                landscape_url,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as img_resp:
                if img_resp.status != 200:
                    LOGGER.warning(f"Spidy API: Image download failed (HTTP {img_resp.status})")
                    return None
                img_data = await img_resp.read()

        save_dir = "Thumbnails/spidy_cache"
        if not await aiopath.isdir(save_dir):
            await makedirs(save_dir, exist_ok=True)

        temp_path = f"{save_dir}/{int(time())}.jpg"
        img = Image.open(BytesIO(img_data)).convert("RGB")
        img.save(temp_path, "JPEG", quality=95)

        LOGGER.info(f"Spidy API: Poster saved to {temp_path}")
        return temp_path

    except aiohttp.ClientConnectorError as e:
        LOGGER.error(f"Spidy API: Connection error — {e}")
        return None
    except Exception as e:
        LOGGER.error(f"Spidy API: Unexpected error for '{filename}': {e}", exc_info=True)
        return None
