"""
Link utilities - Extract and parse links from URLs and messages
"""

from re import match as re_match, search as re_search, findall
from urllib.parse import urlparse, parse_qs
from logging import getLogger

LOGGER = getLogger(__name__)

URL_REGEX = r"^(?!\/)(rtmps?:\/\/|mms:\/\/|rtsp:\/\/|https?:\/\/|ftp:\/\/)?([^\/:]+:[^\/@]+@)?(www\.)?(?=[^\/:\s]+\.[^\/:\s]+)([^\/:\s]+\.[^\/:\s]+)(:\d+)?(\/[^#\s]*[\s\S]*)?(\?[^#\s]*)?(#.*)?$"


def is_url(text):
    """Check if text is a valid URL"""
    return bool(re_match(URL_REGEX, text))


def get_url_name(url):
    """Extract filename from URL
    
    Args:
        url: URL to extract filename from
        
    Returns:
        Extracted filename or None if not found
    """
    try:
        parsed = urlparse(url)
        # Get filename from path
        path = parsed.path
        if path:
            filename = path.split('/')[-1]
            if filename:
                return filename.split('?')[0] or None  # Remove query string
        return None
    except Exception as e:
        LOGGER.error(f"Error extracting URL name: {e}")
        return None


def get_link(text, link_type='all'):
    """Extract links from text
    
    Args:
        text: Text to search for links
        link_type: Type of links to extract ('all', 'url', 'magnet')
        
    Returns:
        List of extracted links
    """
    try:
        links = []
        
        if link_type in ['all', 'url']:
            # Find all URLs
            url_matches = findall(
                r'https?://[^\s\)]+|ftp://[^\s\)]+|magnet:\?[^\s\)]+',
                text
            )
            links.extend(url_matches)
        
        if link_type in ['all', 'magnet']:
            # Find magnet links
            magnet_matches = findall(r'magnet:\?[^\s\)]+', text)
            links.extend([m for m in magnet_matches if m not in links])
        
        return links
    except Exception as e:
        LOGGER.error(f"Error extracting links: {e}")
        return []
