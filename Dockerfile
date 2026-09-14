FROM python:3.12-slim AS build
WORKDIR /wheels
# instagrapi pulls in Pillow and curl_cffi, which need a compiler on slim.
RUN apt-get update && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip3 wheel -r requirements.txt


FROM python:3.12-slim
WORKDIR /home/osintgram
RUN useradd --create-home --shell /usr/sbin/nologin osintgram

COPY --from=build /wheels /wheels
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt -f /wheels \
  && rm -rf /wheels requirements.txt

COPY --chown=osintgram:osintgram src/ /home/osintgram/src
# Kept in the image so the instagrapi login can be run inside the container:
#   docker compose run --rm --entrypoint python osintgram scripts/instagrapi_login.py
COPY --chown=osintgram:osintgram scripts/ /home/osintgram/scripts
# config/, cache/ and dossier/ are mounted at run time (see docker-compose.yml):
# they hold your API key and third parties' Instagram data, so they stay on the
# host rather than being baked into an image you might push somewhere.
RUN mkdir -p config cache dossier && chown -R osintgram:osintgram /home/osintgram
USER osintgram

# 0.0.0.0 here is the container's own interface, not your machine's: only the
# port you publish is reachable, and docker-compose.yml publishes it on
# 127.0.0.1 only. The app has no authentication - if you change that mapping to
# expose it on a network, put an authenticated reverse proxy in front of it.
EXPOSE 8000
ENV OLLAMA_HOST=http://host.docker.internal:11434
ENTRYPOINT ["uvicorn", "src.web.app:app", "--host", "0.0.0.0", "--port", "8000"]
