import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import os
import json
import shutil
import sys
import platform
import tarfile
import urllib.request
import urllib.error
import zipfile
import tempfile
import subprocess
import hashlib
import re
import webbrowser

try:
    import yt_dlp
except ImportError:
    yt_dlp = None  # handled with a user-facing error at startup


def _resource(filename):
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, filename)


APP_VERSION = "1.0.4"
RELEASES_API = "https://api.github.com/repos/MeneerJanssens/YouTube-Downloader/releases/latest"

CONFIG_FILE = os.path.join(os.path.expanduser("~"), ".ytd_config.json")
DEFAULT_FOLDER = os.path.join(os.path.expanduser("~"), "Downloads")
FFMPEG_DIR = os.path.join(os.path.expanduser("~"), ".ytd", "bin")
FFMPEG_EXE = os.path.join(FFMPEG_DIR, "ffmpeg" + (".exe" if sys.platform == "win32" else ""))
FFMPEG_API = "https://api.github.com/repos/BtbN/FFmpeg-Builds/releases/latest"
FFMPEG_API_FALLBACK = "https://api.github.com/repos/BtbN/FFmpeg-Builds/releases?per_page=1"
QJS_EXE = os.path.join(FFMPEG_DIR, "qjs" + (".exe" if sys.platform == "win32" else ""))
QJS_API = "https://api.github.com/repos/quickjs-ng/quickjs/releases/latest"

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


def _darker(hex_color, by=18):
    r = max(0, int(hex_color[1:3], 16) - by)
    g = max(0, int(hex_color[3:5], 16) - by)
    b = max(0, int(hex_color[5:7], 16) - by)
    return f"#{r:02x}{g:02x}{b:02x}"


def _temp_path(suffix=""):
    """Create a unique temp file, close it and return its path."""
    f = tempfile.NamedTemporaryFile(prefix="ytd_", suffix=suffix, delete=False)
    f.close()
    return f.name


def _silent_unlink(path):
    try:
        os.unlink(path)
    except OSError:
        pass


def _download_file(url, path, progress_cb=None, timeout=60, resume=False):
    """Download `url` to `path` with a timeout, optional progress and resume.

    `progress_cb(done_bytes, total_bytes)` is called after each chunk.
    Returns `path` on success.
    """
    headers = {"User-Agent": f"YTD/{APP_VERSION}"}
    mode, offset = "wb", 0
    if resume and os.path.isfile(path) and os.path.getsize(path) > 0:
        offset = os.path.getsize(path)
        headers["Range"] = f"bytes={offset}-"
        mode = "ab"

    req = urllib.request.Request(url, headers=headers)
    try:
        resp = urllib.request.urlopen(req, timeout=timeout)
    except urllib.error.HTTPError as e:
        if e.code == 416:  # Range not satisfiable → already fully downloaded
            return path
        raise

    if resume and offset and resp.status != 206:
        # Server ignored the Range header — start over.
        offset, mode = 0, "wb"

    total = int(resp.headers.get("Content-Length") or 0) + offset
    done = offset
    with open(path, mode) as f:
        while True:
            chunk = resp.read(256 * 1024)
            if not chunk:
                break
            f.write(chunk)
            done += len(chunk)
            if progress_cb:
                progress_cb(done, total)
    return path


