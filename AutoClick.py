'''
AutoClick - Template-based screen auto-clicker with image recognition.

A GUI application that automatically finds and clicks template images on your screen
using OpenCV for image matching. Supports multi-monitor setups, custom search regions,
and configurable click timing.

Requires: pyautogui, mss, pillow, numpy, opencv-python
License: MIT
Repository: https://github.com/maxecution/AutoClick
'''

__version__ = "1.0.0"
__author__ = "maxecution"

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import sys
from pathlib import Path
import threading
import time
import os
from typing import Optional, Dict, Tuple, Callable, Any, Union, TYPE_CHECKING

try:
    import pyautogui
    import mss
    import mss.tools
    import numpy as np
    from PIL import Image, ImageTk, ImageGrab
    DEPS_OK = True
except ImportError as e:
    DEPS_OK = False
    MISSING = str(e)

# Type checking imports for optional dependencies
if TYPE_CHECKING:
    from PIL import Image, ImageTk, ImageGrab
    import numpy as np
    import mss
    import pyautogui


def resource_path(relative_path):
    '''Resolve a resource path, accounting for PyInstaller bundling.'''
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return Path(meipass) / relative_path
    return Path(__file__).parent / relative_path


# ── Palette ────────────────────────────────────────────────────────────────────
BG = "#0e1117"
SURFACE = "#161b27"
SURFACE2 = "#1e2535"
BORDER = "#2a3347"
ACCENT = "#3b82f6"
ACCENT_H = "#60a5fa"
SUCCESS = "#22c55e"
DANGER = "#ef4444"
WARNING = "#f59e0b"
TEXT = "#e2e8f0"
MUTED = "#64748b"
FONT_BODY = ("Consolas", 10)
FONT_SM = ("Consolas", 9)
FONT_LG = ("Consolas", 13, "bold")
FONT_MONO = ("Consolas", 9)

# ── Constants ───────────────────────────────────────────────────────────────────
# Window and UI
WINDOW_WIDTH = 640
WINDOW_HEIGHT = 760
WINDOW_MIN_WIDTH = 560
WINDOW_MIN_HEIGHT = 700
PREVIEW_WIDTH = 120
PREVIEW_HEIGHT = 80

# ScreenSnip overlay
SNIP_DIM_ALPHA = 0.35
SNIP_OVERLAY_DELAY_MS = 150
SNIP_MIN_SELECTION = 4
SNIP_HINT_HEIGHT = 36

# Template matching
CONFIDENCE_MIN = 0.5
CONFIDENCE_MAX = 1.0
CONFIDENCE_DEFAULT = 0.8
TEMPLATE_MIN_SIZE = 10

# Timing
CHECK_SLEEP_INTERVAL = 0.25  # seconds between interval checks
BLINK_INTERVAL = 600  # milliseconds for status dot blink
DEFAULT_CHECK_INTERVAL = 10  # seconds
DEFAULT_PAUSE_AFTER_CLICK = 1  # seconds

# Input validation
OFFSET_DEFAULT = 0
DEFAULT_CLICK_TYPE = "left"


