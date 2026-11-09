<!-- License: see LICENSE (earlier Apache-2.0 grants remain in force) -->

# Ricoh GR IV Firmware Analysis and Feature Expansion

本文记录对 GR IV 固件包、USB/MTP 接口、工厂菜单与关机图替换路径的离线分析和单机实测。测试使用用户自己的相机与 SD 卡。仓库包含可审阅的示例脚本，但不分发固件、系统镜像、相机读回数据或品牌图稿。

## 固件更新包

调查样本为官方 GR IV 1.11 固件包中的 `fwdc248b.bin`，长度 38,648,776 字节，SHA-256：`a2f664dfca034059eb0fd6e18ab08684c326b4a034d85c164dad7e1ec9b5655f`。原始固件文件不包含在仓库中。

- 头部 `0x08` 为 `GR IV` 型号字符串。
- `0x38` 和 `0x50` 处的四字节均为 `01 0B 0A 07`，可读作四段版本号 `1.11.10.7`。固件日志格式也包含 CPU、SRIC、DSP 的四段版本字段。每段参与升级比较的具体规则尚未完全还原。
- 固件末尾含 32 位整文件字和校验；把所有小端 32 位字相加后对 `2^32` 取模，结果为零。这只能说明存在该校验，不能单独证明是否有额外签名验证。
- 更新程序中存在“版本比当前版本旧”的错误字符串。结合理光关于不可降级的官方说明，固件更新前会做版本检查。仅凭静态字符串不能确定完整比较顺序或准确运算符。
- 不要为反复测试任意提高版本字段。公开版本相同但内部版本更低时，设备可能在写入开始前拒绝更新；也不能保证未来官方包一定覆盖自定义版本。

