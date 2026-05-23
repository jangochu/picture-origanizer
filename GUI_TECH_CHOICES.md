# 桌面 GUI 小工具技术选型

> 场景：给不会用命令行的客户做小工具，主要 Windows，也可能要兼顾 macOS / Linux。
> 本项目本身用方案 1（Python + customtkinter + PyInstaller）落地，这里把当时考虑过的几套方案和取舍记录下来，方便下次新工具直接选型。

## 方案 1：Python + Tk/customtkinter + PyInstaller

本项目用的就是这套。

- **优点**
  - Python 生态最丰富，Pillow / exifread / hachoir / 调子进程跑 exiftool 这种「读元数据 / 处理文件」的活很顺手
  - 学习成本最低，写 GUI 不用换语言
  - `customtkinter` 比原生 Tk 好看不少，能糊出能看的现代界面
- **缺点**
  - PyInstaller **不支持跨平台编译**，每个目标 OS 都得在对应机器上各打一次包
  - 带原生依赖（exiftool 这种 Perl 运行时 / ffmpeg 之类）打包坑很多，本项目折腾过：PyInstaller 的 binary/data 重分类会破坏 Perl 的 `lib\` 目录结构，最后只能 sidecar（详见 [BUILD_WINDOWS.md](BUILD_WINDOWS.md)）
  - 产物体积 40~80 MB（Python 运行时 + GUI 库），单个工具不算大，多个工具叠起来用户会嫌
  - UI 风格永远「能用但不漂亮」，没法跟现代设计语言对齐
- **适合**
  - 内部小工具 / 一次性任务 / 自用
  - 用户能接受简陋 UI
  - 已经在写 Python 不想换栈

## 方案 2：Tauri（Rust 后端 + Web 前端 + 系统 Webview）

现代轻量桌面应用的事实标准之一。

- **优点**
  - 产物 5~15 MB，比 Electron 小一个数量级
  - UI 用 HTML/CSS + 任意前端框架（React/Vue/Svelte 都行），外观可以做到跟现代桌面应用持平甚至更好
  - 权限模型清晰，安全性好
  - 调用本地子进程很方便（像本项目「调 exiftool 处理文件」这种模式天生契合）
  - 跨平台 API 抽象到位
- **缺点**
  - 需要会一点 Rust（前端可以全 JS，但桥接和命令注册得写 Rust）
  - 还是要在每个目标 OS 上各打一次包（虽然有 GitHub Actions 模板）
  - 依赖系统 Webview（Windows 上是 WebView2，Win10 1803 以下用户要单独装）
- **适合**
  - 想做得稍微「像个产品」、可能给多个客户用
  - 团队里能凑出一个会 Rust 或愿意学的人
  - 未来要长期维护、加功能

## 方案 3：Web 应用（直接浏览器跑）

- **优点**
  - 零安装、零 OS 适配、改完所有人立刻用上
  - 任何平台都能跑（包括手机平板）
  - 部署 / 升级最省心
- **缺点**
  - 本地文件 API 受沙盒限制：Chrome / Edge 的 File System Access API 还能用，Safari 支持很弱，Firefox 部分支持
  - 用户的文件要么上传到你服务器（隐私 / 带宽 / 成本），要么用 File System Access API 但有兼容性问题
  - 需要服务器和域名（即使是静态 SPA 也需要托管）
  - 没法做需要长时间后台运行、调用系统命令的功能
- **适合**
  - 纯数据处理 / 文本处理 / 在线生成
  - 不需要批量操作本地文件
  - 用户分布广、Windows + macOS + 移动端都有

## 其他可选项（一般不建议优先考虑）

- **Electron**：跟 Tauri 同生态位但产物 100 MB+ 起步，每个应用都打包一份 Chromium，除非团队完全 JS 栈且对体积无感，否则被 Tauri 全方位替代
- **Flutter Desktop**：一套 Dart 代码出 Win/Mac/Linux/iOS/Android 全平台，UI 漂亮，但 Dart 生态相对小、桌面端 native 集成不如 Tauri / Electron 成熟。如果团队已经做 Flutter 移动端可以顺手用
- **.NET + Avalonia / WPF**：Windows 原生体验最好（WPF）或跨平台（Avalonia），但 .NET 生态对个人开发者门槛偏高，且 macOS / Linux 体验略尴尬
- **Go + Fyne / Wails**：Go 跨编译能力强，Fyne 是 Go 原生 GUI（控件略土），Wails 是 Go + WebView（类 Tauri）。如果团队是 Go 栈可以考虑

## 怎么选

- **就这一个工具、客户不多、不打算长期维护** → 方案 1（Python+PyInstaller），已投入的学习成本不浪费
- **以后还会做几个类似工具、想要更专业的观感** → 方案 2（Tauri），投入产出比最高
- **文件处理逻辑能上云、用户跨设备** → 方案 3（Web 应用），省下所有打包分发的事

本项目最初选方案 1 是因为完全 Python 栈、一次性工具、能接受 sidecar 分发。如果以后要做第二个第三个类似工具，建议升到 Tauri。
