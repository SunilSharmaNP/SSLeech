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

# TMDB's include_image_language controls which language-tagged assets are
# returned. Backdrops are typically untagged (null) so they always come
# through. Logos and posters carry real language codes (en, fr, ja, etc.)
# and are filtered by this param.
#
# Passing the full ISO 639-1 list (~180 codes, ~400 chars) causes TMDB to
# silently return 0 logos/posters — the server appears to bail on very long
# values. A curated short list of the languages TMDB actually stores logos
# for covers 99 %+ of real-world titles and stays well within TMDB's limits.
LOGO_LANGUAGE_FILTER = (
    "null,en,hi,fr,ja,ko,de,es,pt,ru,zh,it,ar,tr,pl,nl,sv,da,fi,cs,"
    "hu,ro,bg,hr,sk,uk,fa,he,th,id,vi,nb,el,sr,ms,ca,lt,et,lv,sl"
)


async def fetch_tmdb_assets(title, api_key, year=None, limit=15):
    """
    Search TMDB for `title` (movie or TV show) and return:
      - logos    : PNG/SVG clear logos (every language TMDB has).
      - backdrops: Raw widescreen scene shots with no title text burned in
                   ("RAW Landscape" — different from Spidy's landscape which
                   already has the movie logo overlaid).
      - posters  : Portrait poster images from TMDB.

    Returns {"logos": [...], "backdrops": [...], "posters": [...],
    "title": str, "year": str|None} or None if nothing found.
    Each list can be empty if TMDB has no asset of that type for this title.
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

            logo_urls, backdrop_urls, poster_urls = await _fetch_images(
                session, api_key, media_type, media_id
            )

            return {
                "logos": logo_urls[:limit],
                "backdrops": backdrop_urls[:limit],
                "posters": poster_urls[:limit],
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
    """Return (logo_urls, backdrop_urls, poster_urls) for this title in one
    TMDB call:
      - logos   : PNG/SVG clear logos across all languages. Both formats
                  accepted — TMDB stores many logos exclusively as SVG.
      - backdrops: raw widescreen shots with no title text (RAW Landscape).
      - posters : portrait poster images (all languages).
    """
    params = {"api_key": api_key, "include_image_language": LOGO_LANGUAGE_FILTER}
    async with session.get(
        f"{TMDB_API_BASE}/{media_type}/{media_id}/images",
        params=params,
        timeout=aiohttp.ClientTimeout(total=15),
    ) as resp:
        if resp.status != 200:
            LOGGER.warning(f"TMDB API: Unexpected images status {resp.status}")
            return [], [], []
        data = await resp.json()

    logos = data.get("logos", []) or []
    backdrops = data.get("backdrops", []) or []
    posters = data.get("posters", []) or []
    LOGGER.info(
        f"TMDB API: images response — {len(logos)} logos, "
        f"{len(backdrops)} backdrops, {len(posters)} posters "
        f"for {media_type}/{media_id}"
    )

    # Accept both .png AND .svg — TMDB itself says SVGs are preferred and
    # many titles only have SVG logos (no PNG variant). Both formats work
    # fine as clickable links in Telegram. Filtering to .png only was
    # silently dropping every SVG-only logo.
    valid_logo_exts = (".png", ".svg")
    filtered_logos = [
        l for l in logos
        if l.get("file_path", "").lower().endswith(valid_logo_exts)
    ]
    logo_urls = _dedup_sorted_urls(filtered_logos)
    backdrop_urls = _dedup_sorted_urls(backdrops)
    poster_urls = _dedup_sorted_urls(posters)

    return logo_urls, backdrop_urls, poster_urls