# ══════════════════════════════════════════════════════════════════════════════
#  ScreenSnip - fullscreen rubber-band selection overlay
#  mode="template"  > callback receives a PIL Image (the cropped pixels)
#  mode="region"    > callback receives a dict {left,top,width,height}
# ══════════════════════════════════════════════════════════════════════════════
class ScreenSnip:
    '''
    Freezes the entire desktop into a dim fullscreen overlay and lets the user
    drag a selection rectangle. Works across multiple monitors by spanning the
    combined bounding box of all displays.
    
    Args:
        parent: The parent Tk window to hide during snipping
        mode: Either "template" (returns PIL Image) or "region" (returns dict with bounds)
        callback: Function called with result (PIL Image, dict, or None if cancelled)
    '''

    SEL_FILL = "#3b82f6"
    SEL_OUTLINE = "#60a5fa"
    DIM_ALPHA = SNIP_DIM_ALPHA

    def __init__(self, parent: tk.Tk, mode: str, callback: Callable):
        self.parent = parent
        self.mode = mode
        self.callback = callback

        self._start_x: int = 0
        self._start_y: int = 0
        self._cur_x: int = 0
        self._cur_y: int = 0
        self._rect_id: Optional[int] = None
        self._info_id: Optional[int] = None

        # 1. Grab full-desktop screenshot
        try:
            with mss.mss() as sct:
                mon = sct.monitors[0]          # combined bounding box
                self._offset_x = mon["left"]
                self._offset_y = mon["top"]
                shot = sct.grab(mon)
                self._screenshot = Image.frombytes(
                    "RGB", shot.size, shot.bgra, "raw", "BGRX"
                )
        except Exception as ex:
            messagebox.showerror("Screen capture failed", str(ex))
            callback(None)
            return

        # 2. Dim the screenshot for the overlay background
        w, h = self._screenshot.size
        dim = Image.new("RGB", (w, h), (0, 0, 0))
        self._bg_image = Image.blend(self._screenshot, dim, self.DIM_ALPHA)

        # 3. Hide main window, then open overlay after a short delay
        self.parent.withdraw()
        self.parent.after(SNIP_OVERLAY_DELAY_MS, self._open_overlay)

    # ─────────────────────────────────────────────────────────────────────────
    def _open_overlay(self):
        '''Create and display the fullscreen snipping overlay.'''
        w, h = self._bg_image.size

        self._win = tk.Toplevel(self.parent)
        self._win.overrideredirect(True)
        self._win.attributes("-topmost", True)
        self._win.geometry(f"{w}x{h}+{self._offset_x}+{self._offset_y}")
        self._win.configure(bg="black")

        self._canvas = tk.Canvas(
            self._win, width=w, height=h,
            bg="black", highlightthickness=0, cursor="crosshair"
        )
        self._canvas.pack()

        # Frozen desktop background
        self._tk_bg = ImageTk.PhotoImage(self._bg_image)
        self._canvas.create_image(0, 0, anchor="nw", image=self._tk_bg)

        # Instruction banner
        hint = "Snip template area" if self.mode == "template" else "Select search region"
        self._canvas.create_rectangle(0, 0, w, SNIP_HINT_HEIGHT, fill="#080c14", outline="")
        self._canvas.create_text(
            w // 2, SNIP_HINT_HEIGHT // 2,
            text=f"  {hint}  —  drag to select  ·  Esc to cancel  ",
            fill=TEXT, font=("Consolas", 11)
        )

        self._canvas.bind("<ButtonPress-1>",    self._on_press)
        self._canvas.bind("<B1-Motion>",        self._on_drag)
        self._canvas.bind("<ButtonRelease-1>",  self._on_release)
        self._win.bind("<Escape>",              self._cancel)
        self._win.focus_force()

    # ─────────────────────────────────────────────────────────────────────────
    def _on_press(self, event: tk.Event) -> None:
        '''Handle mouse press—start selection at this point.'''
        self._start_x, self._start_y = event.x, event.y
        self._cur_x,   self._cur_y = event.x, event.y
        for item in (self._rect_id, self._info_id):
            if item:
                self._canvas.delete(item)

    def _on_drag(self, event: tk.Event) -> None:
        '''Handle mouse drag—update selection rectangle dynamically.'''
        self._cur_x, self._cur_y = event.x, event.y
        self._redraw()

    def _redraw(self) -> None:
        '''Redraw the selection rectangle and size indicator.'''
        x0 = min(self._start_x, self._cur_x)
        y0 = min(self._start_y, self._cur_y)
        x1 = max(self._start_x, self._cur_x)
        y1 = max(self._start_y, self._cur_y)

        for item in (self._rect_id, self._info_id):
            if item:
                self._canvas.delete(item)

        # Blue rubber-band rectangle with stipple fill
        self._rect_id = self._canvas.create_rectangle(
            x0, y0, x1, y1,
            outline=self.SEL_OUTLINE, width=2,
            fill=self.SEL_FILL, stipple="gray25"
        )

        # Size badge near the bottom-right corner of selection
        label = f" {x1-x0} × {y1-y0} px "
        bx = min(x1 + 6, self._canvas.winfo_width() - 90)
        by = max(y0 - 6, 40)
        self._info_id = self._canvas.create_text(
            bx, by, text=label, anchor="nw",
            fill="#ffffff", font=("Consolas", 9, "bold")
        )

    def _on_release(self, event):
        '''Handle mouse release—finalize selection or cancel if too small.'''
        self._cur_x, self._cur_y = event.x, event.y
        x0 = min(self._start_x, self._cur_x)
        y0 = min(self._start_y, self._cur_y)
        x1 = max(self._start_x, self._cur_x)
        y1 = max(self._start_y, self._cur_y)

        if (x1 - x0) < SNIP_MIN_SELECTION or (y1 - y0) < SNIP_MIN_SELECTION:
            self._cancel(None)
            return

        self._close()

        if self.mode == "template":
            self.callback(self._screenshot.crop((x0, y0, x1, y1)))
        else:
            self.callback({
                "left":   x0 + self._offset_x,
                "top":    y0 + self._offset_y,
                "width":  x1 - x0,
                "height": y1 - y0,
            })

    def _cancel(self, _event: Optional[tk.Event]) -> None:
        '''Cancel the snipping operation and return None to callback.'''
        self._close()
        self.callback(None)

    def _close(self) -> None:
        '''Close the snipping overlay and restore the main window.'''
        self._win.destroy()
        self.parent.deiconify()


