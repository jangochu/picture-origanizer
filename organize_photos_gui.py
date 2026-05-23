#!/usr/bin/env python3
"""照片整理器 GUI（customtkinter）。

可选择源目录、目标目录，点击开始后在后台线程执行整理，
日志和进度实时刷新到界面上。打包成 Windows .exe 时，
会自动查找同目录或 PyInstaller 内置的 exiftool.exe。
"""

from __future__ import annotations

import queue
import sys
import threading
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk

from organize_photos import (
    EXIFTOOL_BIN,
    HAS_EXIFREAD,
    HAS_EXIFTOOL,
    HAS_HACHOIR,
    HAS_PIL,
    ProgressReporter,
    Stats,
    organize,
)


class _QueueReporter(ProgressReporter):
    """把进度事件塞到 queue，由主线程的 after() 取出更新 UI。"""

    def __init__(self, q: queue.Queue):
        self.q = q

    def on_start(self, total: int) -> None:
        self.q.put(("start", total))

    def on_file(self, idx, total, src, target, date, status) -> None:
        self.q.put(("file", idx, total, src, target, date, status))

    def on_error(self, src, exc) -> None:
        self.q.put(("error", src, str(exc)))

    def on_done(self, stats: Stats) -> None:
        self.q.put(("done", stats))


