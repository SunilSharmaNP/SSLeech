FROM mysterysd/wzmlx:v3

WORKDIR /usr/src/app

RUN chmod 777 /usr/src/app

COPY requirements.txt .RUN pip3 install --no-cache-dir -r requirements.txt
COPY . .

ENTRYPOINT ["bash", "start.sh"]
