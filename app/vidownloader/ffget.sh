#!/usr/bin/env bash
# ffget.sh - simple wrapper to download an HLS (m3u8) with ffmpeg
# Usage: ./ffget.sh URL [OUTPUT] -- [extra ffmpeg args]

set -euo pipefail

usage() {
  cat <<EOF
Usage: $0 URL [OUTPUT] -- [extra ffmpeg args]
Examples:
  $0 "https://example.com/playlist.m3u8" out.mp4
  $0 "https://example.com/playlist.m3u8"
  $0 "URL" out.mp4 -- -bsf:a aac_adtstoasc
EOF
  exit 2
}

if [ $# -lt 1 ]; then
  usage
fi

# Parse args
url="$1"; shift
out=""
extra=()

while [ $# -gt 0 ]; do
  case "$1" in
    --)
      shift
      extra=("$@")
      break
      ;;
    *)
      if [ -z "$out" ]; then
        out="$1"
      else
        extra+=("$1")
      fi
      shift
      ;;
  esac
done

# Derive output filename
if [ -z "${out:-}" ]; then
  base=$(basename "${url%%\?*}")
  out="${base%.*}.mp4"
  if [ -z "$out" ] || [ "$out" = ".mp4" ]; then
    out="output_$(date +%Y%m%d%H%M%S).mp4"
  fi
else
  case "$(basename -- "$out")" in
    *.*) : ;;
    *) out="$out.mp4" ;;
  esac
fi

# Build ffmpeg command
cmd=(
  ffmpeg
  -nostdin          # 🔑 CRITICAL FIX (prevents interactive hang)
  -y
  -loglevel error
  -stats
)

# Optional headers
if [ -n "${FFMPEG_HEADERS:-}" ]; then
  cmd+=(-headers "$FFMPEG_HEADERS")
fi

cmd+=(-i "$url")

if [ ${#extra[@]} -gt 0 ]; then
  cmd+=("${extra[@]}")
else
  cmd+=(-c copy)
fi

cmd+=("$out")

# Print and exec
printf 'Running:'
for arg in "${cmd[@]}"; do
  printf ' %q' "$arg"
done
printf '\n\n'

exec "${cmd[@]}"
