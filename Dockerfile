FROM mysterysd/wzmlx:v3

WORKDIR /usr/src/app
RUN chmod 777 /usr/src/app

COPY requirements.txt .
RUN /usr/src/app/.venv/bin/pip install --no-cache-dir -r requirements.txt

# Patch lk21/exrex.py: 'sre_parse' removed from 're' in Python 3.13
RUN /usr/src/app/.venv/bin/python3 -c "\
import glob, os; \
OLD = 'from re import sre_parse, U'; \
NEW = 'try:\n    import sre_parse\nexcept ImportError:\n    import re; sre_parse = re._parser\nfrom re import U'; \
files = glob.glob('/usr/src/app/.venv/lib/python*/site-packages/lk21/thirdparty/exrex.py'); \
[open(f,'w').write(open(f).read().replace(OLD, NEW)) for f in files if OLD in open(f).read()] or print('exrex: already patched or not found'); \
print('lk21/exrex.py patch done:', files)"

COPY . .

CMD ["bash", "start.sh"]
