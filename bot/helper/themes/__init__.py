#!/usr/bin/env python3
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


def apply_custom_emojis(text: str) -> str:
    """
    Replace plain emojis with Telegram animated custom emoji HTML tags.

    Only applies when the text contains HTML markup (message bodies).
    Button labels (plain text, no HTML) are returned unchanged — Telegram
    does not support <emoji> tags in inline button text.
    """
    if not text or "<" not in text:
        return text
    for emoji, eid in CUSTOM_EMOJI_MAP.items():
        if emoji in text:
            text = text.replace(emoji, f'<emoji id="{eid}">{emoji}</emoji>')
    return text


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
