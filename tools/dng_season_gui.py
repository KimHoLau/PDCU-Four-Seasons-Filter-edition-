#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PDCU MOD - Windows GUI for the Pentax four-season DNG patcher.

Select one or more DNG files, choose the season data source, and write
patched copies with the missing HARUBENI / KATEN / KYUSHU / FUYUNO
records and 3x3 color matrices.
"""
from __future__ import annotations

__copyright__ = "Copyright © 2026 KimHoLau X deepseek harness"

import os
import queue
import sys
import threading
import time
import traceback
from pathlib import Path

import tkinter as tk
import tkinter.font as tkfont
from tkinter import filedialog, ttk

import dng_season_params as core
import season_645d_data
import season_k01_data
import season_k1_data
import season_k1ii_data
import season_k30_data
import season_k50_data
import season_kf_data
import season_mx1_data
import season_q7_data

# Bodies whose 0x021B table is the KF style table times one calibration: the
# KF built-in data is transplanted after calibrating it to the target's own
# base matrix, so no "cross model" opt-in is needed.
CALIBRATED_MODELS = {
    "PENTAX K-3",
    "PENTAX K-3 II",
    "PENTAX K-5 II",
    "PENTAX K-5 II s",
    "PENTAX 645Z",
    "PENTAX KP",
    "PENTAX K-S2",
}

APP_TITLE = "PDCU MOD"
APP_VERSION = "2.5"
APP_INTRO = ("PDCU 宾得相机DNG文件补齐四季色彩矩阵及曲线参数工具"
             "(春红HARUBENI、夏至KATEN、九秋KYUSHU、冬日FUYUNO)")
COPYRIGHT = "版权所有 © 2026 KimHoLau X deepseek harness"
FONT = "Microsoft YaHei UI"
MONO = "Consolas"

# ---- dark theme ----------------------------------------------------------
BG = "#0f0f0f"           # window canvas
HEADER_BG = "#131313"    # hero header
PANEL = "#1f1f1f"        # cards / side panels
ROW_BG = "#242424"       # option rows
FIELD = "#202020"        # inputs
BORDER = "#2d2d2d"
BORDER_SOFT = "#282828"
TEXT = "#ececec"
TEXT_DIM = "#a6a6a6"
TEXT_MUTE = "#8a8a8a"
ACCENT = "#4a9eff"
ACCENT_HOVER = "#6cb2ff"
ACCENT_DOWN = "#2f86e8"
ON_ACCENT = "#07131f"
SELECT_BG = "#17283b"
SELECT_BORDER = "#2c557f"
LOG_BG = "#121212"

SEASONS = (
    ("春红", "HARUBENI", "#e2648c"),
    ("夏至", "KATEN", "#4ea8ff"),
    ("九秋", "KYUSHU", "#e0913c"),
    ("冬日", "FUYUNO", "#a9c4d8"),
)

def resource_path(name: str) -> str:
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, name)


# The season_* modules are imported here on purpose: PyInstaller only bundles
# modules it can see statically, and core.builtin_donor() imports them lazily.
_BUILTIN_MODULES = (season_k1_data, season_k1ii_data, season_kf_data,
                    season_645d_data, season_k30_data, season_k01_data,
                    season_k50_data, season_q7_data, season_mx1_data)


def make_builtin_donor() -> core.DonorData:
    return core.builtin_donor("k1")


def make_builtin_k1ii_donor() -> core.DonorData:
    return core.builtin_donor("k1ii")


def make_builtin_kf_donor() -> core.DonorData:
    return core.builtin_donor("kf")


def make_builtin_645d_donor() -> core.DonorData:
    return core.builtin_donor("645d")


def make_builtin_k30_donor() -> core.DonorData:
    return core.builtin_donor("k30")


def make_builtin_k01_donor() -> core.DonorData:
    return core.builtin_donor("k01")


def make_builtin_k50_donor() -> core.DonorData:
    return core.builtin_donor("k50")


def make_builtin_q7_donor() -> core.DonorData:
    return core.builtin_donor("q7")


def make_builtin_mx1_donor() -> core.DonorData:
    return core.builtin_donor("mx1")


def output_for(target: str, out_dir: str | None) -> str:
    p = Path(target)
    name = p.stem + "_all" + p.suffix
    folder = out_dir if out_dir else str(p.parent)
    return os.path.join(folder, name)


# ---- small drawing helpers ----------------------------------------------
def rounded_points(x1, y1, x2, y2, r):
    return [
        x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r,
        x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2,
        x1, y2, x1, y2 - r, x1, y1 + r, x1, y1,
    ]


class RoundButton(tk.Canvas):
    """Flat rounded button drawn on a canvas (Tk has no native rounding)."""

    def __init__(self, master, text, command=None, *, primary=False,
                 height=32, padx=16, radius=7, font=None, bg=PANEL):
        self._font = tkfont.Font(font=font or (FONT, 9))
        width = self._font.measure(text) + padx * 2
        super().__init__(master, width=width, height=height, bg=bg,
                         highlightthickness=0, bd=0, cursor="hand2")
        self._bw = width
        self._bh = height
        self._radius = radius
        self._text = text
        self._command = command
        self._primary = primary
        self._enabled = True
        self._hover = False
        self._press = False
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<ButtonPress-1>", self._on_press)
        self.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<Configure>", self._on_configure)
        self._paint()

    def _on_configure(self, event):
        self._bw = event.width
        self._bh = event.height
        self._paint()

    def _on_enter(self, _event):
        if self._enabled:
            self._hover = True
            self._paint()

    def _on_leave(self, _event):
        self._hover = False
        self._press = False
        self._paint()

    def _on_press(self, _event):
        if self._enabled:
            self._press = True
            self._paint()

    def _on_release(self, event):
        if not self._enabled:
            return
        was_press = self._press
        self._press = False
        self._paint()
        inside = 0 <= event.x <= self._bw and 0 <= event.y <= self._bh
        if was_press and inside and self._command is not None:
            self._command()

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = bool(enabled)
        self.configure(cursor="hand2" if enabled else "arrow")
        self._paint()

    def _paint(self):
        w, h = max(self._bw, 4), max(self._bh, 4)
        self.delete("all")
        if not self._enabled:
            fill, outline, fg = "#1b1b1b", "#2b2b2b", "#5a5a5a"
        elif self._primary:
            if self._press:
                fill = ACCENT_DOWN
            elif self._hover:
                fill = ACCENT_HOVER
            else:
                fill = ACCENT
            outline, fg = fill, ON_ACCENT
        else:
            if self._press:
                fill = "#191919"
            elif self._hover:
                fill = "#2e2e2e"
            else:
                fill = "#242424"
            outline, fg = ("#4a4a4a" if self._hover else "#3a3a3a"), TEXT
        r = min(self._radius, h / 2, w / 2)
        self.create_polygon(rounded_points(1, 1, w - 1, h - 1, r),
                            smooth=True, splinesteps=24,
                            fill=fill, outline=outline, width=1)
        self.create_text(w / 2, h / 2 + 0.5, text=self._text, fill=fg,
                         font=self._font)


class ProgressBar(tk.Canvas):
    """Thin accent progress line."""

    def __init__(self, master, height=4, bg=BG):
        super().__init__(master, height=height, bg=bg,
                         highlightthickness=0, bd=0)
        self._value = 0.0
        self._max = 1.0
        self.bind("<Configure>", lambda _e: self._draw())

    def set(self, value: float, maximum: float | None = None) -> None:
        if maximum is not None:
            self._max = max(float(maximum), 1.0)
        self._value = float(value)
        self._draw()

    def _draw(self):
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        if w < 2:
            return
        self.create_rectangle(0, 0, w, h, fill="#1a1a1a", outline="")
        frac = 0.0 if self._max <= 0 else max(0.0, min(1.0, self._value / self._max))
        if frac > 0:
            self.create_rectangle(0, 0, max(2, int(w * frac)), h,
                                  fill=ACCENT, outline="")


class DarkEntry(tk.Entry):
    def __init__(self, master, **kw):
        kw.setdefault("bg", FIELD)
        kw.setdefault("fg", TEXT)
        kw.setdefault("disabledbackground", "#191919")
        kw.setdefault("disabledforeground", "#5f5f5f")
        kw.setdefault("insertbackground", TEXT)
        kw.setdefault("font", (FONT, 9))
        kw.setdefault("relief", "flat")
        kw.setdefault("bd", 0)
        kw.setdefault("highlightthickness", 1)
        kw.setdefault("highlightbackground", BORDER)
        kw.setdefault("highlightcolor", ACCENT)
        super().__init__(master, **kw)


class OptionRow(tk.Frame):
    """Radio-style selectable card."""

    def __init__(self, master, title, subtitle="", *, value, variable,
                 command=None):
        super().__init__(master, bg=ROW_BG, highlightthickness=1,
                         highlightbackground=BORDER_SOFT, cursor="hand2",
                         takefocus=1)
        self._value = value
        self._var = variable
        self._command = command
        self._selected = False
        self._bar = tk.Frame(self, width=3, bg=ROW_BG)
        self._bar.pack(side="left", fill="y")
        self._dot = tk.Canvas(self, width=16, height=16, bg=ROW_BG,
                              highlightthickness=0)
        self._dot.pack(side="left", padx=(11, 9))
        col = tk.Frame(self, bg=ROW_BG)
        col.pack(side="left", fill="both", expand=True, pady=5, padx=(0, 10))
        self._title = tk.Label(col, text=title, bg=ROW_BG, fg=TEXT,
                               font=(FONT, 10), anchor="w", justify="left",
                               bd=0, padx=0, pady=0)
        self._title.pack(fill="x")
        self._sub = None
        if subtitle:
            self._sub = tk.Label(col, text=subtitle, bg=ROW_BG,
                                 fg=TEXT_MUTE, font=(FONT, 8),
                                 anchor="w", justify="left", wraplength=298,
                                 bd=0, padx=0, pady=0)
            self._sub.pack(fill="x", pady=(2, 0))
        self._col = col
        self._parts = [self, self._bar, self._dot, col, self._title]
        if self._sub is not None:
            self._parts.append(self._sub)
        for widget in self._parts:
            widget.bind("<Button-1>", self._click)
            widget.configure(cursor="hand2")
        self.bind("<Return>", self._click)
        self.bind("<space>", self._click)
        self._var.trace_add("write", lambda *_a: self._sync())
        self._sync()

    def _click(self, _event=None):
        self._var.set(self._value)
        if self._command is not None:
            self._command()

    def _sync(self):
        selected = self._var.get() == self._value
        if selected == self._selected:
            return
        self._selected = selected
        bg = SELECT_BG if selected else ROW_BG
        for widget in self._parts:
            try:
                widget.configure(bg=bg)
            except tk.TclError:
                pass
        self.configure(highlightbackground=SELECT_BORDER if selected
                       else BORDER_SOFT)
        self._bar.configure(bg=ACCENT if selected else ROW_BG)
        self._title.configure(fg="#f4f8ff" if selected else TEXT)
        if self._sub is not None:
            self._sub.configure(fg="#9db7d4" if selected else TEXT_MUTE)
        self._dot.delete("all")
        ring = ACCENT if selected else "#5c5c5c"
        self._dot.create_oval(3, 3, 13, 13, outline=ring, width=1)
        if selected:
            self._dot.create_oval(5.5, 5.5, 10.5, 10.5,
                                  fill=ACCENT, outline=ACCENT)


class CheckRow(tk.Frame):
    def __init__(self, master, text, variable, *, bg=PANEL, size=8):
        super().__init__(master, bg=bg, cursor="hand2")
        self._var = variable
        self._bg = bg
        self._enabled = True
        self._box = tk.Canvas(self, width=15, height=15, bg=bg,
                              highlightthickness=0, cursor="hand2")
        self._box.pack(side="left")
        self._label = tk.Label(self, text=text, bg=bg, fg=TEXT_DIM,
                               font=(FONT, size), cursor="hand2")
        self._label.pack(side="left", padx=(7, 0))
        for widget in (self, self._box, self._label):
            widget.bind("<Button-1>", self._toggle)
        self._var.trace_add("write", lambda *_a: self._paint())
        self._paint()

    def _toggle(self, _event=None):
        if self._enabled:
            self._var.set(not self._var.get())

    def set_enabled(self, enabled: bool):
        self._enabled = bool(enabled)
        self.configure(cursor="hand2" if enabled else "arrow")
        self._box.configure(cursor="hand2" if enabled else "arrow")
        self._label.configure(cursor="hand2" if enabled else "arrow",
                              fg=TEXT_DIM if enabled else "#4f4f4f")
        self._paint()

    def _paint(self):
        self._box.delete("all")
        checked = bool(self._var.get())
        enabled = self._enabled
        if checked:
            fill = "#17304a" if enabled else "#1b1b1b"
            outline = ACCENT if enabled else "#444444"
        else:
            fill = "#202020" if enabled else "#191919"
            outline = "#5a5a5a" if enabled else "#3a3a3a"
        self._box.create_rectangle(1, 1, 14, 14, fill=fill, outline=outline)
        if checked:
            self._box.create_line(4, 8, 7, 11, 12, 4.5,
                                  fill=ACCENT if enabled else "#555555",
                                  width=2, capstyle="round", joinstyle="round")


class Card(tk.Frame):
    def __init__(self, master, index, title, hint=""):
        super().__init__(master, bg=PANEL, highlightthickness=1,
                         highlightbackground=BORDER)
        head = tk.Frame(self, bg=PANEL)
        head.pack(fill="x", padx=16, pady=(9, 9))
        if index:
            tk.Label(head, text=index, bg="#16283c", fg=ACCENT,
                     font=(MONO, 8, "bold"), padx=5, pady=1).pack(side="left")
        tk.Label(head, text=title, bg=PANEL, fg="#dedede",
                 font=(FONT, 10, "bold")).pack(side="left", padx=(10, 0))
        self.hint_label = tk.Label(head, text=hint, bg=PANEL, fg=TEXT_MUTE,
                                   font=(FONT, 8))
        self.hint_label.pack(side="right")
        tk.Frame(self, bg=BORDER_SOFT, height=1).pack(fill="x")
        self.body = tk.Frame(self, bg=PANEL)
        self.body.pack(fill="both", expand=True, padx=16, pady=11)

    def set_hint(self, text: str) -> None:
        self.hint_label.configure(text=text)


class MessageDialog(tk.Toplevel):
    """Small dark modal used instead of the light native message boxes."""

    def __init__(self, parent, title, message, kind="info", *,
                 confirm=False, ok="确定", cancel="取消"):
        super().__init__(parent, bg=BG)
        self.withdraw()
        self.overrideredirect(True)
        self.configure(highlightthickness=1, highlightbackground="#3a3a3a")
        self.result = False
        accent = {"info": ACCENT, "warning": "#e0a13c",
                  "error": "#e05a5a", "question": ACCENT}.get(kind, ACCENT)
        head = tk.Frame(self, bg=PANEL)
        head.pack(fill="x")
        tk.Frame(head, bg=accent, width=3).pack(side="left", fill="y")
        title_label = tk.Label(head, text=title, bg=PANEL, fg=TEXT,
                               font=(FONT, 10, "bold"))
        title_label.pack(side="left", padx=14, pady=10)

        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True, padx=18, pady=15)
        tk.Label(body, text=message, bg=BG, fg=TEXT_DIM, font=(FONT, 9),
                 justify="left", wraplength=430).pack(anchor="w")

        buttons = tk.Frame(self, bg=BG)
        buttons.pack(fill="x", padx=18, pady=(0, 15))
        RoundButton(buttons, ok, self._ok, primary=True, height=32, bg=BG
                    ).pack(side="right")
        if confirm:
            RoundButton(buttons, cancel, self._cancel, height=32, bg=BG
                        ).pack(side="right", padx=(0, 8))

        for widget in (head, title_label):
            widget.bind("<ButtonPress-1>", self._drag_start)
            widget.bind("<B1-Motion>", self._drag_move)
        self.bind("<Escape>", lambda _e: self._cancel())
        self.bind("<Return>", lambda _e: self._ok())

        self.transient(parent)
        self.update_idletasks()
        w = max(380, self.winfo_reqwidth())
        h = self.winfo_reqheight()
        px, py = parent.winfo_rootx(), parent.winfo_rooty()
        pw, ph = parent.winfo_width(), parent.winfo_height()
        x = px + max(0, (pw - w) // 2)
        y = py + max(0, (ph - h) // 3)
        self.geometry("%dx%d+%d+%d" % (w, h, x, y))
        self.deiconify()
        self.lift()
        self.focus_force()
        self.grab_set()

    def _drag_start(self, event):
        self._drag = (event.x_root - self.winfo_x(),
                      event.y_root - self.winfo_y())

    def _drag_move(self, event):
        dx, dy = self._drag
        self.geometry("+%d+%d" % (event.x_root - dx, event.y_root - dy))

    def _ok(self):
        self.result = True
        self._close()

    def _cancel(self):
        self.result = False
        self._close()

    def _close(self):
        try:
            self.grab_release()
        except tk.TclError:
            pass
        self.destroy()


def show_alert(parent, title, message, kind="info") -> None:
    dlg = MessageDialog(parent, title, message, kind)
    parent.wait_window(dlg)


def show_confirm(parent, title, message, ok="确定", cancel="取消") -> bool:
    dlg = MessageDialog(parent, title, message, "question",
                        confirm=True, ok=ok, cancel=cancel)
    parent.wait_window(dlg)
    return bool(dlg.result)


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("%s v%s" % (APP_TITLE, APP_VERSION))
        self.geometry("1200x900")
        self.minsize(1120, 870)
        self.configure(bg=BG)

        self.targets: list[str] = []
        self.queue: "queue.Queue[tuple]" = queue.Queue()
        self.worker: threading.Thread | None = None
        self.last_out_dir: str | None = None
        self._model_cache: dict[str, str] = {}
        self._logo = None
        self.custom_donor: str = ""
        self._last_builtin: str = "builtin"

        self._build_style()
        self._build_ui()
        self._center_window()
        self.after(100, self._poll)
        self.after(60, self._apply_dark_titlebar)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ---------- theme ----------
    def _build_style(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure(
            "Dark.Vertical.TScrollbar", gripcount=0, background="#3c3c3c",
            darkcolor=PANEL, lightcolor=PANEL, troughcolor="#141414",
            bordercolor="#141414", arrowcolor="#8a8a8a", arrowsize=10,
            relief="flat", width=11)
        style.map("Dark.Vertical.TScrollbar",
                  background=[("active", "#4f4f4f"), ("pressed", ACCENT_DOWN)],
                  arrowcolor=[("active", TEXT)])

    def _apply_dark_titlebar(self) -> None:
        if sys.platform != "win32":
            return
        try:
            import ctypes
            hwnd = ctypes.windll.user32.GetParent(self.winfo_id())
            value = ctypes.c_int(1)
            for attr in (20, 19):
                if ctypes.windll.dwmapi.DwmSetWindowAttribute(
                        hwnd, attr, ctypes.byref(value),
                        ctypes.sizeof(value)) == 0:
                    break
        except Exception:
            pass

    def _center_window(self) -> None:
        self.update_idletasks()
        width, height = 1200, 900
        x = max(0, (self.winfo_screenwidth() - width) // 2)
        y = max(0, (self.winfo_screenheight() - height - 80) // 2)
        self.geometry("%dx%d+%d+%d" % (width, height, x, y))

    # ---------- layout ----------
    def _build_ui(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self._build_header()

        main = tk.Frame(self, bg=BG)
        main.grid(row=1, column=0, sticky="nsew", padx=16, pady=(14, 10))
        main.columnconfigure(0, weight=1)
        main.columnconfigure(1, weight=0, minsize=376)
        main.rowconfigure(0, weight=1)

        left = tk.Frame(main, bg=BG)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        left.columnconfigure(0, weight=1)
        left.rowconfigure(0, weight=1)

        right = tk.Frame(main, bg=BG)
        right.grid(row=0, column=1, sticky="nsew")
        right.columnconfigure(0, weight=1)

        self._build_files_card(left)
        self._build_output_card(left)
        self._build_actions(left)
        self._build_source_card(right)
        self._build_season_card(right)

        self._build_log()

        self._refresh_file_state()
        self._donor_mode_changed()
        self._out_mode_changed()

        # Allow "drag a DNG onto the exe" / passing files on the command line.
        for arg in sys.argv[1:]:
            if arg.lower().endswith(".dng") and os.path.isfile(arg):
                self._append_target(os.path.abspath(arg))
        self._refresh_file_state()
        if self.targets:
            self.status_var.set("已选择 %d 个文件" % len(self.targets))
        self._autoselect_donor()

        ico = resource_path("season.ico")
        if os.path.exists(ico):
            try:
                self.iconbitmap(ico)
            except tk.TclError:
                pass

    def _build_header(self) -> None:
        header = tk.Frame(self, bg=HEADER_BG)
        header.grid(row=0, column=0, sticky="ew")
        self._topline = tk.Canvas(header, height=3, bg=HEADER_BG,
                                  highlightthickness=0, bd=0)
        self._topline.pack(fill="x")
        self._topline.bind("<Configure>", self._paint_topline)

        hero = tk.Frame(header, bg=HEADER_BG)
        hero.pack(fill="x", padx=22, pady=(14, 16))

        logo_path = resource_path(os.path.join("assets", "pdcu_mod_logo_96.png"))
        try:
            self._logo = tk.PhotoImage(file=logo_path)
            tk.Label(hero, image=self._logo, bg=HEADER_BG, bd=0
                     ).pack(side="left", padx=(0, 18))
        except tk.TclError:
            self._logo = None

        copy = tk.Frame(hero, bg=HEADER_BG)
        copy.pack(side="left", fill="x", expand=True)
        tk.Label(copy, text=APP_TITLE, bg=HEADER_BG, fg="#f4f6f8",
                 font=(FONT, 24, "bold")).pack(anchor="w")
        tk.Label(copy, text=APP_INTRO, bg=HEADER_BG, fg="#9aa5b1",
                 font=(FONT, 9), justify="left", wraplength=820
                 ).pack(anchor="w", pady=(4, 0))
        tk.Label(copy, text=COPYRIGHT, bg=HEADER_BG, fg="#5d6670",
                 font=(FONT, 8)).pack(anchor="w", pady=(6, 0))

        chips = tk.Frame(hero, bg=HEADER_BG)
        chips.pack(side="right", anchor="n")
        tk.Label(chips, text="v%s" % APP_VERSION, bg="#1a2431",
                 fg="#8ab4f8", font=(MONO, 8, "bold"), padx=8, pady=2
                 ).pack(anchor="e")
        tk.Label(chips, text="PENTAX · DNG", bg="#1c1c1c", fg="#8a8a8a",
                 font=(MONO, 8), padx=8, pady=2).pack(anchor="e", pady=(6, 0))

    def _paint_topline(self, _event=None) -> None:
        canvas = self._topline
        width = canvas.winfo_width()
        if width <= 1:
            return
        canvas.delete("all")
        for x in range(width):
            t = x / max(width - 1, 1)
            r = int(74 + (176 - 74) * t)
            g = int(158 + (107 - 158) * t)
            b = 255
            canvas.create_line(x, 0, x, 3,
                               fill="#%02x%02x%02x" % (r, g, b))

    def _build_files_card(self, parent) -> None:
        card = Card(parent, "01", "选择 DNG 文件", "0 个文件")
        card.grid(row=0, column=0, sticky="nsew")
        self.files_card = card
        card.body.rowconfigure(0, weight=1)
        card.body.columnconfigure(0, weight=1)
        card.body.configure(height=150)

        wrap = tk.Frame(card.body, bg=PANEL)
        wrap.grid(row=0, column=0, sticky="nsew")
        wrap.rowconfigure(0, weight=1)
        wrap.columnconfigure(0, weight=1)

        self.listbox = tk.Listbox(
            wrap, selectmode=tk.EXTENDED, height=5,
            font=(FONT, 9), activestyle="none", exportselection=False,
            bg=FIELD, fg="#d6d6d6", selectbackground="#1d3f66",
            selectforeground="#ffffff", bd=0, relief="flat",
            highlightthickness=1, highlightbackground=BORDER,
            highlightcolor="#3a3a3a", selectborderwidth=0,
        )
        self.listbox.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(wrap, orient="vertical",
                               style="Dark.Vertical.TScrollbar",
                               command=self.listbox.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.listbox.configure(yscrollcommand=scroll.set)

        self.empty_hint = tk.Label(wrap, text="＋  点击添加 DNG 文件",
                                   bg=FIELD, fg=TEXT_MUTE, font=(FONT, 9),
                                   cursor="hand2")
        self.empty_hint.bind("<Button-1>", lambda _e: self._add_files())
        self.empty_hint.place(relx=0.5, rely=0.5, anchor="center")
        self.empty_hint.lift()

        buttons = tk.Frame(card.body, bg=PANEL)
        buttons.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        self.add_btn = RoundButton(buttons, "添加文件", self._add_files,
                                   primary=True, height=30, bg=PANEL)
        self.add_btn.pack(side="left")
        self.remove_btn = RoundButton(buttons, "移除选中", self._remove_selected,
                                      height=30, bg=PANEL)
        self.remove_btn.pack(side="left", padx=(8, 0))
        self.clear_btn = RoundButton(buttons, "清空", self._clear_files,
                                     height=30, bg=PANEL)
        self.clear_btn.pack(side="left", padx=(8, 0))
        tk.Label(buttons, text="支持一次添加多个 DNG", bg=PANEL,
                 fg=TEXT_MUTE, font=(FONT, 8)).pack(side="right")

    def _build_output_card(self, parent) -> None:
        card = Card(parent, "02", "输出位置")
        card.grid(row=1, column=0, sticky="ew", pady=(12, 0))
        self.out_mode = tk.StringVar(value="same")

        OptionRow(card.body, "与源文件同目录（文件名加 _all）",
                  value="same", variable=self.out_mode,
                  command=self._out_mode_changed).pack(fill="x")
        OptionRow(card.body, "指定输出目录", value="dir",
                  variable=self.out_mode,
                  command=self._out_mode_changed).pack(fill="x", pady=(6, 0))

        row = tk.Frame(card.body, bg=PANEL)
        row.pack(fill="x", padx=(37, 0), pady=(6, 0))
        row.columnconfigure(0, weight=1)
        self.out_entry = DarkEntry(row)
        self.out_entry.grid(row=0, column=0, sticky="ew", ipady=5)
        self.out_browse = RoundButton(row, "浏览…", self._browse_out,
                                      height=30, bg=PANEL)
        self.out_browse.grid(row=0, column=1, padx=(8, 0))

        self.overwrite = tk.BooleanVar(value=False)
        CheckRow(card.body, "覆盖已存在的输出文件", self.overwrite,
                 bg=PANEL, size=9).pack(anchor="w", pady=(10, 0))

    def _build_actions(self, parent) -> None:
        action = tk.Frame(parent, bg=BG)
        action.grid(row=2, column=0, sticky="ew", pady=(12, 0))
        action.columnconfigure(3, weight=1)

        self.start_btn = RoundButton(action, "开始转换", self._start,
                                     primary=True, height=40, padx=30,
                                     font=(FONT, 10, "bold"), bg=BG)
        self.start_btn.grid(row=0, column=0, sticky="w")
        self.open_btn = RoundButton(action, "打开输出目录",
                                    self._open_out_dir, height=40, bg=BG)
        self.open_btn.grid(row=0, column=1, sticky="w", padx=(10, 0))
        self.open_btn.set_enabled(False)

        self.status_var = tk.StringVar(value="就绪")
        tk.Label(action, textvariable=self.status_var, bg=BG, fg=TEXT_DIM,
                 font=(FONT, 9)).grid(row=0, column=3, sticky="e")

        self.progress = ProgressBar(action, height=4, bg=BG)
        self.progress.grid(row=1, column=0, columnspan=4, sticky="ew",
                           pady=(10, 0))

    def _build_source_card(self, parent) -> None:
        card = Card(parent, "03", "季节参数来源", "自动识别机型")
        card.grid(row=0, column=0, sticky="ew")
        self.source_card = card

        self.donor_mode = tk.StringVar(value="builtin")
        rows = (
            ("builtin", "内置 K-1 / K-1 Mark II", "原生四季数据"),
            ("builtin_kf", "内置 KF / K-70",
             "K-3 / K-3 II / K-5 II / K-5 II s / 645Z / KP / K-S2 自动适配"),
            ("builtin_645d", "内置 645D", "PENTAX 645D 专用"),
            ("builtin_k30", "内置 K-30 系列",
             "K-30 / K-01 / K-50 / Q7 / MX-1"),
        )
        for index, (value, title, subtitle) in enumerate(rows):
            OptionRow(card.body, title, subtitle, value=value,
                      variable=self.donor_mode,
                      command=self._donor_mode_changed
                      ).pack(fill="x", pady=(0 if index == 0 else 4, 0))

        tk.Frame(card.body, bg=BORDER_SOFT, height=1).pack(fill="x",
                                                           pady=(8, 6))
        tk.Label(card.body, text="高级", bg=PANEL, fg=TEXT_MUTE,
                 font=(FONT, 8, "bold")).pack(anchor="w")

        adv = tk.Frame(card.body, bg=PANEL)
        adv.pack(fill="x", pady=(4, 0))
        self.donor_btn = RoundButton(adv, "选择 DNG 文件…",
                                     self._browse_donor, height=30, bg=PANEL)
        self.donor_btn.pack(side="left")
        self.donor_name = tk.Label(adv, text="未选择", bg=PANEL,
                                   fg=TEXT_MUTE, font=(FONT, 8), anchor="w")
        self.donor_name.pack(side="left", fill="x", expand=True, padx=(10, 4))
        self.donor_clear = tk.Label(adv, text="清除", bg=PANEL, fg=ACCENT,
                                    font=(FONT, 8), cursor="hand2")
        self.donor_clear.bind("<Button-1>", lambda _e: self._clear_donor())

        self.allow_cross_model = tk.BooleanVar(value=False)
        self.cross_check = CheckRow(card.body,
                                    "允许使用其他机型的 DNG",
                                    self.allow_cross_model, bg=PANEL, size=8)
        self.cross_check.pack(anchor="w", pady=(4, 0))
        self.cross_check.set_enabled(True)

    def _build_season_card(self, parent) -> None:
        card = Card(parent, "", "四季色彩", "补齐后 PDCU 内可选")
        card.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        grid = tk.Frame(card.body, bg=PANEL)
        grid.pack(fill="x")
        for index, (cn, en, color) in enumerate(SEASONS):
            grid.columnconfigure(index, weight=1, uniform="season")
            cell = tk.Frame(grid, bg=PANEL)
            cell.grid(row=0, column=index, sticky="w")
            line = tk.Frame(cell, bg=PANEL)
            line.pack(anchor="w")
            dot = tk.Canvas(line, width=8, height=8, bg=PANEL,
                            highlightthickness=0)
            dot.create_oval(0, 0, 7, 7, fill=color, outline="")
            dot.pack(side="left", pady=(2, 0))
            tk.Label(line, text=cn, bg=PANEL, fg="#d8d8d8",
                     font=(FONT, 9)).pack(side="left", padx=(5, 0))
            tk.Label(cell, text=en, bg=PANEL, fg=TEXT_MUTE,
                     font=(MONO, 7)).pack(anchor="w", pady=(1, 0))

    def _build_log(self) -> None:
        card = Card(self, "", "日志", "运行时输出")
        card.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 14))
        card.body.rowconfigure(0, weight=1)
        card.body.columnconfigure(0, weight=1)

        self.log = tk.Text(card.body, height=8, wrap="word",
                           font=(MONO, 9), state="disabled",
                           bg=LOG_BG, fg="#b9c3cd", insertbackground=TEXT,
                           relief="flat", bd=0, padx=10, pady=8,
                           highlightthickness=0)
        self.log.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(card.body, orient="vertical",
                               style="Dark.Vertical.TScrollbar",
                               command=self.log.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.log.configure(yscrollcommand=scroll.set)
        self.log.tag_configure("ts", foreground="#5f7183")

    # ---------- file list ----------
    def _append_target(self, path: str) -> None:
        path = os.path.abspath(path)
        if path in self.targets:
            return
        self.targets.append(path)
        self.listbox.insert("end", path)

    def _add_files(self) -> None:
        paths = filedialog.askopenfilenames(
            parent=self, title="选择 DNG 文件",
            filetypes=[("DNG 文件", "*.DNG *.dng"), ("所有文件", "*.*")])
        for path in paths:
            self._append_target(path)
        self._refresh_file_state()
        self.status_var.set("已选择 %d 个文件" % len(self.targets))
        self._autoselect_donor()

    def _remove_selected(self) -> None:
        for index in reversed(self.listbox.curselection()):
            self.listbox.delete(index)
            del self.targets[index]
        self._refresh_file_state()
        self.status_var.set("已选择 %d 个文件" % len(self.targets))
        self._autoselect_donor()

    def _clear_files(self) -> None:
        self.listbox.delete(0, "end")
        self.targets.clear()
        self._refresh_file_state()
        self.status_var.set("就绪")

    def _refresh_file_state(self) -> None:
        count = len(self.targets)
        self.files_card.set_hint("%d 个文件" % count if count else "0 个文件")
        self.remove_btn.set_enabled(count > 0)
        self.clear_btn.set_enabled(count > 0)
        if count:
            self.empty_hint.place_forget()
        else:
            self.empty_hint.place(relx=0.5, rely=0.5, anchor="center")
            self.empty_hint.lift()

    def _model_of(self, path: str) -> str:
        if path not in self._model_cache:
            try:
                self._model_cache[path] = (core.Dng(path).model or "").strip()
            except Exception:
                self._model_cache[path] = ""
        return self._model_cache[path]

    def _autoselect_donor(self) -> None:
        """Pick the built-in donor that matches the selected target models."""
        if not self.targets:
            return
        models = {self._model_of(p) for p in self.targets}
        if "" in models:
            return
        current = self.donor_mode.get()
        builtin_modes = ("builtin", "builtin_kf", "builtin_k30", "builtin_645d")
        if current not in builtin_modes:
            return

        def choose(mode: str, message: str) -> None:
            self.donor_mode.set(mode)
            self._donor_mode_changed()
            self.status_var.set(message)

        if models <= {"PENTAX KF", "PENTAX K-70"}:
            choose("builtin_kf", "检测到 KF / K-70，已选择「内置 KF / K-70」")
        elif models <= {"PENTAX K-30", "PENTAX K-01", "PENTAX K-50",
                        "PENTAX Q7", "PENTAX MX-1"}:
            choose("builtin_k30", "检测到 K-30 系列，已选择「内置 K-30 系列」")
        elif models <= {"PENTAX K-1", "PENTAX K-1 Mark II"}:
            choose("builtin", "检测到 K-1 / K-1 Mark II，已选择「内置 K-1」")
        elif models == {"PENTAX 645D"}:
            choose("builtin_645d", "检测到 645D，已选择「内置 645D」")
        elif models <= CALIBRATED_MODELS:
            choose("builtin_kf", "检测到 K-3 / K-5 / 645Z 等机型，"
                                 "已选择「内置 KF / K-70」")
        elif len(models) > 1:
            self.status_var.set("检测到多种机型，请分批处理或使用 DNG 来源")
        else:
            model = next(iter(models))
            self.status_var.set("检测到 %s，请选择来源或使用 DNG 文件" % model)

    # ---------- options ----------
    def _donor_mode_changed(self) -> None:
        mode = self.donor_mode.get()
        if mode == "file":
            name = os.path.basename(self.custom_donor) if self.custom_donor else ""
            self.donor_name.configure(text=self._shorten(name) if name else "未选择",
                                      fg=ACCENT if name else TEXT_MUTE)
            self.cross_check.set_enabled(True)
            if name:
                self.donor_clear.pack(side="left")
        else:
            self._last_builtin = mode
            self.custom_donor = ""
            self.donor_name.configure(text="未选择", fg=TEXT_MUTE)
            self.donor_clear.pack_forget()

    @staticmethod
    def _shorten(text: str, limit: int = 30) -> str:
        if len(text) <= limit:
            return text
        return text[:limit - 1] + "…"

    def _browse_donor(self) -> None:
        path = filedialog.askopenfilename(
            parent=self, title="选择同机型 donor DNG",
            filetypes=[("DNG 文件", "*.DNG *.dng"), ("所有文件", "*.*")])
        if path:
            self.custom_donor = os.path.abspath(path)
            self.donor_mode.set("file")
            self._donor_mode_changed()
            self.status_var.set("已选择 DNG 来源：%s"
                                % os.path.basename(self.custom_donor))

    def _clear_donor(self) -> None:
        self.custom_donor = ""
        self.donor_mode.set(self._last_builtin)
        self._donor_mode_changed()

    def _out_mode_changed(self) -> None:
        enabled = self.out_mode.get() == "dir"
        self.out_entry.configure(state="normal" if enabled else "disabled")
        self.out_browse.set_enabled(enabled)

    def _browse_out(self) -> None:
        path = filedialog.askdirectory(parent=self, title="选择输出目录")
        if path:
            self.out_entry.configure(state="normal")
            self.out_entry.delete(0, "end")
            self.out_entry.insert(0, os.path.abspath(path))
            self.out_mode.set("dir")
            self._out_mode_changed()

    # ---------- start ----------
    def _start(self) -> None:
        if self.worker is not None and self.worker.is_alive():
            return
        if not self.targets:
            show_alert(self, "提示", "请先添加至少一个 DNG 文件。", "warning")
            return

        donor_mode = self.donor_mode.get()
        donor_path = self.custom_donor
        if donor_mode == "file":
            if not donor_path or not os.path.isfile(donor_path):
                show_alert(self, "提示", "请选择一个有效的 DNG 文件。", "warning")
                return

        out_mode = self.out_mode.get()
        out_dir = self.out_entry.get().strip() if out_mode == "dir" else None
        if out_mode == "dir":
            if not out_dir:
                show_alert(self, "提示", "请选择输出目录。", "warning")
                return
            if not os.path.isdir(out_dir):
                if not show_confirm(self, "创建目录",
                                    "输出目录不存在，是否创建？\n%s" % out_dir):
                    return
                os.makedirs(out_dir, exist_ok=True)

        overwrite = bool(self.overwrite.get())
        if not overwrite:
            existing = [output_for(t, out_dir) for t in self.targets
                        if os.path.exists(output_for(t, out_dir))]
            if existing:
                show_alert(
                    self, "输出已存在",
                    "以下输出文件已存在，请勾选「覆盖已存在的输出文件」"
                    "或更换输出目录：\n\n"
                    + "\n".join(existing[:8])
                    + ("\n..." if len(existing) > 8 else ""),
                    "error")
                return

        allow_cross = bool(self.allow_cross_model.get())

        self.start_btn.set_enabled(False)
        self.open_btn.set_enabled(False)
        self.progress.set(0, len(self.targets))
        self.status_var.set("正在转换…")
        self._append_log("=" * 66)
        self._append_log("开始转换 %d 个文件" % len(self.targets))
        if allow_cross:
            self._append_log("注意：已允许使用其他机型的 DNG；"
                             "仅建议在已知结果可接受时使用。")

        args = (list(self.targets), donor_mode, donor_path, out_dir,
                overwrite, allow_cross)
        self.worker = threading.Thread(target=self._worker, args=args,
                                       daemon=True)
        self.worker.start()

    def _worker(self, targets, donor_mode, donor_path, out_dir, overwrite,
                allow_cross) -> None:
        donors = {}
        try:
            if donor_mode == "builtin":
                donors["default"] = make_builtin_donor()
                donors["k1ii"] = make_builtin_k1ii_donor()
                self.queue.put(("log", "季节来源：内置 K-1 / K-1 Mark II 四季参数"))
            elif donor_mode == "builtin_kf":
                donors["default"] = make_builtin_kf_donor()
                self.queue.put(("log", "季节来源：内置 KF / K-70 四季参数"))
            elif donor_mode == "builtin_645d":
                donors["default"] = make_builtin_645d_donor()
                self.queue.put(("log", "季节来源：内置 645D 四季参数"))
            elif donor_mode == "builtin_k30":
                donors["k30"] = make_builtin_k30_donor()
                donors["k01"] = make_builtin_k01_donor()
                donors["k50"] = make_builtin_k50_donor()
                donors["q7"] = make_builtin_q7_donor()
                donors["mx1"] = make_builtin_mx1_donor()
                self.queue.put(("log", "季节来源：内置 K-30 系列四季参数"))
            else:
                donors["default"] = core.Dng(donor_path)
                self.queue.put(("log", "季节来源：%s" % donor_path))
        except Exception:
            self.queue.put(("log", "读取 donor 失败：\n" + traceback.format_exc()))
            self.queue.put(("done", 0, len(targets), None))
            return

        ok = 0
        fail = 0
        last_dir = None
        for i, target in enumerate(targets, 1):
            out = output_for(target, out_dir)
            self.queue.put(("log", "[%d/%d] %s" % (i, len(targets), target)))
            try:
                model = self._model_of(target)
                if donor_mode == "builtin":
                    donor = (donors["k1ii"] if model == "PENTAX K-1 Mark II"
                             else donors["default"])
                elif donor_mode == "builtin_k30":
                    donor = donors.get({
                        "PENTAX K-01": "k01",
                        "PENTAX K-50": "k50",
                        "PENTAX Q7": "q7",
                        "PENTAX MX-1": "mx1",
                    }.get(model, "k30"), donors["k30"])
                else:
                    donor = donors["default"]
                if donor_mode == "builtin" and model == "PENTAX K-1 Mark II":
                    self.queue.put((
                        "log",
                        "  K-1 Mark II：使用 K-1 原生四季表（Y=I，"
                        "28 条记录 / 21 个基础矩阵与 K-1 逐字节相同）"))
                res = core.convert_file(
                    target, out, donor, overwrite=overwrite,
                    allow_cross_model=allow_cross)
                if res.get("changed"):
                    self.queue.put((
                        "log",
                        "  完成 -> %s  (records=%d, matrices=%d)"
                        % (out, res.get("n_records", 0),
                           res.get("new_block_count", 0))))
                    applied = res.get("calibration_applied")
                    if applied:
                        self.queue.put((
                            "log", "  按目标机身校准：%s"
                            % core.describe_calibration(res.get("calibration"))))
                    cm2_text = core.describe_cm2(res.get("calibration"))
                    if cm2_text:
                        self.queue.put(("log", "  %s" % cm2_text))
                    if not applied and res.get("compatible_cross_model"):
                        self.queue.put((
                            "log",
                            "  机型不同，但 KF / K-70 基础矩阵相同：按精确移植处理。"))
                    if res.get("calibrated_cross_model"):
                        self.queue.put((
                            "log",
                            "  机型不同，但风格表一致：已自动校准，无需勾选跨机型。"))
                    if res.get("container") == "makernote":
                        self.queue.put((
                            "log",
                            "  来源：EXIF MakerNote 0x927C（DCU 另存 DNG）"))
                    if res.get("layout_upgraded"):
                        self.queue.put((
                            "log",
                            "  0x021A 记录布局：%d 参数 / %d 字节 -> %d 参数 / %d 字节"
                            "（PDCU 只在 12 参数布局下列出四季）。"
                            % (res.get("target_n_params", 0),
                               res.get("target_rec_size", 0),
                               res.get("n_params", 0),
                               res.get("rec_size", 0))))
                    if res.get("table_relocated"):
                        self.queue.put((
                            "log",
                            "  提示：该文件的 0x021A 后没有空位，"
                            "模式表已迁移到私有块内空闲区（约 0x%X）。"
                            % res.get("table_off", 0)))
                    if res.get("blocks_relocated"):
                        self.queue.put((
                            "log",
                            "  提示：该文件的 0x021B 后没有空位，"
                            "矩阵表已迁移到 MakerNote / 私有块内空闲区（约 0x%X）。"
                            % res.get("blocks_off", 0)))
                    last_dir = os.path.dirname(out)
                else:
                    self.queue.put(("log", "  跳过：该文件已经包含四季记录"))
                    last_dir = os.path.dirname(out)
                ok += 1
            except Exception as exc:
                self.queue.put(("log", "  失败：%s" % exc))
                fail += 1
            self.queue.put(("progress", i, len(targets)))
        self.queue.put(("done", ok, fail, last_dir))

    # ---------- queue / UI updates ----------
    def _poll(self) -> None:
        try:
            while True:
                msg = self.queue.get_nowait()
                kind = msg[0]
                if kind == "log":
                    self._append_log(msg[1])
                elif kind == "progress":
                    self.progress.set(msg[1], msg[2])
                    self.status_var.set("正在转换 %d / %d" % (msg[1], msg[2]))
                elif kind == "done":
                    self._on_done(msg[1], msg[2], msg[3])
        except queue.Empty:
            pass
        self.after(100, self._poll)

    def _append_log(self, text: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", "[%s] " % time.strftime("%H:%M:%S"), "ts")
        self.log.insert("end", text + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _on_done(self, ok: int, fail: int, last_dir: str | None) -> None:
        self.start_btn.set_enabled(True)
        self.progress.set(1, 1)
        self.status_var.set("完成 · 成功 %d / 失败 %d" % (ok, fail))
        if last_dir:
            self.last_out_dir = last_dir
            self.open_btn.set_enabled(True)
        self._append_log("完成：成功 %d，失败 %d" % (ok, fail))
        if fail:
            show_alert(self, "转换完成",
                       "成功 %d 个，失败 %d 个。\n请查看日志。" % (ok, fail),
                       "warning")
        else:
            show_alert(self, "转换完成", "成功处理 %d 个文件。" % ok, "info")

    def _open_out_dir(self) -> None:
        if self.last_out_dir and os.path.isdir(self.last_out_dir):
            os.startfile(self.last_out_dir)
        else:
            show_alert(self, "提示", "还没有输出目录。", "info")

    def _on_close(self) -> None:
        if self.worker is not None and self.worker.is_alive():
            if not show_confirm(self, "退出", "正在转换，确定要退出吗？"):
                return
        self.destroy()


def selftest(argv) -> int:
    """Hidden build test: --selftest[-cross|-kf] <target> <output>."""
    try:
        cross = "--selftest-cross" in argv
        k1ii = "--selftest-k1ii" in argv
        kf = "--selftest-kf" in argv
        k30 = "--selftest-k30" in argv
        k01 = "--selftest-k01" in argv
        k50 = "--selftest-k50" in argv
        q7 = "--selftest-q7" in argv
        mx1 = "--selftest-mx1" in argv
        d645 = "--selftest-645d" in argv
        target, out = argv[-2], argv[-1]
        if k1ii:
            donor = make_builtin_k1ii_donor()
        elif d645:
            donor = make_builtin_645d_donor()
        elif mx1:
            donor = make_builtin_mx1_donor()
        elif q7:
            donor = make_builtin_q7_donor()
        elif k50:
            donor = make_builtin_k50_donor()
        elif k01:
            donor = make_builtin_k01_donor()
        elif k30:
            donor = make_builtin_k30_donor()
        elif kf:
            donor = make_builtin_kf_donor()
        else:
            donor = make_builtin_donor()
        res = core.convert_file(
            target, out, donor, overwrite=True, allow_cross_model=cross)
        log = out + ".selftest.txt"
        cm2 = core.describe_cm2(res.get("calibration"))
        with open(log, "w", encoding="utf-8") as f:
            f.write(repr(res))
            if cm2:
                f.write("\n" + cm2 + "\n")
        return 0
    except Exception:
        try:
            log = argv[-1] + ".selftest.txt"
            with open(log, "w", encoding="utf-8") as f:
                f.write(traceback.format_exc())
        except Exception:
            pass
        return 1


def main() -> int:
    if ("--selftest" in sys.argv or "--selftest-cross" in sys.argv
            or "--selftest-k1ii" in sys.argv
            or "--selftest-kf" in sys.argv or "--selftest-k30" in sys.argv
            or "--selftest-k01" in sys.argv or "--selftest-k50" in sys.argv
            or "--selftest-q7" in sys.argv or "--selftest-mx1" in sys.argv
            or "--selftest-645d" in sys.argv):
        return selftest(sys.argv)
    app = App()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
