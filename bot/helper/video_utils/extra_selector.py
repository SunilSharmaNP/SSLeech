from __future__ import annotations
from asyncio import sleep

from bot import LOGGER


class ExtraSelect:
    def __init__(self, obj):
        # obj is VidEcxecutor instance
        self.obj = obj

    async def get_buttons(self, *args):
        # Minimal automatic selection: build simple stream map from provided streams
        await sleep(0.1)
        streams = args[0] if args and args[0] else []
        data = {}
        data_stream = {}
        ext = []
        v_idx = None
        a_idx = None
        idx = 0
        for s in streams:
            stype = s.get('codec_type') if isinstance(s, dict) else 'video'
            lang = (s.get('tags') or {}).get('language', 'und') if isinstance(s, dict) else 'und'
            data_stream[idx] = {'map': idx, 'type': stype if stype else 'video', 'lang': lang}
            if stype == 'video' and v_idx is None:
                v_idx = idx
            if stype == 'audio' and a_idx is None:
                a_idx = idx
            idx += 1
        if v_idx is None:
            v_idx = 0
        if a_idx is None:
            a_idx = 1 if idx > 1 else 0
        ext = ['mkv', 'mp4', 'mka', 'srt']
        data['stream'] = data_stream
        data['extension'] = ext
        data['key'] = 0
        data['video'] = v_idx
        data['audio'] = a_idx
        data['sdata'] = []
        data['alt_mode'] = False

        # For convert/compress modes, set a quality shortcut
        if getattr(self.obj, 'mode', '') in ('convert', 'compress'):
            self.obj.data = '720p'
        else:
            self.obj.data = data
        # signal executor to continue
        try:
            self.obj.event.set()
        except Exception as e:
            LOGGER.error('ExtraSelect set event failed: %s', e)
