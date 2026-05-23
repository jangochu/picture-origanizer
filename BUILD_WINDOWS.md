# 在 Windows 上打包成 .exe

> PyInstaller 不支持跨平台编译，必须在 Windows 上执行打包流程。
> 当前在 macOS 上无法直接产出 Windows .exe。

## 前置准备

- Windows 10 或更高版本
- Python 3.10+ — [下载](https://www.python.org/downloads/windows/)，**安装时勾选 "Add Python to PATH"**

## 打包步骤

1. 把整个项目目录复制到 Windows 机器上（U 盘 / 网盘 / git clone 任选）
2. 在项目根目录双击 `build.bat`
3. 等待几分钟（首次会下载依赖 + exiftool，约 50MB）
4. 完成后输出在 `dist\` 文件夹：
   - `PhotoOrganizer.exe` —— 主程序，双击运行
   - `exiftool.exe` —— 必须和主程序在同一文件夹
   - `exiftool_files\` —— exiftool 的 Perl 运行时，同样必须保留
5. **分发时打包整个 `dist\` 文件夹**（不是单个 .exe）。少了任何一项 CR3/HEIC/视频的拍摄时间就读不出，文件会进 `unknown/`

## build.bat 做了什么

1. 检查 Python
2. 创建 `.venv` 虚拟环境并激活
3. `pip install -r requirements.txt pyinstaller`
4. 下载 exiftool Windows 版（约 5MB）解压到 `exiftool_bundle\`
5. 用 PyInstaller `--onefile` 打包主程序，再把 `exiftool.exe` + `exiftool_files\` 复制到 `dist\` 旁边

## 为什么 exiftool 不塞进 .exe 内部

现在的 exiftool Windows 包是「`exiftool.exe` 壳 + `exiftool_files\`（含 perl.exe + 一棵 Strawberry-Perl `lib\` 树）」。
PyInstaller 在 `--add-data` 时会做 binary/data 重分类，把 `exiftool_files\lib\auto\...` 里的 .dll 挪到别处，
破坏 Perl 期望的目录结构，运行时报 `Can't locate strict.pm in @INC`。
所以打包脚本改成把 exiftool 整棵子树原样放在 `dist\` 里 .exe 旁边，
`organize_photos.py` 的 `_find_exiftool()` 会自动找到。

## 体积参考

- `dist\PhotoOrganizer.exe` ≈ 40~50 MB（Python 运行时 + Pillow + customtkinter）
- `dist\exiftool.exe` + `dist\exiftool_files\` ≈ 25 MB
- 整个 `dist\` 文件夹 ≈ 60~75 MB

## 如果自动下载 exiftool 失败

公司网络/防火墙可能拦截 exiftool.org，可以手动操作：

1. 浏览器访问 https://exiftool.org/ 下载 **Windows Executable** 那个 zip
2. 解压到 `exiftool_bundle\`，使其包含：
   - `exiftool_bundle\exiftool.exe`（原文件名是 `exiftool(-k).exe`，把 `(-k)` 去掉重命名）
   - `exiftool_bundle\exiftool_files\`（同级目录，里面是 Perl 运行时和模块）
3. 再次运行 `build.bat`，它检测到已就绪会跳过下载

## 不想捆绑 exiftool？

编辑 `build.bat`，删掉 `--add-binary` 和 `--add-data` 那两行参数即可。
代价：CR3、HEIC、视频文件的拍摄时间会读不出来，全部进入 `unknown/`。
