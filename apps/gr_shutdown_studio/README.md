# GR Shutdown Studio

A desktop app for preparing and verifying custom Ricoh GR shutdown images on macOS and Windows.

## Workflow

1. Choose the camera family, select the firmware shown in its menu, and create a backup folder on your computer. Select the FAT32 SD card when prompted.
2. Prepare a small SD copy check. Enable Script from the camera factory menu and run once.
3. Reconnect the card. The app verifies the copy and prepares the backup script.
4. Run the backup once, reconnect, and save the original on your computer.
5. Choose an image, crop or fit it, and preview the encoded 720×480 JPEG.
6. Prepare installation, run the camera script, and reconnect for full readback verification. Urban requires a temporary-image stage first.
7. Check the actual shutdown screen and disable Script. Keep the session to restore later. Urban restoration first exports and verifies its internal original before preparing the restore script.

The sidebar tracks three stages: **Back up original → Choose image → Install & verify**. Each page shows only the current controls. Camera tasks appear as numbered instructions; the bottom-right button advances the current step. Camera family and framing use segmented choices. The firmware popup offers known versions and an “Other version” entry; changing camera family clears the selection. Language options remain visible in Settings.

Secondary actions use compact, borderless sidebar rows with line icons; primary actions stay in the footer.

Home: **Settings / 设置**. Settings dialog: **Language / 语言**. Both labels stay bilingual, with English and Chinese interfaces available.

## Camera support

**Compatibility testing** accepts all ten catalog editions and other menu firmware versions. It creates a local research record, inspects existing update headers and optionally preserves an already extracted original in two verified computer copies. Reports omit pictures, EXIF, paths and body identifiers. This intake generates no camera scripts. GR IV's main workflow also offers 1.04 and 1.03 as backup tests; unqualified backups end with report export instead of image installation.

See the [community testing procedure](../../docs/extensions/community-compatibility-testing.md) for distributing the preview and adapting cameras the maintainer does not own. Unknown III / IIIx editions still need dedicated, reviewed backup methods.

- GR IV / HDF 1.11: automatic model selection during backup, equal-length JPEG encoding, one-shot installation and restoration. Monochrome identification is known but its evidence did not record firmware; installation is currently disabled.
- GR IIIx Urban Edition 1.60: verified original profile only; temporary-image generation, complete readbacks between stages, internal-backup restoration. Exact-length encoding can fail for some artwork; the app stops instead of changing the original.

See the [model/firmware compatibility matrix and contributor procedure](../../docs/extensions/shutdown-compatibility.md). Other model/version combinations have no installer; a common update package does not qualify them.

The app is a preview release. Its desktop workflows have host tests; the complete app has not been camera-tested. Existing identification/copy evidence does not establish support for every firmware or body. The card/session marker cannot distinguish two physical cameras of the same model; the user must keep each session with its original body. An already modified camera cannot recover a factory original that was never backed up.

Only FAT32 volume roots are accepted for deployment. The app does not format cards or install firmware. Existing unrelated startup scripts and colliding task files are refused. Computer originals and recovery copies are checked in full and never replaced by different bytes; readbacks and deployment scripts are archived. An interrupted card deployment stops the workflow for inspection. Photos are never task destinations. No card was written during development tests.

## Desktop stability

Version 0.2.1 replaces Qt 6.8.3 with Qt 6.11.2. An arm64 macOS 27 report showed a startup-time crash in the Cocoa accessibility element destructor. The newer runtime includes accessibility cache/lifetime changes. Packaging checks the actual bundled Qt and app versions; the app version is also shown in the sidebar. Keep accessibility enabled when testing the packaged app. Offline UI tests do not cover Cocoa or macOS accessibility clients.

Version 0.2.3 also addresses a separate exit-time report: dialogs are scheduled for deletion after closing, and the window tree is explicitly destroyed before Python shutdown. Lifecycle tests exercise repeated dialog opening and both window closing and application quit in isolated processes.

## Run and build

From the repository root, with Python 3.10+:

```sh
python -m pip install -r apps/gr_shutdown_studio/requirements.txt
python -m apps.gr_shutdown_studio
python -m unittest discover -s tests/shutdown_studio -v
```

Build on each target operating system:

```sh
python -m pip install -r apps/gr_shutdown_studio/requirements-build.txt
python apps/gr_shutdown_studio/build.py
```

Outputs: `app-dist/GR Shutdown Studio.app` on macOS, `app-dist/GR Shutdown Studio/GR Shutdown Studio.exe` on Windows. The packaged app includes Python and its dependencies. macOS builds require macOS 13+; the provided CI targets Apple Silicon, Intel macOS and Windows x64. Each architecture is built on its corresponding host. Distribution signing/notarization is not configured. The GitHub workflow builds downloadable artifacts without publishing a release.

## 中文

图形化关机画面工具，支持 macOS 和 Windows。按界面完成卡检查、原图备份、选图裁剪、图片编码、准备安装和完整读回校验。相机开关机仍需手动完成；Urban 会自动引导两阶段安装。

0.3.0 的“适配测试”允许 10 类机型及其他菜单版本建立研究记录、分析本地更新包头、记录观察结果，并保留已读出原图的两份电脑副本。报告不含图片、EXIF、路径或机身标识，此入口不生成相机脚本。GR IV 主流程增加 1.04、1.03 的备份测试选项，未确认组合完成备份后导出报告，不进入安装。未知 III／IIIx 型号仍需专用、已审核的读取方法。分发与适配步骤见[社区测试流程](../../docs/extensions/community-compatibility-testing.md)。

界面分为 **备份原图 → 选择画面 → 安装校验** 三个阶段，左侧标明进度。每页只显示当前需要的控件，相机上的操作按序号列出，右下角按钮执行下一步。相机和构图采用分段选择，固件采用版本菜单，其他版本可单独填写；切换机型会清空已选版本。语言选项在设置页直接展开。

侧栏工具改为紧凑的线条图标与文字入口，主操作保留在右下角。

主页设置入口固定为 **Settings / 设置**，设置页语言选项固定为 **Language / 语言**。原图及操作记录保存到电脑，同时保存经核对的恢复副本。两份都在同一文件夹，请另将整个目录复制到其他存储位置。可重新打开继续操作或恢复。每台机身使用独立记录和 SD 卡；机型识别不能区分同型号的两台相机。

支持范围见[机型与固件兼容表](../../docs/extensions/shutdown-compatibility.md)。安装目前仅开放仓库已有版本依据的 GR IV / HDF 1.11 与 Urban 1.60，其他组合保持关闭。网友可通过“保存测试报告”导出不含图片和机身标识的记录。

0.2.1 更新 Qt 组件，并核对打包后的 Qt 与 App 版本，处理 macOS 启动后崩溃的问题。0.2.3 另处理退出时崩溃：关闭的对话框及时销毁，主窗口在 Python 结束前明确清理。macOS 最低版本为 13。离屏测试不能覆盖原生 Cocoa 与系统辅助功能调用，分发前还需检查实际打包的 App。

目前是预览版，完整 App 流程尚未实机验证。Urban 的等长编码不保证适配所有图片，失败时会停止。App 不格式化卡、不刷固件，不会覆盖无法确认归属的旧脚本。操作完成后关闭相机的 Script，保留电脑备份。
