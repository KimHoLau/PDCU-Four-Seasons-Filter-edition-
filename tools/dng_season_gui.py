#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PDCU Four Seasons DNG patcher - Windows GUI.

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
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText

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

APP_TITLE = "PDCU 四季参数补齐工具"
APP_VERSION = "2.4"
COPYRIGHT = "版权所有 © 2026 KimHoLau X deepseek harness"
FONT = "Microsoft YaHei UI"
MONO = "Consolas"


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


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("%s v%s" % (APP_TITLE, APP_VERSION))
        self.geometry("920x1000")
        self.minsize(840, 900)
        self.configure(bg="#f3f5f8")

        self.targets: list[str] = []
        self.queue: "queue.Queue[tuple]" = queue.Queue()
        self.worker: threading.Thread | None = None
        self.last_out_dir: str | None = None
        self._model_cache: dict[str, str] = {}

        self._build_style()
        self._build_ui()
        self.after(100, self._poll)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_style(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("vista")
        except tk.TclError:
            pass
        style.configure("Section.TLabel", font=(FONT, 10, "bold"))
        style.configure("Hint.TLabel", font=(FONT, 8), foreground="#777777")
        style.configure("Accent.TButton", font=(FONT, 10, "bold"))
        style.configure("Status.TLabel", font=(FONT, 9), foreground="#555555")

    def _build_ui(self) -> None:
        header = tk.Frame(self, bg="#223047", height=128)
        header.pack(fill="x")
        header.pack_propagate(False)
        tk.Label(header, text=APP_TITLE, bg="#223047", fg="white",
                 font=(FONT, 18, "bold")).pack(anchor="w", padx=24, pady=(16, 0))
        tk.Label(header,
                 text="支持 PENTAX K-1 / K-1 Mark II / KF / K-70 / K-3 / K-3 II / K-5 II / K-5 II s / 645Z / 645D\n"
                       "KP / K-S2 / K-30 / K-01 / K-50 / Q7 · 补上 HARUBENI / KATEN / KYUSHU / FUYUNO 四季数据",
                 bg="#223047", fg="#c9d4e2", font=(FONT, 9),
                 justify="left").pack(anchor="w", padx=25, pady=(3, 0))
        tk.Label(header, text=COPYRIGHT, bg="#223047", fg="#d5dfeb",
                 font=(FONT, 9)).pack(anchor="w", padx=25, pady=(3, 0))

        body = ttk.Frame(self, padding=18)
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=1)

        # ---- target files ----
        ttk.Label(body, text="1. 选择要转换的 DNG 文件", style="Section.TLabel").grid(
            row=0, column=0, sticky="w", pady=(0, 6))
        list_frame = ttk.Frame(body)
        list_frame.grid(row=1, column=0, sticky="nsew")
        list_frame.columnconfigure(0, weight=1)

        self.listbox = tk.Listbox(
            list_frame, selectmode=tk.EXTENDED, height=5,
            font=(MONO, 9), activestyle="none",
            bg="white", bd=1, relief="solid", highlightthickness=0,
        )
        self.listbox.grid(row=0, column=0, sticky="nsew")
        sb = ttk.Scrollbar(list_frame, orient="vertical", command=self.listbox.yview)
        sb.grid(row=0, column=1, sticky="ns")
        self.listbox.configure(yscrollcommand=sb.set)

        btn_col = ttk.Frame(list_frame)
        btn_col.grid(row=0, column=2, sticky="n", padx=(8, 0))
        ttk.Button(btn_col, text="添加文件...", command=self._add_files).pack(fill="x", pady=(0, 5))
        ttk.Button(btn_col, text="移除选中", command=self._remove_selected).pack(fill="x", pady=(0, 5))
        ttk.Button(btn_col, text="清空", command=self._clear_files).pack(fill="x")

        # ---- donor ----
        donor_box = ttk.LabelFrame(
            body, text="2. 季节参数来源（K-1 / K-1 Mark II / KF / K-70 / K-3 / K-3 II / K-5 II / K-5 II s / 645Z / 645D / KP / K-S2 / K-30 / K-01 / K-50 / Q7 / MX-1）",
            padding=10)
        donor_box.grid(row=2, column=0, sticky="ew", pady=(14, 0))
        donor_box.columnconfigure(1, weight=1)

        self.donor_mode = tk.StringVar(value="builtin")
        ttk.Radiobutton(donor_box,
                        text="使用内置 K-1 / K-1 Mark II 四季参数（适用于 PENTAX K-1 / K-1 Mark II）",
                        variable=self.donor_mode, value="builtin",
                        command=self._donor_mode_changed).grid(row=0, column=0, columnspan=3, sticky="w")
        ttk.Label(donor_box,
                  text="K-1 Mark II 的 28 条模式记录与 21 个基础矩阵和 K-1 逐字节相同，"
                       "内置 K-1 原生四季表可直接精确移植（Y=I）。",
                  style="Hint.TLabel", wraplength=800).grid(row=1, column=0, columnspan=3,
                                                            sticky="w", padx=(22, 0))

        ttk.Radiobutton(donor_box, text="使用内置 KF 四季参数（KF / K-70，以及 K-3 / K-3 II / K-5 II / K-5 II s / 645Z / KP / K-S2）",
                        variable=self.donor_mode, value="builtin_kf",
                        command=self._donor_mode_changed).grid(row=2, column=0, columnspan=3,
                                                               sticky="w", pady=(8, 0))
        ttk.Label(donor_box,
                  text="KF 与 K-70 基础矩阵相同，可精确补；其他机型会按目标机身的 0x021B 基准矩阵"
                       "自动校准（K-3 / K-3 II / K-5 II / K-5 II s / 645Z / KP / K-S2 已验证）。",
                  style="Hint.TLabel", wraplength=800).grid(row=3, column=0, columnspan=3,
                                                            sticky="w", padx=(22, 0))

        ttk.Radiobutton(donor_box, text="使用内置 645D 四季参数（适用于 PENTAX 645D）",
                        variable=self.donor_mode, value="builtin_645d",
                        command=self._donor_mode_changed).grid(row=4, column=0, columnspan=3,
                                                               sticky="w", pady=(8, 0))
        ttk.Label(donor_box,
                  text="645D 的 0x021A 是 11 参数 / 24 字节记录；PDCU 只在 12 参数布局下列出四季，"
                       "工具会整表重建为 12 参数（原有记录逐字段保留）。内置表是 KF 四季矩阵按 645D 基准矩阵校准后的结果。",
                  style="Hint.TLabel", wraplength=800).grid(row=5, column=0, columnspan=3,
                                                            sticky="w", padx=(22, 0))

        ttk.Radiobutton(donor_box, text="使用内置 KF→K-30 / K-01 / K-50 / Q7 / MX-1 四季参数"
                                       "（适用于无 0x021A/0x021B 的机身）",
                        variable=self.donor_mode, value="builtin_k30",
                        command=self._donor_mode_changed).grid(row=6, column=0, columnspan=3,
                                                               sticky="w", pady=(8, 0))
        ttk.Label(donor_box,
                  text="K-30 / K-01 / K-50 / Q7 / MX-1 机内没有 0x021A/0x021B；工具会新建标签，"
                       "并分别用各机身色彩空间校准 KF 四季矩阵（Q7 / MX-1 私有块为小端）。",
                  style="Hint.TLabel", wraplength=760).grid(row=7, column=0, columnspan=3,
                                                            sticky="w", padx=(22, 0))

        ttk.Radiobutton(donor_box, text="使用同机型 DNG 作为 donor：",
                        variable=self.donor_mode, value="file",
                        command=self._donor_mode_changed).grid(row=8, column=0, columnspan=3,
                                                               sticky="w", pady=(8, 0))
        self.donor_entry = ttk.Entry(donor_box)
        self.donor_entry.grid(row=9, column=1, sticky="ew", padx=(22, 6), pady=(4, 0))
        self.donor_browse = ttk.Button(donor_box, text="浏览...", command=self._browse_donor)
        self.donor_browse.grid(row=9, column=2, sticky="e", pady=(4, 0))

        self.allow_cross_model = tk.BooleanVar(value=False)
        self.cross_check = ttk.Checkbutton(
            donor_box,
            text="允许其他跨机型 donor（目标有 0x021B 时会按机身自动校准）",
            variable=self.allow_cross_model,
            state="normal",
        )
        self.cross_check.grid(row=10, column=0, columnspan=3, sticky="w", pady=(8, 0))
        ttk.Label(
            donor_box,
            text="K-3 / K-3 II / K-5 II / K-5 II s / 645Z / 645D / KP / K-S2 已能自动识别并校准，"
                 "不需要勾选；只有风格表与 donor 不一致的未知机型才需要。",
            style="Hint.TLabel", wraplength=800,
        ).grid(row=11, column=0, columnspan=3, sticky="w", padx=(22, 0))

        # ---- output ----
        out_box = ttk.LabelFrame(body, text="3. 输出位置", padding=10)
        out_box.grid(row=3, column=0, sticky="ew", pady=(14, 0))
        out_box.columnconfigure(1, weight=1)

        self.out_mode = tk.StringVar(value="same")
        ttk.Radiobutton(out_box, text="与源文件同目录，文件名加 _all",
                        variable=self.out_mode, value="same",
                        command=self._out_mode_changed).grid(row=0, column=0, columnspan=3, sticky="w")
        ttk.Radiobutton(out_box, text="指定输出目录：",
                        variable=self.out_mode, value="dir",
                        command=self._out_mode_changed).grid(row=1, column=0, sticky="w", pady=(6, 0))
        self.out_entry = ttk.Entry(out_box)
        self.out_entry.grid(row=1, column=1, sticky="ew", padx=(22, 6), pady=(6, 0))
        self.out_browse = ttk.Button(out_box, text="浏览...", command=self._browse_out)
        self.out_browse.grid(row=1, column=2, sticky="e", pady=(6, 0))

        self.overwrite = tk.BooleanVar(value=False)
        ttk.Checkbutton(out_box, text="覆盖已存在的输出文件",
                        variable=self.overwrite).grid(row=2, column=0, columnspan=3,
                                                     sticky="w", pady=(8, 0))

        # ---- actions ----
        action = ttk.Frame(body)
        action.grid(row=4, column=0, sticky="ew", pady=(16, 0))
        action.columnconfigure(2, weight=1)
        self.start_btn = ttk.Button(action, text="开始转换", style="Accent.TButton",
                                    command=self._start)
        self.start_btn.grid(row=0, column=0, sticky="w")
        self.open_btn = ttk.Button(action, text="打开输出目录",
                                   command=self._open_out_dir, state="disabled")
        self.open_btn.grid(row=0, column=1, sticky="w", padx=(10, 0))
        self.status_var = tk.StringVar(value="就绪")
        ttk.Label(action, textvariable=self.status_var, style="Status.TLabel").grid(
            row=0, column=2, sticky="e")

        self.progress = ttk.Progressbar(body, mode="determinate", maximum=1, value=0)
        self.progress.grid(row=5, column=0, sticky="ew", pady=(8, 0))

        # ---- log ----
        log_frame = ttk.LabelFrame(body, text="日志", padding=6)
        log_frame.grid(row=6, column=0, sticky="nsew", pady=(12, 0))
        log_frame.rowconfigure(0, weight=1)
        log_frame.columnconfigure(0, weight=1)
        body.rowconfigure(1, weight=0)
        body.rowconfigure(6, weight=1)

        self.log = ScrolledText(log_frame, height=8, wrap="word",
                                font=(MONO, 9), state="disabled",
                                bg="#1f2430", fg="#d7dce5",
                                insertbackground="#d7dce5", relief="flat")
        self.log.grid(row=0, column=0, sticky="nsew")

        self._donor_mode_changed()
        self._out_mode_changed()

        # Allow "drag a DNG onto the exe" / passing files on the command line.
        for arg in sys.argv[1:]:
            if arg.lower().endswith(".dng") and os.path.isfile(arg):
                p = os.path.abspath(arg)
                if p not in self.targets:
                    self.targets.append(p)
                    self.listbox.insert("end", p)
        if self.targets:
            self.status_var.set("已选择 %d 个文件" % len(self.targets))
        self._autoselect_donor()

        ico = resource_path("season.ico")
        if os.path.exists(ico):
            try:
                self.iconbitmap(ico)
            except tk.TclError:
                pass

    # ---------- file list ----------
    def _add_files(self) -> None:
        paths = filedialog.askopenfilenames(
            parent=self, title="选择 DNG 文件",
            filetypes=[("DNG 文件", "*.DNG *.dng"), ("所有文件", "*.*")])
        for p in paths:
            p = os.path.abspath(p)
            if p not in self.targets:
                self.targets.append(p)
                self.listbox.insert("end", p)
        self.status_var.set("已选择 %d 个文件" % len(self.targets))
        self._autoselect_donor()

    def _remove_selected(self) -> None:
        for i in reversed(self.listbox.curselection()):
            self.listbox.delete(i)
            del self.targets[i]
        self.status_var.set("已选择 %d 个文件" % len(self.targets))
        self._autoselect_donor()

    def _clear_files(self) -> None:
        self.listbox.delete(0, "end")
        self.targets.clear()
        self.status_var.set("就绪")

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
        if models <= {"PENTAX KF", "PENTAX K-70"}:
            if current in ("builtin", "builtin_kf", "builtin_k30",
                           "builtin_645d"):
                self.donor_mode.set("builtin_kf")
                self._donor_mode_changed()
                self.status_var.set("检测到 KF / K-70，已自动选择“内置 KF 四季参数”")
        elif models <= {"PENTAX K-30", "PENTAX K-01", "PENTAX K-50",
                        "PENTAX Q7", "PENTAX MX-1"}:
            if current in ("builtin", "builtin_kf", "builtin_k30",
                           "builtin_645d"):
                self.donor_mode.set("builtin_k30")
                self._donor_mode_changed()
                self.status_var.set("检测到无 0x021A/0x021B 机身（K-30 / K-01 / K-50 / Q7 / MX-1），"
                                    "已自动选择对应内置四季参数")
        elif models <= {"PENTAX K-1", "PENTAX K-1 Mark II"}:
            if current in ("builtin", "builtin_kf", "builtin_k30",
                           "builtin_645d"):
                self.donor_mode.set("builtin")
                self._donor_mode_changed()
                self.status_var.set(
                    "检测到 %s，已自动选择“内置 K-1 / K-1 Mark II 四季参数”"
                    % " / ".join(sorted(models)))
        elif models == {"PENTAX 645D"}:
            if current in ("builtin", "builtin_kf", "builtin_k30",
                           "builtin_645d"):
                self.donor_mode.set("builtin_645d")
                self._donor_mode_changed()
                self.status_var.set("检测到 645D，已自动选择“内置 645D 四季参数”")
        elif models <= CALIBRATED_MODELS:
            if current in ("builtin", "builtin_kf", "builtin_k30",
                           "builtin_645d"):
                self.donor_mode.set("builtin_kf")
                self._donor_mode_changed()
                self.status_var.set(
                    "检测到 %s；已选择内置 KF 四季参数，并按机身自动校准"
                    % " / ".join(sorted(models)))
        elif len(models) > 1:
            self.status_var.set("检测到多种机型；请分批处理，或使用同机型 donor")
        else:
            model = next(iter(models))
            self.status_var.set(
                "检测到 %s；没有内置参数，请选择 donor（跨机型会自动校准）" % model)

    # ---------- options ----------
    def _donor_mode_changed(self) -> None:
        state = "normal" if self.donor_mode.get() == "file" else "disabled"
        self.donor_entry.configure(state=state)
        self.donor_browse.configure(state=state)

    def _out_mode_changed(self) -> None:
        state = "normal" if self.out_mode.get() == "dir" else "disabled"
        self.out_entry.configure(state=state)
        self.out_browse.configure(state=state)

    def _browse_donor(self) -> None:
        p = filedialog.askopenfilename(
            parent=self, title="选择同机型 donor DNG",
            filetypes=[("DNG 文件", "*.DNG *.dng"), ("所有文件", "*.*")])
        if p:
            self.donor_entry.delete(0, "end")
            self.donor_entry.insert(0, os.path.abspath(p))

    def _browse_out(self) -> None:
        p = filedialog.askdirectory(parent=self, title="选择输出目录")
        if p:
            self.out_entry.delete(0, "end")
            self.out_entry.insert(0, os.path.abspath(p))

    # ---------- start ----------
    def _start(self) -> None:
        if self.worker is not None and self.worker.is_alive():
            return
        if not self.targets:
            messagebox.showwarning("提示", "请先添加至少一个 DNG 文件。", parent=self)
            return

        donor_mode = self.donor_mode.get()
        donor_path = self.donor_entry.get().strip()
        if donor_mode == "file":
            if not donor_path or not os.path.isfile(donor_path):
                messagebox.showwarning("提示", "请选择一个有效的 donor DNG 文件。", parent=self)
                return

        out_mode = self.out_mode.get()
        out_dir = self.out_entry.get().strip() if out_mode == "dir" else None
        if out_mode == "dir":
            if not out_dir:
                messagebox.showwarning("提示", "请选择输出目录。", parent=self)
                return
            if not os.path.isdir(out_dir):
                if not messagebox.askyesno("创建目录", "输出目录不存在，是否创建？\n%s" % out_dir,
                                           parent=self):
                    return
                os.makedirs(out_dir, exist_ok=True)

        overwrite = bool(self.overwrite.get())
        if not overwrite:
            existing = [output_for(t, out_dir) for t in self.targets
                        if os.path.exists(output_for(t, out_dir))]
            if existing:
                messagebox.showerror(
                    "输出已存在",
                    "以下输出文件已存在，请勾选“覆盖已存在的输出文件”或更换输出目录：\n\n"
                    + "\n".join(existing[:8]) + ("\n..." if len(existing) > 8 else ""),
                    parent=self)
                return

        allow_cross = bool(self.allow_cross_model.get())

        self.start_btn.configure(state="disabled")
        self.open_btn.configure(state="disabled")
        self.progress.configure(maximum=len(self.targets), value=0)
        self.status_var.set("正在转换...")
        self._append_log("=" * 72)
        self._append_log("开始转换 %d 个文件" % len(self.targets))
        if allow_cross:
            self._append_log("注意：已勾选“允许其他跨机型 donor”；"
                             "目标有 0x021B 时仍会按机身校准，否则颜色只是近似。")

        args = (list(self.targets), donor_mode, donor_path, out_dir, overwrite,
                allow_cross)
        self.worker = threading.Thread(target=self._worker, args=args, daemon=True)
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
                self.queue.put(("log", "季节来源：内置 KF 四季参数（KF / K-70）"))
            elif donor_mode == "builtin_645d":
                donors["default"] = make_builtin_645d_donor()
                self.queue.put(("log", "季节来源：内置 645D 四季参数（PENTAX 645D）"))
            elif donor_mode == "builtin_k30":
                donors["k30"] = make_builtin_k30_donor()
                donors["k01"] = make_builtin_k01_donor()
                donors["k50"] = make_builtin_k50_donor()
                donors["q7"] = make_builtin_q7_donor()
                donors["mx1"] = make_builtin_mx1_donor()
                self.queue.put(("log", "季节来源：内置 KF→K-30 / K-01 / K-50 / Q7 / MX-1 四季参数"))
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
                        % (out, res.get("n_records", 0), res.get("new_block_count", 0))))
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
                    self.progress.configure(value=msg[1])
                    self.status_var.set("正在转换 %d / %d" % (msg[1], msg[2]))
                elif kind == "done":
                    self._on_done(msg[1], msg[2], msg[3])
        except queue.Empty:
            pass
        self.after(100, self._poll)

    def _append_log(self, text: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", "[%s] %s\n" % (time.strftime("%H:%M:%S"), text))
        self.log.see("end")
        self.log.configure(state="disabled")

    def _on_done(self, ok: int, fail: int, last_dir: str | None) -> None:
        self.start_btn.configure(state="normal")
        self.progress.configure(value=self.progress.cget("maximum"))
        self.status_var.set("完成：成功 %d，失败 %d" % (ok, fail))
        if last_dir:
            self.last_out_dir = last_dir
            self.open_btn.configure(state="normal")
        self._append_log("完成：成功 %d，失败 %d" % (ok, fail))
        if fail:
            messagebox.showwarning("转换完成", "成功 %d 个，失败 %d 个。\n请查看日志。" % (ok, fail),
                                   parent=self)
        else:
            messagebox.showinfo("转换完成", "成功处理 %d 个文件。" % ok, parent=self)

    def _open_out_dir(self) -> None:
        if self.last_out_dir and os.path.isdir(self.last_out_dir):
            os.startfile(self.last_out_dir)
        else:
            messagebox.showinfo("提示", "还没有输出目录。", parent=self)

    def _on_close(self) -> None:
        if self.worker is not None and self.worker.is_alive():
            if not messagebox.askyesno("退出", "正在转换，确定要退出吗？", parent=self):
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
