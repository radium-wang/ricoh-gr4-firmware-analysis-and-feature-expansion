# Firmware research / 固件研究

[Documentation / 文档](../README.md) · [Developer guide / 开发者入门](developer-guide.md) · [Open questions / 待研究问题](open-questions.md)

The reports below document existing findings. Static addresses refer to the recorded sample, not every firmware version. “Observed” means a reported device result; “static” means a finding from firmware analysis. Neither establishes general compatibility.

以下按主题索引已有报告。静态地址仅对应记录的样本；“实机”表示设备观察，“静态”表示固件分析，均不能直接推广到所有版本。

## Firmware architecture and memory / 固件结构与内存

| Topic / 主题 | Evidence / 依据 | Report / 报告 |
| --- | --- | --- |
| Container headers, versions, frame decoding and checksum / 容器结构与校验 | Local GR IV 1.11 sample / 本地样本分析 | [Firmware package / 固件更新包](../firmware-and-shutdown-image-research.md#固件更新包) |
| RTOS mapping, Linux device tree and memory / RTOS 与 Linux 内存布局 | Static analysis; chip capacity discussed separately / 静态分析，物理容量另作讨论 | [Memory map / 内存映射](../firmware-and-shutdown-image-research.md#a7linux-内存映射) |
| Linux RAM expansion to 1 GiB / Linux 扩容到 1 GiB | Original kernel booted with a split layout in QEMU; IMAGE2 repartition untested on camera / 原厂内核分段布局离线启动成功，缩小 IMAGE2 尚未验证机身功能 | [Memory feasibility / 内存可行性](2026-10-13-gr4-linux-1gib-memory.md) |
| Update version comparison / 升级版本比较 | Offline container and control-flow checks / 离线容器与控制流核对 | [Version check / 版本检查](../gr4-update-version-check.md) |

## Camera interfaces / 相机接口

| Topic / 主题 | Evidence / 依据 | Report / 报告 |
| --- | --- | --- |
| USB descriptors and MTP capabilities / USB 与 MTP 能力 | Read-only queries on one GR IV / 单台只读查询 | [USB/MTP](../firmware-and-shutdown-image-research.md#usbmtp-调查) |
| Camera Mode persistence and consumers / Debug 持久化与消费者 | Static control-flow tracing / 静态控制流追踪 | [Debug analysis / Debug 分析](../gr4-debug-mode-analysis.md) |
| Version-page startup and key events / Version 页与按键事件 | Static tracing plus a verified startup gesture / 静态追踪及已验证入口 | [Version page / Version 入口](../gr4-debug-mode-analysis.md#开机代码-4-的来源与实机验证) |
| Factory menu, serial input and TTL / 工厂菜单、串口与脚本 | Mixed static findings and device observations / 静态与实机结论分别记录 | [Factory interfaces / 工厂接口](../firmware-and-shutdown-image-research.md#工厂菜单与启动脚本) |
| Product IDs and resource routing / 产品 ID 与资源路径 | Static analysis and three-body identification evidence / 静态分析及三机型识别证据 | [Model identification / 机型识别](../gr4-model-identification.md) |
| Focus modes, hybrid CAF/ZAF and lens requests / 对焦模式、混合 AF 与镜头请求 | Static checks and bounded original ARM execution / 静态核对及有限原 ARM 指令检查 | [Focus research / 对焦研究](2026-10-13-gr4-focus.md) |
| Factory USB/MTP and SD-to-Linux / USB 工厂通道与 SD 桥接 | Static tracing and device probes / 静态追踪与实机探针 | [USB factory path / USB 工厂通道](../2026-10-01-gr4-usb-factory-path.md) · [SD bridge repetitions / SD 桥接复测](../2026-10-01-sd-bridge-repeat.md) |

## XPAN crop and native UI / XPAN 裁切与原生界面

| Topic / 主题 | Evidence / 依据 | Report / 报告 |
| --- | --- | --- |
| Crop geometry and menu candidates / 裁切几何与菜单候选 | Static analysis and bounded tests / 静态分析及有限测试 | [Feasibility / 可行性](../xpan-crop-feasibility.md) · [Native UI routes / 原生界面](2026-10-01-native-ui-routes.md) |
| SD probes and owned RAM execution / SD 探针与自有 RAM 执行 | Device observations on GR IV 1.11 / GR IV 1.11 实机观察 | [SD path / SD 路径](../xpan-sd-path.md) · [RAM core / RAM 核心](2026-10-01-xpan-ram-core.md) · [Recovery / 恢复](../xpan-recovery.md) |
| JPEG, preview and menu hooks / JPEG、预览与菜单挂钩 | Offline candidates and separately labelled read-only device results / 离线候选及另行标记的实机只读结果 | [JPEG route / JPEG 路由](2026-10-02-jpeg-native-route.md) · [Shared selection / 共用选择](2026-10-02-shared-selection-v15.md) · [v16 hooks / v16 挂钩](2026-10-02-native-menu-hooks-v16.md) |

The [research log](../research-log.md) records changes in the proposed menu placement and the intermediate preview experiments. No installable XPAN feature was validated on the camera.

[研究日志](../research-log.md)记录了菜单位置方案的变化及中间预览实验。XPAN 功能未在实机完成安装验证。

## Flash and hotshoe / 闪光灯与热靴

| Topic / 主题 | Evidence / 依据 | Report / 报告 |
| --- | --- | --- |
| Flash research overview / 闪光灯研究总览 | Fixed-sample analysis and GF-2 device observations / 固定样本分析与 GF-2 实机观察 | [Protocol, identity and power / 协议、识别与电源](gr4-flash-research-summary.md) |
| Hotshoe handshake and output encoding / 热靴握手与输出编码 | Static protocol tracing; physical output and timing partly unresolved / 静态协议追踪，部分物理光量和时序待核对 | [Hotshoe protocol / 热靴协议](2026-10-12-gr4-hotshoe-protocol.md) |
| GF-2 power and wake experiments / GF-2 电源与唤醒实验 | v4 logged result; v5 manual-recovery observations with SD log pending / v4 有完整日志，v5 手动恢复有用户观察、SD 日志待读回 | [v4 result / v4 结果](2026-10-13-gr4-hotshoe-a6-test-v4.md) · [v5 record / v5 记录](2026-10-13-gr4-hotshoe-manual-power-v5.md) |
| Nikon flash bridging / 尼康闪光灯桥接 | Feasibility proposal; bridge and GR-side Nikon TTL unverified / 可行性方案，桥接器及 GR 端尼康 TTL 未验证 | [Bridge feasibility / 桥接可行性](2026-10-13-gr4-nikon-flash-bridge-feasibility.md) |

GF-2 kind 0x11 is verified on the tested setup. The completed v4 C0/A6 sequence did not wake the lamp. v5 user observations confirm normal manual recovery; its SD log is still pending. Nikon bridging remains a proposal.

已测 GF-2 的附件类型为 0x11。v4 完整 C0/A6 序列未唤醒闪光灯；v5 用户确认手动恢复正常，SD 日志仍待读回。尼康闪光灯桥接仍是研究方案。

## Resources and scripts / 资源与脚本

| Topic / 主题 | Evidence / 依据 | Report / 报告 |
| --- | --- | --- |
| TTL file-operation failures / TTL 文件操作失败 | Contributor report; root cause unresolved / 社区反馈，根因待查 | [Filesystem comparison](gr4-ttl-filecopy-filesystems.md) |
| Resource writes and JPEG handling / 资源写入及 JPEG 行为 | Camera-specific experiments / 按机型记录的实验 | [GR IV](../firmware-and-shutdown-image-research.md#已验证的写入原理), [Urban](../gr3x-urban-160-shutdown-image.md), [GR IIIx HDF](../gr3x-hdf-160-shutdown-image.md) |

## Reading order / 阅读顺序

1. Read the container and system-layout sections to identify the sample and address space.
2. Follow the Debug report for examples of tracing configuration, messages, controllers and key events.
3. Compare static conclusions with the device observations and corrections in the [log](../research-log.md).
4. Pick an [open question](open-questions.md) and record a reproducible experiment.

先确定样本和地址空间，再阅读 Debug 报告中的配置、消息、控制器与按键追踪。用日志核对实机观察及被撤回的推测，然后选择待研究问题开展实验。

The shutdown-image guides are collected under [feature expansion](../extensions/README.md). The documented resource interface is not a general firmware installer.
