FROM ssbots/ssbots_heroku:latest

WORKDIR /usr/src/app
RUN chmod 777 /usr/src/app

# ── Heroku Ban Bypass Symlinks ────────────────────────────────────────────────
RUN ln -sf "$(which aria2c)"          /usr/local/bin/blitzfetcher \
 && ln -sf "$(which qbittorrent-nox)" /usr/local/bin/stormtorrent \
 && ln -sf "$(which ffmpeg)"          /usr/local/bin/mediaforge \
 && ln -sf "$(which rclone)"          /usr/local/bin/ghostdrive

COPY requirements.txt .

RUN pip3 uninstall -y pyrogram pyrofork 2>/dev/null || true
RUN pip3 install --no-cache-dir -r requirements.txt

RUN ln -sf /usr/bin/python3 /usr/bin/python

COPY . .

CMD ["bash", "start.sh"]
