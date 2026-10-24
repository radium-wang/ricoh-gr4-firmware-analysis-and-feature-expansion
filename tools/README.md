# Tools / 工具

Run commands from the repository root. Paths are unchanged so existing scripts and guides continue to work.

在仓库根目录执行命令。保留工具路径，便于复用现有脚本和指南。

## Firmware and interfaces / 固件与接口

| Tool | Purpose / 用途 | Access / 操作范围 |
| --- | --- | --- |
| [inspect_firmware.py](inspect_firmware.py) | Header, checksum and frame decoding / 包头、校验及帧解码 | Local files only; writes decoded output when requested / 仅本地文件，可输出解码载荷 |
| [gr4_firmware_parts.py](gr4_firmware_parts.py) | Shared update decoder and embedded component detection / 更新包解码与内嵌组件检测 | Local files only; shared module / 仅本地文件，共用模块 |
| [audit_gr4_linux_memory.py](audit_gr4_linux_memory.py) | Linux RAM banks, kernel configuration and 15 RTOS pools / Linux 内存、内核配置与 15 个 RTOS 池 | Read-only pinned GR IV 1.11.10.7 sample; requires Capstone / 固定样本只读审计，需 Capstone |
| [mtp_probe_readonly.py](mtp_probe_readonly.py) | Device and storage queries / 设备及存储查询 | USB read-only; requires PyUSB / USB 只读，需 PyUSB |
| [ic_probe_readonly.swift](ic_probe_readonly.swift) | ImageCaptureCore enumeration / 相机枚举 | macOS device session, read-only / macOS 设备会话，只读 |
| [gr4_model.py](gr4_model.py) | Product-header identification / 产品头识别 | Host-side eight-byte input; no camera access / 电脑端八字节输入 |

## Feature expansion / 功能扩展

| Tool | Purpose / 用途 |
| --- | --- |
| [create_factory_entry.py](create_factory_entry.py) | Generate entry files for documented setups / 生成已记录机型的工厂入口文件 |
| [pad_jpeg.py](pad_jpeg.py) | JPEG COM padding to a requested byte length / 通过 COM 段补齐 JPEG 长度 |
| [gr4_shutdown.py](gr4_shutdown.py) | GR IV-family image preparation, staged script packages and readback verification / 系列图片处理、操作包生成及读回校验 |
| [gr4_hdf_exfat.py](gr4_hdf_exfat.py) | Optional `gr4_shutdown.py exfat` HDF 1.11 literal transport; [workflow and limits](../docs/extensions/gr4-hdf-111-exfat-literal.md) / 可选 HDF 字面量传输、小测试及分阶段完整校验 |
| [gr3x_urban_jpeg.py](gr3x_urban_jpeg.py) | Urban-specific JPEG encoding and checks / Urban JPEG 编码与检查 |
| [gr3x_urban_shutdown.py](gr3x_urban_shutdown.py) | Urban two-stage scripts and verification / Urban 两阶段脚本与校验 |

These generators write local files; they do not install firmware or automatically write to a card. Generated TTL scripts may write camera resources when run on the device. Read the [workflow guide](../docs/extensions/README.md) before using them.

生成器只输出本地文件，不安装固件或自动写卡。生成的 TTL 在相机上运行时可能写入机内资源，使用前阅读对应流程。

## Dependencies / 依赖

Use Python 3.10+ for all Python tools and tests. Basic inspection and entry generation need only the standard library. Install Pillow for image encoding and PyUSB for MTP queries. The Swift probe requires a macOS Swift toolchain and ImageCaptureCore.

整套 Python 工具和测试使用 Python 3.10+。基础检查和入口生成只需标准库，图片编码需 Pillow，MTP 查询需 PyUSB；Swift 探针需 macOS Swift 工具链及 ImageCaptureCore。

The [1 GiB memory report](../docs/research/2026-10-13-gr4-linux-1gib-memory.md) documents a candidate repartition and historical kernel layout tests. Its static audit does not patch firmware or access a camera. Install Capstone with `python3 -m pip install capstone`; obtain the firmware sample separately.

[1 GiB 内存研究](../docs/research/2026-10-13-gr4-linux-1gib-memory.md)记录候选分区及历史内核布局实验。静态工具不修改固件、不连接相机；需自行取得固件并安装 Capstone。
