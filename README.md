# YTD – Video Downloader

A simple desktop app for downloading YouTube videos. No Python required.

## Download

Grab **YTD.exe** from the [Releases](https://github.com/MeneerJanssens/YTD/releases) page and double-click it. That's it.

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
pip install pyinstaller
pyinstaller --onefile --windowed --name "YTD" ytd.py
```

The resulting `dist/YTD.exe` is self-contained and needs no Python installation.