# ══════════════════════════════════════════════════════════════════════════════
#  Misc UI widgets
# ══════════════════════════════════════════════════════════════════════════════
class LogPane(tk.Frame):
    '''A scrollable text widget for displaying timestamped log messages with color-coded levels.'''
    
    def __init__(self, parent: Union[tk.Widget, tk.Tk], **kw):
        super().__init__(parent, bg=BG, **kw)
        self.text = tk.Text(
            self, bg=SURFACE, fg=MUTED, insertbackground=TEXT,
            font=FONT_MONO, relief="flat", bd=0,
            state="disabled", wrap="word",
            selectbackground=ACCENT, selectforeground=TEXT,
            highlightthickness=1, highlightbackground=BORDER,
        )
        sb = tk.Scrollbar(self, orient="vertical", command=self.text.yview, bg=SURFACE2, troughcolor=SURFACE, width=10)
        self.text.configure(yscrollcommand=sb.set)
        self.text.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        self.text.tag_config("ok",   foreground=SUCCESS)
        self.text.tag_config("warn", foreground=WARNING)
        self.text.tag_config("err",  foreground=DANGER)
        self.text.tag_config("info", foreground=ACCENT_H)

    def log(self, msg: str, level: str = "ok") -> None:
        '''
        Add a timestamped log message to the log pane.
        
        Args:
            msg: The message to log
            level: Message level ("ok", "warn", "err", or "info")
        '''
        ts = time.strftime("%H:%M:%S")
        self.text.configure(state="normal")
        self.text.insert("end", f"[{ts}] {msg}\n", level)
        self.text.see("end")
        self.text.configure(state="disabled")


class FlatButton(tk.Label):
    '''A flat-styled button widget with hover effects.'''
    
    def __init__(self, parent: Union[tk.Widget, tk.Tk], text: str, command: Callable, color: str = ACCENT,
                 text_color: str = TEXT, hover_color: Optional[str] = None, **kw):
        '''
        Create a flat button.
        
        Args:
            parent: Parent widget
            text: Button label text
            command: Callback function when clicked
            color: Background color
            text_color: Text color
            hover_color: Background color on hover (defaults to lighter version)
        '''
        self.cmd = command
        self.base_color = color
        self.hover_color = hover_color or ACCENT_H
        self.text_color = text_color
        super().__init__(
            parent, text=text, bg=color, fg=text_color,
            font=FONT_BODY, cursor="hand2",
            padx=14, pady=7, relief="flat", **kw
        )
        self.bind("<ButtonRelease-1>", lambda e: self.cmd())
        self.bind("<Enter>", lambda e: self.configure(bg=self.hover_color))
        self.bind("<Leave>", lambda e: self.configure(bg=self.base_color))

    def set_state(self, enabled: bool) -> None:
        '''Enable or disable the button.'''
        if enabled:
            self.configure(cursor="hand2", bg=self.base_color)
            self.bind("<ButtonRelease-1>", lambda e: self.cmd())
            self.bind("<Enter>", lambda e: self.configure(bg=self.hover_color))
            self.bind("<Leave>", lambda e: self.configure(bg=self.base_color))
        else:
            self.configure(cursor="arrow", bg=BORDER)
            self.unbind("<ButtonRelease-1>")
            self.unbind("<Enter>")
            self.unbind("<Leave>")


class StatusPill(tk.Frame):
    '''A status indicator showing RUNNING/IDLE state with optional blinking dot.'''
    
    def __init__(self, parent: Union[tk.Widget, tk.Tk], **kw):
        super().__init__(parent, bg=BG, **kw)
        self.dot = tk.Label(self, text="●", font=(
            "Consolas", 14), bg=BG, fg=MUTED)
        self.lbl = tk.Label(self, text="IDLE", font=(
            "Consolas", 11, "bold"), bg=BG, fg=MUTED)
        self.dot.pack(side="left", padx=(0, 2))
        self.lbl.pack(side="left", padx=0)
        self._blink_state = False
        self._blink_job: Optional[str] = None

    def set_running(self, running: bool) -> None:
        '''Set the status to RUNNING or IDLE.'''
        if self._blink_job:
            self.after_cancel(self._blink_job)
            self._blink_job = None
        if running:
            self.lbl.configure(text="RUNNING", fg=SUCCESS)
            self._blink()
        else:
            self.dot.configure(fg=MUTED)
            self.lbl.configure(text="IDLE", fg=MUTED)

    def _blink(self) -> None:
        '''Animate the status dot blinking.'''
        self._blink_state = not self._blink_state
        self.dot.configure(fg=SUCCESS if self._blink_state else BG)
        self._blink_job = self.after(BLINK_INTERVAL, self._blink)


