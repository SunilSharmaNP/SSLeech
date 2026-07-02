#!/usr/bin/env python3
import re
from os import listdir
from importlib import import_module
from random import choice as rchoice
from bot import config_dict, LOGGER
from bot.helper.themes import wzml_minimal
from bot.helper.themes.custom_emojis import _FULL_MAP as _EMOJI_FULL_MAP

AVL_THEMES = {}
for theme in listdir("bot/helper/themes"):
    if theme.startswith("wzml_") and theme.endswith(".py"):
        AVL_THEMES[theme[5:-3]] = import_module(f"bot.helper.themes.{theme[:-3]}")

_EMOJI_SORTED = sorted(_EMOJI_FULL_MAP.items(), key=lambda x: len(x[0]), reverse=True)
_EMOJI_PATTERN = re.compile("|".join(re.escape(e) for e, _ in _EMOJI_SORTED)) if _EMOJI_SORTED else None


def apply_custom_emojis(text: str) -> str:
    """Replace plain emoji chars with PyroTGFork <emoji id=DOC_ID>char</emoji> tags.

    Uses the correct HTML tag format for PyroTGFork 2.2.x premium emoji support.
    Checks config_dict["USE_CUSTOM_EMOJI"] at runtime so toggling via Bot Settings
    takes effect immediately without a bot restart.
    """
    if not text or not config_dict.get("USE_CUSTOM_EMOJI", False) or not _EMOJI_PATTERN:
        return text

    def _replace(match: re.Match) -> str:
        emoji = match.group(0)
        eid = _EMOJI_FULL_MAP[emoji]
        return f'<emoji id="{eid}">{emoji}</emoji>'

    return _EMOJI_PATTERN.sub(_replace, text)


def BotTheme(var_name, **format_vars):
    text = None
    theme_ = config_dict["BOT_THEME"]

    if theme_ in AVL_THEMES:
        text = getattr(AVL_THEMES[theme_].WZMLStyle(), var_name, None)
        if text is None:
            LOGGER.error(
                f"{var_name} not Found in {theme_}. Please recheck with Official Repo"
            )
    elif theme_ == "random":
        rantheme = rchoice(list(AVL_THEMES.values()))
        LOGGER.info(f"Random Theme Chosen: {rantheme}")
        text = getattr(rantheme.WZMLStyle(), var_name, None)

    if text is None:
        text = getattr(wzml_minimal.WZMLStyle(), var_name)

    return text.format_map(format_vars)
