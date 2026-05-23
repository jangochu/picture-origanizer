#!/usr/bin/env python3
"""按 EXIF 拍摄日期把照片/视频整理成 YYYY-MM-DD 目录结构。

交互式询问源目录和目标目录，递归扫描源目录，根据每个文件的拍摄日期
将其移动到 `<dst>/YYYY-MM-DD/` 下。无法读取拍摄日期的文件移动到
`<dst>/unknown/`。目标位置存在同名文件时，自动在文件名后追加 `_N` 序号。

依赖（按需安装，缺失时对应能力会被跳过）:
    pip install Pillow exifread hachoir
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".heic", ".heif", ".webp", ".gif", ".bmp", ".tif", ".tiff"}
RAW_EXTS = {".cr2", ".cr3", ".nef", ".arw", ".dng", ".raf", ".orf", ".rw2", ".pef", ".srw"}
VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".m4v", ".3gp", ".mts", ".m2ts", ".wmv", ".flv"}
SUPPORTED_EXTS = IMAGE_EXTS | RAW_EXTS | VIDEO_EXTS

# 可选依赖（缺失时退化）
try:
    from PIL import Image, ExifTags
    _PIL_DATE_TAGS = {tag_id for tag_id, name in ExifTags.TAGS.items()
                      if name in ("DateTimeOriginal", "DateTimeDigitized", "DateTime")}
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

try:
    import exifread
    HAS_EXIFREAD = True
except ImportError:
    HAS_EXIFREAD = False

try:
    from hachoir.parser import createParser
    from hachoir.metadata import extractMetadata
    HAS_HACHOIR = True
except ImportError:
    HAS_HACHOIR = False

def _find_exiftool() -> str | None:
    """查找 exiftool 可执行文件：
    1) PyInstaller 打包后内置的临时解压目录 (_MEIPASS)
    2) 与主程序（.exe）同目录
    3) 系统 PATH
    """
    candidates: list[Path] = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates += [Path(meipass) / "exiftool.exe", Path(meipass) / "exiftool"]
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).parent
        candidates += [exe_dir / "exiftool.exe", exe_dir / "exiftool"]
    for c in candidates:
        if c.exists() and os.access(c, os.X_OK if os.name != "nt" else os.F_OK):
            return str(c)
    return shutil.which("exiftool")


EXIFTOOL_BIN = _find_exiftool()
HAS_EXIFTOOL = EXIFTOOL_BIN is not None

# 记录最近一次 exiftool 调用的失败原因（subprocess 非零退出/异常/无可用时间标签），
# organize() 在该文件最终落入 unknown/ 时会播报出来，方便排查 bundling 之类静默失败。
_EXIFTOOL_LAST_ERROR: str | None = None


# 常见 EXIF 日期格式: "2024:03:15 14:23:01"
_DATE_PATTERNS = (
    "%Y:%m:%d %H:%M:%S",
    "%Y-%m-%d %H:%M:%S",
    "%Y:%m:%d",
    "%Y-%m-%d",
)


@dataclass
class Stats:
    moved: int = 0
    unknown: int = 0
    skipped: int = 0
    failed: int = 0
    by_source: dict = field(default_factory=lambda: {
        "pillow": 0, "exifread": 0, "hachoir": 0, "exiftool": 0, "none": 0
    })


def parse_exif_date(raw: str) -> datetime | None:
    if not raw:
        return None
    raw = raw.strip().strip("\x00")
    for fmt in _DATE_PATTERNS:
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    # 兜底：抓取 YYYY[-:/]MM[-:/]DD
    m = re.search(r"(\d{4})[:\-/](\d{1,2})[:\-/](\d{1,2})", raw)
    if m:
        try:
            return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    return None


def get_date_via_pillow(path: Path) -> datetime | None:
    if not HAS_PIL:
        return None
    try:
        with Image.open(path) as img:
            exif = img.getexif()
            if not exif:
                return None
            for tag_id in (36867, 36868, 306):  # DateTimeOriginal, DateTimeDigitized, DateTime
                val = exif.get(tag_id)
                if val:
                    parsed = parse_exif_date(str(val))
                    if parsed:
                        return parsed
    except Exception:
        return None
    return None


def get_date_via_exifread(path: Path) -> datetime | None:
    if not HAS_EXIFREAD:
        return None
    try:
        with open(path, "rb") as f:
            tags = exifread.process_file(f, details=False, stop_tag="EXIF DateTimeOriginal")
        for key in ("EXIF DateTimeOriginal", "EXIF DateTimeDigitized", "Image DateTime"):
            if key in tags:
                parsed = parse_exif_date(str(tags[key]))
                if parsed:
                    return parsed
    except Exception:
        return None
    return None


def get_date_via_exiftool(path: Path) -> datetime | None:
    """通用兜底：调用 exiftool 读取多个时间字段，覆盖 CR3/HEIC/视频 等绝大多数格式。"""
    global _EXIFTOOL_LAST_ERROR
    _EXIFTOOL_LAST_ERROR = None
    if not HAS_EXIFTOOL:
        _EXIFTOOL_LAST_ERROR = "exiftool 不可用（未找到可执行文件）"
        return None
    tags = (
        "-DateTimeOriginal", "-CreateDate", "-MediaCreateDate",
        "-TrackCreateDate", "-CreationDate", "-ModifyDate",
    )
    try:
        # -s -s -s = 极简输出（只值不带标签）；-d 指定格式
        result = subprocess.run(
            [EXIFTOOL_BIN, "-s", "-s", "-s", "-d", "%Y:%m:%d %H:%M:%S", *tags, str(path)],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode != 0:
            _EXIFTOOL_LAST_ERROR = (
                f"exiftool 退出码 {result.returncode}; "
                f"stderr={result.stderr.strip()[:300]!r}; "
                f"stdout={result.stdout.strip()[:300]!r}"
            )
            return None
        for line in result.stdout.splitlines():
            line = line.strip()
            if not line or line.startswith("0000"):  # 过滤无效时间戳
                continue
            parsed = parse_exif_date(line)
            if parsed and parsed.year > 1970:
                return parsed
        _EXIFTOOL_LAST_ERROR = (
            f"exiftool 返回 0 但解析不到有效时间; "
            f"stdout={result.stdout.strip()[:300]!r}; "
            f"stderr={result.stderr.strip()[:200]!r}"
        )
    except (subprocess.TimeoutExpired, OSError) as e:
        _EXIFTOOL_LAST_ERROR = f"exiftool 调用异常: {e!r}"
        return None
    return None


def get_date_via_hachoir(path: Path) -> datetime | None:
    if not HAS_HACHOIR:
        return None
    try:
        parser = createParser(str(path))
        if not parser:
            return None
        with parser:
            meta = extractMetadata(parser)
        if not meta:
            return None
        for key in ("creation_date", "last_modification"):
            val = meta.get(key) if meta.has(key) else None
            if isinstance(val, datetime):
                return val
            if val:
                parsed = parse_exif_date(str(val))
                if parsed:
                    return parsed
    except Exception:
        return None
    return None


def get_shooting_date(path: Path, ext: str, stats: Stats) -> datetime | None:
    if ext in IMAGE_EXTS:
        d = get_date_via_pillow(path)
        if d:
            stats.by_source["pillow"] += 1
            return d
        d = get_date_via_exifread(path)
        if d:
            stats.by_source["exifread"] += 1
            return d
    elif ext in RAW_EXTS:
        d = get_date_via_exifread(path)
        if d:
            stats.by_source["exifread"] += 1
            return d
    elif ext in VIDEO_EXTS:
        d = get_date_via_hachoir(path)
        if d:
            stats.by_source["hachoir"] += 1
            return d

    # 通用兜底：exiftool 覆盖 CR3、HEIC、各种视频格式等专用解析器搞不定的情况
    d = get_date_via_exiftool(path)
    if d:
        stats.by_source["exiftool"] += 1
        return d

    stats.by_source["none"] += 1
    return None


def resolve_target(dst_root: Path, date: datetime | None, filename: str) -> Path:
    if date is None:
        target_dir = dst_root / "unknown"
    else:
        target_dir = dst_root / f"{date.year:04d}-{date.month:02d}-{date.day:02d}"
    target_dir.mkdir(parents=True, exist_ok=True)

    candidate = target_dir / filename
    if not candidate.exists():
        return candidate
    stem, suffix = candidate.stem, candidate.suffix
    n = 1
    while True:
        candidate = target_dir / f"{stem}_{n}{suffix}"
        if not candidate.exists():
            return candidate
        n += 1


def prompt_path(label: str, must_exist: bool) -> Path:
    while True:
        raw = input(f"{label}: ").strip()
        if not raw:
            print("  路径不能为空，请重新输入。")
            continue
        # 展开 ~ 和环境变量
        path = Path(os.path.expandvars(os.path.expanduser(raw))).resolve()
        if must_exist and not path.is_dir():
            print(f"  目录不存在或不是文件夹: {path}")
            continue
        return path


def iter_media_files(src: Path):
    for root, _, files in os.walk(src):
        for name in files:
            p = Path(root) / name
            if p.suffix.lower() in SUPPORTED_EXTS:
                yield p


class ProgressReporter:
    """组织过程的事件回调。CLI/GUI 各自实现一个子类即可复用核心逻辑。"""

    def on_start(self, total: int) -> None: ...
    def on_file(
        self,
        idx: int,
        total: int,
        src: Path,
        target: Path,
        date: datetime | None,
        status: str,  # "moved" | "unknown" | "skipped"
    ) -> None: ...
    def on_error(self, src: Path, exc: Exception) -> None: ...
    def on_done(self, stats: "Stats") -> None: ...


def organize(src: Path, dst: Path, reporter: ProgressReporter | None = None) -> Stats:
    """递归扫描 src 下的媒体文件，按拍摄日期 move 到 dst/YYYY-MM-DD/。

    返回 Stats。所有进度通过 reporter 上报，方便 GUI 复用。
    """
    reporter = reporter or ProgressReporter()
    stats = Stats()

    if dst == src or str(dst).startswith(str(src) + os.sep):
        raise ValueError("目标目录不能与源目录相同或位于源目录内部。")

    dst.mkdir(parents=True, exist_ok=True)
    files = list(iter_media_files(src))
    total = len(files)
    reporter.on_start(total)

    for idx, src_path in enumerate(files, 1):
        ext = src_path.suffix.lower()
        try:
            date = get_shooting_date(src_path, ext, stats)
            target = resolve_target(dst, date, src_path.name)

            if target.resolve() == src_path.resolve():
                stats.skipped += 1
                reporter.on_file(idx, total, src_path, target, date, "skipped")
                continue

            shutil.move(str(src_path), str(target))
            if date is None:
                stats.unknown += 1
                reporter.on_file(idx, total, src_path, target, date, "unknown")
                # 该文件最终落入 unknown/，如果是 exiftool 失败导致，把原因播报出来，
                # 否则用户只能看到一个孤零零的 unknown，没法排查（CR3/HEIC/视频之类一般都是 exiftool 兜底的）。
                if _EXIFTOOL_LAST_ERROR:
                    reporter.on_error(src_path, RuntimeError(f"[exiftool] {_EXIFTOOL_LAST_ERROR}"))
            else:
                stats.moved += 1
                reporter.on_file(idx, total, src_path, target, date, "moved")
        except Exception as e:
            stats.failed += 1
            reporter.on_error(src_path, e)

    reporter.on_done(stats)
    return stats


def print_env_hint() -> None:
    missing = []
    if not HAS_PIL:
        missing.append("Pillow（用于读取 JPG/PNG/HEIC 等图片 EXIF）")
    if not HAS_EXIFREAD:
        missing.append("exifread（用于 RAW 格式，以及作为图片 EXIF 的备选解析器）")
    if not HAS_HACHOIR:
        missing.append("hachoir（用于读取视频元数据中的拍摄时间）")
    if not HAS_EXIFTOOL:
        missing.append("exiftool（通用兜底，强烈推荐，可解析 CR3/HEIC/各种视频。brew install exiftool）")
    if missing:
        print("提示：以下依赖未安装，对应能力会缺失，部分文件可能进入 unknown/。")
        for m in missing:
            print(f"  - {m}")
        print("  安装命令: pip install Pillow exifread hachoir   &&   brew install exiftool")
        print()


class _CLIReporter(ProgressReporter):
    def on_start(self, total: int) -> None:
        if total == 0:
            print("未发现可处理的文件。")
        else:
            print(f"共发现 {total} 个候选文件。\n")

    def on_file(self, idx, total, src, target, date, status) -> None:
        if status == "skipped":
            print(f"[{idx}/{total}] 跳过（源即目标）: {src}")
            return
        tag = date.strftime("%Y-%m-%d") if date else "unknown"
        print(f"[{idx}/{total}] {tag}  {src.name}  →  {target}")

    def on_error(self, src, exc) -> None:
        print(f"失败: {src}  ({exc})", file=sys.stderr)

    def on_done(self, stats) -> None:
        print("\n" + "=" * 60)
        print("完成统计")
        print(f"  按日期归档: {stats.moved}")
        print(f"  未知日期(unknown/): {stats.unknown}")
        print(f"  跳过: {stats.skipped}")
        print(f"  失败: {stats.failed}")
        print(f"  日期来源 — Pillow: {stats.by_source['pillow']}, "
              f"exifread: {stats.by_source['exifread']}, "
              f"hachoir: {stats.by_source['hachoir']}, "
              f"exiftool: {stats.by_source['exiftool']}, "
              f"无: {stats.by_source['none']}")
        print("=" * 60)


def main() -> int:
    print("=" * 60)
    print("照片整理脚本：按 EXIF 拍摄日期归档到 YYYY-MM-DD 目录")
    print("=" * 60)
    print_env_hint()

    src = prompt_path("源目录（递归扫描）", must_exist=True)
    dst = prompt_path("目标目录（不存在会自动创建）", must_exist=False)

    print(f"\n源: {src}\n目标: {dst}\n开始扫描...\n")
    try:
        stats = organize(src, dst, _CLIReporter())
    except ValueError as e:
        print(f"错误：{e}")
        return 2
    return 0 if stats.failed == 0 else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n已中断。", file=sys.stderr)
        sys.exit(130)
