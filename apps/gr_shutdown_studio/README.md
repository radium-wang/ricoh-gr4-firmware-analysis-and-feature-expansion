# GR Shutdown Studio

A desktop app for preparing and verifying custom Ricoh GR shutdown images on macOS and Windows.

## Workflow

1. Choose the workflow, enter the firmware shown in the camera menu, and create a backup folder on your computer. Select the FAT32 SD card when prompted.
2. Prepare a small SD copy check. Enable Script from the camera factory menu and run once.
3. Reconnect the card. The app verifies the copy and prepares the backup script.
4. Run the backup once, reconnect, and save the original on your computer.
5. Choose an image, crop or fit it, and preview the encoded 720×480 JPEG.
6. Prepare installation, run the camera script, and reconnect for full readback verification. Urban requires a temporary-image stage first.
7. Check the actual shutdown screen and disable Script. Keep the session to restore later. Urban restoration first exports and verifies its internal original before preparing the restore script.

The sidebar tracks three stages: **Back up original → Choose image → Install & verify**. Each page shows only the current controls. Camera tasks appear as numbered instructions; the bottom-right button advances the current step. Camera family, framing and language use visible radio options with the operating system’s control style.

Home: **Settings / 设置**. Settings dialog: **Language / 语言**. Both labels stay bilingual, with English and Chinese interfaces available.

## Camera support

- GR IV / HDF 1.11: automatic model selection during backup, equal-length JPEG encoding, one-shot installation and restoration. Monochrome identification is known but its evidence did not record firmware; installation is currently disabled.
- GR IIIx Urban Edition 1.60: verified original profile only; temporary-image generation, complete readbacks between stages, internal-backup restoration. Exact-length encoding can fail for some artwork; the app stops instead of changing the original.

See the [model/firmware compatibility matrix and contributor procedure](../../docs/extensions/shutdown-compatibility.md). Other model/version combinations have no installer; a common update package does not qualify them.

The app is a preview release. Its desktop workflows have host tests; the complete app has not been camera-tested. Existing identification/copy evidence does not establish support for every firmware or body. The card/session marker cannot distinguish two physical cameras of the same model; the user must keep each session with its original body. An already modified camera cannot recover a factory original that was never backed up.

Only FAT32 volume roots are accepted for deployment. The app does not format cards or install firmware. Existing unrelated startup scripts and colliding task files are refused. Computer originals and recovery copies are checked in full and never replaced by different bytes; readbacks and deployment scripts are archived. An interrupted card deployment stops the workflow for inspection. Photos are never task destinations. No card was written during development tests.

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

Outputs: `app-dist/GR Shutdown Studio.app` on macOS, `app-dist/GR Shutdown Studio/GR Shutdown Studio.exe` on Windows. The packaged app includes Python and its dependencies. macOS builds require macOS 12+; the provided CI targets Apple Silicon, Intel macOS and Windows x64. Each architecture is built on its corresponding host. Distribution signing/notarization is not configured. The GitHub workflow builds downloadable artifacts without publishing a release.

## 中文

图形化关机画面工具，支持 macOS 和 Windows。按界面完成卡检查、原图备份、选图裁剪、图片编码、准备安装和完整读回校验。相机开关机仍需手动完成；Urban 会自动引导两阶段安装。

界面分为 **备份原图 → 选择画面 → 安装校验** 三个阶段，左侧标明进度。每页只显示当前需要的控件，相机上的操作按序号列出，右下角按钮执行下一步。相机、构图和语言选项直接展开，使用系统样式的单选控件。

主页设置入口固定为 **Settings / 设置**，设置页语言选项固定为 **Language / 语言**。原图及操作记录保存到电脑，同时保存经核对的恢复副本。两份都在同一文件夹，请另将整个目录复制到其他存储位置。可重新打开继续操作或恢复。每台机身使用独立记录和 SD 卡；机型识别不能区分同型号的两台相机。

支持范围见[机型与固件兼容表](../../docs/extensions/shutdown-compatibility.md)。安装目前仅开放仓库已有版本依据的 GR IV / HDF 1.11 与 Urban 1.60，其他组合保持关闭。网友可通过“保存测试报告”导出不含图片和机身标识的记录。

目前是预览版，完整 App 流程尚未实机验证。Urban 的等长编码不保证适配所有图片，失败时会停止。App 不格式化卡、不刷固件，不会覆盖无法确认归属的旧脚本。操作完成后关闭相机的 Script，保留电脑备份。