class PhotoOrganizerApp(ctk.CTk):
    POLL_MS = 80

    def __init__(self):
        super().__init__()
        ctk.set_appearance_mode("system")
        ctk.set_default_color_theme("blue")

        self.title("照片整理器")
        self.geometry("760x560")
        self.minsize(680, 480)

        self._queue: queue.Queue = queue.Queue()
        self._worker: threading.Thread | None = None
        self._total = 0

        self._build_ui()
        self._show_env_status()

    # ---------- UI ----------

    def _build_ui(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)

        # 路径选择区
        path_frame = ctk.CTkFrame(self)
        path_frame.grid(row=0, column=0, padx=16, pady=(16, 8), sticky="ew")
        path_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(path_frame, text="源目录:").grid(row=0, column=0, padx=(12, 8), pady=10, sticky="w")
        self.src_entry = ctk.CTkEntry(path_frame, placeholder_text="选择要整理的照片所在文件夹...")
        self.src_entry.grid(row=0, column=1, padx=4, pady=10, sticky="ew")
        ctk.CTkButton(path_frame, text="浏览...", width=90,
                      command=lambda: self._choose_dir(self.src_entry, "选择源目录")).grid(
            row=0, column=2, padx=(4, 12), pady=10)

        ctk.CTkLabel(path_frame, text="目标目录:").grid(row=1, column=0, padx=(12, 8), pady=10, sticky="w")
        self.dst_entry = ctk.CTkEntry(path_frame, placeholder_text="选择整理后照片归档到的文件夹...")
        self.dst_entry.grid(row=1, column=1, padx=4, pady=10, sticky="ew")
        ctk.CTkButton(path_frame, text="浏览...", width=90,
                      command=lambda: self._choose_dir(self.dst_entry, "选择目标目录")).grid(
            row=1, column=2, padx=(4, 12), pady=10)

        # 控制 + 进度
        ctrl_frame = ctk.CTkFrame(self)
        ctrl_frame.grid(row=1, column=0, padx=16, pady=8, sticky="ew")
        ctrl_frame.grid_columnconfigure(1, weight=1)

        self.start_btn = ctk.CTkButton(ctrl_frame, text="开始整理", width=120, command=self._on_start)
        self.start_btn.grid(row=0, column=0, padx=(12, 8), pady=12)

        self.progress = ctk.CTkProgressBar(ctrl_frame)
        self.progress.set(0)
        self.progress.grid(row=0, column=1, padx=8, pady=12, sticky="ew")

        self.status_label = ctk.CTkLabel(ctrl_frame, text="就绪", width=160, anchor="e")
        self.status_label.grid(row=0, column=2, padx=(8, 12), pady=12, sticky="e")

        # 环境状态条
        self.env_label = ctk.CTkLabel(self, text="", anchor="w", text_color=("gray30", "gray70"))
        self.env_label.grid(row=2, column=0, padx=20, pady=(0, 4), sticky="ew")

        # 日志区
        self.log_box = ctk.CTkTextbox(self, font=("Menlo", 12), wrap="none")
        self.log_box.grid(row=3, column=0, padx=16, pady=(4, 8), sticky="nsew")
        self.log_box.configure(state="disabled")

        # 统计条
        self.summary_label = ctk.CTkLabel(self, text="按日期归档: 0    未知: 0    跳过: 0    失败: 0",
                                          anchor="w")
        self.summary_label.grid(row=4, column=0, padx=20, pady=(0, 16), sticky="ew")

    def _show_env_status(self) -> None:
        parts = []
        parts.append(("Pillow ✓" if HAS_PIL else "Pillow ✗"))
        parts.append(("exifread ✓" if HAS_EXIFREAD else "exifread ✗"))
        parts.append(("hachoir ✓" if HAS_HACHOIR else "hachoir ✗"))
        parts.append(("exiftool ✓" if HAS_EXIFTOOL else "exiftool ✗"))
        text = "依赖检测: " + "  ".join(parts)
        if HAS_EXIFTOOL:
            text += f"   (exiftool: {EXIFTOOL_BIN})"
        self.env_label.configure(text=text)

    def _choose_dir(self, entry: ctk.CTkEntry, title: str) -> None:
        initial = entry.get().strip() or str(Path.home())
        d = filedialog.askdirectory(title=title, initialdir=initial)
        if d:
            entry.delete(0, tk.END)
            entry.insert(0, d)

    # ---------- 日志 ----------

    def _append_log(self, text: str) -> None:
        self.log_box.configure(state="normal")
        self.log_box.insert("end", text + "\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def _clear_log(self) -> None:
        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.configure(state="disabled")

    # ---------- 启动整理 ----------

    def _on_start(self) -> None:
        if self._worker and self._worker.is_alive():
            return

        src_raw = self.src_entry.get().strip()
        dst_raw = self.dst_entry.get().strip()
        if not src_raw or not dst_raw:
            messagebox.showwarning("缺少路径", "请选择源目录和目标目录。")
            return

        src = Path(src_raw).expanduser().resolve()
        dst = Path(dst_raw).expanduser().resolve()

        if not src.is_dir():
            messagebox.showerror("路径错误", f"源目录不存在或不是文件夹:\n{src}")
            return
        if dst == src or str(dst).startswith(str(src) + "/") or str(dst).startswith(str(src) + "\\"):
            messagebox.showerror("路径错误", "目标目录不能与源目录相同或位于源目录内部。")
            return

        self._clear_log()
        self.progress.set(0)
        self.summary_label.configure(text="正在扫描...")
        self.status_label.configure(text="处理中...")
        self.start_btn.configure(state="disabled")
        self._append_log(f"源:   {src}")
        self._append_log(f"目标: {dst}")
        self._append_log(f"开始: {datetime.now().strftime('%H:%M:%S')}")
        self._append_log("-" * 70)

        reporter = _QueueReporter(self._queue)
        self._worker = threading.Thread(
            target=self._run_organize, args=(src, dst, reporter), daemon=True
        )
        self._worker.start()
        self.after(self.POLL_MS, self._poll_queue)

    def _run_organize(self, src: Path, dst: Path, reporter: _QueueReporter) -> None:
        try:
            organize(src, dst, reporter)
        except Exception as e:
            self._queue.put(("fatal", str(e)))

    # ---------- 队列事件 ----------

    def _poll_queue(self) -> None:
        drained = False
        try:
            while True:
                event = self._queue.get_nowait()
                self._handle_event(event)
                drained = True
        except queue.Empty:
            pass

        if self._worker and self._worker.is_alive():
            self.after(self.POLL_MS, self._poll_queue)
        elif drained:
            # 兜底一次，把最后残留的事件取完
            self.after(self.POLL_MS, self._poll_queue)

    def _handle_event(self, event: tuple) -> None:
        kind = event[0]
        if kind == "start":
            self._total = event[1]
            self._append_log(f"共发现 {self._total} 个候选文件。")
            if self._total == 0:
                self.progress.set(1.0)
        elif kind == "file":
            _, idx, total, src, target, date, status = event
            tag = date.strftime("%Y-%m-%d") if date else ("unknown" if status == "unknown" else "skip")
            self._append_log(f"[{idx}/{total}] {tag}  {src.name}  →  {target}")
            if total > 0:
                self.progress.set(idx / total)
            self.status_label.configure(text=f"{idx}/{total}")
        elif kind == "error":
            _, src, msg = event
            self._append_log(f"  ✗ 失败: {src}  ({msg})")
        elif kind == "done":
            stats: Stats = event[1]
            self._append_log("-" * 70)
            self._append_log(
                f"完成。归档 {stats.moved}  未知 {stats.unknown}  跳过 {stats.skipped}  失败 {stats.failed}"
            )
            self._append_log(
                f"日期来源: Pillow={stats.by_source['pillow']}, "
                f"exifread={stats.by_source['exifread']}, "
                f"hachoir={stats.by_source['hachoir']}, "
                f"exiftool={stats.by_source['exiftool']}, "
                f"无={stats.by_source['none']}"
            )
            self.summary_label.configure(
                text=(f"按日期归档: {stats.moved}    未知: {stats.unknown}    "
                      f"跳过: {stats.skipped}    失败: {stats.failed}")
            )
            self.status_label.configure(text="完成")
            self.start_btn.configure(state="normal")
            self.progress.set(1.0)
        elif kind == "fatal":
            _, msg = event
            self._append_log(f"\n[致命错误] {msg}")
            self.status_label.configure(text="错误")
            self.start_btn.configure(state="normal")
            messagebox.showerror("整理失败", msg)


def main() -> int:
    app = PhotoOrganizerApp()
    app.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
