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

## MP3 / Audio downloads

MP3 conversion requires **FFmpeg** to be installed and on your PATH.

1. Download FFmpeg from https://ffmpeg.org/download.html
2. Extract and add the `bin` folder to your system PATH
3. Restart YTD

## For developers

Requirements: Python 3.6+, [yt-dlp](https://github.com/yt-dlp/yt-dlp)

```
pip install yt-dlp
python ytd.py
```

To rebuild the exe:

```
pip install pyinstaller pillow
python create_icon.py
pyinstaller --onefile --windowed --icon=icon.ico --add-data "icon.ico;." --name YTD ytd.py
```

The resulting `dist/YTD.exe` is self-contained and needs no Python installation.

## Creating a release

Push a version tag to trigger the GitHub Actions workflow, which automatically builds for both Windows and macOS:

```
git tag v1.0.0
git push origin v1.0.0
```

The workflow uploads `YTD.exe` and `YTD-mac.zip` to the release automatically.
