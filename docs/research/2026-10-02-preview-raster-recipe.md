# 2026-10-02：活动取景尺寸、配置对象与拍摄状态取样（v12）

## 本轮状态

XPAN 尚未安装，仍不能据本轮记录宣称相机已经能拍 XPAN。新增活动取景配置适配和局部恢复代码；原生菜单第五项、实际预览/AF、JPEG/DNG 输出、图标、任务同步/缓存与安装器、自动启动加载仍待接入。

本轮 USB 只用 GetData：未写相机 RAM、未分配或调用原生图像函数。实机观察到 USB 状态下八个配置槽全部为零。这个状态说明 USB 读数不能提供活动取景配置，单凭它不能证明对象是在接 USB 时释放，还是尚未构造。已改为准备在拍摄状态采集的 SD 包。

用户接卡后，已部署 `preview-shooting-snapshot-v12b`：只替换 8280 字节 `script/startup.ttl`，创建 `XPV12` 目录及原脚本恢复副本/说明。原脚本和日志已归档核对，181 个 DCIM/RICOH 文件的路径及大小清单不变；没有修改内部文件或固件。**脚本尚无相机执行结果。**

## 原厂活动尺寸路径

固定原厂样本 SHA-256：`c4e597c7c9ca1bc181b30e35139ed90a4fd876ddcca14f12be0e00b6702233ae`。`audit_gr4_preview_recipe.py` 固定九组代码/类表哈希、直接调用和集合槽写入指令。

`0x5388AED0` / `0x5388B45C` 为尺寸包装器，内部为 `0x5388A954` / `0x5388AF1C`。manager `+A` 为尺寸档、`+9` 为源模式、`+B` 控制另一条外部尺寸路径。72 项原 ARM 检查执行原厂方法，manager 为合成对象，无实机像素。

| 尺寸档，模式 0，两个 flag=0 | 3:2 | 16:9 | 4:3 | 方形 |
| --- | --- | --- | --- | --- |
| 7 / 30 | 720×480 | 720×404 | 640×480 | 480×480 |
| 29 | 1080×720 | 1080×608 | 960×720 | 720×720 |

另测模式 3、flagA=1、flagB=1。原厂参考尺寸可能有意保持满幅，不能全局替换尺寸查询。404/608 是原厂档表结果，**没有据此确认硬件对齐为 2 或 4**。

## 原厂配置 helper ABI

`0x53647498` 是 376 字节直接 ROM 调用，参数为 `r0=recipe,r1=aspect,r2=extra,r3=mode`，栈参数 crop Q13。两条上游调用为 `0x53639A48` 和 `0x5363A924`。后者还进入原厂图像配置方法，但本轮未执行驱动。

| 字段 | 含义 |
| --- | --- |
| recipe `+334` | resolution manager |
| `+BD6/+BD8` | 活动宽高 |
| `+BE0/+BE2` | 相对原始尺寸的居中 X/Y |
| `+BE4/+BE6` | 保持 aspect=0 的完整参考宽高 |
| `+BEA/+BEC` | 档位基础宽高 |
| `+BDC` | 原厂横向 padding，XPAN 代码不改 |
| `+BE8/+BEE/+BF0` | extra、mode、crop Q13 |

`xpan_preview_recipe_native.c` 先按原 ABI 调用 helper，再匹配 plan、owner、集合成员、manager、模式、倍率及 ordinary still flags，最后调用 portable adapter。仅允许已检查的档 7/29/30；特殊/外部/视频路径交还原厂。

**这不是虚表挂钩。** ROM helper 没有可供当前包装器直接替换的虚槽，尚无 call-site 重定向或安装代码。binding 的 ready 只是调用方契约，没有设置 PREVIEW_READY。

Portable apply 只改 `+BD8/+BE2`，保留宽、完整参考和基础尺寸。24 字节 ARM undo 记录目标、原/应用 H/Y、原宽及 crop Q13；重复原厂重新生成要求目标/原尺寸/倍率一致。restore 要求 owner 已暂停，只接受原值或已知应用值，遇到新宽、参考尺寸、倍率或未知位置拒绝覆盖。

45 项 ARM 检查覆盖原厂四比例、三档、三种焦距 crop、新参数、原厂重生成、同一对象撤销及冲突拒绝。alignment=2 仅为模型假设，不是实机 readiness。恢复目前仅局部 recipe 字段，不包括消息、属性副本、LCD/AF 或完整模块卸载。

