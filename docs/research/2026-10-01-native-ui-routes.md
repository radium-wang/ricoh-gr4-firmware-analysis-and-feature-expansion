# GR IV：原生比例菜单入口与拍摄状态取样

承接 [XPAN RAM 核心批次](2026-10-01-xpan-ram-core.md)。本轮没有相机 RAM 写入、原厂函数调用、固件更新或 SD 文件替换。XPAN 尚未接入实际菜单和图像。

## 菜单路径身份更正

旧审计把 `0x53D9F714` 路径称为“主菜单”，把 `0x53DA3744` 称为“第二路径”。原厂源码名、RTTI、构造函数和工厂分支证实如下对应；旧日志保留，当前工具已更正名称。

| 项目 | ADJ 快捷菜单 | 设置菜单 |
| --- | --- | --- |
| 原厂类 | AdjModeController | SelectMenuController |
| 主虚表 | `0x53D9F6A0` | `0x53DA2C70` |
| 构造函数 | `0x531C048C` | `0x531DB284` |
| 对象大小 | `0x294` | `0x1E4` |
| 工厂成员偏移 | `0x84` | `0xB0` |
| 描述符基址、步长 | `0x53D9F714`、`0x5C` | `0x53DA2D20`、`0x4C` |
| 比例行索引 | 5 | 34 |
| 比例行地址 | `0x53D9F8E0` | `0x53DA3738` |

设置菜单的 `0x53DA3744` 实际是第 34 行的 count 回调起点，即行地址加 `0x0C`。UI ID `0x0200008A` 经原厂跳转表选择行 34。

工厂单例 `0x55080D40`，guard `0x55080D3C`，虚表 `0x53D94F08`。`0x53185F7C` 是直接调用的 GetController；工厂虚表两项为析构入口，不能把其中一项当成控制器创建拦截槽。

旧直接引用工具找到的 18 项是 MOVW/MOVT 相隔最多三个指令的固定子集，不是完整引用清单。不得据此推导“改完 18 处即可”。

## 设置菜单 ABI

行内回调偏移：count `+0x0C`，label `+0x14`，setter `+0x24`，selected `+0x2C`，confirm `+0x34`。每项为原厂 C++ member pointer 对，不能只当成普通函数地址数组。

- label `0x531D0CCC`：`r0` 为 controller，`r1` 为 GUI item，`r2` 为菜单索引。
- setter `0x531D2F70`：`r1` 为索引；confirm `0x531D8FFC` 调 setter 后刷新 `0x531D76E4`。
- selected `0x531D4898` 返回“这个索引是否选中”的布尔值，**不是当前索引 getter**。
- 顺序仍为 native ID `[0,1,3,2]`。第五项索引 4 不能直接送入这些原厂四项处理函数。
- 列表拥有者位置为 controller `+0x198`，不是早期猜测的 `+0x18C`。
- 注册列表回调的四字节 record 为 controller 指针；原厂 invoker `0x531D71AC` 解引用两次后进入 `0x531D7120`。这是 std::function 捕获形式，与 ADJ 的十二字节记录不同。
- 列表 `+0x168` 为 callback storage，`+0x170/+0x174` 为 manager/invoker。
- 原厂 `0x535711E4` 修改启用数量时先检查实际已分配 item 数。没有确认容量便增加数量，会进入原厂断言路径。

`check_gr4_ui_native_routes.py` 执行原始 ARM 指令，33 项通过：三个已有对象的工厂分支、UI ID 映射、原计数、四项 label/set/confirm 和十六种 selected 判断。GUI、属性服务和刷新为模拟；没有调用实机 UI，也没有验证 GUI 线程同步。

## USB 实机只读结果

两次固定槽查询，以及一次原厂 16MB 堆和 `0x55080000..0x550A0000` 扫描完成，固定回调、调用缓冲及拍摄属性均一致。

第二次查询前，用户已正常重启、打开“画面比例”菜单，再接回 USB。进入 USB 查询状态后，两槽仍为空；全堆没有 ADJ/SelectMenu 主虚表指针。此结果不能证明菜单从未创建，也不能独自证明是哪条销毁或重置路径清空了它们。

