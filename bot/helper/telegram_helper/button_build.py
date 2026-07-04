from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.enums import ButtonStyle

class ButtonMaker:
    def __init__(self):
        self.__button = []
        self.__header_button = []
        self.__first_body_button = []
        self.__last_body_button = []
        self.__footer_button = []

    def ubutton(self, key, link, position=None, style=None, icon_custom_emoji_id=None):
        button = InlineKeyboardButton(
            text=key,
            url=link,
            style=style,
            icon_custom_emoji_id=icon_custom_emoji_id,
        )

        if not position:
            self.__button.append(button)
        elif position == "header":
            self.__header_button.append(button)
        elif position == "f_body":
            self.__first_body_button.append(button)
        elif position == "l_body":
            self.__last_body_button.append(button)
        elif position == "footer":
            self.__footer_button.append(button)

    def ibutton(self, key, data, position=None, style=None, icon_custom_emoji_id=None):
        button = InlineKeyboardButton(
            text=key,
            callback_data=data,
            style=style,
            icon_custom_emoji_id=icon_custom_emoji_id,
        )

        if not position:
            self.__button.append(button)
        elif position == "header":
            self.__header_button.append(button)
        elif position == "f_body":
            self.__first_body_button.append(button)
        elif position == "l_body":
            self.__last_body_button.append(button)
        elif position == "footer":
            self.__footer_button.append(button)

    def build_menu(self, b_cols=1, h_cols=8, fb_cols=2, lb_cols=2, f_cols=8):
        menu = [
            self.__button[i:i + b_cols]
            for i in range(0, len(self.__button), b_cols)
        ]

        if self.__header_button:
            if len(self.__header_button) > h_cols:
                menu = [
                    self.__header_button[i:i + h_cols]
                    for i in range(0, len(self.__header_button), h_cols)
                ] + menu
            else:
                menu.insert(0, self.__header_button)

        if self.__first_body_button:
            if len(self.__first_body_button) > fb_cols:
                menu.extend(
                    self.__first_body_button[i:i + fb_cols]
                    for i in range(0, len(self.__first_body_button), fb_cols)
                )
            else:
                menu.append(self.__first_body_button)

        if self.__last_body_button:
            if len(self.__last_body_button) > lb_cols:
                menu.extend(
                    self.__last_body_button[i:i + lb_cols]
                    for i in range(0, len(self.__last_body_button), lb_cols)
                )
            else:
                menu.append(self.__last_body_button)

        if self.__footer_button:
            if len(self.__footer_button) > f_cols:
                menu.extend(
                    self.__footer_button[i:i + f_cols]
                    for i in range(0, len(self.__footer_button), f_cols)
                )
            else:
                menu.append(self.__footer_button)

        return InlineKeyboardMarkup(menu)
