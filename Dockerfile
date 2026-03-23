FROM mysterysd/wzmlx:latest

WORKDIR /usr/src/app
RUN chmod 777 /usr/src/app

# Install FFmpeg and other system dependencies for video processing
RUN apt-get update && apt-get install -y \
    ffmpeg \
    python3-dev \
    nodejs \
    npm \
    && rm -rf /var/lib/apt/lists/*

# Install esbuild for JavaScript bundling (needed for yt-dlp challenge solving)
RUN npm install -g esbuild

COPY requirements.txt .
RUN pip3 install --upgrade setuptools wheel
RUN pip3 install --no-cache-dir -r requirements.txt

COPY . .

CMD ["bash", "start.sh"]
y
