#!/usr/bin/env python3
from contextlib import suppress
from re import findall, search, IGNORECASE

import cloudscraper
from imdbinfo import search_title, get_movie
from pycountry import countries as conn
from pyrogram.errors import MediaEmpty, PhotoInvalidDimensions, WebpageMediaEmpty
from pyrogram.handlers import MessageHandler, CallbackQueryHandler
from pyrogram.filters import command, regex
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot import bot, LOGGER, user_data, config_dict
from bot.helper.telegram_helper.filters import CustomFilters
from bot.helper.telegram_helper.bot_commands import BotCommands
from bot.helper.telegram_helper.message_utils import sendMessage, editMessage, deleteMessage
from bot.helper.ext_utils.bot_utils import get_readable_time, sync_to_async
from bot.helper.telegram_helper.button_build import ButtonMaker

IMDB_GENRE_EMOJI = {
    "Action": "🚀",
    "Adult": "🔞",
    "Adventure": "🌋",
    "Animation": "🎠",
    "Biography": "📜",
    "Comedy": "🪗",
    "Crime": "🔪",
    "Documentary": "🎞",
    "Drama": "🎭",
    "Family": "👨‍👩‍👧‍👦",
    "Fantasy": "🫧",
    "Film Noir": "🎯",
    "Game Show": "🎮",
    "History": "🏛",
    "Horror": "🧟",
    "Musical": "🎻",
    "Music": "🎸",
    "Mystery": "🧳",
    "News": "📰",
    "Reality-TV": "🖥",
    "Romance": "🥰",
    "Sci-Fi": "🌠",
    "Short": "📝",
    "Sport": "⛳",
    "Talk-Show": "👨‍🍳",
    "Thriller": "🗡",
    "War": "⚔",
    "Western": "🪩",
}
LIST_ITEMS = 4


async def imdb_search(_, message):
    if " " in message.text:
        k = await sendMessage(message, "<i>Searching IMDB ...</i>")
        title = message.text.split(" ", 1)[1]
        user_id = message.from_user.id
        buttons = ButtonMaker()
        if result := search(r"tt(\d+)", title, IGNORECASE):
            movieid = result.group(1)
            if movie := await sync_to_async(get_movie, movieid):
                buttons.ibutton(
                    f"🎬 {movie.title} ({getattr(movie, 'year', 'N/A')})",
                    f"imdb {user_id} movie {movieid}",
                )
            else:
                return await editMessage(k, "<i>No Results Found</i>")
        else:
            movies = await sync_to_async(get_poster, title, bulk=True)
            if not movies:
                return await editMessage(
                    k, "<i>No Results Found</i>, Try Again or Use <b>Title ID</b>"
                )
            for movie in movies:
                buttons.ibutton(
                    f"🎬 {movie.title} ({getattr(movie, 'year', 'N/A')})",
                    f"imdb {user_id} movie {movie.id}",
                )
        buttons.ibutton("🚫 Close 🚫", f"imdb {user_id} close")
        await editMessage(
            k, "<b><i>Search Results found on IMDb.com</i></b>", buttons.build_menu(1)
        )
    else:
        await sendMessage(
            message,
            "<i>Send Movie / TV Series Name along with /imdb Command or send IMDB URL</i>",
        )


