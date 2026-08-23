# Immutable base image already admitted for Sovereign's editor surface.
FROM lscr.io/linuxserver/code-server@sha256:dfc5e74083f43f3cb217fedfead149f32b319ee663744351c001bdc5e4245441

USER root

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       openbox \
       scrot \
       xterm \
       xdotool \
       xvfb \
    && (apt-get install -y --no-install-recommends firefox-esr || apt-get install -y --no-install-recommends epiphany-browser) \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 desktop \
    && useradd --uid 10001 --gid 10001 --create-home --home-dir /home/desktop --shell /usr/sbin/nologin desktop \
    && mkdir -p /opt/sovereign-desktop-worker /opt/desktop-scopes /workspace /run/user/10001 \
    && chown -R 10001:10001 /opt/sovereign-desktop-worker /opt/desktop-scopes /workspace /home/desktop /run/user/10001

COPY desktop_worker.py /opt/sovereign-desktop-worker/desktop_worker.py
COPY entrypoint.sh /usr/local/bin/sovereign-desktop-worker
RUN chmod 0555 /opt/sovereign-desktop-worker/desktop_worker.py /usr/local/bin/sovereign-desktop-worker

USER 10001:10001
WORKDIR /workspace
EXPOSE 8765
HEALTHCHECK --interval=20s --timeout=5s --start-period=30s --retries=3 \
  CMD python3 -c "import urllib.request; assert urllib.request.urlopen('http://127.0.0.1:8765/health', timeout=3).status == 200"
ENTRYPOINT ["/usr/local/bin/sovereign-desktop-worker"]
