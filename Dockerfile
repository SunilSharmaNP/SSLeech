FROM mysterysd/wzmlx:v3

WORKDIR /usr/src/app
RUN chmod 777 /usr/src/app

COPY requirements.txt .
RUN /usr/src/app/.venv/bin/pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["bash", "start.sh"]
