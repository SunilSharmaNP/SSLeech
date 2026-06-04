FROM mysterysd/wzmlx:v3

WORKDIR /usr/src/app
RUN chmod 777 /usr/src/app

COPY requirements.txt .
RUN /usr/src/app/.venv/bin/pip install --no-cache-dir -r requirements.txt && \
    sed -i 's/from re import sre_parse, U/import sre_parse; from re import U/' \
        /usr/src/app/.venv/lib/python3.13/site-packages/lk21/thirdparty/exrex.py || true

COPY . .

CMD ["bash", "start.sh"]