def get_poster(query, bulk=False, id=False, file=None):
    if not id:
        query = (query.strip()).lower()
        title = query
        year = findall(r"[1-2]\d{3}$", query, IGNORECASE)
        if year:
            year = list_to_str(year[:1])
            title = (query.replace(year, "")).strip()
        elif file is not None:
            year = findall(r"[1-2]\d{3}", file, IGNORECASE)
            if year:
                year = list_to_str(year[:1])
        else:
            year = None
        movieid = search_title(title.lower()).titles
        if not movieid:
            return None
        if year:
            filtered = (
                list(filter(lambda k: str(k.year or "") == str(year), movieid))
                or movieid
            )
        else:
            filtered = movieid
        movieid = (
            list(filter(lambda k: k.kind in ["movie", "tvSeries"], filtered))
            or filtered
        )
        if bulk:
            return movieid
        movieid = movieid[0].id
    else:
        movieid = query
    movie = get_movie(movieid)
    if getattr(movie, "release_date", None):
        date = movie.release_date
    elif getattr(movie, "year", None):
        date = movie.year
    else:
        date = "N/A"

    plot = None
    for keyword in ["plot", "summaries", "synopses"]:
        plot_data = getattr(movie, keyword, None)
        if isinstance(plot_data, list):
            plot = plot_data[0]
        else:
            plot = plot_data
        if plot:
            break
    if plot and len(plot) > 300:
        plot = f"{plot[:300]}..."

    trailer_list = getattr(movie, "trailers", None)
    trailer = trailer_list[-1] if trailer_list else None

    return {
        "title": movie.title,
        "trailer": trailer or "https://imdb.com/",
        "votes": str(getattr(movie, "votes", "N/A") or "N/A"),
        "aka": list_to_str(getattr(movie, "title_akas", []) or []) or "N/A",
        "seasons": (
            len(movie.info_series.display_seasons)
            if getattr(movie, "info_series", None)
            and getattr(movie.info_series, "display_seasons", None)
            else "N/A"
        ),
        "box_office": getattr(movie, "worldwide_gross", "N/A") or "N/A",
        "localized_title": getattr(movie, "title_localized", "N/A") or "N/A",
        "kind": (getattr(movie, "kind", "N/A") or "N/A").capitalize(),
        "imdb_id": f"tt{movie.imdb_id}",
        "cast": list_to_str([i.name for i in getattr(movie, "stars", [])]) or "N/A",
        "runtime": get_readable_time(int(getattr(movie, "duration", 0) or "0") * 60)
        or "N/A",
        "countries": list_to_hash(getattr(movie, "countries", []) or [], flagg=True) or "N/A",
        "languages": list_to_hash(getattr(movie, "languages_text", []) or []) or "N/A",
        "director": list_to_str([i.name for i in getattr(movie, "directors", [])]) or "N/A",
        "writer": list_to_str(
            [i.name for i in getattr(movie, "categories", {}).get("writer", [])]
        ) or "N/A",
        "producer": list_to_str(
            [i.name for i in getattr(movie, "categories", {}).get("producer", [])]
        ) or "N/A",
        "composer": list_to_str(
            [i.name for i in getattr(movie, "categories", {}).get("composer", [])]
        ) or "N/A",
        "cinematographer": list_to_str(
            [i.name for i in getattr(movie, "categories", {}).get("cinematographer", [])]
        ) or "N/A",
        "music_team": list_to_str(
            [i.name for i in getattr(movie, "categories", {}).get("music_department", [])]
        ) or "N/A",
        "distributors": "N/A",
        "release_date": getattr(movie, "release_date", "N/A") or "N/A",
        "year": str(getattr(movie, "year", "N/A") or "N/A"),
        "genres": list_to_hash(getattr(movie, "genres", []) or [], emoji=True) or "N/A",
        "poster": getattr(
            movie, "cover_url", "https://telegra.ph/file/5af8d90a479b0d11df298.jpg"
        ) or "https://telegra.ph/file/5af8d90a479b0d11df298.jpg",
        "plot": plot or "N/A",
        "rating": str(getattr(movie, "rating", "N/A") or "N/A") + " / 10",
        "url": getattr(movie, "url", "N/A") or "N/A",
        "url_cast": f"https://www.imdb.com/title/tt{movieid}/fullcredits#cast",
        "url_releaseinfo": f"https://www.imdb.com/title/tt{movieid}/releaseinfo",
    }


def list_to_str(k):
    if not k:
        return ""
    elif len(k) == 1:
        return str(k[0])
    elif LIST_ITEMS:
        k = k[: int(LIST_ITEMS)]
        return " ".join(f"{elem}," for elem in k)[:-1] + " ..."
    else:
        return " ".join(f"{elem}," for elem in k)[:-1]


