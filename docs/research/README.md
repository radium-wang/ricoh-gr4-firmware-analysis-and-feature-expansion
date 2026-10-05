# Firmware research / 固件研究

[Developer guide / 开发者入门](developer-guide.md) · [Open questions / 待研究问题](open-questions.md)

The reports below document existing findings. Static addresses refer to the recorded sample, not every firmware version. “Observed” means a reported device result; “static” means a finding from firmware analysis. Neither establishes general compatibility.

以下按主题索引已有报告。静态地址仅对应记录的样本；“实机”表示设备观察，“静态”表示固件分析，均不能直接推广到所有版本。

| Topic / 主题 | Evidence / 依据 | Report / 报告 |
| --- | --- | --- |
| Container headers, versions, frame decoding and checksum / 容器结构与校验 | Local GR IV 1.11 sample / 本地样本分析 | [Firmware package / 固件更新包](../firmware-and-shutdown-image-research.md#固件更新包) |
| RTOS mapping, Linux device tree and memory / RTOS 与 Linux 内存布局 | Static analysis; chip capacity discussed separately / 静态分析，物理容量另作讨论 | [Memory map / 内存映射](../firmware-and-shutdown-image-research.md#a7linux-内存映射) |
| USB descriptors and MTP capabilities / USB 与 MTP 能力 | Read-only queries on one GR IV / 单台只读查询 | [USB/MTP](../firmware-and-shutdown-image-research.md#usbmtp-调查) |
| Camera Mode persistence and consumers / Debug 持久化与消费者 | Static control-flow tracing / 静态控制流追踪 | [Debug analysis / Debug 分析](../gr4-debug-mode-analysis.md) |
| Version-page startup and key events / Version 页与按键事件 | Static tracing plus a verified startup gesture / 静态追踪及已验证入口 | [Version page / Version 入口](../gr4-debug-mode-analysis.md#开机代码-4-的来源与实机验证) |
| Factory menu, serial input and TTL / 工厂菜单、串口与脚本 | Mixed static findings and device observations / 静态与实机结论分别记录 | [Factory interfaces / 工厂接口](../firmware-and-shutdown-image-research.md#工厂菜单与启动脚本) |
| Product IDs and resource routing / 产品 ID 与资源路径 | Static analysis and three-body identification evidence / 静态分析及三机型识别证据 | [Model identification / 机型识别](../gr4-model-identification.md) |
| TTL file-operation failures / TTL 文件操作失败 | Contributor report; root cause unresolved / 社区反馈，根因待查 | [Filesystem comparison](gr4-ttl-filecopy-filesystems.md) |
| Resource writes and JPEG handling / 资源写入及 JPEG 行为 | Camera-specific experiments / 按机型记录的实验 | [GR IV](../firmware-and-shutdown-image-research.md#已验证的写入原理), [Urban](../gr3x-urban-160-shutdown-image.md), [GR IIIx HDF](../gr3x-hdf-160-shutdown-image.md) |

## Reading order / 阅读顺序

1. Read the container and system-layout sections to identify the sample and address space.
2. Follow the Debug report for examples of tracing configuration, messages, controllers and key events.
3. Compare static conclusions with the device observations and corrections in the [log](../research-log.md).
4. Pick an [open question](open-questions.md) and record a reproducible experiment.

先确定样本和地址空间，再阅读 Debug 报告中的配置、消息、控制器与按键追踪。用日志核对实机观察及被撤回的推测，然后选择待研究问题开展实验。

The shutdown-image guides are collected under [feature expansion](../extensions/README.md). The documented resource interface is not a general firmware installer.
