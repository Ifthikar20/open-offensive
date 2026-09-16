#!/usr/bin/env bash
# Build the OpenOffensive sandbox toolbox image (openoffensive-sandbox:kali by
# default). Works on a normal host, AND in locked-down environments where Docker
# Hub / apt are blocked but PyPI, git-over-HTTPS and GitHub Releases are reachable
# through an egress proxy. Once built, the engine finds the image and uses it.
set -euo pipefail
cd "$(dirname "$0")"

IMAGE="${OPENOFFENSIVE_SANDBOX_IMAGE:-openoffensive-sandbox:kali}"
CTX="$(mktemp -d)"; trap 'rm -rf "$CTX"' EXIT
cp Dockerfile.toolbox "$CTX/Dockerfile"

# If a TLS-terminating egress proxy is in play, hand its CA to the build so
# pip/curl/git trust it. Pick the first CA bundle we can find; empty otherwise.
CA=""
for c in "${REQUESTS_CA_BUNDLE:-}" "${SSL_CERT_FILE:-}" "${CURL_CA_BUNDLE:-}" \
         /root/.ccr/ca-bundle.crt /etc/ssl/certs/ca-certificates.crt; do
  if [ -n "$c" ] && [ -f "$c" ]; then CA="$c"; break; fi
done
if [ -n "$CA" ]; then cp "$CA" "$CTX/ca.crt"; else : > "$CTX/ca.crt"; fi

build=(docker build -t "$IMAGE" -f "$CTX/Dockerfile")
if [ -n "${HTTPS_PROXY:-}" ]; then
  echo "==> building through egress proxy ${HTTPS_PROXY} (host network)"
  build+=(--network host
          --build-arg "HTTPS_PROXY=${HTTPS_PROXY}"
          --build-arg "HTTP_PROXY=${HTTP_PROXY:-$HTTPS_PROXY}")
fi
build+=("$CTX")

echo "==> ${build[*]}"
DOCKER_BUILDKIT=0 "${build[@]}"
echo "==> built ${IMAGE}"
