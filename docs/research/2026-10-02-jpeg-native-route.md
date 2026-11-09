# 2026-10-02：JPEG 主图尺寸与预览任务

XPAN 仍未安装。原生 JPEG 适配器及 ARM 检查在电脑完成，随后用户连接相机，进行两组合并 USB 只读查询；没有刷固件、修改 SD 或相机 RAM。

## JPEG 原厂入口与候选适配器

`BackResizeMacroProcess` 主虚表 `0x53ECFC58`、RTTI 名称 `22BackResizeMacroProcess`。`+0x20` 指向 `0x536FB8AC`，经请求类型选择 `0x536FAE10` 后尾跳处理主体 `0x536FB694`。不同类型、缩略图及其他调用尚未完整核对。

请求 `+0x34` 的配置指针保存到过程对象 `+0x8A48`。`0x536FB040` 用配置 `+0xB70/+0xB72` 从源 YCbCr 描述符取居中窗口，写入过程内 `+0x8A4C` 描述符；两平面地址均增加 `vertical_offset*pitch+horizontal_offset`，保留 pitch。`0x536FB0DC` 计算目标尺寸并写目标描述符 `+0x10/+0x12`。

| 尺寸查询 | 计算器调用返回地址 | 行为 |
| --- | --- | --- |
| 来源窗口 | `0x53711460` | 发布器写 `+0xB70/+0xB72`；XPAN 候选覆盖范围 |
| JPEG 目标 | `0x536FB22C` | BackResize 目标宽高；XPAN 候选覆盖范围 |
| 发布器完整来源 | `0x537114A4` | size=0/aspect=0/crop=1，写 `+0xB74/+0xB76`；必须保留 |
| DNG 完整来源 | `0x5387E1C4` | 必须保留，不允许统一裁掉全 RAW 尺寸 |

新增 `firmware/xpan_jpeg_native.c/.h`。实际 hard-float ABI 为 `r0=self,r1=size,r2=aspect,r3=width*; stack=height*; s0=crop`。适配器先调用原尺寸方法 `0x538CFBF8`；仅绑定对象/克隆表、ready、合法计划、3:2、crop、指定 size 和两处返回地址匹配时替换。来源还要求原尺寸与计划来源一致；目标按外部对齐要求计算同宽居中 XPAN 窗口。

**没有共享计算器安装器。** 返回地址只区分调用点，不能证明所属拍摄、图像任务锁或请求生命周期。启用前须核对计划生产/消费、所有计算器使用者暂停与排空、绑定更新及卸载，不能直接设置 ready=1；不能在任务仍执行该方法时换表/释放代码。原 DNG 独立对象虚函数适配继续保留。

## 31 项离线 ARM 检查

最新 `jpeg-native-arm-v8/checks.json` 通过，执行编译后的 hard-float 适配器及真实原厂尺寸表、裁切倍率计算、来源发布片段 `0x5371140C..0x537114CC`、描述符复制 `0x538D336C`、主图中心窗口 `0x536FB040`、目标尺寸 `0x536FB0DC`。

OFF、35mm、50mm 各核对两处覆盖、两处完整来源回退及其他调用回退；浮点和栈参数、ushort 相邻字节正确。三种 crop 均从完整模型 `6192×4128` 描述符出发，保留原横向裁切/pitch，两平面位移一致，目标宽高匹配；B74/B76 保留完整来源。无绑定/禁用、对象/虚表/crop/aspect/size 不符、计划无效、来源尺寸不符、目标对齐无效均保留原尺寸，另核对目标 size 1/2/3。

工厂对象选择仍模拟；平面指针是模型地址，未读写像素、执行硬件缩放或 JPEG 压缩。对齐 `[1,4,2]` 是测试参数，不能认定为实机约束。RAW Bayer、缩放、JPEG MCU、文件与缩略图一致性仍需验证；6192×2288 只是 OFF 模型输出。

