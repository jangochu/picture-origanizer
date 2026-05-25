# 照片整理器 (Photo Organizer)

按 EXIF 拍摄日期把照片 / RAW / 视频自动归档到 `YYYY-MM-DD/` 目录的小工具。
提供 **命令行** 与 **桌面 GUI** 两种用法，可在 Windows 上打包成单文件 `.exe` 分发给不会用命令行的用户。

读不出拍摄日期的文件会被丢到 `unknown/`，目标位置同名文件自动追加 `_N` 序号，不会覆盖。

## 功能

- 递归扫描源目录，按拍摄日期 **移动** 到 `<目标>/YYYY-MM-DD/<原文件名>`
- 多解析器接力，最大限度读到拍摄时间：
  - `Pillow` — 图片 EXIF（JPG / PNG / HEIC …）
  - `exifread` — RAW（CR2 / NEF / ARW / DNG …）
  - `hachoir` — 视频元数据（MP4 / MOV / MKV …）
  - `exiftool` — **通用兜底**，覆盖 CR3 / HEIC / 各类视频等其他库搞不定的格式（强烈推荐）
- 同名文件自动追加 `_1`、`_2` …，绝不覆盖
- 拒绝把目标目录设在源目录内部（防止扫描时自食其尾）
- GUI 实时显示进度、日志、依赖检测状态
- exiftool 失败时把 stderr 播报出来，不会静默吞错

## 支持的文件格式

| 类型 | 扩展名 |
| --- | --- |
| 图片 | `.jpg .jpeg .png .heic .heif .webp .gif .bmp .tif .tiff` |
| RAW  | `.cr2 .cr3 .nef .arw .dng .raf .orf .rw2 .pef .srw` |
| 视频 | `.mp4 .mov .avi .mkv .m4v .3gp .mts .m2ts .wmv .flv` |

## 安装

```bash
pip install -r requirements.txt
# 强烈建议同时装 exiftool（CR3 / HEIC / 视频的兜底解析器）
brew install exiftool         # macOS
sudo apt install libimage-exiftool-perl   # Debian/Ubuntu
# Windows: 见下面的「打包成 Windows .exe」一节
```

`requirements.txt` 包含 `Pillow`、`exifread`、`hachoir`、`customtkinter`，缺哪个对应能力会退化，但程序仍可运行（启动时会提示）。

## 使用方式

### 1. 命令行

```bash
python organize_photos.py
```

按提示输入源目录和目标目录即可。完成后打印按日期归档 / unknown / 跳过 / 失败的统计与日期来源分布。

### 2. 桌面 GUI

```bash
python organize_photos_gui.py
```

选源目录、目标目录，点「开始整理」。底部状态条会标出每个依赖是否就绪、exiftool 路径等信息。

### 3. 作为库调用

```python
from pathlib import Path
from organize_photos import organize, ProgressReporter

class MyReporter(ProgressReporter):
    def on_file(self, idx, total, src, target, date, status):
        print(f"[{idx}/{total}] {src.name} → {target}")

stats = organize(Path("/in"), Path("/out"), MyReporter())
print(stats.moved, stats.unknown, stats.failed)
```

`ProgressReporter` 暴露 `on_start / on_file / on_error / on_done` 四个回调，CLI 和 GUI 都基于它实现。

## 打包成 Windows .exe

在 Windows 机器上双击 `build.bat`，产物在 `dist\`：

- `PhotoOrganizer.exe` —— 主程序
- `exiftool.exe` + `exiftool_files\` —— **sidecar，必须和 .exe 在同一文件夹**

> exiftool 没有塞进 .exe 内部 —— 它的 Windows 包是 `exiftool.exe` 壳 + `exiftool_files\`（含 perl.exe 与一棵 Strawberry-Perl `lib\` 树），PyInstaller 的 binary/data 重分类会破坏 Perl 的 `@INC` 目录结构，运行时报 `Can't locate strict.pm`。所以采用 sidecar 模式，由 `_find_exiftool()` 在 `_MEIPASS` / .exe 同目录 / PATH 中查找。

分发时请打包整个 `dist\` 文件夹（zip 后发送），少了 `exiftool.exe` 或 `exiftool_files\` 都会导致 CR3 / HEIC / 视频进 `unknown/`。

详细步骤、体积参考、网络受限时的手动准备方案见 [BUILD_WINDOWS.md](BUILD_WINDOWS.md)。

## 项目结构

```
.
├── organize_photos.py       # 核心：解析 + 归档逻辑 + CLI
├── organize_photos_gui.py   # customtkinter GUI
├── requirements.txt         # Python 依赖
├── build.bat                # Windows 一键打包脚本
├── BUILD_WINDOWS.md         # Windows 打包详细说明
└── GUI_TECH_CHOICES.md      # 桌面小工具技术选型记录（Python/Tauri/Web 取舍）
```

## 设计说明

- **多解析器接力**：图片优先用 Pillow，RAW 用 exifread，视频用 hachoir，最后无论何种格式都让 exiftool 兜底。`Stats.by_source` 会统计每个解析器的命中数。
- **沉默失败保护**：exiftool 调用失败（subprocess 非零退出、解析不到时间、超时等）时，错误原因写入模块全局变量 `_EXIFTOOL_LAST_ERROR`，文件最终落入 `unknown/` 时通过 reporter 一并播报，方便排查打包问题。
- **GUI / CLI 解耦**：核心 `organize()` 只依赖 `ProgressReporter`，GUI 用线程跑、通过 `queue` 把事件回主线程；CLI 直接同步打印。

## 已知限制

- macOS 上无法跨平台打 Windows `.exe`，需在 Windows 机器上跑 `build.bat`
- 当前只「移动」不支持「复制」（如需保留原文件请先备份）
- 跨磁盘 / 跨卷移动会退化为复制 + 删除，速度比同卷 rename 慢
