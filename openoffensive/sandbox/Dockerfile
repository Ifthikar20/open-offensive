# OpenOffensive sandbox image — a Kali base with a real pentest toolset.
# Built once into `openoffensive-sandbox:kali`; every scan runs one container
# from it, and the agents' tool calls execute inside via `docker exec`.
#
# First build is slow and large (it pulls the Kali rolling base). That's the
# same tradeoff Strix makes.
FROM kalilinux/kali-rolling

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1

# A focused, apt-available toolset: recon, web scanners, injection, source review.
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        wget \
        git \
        jq \
        dnsutils \
        netcat-traditional \
        python3 \
        python3-requests \
        python3-pip \
        nmap \
        sqlmap \
        nikto \
        whatweb \
        dirb \
        gobuster \
        wafw00f \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace

# Keep-alive is provided at `docker run` time (`tail -f /dev/null`); the agents
# drive everything else through `docker exec`.
CMD ["sleep", "infinity"]
