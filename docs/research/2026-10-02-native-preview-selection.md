# 2026-10-02：参照原厂 16:9 的窗口选择与属性提交

## 结果与边界

按用户要求沿用其他画幅的控制方法，追踪了原厂 3:2、16:9、特殊窗口的选择和后续发布。新增 `xpan_preview_route.c/.h`，把共享拍摄计划的双窗口计算与原厂裁切分支选择组合起来，纳入 portable unity 模块。

**XPAN 未安装。** 新代码只准备参数，不写原生对象、不发消息。49 项离线 ARM 检查执行了原厂选择、消息生产及属性提交代码；对象、队列、锁、分配/释放及 memcpy 服务为模型，不是显示像素或拍摄验证。PREVIEW_READY/ICON_READY 仍为 false。第五项菜单、真正图标、JPEG/DNG 安装及同步、实际显示消费者/AF 坐标、独立恢复入口和自动启动加载仍待完成。

本轮实机只用 USB GetData，未调用原生图像函数、申请 RAM、SetData、修改 SD 或固件。相机可正常关机，卡上旧实验脚本未更换。

## 原厂 16:9 路径

固定样本 SHA-256：`c4e597c7c9ca1bc181b30e35139ed90a4fd876ddcca14f12be0e00b6702233ae`。`audit_gr4_preview_selection.py` 同时核对上一轮窗口审计、局部代码哈希和直接分支。

| 路径 | 行为 |
| --- | --- |
| `0x5362E454` | 从原属性取得 aspect/crop，调用 `0x538876B8` 计算窗口，再调用选择器 |
| `0x5362E3F0` | 原模型方法返回 1 时选 2；16:9、其他内部裁切画幅或倍率大于 8192 时选 1；普通 3:2 满幅选 0 |
| `0x536342BC` | LiveViewProcess 的另一路选择；特殊标志/模式可选 2，须保留 |
| `0x53887D48` | 原锁下把 full `+4`、crop `+24`、special `+54` 中的一组四字 W/H/X/Y 复制到 selected `+64` |
| `0x53887DD4` | 把 selected 写到静态 16 字节缓冲，通过信息对象 `+253C` 服务发布 |
| `0x53754730` | 原分配器申请 16 字节并复制窗口，以 `0x84` 消息发给服务；原队列参数 `[1,0,result_pair,2]` |

**只改 crop 窗口还不够：** OFF 且原生 aspect=0 时，selector=0 仍会发布 full。XPAN 源图保持原生 aspect=0，在自己的活动路径准备 selector=1；不用项目菜单值 4 去索引原厂比例/图标表。常规画幅、无效计划、错误倍率、selector=2 或未知 selector 都交还原生路径。

新 `gr4_xpan_preview_route_prepare()` 接受共享捕获计划、crop 倍率、域、原双窗口及原 selector，输出 52 字节：双窗口 32 字节、selector=1、selected 16 字节。只有全部校验/计算成功才写输出。此接口不是原生 ABI 包装器或安装器，调用者的同步、计划生命周期和图像消费者仍未绑定。

## 实机只读：消息的接收表

原 `CommonPropertyIf` 消息分派代码使用 RAM 表，而不是 ROM 文件的同地址偏移。两组固定 `0x84` 表项为：

| 表项 | 实机八字节 | 解码 |
| --- | --- | --- |
| set `0x55019318` | `94d8745300000000` | direct method `0x5374D894`，调整值 0 |
| get `0x55018A50` | `4cb9745300000000` | `0x5374B94C`，仅返回 1；不是窗口读取接口 |

`0x5374D894` 从 service `+518` 取 `CommonPropertyManager`，调用 `0x537614F0` / `0x53761418`。后者把输入写到 pending property `+F08`，比较/更新 `+6C0`；有变化时在 dirty list 记录属性 ID `0x84` 和通知 token `0x28501F01`。随后 `0x5375CD2C` 交换 current/pending 指针，并复制 `0x1090` 字节，使另一份属性副本一致；接收方法按 payload 所有权标志释放消息缓冲。

因此窗口恢复的候选流程也应经过原更新/通知链，仅回写几个数值不足以覆盖副本与订阅者。**这里只验证通知记录，未验证真实队列通知交付、屏幕刷新、AF 或跨核/任务恢复。** 该服务为 CommonPropertyIf，不能直接把消息 0x84 等同于已找到 LCD 驱动。

