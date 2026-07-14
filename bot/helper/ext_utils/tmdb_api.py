#!/usr/bin/env python3
"""
TMDB (The Movie Database) integration — used only to fetch a transparent
PNG "clear logo" for a movie/show, which the Spidy poster API doesn't
provide at all (it only ever returns landscape/portrait poster images).

Get a free API key at https://www.themoviedb.org/settings/api and set it
as TMDB_API_KEY (env var / /botsettings -> Config Variables).
"""
import aiohttp
from logging import getLogger

LOGGER = getLogger(__name__)

TMDB_API_BASE = "https://api.themoviedb.org/3"
TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p/original"


async def fetch_tmdb_assets(title, api_key, year=None, limit=15):
    """
    Search TMDB for `title` (movie or TV show) and return:
      - ALL of its PNG clear logos (every language TMDB has one for —
        English, Hindi, native script, etc.), not just a single "best" pick.
      - ALL of its raw backdrop/landscape images (the plain widescreen
        scene shots TMDB stores, with no title text burned in) — this is
        the "RAW Landscape" section other poster bots show, and it's a
        completely different TMDB asset type than Spidy's single
        landscape image.

    Returns {"logos": [url, ...], "backdrops": [url, ...], "title": str,
    "year": str|None} or None if TMDB has no result at all for the title.
    `logos`/`backdrops` can independently be empty lists if TMDB simply
    doesn't have that asset type for this title (never a placeholder).
    """
    if not api_key:
        LOGGER.warning("TMDB API: No API key configured")
        return None
    if not title:
        return None

    try:
        async with aiohttp.ClientSession() as session:
            media_type, media_id, resolved_title, resolved_year = await _search(
                session, api_key, title, year
            )
            if not media_id:
                return None

            logo_urls, backdrop_urls = await _fetch_images(
                session, api_key, media_type, media_id
            )

            return {
                "logos": logo_urls[:limit],
                "backdrops": backdrop_urls[:limit],
                "title": resolved_title,
                "year": resolved_year,
            }

    except aiohttp.ClientConnectorError as e:
        LOGGER.error(f"TMDB API: Connection error — {e}")
        return None
    except Exception as e:
        LOGGER.error(f"TMDB API: Unexpected error fetching assets for '{title}': {e}", exc_info=True)
        return None


async def _search(session, api_key, title, year):
    params = {"api_key": api_key, "query": title, "include_adult": "false"}
    if year:
        params["year"] = year

    async with session.get(
        f"{TMDB_API_BASE}/search/multi",
        params=params,
        timeout=aiohttp.ClientTimeout(total=15),
    ) as resp:
        if resp.status == 401:
            LOGGER.error("TMDB API: Invalid API key (401)")
            return None, None, title, year
        if resp.status != 200:
            LOGGER.warning(f"TMDB API: Unexpected search status {resp.status}")
            return None, None, title, year
        data = await resp.json()

    results = [
        r for r in data.get("results", []) if r.get("media_type") in ("movie", "tv")
    ]
    if not results and year:
        # Retry without the year — TMDB search is exact-year sensitive and
        # a mismatched/guessed year should not throw away an otherwise
        # good match.
        return await _search(session, api_key, title, None)
    if not results:
        return None, None, title, year

    best = results[0]
    media_type = best["media_type"]
    resolved_title = best.get("title") or best.get("name") or title
    date = best.get("release_date") or best.get("first_air_date") or ""
    resolved_year = date[:4] if date else year
    return media_type, best["id"], resolved_title, resolved_year


def _dedup_sorted_urls(images):
    """Highest-voted first; TMDB already sorts by vote_average descending,
    but sort explicitly to be safe. Duplicate file_paths (can happen across
    language variants pointing at the same asset) are dropped."""
    images = sorted(images, key=lambda i: i.get("vote_average", 0), reverse=True)
    seen = set()
    urls = []
    for i in images:
        fp = i["file_path"]
        if fp in seen:
            continue
        seen.add(fp)
        urls.append(f"{TMDB_IMAGE_BASE}{fp}")
    return urls


async def _fetch_images(session, api_key, media_type, media_id):
    """Return (logo_urls, backdrop_urls) for this title in one TMDB call:
      - logos: PNG clear logos across all languages (English, Hindi,
        native-script, no-language, etc.) — TMDB logos are also sometimes
        SVG-only, those are skipped since Telegram can't render them.
      - backdrops: raw widescreen scene shots with no text overlay — TMDB
        stores these separately from logos/posters, and it's what "RAW
        Landscape" sections in other poster bots are built from. All
        languages/no-language backdrops are included, same as TMDB itself
        lists them.
    """
    params = {"api_key": api_key, "include_image_language": "en,hi,null,*"}
    async with session.get(
        f"{TMDB_API_BASE}/{media_type}/{media_id}/images",
        params=params,
        timeout=aiohttp.ClientTimeout(total=15),
    ) as resp:
        if resp.status != 200:
            LOGGER.warning(f"TMDB API: Unexpected images status {resp.status}")
            return [], []
        data = await resp.json()

    logos = data.get("logos", []) or []
    png_logos = [l for l in logos if l.get("file_path", "").lower().endswith(".png")]
    logo_urls = _dedup_sorted_urls(png_logos)

    backdrops = data.get("backdrops", []) or []
    backdrop_urls = _dedup_sorted_urls(backdrops)

    return logo_urls, backdrop_urls
