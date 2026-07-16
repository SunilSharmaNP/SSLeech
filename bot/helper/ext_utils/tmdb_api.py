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

# TMDB's `include_image_language` filter has NO real "all languages"
# wildcard — a bare "*" is silently ignored, so a short list like
# "en,hi,null" only ever returns logos tagged with exactly those languages
# and drops every other-language logo for the title (this is why a movie
# could have a valid PNG logo on TMDB that still came back empty: it was
# tagged e.g. "fr"/"ja"/etc., not "en"/"hi"/null). Backdrops mostly have no
# language tag so they aren't affected the same way, which is why they
# kept working while logos silently disappeared.
# The only reliable workaround (used by most TMDB client libraries) is to
# explicitly list every ISO 639-1 code TMDB recognizes, plus "null" for
# untagged images, so nothing gets filtered out.
_ISO_639_1_CODES = (
    "aa,ab,ae,af,ak,am,an,ar,as,av,ay,az,ba,be,bg,bh,bi,bm,bn,bo,br,bs,ca,ce,"
    "ch,co,cr,cs,cu,cv,cy,da,de,dv,dz,ee,el,en,eo,es,et,eu,fa,ff,fi,fj,fo,fr,"
    "fy,ga,gd,gl,gn,gu,gv,ha,he,hi,ho,hr,ht,hu,hy,hz,ia,id,ie,ig,ii,ik,io,is,"
    "it,iu,ja,jv,ka,kg,ki,kj,kk,kl,km,kn,ko,kr,ks,ku,kv,kw,ky,la,lb,lg,li,ln,"
    "lo,lt,lu,lv,mg,mh,mi,mk,ml,mn,mr,ms,mt,my,na,nb,nd,ne,ng,nl,nn,no,nr,nv,"
    "ny,oc,oj,om,or,os,pa,pi,pl,ps,pt,qu,rm,rn,ro,ru,rw,sa,sc,sd,se,sg,si,sk,"
    "sl,sm,sn,so,sq,sr,ss,st,su,sv,sw,ta,te,tg,th,ti,tk,tl,tn,to,tr,ts,tt,tw,"
    "ty,ug,uk,ur,uz,ve,vi,vo,wa,wo,xh,yi,yo,za,zh,zu"
)
LOGO_LANGUAGE_FILTER = f"null,{_ISO_639_1_CODES}"


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
