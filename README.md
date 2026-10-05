<!-- License: see LICENSE (earlier Apache-2.0 grants remain in force) -->

# Ricoh GR IV Firmware Analysis and Feature Expansion

## English

Research into Ricoh GR IV firmware, internal interfaces and possible feature extensions. The repository contains analysis notes, offline tools, read-only device probes and reproducible experiments. Feature work currently includes custom shutdown images through the factory-script interface.

### Firmware research

| Area | Current work |
| --- | --- |
| Firmware container | Header and version fields, frame decoding, whole-file checksum |
| System layout | RTOS load mapping, embedded Linux device tree and memory regions |
| USB / MTP | Read-only enumeration and the limits of the tested USB modes |
| Factory and debug interfaces | Persistent Camera Mode state, Version page, key-event paths and TTL startup scripts |
| Model identification | GR IV, HDF and Monochrome product IDs and resource selection |

Start with the [research index](docs/research/README.md) and [developer guide](docs/research/developer-guide.md). The [research log](docs/research-log.md) records experiments and corrections; [open questions](docs/research/open-questions.md) lists work that still needs evidence. Most detailed reports are currently in Chinese.

#### Offline analysis

Obtain a firmware file yourself. These commands inspect or decode a local container without connecting to a camera:

```sh
python3 tools/inspect_firmware.py /path/to/fwdc248b.bin
python3 tools/inspect_firmware.py /path/to/fwdc248b.bin --unpack /tmp/gr4-decoded.bin
```

Record the model, firmware version and sample SHA-256 with each finding. Distinguish file offsets from runtime addresses, and static analysis from camera observations. See the developer guide for the documented RTOS mapping and a contribution checklist.

Firmware, extracted system files, device readbacks and private artwork are not distributed. No installable modified firmware or general-purpose camera SDK is provided. Host-side tests do not emulate the camera hardware.

### Feature expansion

#### Custom shutdown images

[Shutdown-image guides](docs/extensions/README.md) cover the GR IV family and GR IIIx Urban Edition 1.60, with separate backup, write, readback and restore procedures. A [GR IIIx HDF 1.60 method record](docs/gr3x-hdf-160-shutdown-image.md) collects a contributor's one-body replacement findings; restoration was not tested. Identification and target paths have physical evidence; newer combined templates and wrappers are not fully camera-qualified. Keep a computer backup of each body's original before writing.

### Repository layout

```text
docs/
  research/       Research index, developer guide and open questions
  extensions/     Feature extension guides and experiments
  *.md            Existing technical reports and experiment log
tools/            Offline analysis, device probes and workflow generators
examples/         TTL experiments and feature templates
tests/            Host-side checks and script control-flow models
```

[Documentation](docs/README.md) · [Tool reference](tools/README.md) · [Examples](examples/README.md) · [Contributing](CONTRIBUTING.md)

### Development

Use Python 3.10+ and Pillow for the complete test suite. Individual analysis tools may have fewer dependencies; see [tools](tools/README.md).

```sh
python3 -m pip install Pillow
python3 -m unittest discover -s tests -v
```

Contributions can include address maps, format documentation, read-only probes, reproducible findings and feature experiments. Include the evidence and limitations, rather than only the final result. See [CONTRIBUTING.md](CONTRIBUTING.md).

### License

Newly licensed project material is released under the [GR IV Project Noncommercial Source License 1.0](LICENSE). Commercial use requires written permission; this is not an OSI-approved open-source license. Revisions through [`a55a2c7`](https://github.com/radium-wang/ricoh-gr4-firmware-analysis-and-feature-expansion/tree/a55a2c7) and unchanged material from those revisions retain their Apache-2.0 grants. See [NOTICE](NOTICE) and [CONTRIBUTING.md](CONTRIBUTING.md).

Camera modifications carry a risk of data loss or malfunction. Results apply only to the documented test setups. No rights to third-party firmware, artwork or trademarks are granted.

---

## 中文

本项目研究理光 GR IV 的固件结构、内部接口和功能扩展可能性，收录分析记录、离线工具、只读探针及可复现实验。目前的功能扩展包括通过工厂脚本接口自定义关机画面。

### 固件研究

| 方向 | 已有内容 |
| --- | --- |
| 固件容器 | 包头、版本字段、帧解码和整文件校验 |
| 系统布局 | RTOS 装载映射、内嵌 Linux 设备树及内存区域 |
| USB / MTP | 只读枚举及已测试 USB 模式的能力边界 |
| 工厂与调试接口 | Camera Mode 持久化、Version 页面、按键事件路径及 TTL 启动脚本 |
| 机型识别 | GR IV、HDF、Monochrome 产品 ID 与资源选择 |

从[研究索引](docs/research/README.md)和[开发者入门](docs/research/developer-guide.md)开始。[研究日志](docs/research-log.md)保留实验过程与结论修订，[待研究问题](docs/research/open-questions.md)列出仍需证据的方向。

#### 离线分析

自行取得固件文件。以下命令只检查或解码本地容器，不连接相机：

```sh
python3 tools/inspect_firmware.py /path/to/fwdc248b.bin
python3 tools/inspect_firmware.py /path/to/fwdc248b.bin --unpack /tmp/gr4-decoded.bin
```

记录每项发现对应的机型、固件版本和样本 SHA-256。区分文件偏移与运行时地址、静态分析与实机观察。开发者指南提供已记录的 RTOS 映射及研究提交要求。

仓库不分发固件、解包系统文件、机身读回数据或私人图稿，目前没有可安装的修改版固件或通用相机 SDK。电脑端测试不等于硬件模拟。

### 功能扩展

#### 自定义关机画面

[关机图片流程](docs/extensions/README.md)包含 GR IV 系列及 GR IIIx Urban Edition 1.60 的备份、写入、读回和恢复指南。[GR IIIx HDF 1.60 方法记录](docs/gr3x-hdf-160-shutdown-image.md)另收录贡献者的单机更换发现，恢复未实测。机型识别及目标路径已有实机依据；新组合模板及工具包装尚未整套上机验证。写入前为每台机身保留电脑端原图备份。

### 仓库结构

```text
docs/
  research/       研究索引、开发者入门、待研究问题
  extensions/     功能扩展指南与实验
  *.md            现有技术报告及实验日志
tools/            离线分析、设备探测及操作包生成工具
examples/         TTL 实验与功能扩展模板
tests/            电脑端检查及脚本控制流模型
```

[文档目录](docs/README.md) · [工具说明](tools/README.md) · [示例说明](examples/README.md) · [贡献指南](CONTRIBUTING.md)

### 开发与贡献

整套测试需要 Python 3.10+ 和 Pillow，各分析工具的依赖见[工具说明](tools/README.md)。

```sh
python3 -m pip install Pillow
python3 -m unittest discover -s tests -v
```

欢迎提交地址映射、格式说明、只读探针、可复现发现和功能实验。请附证据、验证范围及未解决问题，要求见[贡献指南](CONTRIBUTING.md)。

### 许可证

新授权的项目内容采用 [GR IV Project Noncommercial Source License 1.0](LICENSE)，商业使用须取得书面许可；这不是 OSI 定义下的开源许可证。截至 [`a55a2c7`](https://github.com/radium-wang/ricoh-gr4-firmware-analysis-and-feature-expansion/tree/a55a2c7) 的旧版本及其保留的未修改内容仍适用原有 Apache-2.0 授权。详见 [NOTICE](NOTICE) 和[贡献指南](CONTRIBUTING.md)。

改机存在数据丢失或设备故障风险，实测结果仅对应文档记录的环境。项目许可证不授予第三方固件、图稿或商标的使用权。