扫描只保存哈希和精确指针出现位置，不保存完整 RAM dump。发现：

- `0x55080D40`：ControllerFactory。
- `0x59A4B8B0`：图像尺寸计算器虚表指针。

随后独立 USB 查询核对图像工厂 `0x5539FC64`、guard `0x5539FC84`、原厂虚表 `0x53FD8B20`。其 `+0x14` 确实拥有 `0x59A4B8B0`，完整计算器虚表 64 字节与固件 `0x53FD89A0` 相同。构造分支只申请四字节对象，不能把其后相邻分配也算作对象。

尺寸方法 `0x538CFBF8` 还使用 `r3` 的宽度输出指针、栈参数的高度输出指针和 hard-float `s0`，不适合直接由三整数参数适配器调用。DNG 当前窗口、完整源图都调用同一方法；任何全局尺寸挂钩必须保留完整源图计算。本轮没有改动这个对象。

## 下一批候选包

`tools/build_sd_ui_snapshot.py` 生成 `devkit-output/usb-factory-20261001/ui-shooting-snapshot-v1/`。包尚未部署。

在不接 USB 的拍摄状态下，约开机 5、25、45 秒分别记录原厂工厂、菜单对象、列表和 callback record；随后进入原有 USB 协议 1801。读取仅使用既有 `SYS_md`，输出至新建 SD 诊断文件，最大 6120 字节。只跟随四字对齐、原厂堆范围内的指针；设置菜单 class 不匹配时不跟随其列表；文件长度检查在读取每个字节之前进行，防止相机 EOF 旧字节行为。

十项生成 TTL 控制流模型通过，覆盖对象缺失、越界、未对齐、错误工厂/菜单类、无效列表/捕获指针、旧文件保护和短转储。模型不证明相机执行时序或菜单生命周期。USB 主循环及其恢复脚本与旧 2059 字节版本逐字一致。

恢复方法：先正常关机，备份新实验文件后，将包内 `restore-startup.ttl` 还原为 SD 的 `script/startup.ttl`；完全停用则备份并移除自己放入的启动脚本、正常重启。该取样包没有相机系统修改需要撤销；这不等于未来真正 XPAN 挂钩已具备完整恢复。

## 记录

本轮文件均保存于 `devkit-output/usb-factory-20261001/`：`ui-native-routes-audit-v1/v2.json`、`ui-native-routes-live-v1/v2.json`、`ui-native-class-scan-live-v1.json`、`ui-and-calculator-owner-live-v1.json`、`ui-native-arm-check-v1.json`、候选包的 `manifest.json/flow-checks.json`。具体报告记录未安装状态与模拟边界。

下一步需要部署一次新启动脚本，在菜单活动期获取对象与容量证据。此后才能确定原生菜单挂钩、UI 线程同步、预览/JPEG/DNG 路由和完整卸载；不能将本轮只读定位或局部核心检查称为 XPAN 上机完成。

### 部署追加

用户将 SD 卡接回电脑后，确认卷 `GR-SD`、外置 FAT32、设备 `diskNsM`，卡上旧脚本 2059 字节及 SHA 与已核对的协议 1801 完全相同。已将旧脚本、`XPSESSIO.TXT` 备份到 `devkit-output/usb-factory-20261001/sd-ui-snapshot-deployment-v1/`，并将旧脚本另存为卡上 `XPANBK/STARTUP.BAK`，附 `README.TXT`。只替换了 `script/startup.ttl`，新 SHA `a9f66f0b154fd1d995d3f6ba87bf8486c04571233b51c3348b38d8eda5077de8`，写入后逐字读回一致。照片、其他原有文件保留，未移除旧实验日志。

生成时的候选 manifest 保留 `deployed:false`；实际部署事实单独记录在 `sd-ui-snapshot-deployment-v1/deployment.json`，没有覆写准备阶段证据。本批尚待相机执行和回读；操作说明为开机后立即打开画面比例菜单，保持至少 75 秒，再退出并接 USB，留出文件写入与脚本执行的时间。

## 2026-10-02：真实设置对象、第五槽及原生回调后端