# ══════════════════════════════════════════════════════════════════════════════
#  Monitor picker
# ══════════════════════════════════════════════════════════════════════════════
class MonitorPicker(tk.Toplevel):
    '''A dialog for selecting which monitor(s) to search for templates.'''
    
    def __init__(self, parent: Union[tk.Widget, tk.Tk], monitors: list, callback: Callable):
        '''
        Create monitor picker dialog.
        
        Args:
            parent: Parent window
            monitors: List of monitor dicts from mss
            callback: Function called with selected monitor index
        '''
        super().__init__(parent)
        self.title("Pick Monitor")
        self.configure(bg=BG)
        self.resizable(False, False)
        self.grab_set()
        self.callback = callback

        tk.Label(self, text="Select Monitor", font=FONT_LG, bg=BG, fg=TEXT).pack(pady=(18, 4))
        tk.Label(self, text="Tip: use  ⊹ Draw Region  for a custom area.", font=FONT_SM, bg=BG, fg=MUTED).pack(pady=(0, 12))

        self.var = tk.IntVar(value=0)

        row = tk.Frame(self, bg=SURFACE2, padx=12, pady=8)
        row.pack(fill="x", padx=18, pady=3)
        all_w = monitors[0]["width"]
        all_h = monitors[0]["height"]
        tk.Radiobutton(row, text=f"All monitors  ({all_w}×{all_h} combined)", variable=self.var, value=0, bg=SURFACE2, fg=TEXT, selectcolor=SURFACE, activebackground=SURFACE2, font=FONT_BODY).pack(anchor="w")

        for i, m in enumerate(monitors[1:], 1):
            row = tk.Frame(self, bg=SURFACE2, padx=12, pady=8)
            row.pack(fill="x", padx=18, pady=3)
            tk.Radiobutton(
                row,
                text=f"Monitor {i}  —  {m['width']}×{m['height']}  @ ({m['left']}, {m['top']})",
                variable=self.var, value=i,
                bg=SURFACE2, fg=TEXT, selectcolor=SURFACE,
                activebackground=SURFACE2, font=FONT_BODY
            ).pack(anchor="w")

        btns = tk.Frame(self, bg=BG)
        btns.pack(pady=14)
        FlatButton(btns, "  Cancel  ", self.destroy, color=SURFACE2, hover_color=BORDER).pack(side="left", padx=6)
        FlatButton(btns, "  Apply  ", self._apply).pack(side="left", padx=6)

    def _apply(self) -> None:
        '''Apply the selected monitor and close the dialog.'''
        self.callback(self.var.get())
        self.destroy()