新增可选 `--preview-selection` 合并读取五组预览信息、特殊/selected 窗口、service 与 fresh factory holder、两个固定表项、静态发布缓冲，以及两份属性的两个固定窗口字段。前后复核身份/链接及表项。CLI 记录 session 是否由本探针打开和 CloseSession 响应；不会声称关闭未由自身打开的会话。

### 实际读数

成功报告 `capture-preview-selection-live-v2.json` / `capture-preview-selection-live-v4.json`：

- 新鲜 LiveViewInformation `0x59A550B0`，CommonPropertyIf `0x59618EB0`，manager `0x59619580`；没有复用旧开机地址。
- selected 和静态发布窗口都为 `[2949120,1966080,0,0]`；special 为 `[2654208,1490944,147456,237568]`。这不是 XPAN 或像素验证。
- current/pending 属性地址 `0x5D7A0028` / `0x5D7A10B8`，`+6C0` 与 `+F08` 的四组窗口均为同一个满幅值。
- JPEG 配置为空、源宽高/pitch `[0,0,0]`，仍不能从 USB 状态确认拍摄帧。
- 回调、scratch、拍摄属性和任务注册表身份前后一致；没有相机写入。
- OpenSession 返回已打开状态，`opened_by_probe=false`、`close_response=null`，接口已 release/dispose。**本探针未关闭既有 PTP 会话。**

### 边界拒绝与故障保留

第一次 claim 被 macOS `ptpcamerad` 占用拒绝，无 PTP 命令。SIGTERM 后服务未及时释放；改为只终止当前用户精确路径的该服务，同一进程等待 50 ms 并立即 claim 后成功。只处理这一服务，不关闭 Photos 等应用。

追加属性字段读取的 v3 被旧 RAM 边界拦截：属性副本位于 `0x5D7...`，超出旧应用指针 guard；此前有限读取已发生，但属性窗口未读，批次没有成功报告。保留 `capture-preview-selection-attempt-v3-failure.json`。

没有扩大通用 `ram()`：新增只读 `property_image_ram()`，仅跟随新鲜 manager 指向的有限 `0x1090` 跨度，验证高 arena 范围、对齐、长度、样本及实机初始 section 描述符，再读其中两个固定 16 字节字段。描述符是 identity mapped/AP=3。**初始表一致不能证明当前任务 TTBR、所有权、原子取样或允许写入。** v4 成功，未读取整份属性或全 RAM。

## 离线检查与归档

最新 `preview-selection-arm-v5/checks.json` 的 49 项：

- 原厂六个内部画幅 × 三倍率：真实 chooser、selector、消息生产、接收端属性提交；包括原 16:9，而非重新写一份比例公式模拟原厂。
- 模型特殊选择器及六种原 process 条件，保留 special/zoom 路径。
- 三种 crop × 原 selector 0/1：XPAN C 参数经过原 selected/publication/接收代码；保留原 full/special，输出无越界，输入计划/窗口不变。
- 三种 crop：在同一组属性副本上恢复原窗口，不重置模型状态，验证重新记录变更；未验证通知交付或实机恢复。
- 反例 selector=0 仍发布 full；14 类无效/常规/特殊输入不改输出并交还原路径。

初始 ARM v1 把尾调用 B 当作 BL 审计，v2 漏映射锁入口引用的 ROM 常量页；失败留存。v3 46 项通过；v4 追加真实接收端；v5 加同状态撤销，49 项通过。原硬件服务仍为模型。

读取模型 v1=10、v2/v3=12、v4=15 项，覆盖身份/ROM/holder/owner/table 变化、短读、空指针、属性副本变化及高 arena 映射拒绝。旧预览读取六项在新版脚本上复核通过。统一模块主机检查和 ARM 编译无未解析符号，`xpan-core-preview-route-v11-checks.json`。

本轮源文件和上述全部成功/失败报告保存到 `ui-source-snapshot-v11/`、`ui-development-evidence-v11.json`；不覆盖 v10。RAM 修改与 SD 自动重新载入仍是目标方案，当前卡上的实验调用脚本不是 XPAN 自动安装器。
