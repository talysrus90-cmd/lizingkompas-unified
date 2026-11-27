FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /srv/compass
COPY production/requirements.txt /tmp/requirements.txt
RUN python -m pip install --no-cache-dir -r /tmp/requirements.txt && \
    groupadd -g 10001 compass && useradd -u 10001 -g compass -M -s /usr/sbin/nologin compass
COPY production/backend/ /srv/compass/backend/
COPY broker/ /srv/compass/broker/
RUN mkdir -p /srv/compass/backend/collected_static && \
    chown -R compass:compass /srv/compass
USER compass
WORKDIR /srv/compass/backend
ENV PYTHONPATH=/srv/compass:/srv/compass/backend
EXPOSE 8000
CMD ["sh","-c","python manage.py collectstatic --noinput >/dev/null && exec gunicorn compassapp.wsgi:application --bind 0.0.0.0:8000 --workers 2 --timeout 45 --access-logfile - --error-logfile -"]
