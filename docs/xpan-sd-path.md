<!-- License: see LICENSE (earlier Apache-2.0 grants remain in force) -->

# 通过 SD 卡导入 XPAN 功能：已核对的入口

当前目标是在 GR IV 画面比例菜单保留原四项并加入第五项 XPAN 65:24；裁切菜单继续保留 OFF、35mm、50mm，并让实时取景、成片、图标一致。以下分析使用本地 GR IV 1.11 固件样本和用户机身的 SD 卡脚本回读；本轮未改动固件版本或机内资源。

用户明确要求可恢复。2026-09-30 最新菜单目标为画面比例第五项，早期裁切第四档设计属于历史方案。后续改动须先具备原始内容备份、独立回退入口和机身恢复验证；现在不能保证移除 SD 卡后重启一定恢复。现有缓冲回退代码只完成电脑端检查，机内可恢复加载器尚未实现，详见[恢复要求](xpan-recovery.md)。

2026-09-30 用户要求清理 SD 卡：已将卡上 113 个本项目入口、探针、读回结果及 `script/recovery.ttl` 逐字节备份到 `devkit-output/sd-cleanup-20260930/`，记录并复核 SHA-256，随后删除并再次确认全部目标不存在。`script` 目录当时已清空移除；保留 `DCIM`、`RICOH`、来源不明的 ZIP 与 macOS 系统目录。该清理没有触碰相机内部文件或设置。

随后按用户继续实现 XPAN 的要求，部署一次性桥接验证包 `devkit-output/xpan-bridge-gate-20260930/`。它在正常开机时只读取本次 Linux 桥对象、查询 Linux 就绪事件，并尝试让 Linux 执行 SD 上的 `BRRUN.SH` 写回精确标记；不使用 `SYS_reg`、不修改相机代码、比例设置或固件。首个 `BRTEST.TXT` 阻止后续开机重复执行，脚本与工厂入口文件逐字节回读通过，SD 安全弹出后进行机身验证。

**后续两次机身结果（2026-10-01）：**两次 `BRTEST.TXT` 均完整开始、结束；`is_linux_boot=1`，`lcmd` 处理函数返回 0，117 字节桥对象前后均成功读回，响应标志前后都是 0。桥对象本次地址分别为 `0x5A080E30`、`0x5A080E38`，均落在新读界内。两次均无 `BRDONE.TXT`，不能认定 Linux 已执行 SD 脚本；第二次并非“没有插 SD 卡”，因为脚本日志和对象读回确实来自相机运行。结果分别备份在 `devkit-output/xpan-readbacks/2026-10-01-bridge-gate-1/` 和 `...-repeat/`；输入和输出逐字节核对后已从卡上清理，`script` 目录也已移除。此次没有安装 XPAN。

进一步静态审计：`is_linux_boot` 零等待查询事件位 3；`lcmd` 下层 `0x535CFF8C` 在派发前另调用 `0x535D7118`，使用 `0x80000002` 事件掩码检查。两者不是同一个就绪判断，所以 `is_linux_boot=1` 不保证 `lcmd` 实际送达 Linux。`lcmd` 上层仍固定返回 0。尚无下层返回值或 Linux 写回标记，现有 SD→Linux 装载通道仍未证实；不重复相同探针。

新的只读 [`audit_xpan_memory_map.py`](../tools/audit_xpan_memory_map.py) 固定核对初始 TTBR0 `0x53004000` 和页表：`0x53` 段描述符 AP 位 6，`0x55`、`0x59`–`0x5B` 为 AP 位 3，样本的 XN 位均为 0。它提示可研究“拥有的 RAM 中装载代码 + RAM 对象挂钩”方案；不证明运行中仍使用同一页表、哪段 RAM 可供本模块占用，也不证明缓存同步和卸载。主比例菜单描述符在初始只读 `0x53` 映射中，不能假定能通过 `SYS_reg` 原地修改。

## SD 卡能做到的事

- 工厂菜单启用 `Script` 后，RTOS 启动流程会执行卡上的 `C:\script\startup.ttl`。此前实机已经用 `filecopy` 验证从机内 `A:` 资源盘读取 JPEG，以及从 `C:` 写入、读回一个资源文件。
- Linux initfs 中的 `/etc/udev/rules.d/sd.rules` 会在发现 SD 分区时调用 `/lib/udev/storage.sh`。该脚本把卡挂载到 `/run/SD/<卷标或设备名>`，选项为 `rw,noatime,nodiratime,nosuid,nodev`。这证明 Linux 可访问卡上的文件，但不等于自动执行它们。
- `/etc/rc.local` 启动 `camctld`、`usbd`、`sysmgrd` 等服务，并没有从 `/run/SD` 执行程序或脚本。`/etc/fstab` 中 `/media/card` 一行是被注释的示例，不是本机已启用的自动加载入口。