用户按上述取样流程开机后接 USB。本次 `ui-snapshot-postboot-usb-v1.json` 显示脚本完成取样并进入 1801；随后两次 USB 原厂槽读取均确认实际设置控制器 `0x5A0E4CF0`，原虚表 `0x53DA2C70`，UI ID `0x0200008A`，比例行 34。此时控制器在 USB 状态下仍存在，**不得从先前空槽结果推导 USB 必定销毁菜单对象**。SD 上各阶段 BIN 尚未回收，脚本状态与 USB 对象证据不能代替这些文件。

列表 `0x5A0BB058`，向量范围 `0x5A0FE9F8..0x5A0FEA8C`：37 个已构造记录，底层向量申请 64 个指针的空间，当前启用数量 4。第五记录 `0x5A0EC720` 已拥有 `SelectMenuLineView` `0x5A0EBD20`，其自定义文字组件 `AsciiView` `0x5A0EC4A0` 也已构造。**37 是可用于启用检查的已构造容量；64 是向量分配容量，不能把额外 27 个槽当成已构造 GUI 对象。** 第五项无需挤掉原四项。

原四项 caption ID 顺序 `0x10B,0x10C,0x10D,0x10A`，对应菜单顺序 3:2、4:3、1:1、16:9。第五项当前未启用，caption ID 0，两个 AsciiView 的拥有文字指针均为零。

两项读取格式更正：

- std::function 的 manager/invoker 位于列表 `+0x170/+0x174`。旧合并报告误把 `+0x16C` 的存储填充当成 manager；正确值分别为 `0x531D5D0C/0x531D71AC`，捕获记录拥有者与控制器相符。旧报告保留，以 `ui-slot-details-live-v2.json` 为准。
- item record `+4` 是 **一个字节**的启用标志，原厂用 STRB 写入。`+5..7` 为填充，并非有效状态。第一份细槽报告的 `active_word` 是原始四字节转为整数，不能作为布尔状态使用；第二份报告改为 `active_byte`，四项为 1、第五项为 0。

### XPAN 文字接口与原生后端

`0x5357ADE0` 接收语言资源 caption ID，不能传入 C 字符串指针。已确认 `0x5357AE1C(item,const char*)` 使用 item `+0x100` 的 AsciiView，可传入 ASCII `XPAN\0`；其 `0x5356D1C8` 经原厂长度函数及 `0x538EA24C` 转为含结尾零的 UTF-16，申请 10 字节，指针由 widget `+0xF0` 拥有。相同文本释放临时新缓冲、保留旧缓冲；文本改变则释放旧缓冲。析构 `0x5356D010` 释放其拥有文字。标签不等于所要求的 XPAN 图标。

新增 `firmware/xpan_settings_native.c/.h`，按已核对的寄存器顺序绑定实际原厂 label、setter、confirm。索引 0..3 委派原 label；索引 4 使用 AsciiView，并仅向原选择处理函数传入索引 0。项目状态在原 setter 通知前提交，调用者必须持有状态锁，且所有观察者必须遵循同一锁。这里没有安装器，不可从脚本线程直接调用 GUI；也没有覆盖原刷新、导航、回调投递。

`settings-native-backend-v1/checks.json` 的 33 项离线 ARM 检查通过。执行实际链接后端、原厂 ASCII 长度/转换/比较和数量设置指令；分配、可见性、失效刷新、属性服务模拟。覆盖原四项、第五项、文字重复/替换后的申请释放、crop 保留、selected 布尔谓词、错误类/行/索引拒绝及 padding 保留。未验证实机渲染、线程同步或照片输出。

还执行了原三种确认入口：列表 invoker、确认按钮、事件 `0xE0` 都会将选中的第五索引直接送到原四项 setter/confirm，故三条路径均需拦截。原刷新 `0x531DA9D4` 会重新设为四项；向下事件 `0xDB` 仍读取 ROM count 4。只修改列表 count 或一个 invoker 并不充分。

### AppMain 原厂消息队列候选入口

