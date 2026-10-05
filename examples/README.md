# Examples / 示例

TTL scripts run inside the camera, not in a terminal on your computer. Most application templates use `script/startup.ttl` on an SD card with Script enabled. Do not run every example together.

TTL 由相机解释器执行，不是电脑终端脚本。多数应用模板放在卡上的 `script/startup.ttl`，需要开启 Script。每次按对应指南选择一个示例。

## Read-only interface research / 只读接口研究

| Example | Behavior / 行为 |
| --- | --- |
| [identify-gr4-model](identify-gr4-model.ttl.example) | Reads eight product-header bytes from `E:\BlkCtl15.bin`; writes only the model label to `C:\AUTOMOD.TXT` / 读取产品头，向卡输出机型标签 |

See [identification evidence](../docs/gr4-model-identification.md) for the product allowlist, output handling and limits. It identifies model families, not individual bodies or firmware versions.

## Feature expansion / 功能扩展

| Templates | Guide / 指南 |
| --- | --- |
| `backup-gr4-family`, `write-gr4-family`, `restore-gr4-family` | [GR IV family](../docs/gr4-family-shutdown-workflow.md) · [中文](../docs/gr4-family-shutdown-workflow.zh-CN.md) |
| `backup-goodbye`, `write-goodbye`, `restore-goodbye` | Standard GR IV only, `GBBACK.JPG`; see below / 仅普通 GR IV，使用 `GBBACK.JPG` |
| `gr3x-urban-backup`, `gr3x-urban-restore` | [Urban 1.60](../docs/gr3x-urban-160-shutdown-image.md) |
| `gr3x-hdf-160-backup` | [GR IIIx HDF 1.60 method record](../docs/gr3x-hdf-160-shutdown-image.md); contributor-reported one-body backup / 贡献者报告的单机备份 |

### Original standard GR IV templates / 普通 GR IV 旧模板

Follow the [entry setup](../docs/extensions/README.md#entry-and-preparation--入口与准备), then run [backup-goodbye](backup-goodbye.ttl.example) first. Confirm `GBBACK.JPG` opens and save another copy on your computer. Prepare a camera-compatible 720×480 `NEWGB.JPG` matching the original byte length; `tools/pad_jpeg.py` can pad a shorter JPEG.

Run [write-goodbye](write-goodbye.ttl.example), then compare `NEWGB.JPG` with `GBREAD.JPG` using `shasum -a 256`. For restoration, run [restore-goodbye](restore-goodbye.ttl.example) and compare `GBBACK.JPG` with `GBREST.JPG`. Check the actual screen in both cases. Archive and investigate old readbacks before removing them for another attempt. Finish by deleting the startup script and disabling Script.

按入口说明开启 Script，先执行备份，确认 `GBBACK.JPG` 可打开并另存电脑。新图使用与原图等长的 720×480 JPEG。写入后比较 `NEWGB.JPG`／`GBREAD.JPG`，恢复后比较 `GBBACK.JPG`／`GBREST.JPG`，均需完整哈希一致且实际画面正确。重试前归档并排查旧读回，结束后删除启动脚本并关闭 Script。

These older templates check file existence, not model or equal lengths. They target `A:\Resource\Jpeg\GoodBye.jpg` and must not be used on HDF/Monochrome or Urban. Keep their backup names separate from family templates. The original copy experiment was camera-tested; later guards and the restore template have offline tests only.

旧模板不检查机型或等长条件，仅用于普通 GR IV。不要混用系列模板的备份名。原始复制实验有实机结果，后加保护及恢复模板仅经过离线测试。
