#!/bin/bash

# Exit if any command fails
set -e

# Check if all arguments are provided
if [ "$#" -ne 3 ]; then
    echo "Usage: $0 <video_path> <start_time> <end_time>"
    echo "Example: $0 /home/user/video.mp4 00:00:10 00:00:30"
    exit 1
fi

# Read input arguments
VIDEO_PATH="$1"
START_TIME="$2"
END_TIME="$3"

# Verify that the file exists
if [ ! -f "$VIDEO_PATH" ]; then
    echo "Error: File not found: $VIDEO_PATH"
    exit 1
fi

# Extract file info
DIR=$(dirname "$VIDEO_PATH")
BASENAME=$(basename "$VIDEO_PATH")
FILENAME="${BASENAME%.*}"
EXT="${BASENAME##*.}"

# Create output file name
OUTPUT_FILE="$DIR/${FILENAME}_trimmed.$EXT"

# Use ffmpeg to trim the video
# -ss : start time
# -to : end time
# -c copy : copies streams without re-encoding (fast)
echo "Trimming video..."
ffmpeg -y -i "$VIDEO_PATH" -ss "$START_TIME" -to "$END_TIME" -c copy "$OUTPUT_FILE"

# Verify if trimming was successful
if [ -f "$OUTPUT_FILE" ]; then
    echo "Trimmed video created: $OUTPUT_FILE"
    echo "Deleting original file..."
    rm "$VIDEO_PATH"
    echo "Original file deleted."
else
    echo "Error: Failed to create trimmed file."
    exit 1
fi