从原厂 AppMain 任务的 `0x5323B9F4` 主循环追踪到 MessageMediator `0x55087470` 和 `0x5325C8D0` 消费循环。mediator 是普通对象，**首字为当前 controller ID，不是虚表**。`0x5325C768` 在原厂互斥锁内复制十二字节消息，释放锁后设置事件位 1；消息格式为 `u16 code@0,u32 data@4,u32 handler@8`。code `0x17D` 绕过当前控制器事件分派，随后调用 `handler->vtable[0](handler,code,data)`。消息析构 `0x5323B804` 不释放 handler，故生命周期必须由实验持有和确认，不能凭析构自行 free。

USB 只读 `ui-queue-live-v1.json` 确认本次 AppMain ID `0x0100008E`、TCB `0x570BB108`、原类/配置和队列布局。ID 不同于旧开机的 `0x01000082`，不得硬编码旧任务编号。环地址 `0x59B93118`，64 槽、mask 63，读取时 count=0、head=tail=39；这是取样值，不是持续空闲保证，也没有执行界面线程上的回调。

新增 `firmware/xpan_ui_queue_native.c`：在同一原厂生产者锁内检查布局与容量，队列满时退出而不触发原厂断言；只接收 `0x17D` 类型。结果 1、4、5 表示消息已提交（分别为已通知、通知失败、解锁失败），均禁止再次投递或释放仍可能被消费的 handler。自身不申请、不释放对象，不改变菜单或图像。`ui-queue-arm-check-v2.json` 15 项离线检查通过，锁/通知/控制器服务为模拟。原厂复制、分派及只写目标首字的 ROM 短函数也在模型中执行；实机投递和跨核可见性仍未验证。

本轮未写相机 RAM、未更改相机文件/设置、未刷固件。USB 回调、scratch 和拍摄属性前后保持原值。最后只读发现脚本 names pointer 已为零、count 28 保留；不能再跟随旧变量表发起调用。下面的追加检查发现卡上旧取样脚本不能仅靠重启复用，因此没有提前要求用户重启。

下一批将先核对消息投递与回调回收，再据此实现 UI 线程内安装/撤销；真实预览、JPEG/DNG 与 XPAN 图标仍待接入。不要把本轮文字后端、队列定位或离线 ARM 检查称为 XPAN 已上机。证据与源码哈希记录于 `ui-development-evidence-v3.json`。

### 下一批可执行入口及启动复用修正

已准备 `tools/mtp_factory_ui_queue_trial.py`，默认只读，显式 `--trial` 使用既有 1801 和 16 调用的装载/恢复流程。固定 512 字节入口 SHA `ed27858244e5b73affe7de6a8ad8c8f2cd49077abc9549dc696d603855c5120e`（428 字节代码加填充），入口含 ISB。消息、handler 和只含原厂 ROM store 入口的 vtable 均置于同一原厂申请的 8KB 内；该 ROM 短函数只写 handler 首字并 BX LR，不调用图像/菜单。只有消息已消费、原厂 RAM 调用已返回、回调的最后一次自有内存访问已确认后，才恢复 1024 字节自有区域、发布恢复缓存、恢复独立缓存输出、释放。消息 pending/提交不确定时保留分配，拒绝重投递和旧开机指针。

`ui-queue-arm-check-v3.json` 同一 15 项检查执行带 ISB 的最终入口；`ui-queue-lifecycle-check-v3.json` 11 项主机模型通过，覆盖成功整批、部分上传、缓存拒绝、队列忙/满、通知失败、消费延迟及重复投递拒绝、两处断线、发布已提交后的 USB 错误和跨重启拒绝。实际 UI 消费在该模型中模拟，实机尚未运行。

**启动复用问题在请求用户重启之前查明：** 已部署取样 v1 的任一指定 BIN 存在保护会执行 END，结束整个启动脚本，USB 主循环也不运行；不是仅跳过取样。因此重启不能恢复本次调用窗口。新生成器改为跳转到 `ui_skip_capture`，保留旧文件并继续发布 1801。候选 `ui-shooting-snapshot-v2` 已生成，SHA `e565e66a81069e252608df4d021f98079b2e03d62fc635a7ccd5ad4918058c50`；12 项检查包含**实际生成并插入的前缀**在正常/旧文件两情形均发布 1801，没有读取 EOF 或覆盖旧记录。新包尚未部署。

