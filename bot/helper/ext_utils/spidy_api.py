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


def parse_filename_for_search(filename):
    """Extract title, year and season from filename for Spidy API search."""
    name = ospath.splitext(filename)[0]

    year_match = re.search(r'(19|20)\d{2}', name)
    year = year_match.group(0) if year_match else None

    season_match = re.search(r'[Ss](\d{1,2})[Ee]\d|[Ss]eason[\s._-]*(\d{1,2})', name, re.IGNORECASE)
    season = None
    if season_match:
        season = (season_match.group(1) or season_match.group(2)).lstrip('0') or '1'

    title_part = name
    cut_patterns = [
        r'(19|20)\d{2}',
        r'[Ss]\d{1,2}[Ee]\d{1,2}',
        r'[Ss]eason[\s._-]*\d{1,2}',
        r'\d{3,4}p',
        r'BluRay', r'Blu-Ray',
        r'WEBRip', r'WEB-DL', r'WEB\.DL',
        r'HDTV', r'HDRip', r'DVDRip',
        r'x264', r'x265', r'HEVC', r'AVC',
        r'AAC', r'DD5', r'DTS',
    ]
    for pattern in cut_patterns:
        m = re.search(pattern, title_part, re.IGNORECASE)
        if m:
            title_part = title_part[:m.start()]
            break

    title = re.sub(r'[._\-]', ' ', title_part).strip()
    title = re.sub(r'\s+', ' ', title).strip()

    return title, year, season


async def fetch_spidy_poster(filename, api_key):
    """
    Fetch a landscape poster from Spidy API using the leech filename.
    Returns local JPEG file path of downloaded poster, or None on failure.
    """
    if not api_key:
        LOGGER.warning("Spidy API: No API key configured")
        return None

    title, year, season = parse_filename_for_search(filename)

    if title:
        params = {"api_key": api_key, "title": title}
        if year:
            params["year"] = year
        if season:
            params["season"] = season
    else:
        params = {"api_key": api_key, "query": filename}

    LOGGER.info(f"Spidy API search params: {params}")

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                SPIDY_API_BASE,
                params=params,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status == 401:
                    LOGGER.error("Spidy API: Invalid API key")
                    return None
                if resp.status == 429:
                    LOGGER.warning("Spidy API: Rate limit hit")
                    return None
                if resp.status != 200:
                    LOGGER.warning(f"Spidy API returned status {resp.status}")
                    return None

                data = await resp.json()

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
                LOGGER.info(f"Spidy API: No landscape poster found for '{filename}'")
                return None

            LOGGER.info(f"Spidy API: Poster URL found: {landscape_url}")

            async with session.get(
                landscape_url,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as img_resp:
                if img_resp.status != 200:
                    LOGGER.warning(f"Spidy API: Failed to download poster image (HTTP {img_resp.status})")
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

    except aiohttp.ClientConnectorError:
        LOGGER.error("Spidy API: Cannot connect to poster API server")
        return None
    except Exception as e:
        LOGGER.error(f"Spidy API error for '{filename}': {e}")
        return None
