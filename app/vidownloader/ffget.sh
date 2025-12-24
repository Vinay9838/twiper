#!/usr/bin/env bash
# ffget.sh - simple wrapper to download an HLS (m3u8) with ffmpeg
# Usage: ./ffget.sh URL [OUTPUT] -- [extra ffmpeg args]
# Example: ./ffget.sh "https://.../master.m3u8" myvideo.mp4
# Example with extra args: ./ffget.sh "URL" out.mp4 -- -bsf:a aac_adtstoasc
set -euo pipefail

usage() {
  cat <<EOF
Usage: $0 URL [OUTPUT] -- [extra ffmpeg args]
Examples:
  $0 "https://example.com/playlist.m3u8" out.mp4
  $0 "https://example.com/playlist.m3u8"          # will auto-derive filename
  $0 "URL" out.mp4 -- -bsf:a aac_adtstoasc         # pass extra ffmpeg args
Notes:
  - If OUTPUT has no extension, .mp4 is automatically appended (e.g., "out" -> "out.mp4").
Notes:
  - If you need custom request headers (Cookie, Referer, User-Agent), set
    the FFMPEG_HEADERS environment variable to a single string with CRLF
    separators, e.g.:
      export FFMPEG_HEADERS=$'Cookie: name=value\r\nReferer: https://site.com\r\nUser-Agent: Mozilla/5.0\r\n'
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

# Derive output filename if not provided
if [ -z "${out:-}" ]; then
  base=$(basename "${url%%\?*}")
  out="${base%.*}.mp4"
  if [ -z "$out" ] || [ "$out" = ".mp4" ]; then
    out="output_$(date +%Y%m%d%H%M%S).mp4"
  fi
else
  # If user provided an output name without an extension, append .mp4
  base_out=$(basename -- "$out")
  case "$base_out" in
    *.*) : ;; # has an extension, do nothing
    *) out="$out.mp4" ;;
  esac
fi

# Build ffmpeg command
cmd=(ffmpeg -y)

# Include headers if FFMPEG_HEADERS is set (useful for cookies/referer)
if [ -n "${FFMPEG_HEADERS:-}" ]; then
  cmd+=(-headers "$FFMPEG_HEADERS")
fi

cmd+=(-i "$url")

if [ ${#extra[@]} -gt 0 ]; then
  cmd+=("${extra[@]}")
else
  # default: remux without re-encoding
  cmd+=(-c copy)
fi

cmd+=("$out")

# Print and run
printf 'Running:'
for arg in "${cmd[@]}"; do
  printf ' %q' "$arg"
done
printf '\n\n'

exec "${cmd[@]}"