失败产物 v1..v6 保留：v1 缺复制辅助函数；v2 配置拥有者仿真偏移错误；v3 缺描述符复制代码页；v4..v6 因重复使用翻译块越过变化的停止地址。最后加逐指令停止保护修复仿真边界，未改原厂代码。v7 的 31 项通过，但描述符复制模拟；v8 改执行真实复制，从完整来源核对横向裁切，两份分别保存。

## 同一次 USB 连接完成对象与任务查询

`capture-pipeline-live-v1.json` 合并原 DNG/预览、JPEG 缩放、预览尺寸管理器及 Kb636 预览参数对象，一次遍历既有应用堆/静态范围，只保存哈希/指针和有限对象前缀；注册表共有 192 个任务。注册表、任务 ID、TCB exinf/入口及原 ROM 类核对相符：

| 对象 | 本次地址 | 任务 ID / TCB |
| --- | --- | --- |
| BackResizeMacroProcess | `0x59CED980` | `0x0100009F` / `0x570C0608` |
| LiveViewControl | `0x59CEC2E8` | `0x0100009A` / `0x570BED08`（Task 基类 +4） |
| LiveViewProcess | `0x59CD6290` | `0x01000099` / `0x570BE808`（Task 基类 +4） |
| LiveViewResolutionManager | `0x59A589F8` | 由 process +0x398 指向；虚表 `0x53FD19F8` |
| 预览 Kb636 image map | `0x59A4C000` | 由 process +0x3A4 指向；虚表 `0x53FCF708` |
| 静态 DNG Kb636 | `0x59A4B920` | 虚表 `0x53FCF430` |

地址不同于上次开机，没有复用旧对象。三条图像任务内核入口均 `0x538E1F70`，属性 `0x21003`。这证明本次读取时任务与对象身份关联，不证明分配尺寸、持有锁、任务暂停/排空或像素缓冲界限。

`mtp_factory_capture_state_readonly.py` 在同一连接进一步从新注册表取得任务，再读取 JPEG 固定状态/描述符、非空配置的有限裁切字段、预览状态和绑定服务、三处原生 mutex 的字节。mutex 字节不能作为空闲证明；配置可能属于旧拍摄，不能作为当前拍摄计划。查询只使用 GetData，不调用图像函数，不使用启动脚本的 16 次编号，SD 不用移动。

两组查询均须前后核对原回调、scratch、拍摄属性及注册表身份；原始报告保存实际结果，任何不完整报告不能当成成功。下一步接预览范围、图像 worker 同步与可撤销安装，不把本轮模型 JPEG 尺寸或对象查询称为已能拍摄 XPAN。

### 参数与既有照片读取实际完成

`capture-state-live-v1.json` 成功保存。JPEG 配置 `+0x8A48` 为零，源描述符 format=1，但 planes/width/height/pitch 为零；没有跟随空配置，不认为已获得可用帧或分配界限。预览 process `+0x8D` 为 0，尺寸管理器/参数对象身份与第一批相同。原回调、scratch、拍摄属性未变。这个 USB 状态无法给出拍摄中的 JPEG 参数，需要后续在真实拍摄任务中采集。

在同一连接追加标准 PTP GetObjectHandles/GetObjectInfo/GetPartialObject，文件头每个最多 256KiB，仅分析长度/hash/选定字段，不保存照片或完整文件头。每个存储最多考虑返回列表末尾 64 个 handles，顺序不当作拍摄时间；最多六张。`existing-photo-headers-live-v1.json` 读到 六个 JPEG 样本，SOF0 均 **6192×4128 / 8-bit**。这为实际原厂 JPEG 输出尺寸提供依据，但不能证明 YCbCr 源缓冲尺寸、当前焦距裁切或 XPAN 输出；本次选中对象没有 DNG，不推断 RAW 实际尺寸/裁切标签。

本轮所有 USB 进程正常结束、会话关闭，未申请/保留 RAM 分配或发布挂钩。SD 启动脚本未改、固件未刷，可以正常关机。新的源码及成功/失败产物哈希归档至 `ui-development-evidence-v9.json` / `ui-source-snapshot-v9/`。
