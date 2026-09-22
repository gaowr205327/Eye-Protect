# 👁 护眼助手（Eye-Protect）

一款运行在 **Windows 10/11** 上的桌面小工具，帮助长时间面对电脑的办公人群 **定时休息眼睛**，并提供**每日上下班打卡提醒**。完全离线运行、不联网，绿色免安装。

界面采用 **星露谷像素风**（Stardew Valley style）—— 全部组件由程序化 2D 像素绘制，**零外部图片素材**，搭配开源像素字体 **Fusion Pixel 12px**（OFL 1.1，可商用）。

## ✨ 功能特性

- **定时休息提醒**：按设定间隔（1~180 分钟）循环在屏幕正中央弹出像素木牌提醒窗
- **上下班打卡提醒**：每日 4 次（上班 / 午休 / 午休结束 / 下班），可逐条开关、自定义时刻与提示词
- **提醒文案自定义**：支持多行多段，顺序轮换或随机展示
- **按钮文字自定义**：休息弹窗与打卡弹窗按钮文案各自独立设置
- **系统托盘常驻**：右键菜单 打开设置 / 立即提醒 / 退出，关闭窗口不退出程序
- **开机自启**：可选，写 HKCU 注册表，不需要管理员权限
- **单实例运行**：防止重复启动
- **自适应分辨率/DPI**：弹窗始终居中，兼容单/双屏切换
- **配置自动保存**：存于 `%APPDATA%\EyeReminder\config.json`，不污染 exe 目录

## 🖥 界面一览

像素木牌招牌、羊皮纸钉木框弹窗、抖动渐变草地装饰、16px 手绘图标等，详见 `docs/preview/` 截图。

## 📦 环境依赖

- Python 3.13+（需带 tkinter 的系统 Python）
- 运行依赖：`pystray`、`Pillow`
- 打包依赖：`pyinstaller`

```bash
pip install -r requirements.txt
```

## 🚀 运行

```bash
python src/main.py
```

## 🧱 打包

使用 `build.bat` 一键打包：

```bat
build.bat                :: 单文件版 -> dist\护眼助手.exe
build.bat --onedir       :: 目录版   -> dist\护眼助手\护眼助手.exe
build.bat --no-pause     :: 自动化调用，结束不暂停
```

> 注意：必须使用带 tkinter 的解释器（如 `C:\Program Files\Python314\python.exe`）。
> WorkBuddy 托管 Python 不含 tkinter，用它打出的 exe 启动即崩。

## 📁 项目结构

```
├── src/            # 源代码
│   ├── main.py     # 入口：单实例检查、启动
│   ├── app.py      # 应用主控制器
│   ├── config.py   # 配置读写（JSON）
│   ├── scheduler.py# 定时调度器
│   ├── settings_window.py # 设置主窗口（三标签页）
│   ├── popup.py    # 屏幕中央提醒弹窗（像素木牌样式）
│   ├── theme.py    # 配色表（单套经典蓝 + 像素调色板）
│   ├── pixelart.py # 像素绘制引擎（全组件唯一绘制出口）
│   ├── fonts.py    # 像素字体加载
│   ├── tray.py     # 系统托盘
│   └── icons.py    # 程序内图标
├── assets/
│   └── fonts/      # 像素字体（Fusion Pixel 12px）——唯一随包分发的文件资源
├── scripts/        # 开发辅助（图标生成 / 各项自测）
├── docs/           # 需求文档、构建指令、界面截图
├── requirements.txt
└── build.bat       # 一键打包脚本
```

## 📄 文档

- [需求文档](docs/需求文档.md) —— 完整功能需求、技术方案与验收标准（v1.7）
- [构建指令](docs/构建Prompt.md)

## 📜 字体许可

- 像素字体 **Fusion Pixel 12px** 采用 [SIL Open Font License 1.1](assets/fonts/OFL.txt)，可商用。
