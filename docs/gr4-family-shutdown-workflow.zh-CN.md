# GR IV／HDF／Monochrome 自适应单张关机图

[English](gr4-family-shutdown-workflow.md) · [简体中文](gr4-family-shutdown-workflow.zh-CN.md)

自动识别机型并选择对应关机图路径。保留项目原来的复制脚本、开机执行、电脑校验方式；不刷固件，不包含轮换，也不提供图片。

## 与原项目的兼容关系

原有 `backup-goodbye`、`write-goodbye`、`restore-goodbye` 示例及其 `GBBACK.JPG` 文件名未改变，仍用于普通 GR IV。工厂入口生成命令、默认机型和 `pad_jpeg.py` 均未改变。GR IIIx Urban 按独立指南使用。新增 family 模板是可选的新流程，旧用户不需要迁移；不要将旧的 `GBBACK.JPG` 直接混入新流程。

## 准备

使用 FAT32 卡，按 README 原有步骤开启 Script。保持电量充足，每次执行后等读写结束再关机取卡。此流程不支持从 exFAT 卡首次写入图片。

GR IV HDF 1.11 与 256GB exFAT 卡另有可选的[字面量写入流程及实测记录](extensions/gr4-hdf-111-exfat-literal.md)，通过分阶段验证绕过卡源 `filecopy`，其图像配置和验证范围与本页默认生成器不同。

为每台机身保留独立备份。更换测试机身前，先将旧的 `GBMODEL.TXT`、三种备份、读回文件及执行标记归档到电脑，再清理工作卡上的旧输出。识别机型不能区分同型号的两台机身，也不能识别固件版本。

## 1. 备份

将 `examples/backup-gr4-family.ttl.example` 复制为卡上的 `script/startup.ttl`，安全弹出，正常开机一次，等读写结束后关机接回。

卡上会生成 `GBMODEL.TXT` 及对应原图：

| 机型 | 原图备份 |
| --- | --- |
| 普通 GR IV | `GBSTD.JPG` |
| GR IV HDF | `GBHDF.JPG` |
| GR IV Monochrome | `GBMONO.JPG` |

打开图片确认内容，把原图和报告另存到电脑。已有备份不会被覆盖。识别为 UNKNOWN、缺少文件或图片不正确时停止。已改过的相机只能备份当前图片，不能找回遗失的出厂原图。

## 2. 准备图片

使用自己的 720×480、相机可解码的 JPEG，命名为 `NEWGB.JPG`。新图必须与原图字节数相同；较短时可沿用原项目命令：

```sh
python3 tools/pad_jpeg.py NEWGB.JPG TARGET_BYTES NEWGB_READY.JPG
```

`TARGET_BYTES` 是本机原图长度，例如 macOS 执行 `stat -f %z GBHDF.JPG`。将生成文件改名为 `NEWGB.JPG`。不要修改原图。工具不改变像素、不验证相机解码能力，且单段补齐长度有限；新图太大或无法补齐时请重新压缩、简化图案，或使用后面的可选生成器。新模板不尝试扩容或截断机内文件。

## 3. 替换与校验

归档并移除旧的 `GBREAD.JPG`。保持原图和 `GBMODEL.TXT` 在卡上，放入 `NEWGB.JPG`，将 `examples/write-gr4-family.ttl.example` 复制为 `script/startup.ttl`。正常开机一次，等读写结束后关机接回，执行：

```sh
shasum -a 256 NEWGB.JPG GBREAD.JPG
```

两个文件必须存在，完整哈希一致，并且实际关机画面正确。前缀相同、尾部残留不算通过。完成后删除启动脚本；若没有其他脚本功能，将 Script 设回 Disable，再确认普通开关机仍显示新图。保留电脑上的原图。

脚本会先预留读回文件，再执行写入，防止每次开机盲目重试。**空读回文件表示失败或未完成，不表示成功。** 不一致时保存现场并排查，不要反复删除输出来重试。保护不等于断电事务保证；相机端只检查长度，电脑端才做完整哈希校验。

## 4. 恢复

仅在同一台机身上使用它自己的原图和报告。归档并移除旧 `GBREST.JPG`，将 `examples/restore-gr4-family.ttl.example` 复制为 `script/startup.ttl`，开启 Script，正常执行一次后接回。以 HDF 为例：

```sh
shasum -a 256 GBHDF.JPG GBREST.JPG
```

普通版、Mono 分别换成自己的备份文件名。完整哈希及实际画面都正确后，移除恢复脚本。若当前目标长度已被其他操作改变，恢复脚本会停止；不会删除、截断或强制修复。

## 可选：自动处理图片与生成操作包

这不是必需步骤。需要 Python 3.10+，图片处理另需 `python3 -m pip install Pillow`。在仓库根目录：

```sh
python3 tools/gr4_shutdown.py backup ./stage-backup
python3 tools/gr4_shutdown.py prepare /path/to/card ./my-image.png ./my-camera-package
python3 tools/gr4_shutdown.py verify ./my-camera-package /path/to/card/GBREAD.JPG
python3 tools/gr4_shutdown.py restore ./my-camera-package ./stage-restore
python3 tools/gr4_shutdown.py verify ./my-camera-package /path/to/card/GBREST.JPG --restore
```

这些命令按阶段运行，不是连续执行全部命令。backup 生成备份脚本，先完成机内备份再运行 prepare。prepare 读取卡上报告与原图，接受 720×480 图片，编码为非渐进 4:2:0 JPEG，从质量 95 降至 5 尝试适配原图大小，再用 COM 补齐。无法适配则停止，不改原图。查看 `manifest.json` 中质量并打开新图确认。

prepare 输出中的原图和 manifest 留存在电脑；将 `NEWGB.JPG`、`GBARM.TXT`、`script/startup.ttl` 复制到同一机身的卡上。保持原备份在卡上，先清理已归档的旧读回文件，再执行并 verify。生成器使用一次性执行标记，失败后不会自动重试。restore 生成恢复包，将其中原图、执行标记和启动脚本复制到卡，执行后用 `--restore` 校验。输出目录必须新建或为空。

生成器不会格式化、自动寻找或写入存储卡；完整操作包应保留在电脑。不要恢复会覆盖此图片的旧轮换脚本。

## 验证边界

三种机身的识别和目标路径已有真机依据。普通版、HDF 已确认 1.11；Mono 的精确版本未记录。**本次组合模板、执行保护和自动图片处理通过离线测试，尚未整套上机验证。** Python 测试不等于相机模拟器，电脑解码成功不保证相机接受。

不能自动识别同型号换机、不能恢复未保存的原图、不保证所有固件兼容。仓库不包含固件、机身读回数据、序列号、生产配置转储或私人图片。技术依据见[机型识别说明](gr4-model-identification.md)。
