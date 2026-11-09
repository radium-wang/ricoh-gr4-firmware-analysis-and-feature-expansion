# Feature expansion / 功能扩展

Feature extensions build on the firmware interfaces documented in this repository. For firmware architecture and interface research, start with the [research index](../research/README.md).

功能扩展基于本仓库记录的固件接口开展。固件结构和接口分析见[研究索引](../research/README.md)。

## Custom shutdown images / 自定义关机画面

Shutdown-image resource locations are listed below. Model names link to the existing guides and reports; firmware versions and procedures are documented there.

下表列出各机型关机图片的资源位置。点击机型名称查看现有指南或研究报告，固件版本和操作步骤见对应文档。

| Camera / 机型 | Internal directory / 相机内目录 | Original filename / 原文件名 |
| --- | --- | --- |
| GR III | - | - |
| GR III Street Edition | - | - |
| GR III Diary Edition | - | - |
| GR III HDF | - | - |
| GR IIIx | - | - |
| [GR IIIx Urban Edition](../gr3x-urban-160-shutdown-image.md) | `B:\Resource\Jpeg\` | `GB_Urban.jpg` |
| [GR IIIx HDF](../gr3x-hdf-160-shutdown-image.md) | `B:\Resource\Jpeg\` | `GoodBye.jpg` |
| [GR IV](../gr4-family-shutdown-workflow.md) | `A:\Resource\Jpeg\` | `GoodBye.jpg` |
| [GR IV HDF](../gr4-family-shutdown-workflow.md) | `A:\Resource\Jpeg\` | `GB_HDF.jpg` |
| [GR IV Monochrome](../gr4-family-shutdown-workflow.md) | `A:\Resource\Jpeg\` | `GB_Mono.jpg` |

`-` means no resource mapping has been submitted yet. Entries will be filled in as model-specific PRs arrive. See also the [GR IV 中文指南](../gr4-family-shutdown-workflow.zh-CN.md) and [original GR IV report](../firmware-and-shutdown-image-research.md).

`-` 表示尚未收到该机型的资源记录，后续随 PR 补充。GR IV 系列另有[中文指南](../gr4-family-shutdown-workflow.zh-CN.md)和[原始研究报告](../firmware-and-shutdown-image-research.md)。

For GR IV HDF 1.11 with a 256GB exFAT card, see the optional [literal-write workaround and device evidence](gr4-hdf-111-exfat-literal.md). It uses separate probe, temporary, installation and recovery stages; it does not change the FAT32 workflow or establish compatibility for other bodies.

GR IV HDF 1.11 搭配 256GB exFAT 卡的可选方法见[字面量写入流程与实测记录](gr4-hdf-111-exfat-literal.md)。小测试、临时写入、安装和恢复分别进行；原 FAT32 流程不变，其他机身不由此获得兼容性结论。

### Entry and preparation / 入口与准备

Generate files on a computer, then follow the selected guide for copying them and enabling Script:

```sh
python3 tools/create_factory_entry.py ./entry
python3 tools/create_factory_entry.py ./entry-urban --model gr3x-urban-160
python3 tools/create_factory_entry.py ./entry-hdf --model gr3x-hdf-160
```

For the GR IV-family guide, copy `00078560.636` and `DEVELOP.MOD` to the SD-card root. With the camera off, hold MENU while powering on to enter the factory menu. Enable only Script, then shut down before removing the card. The family workflow uses FAT32; do not treat this entry method as universal firmware support.

GR IV 系列入口为卡根目录的 `00078560.636` 与 `DEVELOP.MOD`，关机时按住 MENU 开机进入工厂菜单，仅开启 Script，再关机取卡。系列流程使用 FAT32。Urban 的入口和后续传输方法不同，请按独立指南操作。

For GR IIIx Urban Edition and HDF, follow each model's report for entry files and image transfer.

GR IIIx Urban Edition 和 HDF 的入口文件与图片传输步骤见各自的报告。

### Backup and verification / 备份与校验

Keep the original and a second copy on your computer for each body. Verify complete SHA-256 readbacks and the visible screen. Empty readbacks indicate failure or incomplete execution. Archive failed attempts before investigating; do not retry blindly. Remove the startup script and disable Script after completion.

每台机身单独保存原图及电脑副本，以完整 SHA-256 和实际画面核对结果。空读回不是成功，失败时保留现场并排查，结束后移除启动脚本并关闭 Script。已经覆盖且未备份的原图无法由这些工具找回。

## File-operation checks / 文件操作检查

Before writing internal resources, test a small SD-to-SD copy and verify its complete contents on the computer. See the [TTL file-operation findings](../research/gr4-ttl-filecopy-filesystems.md) for details.

写入前先用小文件核对卡内复制，再在电脑上校验完整内容。详情见 [TTL 文件操作记录](../research/gr4-ttl-filecopy-filesystems.md)。