为减少下一批操作，`ui-queue-next-batch-v1/` 直接准备已经验证的原 2059 字节 USB 协议脚本（SHA `221d79821b4f7cbd2028477001529b02dcb8f9bfcf016cecffa11c71cf071c59`），不再要求菜单取样。下一次接卡一次完成现有 BIN/日志归档、原脚本备份和恢复原 USB 脚本；之后放回相机开机直接接 USB，整个投递批次不用换卡或等待 75 秒。无相机写入已发生，所有新包均为 prepared/deployed:false。

### 2026-10-02 SD 实际回读与 USB 脚本恢复部署

用户再次接卡后确认 `GR-SD` 为外置、可写 FAT32，当前设备 `diskNsM`（设备编号与上次不同）。旧启动脚本 SHA 与取样 v1 一致；卡上 `XPANBK/STARTUP.BAK` 与原协议 1801 的 2059 字节脚本完全一致。

所有实际存在的 12 个取样 BIN、`XPSESSIO.TXT`、旧启动脚本和两份恢复说明/副本均复制到 `sd-ui-queue-deployment-v1/archive/`，逐字回读核对，长度和 SHA 保存于 `archive.json`。A 阶段只产生 ROOT/IM，设置控制器槽为零；B、C 各产生 ROOT/SET/LIST/CALL/IM，ADJ 槽均为零。两组设置控制器 `0x5A0E4CF0`、比例行 34、列表 `0x5A0BB058`、37 个已构造槽、64 个向量分配槽、启用 4 项；manager/invoker `0x531D5D0C/0x531D71AC`，捕获记录持有同一控制器，均与 USB v2 身份证据相符。图像计算器三组均为 `0x59A4B8D0`。详细解析保存于 `snapshot-results.json`；这些分次读取不能当成原子快照或持续生命周期保证。

归档核对完成后，已恢复原 2059 字节 USB 启动脚本，写入后逐字回读一致。只移除上述已归档的 12 个 BIN 和一份自建日志；保留卡上的恢复副本、照片及其他文件。DCIM/RICOH 文件名称与大小清单前后完全一致。实际写入与清理事实保存于 `deployment.json`，候选包的生成 manifest 不覆写。已同步并安全弹出 `disk5`。

本次没有相机 RAM 写入或固件更新，XPAN 尚未安装。下一步为放回卡、开机立即连接 USB，通过 `mtp_factory_ui_queue_trial.py` 完成整批原厂界面线程消息诊断；无需再次执行菜单取样或等待十分钟。

### 2026-10-02 AppMain 投递实机整批通过

用户放回 SD 并开机接 USB 后，只读预检确认协议 1801 新会话、原回调和 scratch、队列及固件代码 pins。本次 AppMain ID `0x0100007C`、TCB `0x570B5708`、队列 `0x59AE2670`；这些身份与上一开机不同，不能复用旧地址。队列容量仍为 64。

`ui-queue-session-trial-v1.json` 完整记录 16 次已完成调用，逐次原回调/scratch 恢复均确认。CPU=1，TTBR `0x53004000`，SCTLR 原值 `0x00C51C7D`，8KB 分配 `0x5A0C28B0`，对齐代码 `0x5A0C28C0`。第 10 次调用固定队列入口返回 1，读回 ROM 回调对自有 handler 的完成标记 `0x17D`；没有投递第二次消息。恢复 1024 字节自有区、完成原厂缓存/屏障序列、恢复独立 20 字节缓存输出后，第 15 次 free 返回 1，第 16 次诊断返回 3。最终 `cleaned_up/cleanup_verified/allocation_free_verified` 均为 true，分配不再持有，拍摄属性前后 `000000803f`。

另开独立只读 USB 会话，`ui-queue-posttrial-readonly-v1.json` 确认回调和缓冲、拍摄属性原值，队列 count=0、head=tail=38。该值是读取时的状态，并非所有消费均由本次诊断引起。过程中 6 次 names-holder 短暂为空被原有整组身份重读保护捕获，未跟随空指针；异常记录保留，不改变整批成功事实。

这证明自有队列代码在 Script 上运行并让原厂 AppMain 执行 ROM 回调，**尚未证明 RAM 回调代码在 AppMain 上运行，也没有 GUI 操作、原生菜单安装或图像挂钩**。本次硬件所用主机源码及新菜单代码已复制保存于 `ui-source-snapshot-v6/`，证据哈希在 `ui-development-evidence-v6.json`。

