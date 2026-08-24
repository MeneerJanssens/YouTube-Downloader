# YTD – Video Downloader

A simple desktop app for downloading YouTube videos. No Python required.

## Download

Grab the latest version from the [Releases](https://github.com/MeneerJanssens/YTD/releases) page:

| Platform | File |
|----------|------|
| Windows  | `YTD.exe` — double-click to run |
| macOS    | `YTD-mac.zip` — unzip, then double-click `YTD.app` |

> First launch takes a few seconds — this is normal.

## Features

- Download videos in multiple qualities: Best, 1080p, 720p, 480p, 360p
- Download audio only as MP3 (requires FFmpeg, see below)
- Queue multiple URLs and download them in one go
- Live progress bar with speed and ETA
- Remembers your last used folder and format

## JavaScript runtime (YouTube)

Recent yt-dlp versions need a small JavaScript runtime to download from YouTube.
YTD checks for one on startup and offers to install **QuickJS** (~2 MB) automatically;
it lives in `~/.ytd/bin`, next to FFmpeg. You can also install Deno 2+, Node.js 20+
or Bun yourself and put it on your PATH.

## MP3 / Audio downloads

MP3 conversion requires **FFmpeg**. YTD shows its status in the Settings panel:

- **Windows:** click **Install** in the FFmpeg row — YTD downloads, verifies and
  installs FFmpeg automatically (no admin rights needed).
- **macOS:** run `brew install ffmpeg` in Terminal (Homebrew:
  https://brew.sh).
- Or install manually from https://ffmpeg.org/download.html and make sure it is
  on your PATH.

## For developers

Requirements: Python 3.8+, [yt-dlp](https://github.com/yt-dlp/yt-dlp)

```
pip install yt-dlp
python ytd.py
```

To rebuild the exe locally:

```
pip install -r requirements-build.txt
python create_icon.py
pyinstaller YTD.spec
```

or, without the spec file:

```
pyinstaller --onefile --windowed --icon=icon.ico --add-data "icon.ico;." --name YTD ytd.py
```

The resulting `dist/YTD.exe` is self-contained and needs no Python installation.

## Creating a release

Push a version tag to trigger the GitHub Actions workflow, which automatically builds for both Windows and macOS:

```
git tag v1.0.0
git push origin v1.0.0
```

The tag **must match `APP_VERSION` in `ytd.py`** — the workflow verifies this
before building, so bump the version in the code first.

The workflow uploads `YTD.exe` and `YTD-mac.zip` to the release automatically.
