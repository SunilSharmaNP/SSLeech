#!/usr/bin/env python3
import re
from os import listdir
from importlib import import_module
from random import choice as rchoice
from bot import config_dict, LOGGER
from bot.helper.themes import wzml_minimal
from bot.helper.themes.custom_emojis import CUSTOM_EMOJI_MAP

AVL_THEMES = {}
for theme in listdir("bot/helper/themes"):
    if theme.startswith("wzml_") and theme.endswith(".py"):
        AVL_THEMES[theme[5:-3]] = import_module(f"bot.helper.themes.{theme[:-3]}")

_EMOJI_SORTED = sorted(CUSTOM_EMOJI_MAP.items(), key=lambda x: len(x[0]), reverse=True)
_EMOJI_PATTERN = re.compile("|".join(re.escape(e) for e, _ in _EMOJI_SORTED))

# Match <emoji id="...">...</emoji> tags (Pyrofork's actual HTML tag for custom emoji)
_EMOJI_TAG = re.compile(r'<emoji\s+id="[^"]*">.*?</emoji>', re.DOTALL)


def apply_custom_emojis(text: str) -> str:
    """Replace plain emoji chars with Pyrofork <emoji id="..."> tags.
    Skips emojis already wrapped to prevent double-wrapping."""
    if not text:
        return text

    def _replace(match: re.Match) -> str:
        emoji = match.group(0)
        eid = CUSTOM_EMOJI_MAP[emoji]
        return f'<emoji id="{eid}">{emoji}</emoji>'

    # Split on already-tagged regions so we don't double-wrap
    parts = _EMOJI_TAG.split(text)
    tags = _EMOJI_TAG.findall(text)
    result = []
    for i, part in enumerate(parts):
        result.append(_EMOJI_PATTERN.sub(_replace, part))
        if i < len(tags):
            result.append(tags[i])
    return "".join(result)


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

    text = apply_custom_emojis(text)
    return text.format_map(format_vars)
