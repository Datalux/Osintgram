FROM python:3.9.2-alpine3.13 as build
WORKDIR /wheels
RUN apk add --no-cache \
    g++ \
    gcc \
    git \
    libxml2 \
    libxml2-dev \
    libxslt-dev \
    ncurses-dev \
    build-base \
    linux-headers
COPY requirements.txt /opt/osintgram/
RUN pip3 wheel -r /opt/osintgram/requirements.txt


FROM python:3.9.2-alpine3.13
WORKDIR /opt/osintgram
RUN adduser -D osintgram
RUN mkdir -p /opt/osintgram && chown -R osintgram:osintgram /opt/osintgram

COPY --from=build /wheels /wheels
COPY --chown=osintgram:osintgram requirements.txt /opt/osintgram/
RUN pip3 install -r requirements.txt -f /wheels \
  && rm -rf /wheels \
  && rm -rf /root/.cache/pip/* \
  && rm requirements.txt

COPY --chown=osintgram:osintgram src/ /opt/osintgram/src
COPY --chown=osintgram:osintgram main.py /opt/osintgram/

USER osintgram

ENTRYPOINT ["sleep", "infinity"]