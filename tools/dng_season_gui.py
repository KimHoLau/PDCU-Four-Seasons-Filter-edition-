#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PDCU MOD - Windows GUI for the Pentax four-season DNG patcher.

Select one or more DNG files, choose the season data source, and write
patched copies with the missing HARUBENI / KATEN / KYUSHU / FUYUNO
records and 3x3 color matrices.
"""
from __future__ import annotations

__copyright__ = "Copyright © 2026 KimHoLau X deepseek harness"

import io
import os
import queue
import sys
import threading
import time
import traceback
from pathlib import Path

import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk

try:
    from PIL import Image, ImageTk
except Exception:  # Pillow is optional in a source checkout.
    Image = None
    ImageTk = None

import dng_season_params as core

APP_TITLE = "PDCU MOD"
APP_VERSION = "2.7"
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
    ("春红", "HARUBENI", "#e2648c", "spring.png"),
    ("夏至", "KATEN", "#4ea8ff", "summer.png"),
    ("九秋", "KYUSHU", "#e0913c", "autumn.png"),
    ("冬日", "FUYUNO", "#a9c4d8", "winter.png"),
)
SEASON_ICON_SIZE = 24

def resource_path(name: str) -> str:
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, name)


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


class HoverTip:
    """Small dark tooltip that appears after hovering a row."""

    def __init__(self, owner, text, widgets):
        self._owner = owner
        self._text = text
        self._tip = None
        self._show_job = None
        self._hide_job = None
        for widget in widgets:
            widget.bind("<Enter>", self._enter, add="+")
            widget.bind("<Leave>", self._leave, add="+")
            widget.bind("<ButtonPress-1>", self._click, add="+")

    def _enter(self, _event=None):
        self._cancel_hide()
        if self._tip is not None or self._show_job is not None:
            return
        self._show_job = self._owner.after(350, self._show)

    def _leave(self, _event=None):
        self._cancel_show()
        if self._tip is not None and self._hide_job is None:
            self._hide_job = self._owner.after(80, self._hide)

    def _click(self, _event=None):
        self._cancel_show()
        self._hide()

    def _show(self):
        self._show_job = None
        if self._tip is not None or not self._owner.winfo_exists():
            return
        window = tk.Toplevel(self._owner)
        window.withdraw()
        window.overrideredirect(True)
        window.configure(bg=BORDER)
        frame = tk.Frame(window, bg=PANEL)
        frame.pack(padx=1, pady=1)
        tk.Label(frame, text=self._text, bg=PANEL, fg=TEXT_DIM,
                 font=(FONT, 8), justify="left", wraplength=340,
                 padx=10, pady=7).pack()
        window.update_idletasks()
        x = self._owner.winfo_rootx()
        y = self._owner.winfo_rooty() + self._owner.winfo_height() + 4
        width, height = window.winfo_reqwidth(), window.winfo_reqheight()
        x = min(max(4, x), window.winfo_screenwidth() - width - 4)
        y = min(max(4, y), window.winfo_screenheight() - height - 4)
        window.geometry("+%d+%d" % (x, y))
        window.deiconify()
        self._tip = window

    def _hide(self):
        self._hide_job = None
        self._show_job = None
        if self._tip is not None:
            self._tip.destroy()
            self._tip = None

    def _cancel_show(self):
        if self._show_job is not None:
            try:
                self._owner.after_cancel(self._show_job)
            except tk.TclError:
                pass
            self._show_job = None

    def _cancel_hide(self):
        if self._hide_job is not None:
            try:
                self._owner.after_cancel(self._hide_job)
            except tk.TclError:
                pass
            self._hide_job = None


class OptionRow(tk.Frame):
    """Radio-style selectable card."""

    def __init__(self, master, title, subtitle="", *, value, variable,
                 command=None, tooltip=""):
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
        self._tooltip = (HoverTip(self, tooltip, self._parts)
                         if tooltip else None)

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


class FileChooserDialog(tk.Toplevel):
    """Dark self-drawn file/directory chooser."""

    def __init__(self, parent, title, *, mode="files", multiple=False,
                 initial=None):
        super().__init__(parent, bg=BG)
        self.withdraw()
        self.overrideredirect(True)
        self.configure(highlightthickness=1, highlightbackground="#3a3a3a")
        self.result = None
        self._mode = mode
        self._multiple = bool(multiple and mode == "files")
        self._entries = []
        self._current = ""
        self._drag = (0, 0)
        self._preview_queue = queue.Queue()
        self._preview_seq = 0
        self._preview_photo = None
        self._preview_busy = False
        self._preview_pending = None

        head = tk.Frame(self, bg=PANEL)
        head.pack(fill="x")
        tk.Frame(head, bg=ACCENT, width=3).pack(side="left", fill="y")
        title_label = tk.Label(head, text=title, bg=PANEL, fg=TEXT,
                               font=(FONT, 10, "bold"))
        title_label.pack(side="left", padx=14, pady=10)
        close = tk.Label(head, text="×", bg=PANEL, fg=TEXT_MUTE,
                         font=(FONT, 12), cursor="hand2")
        close.pack(side="right", padx=14)
        close.bind("<Button-1>", lambda _e: self._cancel())
        for widget in (head, title_label):
            widget.bind("<ButtonPress-1>", self._drag_start)
            widget.bind("<B1-Motion>", self._drag_move)

        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True, padx=16, pady=(12, 14))

        tk.Label(body, text="路径", bg=BG, fg=TEXT_MUTE,
                 font=(FONT, 8)).pack(anchor="w")
        path_row = tk.Frame(body, bg=BG)
        path_row.pack(fill="x", pady=(4, 10))
        path_row.columnconfigure(0, weight=1)
        self.path_entry = DarkEntry(path_row)
        self.path_entry.grid(row=0, column=0, sticky="ew", ipady=5)
        self.path_entry.bind("<Return>", lambda _e: self._go())
        RoundButton(path_row, "转到", self._go, height=30, bg=BG
                    ).grid(row=0, column=1, padx=(8, 0))
        RoundButton(path_row, "上级", self._up, height=30, bg=BG
                    ).grid(row=0, column=2, padx=(8, 0))

        quick = tk.Frame(body, bg=BG)
        quick.pack(fill="x", pady=(0, 8))
        RoundButton(quick, "此电脑", self._show_drives, height=26, padx=10,
                    font=(FONT, 8), bg=BG).pack(side="left")
        home = os.path.expanduser("~")
        for label, folder in (("主目录", home),
                              ("桌面", os.path.join(home, "Desktop")),
                              ("下载", os.path.join(home, "Downloads")),
                              ("图片", os.path.join(home, "Pictures"))):
            if os.path.isdir(folder):
                RoundButton(quick, label,
                            lambda path=folder: self._load_dir(path),
                            height=26, padx=10, font=(FONT, 8), bg=BG
                            ).pack(side="left", padx=(6, 0))

        content = tk.Frame(body, bg=BG)
        content.pack(fill="both", expand=True)
        content.rowconfigure(0, weight=1)
        content.columnconfigure(0, weight=1)
        list_wrap = tk.Frame(content, bg=BG)
        list_wrap.grid(row=0, column=0, sticky="nsew")
        list_wrap.rowconfigure(0, weight=1)
        list_wrap.columnconfigure(0, weight=1)
        self.listbox = tk.Listbox(
            list_wrap, selectmode=(tk.EXTENDED if self._multiple else tk.BROWSE),
            font=(FONT, 9), activestyle="none", exportselection=False,
            bg=FIELD, fg="#d6d6d6", selectbackground="#1d3f66",
            selectforeground="#ffffff", bd=0, relief="flat",
            highlightthickness=1, highlightbackground=BORDER,
            highlightcolor="#3a3a3a", selectborderwidth=0)
        self.listbox.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(list_wrap, orient="vertical",
                               style="Dark.Vertical.TScrollbar",
                               command=self.listbox.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.listbox.configure(yscrollcommand=scroll.set)
        self.listbox.bind("<Double-Button-1>", self._on_double)
        self.listbox.bind("<Return>", self._on_double)
        self.listbox.bind("<<ListboxSelect>>", self._on_select)

        preview = tk.Frame(content, bg=PANEL, width=276,
                           highlightthickness=1, highlightbackground=BORDER)
        preview.grid(row=0, column=1, sticky="ns", padx=(10, 0))
        preview.grid_propagate(False)
        self.preview_label = tk.Label(
            preview, text="选择 DNG 查看预览", bg=PANEL, fg=TEXT_MUTE,
            font=(FONT, 9), justify="center")
        self.preview_label.pack(fill="both", expand=True, padx=8, pady=8)
        self.preview_info = tk.Label(
            preview, text="", bg=PANEL, fg=TEXT_MUTE, font=(FONT, 8),
            anchor="w", justify="left")
        self.preview_info.pack(fill="x", padx=8, pady=(0, 8))

        self.error = tk.Label(body, text="", bg=BG, fg="#e05a5a",
                              font=(FONT, 8), anchor="w")
        self.error.pack(fill="x", pady=(6, 0))

        foot = tk.Frame(body, bg=BG)
        foot.pack(fill="x", pady=(8, 0))
        self.hint = tk.Label(foot, text="", bg=BG, fg=TEXT_MUTE,
                             font=(FONT, 8), anchor="w")
        self.hint.pack(side="left", fill="x", expand=True)
        ok_text = "打开" if mode == "files" else "选择文件夹"
        RoundButton(foot, ok_text, self._accept, primary=True, height=32,
                    bg=BG).pack(side="right")
        RoundButton(foot, "取消", self._cancel, height=32, bg=BG
                    ).pack(side="right", padx=(0, 8))

        self.bind("<Escape>", lambda _e: self._cancel())
        start = initial or os.getcwd()
        if os.path.isfile(start):
            start = os.path.dirname(start)
        if not os.path.isdir(start):
            start = os.getcwd()
        self._load_dir(start)

        self.transient(parent)
        self.update_idletasks()
        w, h = 900, 600
        px, py = parent.winfo_rootx(), parent.winfo_rooty()
        pw, ph = parent.winfo_width(), parent.winfo_height()
        x = px + max(0, (pw - w) // 2)
        y = py + max(0, (ph - h) // 3)
        self.geometry("%dx%d+%d+%d" % (w, h, x, y))
        self.deiconify()
        self.lift()
        self.focus_force()
        self.grab_set()
        self.after(20, self.path_entry.focus_set)
        self.after(80, self._poll_preview)

    # ---------- window ----------
    def _drag_start(self, event):
        self._drag = (event.x_root - self.winfo_x(),
                      event.y_root - self.winfo_y())

    def _drag_move(self, event):
        dx, dy = self._drag
        self.geometry("+%d+%d" % (event.x_root - dx, event.y_root - dy))

    def _close(self):
        try:
            self.grab_release()
        except tk.TclError:
            pass
        self.destroy()

    def _cancel(self):
        self.result = None
        self._close()

    def _error(self, text):
        self.error.configure(text=text)

    def _clear_error(self):
        self.error.configure(text="")

    # ---------- navigation ----------
    @staticmethod
    def _normalize(text):
        text = (text or "").strip().strip('"')
        if not text:
            return ""
        return os.path.abspath(os.path.expanduser(os.path.expandvars(text)))

    @staticmethod
    def _drives():
        try:
            return list(os.listdrives())
        except AttributeError:
            return [drive for drive in
                    ("%s:\\" % chr(code) for code in range(ord("C"), ord("Z") + 1))
                    if os.path.isdir(drive)]

    def _show_drives(self):
        drives = self._drives()
        if not drives:
            self._error("没有可用的驱动器")
            return
        self._current = ""
        self._entries = [(drive, drive, True) for drive in drives]
        self.path_entry.delete(0, "end")
        self.listbox.delete(0, "end")
        for drive, _path, _is_dir in self._entries:
            self.listbox.insert("end", drive)
        self._clear_preview()
        self._clear_error()
        self._update_hint()

    def _load_dir(self, path):
        path = self._normalize(path)
        if not path or not os.path.isdir(path):
            self._error("目录不存在或不可访问")
            return False
        try:
            items = []
            with os.scandir(path) as entries:
                for entry in entries:
                    try:
                        is_dir = entry.is_dir()
                    except OSError:
                        continue
                    if is_dir:
                        items.append((entry.name, entry.path, True))
                    elif (self._mode != "dir"
                          and entry.name.lower().endswith(".dng")):
                        items.append((entry.name, entry.path, False))
        except OSError as exc:
            self._error("无法读取目录：%s" % exc)
            return False
        items.sort(key=lambda item: (not item[2], item[0].casefold()))
        self._current = path
        self._entries = items
        self.path_entry.delete(0, "end")
        self.path_entry.insert(0, path)
        self.listbox.delete(0, "end")
        for name, _full, is_dir in items:
            self.listbox.insert("end", name + (os.sep if is_dir else ""))
        self._clear_preview()
        self._clear_error()
        self._update_hint()
        return True

    def _up(self):
        parent = os.path.dirname(self._current.rstrip("\\/"))
        if not parent or os.path.normcase(parent) == os.path.normcase(self._current):
            return
        self._load_dir(parent)

    def _go(self):
        path = self._normalize(self.path_entry.get())
        if not path:
            self._error("请输入路径")
            return
        if os.path.isdir(path):
            self._load_dir(path)
            return
        if os.path.isfile(path):
            if self._mode == "dir":
                self._error("这里需要选择目录，不是文件")
                return
            if not path.lower().endswith(".dng"):
                self._error("请选择 .DNG 文件")
                return
            parent = os.path.dirname(path)
            if not self._load_dir(parent):
                return
            target = os.path.normcase(path)
            for index, (_name, full, is_dir) in enumerate(self._entries):
                if not is_dir and os.path.normcase(full) == target:
                    self.listbox.selection_clear(0, "end")
                    self.listbox.selection_set(index)
                    self.listbox.activate(index)
                    self.listbox.see(index)
                    self._update_hint()
                    return
            self._error("文件不在这个目录中")
            return
        self._error("路径不存在")

    def _update_hint(self):
        if not self._current:
            action = "打开" if self._mode == "files" else "选择文件夹"
            self.hint.configure(text="选择驱动器后按「%s」进入" % action)
            return
        if self._mode == "dir":
            self.hint.configure(text="单击文件夹后按「选择文件夹」；双击也可进入")
            return
        count = len(self.listbox.curselection())
        if self._multiple and count:
            self.hint.configure(text="已选 %d 个文件" % count)
        else:
            self.hint.configure(text="单击文件夹后按「打开」进入；双击文件可直接选择")

    # ---------- selection ----------
    def _on_double(self, _event=None):
        selected = self.listbox.curselection()
        if not selected:
            return
        index = selected[0]
        _name, path, is_dir = self._entries[index]
        if is_dir:
            self._load_dir(path)
            return
        self.listbox.selection_clear(0, "end")
        self.listbox.selection_set(index)
        self.listbox.activate(index)
        self._accept()

    # ---------- preview ----------
    def _on_select(self, _event=None):
        self._update_hint()
        self._queue_preview()

    def _clear_preview(self, text="选择 DNG 查看预览"):
        self._preview_seq += 1
        self._preview_pending = None
        self._preview_photo = None
        self.preview_label.configure(image="", text=text)
        self.preview_info.configure(text="")

    def _queue_preview(self):
        selected = self.listbox.curselection()
        path = None
        for index in selected:
            _name, full, is_dir = self._entries[index]
            if not is_dir:
                path = full
                break
        if path is None:
            self._clear_preview()
            return
        if Image is None:
            self._clear_preview("预览需要 Pillow")
            return
        self._preview_seq += 1
        seq = self._preview_seq
        self._preview_photo = None
        self.preview_label.configure(image="", text="正在加载预览…")
        self.preview_info.configure(text=os.path.basename(path))
        self._preview_pending = (seq, path)
        self._start_preview()

    def _start_preview(self):
        if self._preview_busy or self._preview_pending is None:
            return
        seq, path = self._preview_pending
        self._preview_pending = None
        self._preview_busy = True
        threading.Thread(target=self._load_preview, args=(seq, path),
                         daemon=True).start()

    def _load_preview(self, seq, path):
        try:
            dng = core.Dng(path)
            raw = dng.preview_jpeg()
            if raw:
                image = Image.open(io.BytesIO(raw))
            else:
                image = Image.open(path)
            image.load()
            original_w, original_h = image.size
            image.thumbnail((248, 190), Image.LANCZOS)
            if image.mode not in ("RGB", "RGBA"):
                image = image.convert("RGB")
            self._preview_queue.put(
                (seq, image, dng.model, original_w, original_h, ""))
        except Exception as exc:
            self._preview_queue.put((seq, None, "", 0, 0, str(exc)))

    def _poll_preview(self):
        if not self.winfo_exists():
            return
        try:
            while True:
                seq, image, model, width, height, error = (
                    self._preview_queue.get_nowait())
                self._preview_busy = False
                if seq != self._preview_seq:
                    continue
                if image is not None:
                    self._preview_photo = ImageTk.PhotoImage(image)
                    self.preview_label.configure(image=self._preview_photo,
                                                 text="")
                    self.preview_info.configure(
                        text="%s\n%d × %d"
                        % (model or os.path.basename(self._current), width, height))
                else:
                    self._preview_photo = None
                    self.preview_label.configure(image="",
                                                 text="无法读取预览")
                    self.preview_info.configure(text=error[:120])
        except queue.Empty:
            pass
        if self._preview_pending is not None:
            self._start_preview()
        self.after(80, self._poll_preview)

    def _accept(self):
        if self._mode == "dir":
            selected = self.listbox.curselection()
            if selected:
                _name, path, is_dir = self._entries[selected[0]]
                if not is_dir:
                    self._error("请选择文件夹")
                    return
                self.result = path
            elif self._current:
                self.result = self._current
            else:
                self._error("请选择驱动器或文件夹")
                return
            self._close()
            return
        picked = [self._entries[i] for i in self.listbox.curselection()]
        files = [item for item in picked if not item[2]]
        if files:
            paths = [item[1] for item in files]
            if self._multiple:
                self.result = paths
            else:
                self.result = paths[0]
            self._close()
            return
        folders = [item for item in picked if item[2]]
        if folders:
            self._load_dir(folders[0][1])
            return
        self._error("请选择 .DNG 文件或文件夹")


def ask_files(parent, title="选择 DNG 文件", initial=None):
    dialog = FileChooserDialog(parent, title, mode="files", multiple=True,
                               initial=initial)
    parent.wait_window(dialog)
    return list(dialog.result or [])


def ask_file(parent, title="选择 DNG 文件", initial=None):
    dialog = FileChooserDialog(parent, title, mode="files", multiple=False,
                               initial=initial)
    parent.wait_window(dialog)
    return dialog.result


def ask_directory(parent, title="选择目录", initial=None):
    dialog = FileChooserDialog(parent, title, mode="dir", initial=initial)
    parent.wait_window(dialog)
    return dialog.result


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
        self._detect_pending: set[str] = set()
        self._detect_errors: dict[str, str] = {}
        self._logo = None
        self._season_icons = []
        self._last_browse_dir = os.getcwd()
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
        added = []
        for arg in sys.argv[1:]:
            if arg.lower().endswith(".dng") and os.path.isfile(arg):
                if self._append_target(os.path.abspath(arg)):
                    added.append(os.path.abspath(arg))
        self._refresh_file_state()
        if self.targets:
            self.status_var.set("已选择 %d 个文件" % len(self.targets))
        self._request_model_detection(added)

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
        for index, source in enumerate(core.BUILTIN_SOURCES.values()):
            tip = "适配机型：\n" + "、".join(source.models)
            OptionRow(card.body, source.label, value=source.key,
                      variable=self.donor_mode,
                      command=self._donor_mode_changed, tooltip=tip
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

    def _load_season_icon(self, filename):
        """Load and nearest-neighbour shrink one season PNG for Tk."""
        try:
            image = tk.PhotoImage(file=resource_path(
                os.path.join("assets", filename)))
            side = max(image.width(), image.height())
            factor = max(1, round(side / SEASON_ICON_SIZE))
            if factor > 1:
                image = image.subsample(factor, factor)
        except tk.TclError:
            return None
        self._season_icons.append(image)
        return image

    def _build_season_card(self, parent) -> None:
        card = Card(parent, "", "四季色彩", "补齐后 PDCU 内可选")
        card.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        grid = tk.Frame(card.body, bg=PANEL)
        grid.pack(fill="x")
        for index, (cn, en, color, icon_name) in enumerate(SEASONS):
            grid.columnconfigure(index, weight=1, uniform="season")
            cell = tk.Frame(grid, bg=PANEL)
            cell.grid(row=0, column=index, sticky="w")
            line = tk.Frame(cell, bg=PANEL)
            line.pack(anchor="w")
            slot = tk.Frame(line, width=SEASON_ICON_SIZE,
                            height=SEASON_ICON_SIZE, bg=PANEL)
            slot.pack_propagate(False)
            slot.pack(side="left")
            icon = self._load_season_icon(icon_name)
            if icon is not None:
                tk.Label(slot, image=icon, bg=PANEL, bd=0,
                         highlightthickness=0).place(relx=0.5, rely=0.5,
                                                     anchor="center")
            else:
                dot = tk.Canvas(slot, width=SEASON_ICON_SIZE,
                                height=SEASON_ICON_SIZE, bg=PANEL,
                                highlightthickness=0)
                dot.pack()
                dot.create_oval(8, 8, 15, 15, fill=color, outline="")
            tk.Label(line, text=cn, bg=PANEL, fg="#d8d8d8",
                     font=(FONT, 9)).pack(side="left", padx=(6, 0))
            tk.Label(cell, text=en, bg=PANEL, fg=TEXT_MUTE,
                     font=(MONO, 7)).pack(anchor="w", padx=(30, 0),
                                          pady=(1, 0))

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
    def _append_target(self, path: str) -> bool:
        path = os.path.abspath(path)
        if path in self.targets:
            return False
        self.targets.append(path)
        self.listbox.insert("end", path)
        return True

    def _add_files(self) -> None:
        paths = ask_files(self, "选择 DNG 文件", self._last_browse_dir)
        if paths:
            self._last_browse_dir = os.path.dirname(os.path.abspath(paths[0]))
        added = [path for path in paths if self._append_target(path)]
        self._refresh_file_state()
        self.status_var.set("已选择 %d 个文件" % len(self.targets))
        self._request_model_detection(added)

    def _remove_selected(self) -> None:
        for index in reversed(self.listbox.curselection()):
            self.listbox.delete(index)
            del self.targets[index]
        self._refresh_file_state()
        self.status_var.set("已选择 %d 个文件" % len(self.targets))
        self._request_model_detection(self.targets)

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

    @staticmethod
    def _read_model(path: str) -> str:
        return (core.Dng(path).model or "").strip()

    def _request_model_detection(self, paths) -> None:
        """Parse unknown models on a background thread, not on the Tk thread."""
        pending = []
        for path in paths:
            path = os.path.abspath(path)
            if path in self._model_cache or path in self._detect_pending:
                continue
            pending.append(path)
        if not pending:
            self._autoselect_donor()
            return
        self._detect_pending.update(pending)
        for path in pending:
            self._detect_errors.pop(path, None)
        self.status_var.set("正在识别机型…")
        threading.Thread(target=self._detect_models, args=(pending,),
                         daemon=True).start()

    def _detect_models(self, paths) -> None:
        """Background model reader; results go through self.queue only."""
        try:
            for path in paths:
                try:
                    model = self._read_model(path)
                    error = "" if model else "未读取到机型"
                except Exception as exc:
                    model, error = "", str(exc)
                self.queue.put(("model", path, model, error))
        finally:
            self.queue.put(("detect_done",))

    def _finish_detection(self) -> None:
        if not self.targets:
            return
        self._autoselect_donor()
        failed = [p for p in self.targets if p in self._detect_errors]
        if failed:
            self.status_var.set("%d 个文件无法识别机型，其余文件可继续" % len(failed))

    def _autoselect_donor(self) -> None:
        """Pick the built-in donor that matches the selected target models."""
        if not self.targets:
            return
        if any(path not in self._model_cache for path in self.targets):
            return
        models = {self._model_cache[path] for path in self.targets}
        if "" in models:
            return
        if self.donor_mode.get() not in core.BUILTIN_SOURCES:
            return
        source = core.source_for_models(models)
        if source is None:
            if len(models) > 1:
                self.status_var.set("检测到多种机型，请分批处理或使用 DNG 来源")
            else:
                model = next(iter(models))
                self.status_var.set("检测到 %s，请选择来源或使用 DNG 文件" % model)
            return
        self.donor_mode.set(source.key)
        self._donor_mode_changed()
        self.status_var.set("检测到 %s，已选择「%s」"
                            % ("、".join(sorted(models)), source.label))

    # ---------- options ----------
    def _donor_mode_changed(self) -> None:
        mode = self.donor_mode.get()
        if mode == core.CUSTOM_DONOR_MODE:
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
            self.cross_check.set_enabled(False)

    @staticmethod
    def _shorten(text: str, limit: int = 30) -> str:
        if len(text) <= limit:
            return text
        return text[:limit - 1] + "…"

    def _browse_donor(self) -> None:
        path = ask_file(self, "选择同机型 donor DNG", self._last_browse_dir)
        if path:
            self._last_browse_dir = os.path.dirname(os.path.abspath(path))
            self.custom_donor = os.path.abspath(path)
            self.donor_mode.set(core.CUSTOM_DONOR_MODE)
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
        initial = self.out_entry.get().strip() or self._last_browse_dir
        path = ask_directory(self, "选择输出目录", initial)
        if path:
            self._last_browse_dir = path
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
        if any(path in self._detect_pending for path in self.targets):
            show_alert(self, "正在识别机型",
                       "机型识别在后台进行，请稍候再开始转换。", "info")
            return

        donor_mode = self.donor_mode.get()
        donor_path = self.custom_donor
        if donor_mode == core.CUSTOM_DONOR_MODE:
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

        # A built-in source is tied to the bodies it was calibrated for.  A
        # mismatch is refused here, before any worker starts, so no output
        # file can be produced.  The cross-model opt-in is only for a custom
        # donor DNG.
        if donor_mode in core.BUILTIN_SOURCE_MODELS:
            rejected = []
            for target in self.targets:
                model = self._model_cache.get(target, "")
                if not core.builtin_source_allows(donor_mode, model):
                    rejected.append((target, model or "无法识别"))
            if rejected:
                lines = ["所选内置来源不适用于以下机型：", ""]
                for target, model in rejected[:8]:
                    lines.append("%s（%s）" % (os.path.basename(target), model))
                if len(rejected) > 8:
                    lines.append("…")
                lines += ["", "请选择匹配的内置来源，或在「高级」里使用自定义 DNG 来源。"]
                show_alert(self, "来源不匹配", "\n".join(lines), "warning")
                return

        allow_cross = (bool(self.allow_cross_model.get())
                       and donor_mode == core.CUSTOM_DONOR_MODE)

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
        source = core.BUILTIN_SOURCES.get(donor_mode)
        try:
            if source is not None:
                donors = {kind: core.builtin_donor(kind)
                          for kind in source.kinds}
                self.queue.put(("log", source.log_text))
            else:
                donors[core.CUSTOM_DONOR_MODE] = core.Dng(donor_path)
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
                model = self._model_cache.get(target)
                if model is None:
                    try:
                        model = self._read_model(target)
                    except Exception:
                        model = ""
                if source is not None:
                    kind = core.donor_kind_for_model(model)
                    if kind not in donors:
                        raise core.DngError(
                            "内置来源不适用于机型 %r" % (model or "无法识别"))
                    donor = donors[kind]
                    if kind == "k1ii":
                        self.queue.put((
                            "log",
                            "  K-1 Mark II：使用 K-1 原生四季表（Y=I，"
                            "28 条记录 / 21 个基础矩阵与 K-1 逐字节相同）"))
                else:
                    donor = donors[core.CUSTOM_DONOR_MODE]
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
                elif kind == "model":
                    _kind, path, model, error = msg
                    self._model_cache[path] = model
                    self._detect_pending.discard(path)
                    if error:
                        self._detect_errors[path] = error
                    else:
                        self._detect_errors.pop(path, None)
                elif kind == "detect_done":
                    if not self._detect_pending:
                        self._finish_detection()
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
        target, out = argv[-2], argv[-1]
        donor = core.builtin_donor(core.selftest_donor_kind(argv) or "k1")
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
    if any(flag in sys.argv for flag in core.SELFTEST_FLAGS):
        return selftest(sys.argv)
    app = App()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
