FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# << WICHTIG: Arbeitsverzeichnis ist das ÄUSSERE 'lagerbestand_site'
WORKDIR /app/lagerbestand_site

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY . /app

# normaler WSGI-Pfad
CMD ["gunicorn","lagerbestand_site.wsgi:application","--bind","0.0.0.0:8000","--workers","3","--timeout","60"]