def list_to_hash(k, flagg=False, emoji=False):
    listing = ""
    if not k:
        return ""
    elif len(k) == 1:
        if not flagg:
            if emoji:
                return str(
                    IMDB_GENRE_EMOJI.get(k[0], "")
                    + " #"
                    + k[0].replace(" ", "_").replace("-", "_")
                )
            return str("#" + k[0].replace(" ", "_").replace("-", "_"))
        try:
            conflag = (conn.get(name=k[0])).flag
            return str(f"{conflag} #" + k[0].replace(" ", "_").replace("-", "_"))
        except AttributeError:
            return str("#" + k[0].replace(" ", "_").replace("-", "_"))
    elif LIST_ITEMS:
        k = k[: int(LIST_ITEMS)]
        for elem in k:
            ele = elem.replace(" ", "_").replace("-", "_")
            if flagg:
                with suppress(AttributeError):
                    conflag = (conn.get(name=elem)).flag
                    listing += f"{conflag} "
            if emoji:
                listing += f"{IMDB_GENRE_EMOJI.get(elem, '')} "
            listing += f"#{ele}, "
        return f"{listing[:-2]}"
    else:
        for elem in k:
            ele = elem.replace(" ", "_").replace("-", "_")
            if flagg:
                with suppress(AttributeError):
                    conflag = (conn.get(name=elem)).flag
                    listing += f"{conflag} "
            listing += f"#{ele}, "
        return listing[:-2]


async def imdb_callback(_, query):
    message = query.message
    user_id = query.from_user.id
    data = query.data.split()
    if user_id != int(data[1]):
        await query.answer("Not Yours!", show_alert=True)
    elif data[2] == "movie":
        await query.answer()
        imdb = await sync_to_async(get_poster, data[3], id=True)
        buttons = ButtonMaker()
        if imdb["trailer"]:
            if isinstance(imdb["trailer"], list):
                buttons.ubutton("▶️ IMDb Trailer", str(imdb["trailer"][-1]))
                imdb["trailer"] = list_to_str(imdb["trailer"])
            else:
                buttons.ubutton("▶️ IMDb Trailer", str(imdb["trailer"]))
        buttons.ibutton("🚫 Close 🚫", f"imdb {user_id} close")
        reply_markup = buttons.build_menu(1)
        template = config_dict.get("IMDB_TEMPLATE", "")
        if imdb and template:
            try:
                cap = template.format(**imdb, **locals())
            except KeyError:
                cap = template.format(
                    title=imdb["title"],
                    trailer=imdb["trailer"],
                    votes=imdb["votes"],
                    aka=imdb["aka"],
                    seasons=imdb["seasons"],
                    box_office=imdb["box_office"],
                    localized_title=imdb["localized_title"],
                    kind=imdb["kind"],
                    imdb_id=imdb["imdb_id"],
                    cast=imdb["cast"],
                    runtime=imdb["runtime"],
                    countries=imdb["countries"],
                    languages=imdb["languages"],
                    director=imdb["director"],
                    writer=imdb["writer"],
                    producer=imdb["producer"],
                    composer=imdb["composer"],
                    cinematographer=imdb["cinematographer"],
                    music_team=imdb["music_team"],
                    distributors=imdb["distributors"],
                    release_date=imdb["release_date"],
                    year=imdb["year"],
                    genres=imdb["genres"],
                    poster=imdb["poster"],
                    plot=imdb["plot"],
                    rating=imdb["rating"],
                    url=imdb["url"],
                    url_cast=imdb["url_cast"],
                    url_releaseinfo=imdb["url_releaseinfo"],
                    **locals(),
                )
        else:
            cap = "No Results"
        if imdb.get("poster"):
            try:
                await bot.send_photo(
                    chat_id=query.message.reply_to_message.chat.id,
                    caption=cap,
                    photo=imdb["poster"],
                    reply_to_message_id=query.message.reply_to_message.id,
                    reply_markup=reply_markup,
                )
            except (MediaEmpty, PhotoInvalidDimensions, WebpageMediaEmpty):
                poster = imdb.get("poster").replace(".jpg", "._V1_UX360.jpg")
                await sendMessage(
                    message.reply_to_message, cap, reply_markup, poster
                )
        else:
            await sendMessage(
                message.reply_to_message,
                cap,
                reply_markup,
                "https://telegra.ph/file/5af8d90a479b0d11df298.jpg",
            )
        await deleteMessage(message)
    else:
        await query.answer()
        await deleteMessage(message)
        if message.reply_to_message:
            await deleteMessage(message.reply_to_message)


bot.add_handler(
    MessageHandler(
        imdb_search,
        filters=command(BotCommands.IMDBCommand)
        & CustomFilters.authorized
        & ~CustomFilters.blacklisted,
    )
)
bot.add_handler(CallbackQueryHandler(imdb_callback, filters=regex(r"^imdb")))
