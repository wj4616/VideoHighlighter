#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="${1:-$ROOT/dist-linux-portable}"
APP="Video Highlighter"
BINARY="$ROOT/frontend/src-tauri/target/release/video-highlighter"
SIDECAR="$ROOT/dist-sidecar/vh-sidecar"
VIEWER="$ROOT/dist-viewer/vh-viewer"

for input in "$BINARY" "$SIDECAR/vh-sidecar" "$SIDECAR/_internal" "$VIEWER/vh-viewer" "$VIEWER/_internal" "$ROOT/LICENSE" "$ROOT/COPYRIGHT"; do
    if [[ ! -e "$input" ]]; then
        printf "Missing release input: %s\n" "$input" >&2
        exit 1
    fi
done
if [[ -e "$OUT" ]]; then
    printf "Destination already exists (not replacing it): %s\n" "$OUT" >&2
    exit 1
fi

mkdir -p "$OUT/usr/bin" "$OUT/usr/lib/$APP/vh-sidecar" "$OUT/usr/lib/$APP/vh-viewer"
cp -a --reflink=auto "$BINARY" "$OUT/usr/bin/video-highlighter"
# Copy only frozen-build inputs. The source onedir folders may contain logs,
# a locally modified config, or caches after a smoke test.
cp -a --reflink=auto "$SIDECAR/vh-sidecar" "$SIDECAR/_internal" "$OUT/usr/lib/$APP/vh-sidecar/"
cp -a --reflink=auto "$VIEWER/vh-viewer" "$VIEWER/_internal" "$OUT/usr/lib/$APP/vh-viewer/"
cp -a "$ROOT/LICENSE" "$ROOT/COPYRIGHT" "$OUT/usr/lib/$APP/"
printf "Linux desktop folder: %s\n" "$OUT"
printf "Run: %s/usr/bin/video-highlighter\n" "$OUT"
