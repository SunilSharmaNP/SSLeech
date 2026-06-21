from base64 import b64encode
from hashlib import sha256
from os import urandom, environ
from random import choice, random, randrange
from time import sleep, time
from urllib.parse import quote

from cloudscraper import create_scraper
from urllib3 import disable_warnings

from bot import LOGGER, shorteners_list


def short_url(longurl, attempt=0):
    if not shorteners_list:
        return longurl
    if attempt >= 4:
        return longurl
    i = 0 if len(shorteners_list) == 1 else randrange(len(shorteners_list))
    _shorten_dict = shorteners_list[i]
    _shortener = _shorten_dict["domain"]
    _shortener_api = _shorten_dict["api_key"]
    cget = create_scraper().request
    disable_warnings()
    try:
        if "shorte.st" in _shortener:
            headers = {"public-api-token": _shortener_api}
            data = {"urlToShorten": quote(longurl)}
            return cget(
                "PUT", "https://api.shorte.st/v1/data/url", headers=headers, data=data
            ).json()["shortenedUrl"]
        elif "linkvertise" in _shortener:
            url = quote(b64encode(longurl.encode("utf-8")))
            linkvertise = [
                f"https://link-to.net/{_shortener_api}/{random() * 1000}/dynamic?r={url}",
                f"https://up-to-down.net/{_shortener_api}/{random() * 1000}/dynamic?r={url}",
                f"https://direct-link.net/{_shortener_api}/{random() * 1000}/dynamic?r={url}",
                f"https://file-link.net/{_shortener_api}/{random() * 1000}/dynamic?r={url}",
            ]
            return choice(linkvertise)
        elif "bitly.com" in _shortener:
            headers = {"Authorization": f"Bearer {_shortener_api}"}
            return cget(
                "POST",
                "https://api-ssl.bit.ly/v4/shorten",
                json={"long_url": longurl},
                headers=headers,
            ).json()["link"]
        elif "ouo.io" in _shortener:
            return cget(
                "GET", f"http://ouo.io/api/{_shortener_api}?s={longurl}", verify=False
            ).text
        elif "cutt.ly" in _shortener:
            return cget(
                "GET",
                f"http://cutt.ly/api/api.php?key={_shortener_api}&short={longurl}",
            ).json()["url"]["shortLink"]
        else:
            res = cget(
                "GET",
                f"https://{_shortener}/api?api={_shortener_api}&url={quote(longurl)}",
            ).json()
            shorted = res["shortenedUrl"]
            if not shorted:
                shrtco_res = cget(
                    "GET", f"https://api.shrtco.de/v2/shorten?url={quote(longurl)}"
                ).json()
                shrtco_link = shrtco_res["result"]["full_short_link"]
                res = cget(
                    "GET",
                    f"https://{_shortener}/api?api={_shortener_api}&url={shrtco_link}",
                ).json()
                shorted = res["shortenedUrl"]
            if not shorted:
                shorted = longurl
            return shorted
    except Exception as e:
        LOGGER.error(e)
        sleep(1)
        attempt += 1
        return short_url(longurl, attempt)


def wrap_verify_page(shortener_url: str, user_id: int) -> str:
    """
    Wrap a shortener URL inside the anti-bypass human verification page.

    Flow:
      User → Verify Page (Cloudflare Turnstile) → shortener_url → bot start link

    The shortener_url is AES-256-GCM encrypted so automated tools
    cannot extract it from the verification page URL.

    Returns the plain shortener_url unchanged if VERIFY_PAGE_URL or
    VERIFY_SECRET_KEY env vars are not configured.
    """
    from bot import config_dict
    verify_page = config_dict.get("VERIFY_PAGE_URL", "").rstrip("/")
    secret = config_dict.get("VERIFY_SECRET_KEY", "")

    if not verify_page or not secret:
        return shortener_url

    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        from base64 import urlsafe_b64encode

        key = sha256(secret.encode()).digest()
        plaintext = f"{shortener_url}|{int(time())}|{user_id}".encode()
        nonce = urandom(12)
        aesgcm = AESGCM(key)
        ciphertext_with_tag = aesgcm.encrypt(nonce, plaintext, None)
        encrypted = (
            urlsafe_b64encode(nonce + ciphertext_with_tag)
            .decode()
            .rstrip("=")
        )
        return f"{verify_page}/?d={encrypted}"
    except ImportError:
        LOGGER.warning(
            "wrap_verify_page: 'cryptography' package not installed. "
            "Install it via: pip install cryptography. "
            "Falling back to direct shortener URL."
        )
        return shortener_url
    except Exception as e:
        LOGGER.error(f"wrap_verify_page error: {e}")
        return shortener_url
