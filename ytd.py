import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import os
import json
import shutil
import sys
import urllib.request
import zipfile
import tempfile
import subprocess

try:
    import yt_dlp
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "yt-dlp"])
    import yt_dlp


def _resource(filename):
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, filename)


APP_VERSION = "1.0.4"
RELEASES_API = "https://api.github.com/repos/MeneerJanssens/YouTube-Downloader/releases/latest"

CONFIG_FILE = os.path.join(os.path.expanduser("~"), ".ytd_config.json")
DEFAULT_FOLDER = os.path.join(os.path.expanduser("~"), "Downloads")
FFMPEG_DIR = os.path.join(os.path.expanduser("~"), ".ytd", "bin")
FFMPEG_EXE = os.path.join(FFMPEG_DIR, "ffmpeg" + (".exe" if sys.platform == "win32" else ""))
FFMPEG_ZIP_URL = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"

FORMAT_OPTIONS = {
    "Best quality (video + audio)": "bestvideo+bestaudio/best",
    "1080p": "bestvideo[height<=1080]+bestaudio/best[height<=1080]",
    "720p":  "bestvideo[height<=720]+bestaudio/best[height<=720]",
    "480p":  "bestvideo[height<=480]+bestaudio/best[height<=480]",
    "360p":  "bestvideo[height<=360]+bestaudio/best[height<=360]",
    "Audio only (MP3)": "bestaudio/best",
}

# ── Colour palette ─────────────────────────────────────────────────────────────
BG         = "#f3f3f3"
CARD       = "#ffffff"
BORDER     = "#dcdcdc"
ACCENT     = "#0067b8"
ACCENT_HV  = "#005a9e"
GREEN      = "#107c10"
GREEN_HV   = "#0b5e0b"
RED        = "#c50f1f"
RED_HV     = "#a50d1a"
ORANGE     = "#ca5010"
ORANGE_HV  = "#b34610"
TEXT       = "#1a1a1a"
TEXT_MUTED = "#888888"
LABEL_W    = 80   # px width for left-column labels


def _darker(hex_color, by=18):
    r = max(0, int(hex_color[1:3], 16) - by)
    g = max(0, int(hex_color[3:5], 16) - by)
    b = max(0, int(hex_color[5:7], 16) - by)
    return f"#{r:02x}{g:02x}{b:02x}"


def ffmpeg_available():
    return shutil.which("ffmpeg") is not None or os.path.isfile(FFMPEG_EXE)


def ffmpeg_location():
    if os.path.isfile(FFMPEG_EXE):
        return FFMPEG_DIR
    return None


def load_config():
    try:
        with open(CONFIG_FILE) as f:
            return json.load(f)
    except Exception:
        return {}


def save_config(data):
    try:
        with open(CONFIG_FILE, "w") as f:
            json.dump(data, f)
    except Exception:
        pass


def format_duration(seconds):
    if not seconds:
        return ""
    seconds = int(seconds)
    h, m, s = seconds // 3600, (seconds % 3600) // 60, seconds % 60
    return f"{h}:{m:02}:{s:02}" if h else f"{m}:{s:02}"


def _version_tuple(v):
    return tuple(int(x) for x in v.lstrip("v").split("."))


class YTDApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("YTD – Video Downloader")
        self.minsize(560, 680)
        self.config(bg=BG)
        try:
            self.iconbitmap(_resource("icon.ico"))
        except Exception:
            pass

        self._configure_styles()

        cfg = load_config()
        self._download_folder = cfg.get("folder", DEFAULT_FOLDER)
        self._saved_format = cfg.get("format")

        self._queue = []
        self._cancel_event = threading.Event()
        self._is_running = False
        self._fetched_title = None
        self._fetch_job = None
        self._pending_update_url = None

        self._build_ui()

        if self._saved_format and self._saved_format in FORMAT_OPTIONS:
            self._fmt_var.set(self._saved_format)

        self.after(2000, self._check_for_updates)

    # ── Styles ────────────────────────────────────────────────────────────────

    def _configure_styles(self):
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass

        style.configure(
            "Accent.Horizontal.TProgressbar",
            troughcolor=BORDER, background=ACCENT,
            bordercolor=BORDER, lightcolor=ACCENT, darkcolor=ACCENT,
        )
        style.configure(
            "TCombobox", fieldbackground=CARD, background=CARD,
            foreground=TEXT, bordercolor=BORDER, arrowcolor=TEXT,
        )
        style.map("TCombobox", fieldbackground=[("readonly", CARD)])

    # ── UI helpers ────────────────────────────────────────────────────────────

    def _btn(self, parent, text, command, bg, fg="white", font_bold=False, **kw):
        fnt = ("Segoe UI", 9, "bold") if font_bold else ("Segoe UI", 9)
        b = tk.Button(
            parent, text=text, command=command, bg=bg, fg=fg,
            activebackground=_darker(bg), activeforeground=fg,
            relief="flat", bd=0, cursor="hand2", font=fnt, **kw,
        )
        b.bind("<Enter>", lambda _: b.config(bg=_darker(bg)))
        b.bind("<Leave>", lambda _: b.config(bg=bg))
        return b

    def _card(self, parent, **pack_kw):
        """White bordered card container."""
        outer = tk.Frame(parent, bg=BORDER)
        outer.pack(**pack_kw)
        inner = tk.Frame(outer, bg=CARD)
        inner.pack(fill="both", expand=True, padx=1, pady=1)
        return inner

    def _row(self, parent, label_text):
        """Labelled row inside a card."""
        f = tk.Frame(parent, bg=CARD)
        f.pack(fill="x", padx=14, pady=5)
        tk.Label(
            f, text=label_text, bg=CARD, fg=TEXT_MUTED,
            font=("Segoe UI", 9), width=8, anchor="w",
        ).pack(side="left")
        return f

    # ── Build UI ──────────────────────────────────────────────────────────────

    def _build_ui(self):
        # Thin accent bar at the very top
        tk.Frame(self, bg=ACCENT, height=3).pack(fill="x")

        outer_pad = {"padx": 14, "pady": 0}

        # ── URL card ──────────────────────────────────────────────────────────
        url_card = self._card(self, fill="x", padx=14, pady=(12, 0))

        url_row = tk.Frame(url_card, bg=CARD)
        url_row.pack(fill="x", padx=14, pady=(10, 6))

        self._url_var = tk.StringVar()
        self._url_var.trace_add("write", self._on_url_change)

        url_entry_frame = tk.Frame(url_row, bg=BORDER, padx=1, pady=1)
        url_entry_frame.pack(side="left", fill="x", expand=True)
        tk.Entry(
            url_entry_frame, textvariable=self._url_var,
            relief="flat", bd=4, font=("Segoe UI", 10),
            bg=CARD, fg=TEXT, insertbackground=TEXT,
        ).pack(fill="x")

        self._fetch_btn = self._btn(
            url_row, "Fetch", self._fetch_info, ACCENT,
            padx=12, pady=5, font_bold=False,
        )
        self._fetch_btn.pack(side="left", padx=(6, 4))

        self._btn(
            url_row, "Add to Queue", self._add_to_queue, GREEN,
            padx=12, pady=5,
        ).pack(side="left")

        self._info_var = tk.StringVar(value="")
        self._info_lbl = tk.Label(
            url_card, textvariable=self._info_var, bg=CARD,
            fg=ACCENT, font=("Segoe UI", 9), anchor="w", wraplength=520,
        )
        self._info_lbl.pack(fill="x", padx=14, pady=(0, 8))

        # ── Settings card ─────────────────────────────────────────────────────
        settings_card = self._card(self, fill="x", padx=14, pady=(8, 0))

        # Format row
        fmt_row = self._row(settings_card, "Format")
        self._fmt_var = tk.StringVar(value=list(FORMAT_OPTIONS.keys())[0])
        self._fmt_var.trace_add("write", self._save_settings)
        ttk.Combobox(
            fmt_row, textvariable=self._fmt_var,
            values=list(FORMAT_OPTIONS.keys()), state="readonly",
            font=("Segoe UI", 9), width=44,
        ).pack(side="left", fill="x", expand=True)

        # Folder row
        folder_row = self._row(settings_card, "Save to")
        self._folder_label = tk.Label(
            folder_row, text=self._download_folder,
            bg="#f8f8f8", fg=TEXT, font=("Segoe UI", 9),
            anchor="w", relief="flat", bd=0,
        )

        folder_border = tk.Frame(folder_row, bg=BORDER, padx=1, pady=1)
        folder_border.pack(side="left", fill="x", expand=True)
        self._folder_label = tk.Label(
            folder_border, text=self._download_folder,
            bg=CARD, fg=TEXT, font=("Segoe UI", 9), anchor="w", padx=4,
        )
        self._folder_label.pack(fill="x")

        self._btn(folder_row, "Browse…", self._browse, ACCENT, padx=10, pady=3).pack(
            side="left", padx=(6, 0)
        )

        # FFmpeg row
        ffmpeg_row = self._row(settings_card, "FFmpeg")
        self._ffmpeg_status_var = tk.StringVar()
        self._ffmpeg_status_lbl = tk.Label(
            ffmpeg_row, textvariable=self._ffmpeg_status_var,
            bg=CARD, font=("Segoe UI", 9), anchor="w",
        )
        self._ffmpeg_status_lbl.pack(side="left", fill="x", expand=True)
        self._ffmpeg_btn = self._btn(
            ffmpeg_row, "Install", self._install_ffmpeg, ORANGE, padx=10, pady=3,
        )
        tk.Frame(settings_card, bg=CARD, height=4).pack()  # bottom padding
        self._update_ffmpeg_ui()

        # ── Queue card ────────────────────────────────────────────────────────
        tk.Label(
            self, text="Queue", bg=BG, fg=TEXT,
            font=("Segoe UI", 9, "bold"),
        ).pack(anchor="w", padx=15, pady=(12, 4))

        queue_card = self._card(self, fill="both", expand=True, padx=14)

        self._queue_list = tk.Listbox(
            queue_card, relief="flat", bd=0,
            bg=CARD, fg=TEXT, selectbackground=ACCENT,
            selectforeground="white", font=("Segoe UI", 9),
            activestyle="none", height=5,
        )
        self._queue_list.pack(fill="both", expand=True, padx=1, pady=1)

        remove_row = tk.Frame(queue_card, bg=CARD)
        remove_row.pack(fill="x", padx=10, pady=(0, 6))
        self._btn(
            remove_row, "Remove selected", self._remove_selected,
            "#e8e8e8", fg=TEXT, padx=8, pady=2,
        ).pack(side="right")

        # ── Progress ──────────────────────────────────────────────────────────
        self._progress = ttk.Progressbar(
            self, length=440, mode="determinate",
            style="Accent.Horizontal.TProgressbar",
        )
        self._progress.pack(fill="x", padx=14, pady=(10, 2))

        self._status_var = tk.StringVar(value="Ready.")
        tk.Label(
            self, textvariable=self._status_var, bg=BG,
            fg=TEXT_MUTED, font=("Segoe UI", 9), anchor="w",
        ).pack(fill="x", padx=15)

        # ── Log card ──────────────────────────────────────────────────────────
        tk.Label(
            self, text="Log", bg=BG, fg=TEXT,
            font=("Segoe UI", 9, "bold"),
        ).pack(anchor="w", padx=15, pady=(10, 4))

        log_card = self._card(self, fill="x", padx=14)
        self._log = tk.Text(
            log_card, height=5, relief="flat", bd=0,
            bg="#1e1e1e", fg="#d4d4d4", font=("Consolas", 9),
            insertbackground="#d4d4d4",
        )
        log_scroll = tk.Scrollbar(log_card, command=self._log.yview, bg="#2d2d2d")
        self._log.configure(yscrollcommand=log_scroll.set, state="disabled")
        log_scroll.pack(side="right", fill="y", padx=(0, 1), pady=1)
        self._log.pack(fill="x", padx=1, pady=1)

        # ── Bottom bar ────────────────────────────────────────────────────────
        bottom = tk.Frame(self, bg=BG)
        bottom.pack(fill="x", padx=14, pady=(10, 14))

        self._start_btn = self._btn(
            bottom, "⬇  Download All", self._start_queue, ACCENT,
            font_bold=True, padx=18, pady=8,
        )
        self._start_btn.pack(side="left", padx=(0, 8))

        self._cancel_btn = self._btn(
            bottom, "Cancel", self._cancel, RED,
            padx=18, pady=8,
        )
        self._cancel_btn.config(state="disabled")
        self._cancel_btn.pack(side="left")

        self._update_btn = self._btn(
            bottom, "", self._apply_update, GREEN, padx=12, pady=8,
        )
        self._version_lbl = tk.Label(
            bottom, text=f"v{APP_VERSION}", bg=BG,
            fg=TEXT_MUTED, font=("Segoe UI", 8),
        )
        self._version_lbl.pack(side="right")

    # ── Persistence ───────────────────────────────────────────────────────────

    def _save_settings(self, *_):
        save_config({"folder": self._download_folder, "format": self._fmt_var.get()})

    # ── Auto-update ───────────────────────────────────────────────────────────

    def _check_for_updates(self):
        threading.Thread(target=self._do_check_updates, daemon=True).start()

    def _do_check_updates(self):
        try:
            req = urllib.request.Request(
                RELEASES_API,
                headers={"User-Agent": f"YTD/{APP_VERSION}"},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())

            latest = data["tag_name"].lstrip("v")
            if _version_tuple(latest) <= _version_tuple(APP_VERSION):
                return

            assets = data.get("assets", [])
            if sys.platform == "win32":
                url = next(
                    (a["browser_download_url"] for a in assets if a["name"].endswith(".exe")),
                    data.get("html_url"),
                )
            else:
                url = data.get("html_url")

            self.after(0, self._on_update_available, latest, url)
        except Exception:
            pass

    def _on_update_available(self, latest, url):
        self._pending_update_url = url
        self._update_btn.config(text=f"↑ Update to v{latest}")
        self._update_btn.pack(side="right", padx=(0, 8))

    def _apply_update(self):
        url = self._pending_update_url
        if not url:
            return
        if sys.platform != "win32":
            import webbrowser
            webbrowser.open(url)
            return
        self._update_btn.config(state="disabled", text="Downloading…")
        threading.Thread(target=self._do_download_update, args=(url,), daemon=True).start()

    def _do_download_update(self, url):
        try:
            tmp = tempfile.mktemp(suffix=".exe")

            def _progress(count, block, total):
                if total > 0:
                    pct = min(count * block / total * 100, 100)
                    self.after(0, self._update_btn.config, {"text": f"Downloading… {pct:.0f}%"})

            urllib.request.urlretrieve(url, tmp, reporthook=_progress)
            self.after(0, self._launch_updater, tmp)
        except Exception as e:
            self.after(0, self._update_btn.config, {"text": "Download failed — retry", "state": "normal"})
            self.after(0, self._log_write, f"✗ Update error: {e}")

    def _launch_updater(self, new_exe):
        current = sys.executable
        bat = tempfile.mktemp(suffix=".bat")
        with open(bat, "w") as f:
            f.write(
                f"@echo off\n"
                f"timeout /t 2 /nobreak > nul\n"
                f'copy /Y "{new_exe}" "{current}"\n'
                f'start "" "{current}"\n'
                f'del "{new_exe}"\n'
                f'del "%~f0"\n'
            )
        subprocess.Popen(["cmd", "/c", bat], creationflags=subprocess.CREATE_NO_WINDOW)
        self.quit()

    # ── FFmpeg install ─────────────────────────────────────────────────────────

    def _update_ffmpeg_ui(self):
        if ffmpeg_available():
            self._ffmpeg_status_var.set("✓  Ready")
            self._ffmpeg_status_lbl.config(fg=GREEN)
            self._ffmpeg_btn.pack_forget()
        else:
            self._ffmpeg_status_var.set("Not installed — needed for best quality and MP3")
            self._ffmpeg_status_lbl.config(fg=ORANGE)
            self._ffmpeg_btn.pack(side="left", padx=(6, 0))

    def _install_ffmpeg(self):
        if sys.platform != "win32":
            messagebox.showinfo(
                "Install FFmpeg",
                "On macOS, open Terminal and run:\n\n  brew install ffmpeg\n\n"
                "If you don't have Homebrew: https://brew.sh",
            )
            return
        self._ffmpeg_btn.config(state="disabled", text="Installing…")
        self._ffmpeg_status_var.set("Downloading FFmpeg…")
        threading.Thread(target=self._do_install_ffmpeg, daemon=True).start()

    def _do_install_ffmpeg(self):
        try:
            os.makedirs(FFMPEG_DIR, exist_ok=True)
            tmp = tempfile.mktemp(suffix=".zip")

            def _progress(count, block, total):
                if total > 0:
                    pct = min(count * block / total * 100, 100)
                    self.after(0, self._ffmpeg_status_var.set, f"Downloading FFmpeg… {pct:.0f}%")

            urllib.request.urlretrieve(FFMPEG_ZIP_URL, tmp, reporthook=_progress)
            self.after(0, self._ffmpeg_status_var.set, "Extracting…")

            with zipfile.ZipFile(tmp) as z:
                for name in z.namelist():
                    if name.endswith("/bin/ffmpeg.exe"):
                        with z.open(name) as src, open(FFMPEG_EXE, "wb") as dst:
                            dst.write(src.read())
                        break
            os.unlink(tmp)

            if not os.path.isfile(FFMPEG_EXE):
                raise RuntimeError("ffmpeg.exe not found in archive")

            self.after(0, self._on_ffmpeg_ready)
        except Exception as e:
            self.after(0, self._on_ffmpeg_error, str(e))

    def _on_ffmpeg_ready(self):
        self._log_write("✓ FFmpeg installed successfully")
        self._ffmpeg_btn.config(state="normal", text="Install")
        self._update_ffmpeg_ui()

    def _on_ffmpeg_error(self, msg):
        self._ffmpeg_status_var.set("Install failed — try again")
        self._ffmpeg_status_lbl.config(fg=RED)
        self._ffmpeg_btn.config(state="normal", text="Retry")
        self._log_write(f"✗ FFmpeg install error: {msg}")

    # ── URL / info fetch ──────────────────────────────────────────────────────

    def _on_url_change(self, *_):
        if self._fetch_job:
            self.after_cancel(self._fetch_job)
        url = self._url_var.get().strip()
        if url.startswith("http"):
            self._fetch_job = self.after(800, self._fetch_info)
        else:
            self._info_var.set("")
            self._fetched_title = None

    def _fetch_info(self):
        url = self._url_var.get().strip()
        if not url:
            return
        self._info_var.set("Fetching info…")
        self._fetch_btn.config(state="disabled")
        threading.Thread(target=self._do_fetch, args=(url,), daemon=True).start()

    def _do_fetch(self, url):
        try:
            with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True}) as ydl:
                info = ydl.extract_info(url, download=False)
            title = info.get("title", "Unknown")
            duration = format_duration(info.get("duration"))
            uploader = info.get("uploader") or info.get("channel") or ""
            parts = [title]
            if duration:
                parts.append(duration)
            if uploader:
                parts.append(f"by {uploader}")
            self.after(0, self._on_fetch_done, "  |  ".join(parts), title)
        except Exception as e:
            self.after(0, self._on_fetch_error, str(e))

    def _on_fetch_done(self, display, title):
        self._info_var.set(display)
        self._fetched_title = title
        self._fetch_btn.config(state="normal")

    def _on_fetch_error(self, err):
        self._info_var.set(f"Could not fetch info: {err[:90]}")
        self._fetched_title = None
        self._fetch_btn.config(state="normal")

    # ── Queue management ──────────────────────────────────────────────────────

    def _add_to_queue(self):
        url = self._url_var.get().strip()
        if not url:
            messagebox.showwarning("No URL", "Please paste a URL first.")
            return
        title = self._fetched_title or url
        self._queue.append({"url": url, "title": title, "status": "pending"})
        self._refresh_queue_list()
        self._url_var.set("")
        self._info_var.set("")
        self._fetched_title = None

    def _remove_selected(self):
        sel = self._queue_list.curselection()
        if not sel:
            return
        idx = sel[0]
        if self._queue[idx]["status"] == "downloading":
            messagebox.showinfo("In progress", "Can't remove an item that is currently downloading.")
            return
        del self._queue[idx]
        self._refresh_queue_list()

    def _refresh_queue_list(self):
        self._queue_list.delete(0, "end")
        icons = {"pending": "⏳", "downloading": "⬇", "done": "✓", "error": "✗", "cancelled": "–"}
        colors = {"done": GREEN, "error": RED, "cancelled": TEXT_MUTED, "downloading": ACCENT}
        for item in self._queue:
            icon = icons.get(item["status"], "")
            self._queue_list.insert("end", f"   {icon}  {item['title']}")
            color = colors.get(item["status"])
            if color:
                self._queue_list.itemconfig("end", fg=color)

    # ── Folder ────────────────────────────────────────────────────────────────

    def _browse(self):
        folder = filedialog.askdirectory(initialdir=self._download_folder)
        if folder:
            self._download_folder = folder
            self._folder_label.config(text=folder)
            self._save_settings()

    # ── Download ──────────────────────────────────────────────────────────────

    def _start_queue(self):
        if not any(item["status"] == "pending" for item in self._queue):
            messagebox.showinfo("Queue empty", "Add some URLs to the queue first.")
            return
        if self._is_running:
            return
        self._is_running = True
        self._cancel_event.clear()
        self._start_btn.config(state="disabled")
        self._cancel_btn.config(state="normal")
        threading.Thread(target=self._run_queue, daemon=True).start()

    def _run_queue(self):
        for item in self._queue:
            if item["status"] != "pending":
                continue
            if self._cancel_event.is_set():
                item["status"] = "cancelled"
                self.after(0, self._refresh_queue_list)
                continue
            item["status"] = "downloading"
            self.after(0, self._refresh_queue_list)
            success, _ = self._download_one(item["url"])
            item["status"] = "cancelled" if self._cancel_event.is_set() else ("done" if success else "error")
            self.after(0, self._refresh_queue_list)
        self.after(0, self._on_queue_done)

    def _download_one(self, url):
        fmt_key = self._fmt_var.get()
        fmt = FORMAT_OPTIONS[fmt_key]
        audio_only = "Audio only" in fmt_key

        if not ffmpeg_available() and not audio_only:
            fmt = fmt.split("/")[-1]
            self.after(0, self._log_write,
                       "[warn] FFmpeg not found — using pre-merged format (quality may be slightly lower)")

        ydl_opts = {
            "format": fmt,
            "outtmpl": os.path.join(self._download_folder, "%(title)s.%(ext)s"),
            "progress_hooks": [self._progress_hook],
            "quiet": True,
            "no_warnings": False,
            "logger": _YTDLogger(self._log_write),
        }

        loc = ffmpeg_location()
        if loc:
            ydl_opts["ffmpeg_location"] = loc

        if audio_only:
            ydl_opts["postprocessors"] = [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }]

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
            self.after(0, self._set_status, f"Done! Saved to: {self._download_folder}")
            self.after(0, self._log_write, f"✓ Saved to {self._download_folder}")
            return True, None
        except Exception as exc:
            msg = str(exc)
            if "cancelled" not in msg.lower():
                self.after(0, self._log_write, f"✗ Error: {msg}")
            return False, msg

    def _cancel(self):
        self._cancel_event.set()
        self._set_status("Cancelling…")

    def _on_queue_done(self):
        self._is_running = False
        self._start_btn.config(state="normal")
        self._cancel_btn.config(state="disabled")
        self._progress["value"] = 0
        done = sum(1 for item in self._queue if item["status"] == "done")
        total = len(self._queue)
        self._set_status(f"Finished — {done} of {total} downloaded.")
        self._log_write(f"─── Queue complete: {done}/{total} ───")

    # ── Progress hook ─────────────────────────────────────────────────────────

    def _progress_hook(self, d):
        if self._cancel_event.is_set():
            raise Exception("cancelled")
        status = d.get("status")
        if status == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            downloaded = d.get("downloaded_bytes", 0)
            speed = d.get("_speed_str", "")
            eta = d.get("_eta_str", "")
            pct = (downloaded / total * 100) if total else 0
            self.after(0, self._update_progress, pct, f"Downloading… {pct:.0f}%  {speed}  ETA {eta}")
        elif status == "finished":
            self.after(0, self._update_progress, 100, "Processing…")

    def _update_progress(self, pct, msg):
        self._progress["value"] = pct
        self._set_status(msg)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _log_write(self, text):
        self._log.config(state="normal")
        self._log.insert("end", text + "\n")
        self._log.see("end")
        self._log.config(state="disabled")

    def _set_status(self, text):
        self._status_var.set(text)


class _YTDLogger:
    def __init__(self, write_fn):
        self._write = write_fn

    def debug(self, msg):
        if msg.startswith("[debug]"):
            return
        self._write(msg)

    def info(self, msg):
        self._write(msg)

    def warning(self, msg):
        self._write(f"[warn] {msg}")

    def error(self, msg):
        self._write(f"[error] {msg}")


if __name__ == "__main__":
    app = YTDApp()
    app.mainloop()
