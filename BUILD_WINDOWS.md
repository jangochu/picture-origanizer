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
4. 完成后输出在 `dist\PhotoOrganizer.exe`，单文件、可直接双击运行

## build.bat 做了什么

1. 检查 Python
2. 创建 `.venv` 虚拟环境并激活
3. `pip install -r requirements.txt pyinstaller`
4. 下载 exiftool Windows 版（约 5MB）解压到 `exiftool_bundle\`
5. 用 PyInstaller 单文件模式打包，`--add-binary` 把 exiftool 一起塞进 .exe

## 体积参考

- `PhotoOrganizer.exe` ≈ 40~60 MB（包含 Python 运行时 + Pillow + customtkinter + exiftool）

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