### 第五项路由代码与下一批 RAM 界面回调

新增 `firmware/xpan_settings_routes.c/.h`，实现原刷新/激活后的五项呈现、5×60 像素列表高度、原生列表导航的五项环绕及重复键边界，以及 list/button/E0 三路确认保护。原 crop 和四项索引保留，XPAN 映射到原 3:2 来源索引 0。启用第五项要求预览/JPEG/DNG/图标四个 ready 位全部满足，当前实机没有这些 hooks，不能设置为就绪。`settings-routes-native-v1/checks.json` 56 项离线 ARM 检查通过：执行链接路由、原厂列表数量/导航/矩形指令；GUI 文字、属性、生命周期、除法及布局服务为模拟。尚无 ABI 安装适配、克隆虚表支持、撤销/析构与状态失效防落入原四项处理器的安装生命周期。零返回不授权把索引 4 交给原厂，接口已明确记录。

下一包 `ui-inspect-native-v2` 为固定 2048 字节候选，只读 RAM 回调和队列入口 SHA `ba2eefef4b083b19793f3c65024a8a5d221087a7f41628b54b456a7a3f7ba38e`。AppMain 的 RAM 回调按原厂范围/class 校验读取比例控制器、五个记录及 AsciiView、图像计算器，输出至自有 256 字节报告。汇编出口恢复 r4/lr 后跳入 ROM `0x5325CA0C`，该 ROM store 是最后一次自有访问；完成标记之后没有 RAM 指令，允许在确认原提交调用也返回后恢复/释放。数据与代码共备份/恢复 4096 字节，缓存输出置于 +6144，仍在同一 8KB 申请内，16 次调用、原 SD 脚本不变。

候选 15 项队列、4 项 RAM 回调 ARM 检查通过；后者确认只写自有报告/栈/marker，不改菜单对象，缺失菜单、错误比例行及构造容量不足会给出状态。扩展报告 6 项生命周期模型和原队列 11 项回归模型通过，覆盖恢复、pending 保留、部分上传及断线。`ui-inspect-native-v1` 保留构建时寄存器掩码断言失败产物；实际编译 r4/lr 掩码为 `0x4010`，修正模型预期后另存 v2，未上机运行 v1。

由于本次开机已用完 16 编号，已请求用户正常重启、打开一次比例菜单后接回 USB。无需再取卡。候选尚未上机；第五项、XPAN 图标、预览和 JPEG/DNG 输出均未安装。

### 2026-10-02 RAM AppMain 回调、图像对象查询实机完成

用户重启、打开比例菜单并重新连接后，首次只读预检因变量名表在读取中变化而拒绝，未启动任何写入；空输出文件 `ui-inspect-preflight-v1.json` 保留为失败产物，后续完整预检保存于 v2。新会话协议 1801、go/done/token 均为零，AppMain ID `0x0100007E`，所有原厂 pins 通过。

`ui-inspect-session-trial-v1.json` 记录第二个完整 16 次硬件调用批次。固定 2048 字节代码在 Script 投递后，**自有 RAM 回调实际在 AppMain 执行**，256 字节报告 magic `0x58504931`、status=0、AppMain ID 与预检一致。报告确认控制器 `0x5A097568`、比例行 34、列表 `0x5A093AB8`、37 个已构造槽/64 个向量容量、原四项启用。第五记录 `0x5A092E50`、item `0x5A092450`、AsciiView `0x5A092BD0` 存在，未启用，文字拥有指针为零。图像计算器 `0x59A4B8C8`、虚表 `0x53FD89A0`；manager/invoker 和捕获拥有者均匹配。

回调汇编末尾跳入原厂 ROM store，marker `0x17D` 证明最后自有访问完成；原 Script 提交调用也返回 1。随后恢复全部 4096 字节自有区域、原厂缓存/屏障发布及独立输出，free 返回 1、末次诊断返回 3。最终 `cleaned_up`、`cleanup_verified`、`allocation_free_verified` 均 true，USB 回调/scratch 每步恢复，拍摄属性仍为 `000000803f`。没有留装菜单或图像挂钩。