# ══════════════════════════════════════════════════════════════════════════════
#  Main application
# ══════════════════════════════════════════════════════════════════════════════
class AutoClickerApp(tk.Tk):
    '''
    Main AutoClick application window.
    
    Manages template selection, search region configuration, and clicking automation
    through a modern dark-themed GUI.
    '''
    
    def __init__(self):
        super().__init__()
        self.title("AutoClick")

        # Try to set icon, but don't fail if it's missing
        try:
            icon_path = resource_path("AutoClick.ico")
            if icon_path.exists():
                self.iconbitmap(str(icon_path))
        except (tk.TclError, FileNotFoundError):
            # Icon not found, continue without it
            pass

        self.configure(bg=BG)
        self.geometry(f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}")
        self.minsize(WINDOW_MIN_WIDTH, WINDOW_MIN_HEIGHT)

        # State
        self.template_image: Optional["Image.Image"] = None
        self.template_np: Optional["np.ndarray"] = None
        self.is_running = False
        self.worker_thread: Optional[threading.Thread] = None
        self.stop_event = threading.Event()

        self.monitor_index: int = 0
        self.custom_region: Optional[Dict[str, int]] = None

        # UI elements (set by _build_ui)
        self.preview_canvas: tk.Canvas
        self.template_label: tk.Label
        self.region_label: tk.Label
        self.conf_var: tk.DoubleVar
        self.conf_label: tk.Label
        self.interval_entry: tk.Entry
        self.offset_x_entry: tk.Entry
        self.offset_y_entry: tk.Entry
        self.post_click_entry: tk.Entry
        self.click_var: tk.StringVar
        self.start_btn: FlatButton
        self.stop_btn: FlatButton
        self.click_count = 0
        self.counter_lbl: tk.Label
        self.status_pill: StatusPill
        self.log: LogPane

        self._build_ui()

        if not DEPS_OK:
            self.after(200, self._show_dep_warning)

    # ── UI Construction ───────────────────────────────────────────────────────
    def _build_ui(self):
        # Header
        header = tk.Frame(self, bg=SURFACE, pady=14)
        header.pack(fill="x")
        tk.Label(header, text="⬡ AutoClick", font=("Consolas", 15, "bold"), bg=SURFACE, fg=TEXT).pack(side="left", padx=20)
        self.status_pill = StatusPill(header)
        self.status_pill.pack(side="right", padx=20)

        # ── Template ─────────────────────────────────────────────────────────
        sec = self._section(self, "Template Image")
        sec.pack(fill="x", padx=16, pady=(14, 0))

        preview_row = tk.Frame(sec, bg=SURFACE)
        preview_row.pack(fill="x", pady=(8, 0))

        self.preview_canvas = tk.Canvas(
            preview_row, width=PREVIEW_WIDTH, height=PREVIEW_HEIGHT,
            bg=SURFACE2, highlightthickness=1, highlightbackground=BORDER
        )
        self.preview_canvas.pack(side="left", padx=(0, 14))
        self._draw_placeholder()

        right = tk.Frame(preview_row, bg=SURFACE)
        right.pack(side="left", fill="both", expand=True)

        self.template_label = tk.Label(
            right, text="No template loaded",
            font=FONT_SM, bg=SURFACE, fg=MUTED, anchor="w", wraplength=340
        )
        self.template_label.pack(anchor="w")

        btn_row = tk.Frame(right, bg=SURFACE)
        btn_row.pack(anchor="w", pady=(10, 0))

        FlatButton(btn_row, "✂  Snip Screen", self._snip_template, color=ACCENT, hover_color=ACCENT_H).pack(side="left", padx=(0, 8))
        FlatButton(btn_row, "Add File…", self._load_from_file, color=SURFACE2, hover_color=BORDER).pack(side="left", padx=(0, 8))
        FlatButton(btn_row, "Paste Clipboard", self._load_from_clipboard, color=SURFACE2, hover_color=BORDER).pack(side="left")

        # Confidence
        conf_row = tk.Frame(sec, bg=SURFACE)
        conf_row.pack(fill="x", pady=(12, 0))
        tk.Label(conf_row, text="Match confidence:", font=FONT_SM, bg=SURFACE, fg=MUTED).pack(side="left")
        self.conf_var = tk.DoubleVar(value=CONFIDENCE_DEFAULT)
        self.conf_label = tk.Label(conf_row, text=f"{CONFIDENCE_DEFAULT:.2f}", font=FONT_SM, bg=SURFACE, fg=ACCENT_H, width=4)
        self.conf_label.pack(side="right")
        ttk.Scale(conf_row, from_=CONFIDENCE_MIN, to=CONFIDENCE_MAX, variable=self.conf_var, orient="horizontal", command=self._on_conf_change).pack(
            side="right", padx=8, fill="x", expand=True)

        # ── Search Region ─────────────────────────────────────────────────────
        sec2 = self._section(self, "Search Region")
        sec2.pack(fill="x", padx=16, pady=(14, 0))

        region_row = tk.Frame(sec2, bg=SURFACE)
        region_row.pack(fill="x", pady=(8, 0))

        self.region_label = tk.Label(
            region_row, text="All monitors",
            font=FONT_SM, bg=SURFACE, fg=TEXT
        )
        self.region_label.pack(side="left")

        btn_reg = tk.Frame(region_row, bg=SURFACE)
        btn_reg.pack(side="right")
        FlatButton(btn_reg, "+ Draw Region", self._snip_region, color=ACCENT, hover_color=ACCENT_H).pack(side="left", padx=(0, 8))
        FlatButton(btn_reg, "Monitor…", self._open_monitor_selector, color=SURFACE2, hover_color=BORDER).pack(side="left", padx=(0, 8))
        FlatButton(btn_reg, "Reset", self._reset_region, color=SURFACE2, hover_color=BORDER).pack(side="left")

        # ── Timing & Click ────────────────────────────────────────────────────
        sec3 = self._section(self, "Timing & Click")
        sec3.pack(fill="x", padx=16, pady=(14, 0))

        grid = tk.Frame(sec3, bg=SURFACE)
        grid.pack(fill="x", pady=(8, 0))

        # Create two columns
        left_col = tk.Frame(grid, bg=SURFACE)
        right_col = tk.Frame(grid, bg=SURFACE)

        left_col.grid(row=0, column=0, sticky="nw", padx=(0, 20))
        right_col.grid(row=0, column=1, sticky="nw")

        # ── Left column ──
        self._labeled_entry(left_col, "Check interval (s):",
                            str(DEFAULT_CHECK_INTERVAL), 0, "interval_entry")
        self._labeled_entry(left_col, "Click offset X (px):",
                            str(OFFSET_DEFAULT),  1, "offset_x_entry")
        self._labeled_entry(left_col, "Click offset Y (px):",
                            str(OFFSET_DEFAULT),  2, "offset_y_entry")

        # ── Right column ──
        self._labeled_entry(
            right_col, "Pause after click (s):", str(DEFAULT_PAUSE_AFTER_CLICK), 0, "post_click_entry")

        # Click type dropdown
        tk.Label(right_col, text="Click type:", font=FONT_SM, bg=SURFACE, fg=MUTED, width=24, anchor="w").grid(row=1, column=0, sticky="w", pady=3)

        self.click_var = tk.StringVar(value=DEFAULT_CLICK_TYPE)

        click_dropdown = ttk.Combobox(
            right_col,
            textvariable=self.click_var,
            values=["left", "right", "double"],
            state="readonly",
            width=10
        )
        click_dropdown.grid(row=1, column=1, sticky="w", padx=(8, 0))

        # ── Control row ───────────────────────────────────────────────────────
        ctrl = tk.Frame(self, bg=BG)
        ctrl.pack(fill="x", padx=16, pady=18)

        self.start_btn = FlatButton(ctrl, "▶  Start", self._start,
                                    color=SUCCESS, hover_color="#16a34a")
        self.start_btn.pack(side="left", padx=(0, 10))
        self.stop_btn = FlatButton(ctrl, "■  Stop", self._stop, color=DANGER, hover_color="#b91c1c")
        self.stop_btn.pack(side="left")
        self.stop_btn.set_state(False)

        self.click_count = 0
        self.counter_lbl = tk.Label(ctrl, text="Clicks: 0", font=FONT_SM,
                                    bg=BG, fg=MUTED)
        self.counter_lbl.pack(side="right")

        # ── Log ───────────────────────────────────────────────────────────────
        log_header = tk.Frame(self, bg=BG)
        log_header.pack(fill="x", padx=16, pady=(0, 4))
        tk.Label(log_header, text="Activity Log", font=("Consolas", 10, "bold"), bg=BG, fg=MUTED).pack(side="left")
        FlatButton(log_header, "Clear", self._clear_log, color=BG, hover_color=SURFACE2, text_color=MUTED).pack(side="right")

        self.log = LogPane(self)
        self.log.pack(fill="both", expand=True, padx=16, pady=(0, 16))

        self.log.log(
            "AutoClick ready.  Use  ✂ Snip Screen  to capture a template.", "info")

    def _section(self, parent: Union[tk.Widget, tk.Tk], title: str) -> tk.Frame:
        '''Create a styled section frame with a title.'''
        frame = tk.Frame(parent, bg=SURFACE, highlightthickness=1, highlightbackground=BORDER, padx=14, pady=10)
        tk.Label(frame, text=title.upper(), font=("Consolas", 8, "bold"), bg=SURFACE, fg=MUTED).pack(anchor="w")
        return frame

    def _labeled_entry(self, parent: Union[tk.Widget, tk.Tk], label: str, default: str, row: int, attr: str) -> None:
        '''Create a labeled entry field and store reference in self.<attr>.'''
        tk.Label(parent, text=label, font=FONT_SM, bg=SURFACE, fg=MUTED, width=24, anchor="w").grid(row=row, column=0, sticky="w", pady=3)
        e = tk.Entry(parent, width=8, bg=SURFACE2, fg=TEXT, insertbackground=TEXT, relief="flat", font=FONT_MONO, highlightthickness=1, highlightbackground=BORDER)
        e.insert(0, default)
        e.grid(row=row, column=1, sticky="w", padx=(8, 0))
        setattr(self, attr, e)

    def _draw_placeholder(self) -> None:
        '''Draw the placeholder image in the preview canvas.'''
        self.preview_canvas.delete("all")
        self.preview_canvas.create_rectangle(
            2, 2, PREVIEW_WIDTH-2, PREVIEW_HEIGHT-2, outline=BORDER, fill=SURFACE2)
        self.preview_canvas.create_text(
            PREVIEW_WIDTH//2, PREVIEW_HEIGHT//2, text="No image", fill=MUTED, font=FONT_SM)

    # ── Template loading ──────────────────────────────────────────────────────
    def _snip_template(self) -> None:
        '''Open the screen snipping tool to capture a template image.'''
        if not DEPS_OK:
            self._show_dep_warning()
            return
        ScreenSnip(self, mode="template", callback=self._on_template_snipped)

    def _on_template_snipped(self, img: Optional["Image.Image"]) -> None:
        '''Handle a snipped template image.'''
        if img is None:
            self.log.log("Template snip cancelled.", "warn")
            return
        self._set_template(img, f"snip ({img.width}×{img.height})")

    def _load_from_file(self) -> None:
        '''Load a template image from disk.'''
        path = filedialog.askopenfilename(
            title="Select template image",
            filetypes=[
                ("Image files", "*.png *.jpg *.jpeg *.bmp *.gif *.tiff"), ("All", "*.*")]
        )
        if path:
            try:
                self._set_template(Image.open(path).convert(
                    "RGB"), os.path.basename(path))
            except Exception as ex:
                messagebox.showerror("Error", f"Could not load image:\n{ex}")

    def _load_from_clipboard(self) -> None:
        '''Load a template image from the system clipboard.'''
        try:
            img = ImageGrab.grabclipboard()
            if img is None:
                messagebox.showinfo(
                    "Clipboard", "No image in clipboard.\nCopy a screenshot snippet first.")
                return
            if not isinstance(img, Image.Image):
                messagebox.showinfo(
                    "Clipboard", "Clipboard content is not an image.")
                return
            self._set_template(img.convert("RGB"), "clipboard")
        except Exception as ex:
            messagebox.showerror("Error", f"Could not read clipboard:\n{ex}")

    def _set_template(self, img: "Image.Image", source: str) -> None:
        '''
        Set the current template image and update the preview.
        
        Args:
            img: PIL Image to use as template
            source: String description of where image came from (for logging)
        '''
        self.template_image = img.convert("RGB")
        self.template_np = np.array(self.template_image)
        thumb = img.copy()
        thumb.thumbnail((PREVIEW_WIDTH-4, PREVIEW_HEIGHT-4))
        self._tk_thumb = ImageTk.PhotoImage(thumb)
        self.preview_canvas.delete("all")
        self.preview_canvas.create_image(PREVIEW_WIDTH//2, PREVIEW_HEIGHT//2, image=self._tk_thumb)
        self.template_label.configure(
            text=f"{source}  ({img.width}×{img.height}px)", fg=TEXT)
        self.log.log(
            f"Template loaded: {source} ({img.width}×{img.height})", "info")

    # ── Region selection ──────────────────────────────────────────────────────
    def _snip_region(self) -> None:
        '''Open the screen snipping tool to define a custom search region.'''
        if not DEPS_OK:
            self._show_dep_warning()
            return
        ScreenSnip(self, mode="region", callback=self._on_region_snipped)

    def _on_region_snipped(self, region: Optional[Dict[str, int]]) -> None:
        '''Handle a snipped region selection.'''
        if region is None:
            self.log.log("Region selection cancelled.", "warn")
            return
        self.monitor_index = "custom"  # type: ignore
        self.custom_region = region
        r = region
        self.region_label.configure(
            text=f"Custom: {r['width']}×{r['height']} @ ({r['left']},{r['top']})")
        self.log.log(
            f"Search region: {r['width']}×{r['height']} @ ({r['left']},{r['top']})", "info")

    def _reset_region(self) -> None:
        '''Reset search region to all monitors.'''
        self.monitor_index = 0
        self.custom_region = None
        self.region_label.configure(text="All monitors")
        self.log.log("Search region reset to all monitors.", "info")

    def _open_monitor_selector(self) -> None:
        '''Open dialog to select a specific monitor.'''
        try:
            with mss.mss() as sct:
                monitors = sct.monitors
        except Exception:
            monitors = [{"left": 0, "top": 0, "width": 1920, "height": 1080}]
        MonitorPicker(self, monitors, self._apply_monitor)

    def _apply_monitor(self, monitor_index: int) -> None:
        '''Apply the selected monitor choice.'''
        self.monitor_index = monitor_index
        self.custom_region = None
        self.region_label.configure(
            text="All monitors" if monitor_index == 0 else f"Monitor {monitor_index}")
        self.log.log(f"Search region: {self.region_label['text']}", "info")

    # ── Confidence slider ─────────────────────────────────────────────────────
    def _on_conf_change(self, val: str) -> None:
        '''Update confidence label when slider changes.'''
        self.conf_label.configure(text=f"{float(val):.2f}")

    # ── Start / Stop ──────────────────────────────────────────────────────────
    def _start(self) -> None:
        '''Start the auto-clicking worker thread.'''
        if not DEPS_OK:
            self._show_dep_warning()
            return
        if self.template_image is None:
            messagebox.showwarning(
                "No Template", "Please load a template image first.")
            return
        
        # Validate interval
        try:
            interval = float(self.interval_entry.get())
            if interval <= 0:
                raise ValueError("must be positive")
        except ValueError:
            messagebox.showerror("Invalid interval", "Interval must be a positive number.")
            return

        # Validate offsets (optional, default to 0)
        try:
            int(self.offset_x_entry.get())
            int(self.offset_y_entry.get())
        except ValueError:
            messagebox.showerror("Invalid offset", "Click offsets must be integers.")
            return

        # Validate post-click pause (optional, default to 0)
        try:
            float(self.post_click_entry.get())
        except ValueError:
            messagebox.showerror("Invalid pause", "Pause value must be a number.")
            return

        self.is_running = True
        self.stop_event.clear()
        self.click_count = 0
        self.counter_lbl.configure(text="Clicks: 0")
        self.status_pill.set_running(True)
        self.start_btn.set_state(False)
        self.stop_btn.set_state(True)
        self.log.log("─" * 40, "info")
        self.log.log(
            f"Started. Interval: {interval}s  Confidence: {self.conf_var.get():.2f}", "info")

        self.worker_thread = threading.Thread(target=self._worker, daemon=True)
        self.worker_thread.start()

    def _stop(self) -> None:
        '''Stop the auto-clicking worker thread.'''
        self.stop_event.set()
        self.is_running = False
        self.status_pill.set_running(False)
        self.start_btn.set_state(True)
        self.stop_btn.set_state(False)
        self.log.log("Stopped by user.", "warn")

    # ── Worker thread ─────────────────────────────────────────────────────────
    def _worker(self) -> None:
        '''
        Main worker thread that continuously scans for templates.
        
        Runs in background thread, checking at regular intervals until stop_event is set.
        Uses thread-safe value access through UI widget methods.
        '''
        import cv2
        while not self.stop_event.is_set():
            # Get interval value in thread-safe manner
            try:
                interval = float(self.interval_entry.get())
                if interval <= 0:
                    interval = DEFAULT_CHECK_INTERVAL
            except (ValueError, tk.TclError):
                interval = DEFAULT_CHECK_INTERVAL
            
            self._do_scan(cv2)
            
            # Sleep in small chunks so we respond quickly to stop event
            elapsed = 0.0
            while elapsed < interval and not self.stop_event.is_set():
                time.sleep(CHECK_SLEEP_INTERVAL)
                elapsed += CHECK_SLEEP_INTERVAL

    def _do_scan(self, cv2: Any) -> None:
        '''
        Perform one template match scan of the screen.
        
        Args:
            cv2: OpenCV module (imported in worker thread)
        '''
        try:
            # Ensure template is loaded
            if self.template_np is None:
                return
            
            screenshot = self._capture_screen()
            if screenshot is None:
                self._log_thread("Screen capture failed.", "err")
                return

            screen_bgr = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
            tmpl_bgr = cv2.cvtColor(self.template_np.copy(), cv2.COLOR_RGB2BGR)

            result = cv2.matchTemplate(
                screen_bgr, tmpl_bgr, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv2.minMaxLoc(result)

            # Get confidence threshold in thread-safe manner
            try:
                confidence_threshold = self.conf_var.get()
            except tk.TclError:
                confidence_threshold = CONFIDENCE_DEFAULT

            if max_val >= confidence_threshold:
                region = self._get_region()
                # Calculate click position at template center
                abs_x = (region["left"] if region else 0) + \
                    max_loc[0] + tmpl_bgr.shape[1] // 2
                abs_y = (region["top"] if region else 0) + \
                    max_loc[1] + tmpl_bgr.shape[0] // 2
                
                # Apply click offsets if provided
                try:
                    abs_x += int(self.offset_x_entry.get())
                    abs_y += int(self.offset_y_entry.get())
                except (ValueError, tk.TclError):
                    pass
                
                self._do_click(abs_x, abs_y, max_val)
            else:
                self._log_thread(
                    f"Template not found (best match: {max_val:.2f})", "warn")

        except Exception as ex:
            self._log_thread(f"Scan error: {ex}", "err")

    def _capture_screen(self) -> Optional["Image.Image"]:
        '''
        Capture screenshot of the search region.
        
        Returns:
            PIL Image of the captured region, or None if capture failed
        '''
        try:
            with mss.mss() as sct:
                region = self._get_region()
                shot = sct.grab(region if region else sct.monitors[0])
                return Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
        except Exception as ex:
            self._log_thread(f"Capture error: {ex}", "err")
            return None

    def _get_region(self) -> Optional[Dict[str, int]]:
        '''
        Get the current search region (custom, specific monitor, or None for all).
        
        Returns:
            Dict with left/top/width/height, or None to search all monitors
        '''
        if self.custom_region:
            return self.custom_region
        if self.monitor_index == 0:
            return None
        try:
            with mss.mss() as sct:
                m = sct.monitors[self.monitor_index]
                return {"left": m["left"], "top": m["top"],
                        "width": m["width"], "height": m["height"]}
        except (IndexError, Exception):
            return None

    def _do_click(self, x: int, y: int, confidence: float) -> None:
        '''
        Perform the configured click action.
        
        Args:
            x: X coordinate to click
            y: Y coordinate to click
            confidence: Match confidence score (for logging)
        '''
        try:
            pyautogui.FAILSAFE = True
            ct = self.click_var.get()
            if ct == "double":
                pyautogui.doubleClick(x, y)
            elif ct == "right":
                pyautogui.rightClick(x, y)
            else:
                pyautogui.click(x, y)

            self.click_count += 1
            self.after(0, lambda: self.counter_lbl.configure(
                text=f"Clicks: {self.click_count}"))
            self._log_thread(
                f"✓ Clicked at ({x}, {y})  confidence={confidence:.2f}", "ok")

            # Pause after click as configured
            try:
                pause_time = float(self.post_click_entry.get())
                if pause_time > 0:
                    time.sleep(pause_time)
            except (ValueError, tk.TclError):
                pass

        except pyautogui.FailSafeException:
            self._log_thread(
                "Fail-safe triggered (mouse in corner). Stopping.", "err")
            self.after(0, self._stop)
        except Exception as ex:
            self._log_thread(f"Click error: {ex}", "err")

    def _log_thread(self, msg: str, level: str = "ok") -> None:
        '''
        Log a message from the worker thread in a thread-safe manner.
        
        Uses self.after() to schedule UI updates on the main thread.
        
        Args:
            msg: Message to log
            level: Log level ("ok", "warn", "err", or "info")
        '''
        self.after(0, lambda: self.log.log(msg, level))

    def _clear_log(self) -> None:
        '''Clear all messages from the activity log.'''
        self.log.text.configure(state="normal")
        self.log.text.delete("1.0", "end")
        self.log.text.configure(state="disabled")

    def _show_dep_warning(self) -> None:
        '''Show error dialog about missing dependencies.'''
        messagebox.showerror(
            "Missing Dependencies",
            f"Required packages are not installed.\n\n"
            f"Error: {MISSING if not DEPS_OK else ''}\n\n"
            f"Please run:\n\n"
            f"  pip install -r requirements.txt\n\n"
            f"Then restart the application."
        )


def main() -> None:
    '''Entry point for the application.'''
    app = AutoClickerApp()
    style = ttk.Style(app)
    style.theme_use("clam")
    style.configure("Horizontal.TScale",
                    background=SURFACE, troughcolor=SURFACE2,
                    slidercolor=ACCENT, sliderlength=16)
    app.mainloop()


# ── Entry point ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    main()
