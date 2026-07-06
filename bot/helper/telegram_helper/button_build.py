from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

try:
    from pyrogram.enums import ButtonStyle
except ImportError:
    ButtonStyle = None


class ButtonMaker:
    def __init__(self):
        self.__button = []
        self.__header_button = []
        self.__first_body_button = []
        self.__last_body_button = []
        self.__footer_button = []

    def _make_btn(self, key, url=None, data=None, style=None, icon_custom_emoji_id=None):
        kwargs = {"text": key}
        if url is not None:
            kwargs["url"] = url
        if data is not None:
            kwargs["callback_data"] = data
        if style is not None and ButtonStyle is not None:
            kwargs["style"] = style
        if icon_custom_emoji_id is not None:
            kwargs["icon_custom_emoji_id"] = icon_custom_emoji_id
        try:
            return InlineKeyboardButton(**kwargs)
        except TypeError:
            kwargs.pop("icon_custom_emoji_id", None)
            kwargs.pop("style", None)
            return InlineKeyboardButton(**kwargs)

    def _get_list(self, position):
        if position == "header":
            return self.__header_button
        elif position == "f_body":
            return self.__first_body_button
        elif position == "l_body":
            return self.__last_body_button
        elif position == "footer":
            return self.__footer_button
        return self.__button

    def ubutton(self, key, link, position=None, style=None, icon_custom_emoji_id=None):
        self._get_list(position).append(
            self._make_btn(key, url=link, style=style, icon_custom_emoji_id=icon_custom_emoji_id)
        )

    def ibutton(self, key, data, position=None, style=None, icon_custom_emoji_id=None):
        self._get_list(position).append(
            self._make_btn(key, data=data, style=style, icon_custom_emoji_id=icon_custom_emoji_id)
        )

    def url_button(self, key, link, position=None, style=None, icon_custom_emoji_id=None):
        self.ubutton(key, link, position=position, style=style, icon_custom_emoji_id=icon_custom_emoji_id)

    def data_button(self, key, data, position=None, style=None, icon_custom_emoji_id=None):
        self.ibutton(key, data, position=position, style=style, icon_custom_emoji_id=icon_custom_emoji_id)

    def build_menu(self, b_cols=1, h_cols=8, fb_cols=2, lb_cols=2, f_cols=8):
        def chunk(lst, n):
            return [lst[i: i + n] for i in range(0, len(lst), n)]

        menu = chunk(self.__button, b_cols)
        if self.__header_button:
            menu = chunk(self.__header_button, h_cols) + menu
        if self.__first_body_button:
            menu += chunk(self.__first_body_button, fb_cols)
        if self.__last_body_button:
            menu += chunk(self.__last_body_button, lb_cols)
        if self.__footer_button:
            menu += chunk(self.__footer_button, f_cols)
        return InlineKeyboardMarkup(menu)

    def reset(self):
        for lst in [
            self.__button, self.__header_button, self.__first_body_button,
            self.__last_body_button, self.__footer_button,
        ]:
            lst.clear()