def _sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _ffmpeg_release_info():
    """Return (zip_url, sha256_hex) for the latest Windows FFmpeg build.

    Discovered via the GitHub API so the download is verified against the
    digest GitHub publishes for the asset ("sha256:" may be empty if GitHub
    did not publish one for this asset).
    """
    req = urllib.request.Request(FFMPEG_API, headers={"User-Agent": f"YTD/{APP_VERSION}"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
    except Exception:
        req = urllib.request.Request(
            FFMPEG_API_FALLBACK, headers={"User-Agent": f"YTD/{APP_VERSION}"}
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())[0]

    assets = data.get("assets", [])
    zips = [a for a in assets if a["name"].endswith("-win64-gpl.zip")]
    if not zips:
        raise RuntimeError("FFmpeg build not found in release assets")
    asset = next((a for a in zips if a["name"] == "ffmpeg-master-latest-win64-gpl.zip"), zips[0])

    digest = asset.get("digest", "") or ""
    sha256_hex = digest.split(":", 1)[1] if digest.startswith("sha256:") else ""
    return asset["browser_download_url"], sha256_hex


def _quickjs_release_info():
    """Return (url, sha256_hex) for a QuickJS-ng binary for this platform."""
    req = urllib.request.Request(QJS_API, headers={"User-Agent": f"YTD/{APP_VERSION}"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read())

    machine = platform.machine().lower()
    is_arm = machine in ("arm64", "aarch64")
    if sys.platform == "win32":
        os_word, arch_words = "windows", ("x86_64", "x86", "arm64")
    else:
        os_word = "darwin"
        arch_words = (("aarch64", "x86_64") if is_arm else ("x86_64", "aarch64"))

    # Assets look like: qjs-windows-x86_64.exe, qjs-darwin-aarch64, qjs-linux-x86_64
    assets = data.get("assets", [])
    cands = [
        a for a in assets
        if a["name"].lower().startswith("qjs-") and os_word in a["name"].lower()
    ]
    if not cands:
        raise RuntimeError("no QuickJS build found in release assets")
    asset = next(
        (a for arch in arch_words for a in cands if arch in a["name"].lower()),
        cands[0],
    )

    digest = asset.get("digest", "") or ""
    sha256_hex = digest.split(":", 1)[1] if digest.startswith("sha256:") else ""
    return asset["browser_download_url"], sha256_hex


def _extract_executable(src, dest, basename):
    """Copy the `basename` executable out of a zip/tar.gz, or copy the file itself."""
    lower = src.lower()
    wanted = (basename, basename + ".exe")
    if lower.endswith(".zip"):
        with zipfile.ZipFile(src) as z:
            for name in z.namelist():
                if os.path.basename(name.rstrip("/")) in wanted:
                    with z.open(name) as fsrc, open(dest, "wb") as fdst:
                        shutil.copyfileobj(fsrc, fdst)
                    return
        raise RuntimeError(f"{basename} not found in archive")
    if lower.endswith((".tar.gz", ".tgz")):
        with tarfile.open(src) as t:
            for member in t.getmembers():
                if os.path.basename(member.name.rstrip("/")) in wanted:
                    with t.extractfile(member) as fsrc, open(dest, "wb") as fdst:
                        shutil.copyfileobj(fsrc, fdst)
                    return
        raise RuntimeError(f"{basename} not found in archive")
    shutil.copyfile(src, dest)


def js_runtime_opts():
    """Build the yt-dlp `js_runtimes` option from every runtime found.

    Returns a dict to pass as the `js_runtimes` ydl_opts key, or None when no
    runtime was found (yt-dlp then falls back to its own default detection).
    yt-dlp itself picks the highest-priority enabled runtime
    (deno > node > quickjs > bun).
    """
    runtimes = {}
    # qjs bundled inside the app (PyInstaller datas, next to the exe)
    bundled = _resource("qjs" + (".exe" if sys.platform == "win32" else ""))
    if os.path.isfile(bundled):
        runtimes["quickjs"] = {"path": bundled}
    # managed copy in ~/.ytd/bin
    elif os.path.isfile(QJS_EXE):
        runtimes["quickjs"] = {"path": QJS_EXE}
    # system runtimes (yt-dlp needs node>=20, deno>=2, bun>=1.0.31)
    for name, exe in (("deno", "deno"), ("node", "node"), ("bun", "bun"), ("quickjs", "qjs")):
        if name in runtimes:
            continue
        path = shutil.which(exe)
        if path:
            runtimes[name] = {"path": path}
    return runtimes or None


def js_ready_name():
    """Highest-priority available runtime name, or None."""
    opts = js_runtime_opts() or {}
    for name in ("deno", "node", "quickjs", "bun"):
        if name in opts:
            return name
    return None


def _verify_exe(path):
    """Integrity check for a downloaded updater exe: PE header + Authenticode.

    Returns True if the file looks like a PE executable whose signature (when
    present) is Valid; unsigned files are accepted, tampered signed files are
    rejected.
    """
    try:
        with open(path, "rb") as f:
            if f.read(2) != b"MZ":
                return False
    except OSError:
        return False

    try:
        env = dict(os.environ, YTD_VERIFY=path)
        ps = (
            "$s = Get-AuthenticodeSignature -LiteralPath $env:YTD_VERIFY; "
            "if ($s.Status -eq 'Valid' -or $s.Status -eq 'NotSigned') { exit 0 } else { exit 1 }"
        )
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
            env=env, capture_output=True, timeout=120,
        )
        return proc.returncode == 0
    except Exception:
        return False


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
    """Parse a version string into a tuple of ints, ignoring non-numeric parts."""
    nums = []
    for part in re.split(r"[^0-9]+", str(v).lstrip("v")):
        if part:
            nums.append(int(part))
    return tuple(nums)


class YTDApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("YTD – Video Downloader")
        self.minsize(560, 680)
        self.config(bg=BG)
        try:
            icon = _resource("icon.icns" if sys.platform == "darwin" else "icon.ico")
            self.iconbitmap(icon)
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
        self._pending_release_url = None
        self._pending_update_sha256 = ""

        self._build_ui()

        if yt_dlp is None:
            messagebox.showerror(
                "yt-dlp missing",
                "yt-dlp is not installed, so YTD cannot download videos.\n\n"
                "Install it and restart YTD:\n"
                "    pip install yt-dlp",
            )
            self.quit()
            return

        if self._saved_format and self._saved_format in FORMAT_OPTIONS:
            self._fmt_var.set(self._saved_format)

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(2000, self._check_for_updates)
        self.after(2500, self._prompt_js_runtime)

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

        # JS runtime row
        js_row = self._row(settings_card, "JS engine")
        self._js_status_var = tk.StringVar()
        self._js_status_lbl = tk.Label(
            js_row, textvariable=self._js_status_var,
            bg=CARD, font=("Segoe UI", 9), anchor="w",
        )
        self._js_status_lbl.pack(side="left", fill="x", expand=True)
        self._js_btn = self._btn(
            js_row, "Install", self._install_js_runtime, ORANGE, padx=10, pady=3,
        )
        tk.Frame(settings_card, bg=CARD, height=4).pack()  # bottom padding
        self._update_ffmpeg_ui()
        self._update_js_ui()

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

    # ── Shutdown ──────────────────────────────────────────────────────────────

    def _on_close(self):
        if self._is_running and not messagebox.askyesno(
            "Quit YTD", "Downloads are in progress.\n\nCancel them and quit?"
        ):
            return
        self._cancel_event.set()
        self.destroy()

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

            release_url = data.get("html_url")
            sha256_hex = ""
            if sys.platform == "win32":
                exe_assets = [a for a in data.get("assets", []) if a["name"].lower().endswith(".exe")]
                if not exe_assets:
                    return  # nothing safe to download — skip the update
                asset = next(
                    (a for a in exe_assets if a["name"].upper().startswith("YTD")),
                    exe_assets[0],
                )
                url = asset["browser_download_url"]
                digest = asset.get("digest", "") or ""
                sha256_hex = digest.split(":", 1)[1] if digest.startswith("sha256:") else ""
            else:
                url = release_url

            self.after(0, self._on_update_available, latest, url, release_url, sha256_hex)
        except Exception:
            pass

    def _on_update_available(self, latest, url, release_url, sha256_hex):
        self._pending_update_url = url
        self._pending_release_url = release_url
        self._pending_update_sha256 = sha256_hex
        self._update_btn.config(text=f"↑ Update to v{latest}")
        self._update_btn.pack(side="right", padx=(0, 8))

    def _apply_update(self):
        url = self._pending_update_url
        if not url:
            return
        # Self-replacement only makes sense in a frozen (exe) build; otherwise
        # point the user at the release page.
        if not getattr(sys, "frozen", False) or sys.platform != "win32":
            webbrowser.open(self._pending_release_url or url)
            return
        self._update_btn.config(state="disabled", text="Downloading…")
        threading.Thread(target=self._do_download_update, args=(url,), daemon=True).start()

    def _do_download_update(self, url):
        tmp = _temp_path(".exe")
        try:
            def _progress(done, total):
                if total > 0:
                    pct = min(done / total * 100, 100)
                    self.after(0, self._update_btn.config, {"text": f"Downloading… {pct:.0f}%"})

            _download_file(url, tmp, progress_cb=_progress)

            if self._pending_update_sha256:
                if _sha256_file(tmp).lower() != self._pending_update_sha256.lower():
                    raise RuntimeError("downloaded file failed its checksum check")
            if not _verify_exe(tmp):
                raise RuntimeError("downloaded file failed integrity verification")

            self.after(0, self._launch_updater, tmp)
        except Exception as e:
            _silent_unlink(tmp)
            self.after(0, self._update_btn.config, {"text": "Update failed — retry", "state": "normal"})
            self.after(0, self._log_write, f"✗ Update error: {e}")

    def _launch_updater(self, new_exe):
        current = sys.executable
        bat = _temp_path(".bat")
        with open(bat, "w") as f:
            f.write(
                "@echo off\n"
                "timeout /t 3 /nobreak > nul\n"
                'copy /Y "%~1" "%~2" > nul\n'
                "if errorlevel 1 goto failed\n"
                'start "" "%~2"\n'
                'del "%~1" > nul 2>&1\n'
                'del "%~f0"\n'
                "exit /b 0\n"
                ":failed\n"
                "echo.\n"
                'echo YTD update failed - could not replace "%~2".\n'
                'echo The new version was kept at "%~1".\n'
                "echo Close all YTD windows and run that file manually.\n"
                "pause\n"
                "exit /b 1\n"
            )
        subprocess.Popen(
            ["cmd", "/c", bat, new_exe, current],
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
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
        # `part` lives in FFMPEG_DIR so an interrupted download resumes on retry.
        part = os.path.join(FFMPEG_DIR, "ffmpeg-download.zip.part")
        tmp_exe = os.path.join(FFMPEG_DIR, "ffmpeg.exe.new")
        downloaded = False
        try:
            os.makedirs(FFMPEG_DIR, exist_ok=True)
            zip_url, sha256_hex = _ffmpeg_release_info()

            def _progress(done, total):
                if total > 0:
                    pct = min(done / total * 100, 100)
                    self.after(0, self._ffmpeg_status_var.set, f"Downloading FFmpeg… {pct:.0f}%")

            _download_file(zip_url, part, progress_cb=_progress, resume=True)
            downloaded = True

            if sha256_hex:
                self.after(0, self._ffmpeg_status_var.set, "Verifying download…")
                actual = _sha256_file(part)
                if actual.lower() != sha256_hex.lower():
                    raise RuntimeError(
                        f"checksum mismatch — refusing to install "
                        f"(expected {sha256_hex[:12]}…, got {actual[:12]}…)"
                    )
            else:
                self.after(0, self._log_write, "[warn] No checksum published for this FFmpeg build — installing unverified")

            self.after(0, self._ffmpeg_status_var.set, "Extracting…")
            with zipfile.ZipFile(part) as z:
                for name in z.namelist():
                    if name.endswith("/bin/ffmpeg.exe"):
                        with z.open(name) as src, open(tmp_exe, "wb") as dst:
                            shutil.copyfileobj(src, dst)
                        break
                else:
                    raise RuntimeError("ffmpeg.exe not found in archive")

            os.replace(tmp_exe, FFMPEG_EXE)  # atomic — never leave a partial exe
            _silent_unlink(part)

            if not os.path.isfile(FFMPEG_EXE):
                raise RuntimeError("ffmpeg.exe not found after install")

            self.after(0, self._on_ffmpeg_ready)
        except Exception as e:
            _silent_unlink(tmp_exe)
            if downloaded:
                # Bytes we already fetched are bad — don't resume from them.
                _silent_unlink(part)
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

    # ── JavaScript runtime (needed by recent yt-dlp for YouTube) ──────────────

    def _update_js_ui(self):
        name = js_ready_name()
        if name:
            self._js_status_var.set(f"✓  Ready ({name})")
            self._js_status_lbl.config(fg=GREEN)
            self._js_btn.pack_forget()
        else:
            self._js_status_var.set("Not installed — needed for YouTube downloads")
            self._js_status_lbl.config(fg=ORANGE)
            self._js_btn.pack(side="left", padx=(6, 0))

    def _prompt_js_runtime(self):
        """One-time startup prompt: offer to install a JS runtime when missing."""
        if js_runtime_opts():
            self._update_js_ui()
            return
        if sys.platform not in ("win32", "darwin"):
            self._js_status_var.set("Missing — install Node.js 20+, Deno 2+ or qjs on PATH")
            return
        if messagebox.askyesno(
            "JavaScript runtime",
            "YouTube downloads now require a small JavaScript runtime.\n\n"
            "YTD can download and install QuickJS automatically (~2 MB).\n"
            "Install it now?",
        ):
            self._install_js_runtime()

    def _install_js_runtime(self):
        if sys.platform not in ("win32", "darwin"):
            messagebox.showinfo(
                "JavaScript runtime",
                "Install Node.js (v20+) or Deno (v2+) and make sure it is on your "
                "PATH, then restart YTD.",
            )
            return
        self._js_btn.config(state="disabled", text="Installing…")
        self._js_status_var.set("Downloading QuickJS…")
        threading.Thread(target=self._do_install_js_runtime, daemon=True).start()

    def _do_install_js_runtime(self):
        part = os.path.join(FFMPEG_DIR, "qjs-download.part")
        tmp = os.path.join(FFMPEG_DIR, "qjs.new" + (".exe" if sys.platform == "win32" else ""))
        downloaded = False
        try:
            os.makedirs(FFMPEG_DIR, exist_ok=True)
            url, sha256_hex = _quickjs_release_info()

            def _progress(done, total):
                if total > 0:
                    pct = min(done / total * 100, 100)
                    self.after(0, self._js_status_var.set, f"Downloading QuickJS… {pct:.0f}%")

            _download_file(url, part, progress_cb=_progress, resume=True)
            downloaded = True

            if sha256_hex:
                self.after(0, self._js_status_var.set, "Verifying download…")
                actual = _sha256_file(part)
                if actual.lower() != sha256_hex.lower():
                    raise RuntimeError(
                        f"checksum mismatch — refusing to install "
                        f"(expected {sha256_hex[:12]}…, got {actual[:12]}…)"
                    )
            else:
                self.after(0, self._log_write, "[warn] No checksum published for this QuickJS build — installing unverified")

            self.after(0, self._js_status_var.set, "Installing…")
            _extract_executable(part, tmp, "qjs")
            if sys.platform != "win32":
                os.chmod(tmp, 0o755)
            os.replace(tmp, QJS_EXE)  # atomic
            _silent_unlink(part)
            self.after(0, self._on_js_ready)
        except Exception as e:
            _silent_unlink(tmp)
            if downloaded:
                _silent_unlink(part)
            self.after(0, self._on_js_error, str(e))

    def _on_js_ready(self):
        self._log_write("✓ JavaScript runtime installed (QuickJS)")
        self._js_btn.config(state="normal", text="Install")
        self._update_js_ui()

    def _on_js_error(self, msg):
        self._js_status_var.set("Install failed — try again")
        self._js_status_lbl.config(fg=RED)
        self._js_btn.config(state="normal", text="Retry")
        self._log_write(f"✗ JS runtime install error: {msg}")

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
            opts = {
                "quiet": True, "no_warnings": True, "noplaylist": True,
                # Allow yt-dlp to fetch its hash-verified challenge solver script.
                "remote_components": ["ejs:github"],
            }
            jr = js_runtime_opts()
            if jr:
                opts["js_runtimes"] = jr
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
            title = info.get("title", "Unknown")
            duration = format_duration(info.get("duration"))
            uploader = info.get("uploader") or info.get("channel") or ""
            parts = [title]
            if duration:
                parts.append(duration)
            if uploader:
                parts.append(f"by {uploader}")
            self.after(0, self._on_fetch_done, url, "  |  ".join(parts), title)
        except Exception as e:
            self.after(0, self._on_fetch_error, url, str(e))

    def _on_fetch_done(self, url, display, title):
        if url != self._url_var.get().strip():
            self._fetch_btn.config(state="normal")  # stale response — discard
            return
        self._info_var.set(display)
        self._fetched_title = title
        self._fetch_btn.config(state="normal")

    def _on_fetch_error(self, url, err):
        if url != self._url_var.get().strip():
            self._fetch_btn.config(state="normal")  # stale error — discard
            return
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
        if self._is_running:
            return
        if not self._queue:
            messagebox.showinfo("Queue empty", "Add some URLs to the queue first.")
            return

        # Failed/cancelled items from a previous run are retried.
        for item in self._queue:
            if item["status"] in ("error", "cancelled"):
                item["status"] = "pending"
        self._refresh_queue_list()

        if not any(item["status"] == "pending" for item in self._queue):
            messagebox.showinfo(
                "Nothing to download",
                "Every item in the queue has already been downloaded.",
            )
            return

        if "Audio only" in self._fmt_var.get() and not ffmpeg_available():
            if messagebox.askyesno(
                "FFmpeg required",
                "MP3 conversion requires FFmpeg.\n\nInstall it now?",
            ):
                self._install_ffmpeg()
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
            self.after(0, self._update_progress, 0, f"Starting: {item['title']}…")
            success, _ = self._download_one(item["url"])
            item["status"] = "cancelled" if self._cancel_event.is_set() else ("done" if success else "error")
            self.after(0, self._refresh_queue_list)
        self.after(0, self._on_queue_done)

    def _download_one(self, url):
        fmt_key = self._fmt_var.get()
        fmt = FORMAT_OPTIONS[fmt_key]
        audio_only = "Audio only" in fmt_key

        if audio_only and not ffmpeg_available():
            self.after(0, self._log_write, "✗ FFmpeg is required for MP3 conversion — install it from the Settings panel")
            return False, "FFmpeg required for MP3"

        if not ffmpeg_available() and not audio_only:
            fmt = fmt.split("/")[-1]
            self.after(0, self._log_write,
                       "[warn] FFmpeg not found — using pre-merged format (quality may be slightly lower)")

        ydl_opts = {
            "format": fmt,
            "noplaylist": True,
            "outtmpl": os.path.join(self._download_folder, "%(title)s.%(ext)s"),
            "progress_hooks": [self._progress_hook],
            "quiet": True,
            "no_warnings": False,
            "logger": _YTDLogger(self),
            # Allow yt-dlp to fetch its hash-verified challenge solver script.
            "remote_components": ["ejs:github"],
        }

        jr = js_runtime_opts()
        if jr:
            ydl_opts["js_runtimes"] = jr
        elif "youtu.be" in url or "youtube.com" in url:
            self.after(0, self._log_write,
                       "[warn] No JavaScript runtime found — YouTube downloads may fail. "
                       "Install one from the Settings panel.")

        loc = ffmpeg_location()
        if loc:
            ydl_opts["ffmpeg_location"] = loc

        if audio_only:
            ydl_opts["postprocessors"] = [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }]

        # YouTube returns HTTP 403 for some clients/IPs — retry with fallbacks.
        attempts = [
            dict(ydl_opts),
            dict(ydl_opts, extractor_args={"youtube": {"player_client": ["tv", "web_embedded"]}}),
            dict(ydl_opts, source_address="0.0.0.0"),  # force IPv4
        ]
        last_msg = "unknown error"
        for i, opts in enumerate(attempts):
            if self._cancel_event.is_set():
                return False, "cancelled"
            if i:
                self.after(0, self._log_write, f"[warn] Retrying (attempt {i + 1}/{len(attempts)})…")
            try:
                with yt_dlp.YoutubeDL(opts) as ydl:
                    ydl.download([url])
                if self._cancel_event.is_set():
                    return False, "cancelled"
                self.after(0, self._set_status, f"Done! Saved to: {self._download_folder}")
                self.after(0, self._log_write, f"✓ Saved to {self._download_folder}")
                return True, None
            except Exception as exc:
                last_msg = str(exc)
                if "cancelled" in last_msg.lower():
                    return False, last_msg
                # Only retry on bot-block style failures (403 Forbidden).
                if "403" not in last_msg and "forbidden" not in last_msg.lower():
                    break
                if i == len(attempts) - 1:
                    self.after(0, self._log_write,
                               "[warn] YouTube keeps refusing this download (403). "
                               "If you're on a VPN/proxy, try another network — "
                               "this video may also require a YouTube login.")
        self.after(0, self._log_write, f"✗ Error: {last_msg}")
        return False, last_msg

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
            raise yt_dlp.utils.DownloadCancelled("cancelled by user")

        status = d.get("status")
        if status == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            downloaded = d.get("downloaded_bytes", 0)
            pct = (downloaded / total * 100) if total else 0
            speed = d.get("speed") or 0
            eta = d.get("eta")
            speed_str = f"{yt_dlp.utils.format_bytes(speed)}/s" if speed else ""
            eta_str = f"ETA {format_duration(eta)}" if eta else ""
            msg = f"Downloading… {pct:.0f}%  {speed_str}  {eta_str}".rstrip()
            self.after(0, self._update_progress, pct, msg)
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
    """Routes yt-dlp log lines onto the Tk log widget on the main thread."""

    def __init__(self, app):
        self._app = app

    def _emit(self, msg):
        if msg.startswith("[debug]"):
            return
        self._app.after(0, self._app._log_write, msg)

    def debug(self, msg):
        self._emit(msg)

    def info(self, msg):
        self._emit(msg)

    def warning(self, msg):
        self._emit(f"[warn] {msg}")

    def error(self, msg):
        self._emit(f"[error] {msg}")


if __name__ == "__main__":
    app = YTDApp()
    app.mainloop()