官方参考：[GR IV 固件页面](https://www.ricoh-imaging.co.jp/english/support/digital/gr4_s.html)、[理光 GR 系列 FAQ](https://www.ricoh-imaging.co.jp/english/support/qa/gr-world/)。固件格式解码器参考 [yeahnope/gr_unpack](https://github.com/yeahnope/gr_unpack) 对 GR III 的公开说明；本项目的脚本在 GR IV 样本上用于离线检查，不输出可安装固件。

### 离线分析工具

本仓库的 `tools/inspect_firmware.py` 可以检查本地固件包的型号字段、版本字段和整文件校验，也能用 `--unpack` 解码载荷供静态分析。用户须自行从官方来源取得固件文件，并遵守其许可与使用条款。

```sh
python3 tools/inspect_firmware.py /path/to/fwdc248b.bin
python3 tools/inspect_firmware.py /path/to/fwdc248b.bin --unpack /tmp/gr4-decoded.bin
```

脚本只做本地读文件与输出分析结果，不连接相机，也不修改固件。

## USB/MTP 调查

对一台 GR IV 的只读枚举显示，设备 USB ID 为 `0x25FB:0x2123`，接口为 PTP/MTP。macOS 不会把该接口挂载成普通磁盘。相机“影像显示”模式呈现照片存储；“许可证显示”模式呈现只读开源许可证存储。测试中没有发现标准 MTP 上传操作码，因此这两种模式都没有提供直接写入系统资源目录的路径。

`tools/mtp_probe_readonly.py` 实现有限的只读查询：获取设备信息、存储信息和对象列表。它不实现文件上传、删除或重命名。连接前应退出会独占相机 USB 接口的应用。脚本需要 Python 与 PyUSB。

`tools/ic_probe_readonly.swift` 是基于 macOS ImageCaptureCore 的设备枚举示例，只查询设备会话和顶层内容。

以上 USB 结果来自单台设备及当时固件版本，不代表所有固件或地区配置。

## A7/Linux 内存映射

在解包的 GR IV 1.11.10.7 载荷中，找到一个 Flattened Device Tree。其 `compatible` 为 `milbeaut,sc2000a`，`model` 字符串为 `Socionext SC2000A EVB w/ RTOS and NETSEC`；`/cpus` 下只列出一个 `cpu@3` 节点，兼容项为 `arm,cortex-a7`。这是该 Linux 设备树公开给 Linux 的 CPU 拓扑，不足以单独还原其他处理器域的配置。

`/memory/reg` 列出两段区域：`0x40000000–0x43000000`（48 MiB）和 `0x44f00000–0x4bf00000`（112 MiB），合计 Linux 可用映射 **160 MiB**。同一设备树的启动参数另有 `slram=slram0,0x43000000,+0x01F00000`，即从两段区域之间划出 31 MiB 的 RAM-backed MTD 区域。把这段也计入，此地址图覆盖约 **191 MiB**，但不能据此断定 DRAM 芯片的物理总容量：可能还有未交给 Linux 的内存、其他处理器域或保留区。

固件还包含工程命令 `CAP_FMem`（函数地址 `0x530430cc`）及 `[DRAM] ch0: %04d(%04d)MB %09d(%09d)B` 输出格式。2026-09-30 进一步反汇编确认，它调用 `0x538cee54`，该函数的断言名称为 `FreeMemorySize`，所属源文件字符串为 `src/ImageBufferAllocator.cpp`，并查询编号 14 的内存池。因此它报告图像缓冲分配器的空闲内存信息，不能直接证明整机 DRAM 总量。两列输出的精确含义仍需继续追踪。固件 RTOS 段在解包文件偏移 `0x17d10`，装载基址为 `0x53000000`，上述函数可据此定位。此处纠正之前仅按 DRAM 输出字符串将其视为总量查询入口的推测。

设备树映射与芯片物理容量需要分开。Linux 的 `/proc/meminfo` 中 `MemTotal` 报告内核可用的 RAM，不能单独用于推定整机所有处理域的物理内存。固件开头存在 `BOOTPARA` 和 `DRAMPARA` 参数块，其容量字段尚未解码。

### 物理 RAM：拆解丝印与原厂规格交叉核对

2026-09-30 查阅了清水洋治（TechanaLye）在 EE Times Japan 发表的 [GR IV 实物拆解](https://eetimes.itmedia.co.jp/ee/articles/2605/27/news008_2.html)，放大其[图 3 原图](https://image.itmedia.co.jp/ee/articles/2605/27/l_ks2605_T03.jpg)，可读到处理器上方 PoP 内存的型号为 `NANYA NT6CL256T64AJ-H1`。南亚科技[该型号的原厂产品页](https://www.nanya.com/cn/Product/4497/NT6CL256T64AJ-H1)明确列出 LPDDR3、16Gb、x64、256-ball PoP。该 DRAM 密度对应 **2 GiB（2048 MiB，约 2147.48 MB；通常称 2 GB）**。

拆解图另印有“256MB LPDDR3”，与图中芯片型号对应的原厂容量冲突；不能直接采用这个容量标注。以可读丝印与原厂规格交叉核对，公开拆解样机安装 2 GiB LPDDR3 有较强证据，但本项目尚未从用户相机运行时读回物理容量，亦不能排除批次用料差异。Linux 的 160 MiB 映射与这一物理容量不矛盾，其余内存的完整分区及实际启用范围仍未还原。原厂标称 1866 Mbps 是颗粒规格，不能作为相机实测内存运行速率。

## 工厂菜单与启动脚本

通过固件静态分析，在 SD 卡根目录放置机型对应的两个入口文件后，普通开机仍进入正常界面；开机时按住 MENU 才进入工厂菜单。入口文件中 `DEVELOP.MOD` 必须为 10 字节，实测使用的字节为 `07 01 2C 1F 10 03 1E 16 05 2D`。这组入口只在一台 GR IV 上验证。进入后可见 `FW Setting1`、`FW Setting2` 以及其他测试页面。菜单项目名可从固件页面表中恢复，但项目含义和副作用不能只按名称推断。尤其不要随意更改测试、初始化、射频或校准类项目。

### Camera Mode 的 Normal / Debug（静态分析）

2026-09-30 追踪工厂菜单的 `SetCameraMode` 路径：`0x5337dad8` 接受枚举 5/6，结合菜单显示函数可对应 Normal/Debug。Debug 分支把 `CameraModeData` 的偏移 `+4` 写为 `0x5AA5A55A`，Normal 分支写为 `0xFFFFFFFF`；同时发送运行时模式更新，并调用配置保存路径。启动函数 `0x53a79bc0` 重新检查同一字段，Debug 分支输出 `=== DEBUG MODE ===`，再向公共属性管理器发送启用值。因此这是保存并在启动时应用的工程调试模式标志，并非仅改变菜单显示文字。

同一启动函数分别检查日志存储/打印、Serial Input、卡门相关开关与调试模式字段；Script 也有自己的持久化字段。仅设置 Debug 的菜单处理路径没有同时改写这些字段，不能把它理解为自动开启脚本、串口和全部调试功能的总开关。字符串中的 DEBUG MODE 是日志输出，不证明 LCD 一定显示该提示。

继续追踪后，已把属性 ID `0x0E` 连接到公共属性 `+0x5F`，并找到两个直接调用 getter 的界面：一个显示 `Camera Mode: Normal/Debug`；另一个是开机代码 4 对应的 `Version` 页面 `FactoryEntranceController`，Debug 下将版本号从两段改为四段，并有条件启用限时四次按键序列入口，匹配后进入 `DevelopmentMenuController`。此前误把页面状态 2 写成开机代码 2，现已纠正。用户已实测普通“相机信息”、关机画面，以及 MENU+电源（卡内放官网固件和取出 SD 卡两种情况）均未显示该 Version 页。后续静态追踪将开机代码 4 连接到 `RDIAL Push`（机背 ADJ./后拨轮按压）；用户随后实测**按住后拨轮向内按压，再用回放键开机**，确认出现 `Version` 页面。此前将 MENU+电源/无卡启动建议为 Version 页测试的说法已撤回。

上述按键入口已由用户在一台 GR IV 上实测，用户报告该页显示 `01.11.10.07`。隐藏菜单序列仍只来自静态分析。完整地址、可写数据搬运映射、版本格式、序列事件 ID 和覆盖范围见 [Debug 模式消费者追踪](gr4-debug-mode-analysis.md)。升级器的版本比较规则见[版本检查分析](gr4-update-version-check.md)，其他间接消费者仍应分别验证。

### Serial Input：已找到的机制与边界

工厂菜单有 `Serial Input` 开关。固件同时包含 `EnableSerialInput`、启动时的 `Serial Input is enabled!` 日志、UART 接收错误日志，以及 `Shell.cpp` 对 `A:\UARTI_ON.BIN` 的引用。这些线索支持它控制工程串行输入；尚未通过实机确认串口接点、该文件与菜单开关的具体关系，或实际接收到命令的过程。

固件内的 `SHELLCMD` 区块列出约 650 个命令名称及处理地址，涵盖系统信息、日志、按键、显示、拍摄管线与硬件测试。例子包括 `SYS_help`、查询图像缓冲空闲内存的 `CAP_FMem`、等待方向键/OK/MENU/半按快门事件的 `SW_wait`，以及屏幕测试图命令 `Screen_DisplayTestPattern`。它也列出修改内存、复位等高风险命令。命令存在于固件并不表示每条在量产机上都能执行。

另有较强的 Linux 命令桥接线索：`SHELLCMD` 列出 `lcmd` 和 `lcmd_resp`；相应固件字符串将 `lcmd` 描述为向 Linux 发送 `ExecLinuxCommand`，参数为 `<command_string>`。Linux 根文件系统中的 `sysmgrd` 包含 `RecvExecLinuxCommand`、`ExecWithOutput` 和 `popen` 调用，表明送达该处理器的命令字符串会交给 Linux shell 执行并取得输出。尚未验证 `Serial Input` 开关是否足以进入这个工程 shell、命令传输是否存在额外限制、或程序实际以何种权限运行。因此不能把静态代码路径当成已完成的实机任意程序执行测试。

Linux 根文件系统的 `/etc/inittab` 配置了 `ttyUSI0` 的 115200 波特率 getty，`/etc/rc.local` 设置了 `ttyUSI1` 的 115200 波特率和硬件流控。这证明固件配置了串行终端，但不能确定工厂菜单的 `Serial Input` 对应哪个端口。USB 用户模式仍需与串口区分：已检查的配置脚本创建 `mtp.usb0`。

2026-09-30，请用户启用 `Serial Input`、重启并连接 USB 后，从 Mac 的 IORegistry 实测得到 `25fb:2123` 的 GR IV，当前配置下只有 `MTP@0` 接口（类/子类/协议 `06/01/01`，三个端点）。Mac 串口列表没有新增相机串口，仍只有系统 `debug-console` 和蓝牙端口。MTP 接口由 `ptpcamerad` 占用；该占用不影响接口描述读取，也不能解释为串口被隐藏。本次结果不支持“仅启用 Serial Input 即可经普通 USB 获得串口”；尚不能排除其他配置或厂商私有传输。菜单开关状态由用户操作，未通过命令读回。

对自制小游戏而言，工程 shell 的 `SW_wait` 证明有读取部分机身按键事件的代码，屏幕模块有测试图和 DirectDraw 相关代码，Linux 命令桥提供了运行自编译程序的可能入口。但脚本/程序能否取得 LCD 的自由绘图权、稳定读取按键、从 SD 卡加载并安全退出仍未验证。TTL 脚本内的 `execcmnd` 只应按其脚本命令解释；它与工程 shell 的 `lcmd` 是两条不同路径。

### TTL 文件操作的后续反馈

[Issue #1](https://github.com/radium-wang/ricoh-gr4-firmware-analysis-and-feature-expansion/issues/1) 补充了存储卡相关的复制失败。观察与根因假设分开记录，详见[文件操作研究](research/gr4-ttl-filecopy-filesystems.md)。此前单机复制成功不应视为通用行为。

### 已验证的写入原理

这不是通过 USB/MTP 直接挂载系统盘。USB 的只读调查没有发现上传文件的标准操作码。实际使用的是 SD 卡和机内工厂脚本功能：

1. 工厂菜单的 `Script` 设为 Enable 后，启动流程会检查 SD 卡中的 `script/startup.ttl` 并运行它。脚本在相机固件的 Tera Term Language（TTL）解释器中执行。
2. 解释器内置 `filecopy`、`filesearch` 等文件命令。实测 `C:` 对应 SD 卡，`A:` 对应相机资源存储。启动脚本可以把 `A:\Resource\Jpeg\GoodBye.jpg` 复制到 `C:`，也能把 SD 卡上的文件复制回 `A:`。
3. 先用小文本完成 `C:` → `A:` → `C:` 的写入和读回验证，再对目标 JPEG 做备份、复制、读回校验。完整 SHA-256 相同，且关机图显示更新后的图像，证明该机目标文件确实被持久改写。
4. 实测 `filecopy` 覆盖较长的目标文件时不会自动截短尾部。首版图因此在 JPEG 尾部补入合法 COM 段，使文件长度与旧图相同；补齐前后解码像素一致。后续也单独测试了目标扩容，并完成了更大文件的回读核对。
5. 写入完成并确认读回内容后，从 SD 卡移除启动脚本，再把 `Script` 设回 Disable。关机图仍显示新图，说明结果在资源存储中持久化，不依赖启动脚本持续运行。

因此，“换关机图”的实测原理是：工厂菜单允许启动一个从 SD 卡读取的 TTL 脚本；脚本使用内置文件复制命令，将用户图片写到系统资源存储中对应 JPEG 的路径。USB 并没有承担系统文件写入。仓库中的 `examples/` 提供备份脚本和写入/回读脚本模板，`tools/create_factory_entry.py` 生成已验证的入口文件，`tools/pad_jpeg.py` 可把 JPEG 补到目标长度。详细步骤见 README。

以上是单台设备上的实验结论，不说明所有 `A:` 路径均可写，也不证明可通过脚本执行任意系统命令。原图备份和逐文件读回校验是这次实验的一部分。仓库提供通用模板，但不附带固件、系统镜像、原图备份、相机读回件或品牌图稿。操作者须自行备份、运行示例并核对读回结果。

用户用自己的图像完成了关机图替换，并在相机回读后核对整文件哈希。最终图在不插 SD 卡时仍能显示；之后将 Script 设回 Disable，图像仍保留。该结果证明这一台相机上的修改已持久化，不表示所有机身或固件版本都适用。

备份保护更新（2026-09-30）：`backup-goodbye.ttl.example` 在 SD 卡已有 `GBBACK.JPG` 时退出，保留首次备份；`write-goodbye.ttl.example` 缺少备份或新图、或已有写入读回件时退出。新增 `restore-goodbye.ttl.example`，将备份写回后另存为 `GBREST.JPG`，供电脑端 SHA-256 校验。存在性检查不等于完整性或原图身份校验，备份必须在电脑上确认并另存。这些新增保护和恢复脚本只经过离线模型测试，尚未实机验证；相机 `filecopy` 错误返回语义未验证，因此不依赖其返回值判断成功。详见 README 的恢复步骤。已经覆盖且未备份的原图无法由该功能找回。

安全操作要点：先把原始 `GoodBye.jpg` 备份到 SD 卡并在电脑上留存；每次只替换目标图片；通过读回文件校验内容；确认显示正确后移除启动脚本，并关闭 Script。仓库包含通用入口生成器与 TTL 示例，不附原图备份、相机读回件或最终品牌图片。

## 仓库内容与边界

- `tools/inspect_firmware.py`：固件容器离线检查与解码。
- `tools/mtp_probe_readonly.py`：有限的 MTP 只读探测。
- `tools/ic_probe_readonly.swift`：macOS 相机设备只读枚举示例。
- `tools/create_factory_entry.py`、`tools/pad_jpeg.py`：入口文件生成和 JPEG 长度补齐工具。
- `examples/`：先备份、再写入及读回的 TTL 模板。
- 本文：固件结构、USB 调查与关机图实机结果。
- `docs/research-log.md`：按时间整理的实验过程、结果与修订。

本仓库没有固件文件、解包系统镜像、相机回读数据或 Hasselblad 商标图稿。对品牌图像的权利归相应权利人所有；本文记录的是用户自有设备上的个案实验。本仓库当前版本的许可条款见 [LICENSE](../LICENSE) 和 [README](../README.md#免责声明和许可证)；截至 `a55a2c7` 的旧版本按 Apache License 2.0 发布，原授权继续有效。许可只覆盖相关权利人有权授权的内容，不覆盖第三方固件、商标或其他权利。免责声明不是法律意见，也不能消除设备改造或再分发在特定司法辖区可能产生的责任。
