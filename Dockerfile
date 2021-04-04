FROM python:3.9.2-alpine3.13 as build
WORKDIR /wheels
RUN apk add --no-cache \
    ncurses-dev \
    build-base
COPY docker_reqs.txt /opt/osintgram/requirements.txt
RUN pip3 wheel -r /opt/osintgram/requirements.txt


FROM python:3.9.2-alpine3.13
WORKDIR /home/osintgram
RUN adduser -D osintgram

COPY --from=build /wheels /wheels
COPY --chown=osintgram:osintgram requirements.txt /home/osintgram/
RUN pip3 install -r requirements.txt -f /wheels \
  && rm -rf /wheels \
  && rm -rf /root/.cache/pip/* \
  && rm requirements.txt

COPY --chown=osintgram:osintgram src/ /home/osintgram/src
COPY --chown=osintgram:osintgram main.py /home/osintgram/
COPY --chown=osintgram:osintgram config/ /home/osintgram/config
USER osintgram

ENTRYPOINT ["python", "main.py"]
