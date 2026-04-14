#!/usr/bin/env bash
# Build official mobile-ai-assistant web bundle and copy into Android/iOS host app trees.
# Requires: bun, dawnchat-plugins/official-plugins/mobile-ai-assistant/web-src
#
# Output layout (matches offline PluginStorage versions/{version}/):
#   apps/dawnchat-android/android/app/src/main/assets/builtin_mobile_assistant/<version>/
#   apps/dawnchat-ios/ios/App/App/BuiltinPlugins/builtin_mobile_assistant/<version>/

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
WEB_SRC="${DAWNCHAT_MOBILE_ASSISTANT_WEB_SRC:-$REPO_ROOT/dawnchat-plugins/official-plugins/mobile-ai-assistant/web-src}"

if [[ ! -d "$WEB_SRC" ]]; then
  echo "error: mobile-ai-assistant web-src not found: $WEB_SRC" >&2
  echo "Set DAWNCHAT_MOBILE_ASSISTANT_WEB_SRC or sync dawnchat-plugins (see scripts/dev/sync.sh)." >&2
  exit 1
fi

cd "$WEB_SRC"

if ! command -v bun &>/dev/null; then
  echo "error: bun is required to build the assistant web bundle" >&2
  exit 1
fi

echo "==> bun install (mobile-ai-assistant web-src)"
bun install

echo "==> bun run build"
bun run build

OUT_DIR=""
if [[ -d "$WEB_SRC/dist" && -f "$WEB_SRC/dist/index.html" ]]; then
  OUT_DIR="$WEB_SRC/dist"
elif [[ -d "$WEB_SRC/www" && -f "$WEB_SRC/www/index.html" ]]; then
  OUT_DIR="$WEB_SRC/www"
else
  echo "error: expected dist/ or www/ with index.html after build under $WEB_SRC" >&2
  exit 1
fi

VERSION="$(node -p "require('./package.json').version || '0.0.0'" 2>/dev/null || echo "0.0.0")"
if [[ -z "$VERSION" || "$VERSION" == "undefined" || "$VERSION" == "null" ]]; then
  VERSION="0.0.0"
fi

PLUGIN_ID="${BUILTIN_MOBILE_ASSISTANT_ID:-com.dawnchat.mobile-ai-assistant}"
NAME="${BUILTIN_MOBILE_ASSISTANT_NAME:-Mobile AI Assistant}"

ANDROID_DST="$REPO_ROOT/apps/dawnchat-android/android/app/src/main/assets/builtin_mobile_assistant/$VERSION"
IOS_DST="$REPO_ROOT/apps/dawnchat-ios/ios/App/App/BuiltinPlugins/builtin_mobile_assistant/$VERSION"

echo "==> sync $OUT_DIR -> Android $ANDROID_DST"
rm -rf "$ANDROID_DST"
mkdir -p "$ANDROID_DST"
rsync -a --delete "$OUT_DIR/" "$ANDROID_DST/"

echo "==> sync $OUT_DIR -> iOS $IOS_DST"
rm -rf "$IOS_DST"
mkdir -p "$IOS_DST"
rsync -a --delete "$OUT_DIR/" "$IOS_DST/"

MANIFEST=$(printf '{"pluginId":"%s","version":"%s","name":"%s","entry":"index.html"}\n' "$PLUGIN_ID" "$VERSION" "$NAME")
echo "$MANIFEST" > "$REPO_ROOT/apps/dawnchat-android/android/app/src/main/assets/builtin_mobile_assistant/builtin-manifest.json"
echo "$MANIFEST" > "$REPO_ROOT/apps/dawnchat-ios/ios/App/App/BuiltinPlugins/builtin-manifest.json"

echo ""
echo "Done. Embedded version: $VERSION"
echo "Update BuiltinMobileAssistant.BUNDLED_VERSION in Android/iOS if it differs from $VERSION."