上述 initfs 文件可用 `tools/inspect_initfs_readonly.py` 从用户自己持有的 SquashFS 样本只读复核：

```sh
python3 tools/inspect_initfs_readonly.py samples/gr4_initfs.squashfs /etc/rc.local
python3 tools/inspect_initfs_readonly.py samples/gr4_initfs.squashfs /etc/udev/rules.d/sd.rules
python3 tools/inspect_initfs_readonly.py samples/gr4_initfs.squashfs /lib/udev/storage.sh
```

这个检查工具只实现本样本所需的 SquashFS 小型目录和常规文件读取，不承担通用镜像解包或完整性验证。

## 拍摄功能仍未接通的部分

- 固件列出的 `A:\Resource` 路径主要是字体、JPEG 和声音。裁切菜单图标相关数据位于解码固件的 `ICONBIN` 区段，没有找到可直接以 `filecopy` 替换的独立 `A:` 图标文件。
- 卡上的 `C:\custom%d.bin` 出现在“读取/设置自定义影像控制”的命令字符串旁，`C:\imgipcu.bin` 也用于影像控制自定义数据传递。现有上下文并不支持把它们当作可加载的功能模块。
- TTL 命令表含文件操作、`execcmnd` 和 `sendln`。上游 Tera Term 的[`execcmnd` 文档](https://teratermproject.github.io/manual/4/en/macro/command/execcmnd.html)说明它执行另一条 TTL 语句，[`sendln` 文档](https://teratermproject.github.io/manual/5/en/macro/command/sendln.html)说明它向已连接主机发文字。相机移植版的 `sendln` 已静态追到本机工程 shell，并由第二阶段返回值探针实机确认；详见下面的记录。
- Linux 侧虽有处理工程命令 `lcmd` 的静态代码和 `popen` 调用，但尚未证明 SD 卡 TTL 能把命令送达该接口，也未验证权限或输出。直接向相机发送未知命令可能改变运行状态，不应当作无风险探针。
- 即使能从 SD 卡执行 Linux 程序，拍摄菜单、实时取景与 JPEG/DNG 管线的主要代码在 RTOS 侧。仍需找到跨处理器调用或 RTOS 注入入口，才能完成机内 XPAN；仅在 Linux 上裁切已保存照片无法满足实时取景与机内图标目标。

## 风险和下一步

只读取 SD 卡文件或让 TTL 在卡上写一份探针结果，不改变固件版本，也不涉及升级包刷写。TTL 已能写 `A:` 资源盘，所以一旦脚本覆盖机内文件，仍可能破坏启动或功能。未来若发现运行时代码注入，风险还需按实际写入目标、内存权限和恢复方式重新评估，不能简单视为零。

已用 [`examples/probe-sd-command-link.ttl.example`](../examples/probe-sd-command-link.ttl.example) 完成第一阶段实机探针：它仅在 SD 卡根目录建立状态文件，发送固件命令表里只读的 `SYS_buildinfo`，再尝试追加 `sendln returned`。`SYS_buildinfo` 的处理函数 `0x53054854` 只读取并打印构建信息。探针的操作次序是：

1. 从卡上移除旧的 `script/startup.ttl`，把这个示例复制为卡上的 `script/startup.ttl`；确认工厂菜单的 `Script` 已启用。
2. 正常开机一次，等待启动完成后关机，再取出卡查看根目录中的状态文件。
3. 删除卡上的探针脚本，并将 `Script` 设回 Disable。把探针文件是否出现及其内容记录下来。

**2026-09-30 实机结果：**卡上生成了 32 字节的 `XPAN_LIN.TXT`，精确内容为 `before sendln\r\nsendln returned\r\n`。相机的文件接口将脚本原先使用的长主文件名 `XPAN_LINK_PROBE.TXT` 截成了八字符主文件名；示例现已改用 `XPLINK.TXT`。这证明脚本执行且 `sendln` 返回，但卡上未见命令输出，**不能**证明工程命令真的执行，更不能证明 Linux shell 可达。读回后已移除 SD 卡上的 `script/startup.ttl`，避免再次开机重复运行；保留了 `DEVELOP.MOD` 供用户关闭工厂菜单中的 `Script`。该脚本没有写 `A:`、更改版本或刷写固件。

本地固件中与 `sendln` 同组的 TTL 词表（解码载荷 `0x138B450`–`0x138B774`）没有 `connect`、`recvln` 或 `wait`。进一步追踪发现，移植版通过 `result` 和 `inputstr` 回读，而不需要这些命令。第一次探针没有记录这两个变量，不能从它的状态文件判断命令是否成功。

## sendln 回调追踪与第二阶段探针

2026-09-30 继续反汇编已建立以下链路。地址为本地样本的 RTOS 虚拟地址，均可用 `tools/audit_sd_shell_path.py` 复核：

| 环节 | 地址 | 静态证据 |
| --- | --- | --- |
| 识别 `sendln` | `0x53B1C9EC` | 比较文字后返回 token ID `0x4E` |
| token 分派 | 表项 `0x53B1A7D0` → `0x53B1AB0C` | 调用处理函数 `0x53B197EC` |
| 脚本运行时回调 | `0x538F0DFC` → `0x53B151BC` → `0x53B157E8` | 传入 RAM 表 `0x5501A33C`，第 0 项是 `0x538EF3C8` |
| 发送与保存返回值 | `0x53B19830` / `0x53B19834` | 调用上述回调，将返回值交给 `0x53B18018` 写到 TTL `result` |
| 本机 shell | `0x538EF410` → `0x538EEFF4` | 回调进入命令分词、名称匹配与处理函数调用；并非单纯打印日志 |
| 可选文本响应 | 回调表 `+0x30` → `0x538EF9F0` | 若 shell 已标记响应可用，复制最多 63 字符到 TTL `inputstr`；普通日志不自动成为响应 |

回调有执行上下文门槛：`0x538E20F8` 判断当前上下文，不满足时返回 -1 并记录 `Shell can't be used in Interrupt.`。命令表未初始化、命令不存在等也返回 -1。`SYS_buildinfo` 处理函数只读并打印信息，正常返回 **0**；第一轮中“脚本继续运行”仍不足以证明此门槛已通过。

已准备 [`examples/probe-sd-shell-result.ttl.example`](../examples/probe-sd-shell-result.ttl.example)。它在 SD 卡 `C:\XPSHELL.TXT` 记录两个结果：先发送只读 `SYS_buildinfo`，紧接着捕获 `result` 和可选的 `inputstr`；随后发送经本样本命令表确认不存在的 `XPAN_NO_SUCH_COMMAND`，捕获结果。文件操作可能改写 `result`，因此必须在每次 `sendln` 后立即转换并保存返回值。

| 读回 | 能得出的结论 |
| --- | --- |
| `SYS_buildinfo=0` 且对照命令 `=-1`，有 `probe finished` | 与执行本机 shell 的预期相符，能区分只读命令成功和名称未匹配 |
| 两者都是 `-1` | 工程入口或执行上下文仍不满足，不能据此向机身部署功能 |
| 脚本未完成或其它结果 | 需核对实际文件与解释器行为，暂不进入下一阶段 |

**第二阶段实机通过：**2026-09-30 读回 `XPSHELL.TXT` 为 99 字节，内容如下；SHA-256 为 `13994515baba1f9e32cc47a735355dc108c608fa8ba1d3066b5347c45b9a4339`。各行实际以 CRLF 结束。

```text
probe started
SYS_buildinfo result:
0
inputstr:

unknown command result:
-1
probe finished
```

该结果与静态分派路径一致，确认当前机身的 SD 卡 TTL 脚本能调用本机工程命令并读回返回值。空 `inputstr` 符合 `SYS_buildinfo` 只打印日志、未设置 shell 文本响应的实现。读回后已保存电脑副本并移除卡上的本轮 `startup.ttl`；第二阶段仅在 SD 卡写文件，没有机内资源、内存或版本修改。Linux 桥接和任意程序加载仍未实测，XPAN 的菜单、预览、JPEG/DNG 和图标仍需分别实现。

### 离线模拟器限制

为验证 shell 的参数解析，尝试在电脑上用 Unicorn 执行原始解析函数，但宿主 Python 在首次 `uc_mem_map` 初始化引擎时出现 SIGILL。用户提供的崩溃报告定位为 `libunicorn.2.dylib` 的 `init_cache_info +88`，指令 `0xD53B0028` 解码为宿主 ARM64 `mrs x8, ctr_el0`。崩溃发生在执行客体相机代码之前；这一工具故障与上述实机读回是两项独立结果。该模拟路径已停用，未据此部署下一轮 Linux 探针，也未修改系统 Python 或相机固件。

## 第三阶段：Linux 从 SD 卡读取脚本并回写标记

已准备两个示例，目标是确认完整的 TTL → 工程 shell → Linux → SD 卡读写链路：

- [`probe-sd-linux-link.ttl.example`](../examples/probe-sd-linux-link.ttl.example) 放到卡的 `script/startup.ttl`。它先等待 10 秒，再发送 `lcmd "/bin/sh /run/SD/RICOH?GR/LXCMD.SH"`，记录分派返回值，等待 5 秒后检查 `LXDONE.TXT` 是否存在。状态写在卡根目录的 `LXSTATE.TXT`。
- [`probe-sd-linux-marker.sh.example`](../examples/probe-sd-linux-marker.sh.example) 放到卡根目录的 `LXCMD.SH`，使用 LF 换行。它只接受 `/run/SD/RICOH?GR/LXCMD.SH` 下的启动路径，并核对同目录有工厂入口文件和 `DCIM`；然后读取 `uname -sr`，在同一目录新建 `LXDONE.TXT`。已有结果文件时拒绝覆盖。

本地 initfs 中 `/bin/sh` 和 `/bin/uname` 均指向 `/bin/busybox.nosuid`。`lcmd` 处理函数 `0x5301C5B8` 将参数连接成命令字符串，再调用 Linux 桥 `0x535CFF8C`；已加入只读审计。`?` 由 Linux shell 展开成卷标中的空格等单个字符，因此从工程 shell 到 Linux 的这一条命令不需要嵌套的路径引号；脚本内部仍给所有路径变量加引号。

这里的 `lcmd=0` 只说明处理函数返回，**不能代替 Linux 执行成功的证据**。必须读回 `LXDONE.TXT`，并同时看到 `XPAN_LINUX_SD_OK`、系统版本、实际脚本路径和 `query finished`。如果只有 `LXSTATE.TXT`，仍需追查服务就绪、挂载路径或桥接处理条件。正常开机后等至少 30 秒再关机回读；读回后移除本轮两个输入文件。

电脑检查已通过 shell 语法校验，并确认脚本从指定 SD 路径之外启动时以 64 退出且没有输出。该检查不证明相机 Linux 实际执行，最终结果由设备回读决定。这一阶段仅运行系统信息查询并写 SD 卡结果文件，不修改机内资源、版本、内存或启动配置。

**第三阶段实机未确认 Linux 执行：**2026-09-30，最初读回仅有 `linux probe started`。用户重新开机并确认等满 30 秒后，读回 `LXSTATE.TXT` 为 90 字节，SHA-256 为 `ff0bdd02f1112370b402e8b6ba43dce288655ab05d8cdbcd9659d07b0f71d379`。各行以 CRLF 结束：

```text
linux probe started
lcmd dispatch result:
0
SD marker found:
0
linux probe finished
```

卡上没有 `LXDONE.TXT`。因此 TTL 完整结束，但 Linux → SD 的链路仍未确认。输入文件 `script/startup.ttl` 和 `LXCMD.SH` 已核对为本轮原件后移除，状态文件保留。进一步反汇编确认 `lcmd` 在 `0x5301C714` 调用桥接函数后，不传播桥接结果，在 `0x5301C73C` 固定返回 0；即便参数解析未通过，也可能返回 0。这解释了为什么单看返回值不足以判断桥接是否执行。

## 第四阶段：查询 Linux 就绪状态

已准备 [`probe-sd-linux-ready.ttl.example`](../examples/probe-sd-linux-ready.ttl.example)，只向 SD 卡 `C:\LXREADY.TXT` 写结果。它在脚本开始、约 5、15、25 秒时分别发送 `is_linux_boot`，每次立即记录返回值，并用 `SYS_buildinfo` 和不存在的对照命令核验工程 shell。它不执行 Linux 命令，不启动 Linux，也不改变启动配置。

本样本的静态路径为：命令表 `is_linux_boot → 0x53021D18`，取得启动状态对象后调用 `0x538DB6B4`（`WaitAnd`），参数为事件位掩码 3、超时 0。该包装器在 `0x538DB774`–`0x538DB780` 将 OS 查询成功转换为 1，失败转换为 0，并在 `0x538DB7AC` 返回。命令处理函数直接返回该值。超时常量位于 `0x53FE1668`。这些位置已加入 `tools/audit_sd_shell_path.py`，通过原样本核对。

| 就绪查询结果 | 下一步依据 |
| --- | --- |
| 全部为 0，且对照命令正常 | 查询时 Linux 的就绪事件条件不满足，应调查启动条件；不能仅增加文件或改挂载路径 |
| 后续为 1 | 就绪条件满足，可继续追查命令参数、Linux 响应和 SD 挂载路径；1 本身不证明 shell 命令成功 |
| -1 或其他异常，或脚本未完成 | 先检查当前命令表与脚本执行结果，不能解释为 Linux 是否启动 |

该探针只读就绪事件位，并非 `/proc` 查询；不能单凭 0 断言 Linux 从未运行。正常开机至少 30 秒后关机回读。读回后移除本轮 `startup.ttl`。

2026-09-30 曾将本阶段脚本写入用户卡上的 `script/startup.ttl`，逐字节回读一致：1,358 字节，SHA-256 为 `490c237cc3fadc3fe5c50b2c4de110b3d5faad3b6c0bd972132ffa2971f5915d`。部署时旧 Linux 脚本已移除，`LXREADY.TXT` 尚不存在；仅新建本轮入口文件，保留照片和此前结果。

**第四阶段实机结果：**2026-09-30，`LXREADY.TXT` 为 228 字节，SHA-256 为 `fd1430037b4c155dbf255b86cdb841de36908248561040dfb0bf0136de34c3d5`；已保存电脑副本并核对移除本轮脚本。返回顺序如下：

| 查询 | 返回值 |
| --- | --- |
| `SYS_buildinfo` | 0 |
| `is_linux_boot`，脚本开始时 | 0 |
| 约 5 秒后 | 1 |
| 约 15 秒后 | 1 |
| 约 25 秒后 | 1 |
| 不存在的对照命令 | -1 |

结果含完整结束标记，工程命令通道正常，就绪事件条件在约 5 秒前满足。第三阶段在 10 秒发送命令，因此不能简单归因为启动太慢；不同开机之间的时序仍可能变化。接下来核对桥接处理、SD 挂载与命令输出，仍未证明 Linux 执行成功。

## 第五阶段：查询系统与挂载表，导出可用日志

[`probe-sd-linux-logs.ttl.example`](../examples/probe-sd-linux-logs.ttl.example) 使用同一张卡进行两次正常开机：

1. 第一次等待 10 秒，查询 `is_linux_boot`。就绪值为 1 时发送 `/bin/uname -sr` 和 `/bin/cat /proc/mounts`，均为只读查询；记录处理函数返回值，并新建 SD 阶段标记 `LXPHASE.TXT`。返回 0 仍不能证明 Linux 执行成功。
2. 正常关机后再次开机。脚本识别阶段标记，调用 `llog_export`，将可用日志导出到 SD 根目录 `linux01.log` 至 `linux05.log`，状态追加在 `LXRUN.TXT`。任一目标日志已经存在时拒绝导出，避免重复开机覆盖结果。

两次开机是为了兼容从关机时保存的 Linux 日志读取的路径。不能假定日志导出包含当前运行期间的实时输出，也不能假定所有五份日志均可用。Linux 根文件系统的启动配置以 `SYSMGRD_LOG=info` 启动 `sysmgrd`；其 `RecvExecLinuxCommand` 在执行前后以级别 2 记录命令和返回文本，静态字符串为 `received ExecLinuxCommand cmd="{}"`、`ExecLinuxCommand result: {}, output: "{}"`。如果导出包含这些记录，可据此确认命令实际收到以及挂载表；否则继续核对日志保存条件，不将空日志当作 Linux 未运行。

命令表 `llog_export → 0x53016D6C`，说明文字 `0x53E9E478` 为 `export linux log to sd card.`，输出模板 `0x53E9E498` 为 `C:\linux%02d.log`，盘符文字 `0x53E9E4B8` 为 `C:`；循环范围 1–5，大小及数据来自 `0x53A7E208` / `0x53A7E364`，随后经 SD 文件接口创建、写入、关闭。日志管理器可从内存中已有数据或 `F:` / `H:\DOMDTBK` 下的已保存数据读取；导出命令不修改源日志。关键命令映射、路径和调用点已加入只读审计并通过原样本核对。

电脑只检查了 TTL 条件结构、命令关键字存在、输出路径和固件分派地址；没有运行相机代码。新脚本 2,424 字节，SHA-256 为 `087f46ba77a65335ebd9afbf7b81546f47476f8f7cceff630fa5b6430c922148`。每次开机等待至少 45 秒、正常关机并等待完全熄灭；两次完成后再回读。该轮不改版本、资源、启动配置或内存补丁。

2026-09-30 已部署第五阶段脚本到用户 SD 卡 `script/startup.ttl` 并逐字节核对；部署前确认 `LXPHASE.TXT`、`LXRUN.TXT` 和五个日志目标均不存在，第四阶段脚本已移除，照片及此前结果保留。第五阶段实机结果待回读。

**第五阶段第一次开机读回：**用户确认本次只完成一次开机。`LXRUN.TXT` 为 165 字节，SHA-256 为 `2297c6a25fa73ef8f5ba2bbb4a3857ddfdbc8ac9a46c64dbfaaf05f533c11a3d`，包含 `query boot started`、就绪值 1、两个查询处理函数返回 0 和完整结束标记。`LXPHASE.TXT` 为 50 字节，SHA-256 为 `179fc29abaf86c4dc5237bdb419e619a8a5f1334142b471ec22499aeb609acd7`，内容为 `queries dispatched; next boot exports saved logs\r\n`。五个日志文件均未生成，符合未执行第二次开机的阶段安排，不能解释为日志导出失败。读回已保存电脑副本，清理入口后为补做导出阶段重新部署同一脚本；阶段标记与查询结果保留。

**第五阶段第二次开机读回：**2026-09-30，`LXRUN.TXT` 增长为 276 字节，SHA-256 为 `f00cbed82d7ff7aeed1dca4d1e9af242c91e225f789d60b912ccaf72a35c74ab`，在第一次结果后追加：

```text
log export boot started
Linux readiness:
1
log export handler result (check files):
0
this boot finished
```

五个目标日志仍均不存在；完整结束标记证明导出阶段已调用并返回，但 `llog_export` 本身也不传播数据是否导出的状态。可能原因包括没有可用的已保存日志、日志保存条件未满足或读写接口失败，不能从缺文件推出 Linux 查询执行与否。已备份结果并移除本轮启动脚本。不重复同一个日志导出探针。

## 第六阶段：直接只读核对 RTOS 运行时

工程命令表还提供 `SYS_md`，说明为 `dump memory`，参数支持起始地址、`-s` 字节数和 `-f` 输出文件。静态处理路径 `0x53053A84` 在解析完参数后，将源地址、长度和文件名交给 `0x538EF988 → 0x5383BEC4` 写入文件。此路径不向提供的内存地址写数据；`SYS_reg set` 才是任意地址写入路径，本阶段没有使用。后续纠正：`SYS_mm` 实际为性能测量标记控制，不是内存写命令。

准备 [`probe-sd-runtime-read.ttl.example`](../examples/probe-sd-runtime-read.ttl.example)，一次开机读取三个固定区域，共 174 字节：

| 地址 | 长度 | SD 输出 | 用途 |
| --- | --- | --- | --- |
| `0x53EA38FC` | 30 | `LXCONST.BIN` | 已知 `lcmd` 说明文字，核对当前映射 |
| `0x5380D1EC` | 16 | `LXCODE.BIN` | 已定位的画面比例分派代码，核对实机与样本是否一致 |
| `0x553A08E4` | 128 | `LXRAM.BIN` | 日志管理器固定全局对象，核对其运行时保存/级别状态 |

这三处地址均来自用户报告版本相同的本地 1.11.10.7 样本：前两处为已定位的已加载代码/文字，第三处被日志管理器的读取函数直接引用。探针只读取这些固定映射的字节，不访问硬件寄存器，不遍历任意内存，不更改日志开关，不执行 Linux 命令，不注入代码。读回应核对输出长度、文字和代码的精确字节；处理函数返回 0 或文件存在本身不足以确认读取正确。状态写 `LXMEM.TXT`。

工程 shell 对未加引号的路径保留反斜杠；因此命令的 `C:\LXCONST.BIN` 等路径不加工程 shell 的双引号，避免其引号内的反斜杠转义处理。TTL 本身仍用单引号包围整条命令。关键命令映射、选项分派、源地址/长度传参和文件写入调用已加入 `tools/audit_sd_shell_path.py` 并通过原样本核对。电脑另已确认三个命令地址、长度和八字符文件名完全符合上表。

直接读回 RTOS 是独立于 Linux 的验证路径。如果读取成功，将可以基于实机状态继续核对菜单、裁切和日志；它不证明运行时代码可安全修改，也不等于新增 XPAN。此阶段正常开机至少 30 秒后关机回读，并移除本轮脚本。

2026-09-30 已部署本轮 `startup.ttl` 并逐字节回读核对：1,344 字节，SHA-256 为 `af01ea5f9cd93b803f0e64cf86bf7918b4560fa9ddb4cbbe3f7358f5389d00ae`。四个输出目标部署前均不存在，旧脚本已移除，照片和此前结果保留。第六阶段实机结果待回读。

**第六阶段实机成功：**2026-09-30 完整读回，三条处理函数均返回 0、文件均存在，且精确长度为 30、16、128 字节。`LXCONST.BIN` 是原样本文字 `issue ifcmd "ExecLinuxCommand"`，`LXCODE.BIN` 是原样本代码 `030053e303f19f970f0000ea20d28053`，证明当前 RTOS 固定地址读取与本地样本相符。`LXRAM.BIN` 的日志对象 `+0x2C` 为 0，确认 RTOS 日志存储开关关闭；不能自动解释为 Linux 保存日志开关。结果已备份到电脑，原启动脚本已核对移除。读取成功仍不证明可安全注入 XPAN。

## 第七阶段：一次开机的自适应批量检查

用户要求减少插拔次数。本轮由 `tools/build_sd_batch_probe.py` 生成 [`probe-sd-xpan-batch.ttl.example`](../examples/probe-sd-xpan-batch.ttl.example)，合并菜单、预览布局、裁切图标、拍照比例、DNG 裁切、运行时拍摄属性、日志对象和 Linux 桥状态等 16 处固定读取，共 3,856 字节。随后用原生 TTL 的单字节 `fileread`、`str2code` 解码本次开机刚保存的指针，继续读取图像尺寸计算对象及函数表、工程命令表、输出缓冲和桥对象。不会沿用上次开机的堆指针。

动态读取限定在 `0x59000000..0x5A000000`，单块最大 1 MiB，检查长度和末地址；代码函数表另限定在已确认代码范围。命令表最多 1,024 条、每条 52 字节。最大动态读取量为 2,150,986 字节。地址区间检查只能筛除明显无效值，不能证明每个内部对象均稳定；设备上的动态读取尚待实测。

仅当已读到输出缓冲、原响应标志和 Linux 就绪值 1 时，临时启用 `lcmd_resp`，执行计算标记、系统版本、挂载表和 SD 路径四个只读查询。查询后立即恢复原标志，再写状态文件；标志改变期间没有 SD 操作或子程序调用。原标志为 1 时保持 1。计算结果 `XPAN_SD_EXECUTED_REPLY` 不完整出现在命令文本中，避免把输入回显当执行证据。`lcmd` 返回 0 仍只代表处理函数返回；需要回读输出缓冲并人工核对证据。

本轮不写固件、资源、裁切属性或代码；工程响应标志是暂时的 RAM 状态变化，正常执行时恢复。卡上已有 `XPBATCH.TXT` 就停止，避免反复运行和覆盖结果。只需正常开机一次、保持开机至少 90 秒、正常关机后再回读，无需两次开机。XPAN 尚未安装。

电脑端原样本审计通过，七种合成流程检查通过：包含 NUL 字节的指针解码、原标志 0/1、无效指针、过大长度、解码不符、已有结果与后续文件失败。检查器验证脚本控制流，不是相机模拟器。`tools/analyze_sd_batch_readback.py` 可只读分析复制到电脑的结果目录，比较固定代码、解码属性及函数表，并核对响应标志恢复；模拟的命令回显未被误判为执行证据。

批量脚本 8,495 字节，SHA-256 为 `0f537f9313ecaf7179dac4e28ee179ba113a0a3235b740424fdb0b252720adbb`。实机结果待回读。

2026-09-30 已将此脚本新建到用户 SD 卡 `script/startup.ttl`，逐字节回读一致。部署前核对卷、设备、工厂入口和上一轮精确代码读回；26 个批量输出目标均不存在，卡上有足够空间。仅新建本轮入口，保留照片与所有此前结果。用户下一步为正常开机一次、等待 90 秒、正常关机后回读。

### 第七阶段实机结果：批量读取完成，Linux 查询被保护条件跳过

2026-09-30 完整回读 `XPBATCH.TXT`，461 字节，SHA-256 为 `79357d7b4ff5f47b180cbcbb675bbd8d98288f53a92ef0f878e0de03376a3efd`，含 `XPAN batch finished`。16 处固定输出全部存在且长度准确，10 处代码/常量输出与原样本逐字节一致。原生二进制解码校验为 1；图像尺寸对象及函数表、651 条工程命令表和当前输出缓冲均成功读回。两次拍摄属性快照一致：比例 ID 0、倍率 1.0。

| 动态输出 | 字节数 | 结果 |
| --- | --- | --- |
| `XPRMETA.BIN` | 32 | 描述符容量 `0xEFFEC`、数据地址位于原限定范围 |
| `XPRPRE.BIN` | 983,020 | 含正常开机事件和脚本执行记录；不是纯文字文件 |
| `XPIMOBJ.BIN` | 32 | 函数表指向 `0x53FD89A0` |
| `XPIMVT.BIN` | 64 | 与原样本同地址函数表完全一致 |
| `XPCMDS.BIN` | 33,852 | 651 条、每条 52 字节；结构为处理地址＋48 字节内联名称 |
| `XPPEND.BIN` | 192 | 与首次属性快照一致 |

Linux 桥对象指针为 `0x5A08B1E0`，超出本轮 `0x5A000000` 上界，故保护条件跳过桥对象读取和四个 Linux 查询。`bridge setting read available` 为 0，三个后续文件没有生成。这是脚本正常保护行为，不是脚本中断；本轮没有启用 `lcmd_resp`，原标志未知，不能宣称读回证明恢复了标志。也不能根据没有查询输出判断 Linux 命令可否运行。不直接扩大所有堆读取范围；Linux 路径并非继续分析 RTOS 裁切的前提。

函数表已确定实际尺寸计算方法 `+8 → 0x538CFBF8`，裁切倍率分类 `+0x30 → 0x538CFB5C`、分类转倍率 `+0x34 → 0x538CFB90`。后续追踪 JPEG 调用修正了参数命名：方法 `+8` 的 `r1` 是分辨率/尺寸索引，`r2` 是比例 ID，`s0` 是裁切倍率；DNG 先将倍率分类为匹配的尺寸索引。已加入 `tools/audit_runtime_image_calculator.py`，核对实机函数表后从原样本受限解码 16 个尺寸分支，未执行相机代码。详见 [XPAN 尺寸计算依据](xpan-crop-feasibility.md#实机确认的尺寸计算器与保留原选项的修改依据)。

全部读回及脚本已备份到电脑，核对原哈希后移除卡上 `script/startup.ttl`。保留卡上结果和照片；本轮不立即部署另一份探针，先使用现有数据开展离线修改分析。XPAN 菜单、预览、成片和图标仍未安装。

### 批量读取后的离线接入进度

2026-09-30 继续使用本次读回与同版样本，没有新 SD 卡轮次。裁切第四档状态核心现已配套每张照片的固定窗口、Kb636 DNG 参数块与叶函数 ABI 包装、422 主图源描述中心裁切适配。电脑检查验证原选项恢复、DNG 字段范围、两路合成像素的实际中心行选择和拒绝无效输入；ARM 硬浮点模块编译通过，无未解析符号。

同时修正先前入口判断：`0x5380D1D0` 只写 Makernote 比例元数据，`0x5339E894` 附近属于 FocusModel；DNG Kb588 起点 `[68,40]` 与 Kb636 `[54,58]` 必须区分。DNG 两次查询同一尺寸计算器，第二次取得完整基础范围，因此不能全局替换这个计算器。

这些模块没有安装器、跳板或已验证的运行时代码装载机制，实际主图格式/分配边界、JPEG 目标尺寸、完整预览和图标还未接通。DNG 包装默认禁用，保持原函数行为；没有任何新代码在相机运行。详细证据与模块边界见 [拍摄窗口适配](xpan-crop-feasibility.md#拍摄窗口dng-接口与实际像素源适配)。


## 第八阶段：最小指针恢复诊断

用户要求可恢复，先验证有限诊断指针的临时替换和原值恢复。八个参考文件与两个脚本已经写入 SD 并逐字节核对，启动脚本最后写入，卡已安全弹出；机身结果待两次开机后回读。两次之间无需拔卡。设计、边界和操作见[恢复测试](xpan-recovery.md#最小诊断指针恢复测试2026-09-30)。

新增 `tools/audit_xpan_runtime_loader.py` 核对本地样本及实机命令表：`SYS_reg set ADDRESS 4 VALUE` 走四字节复制路径，既没有安全事务也不是代码加载器。`SYS_mm` 是 measure-mark control；`file_dd_load` 操作内部文件状态，未证实是程序加载入口；`SYS_memovr` 为有意越界复制测试，禁止用于本方案。

原生分配和释放包装 `0x538E0A24` / `0x538E0A60` 已定位，但尚未确认可执行内存所有权和加载协议。`SYS_cache` 的 flush/clean 路径涉及数据缓存，不能据其名称认定能发布新指令。内核中存在 `ICIMVAU`、`ICIALLU` 和 `ICIALLUIS` 指令，但可调用 ABI、屏障顺序及跨 CPU 同步未验证。架构含义参考 [ARM 官方架构手册](https://documentation-service.arm.com/static/5f8daeb7f86e16515cdb8c4e)，不能代替本机协议证据。因此本轮调用的仅为原固件已有短函数，不向 RAM 装载 XPAN 代码。


**第八阶段第一次回读：**保护条件阻止了修改，不能报告恢复成功。原代码与三条命令记录在电脑上全部匹配，当前表地址有效；TTL 内比较失败尚待查明。启动脚本已备份核对后移除，随后部署一次开机的纯只读比较诊断（六文件已核对并安全弹出），详见[实际结果](xpan-recovery.md#第一轮实际结果前置比较未通过未进行指针修改)。


**只读比较诊断实机结果：**九组记录完整，五段代码逐字节匹配样本，差异控制正确停在第 1 字节。机内 `fileread` 在 EOF 仍返回 0，导致原长度保护误判；短控制文件越界读取还产生非文件字节。因此改用本机已静态核对的 `filestat` 精确长度检查，不读取 EOF。修正版先校验四组已知长度控制，再核对七段原代码和命令记录，才允许最小临时指针测试。使用新 `ZP` 输出前缀，17 项文件已核对并安全弹出；实机恢复结果仍待两次正常开机回读。见[修正版说明](xpan-recovery.md#比较故障已定位长度核验修正版已部署)。


### 最新方案：画面比例第五项

用户进一步纠正 XPAN 的菜单位置。现将 XPAN 作为原四比例之后的第五项，裁切菜单维持原三档。原生主比例菜单及另一比例入口均读取现有四项顺序表，需配套独立回调和状态，不能仅把计数改为 5，也不能直接把项目逻辑 ID 4 写进原生属性。具体只读审计与电脑端状态/拍摄计划见[当前交互目标](xpan-crop-feasibility.md#当前交互目标画面比例第五项)。本次无 SD 卡写入；已验证的临时诊断指针恢复只覆盖 4 字节，不等于 XPAN 模块可装载。