在同一连接继续只读遍历已核对的应用堆和两段静态区域，仅保存哈希、类指针出现位置和入向指针候选，没有保存完整 RAM 转储。`image-owner-candidates-live-v1.json` 找到 DNG Kb636 类指针 `0x59A4B900`（入向字段 `0x55397510/0x59A4B8E0`）、LiveViewControl `0x59CE2358`、LiveViewProcess `0x59CD5438`。各虚表原厂 pins 和遍历后首指针匹配；**不因此认定对象分配尺寸、完整拥有链、线程同步或像素缓冲界限已验证**。独立 USB 菜单深读与 RAM 回调的控制器、五个记录/item/AsciiView/启用字节/文字指针、计算器全部相符，交叉证据 `ui-inspection-independent-crosscheck-v1.json`，原回调/scratch/拍摄属性再次确认未变。

### Kb636 DNG 独立虚函数适配器

离线 RTTI/原厂代码确认 Kb636 虚表 `0x53FCF430`，`+0x34` 为 `0x5387E220`，与直接叶函数 `0x5387E108` 的 ABI 不同：虚函数 `r0=self,r1=width*,r2=height*,r3=left*`，栈为 `top*,aspect,flag`，hard-float `s0=crop`。原厂参数写入器 `0x5387E2AC` 比较该槽与原方法；相等时直接调用叶函数，不相等时通过 `0x5387E4C8..0x5387E4F0` 使用上述虚函数 ABI。因此无需以全局尺寸方法覆盖完整源图路径。此为静态入口依据，尚未修改实机虚表。

新增 `firmware/xpan_dng_native.c/.h`：先按全部原始参数调用原虚函数，只有绑定对象/虚表、ready、捕获计划、aspect、crop 全匹配时替换当前四个裁切输出。绑定更新和安装/拆除都要求图像 worker 停止并排空；对象/计划/代码需一直存活，尚未实现此原厂同步接口。`dng-native-virtual-v2/checks.json` 9 项离线 ARM 检查通过，执行链接 hard-float 适配器、原虚函数包装器及完整原参数写入器的替换分支。普通画幅/禁用/无绑定/错误对象、虚表、crop、aspect、计划均保留原输出。最后一项保留完整源图及 source origin/dimensions，只将当前窗口改为模型 `6192×2288 @ (54,978)`。尺寸叶函数与工厂/crop 查询模拟，不能作为实机 RAW 编码、Bayer 对齐或 DNG 输出验证。

MOVW/MOVT 对的局部候选查询没有匹配，记录保留；继续 literal-load 查询找到 DNG 构造 `0x5387F154` 与预览过程构造线索，报告 `image-owner-code-refs-v1.json/image-owner-literal-refs-v1.json`。这些检索结果不代表没有其他调用或已确认完整拥有关系。

用户询问是否可关机时，两个 RAM 批次都已结束并完成恢复/释放，所有 USB 会话已关闭。已告知可正常关机、SD 留在相机。后续工作在电脑上进行；第五项、预览/JPEG/DNG 实机输出与图标仍未安装，完整安装/卸载还需原生 ABI、拥有关系、图像 worker 同步和像素路径接入。

### 2026-10-02 JPEG 原生尺寸适配与图像任务合并查询

新增有调用范围检查的 hard-float JPEG 适配器。`jpeg-native-arm-v8/checks.json` 31 项离线 ARM 检查通过，执行原厂尺寸、来源配置、描述符复制/裁切/目标尺寸代码，保留完整来源。三种 crop 从完整模型描述符出发，未执行真实像素或编码、未安装共享计算器表。

用户接 USB 后，`capture-pipeline-live-v1.json` 同一次连接核对 JPEG 缩放、预览控制/处理任务的注册表和 TCB 身份，及预览尺寸/参数服务指针。192 个任务，本次各地址重新定位，原回调/scratch/拍摄属性未变。继续进行有限参数只读查询，没有 SD 插拔或相机写入。详细结果、地址与失败产物见 [JPEG 原生路由记录](2026-10-02-jpeg-native-route.md)。XPAN 尚未安装。