## 集合关系的纠正

反汇编确认原调用 `0x5363F98C` 从 process `+3B0` 取集合，再调用 `0x53648034`。构造器从 this+4 起，以 preincrement 写八个对象到 `+8,+C,+10,+14,+18,+1C,+20,+24`，每个申请 `0x19F0` 并调用 `0x53641F90`。recipe 主虚表为 `0x53EB16E8`。

早期离线模型先误把 process `+3AC` 当 recipe，后又把其 `+8` 当集合槽；v2/v3/v4 因使用合成数据仍通过，不能作为实机关系依据。v5 修正到 `+3B0` 集合，v6 增加恢复记录冲突和 manager 模式限制。所有旧成功/失败报告保留，均无相机写入。

## USB 读数与失败保留

1. attempt v1：GetDeviceInfo 无回包，未开始 RAM 采集，用户随后只重接 USB。
2. attempt v2：正常回包；八个槽不满足唯一对象条件，批次拒绝，未解引用 recipe。
3. attempt v3：合并属性读取时 current/pending 所有权变化，批次拒绝；不能当稳定快照。
4. live v4：去掉正在变化的属性副本，读取固定集合 header/slots，不跟随任何槽指针；成功并保存逐次有限读数。

v4 实际 process `0x59D10470`，manager `0x59A589C0`（类 `0x53FD19F8`，档 7、模式 0、external=0），集合 `0x59BC83B8`。集合 48 字节全部为零，八槽为空；JPEG 源尺寸 `[0,0,0]`。回调/scratch/属性/注册表前后不变，PTP 会话已由其他客户端打开，本探针没有关闭它，只释放自己的接口。

读取工具的严格八对象模式仍拒绝空/重复槽。新增 `--preview-collection` 仅观察固定 header，不跟随指针，也不许可安装。10 项原读取模型和 6 项集合状态模型通过。

## 合并拍摄状态包与恢复

`build_sd_preview_snapshot.py` 使用先前实际验证的 TTL 二进制读取 helper，追加的 shell 命令全部是 `SYS_md`。从固定注册表根 `0x553A0030` 重新找 native worker；节点遍历上限 512，验证任务 identity，对所有动态范围/对齐/长度设限。

三个阶段最早为 15/75/135 秒，实际还有未验证的 SD 读写耗时。采集 process、manager、information、特殊窗口标志、八槽/recipe identity/link/raster、JPEG 状态和结束 owner/slot 字段；不复制像素。每阶段诊断数据上限包含 512 节点，三阶段总上限 45924 字节；目录项/簇占用另计。字段不是同一帧快照，没有锁住图像线程；分析结果永不设 PREVIEW_READY。

所有文件集中在 `XPV12`，文件名不超过 8.3。首次候选用 `COLLECTION` 长名，发现卡上旧 `XPSESSION.TXT` 被机身写成 `XPSESSIO.TXT` 后，在部署前改为 `COLL`；旧候选保留但未部署。新包 14 项 TTL 控制流检查通过（包括边界、短读、循环上限、既有输出和 USB handoff）；离线分析三案例通过。

存在 ROOT 文件时保留原诊断并跳过全部采集，继续原 USB 协议 1801，不会提前 END。`analyze_sd_preview_snapshot.py` 只处理电脑诊断副本；输出缺失/变化、类身份和尺寸，不能把字段关系当作帧拥有/同步证明。

恢复方法：相机正常关机，将卡接电脑，把 `XPV12/RESTORE.TTL` 的原 2059 字节内容复制到 `script/startup.ttl`，回读应为 SHA-256 `221d79821b4f7cbd2028477001529b02dcb8f9bfcf016cecffa11c71cf071c59`。诊断先完整归档再移除 XPV12。此方法撤销本轮 SD 取样脚本，不是尚未安装的 XPAN 模块恢复证明。

本轮源/依赖/失败/报告保存在 `ui-source-snapshot-v12` 和 `ui-development-evidence-v12.json`。v11 的 106 个哈希先检查不变；统一模块主机检查及 ARM 编译无未解析符号。部署备份、照片清单和写入回读位于 `sd-preview-deployment-v12b/deployment.json`。
