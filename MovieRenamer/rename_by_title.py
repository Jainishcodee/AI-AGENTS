"""
rename_by_title.py
------------------
Renames video files (mp4, mkv, etc.) to the real title that is stored inside
the file's metadata -- the same name VLC shows when you start playing it.

Telegram downloads often have garbage names like "684979868.mkv", but the
file still carries a "title" tag in its metadata (e.g. "Wednesday S02E04").
This script reads that tag with ffprobe (part of FFmpeg) and renames the file.

You point it at a FOLDER. Only video files whose name STARTS WITH A NUMBER
(like 684979868.mkv) are touched -- files that already have a proper name
are left alone.

USAGE (from PowerShell):
    # Preview only -- shows what WOULD be renamed, changes nothing (default):
    python rename_by_title.py "C:\\Users\\Jainish\\Downloads"

    # Actually rename the files:
    python rename_by_title.py "C:\\Users\\Jainish\\Downloads" --apply

    # Also look inside sub-folders:
    python rename_by_title.py "C:\\Users\\Jainish\\Downloads" --apply --recursive

Requires: Python 3.8+  and  ffprobe on PATH (you already have FFmpeg installed).
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

# Common video file extensions we will consider.
VIDEO_EXTENSIONS = {
    ".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv",
    ".m4v", ".mpg", ".mpeg", ".webm", ".ts", ".m2ts",
}

# Characters that are illegal in Windows file names -> replace with a space.
ILLEGAL_CHARS = r'[<>:"/\\|?*]'


def get_title(file_path: Path) -> str | None:
    """Return the embedded 'title' metadata tag, or None if there isn't one.

    Checks the container-level title first (what VLC usually shows), then
    falls back to the first stream that has a title tag.
    """
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v", "quiet",
                "-print_format", "json",
                "-show_format",
                "-show_streams",
                str(file_path),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except FileNotFoundError:
        print("ERROR: 'ffprobe' was not found on PATH. Install FFmpeg first.")
        sys.exit(1)

    if result.returncode != 0 or not result.stdout.strip():
        return None

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None

    # 1) Container / format level title (this is what VLC shows most often).
    fmt_tags = data.get("format", {}).get("tags", {})
    title = _pick_title(fmt_tags)
    if title:
        return title

    # 2) Fall back to a title tag on any stream.
    for stream in data.get("streams", []):
        title = _pick_title(stream.get("tags", {}))
        if title:
            return title

    return None


def _pick_title(tags: dict) -> str | None:
    """Tags can be cased differently (title / TITLE / Title)."""
    for key, value in tags.items():
        if key.lower() == "title" and value and str(value).strip():
            return str(value).strip()
    return None


def sanitize_filename(name: str) -> str:
    """Turn an arbitrary title into a safe Windows file name (no extension)."""
    name = re.sub(ILLEGAL_CHARS, " ", name)
    name = name.replace("\n", " ").replace("\r", " ")
    name = re.sub(r"\s+", " ", name).strip()
    name = name.rstrip(". ")  # Windows dislikes trailing dots/spaces.
    return name


def unique_destination(dest: Path) -> Path:
    """If 'dest' already exists, append ' (2)', ' (3)', ... to avoid clobbering."""
    if not dest.exists():
        return dest
    stem, suffix, parent = dest.stem, dest.suffix, dest.parent
    counter = 2
    while True:
        candidate = parent / f"{stem} ({counter}){suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


def iter_video_files(root: Path, recursive: bool):
    """Yield video files whose name STARTS WITH A NUMBER (e.g. 684979868.mkv).

    Files that already have a real name (letters first) are left untouched.
    """
    pattern = "**/*" if recursive else "*"
    for path in sorted(root.glob(pattern)):
        if (
            path.is_file()
            and path.suffix.lower() in VIDEO_EXTENSIONS
            and path.stem[:1].isdigit()
        ):
            yield path


def rename_videos(folder: str, apply: bool, recursive: bool) -> None:
    root = Path(folder).expanduser()
    if not root.is_dir():
        print(f"ERROR: '{folder}' is not a folder.")
        sys.exit(1)

    mode = "APPLYING CHANGES" if apply else "PREVIEW (no changes -- add --apply to rename)"
    print(f"Folder : {root}")
    print(f"Mode   : {mode}")
    print("-" * 70)

    renamed = skipped = unchanged = 0

    for path in iter_video_files(root, recursive):
        title = get_title(path)

        if not title:
            print(f"[skip ] no title metadata : {path.name}")
            skipped += 1
            continue

        new_name = sanitize_filename(title) + path.suffix.lower()

        if new_name == path.name:
            unchanged += 1
            continue

        dest = unique_destination(path.with_name(new_name))

        if apply:
            try:
                path.rename(dest)
                print(f"[done ] {path.name}  ->  {dest.name}")
                renamed += 1
            except OSError as exc:
                print(f"[error] could not rename {path.name}: {exc}")
                skipped += 1
        else:
            print(f"[would] {path.name}  ->  {dest.name}")
            renamed += 1

    print("-" * 70)
    verb = "Renamed" if apply else "Would rename"
    print(f"{verb}: {renamed}   |   No title found: {skipped}   |   Already correct: {unchanged}")
    if not apply and renamed:
        print("\nRun again with --apply to actually rename these files.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Rename video files to the real title stored in their metadata (the name VLC shows)."
    )
    parser.add_argument("folder", help="Folder containing the video files.")
    parser.add_argument("--apply", action="store_true",
                        help="Actually rename. Without this, it only previews.")
    parser.add_argument("--recursive", action="store_true",
                        help="Also process files inside sub-folders.")
    args = parser.parse_args()

    rename_videos(args.folder, apply=args.apply, recursive=args.recursive)


if __name__ == "__main__":
    main()
