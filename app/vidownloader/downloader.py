#!/usr/bin/env python3
import argparse
import json
import os
import re
import stat
import subprocess
from pathlib import Path

BASE_DEFAULT = "/home/vinay/Videos/msg"
BASE_DIR = Path(__file__).resolve().parent.parent.parent
print(BASE_DIR)

def load_videos(json_path: Path) -> list:
	with json_path.open("r", encoding="utf-8") as f:
		data = json.load(f)
	videos = data.get("videos", [])
	if not isinstance(videos, list):
		raise ValueError("Invalid JSON: 'videos' must be a list")
	return videos


def ensure_executable(sh_path: Path) -> None:
	if not sh_path.exists():
		raise FileNotFoundError(f"ffget.sh not found at {sh_path}")
	mode = sh_path.stat().st_mode
	if not (mode & stat.S_IXUSR):
		sh_path.chmod(mode | stat.S_IXUSR)


def next_start_number(base_dir: Path) -> int:
	base_dir.mkdir(parents=True, exist_ok=True)
	max_num = 0
	num_re = re.compile(r"^(\d+)(?:\.[^.]+)?$")
	for entry in base_dir.iterdir():
		if not entry.is_file():
			continue
		m = num_re.match(entry.name)
		if m:
			try:
				n = int(m.group(1))
				if n > max_num:
					max_num = n
			except ValueError:
				pass
	return max_num + 1


def pick_url(video: dict) -> str | None:
	url = video.get("videoUrl")
	if isinstance(url, str) and url.strip():
		return url.strip()
	url = video.get("trailerUrl")
	if isinstance(url, str) and url.strip():
		return url.strip()
	return None


def run_ffget(ffget_path: Path, url: str, output_path: Path, dry_run: bool) -> int:
	cmd = [str(ffget_path), url, str(output_path)]
	if dry_run:
		print(f"DRY-RUN: {' '.join(cmd)}")
		return 0
	proc = subprocess.run(cmd)
	return proc.returncode


def main() -> int:
	parser = argparse.ArgumentParser(description="Read videos.json and download via ffget.sh")
	parser.add_argument("--json", default=(BASE_DIR / 'data/videos.json'), help="Path to videos.json")
	parser.add_argument("--base", default=BASE_DEFAULT, help="Base output directory")
	parser.add_argument("--start", type=int, default=None, help="Starting number (overrides auto-detect)")
	parser.add_argument("--limit", type=int, default=None, help="Limit number of downloads")
	parser.add_argument("--dry-run", action="store_true", help="Print commands without downloading")
	args = parser.parse_args()

	json_path = Path(args.json)
	base_dir = Path(args.base)
	ffget_path = Path(__file__).with_name("ffget.sh")

	ensure_executable(ffget_path)

	videos = load_videos(json_path)
	start_num = args.start if args.start and args.start > 0 else next_start_number(base_dir)

	count = 0
	num = start_num
	for v in videos:
		url = pick_url(v)
		if not url:
			continue
		out_path = base_dir / str(num)
		rc = run_ffget(ffget_path, url, out_path, args.dry_run)
		if rc != 0:
			print(f"ffget.sh failed for #{num} (rc={rc})")
		num += 1
		count += 1
		if args.limit is not None and count >= args.limit:
			break

	print(f"Processed {count} item(s). Next number would be {num}.")
	return 0


if __name__ == "__main__":
	raise SystemExit(main())

