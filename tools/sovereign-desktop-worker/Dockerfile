# syntax=docker/dockerfile:1.7
FROM debian:12.13-slim@sha256:67b30a61dc87758f0caf819646104f29ecbda97d920aaf5edc834128ac8493d3

ARG DEBIAN_FRONTEND=noninteractive
ARG SOURCE_REVISION
LABEL org.opencontainers.image.source="https://github.com/OuroborosCollective/Sovereign-Studio-ato" \
      org.opencontainers.image.revision="${SOURCE_REVISION}"

RUN apt-get update \
    && apt-get install --yes --no-install-recommends \
        ca-certificates \
        curl \
        firefox-esr \
        git \
        mousepad \
        novnc \
        openbox \
        procps \
        python3 \
        tini \
        websockify \
        x11-apps \
        x11-utils \
        x11vnc \
        xdotool \
        xterm \
        xvfb \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd --gid 10001 desktop \
    && useradd --uid 10001 --gid 10001 --create-home --home-dir /home/desktop --shell /usr/sbin/nologin desktop \
    && groupadd --gid 10002 desktop-controller \
    && useradd --uid 10002 --gid 10002 --no-create-home --home-dir /nonexistent --shell /usr/sbin/nologin desktop-controller \
    && install --directory --owner=desktop --group=desktop --mode=0711 /run/desktop-control \
    && install --directory --owner=desktop-controller --group=desktop-controller --mode=0700 /run/desktop-view-gateway

COPY --chown=desktop:desktop desktop-entrypoint /usr/local/bin/desktop-entrypoint
COPY --chown=desktop:desktop desktop-control.py /usr/local/lib/desktop-control.py
COPY --chown=desktop:desktop desktop-control-client.py /usr/local/bin/desktop-control-client
COPY --chown=desktop-controller:desktop-controller desktop-view-gateway.py /usr/local/lib/desktop-view-gateway.py

RUN chmod 0755 /usr/local/bin/desktop-entrypoint /usr/local/bin/desktop-control-client \
    && chmod 0644 /usr/local/lib/desktop-control.py /usr/local/lib/desktop-view-gateway.py

ENV HOME=/home/desktop \
    DISPLAY=:99 \
    XDG_RUNTIME_DIR=/run/desktop \
    DESKTOP_CONTROL_SOCKET=/run/desktop-control/worker.sock \
    DESKTOP_ACTIVITY_PATH=/run/desktop-control/activity \
    DESKTOP_CONTROL_CLIENT_UID=10002 \
    DESKTOP_STREAM_PORT=6080 \
    DESKTOP_MAX_LIFETIME_SECONDS=3600 \
    DESKTOP_MAX_IDLE_SECONDS=900

USER desktop
ENTRYPOINT ["/usr/bin/tini", "--", "/usr/local/bin/desktop-entrypoint"]
