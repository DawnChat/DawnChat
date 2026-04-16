#!/usr/bin/env bash
# Download dawnchat-plugins sidecar embed from GitHub Release (see config/dawnchat-plugins.lock.json),
# or fall back to shallow clone of main when release_tag is empty.
#
# Environment:
#   DAWNCHAT_PLUGINS_LOCK_PATH   path to lock JSON (default: <repo>/config/dawnchat-plugins.lock.json)
#   DAWNCHAT_PLUGINS_RELEASE_TAG  overrides lock.release_tag
#   DAWNCHAT_PLUGINS_REPOSITORY overrides lock.repository (owner/repo)
#   DAWNCHAT_PLUGINS_SKIP_DOWNLOAD=1  skip (use existing dawnchat-plugins/)
#   DAWNCHAT_PLUGINS_DOWNLOAD_FALLBACK=1  when download fails, git clone main (default: 0)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
LOCK_PATH="${DAWNCHAT_PLUGINS_LOCK_PATH:-$PROJECT_ROOT/config/dawnchat-plugins.lock.json}"
DEST_DIR="${DAWNCHAT_PLUGINS_DEST_DIR:-$PROJECT_ROOT/dawnchat-plugins}"

if [[ ! -f "$LOCK_PATH" ]]; then
  echo "error: lock file not found: $LOCK_PATH" >&2
  exit 1
fi

if [[ "${DAWNCHAT_PLUGINS_SKIP_DOWNLOAD:-}" == "1" ]]; then
  echo "[download-dawnchat-plugins] DAWNCHAT_PLUGINS_SKIP_DOWNLOAD=1, skip."
  exit 0
fi

if [[ -d "$DEST_DIR" ]] && [[ -f "$DEST_DIR/.sidecar-embed-bundled" ]]; then
  echo "[download-dawnchat-plugins] existing sidecar embed bundle at $DEST_DIR/.sidecar-embed-bundled, skip."
  exit 0
fi

read_lock() {
  python3 - "$LOCK_PATH" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
data = json.loads(path.read_text(encoding="utf-8"))
repo = str(data.get("repository") or "").strip()
tag = str(data.get("release_tag") or "").strip()
asset = str(data.get("asset_name") or "").strip()
sha = str(data.get("sha256") or "").strip()
print(repo or "")
print(tag or "")
print(asset or "")
print(sha or "")
PY
}

mapfile -t LOCK_PARTS < <(read_lock)
LOCK_REPO="${LOCK_PARTS[0]:-}"
LOCK_TAG="${LOCK_PARTS[1]:-}"
LOCK_ASSET="${LOCK_PARTS[2]:-}"
LOCK_SHA="${LOCK_PARTS[3]:-}"

REPO="${DAWNCHAT_PLUGINS_REPOSITORY:-$LOCK_REPO}"
RELEASE_TAG="${DAWNCHAT_PLUGINS_RELEASE_TAG:-$LOCK_TAG}"

if [[ -z "$REPO" ]]; then
  echo "error: lock file missing repository: $LOCK_PATH" >&2
  exit 1
fi

clone_main() {
  echo "[download-dawnchat-plugins] git clone --depth 1 --branch main https://github.com/${REPO}.git"
  rm -rf "$DEST_DIR"
  git clone --depth 1 --branch main "https://github.com/${REPO}.git" "$DEST_DIR"
}

if [[ -z "${RELEASE_TAG}" ]]; then
  echo "[download-dawnchat-plugins] release_tag empty; using shallow clone of main (no sidecar embed marker)."
  clone_main
  exit 0
fi

if [[ -z "${LOCK_ASSET}" ]]; then
  ASSET_NAME="dawnchat-sidecar-embed-${RELEASE_TAG}.tar.zst"
else
  ASSET_NAME="${LOCK_ASSET}"
fi

URL="https://github.com/${REPO}/releases/download/${RELEASE_TAG}/${ASSET_NAME}"
TMP_DIR="${TMPDIR:-/tmp}"
ARCHIVE="${TMP_DIR}/dawnchat-sidecar-embed.$$.tar.zst"

echo "[download-dawnchat-plugins] fetching ${URL}"

if ! curl -fsSL -o "$ARCHIVE" "$URL"; then
  echo "[download-dawnchat-plugins] download failed" >&2
  if [[ "${DAWNCHAT_PLUGINS_DOWNLOAD_FALLBACK:-0}" == "1" ]]; then
    echo "[download-dawnchat-plugins] DAWNCHAT_PLUGINS_DOWNLOAD_FALLBACK=1, cloning main" >&2
    clone_main
    exit 0
  fi
  exit 1
fi

if [[ -n "${LOCK_SHA}" ]]; then
  echo "[download-dawnchat-plugins] verifying sha256..."
  if command -v shasum >/dev/null 2>&1; then
    actual="$(shasum -a 256 "$ARCHIVE" | awk '{print $1}')"
  else
    actual="$(sha256sum "$ARCHIVE" | awk '{print $1}')"
  fi
  if [[ "${actual}" != "${LOCK_SHA}" ]]; then
    echo "error: sha256 mismatch (expected ${LOCK_SHA}, got ${actual})" >&2
    rm -f "$ARCHIVE"
    exit 1
  fi
else
  echo "[download-dawnchat-plugins] warning: lock sha256 empty, skipping checksum" >&2
fi

mkdir -p "$DEST_DIR"

# Remove stale subtree before merge (avoid mixed old/new template dirs).
rm -rf \
  "${DEST_DIR}/sdk" \
  "${DEST_DIR}/assistant-sdk" \
  "${DEST_DIR}/capacitor-plugins-sdk" \
  "${DEST_DIR}/assistant-workspace" \
  "${DEST_DIR}/.opencode"
for tid in desktop-starter desktop-hello-world desktop-ai-assistant web-starter-vue web-ai-assistant mobile-starter-ionic mobile-ai-assistant; do
  rm -rf "${DEST_DIR}/official-plugins/${tid}"
done

tar -xf "$ARCHIVE" -C "$DEST_DIR"
rm -f "$ARCHIVE"

{
  echo "release_tag=${RELEASE_TAG}"
  echo "asset_name=${ASSET_NAME}"
  if [[ -n "${LOCK_SHA}" ]]; then
    echo "sha256=${LOCK_SHA}"
  fi
  echo "bundled_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
} > "${DEST_DIR}/.sidecar-embed-bundled"

echo "[download-dawnchat-plugins] extracted sidecar embed -> ${DEST_DIR} (marker .sidecar-embed-bundled)"
