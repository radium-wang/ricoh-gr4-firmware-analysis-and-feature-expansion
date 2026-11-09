# GR IV USB 工厂通道与系统文件写入调查（2026-10-01）

设置菜单身份、33 项原厂 ARM 参数核对及实际尺寸计算器拥有者，见 [原生比例菜单入口与拍摄状态取样](research/2026-10-01-native-ui-routes.md)。下一取样包已在电脑准备并附原脚本恢复副本，尚未部署；实际 XPAN 菜单和图像挂钩仍待接入。

最新进展及对旧恢复标志的更正见 [新 RAM 代码执行与 XPAN 核心批次](research/2026-10-01-xpan-ram-core.md)。固定新 ARM 叶函数已实机运行并释放；XPAN 菜单及真实图像管线仍未安装。

目标：在保留原有菜单选项、可恢复的前提下，寻找通过 USB 为 GR IV 添加 XPAN 65:24 画幅第五项的路径。已向相机发送 MTP 读取请求，以及一组固件内置的临时 WLAN 工厂启动／停止命令；未向相机上传、删除或更改文件。

## 实机枚举与只读 MTP 查询

- 机身固件：`01.11.10.07`；电脑连接时读到 `VID:PID=25FB:2123`，产品名 `RICOH GR IV`，仅 1 个 USB 配置。先前完整接口枚举记录为单一 PTP/MTP 接口 `06/01/01`、3 个端点；启用工厂菜单 `Serial Input` 后也没有新增串口接口。当前再次读取的设备身份与之相符。
- 为避免 macOS `ptpcamerad` 占用，临时终止该用户进程后立即运行现有 `tools/mtp_probe_readonly.py`。查询完成后 macOS 自动重启了该进程。`GetDeviceInfo` 返回 `0x2001`，公布的操作码为：

  `1001 1002 1003 1004 1005 1006 1007 1008 1009 100A 1014 1015 1016 101B`

  不含 `100B`（DeleteObject）、`100C`（SendObjectInfo）和 `100D`（SendObject），也不含厂商 `9xxx` 操作码。
- `GetStorageIDs` 仅返回 `00080001`；`GetStorageInfo` 报 `storage type=3`、`filesystem=3`、`access=0`，22 个可见对象的根目录仅有 `DCIM`。`access=0` 指这个照片存储报告“读写”，**不等于**主机能通过当前 MTP 命令表上传文件，也不表示系统分区可见。
- `OpenSession` 返回 `0x201E`，表示会话已存在；后续只读查询仍成功。基线枚举时没有尝试结束别人的会话；随后针对未公布的 `0x9093` 做了独立只读验证，见下文。

## 固件静态检查

- `samples/gr4_decoded.bin` 中的 Linux initfs `/etc/rc.local` 启动 `usbd` 与 `mtpd`。`/usr/bin/usb30dev_mtp_func*.sh` 五个配置脚本都只建立 `functions/mtp.usb0` 并绑定单个配置；其中 `25FB:2123` 与实机一致。`sysmgrd` 只引用这些 MTP 脚本的三个变体。没有发现创建 USB ACM、RNDIS、ADB 或独立工厂 bulk 接口的配置脚本；系统内存在通用 USB 内核模块不代表量产配置启用了它们。
- `mtpd` 包含通用 MTP 代码的 `doSendObjectInfo` / `doSendObject`，但机型适配层 `RicohMtpDatabase::beginSendObject` 在 Thumb 地址 `0x20FA4` 是 `movs r0,#0; bx lr`，直接返回无效对象句柄；`endSendObject` 为无操作。因此仅看通用函数名不能推断上传可用。
- `mtpd` 的 `doGetDeviceInfo` 根据 `DeviceProperty::GetVendorMode` 返回值在普通 14 项和扩展 32 项操作表之间选择。扩展表含 `9001 ... 9017` 的部分厂商命令；`handleRequest` 中确有 `GeneralPurpose*` 处理器。`RicohMtpDatabase::setPentaxVendorMode` 只接受值 0/1，转到 `DeviceController::ChangeTetherMode`；这更像远程控制模式切换，不能从名称推断有文件系统 shell。当前机身未公布这些操作。尚未证明存在安全可进入的厂商模式，亦未证明这些命令能读写任意系统文件。未向实机发送进入模式或厂商命令。
- 扩展 32 项操作表已由离线审计逐字节核对：其中仍没有 `0x100C SendObjectInfo` 或 `0x100D SendObject`，所以切换厂商模式也不能仅凭操作表获得标准 MTP 上传入口。
- 进一步解码 `mtpd` 的 `MtpServer::handleRequest` 跳转表，发现即使 `GetDeviceInfo` 不公布，命令分派仍包含 `0x9090` SetValue、`0x9091` RunFunc、`0x9092` EndCheck、`0x9093` GetValue、`0x9094` GetData、`0x9095` SetData。`0x9093` 调用 `CameraController::GetFactoryCommand()` 返回的 `FactoryCommandImpl::GPGetValue`。未知参数的 `RunFunc` 与 Set* 可能改变相机状态；实机仅对已离线核对、带停止命令的固定 WLAN 命令做了试验。离线映射可用 `tools/audit_gr4_mtp_factory.py samples/gr4_decoded.bin` 复核；实机只读工具为 `tools/mtp_factory_getvalue_readonly.py`。
- 2026-10-01 实机只读验证：`0x9093 GetValue(count=0,index=0)` 返回 `0x2002`（GeneralError，无数据）；未分配的 `0x90FF` 对照返回 `0x2005`（OperationNotSupported）。随后反汇编发现 `FactoryCommandImpl::GPGetValue` 会在 `count=0` 时本地拒绝，因此第一次并未到达 RTOS。修正为 `GetValue(count=1,index=0)` 后返回 `0x2001`，数据 `00000000`（1 个四字节值）。这确认工厂读路径可用，但不表示可以读取任意地址或文件。完整响应见 `devkit-output/usb-factory-20261001/readback.json`。当时尚未发送 `RunFunc`；后续固定 WLAN 命令试验见下文。
- `libcamera-controller.so` 有 `FactoryCommandImpl::{GPSetValue,GPRunFunc,GPEndCheck,GPGetValue,GPGetData,GPSetData}`，`GPRunFunc` 接受 8 位 category ID 和 command ID。RTOS `FactoryCommandServer` 有按 `(category, command)` 查找的三字节表（当前样本从文件偏移 `0xEB8754` 开始，329 个条目，以 `0xFF` 结束），然后转发请求。离线脚本已固定这张表的边界和唯一编号，审计输出保存在 `devkit-output/usb-factory-20261001/offline-audit.json`。该表只给出命令编号和域标志，尚未给出每个命令的文件操作语义。RTOS 另有 `FileCommand`、`FileCopy` 和 `FactoryCommandFileSystem`，但还没有证明它们能由此 USB 工厂接口调用，更没有验证安全回退路径。
- RTOS 镜像里出现的 `GeneralPurposeOperationUnitService` 属于图像处理器 GPC/像素处理服务，与 `FactoryCommandImpl` 不是同一证据链；不能凭相同英文词认定它是工厂命令接收端。
- 继续追踪 RTOS 工厂命令发现一条**固定用途的 Linux 桥**：类别 `0x0F`、命令 `0x2C` 与 `0x2D` 均在路由表中，分别进入 WLAN 工厂函数，使用内置字符串 `iperf3 -s &` 与 `killall iperf3`，再调用与 SD `lcmd` 相同的 Linux 命令桥 `0x535CFF8C`。这一链条已加入离线审计。它证明工厂服务可为特定 WLAN 测试调用 Linux 命令，但参数是固件内置字符串，不能由此推断 USB 主机能提交任意 shell 脚本。WLAN 的其他路径会构造 `hostapd` 配置；尚未证明用户参数的来源、转义、恢复和适合本项目的调用方式。
- 实机固定命令试验：在相机通过 USB 连接时，按 `0x0F:0x2C` 启动、查询完成、`0x0F:0x2D` 停止、查询完成的顺序发送。两次 `RunFunc` 均返回 `0x2001`，两次 `EndCheck` 均返回 `0x2001` 和 `0000000000000001`。停止命令已发送；没有经 USB 读取 Linux 进程表，故这些回包仍不能单独证明 `iperf3` 实际启动/退出。实机记录为 `devkit-output/usb-factory-20261001/wlan-bridge-readback.json`，脚本为 `tools/mtp_factory_wlan_bridge_probe.py`。未传主机 shell 文本，未上传或写入相机文件。
- 追加只读 `GetDeviceInfo`／`GetDevicePropDesc` 查询：普通 MTP 公布的设备属性仅有 `5001 5011 D406 D407 D303`，没有 WLAN SSID、密码或通用脚本属性。五项的属性描述返回码依次为 `2001 200A 2001 2001 2001`。因此标准 MTP 设备属性不是已验证的 WLAN 参数输入路径。
- 进一步反汇编 `mtpd` 的 `DeviceProperty::SetDevicePropertyValue`（Thumb `0x53F3C`）：普通属性设置入口首先仅比较 `0x5011` 和 `0xD406`，其他编号进入不支持的分支。因此不能把未公布的 WLAN 属性编号塞给标准 `0x1016` 来写入 SSID 或密码；该门控已加入离线审计。
- 整个已解码镜像的可打印字符串中未见 X2D 的 `HblM`、`HblShell`、相同工厂帧头对应服务；GR IV 是 Linux + RTOS 架构，X2D 资料里的 Android `setprop sys.usb.config` / ADB 步骤没有对应的 GR IV 实现证据。

## GR WORLD 无线固件上传路径

- 理光官方说明 GR WORLD 1.2.0 起可以给 GR IV 更新固件：App 先下载固件，随后经 Wi-Fi 向相机传送。因此无线链路确有固件数据写入接收路径，但官方流程没有提供任意文件目的路径或脚本执行入口。官方说明：[GR WORLD 固件更新步骤](https://www.ricoh-imaging.co.jp/english/products/app/gr-world/firmup/)、[常见问题](https://www.ricoh-imaging.co.jp/english/support/qa/gr-world/)。
- 本地固件 initfs 的 `/usr/bin/webapid` 包含 `PUT /v1/configs/firmware`、`POST /v1/configs/firmware/prepare`、`POST /v1/configs/firmware/cancel`；实现含 `Firmware::SaveFirmware`、`FirmwareTransferManager`、`FirmwareMemoryManager`，并调用相机控制器的 `PreSendFirmware`、`CreateFirmware`、`SaveFirmware`、`PostSendFirmware`、`StartFirmwareUpdate` 等专门接口。
- 反汇编 `FirmwareMemoryManager::Open`（Thumb `0x6BB24`）可见它用固定字符串 `/dev/mem` 调用 `open`，随后调用 `mmap`；`FirmwareTransferManager::PutData`（`0x6C6F8`）用 `memcpy` 把收到的数据放进这块映射内存。上传入口因而是相机指定的固件内存缓冲区，不是一个由客户端自选文件名或系统路径的通用文件上传 API。固件解析与升级还有专门的相机控制器流程；不能由“支持无线更新”推出可把 XPAN 脚本写入任意系统文件。可复核的离线脚本为 `tools/audit_gr4_wifi_firmware_path.py`，记录为 `devkit-output/usb-factory-20261001/wifi-firmware-offline-audit.json`。尚未向相机发送 Web API 上传请求。
- 官方还说明 GR WORLD 可设置 GR IV 的 WLAN SSID 和密码。RTOS 密码设置函数 `0x535D5698` 约束长度 8–63、检查字符类别并明确拒绝 `=`。本地调用图进一步表明：RTOS 中把这些值拼成 shell 命令的 `0x535AB714`，其直接调用点仅在 WLAN 工厂配置函数 `0x535ADAC8`，该函数由工厂命令 `0x0F:0x2A` 选中。普通 Linux WLAN 启动则从相机属性取得 SSID／密码，调用 `HostapdConf::SetValue`、`HostapdConf::Write` 写配置文件。因而不能把常规 App 连接等同于自动触发 RTOS 工厂 shell 构造。工厂 `0x0F:0x2A` 未经实机试验，字符限制、App 端限制和恢复方式也未核实；本轮没有修改 WLAN 设置。官方功能说明：[GR WORLD](https://www.ricoh-imaging.co.jp/english/products/app/gr-world/)。
- 理光 [GR WORLD FAQ](https://www.ricoh-imaging.co.jp/english/support/qa/gr-world/) 确认 App 可以修改 SSID、密码，也提供连接失败时的“Reconnect Settings”。这只是重新建立 App 与相机的连接步骤，不能据此保证异常 WLAN 参数或工厂命令副作用可恢复。GR IV 手册的全厂重置还会删除内存中的照片，不能把它当作本项目可接受的常规回退方法。没有独立恢复验证前，不对用户相机测试带特殊字符的 WLAN 参数或 `0x0F:0x2A`。

### 待用户本机运行的 Wi-Fi 只读探针

用户已确认相机与 GR WORLD 配对，可连接相机 Wi-Fi；Mac 切到相机热点时会暂时失去当前 Wi-Fi 的互联网连接。`tools/gr4_wifi_readonly_probe.py` 已准备好：它先检查 Mac 的 `en0` 是否获得相机网段 `192.168.0.x` 地址，再只向固件中固定的相机地址 `192.168.0.1` 的少数端口发送 `GET /v1/ping`；找到 HTTP 200 后额外发送 `GET /v1/debug/revisions`。不发送 PUT、POST、工厂命令或文件。结果以独占新文件写入本项目 `devkit-output/usb-factory-20261001/`，方便离线回读。当前 Mac 仍在 `192.168.31.x`，本地预检正确拒绝执行；未发生实机 Wi-Fi 请求。

用户只需将 Mac 连到相机热点后，在终端运行：

```sh
cd ricoh-gr4-firmware-analysis-and-feature-expansion
python3 -B tools/gr4_wifi_readonly_probe.py
```

脚本结束后把 Mac 连回原来的网络，再告知结果文件路径。无需移动 SD 卡，也无需提供热点密码。若脚本提示 `not on the camera's 192.168.0.x hotspot`，它在发送请求前已停止；应检查连接状态，不要手动改脚本地址。

**实机回读：**用户将 Mac 连到相机热点后运行上述脚本；Mac 获得相机子网的客户端地址，相机 `192.168.0.1:80` 对 `/v1/ping` 和 `/v1/debug/revisions` 均返回 HTTP 200。前者是 JSON `errCode=200`、`errMsg=OK`；后者列出 13 个组件版本。原始文件为 `devkit-output/usb-factory-20261001/wifi-readonly-20261001-105529-033408.json`，SHA-256 `0d547879b86b92d7135ab755c6682e2a69c3fc3b1a637e87dfd0ed23afc49836`。`tools/analyze_gr4_wifi_readonly.py` 已将这 13 项逐一与本地解包固件 `/etc/revisions` 比对，全部精确一致；结果为 `devkit-output/usb-factory-20261001/wifi-readonly-analysis-20261001.json`。用户已把 Mac 切回原网络。这次仅有两个 GET 请求，未改变相机设置。

## 对 X2D 方法的结论

X2D 方法依赖 `2756:0009` 的 interface 3 与独立 bulk 端点及 HblM 帧。GR IV 当前量产 USB 身份、接口和服务代码均不同；将 X2D 脚本的 VID/PID 改成 GR IV 后发送 `HblShell` 帧没有协议依据。GR IV 确有隐藏 MTP 工厂命令分支，`GetValue` 已从实机读出一个四字节值；静态链条还确认两个固定用途 WLAN 工厂命令能够调用 Linux 命令桥。尚无已验证的任意脚本提交、系统文件写入或可恢复 XPAN 装载方法。

后续若继续 USB 方向，应先离线弄清 `GetVendorMode` 的进入条件、扩展操作码与 `GeneralPurpose*` 的 RTOS 接收端、写入目标和恢复机制，再考虑实机验证。不得把固件中通用 MTP 或 USB 内核模块的存在当成可用的文件写入口。

## 一次固件升级增加 USB 调试配置的可行性（2026-10-01）

**原则上可以设计，但目前没有达到可安装、可恢复的条件。** 已解出的 Linux 启动流程由 `/etc/rc.local` 启动 `usbd`、`sysmgrd`、`mtpd`；原厂 `/usr/bin/usb30dev_mtp_func.sh` 在 configfs 下创建 `functions/mtp.usb0`，只建立 `configs/c.1`，绑定 `19c00000.dwc3`。同目录其他机型／模式脚本也创建单一 MTP 配置。固件内含 ARM `zImage`、设备树和 LZ4 SquashFS；若修改启动脚本或增添 USB 服务，至少涉及被升级包携带的启动镜像，而不只是把一个脚本复制到 SD 卡。

新增 ACM 串口、网络接口或调试 bulk 功能，还要确认内核是否编入相应 gadget function、configfs 接口能否实例化、`usbd`／`sysmgrd` 会不会在模式切换时删除或重建配置、端点数量是否足够，并实现有明确认证边界的服务。初查模块目录只看到 `libcomposite.ko`，继续检查其 `function/` 子目录并从 QEMU 解压后的内核内存读出原始 Kconfig，确认 `CONFIG_USB_CONFIGFS_ACM=y`、`CONFIG_USB_F_ACM=m`，根文件系统包含 `usb_f_acm.ko`、`u_serial.ko`。可复核脚本为 `tools/audit_gr4_usb_runtime.py`，记录为 `devkit-output/usb-factory-20261001/usb-runtime-offline-audit.json`。这证明原厂镜像具有 ACM 编译配置与模块文件，**尚未证明机身运行时能成功实例化或枚举**；本轮未在实机创建功能。

恢复是主要阻碍：理光的[官方升级说明](https://www.ricoh-imaging.co.jp/english/support/digital/gr4_s.html)明确警告，升级中断可能使相机无法工作；[GR WORLD FAQ](https://www.ricoh-imaging.co.jp/english/support/qa/gr-world/)说明固件不能回退。当前已验证的只是更新容器离线重封装、版本字段和局部校验；未验证修改后的启动镜像能通过完整验签／写入流程，也未找到独立于该镜像、可从失败启动恢复原厂的入口。因此不能把“一次升级”当作降低风险的步骤，也不应生成供机身安装的 USB 调试固件。

继续研究时，先离线核对内核 gadget 功能、`usbd` 的配置生命周期和更新器对启动镜像的验证／写入范围；再寻找无需依赖已改 Linux 镜像的原厂恢复入口。现有隐藏 MTP 工厂命令可经原厂 USB 配置到达部分相机服务，优先弄清它的读写目标和回退机制，可能避免为了调试接口先刷写固件。XPAN 第五画幅、预览、JPEG/DNG 和图标仍未安装。

### SD 脚本临时补充 USB 配置的边界

如果获得**已验证的 Linux 命令执行入口**，可以尝试只在运行时修改 configfs：临时解绑 UDC，在原 MTP 配置中加入一个 ACM 串口功能，再重新绑定；退出时逆序删除新增链接和功能并重新绑定。[Linux 内核的 configfs gadget 文档](https://docs.kernel.org/6.15/usb/gadget_configfs.html)明确给出了创建功能、链接到配置、UDC 绑定／解绑的流程。这样的操作不需要改固件版本或闪存文件，正常重启应重新运行原厂脚本。但“能创建接口”“接口能收发数据”“能获得有认证的调试会话”是三项不同的验证，不能只看到一个新 USB 设备就宣布调试成功。

当前卡上的 `startup.ttl` 是 RTOS 脚本。两次同样的 SD→Linux `lcmd` 实验只证明 TTL 运行、上层函数返回 0；Linux 侧标记始终没有出现，详见[桥接重复实验](2026-10-01-sd-bridge-repeat.md)。USB 隐藏 MTP 工厂路径也只验证固定 WLAN 命令，尚未验证任意 shell 文本输入。因此**现在没有已证实的渠道可让 Linux 执行添加 USB 配置的脚本**。直接把 shell 文件放在 SD 卡上不会被原厂启动流程自动执行。

已准备 `tools/gr4_usb_runtime_probe.sh` 作为后续 Linux shell 的只读探针。它只把机型 USB gadget 的 VID/PID、UDC、已有配置／功能、内核 gadget 选项和候选 `/dev/ttyGS*` 输出到标准输出；不解绑 USB、不创建接口、不修改文件。

另备 `tools/gr4_usb_acm_trial.sh`，默认只运行前置检查；必须显式传入 `--trial` 才临时解绑原 MTP gadget、在同一配置中添加 ACM、重新绑定，60 秒后反向删除 ACM 并恢复原 MTP。脚本核对原厂 VID:PID、MTP 链接、UDC、内核选项和模块文件，退出／常见终止信号触发恢复；只写 configfs，不写闪存。**该脚本未在相机执行，其恢复机制也未实机验证**。若执行进程被强制杀死、内核或 USB 控制器异常，自动恢复不能保证；重启后原厂配置应重新建立，但同样需要机身验证。当前没有把任何脚本放入 SD 卡或发送到相机，更没有可靠的 Linux shell 入口可调用它。即便 ACM 成功枚举，还需有受认证的登录或调试服务，才能通过串口操作系统文件。

### 下一轮：一次开机确认 SD→Linux 回复

2026-10-01 检查电脑当前连接状态时，IORegistry 未显示 GR IV，`/Volumes` 未挂载相机 SD 卡；`diskutil` 因当前环境的 DiskManagement 框架不可用而未能列盘。这些结果只说明本次探测未取得设备，不推断相机自身状态。离线检查 `webapid` 可见的调试路由仍只有 `GET /v1/debug/revisions`，没有发现可直接执行脚本的 Web API 路由。

已准备 `tools/build_sd_linux_reply_probe.py` 及生成包 `devkit-output/usb-factory-20261001/linux-reply-probe-v1/`，并配套只读回读分析器 `tools/analyze_sd_linux_reply_probe.py`。新包只含 `script/startup.ttl` 一个文件，3867 字节、SHA-256 `099b8b460b914a573d74930854fd641f9f5d987c0a5f11553fc2824f9904083e`。它沿用两次已验证的 SD 启动和桥对象快照读取，开机等待 45 秒后读本次桥对象的回复标志；只有读到有效原值 0/1 且 `is_linux_boot=1` 时才暂时启用回复，执行 `printf GR4_%s_READY LINUX` 和 `/bin/uname -r` 两条不改机内文件的命令，保存回复，立即恢复原标志，然后回读桥对象。计算出的完整标记 `GR4_LINUX_READY` 不在输入命令中，以免把回显误认成 Linux 执行。已有 `LRTEST.TXT` 时脚本停止，避免重复执行。生成器对调用标签、条件块、命令数、回复开关顺序和输出字节做了电脑端检查。

部署前须检查卷身份、现有 `script/startup.ttl` 和 `LR*` 文件冲突，逐字节核对写入；相机只需一次正常开机、等待至少 90 秒、正常关机，再接回电脑回读。若 Linux 回复仍未出现，不重复同样的实验；根据桥对象前后字节和回复状态判断下一研究方向。此包不创建 USB ACM，不修改固件、系统分区、画面比例或 XPAN 功能。

**部署状态更新：**用户接入 SD 后，电脑识别 `/dev/diskNsM` 挂载于 `GR-SD`，文件系统为 FAT，根目录有 `DCIM`、`RICOH` 和原有 ZIP；没有 `script` 目录或 `LR*` 冲突文件。只新建了 `script/startup.ttl`，写后回读与包逐字节一致，SHA-256 为 `099b8b460b914a573d74930854fd641f9f5d987c0a5f11553fc2824f9904083e`；记录存于 `devkit-output/usb-factory-20261001/linux-reply-probe-v1/deployment.json`。原有照片和 ZIP 未改。已用 `diskutil unmount /dev/diskNsM` 安全卸载并核对挂载点消失。尚未让相机执行；下一步只需把卡放回相机、正常开机等待至少 90 秒、正常关机，然后把卡接回电脑回读。

**实机回读与清理：**用户接回 SD 后，`LRTEST.TXT` 完整记录 `Linux reply probe started` 到 `Linux reply probe finished`，四个输出文件和启动脚本均存在且长度正确。桥对象前、后 117 字节快照的回复标志 `+116` 都为 0；`is_linux_boot=1`，原标志读取成功，两条 `lcmd` 处理函数都返回 0，但计算标记回复和 `/bin/uname -r` 回复均为空。因上层 `lcmd` 固定返回 0，这**不能证明 Linux 收到或执行了命令**。桥对象变化偏移为 `64,72,100,107,109,110,111`，含义尚未核实，不把变化当成功证据。只读分析结果和全部原始文件、哈希清单保存在 `devkit-output/usb-factory-20261001/linux-reply-readback-1/`。清理前逐项核对卡上内容和备份完全一致，随后删除五个本轮文件和空 `script` 目录；保留 `DCIM`、`RICOH` 与原有 ZIP。`diskutil unmount /dev/diskNsM` 成功，卡上无本项目自动启动脚本。本轮未新增 USB 配置，也未安装 XPAN。

### 改走原厂 USB 工厂数据读路径

离线追踪 `0x9094 GetData` 与 `0x9095 SetData` 的 RTOS 接收函数：`ExecCommandGetData` 在 `0x535A9E7C` 将请求参数 0 作为源地址、参数 1 作为长度，复制到返回缓冲；`ExecCommandSetData` 在 `0x535A9D8C` 将请求参数 0 作为目的地址、参数 1 作为长度，从主机共享内存复制。主机侧 `libcamera-controller.so` 的 `GPSetData` 先将输入字节复制到共享内存，再把目的地址、长度和共享内存物理地址发给 RTOS。这意味着隐藏 USB 数据操作**可能**提供直接 RTOS 内存读写，不等于能写 Linux 文件或执行脚本；无效地址可能使相机异常。只读固定哈希审计为 `tools/audit_gr4_mtp_data_memory.py`，输出 `devkit-output/usb-factory-20261001/mtp-data-memory-offline-audit.json`。本轮没有向相机发送 `GetData` 或 `SetData`。

为避免再动 SD 卡，先准备 `tools/mtp_factory_getdata_readonly.py`：只请求实机曾通过 SD 精确读出、同版固件固定的 30 字节文字 `issue ifcmd "ExecLinuxCommand"`，地址 `0x53EA38FC`；严格核对 USB 机型、bcdDevice `0x0111` 和普通 MTP 操作表，不接受用户传入地址或长度，也不发送写命令。最初无相机连接时，脚本正确停于“GR IV is not connected”；随后实机结果见下文。

**2026-10-01 USB 实机更新：**相机在“影像显示”模式连接 Mac 后，设备身份仍为 `25FB:2123`、`bcdDevice 0x0111`。macOS `ptpcamerad` 占用接口；`SIGTERM` 未释放该进程，向本用户的该进程发送 `SIGKILL` 后，固定地址 `0x9094 GetData` 返回 `0x2001`，30 字节与上述固件字符串逐字节一致。结果见 `devkit-output/usb-factory-20261001/getdata-readback.json`。这是**指定 RTOS 地址只读访问**的实机证据，不证明 Linux 系统文件可访问。

随后只读 `tools/mtp_factory_runtime_readonly.py` 从固定 RAM 锚点 `0x553A094C` 取得本次开机命令表 `0x591F1480`、条目数 651，按第 533 项动态定位 `SYS_buildinfo` 行 `0x591F80C4`；处理函数 `0x53054854`、命令名、固件已有的返回 3 短函数字节均与此前 SD 记录和原镜像一致。拍摄属性 `0x55085D63` 读回 `000000803f`（比例 ID 0、倍率 1.0）。结果见 `devkit-output/usb-factory-20261001/runtime-readback.json`。两次 USB 探针都没有发送写命令，卡也未移动。

离线检查 `mtpd` 的 `doGeneralPurposeSetData`：它从 MTP 请求参数 1、2 取目标地址和长度，从数据容器正文取源指针，转给 `FactoryCommandImpl::GPSetData`。按此准备的 `tools/mtp_factory_samevalue_probe.py` 仅能向刚读出的 `SYS_buildinfo` 处理函数槽发送**与原值相同**的四字节，并立即读回。首次实机调用被自动审批拒绝，原因是即使原值写回也属于未验证的实时命令表写入；被拒绝的请求没有到达相机。用户随后明确同意，后续结果见下文。

**用户明确同意后的写入验证：**在保持相机 USB 连接的同一轮，运行了固定四字节的 `tools/mtp_factory_samevalue_probe.py`。`0x9095 SetData` 返回 `0x2001`，随后 `GetData` 读回整个 `SYS_buildinfo` 行与写入前完全相同，记录为 `devkit-output/usb-factory-20261001/samevalue-readback.json`。这验证了 MTP 数据容器及工厂写请求可到达相机；单凭原值写回还不能证明不同值能够落入 RAM。

随后运行 `tools/mtp_factory_pointer_trial.py --trial` 完成一次有变化的最小 RAM 事务：先核对当前命令表锚点、原处理函数 `0x53054854`、命令名、原厂返回 3 短函数字节与拍摄属性；将 `0x591F80C4` 的四字节处理函数指针临时改为 `0x538C9760`，`GetData` 读回该新值；在 `finally` 中写回 `0x53054854`，再次读取整行确认完全恢复。拍摄属性前后均为 `000000803f`。记录为 `devkit-output/usb-factory-20261001/reversible-pointer-trial.json`，独立 USB `--restore-only` 入口已准备，但本次正常恢复，未执行该入口。**这证明 USB 可进行一次受限、立即恢复的 RTOS RAM 修改；不证明所有地址可写，也不证明冷重启恢复、Linux shell、相机文件写入或 XPAN 安装。**

为避免再用 SD 卡，`tools/mtp_factory_bridge_readonly.py` 又从固定锚点 `0x550A03BC` 取得当前 Linux 桥对象指针 `0x59B84D40`。此地址在已审计的 `0x59` RAM 映射中，但与先前 SD 实验的 `0x5A` 堆地址不同；工具先核对对象的前 12 字节与旧快照一致，再读 117 字节。当前回复标志偏移 116 仍为 0；完整快照在 `devkit-output/usb-factory-20261001/bridge-usb-readback.json`。这次没有发送 Linux 命令，因此不能从单个对象快照判断之前 `lcmd` 为什么没有有效回复。最初受限于 `0x5A` 地址范围的探针在读取对象前停止，随后加上已审计的 `0x59` 范围和对象头校验才成功。

进一步静态复核说明 `is_linux_boot` 与真正的 Linux 命令桥采用不同的就绪条件：`is_linux_boot` 通过 `0x535D7100` 查询事件位掩码 `3`，而 `0x535CFF8C` 在分配和提交命令前先调用 `0x535D7118`，后者用掩码 `0x80000002` 轮询。因此此前 `is_linux_boot=1` 与 `lcmd` 上层返回 0，均不足以确认桥的提交条件已满足或 Linux 已执行。当前 USB 只读快照没有解出 OS 事件组的实时位值，也没有发送新的 Linux 命令。XPAN 的第五项菜单、预览、JPEG/DNG 和图标仍未上机。

**XPAN 菜单直接写入边界：**同版原始页表 `0x53004000` 对主画面比例描述符所在的 `0x53D00000` 段标记 AP=6、XN=0；离线枚举全部 4096 个一级描述符，只找到该物理段的一个同地址映射，没有发现可写别名。主菜单回调 `0x531BE2EC`、`0x531BB250`、`0x531BAF70`、`0x531BA14C` 也位于 AP=6 的 `0x53100000` 段。相比之下，实机刚完成的临时事务目标是 AP=3 的 `0x59` RAM。可复核的完整页表扫描已加入 `tools/audit_xpan_memory_map.py`，输出为 `devkit-output/usb-factory-20261001/menu-mapping-offline-audit.json`。这些是初始页表证据，运行时可能改表，但当前**不能**把 `SetData` 在 RAM 成功推成可直接改写菜单描述符或代码；没有对 `0x53` 段发送写命令。下一步需找到可重定向到自有 RAM 的原生菜单入口，以及安全的代码装载、缓存同步与故障恢复流程。

**主菜单入口补查：**`tools/audit_gr4_menu_dispatch.py` 对固定哈希的 RTOS 代码做完整 ARM 扫描，找到 18 处直接构造主菜单描述表地址 `0x53D9F714` 的指令序列。中央计数分派 `0x531BE070` 在 `0x531BE088` 直接构造这个只读基址，按 `0x5C` 行跨度定位描述符，并从 `+0x30` 加载数量回调。原比例数量回调仍直接返回 4。审计报告 `devkit-output/usb-factory-20261001/menu-dispatch-offline-audit.json` 记录全部 18 处地址与初始页表映射。这否定了“只把一个 RAM 指针改到新表就能得到第五项”的简单方案；它不排除经过完整分析后在统一控制点拦截，也不证明实机当前 TTBR0 与初始页表相同。没有向菜单或代码地址发出 USB 写入。

**独立恢复入口核对：**官方 GR IV 升级步骤是在关机时按住 MENU 开机、从 SD 卡进入固件更新界面；[官方升级说明](https://www.ricoh-imaging.co.jp/english/support/digital/gr4_s.html)同时警告更新中断可能使机身无法使用。[GR WORLD FAQ](https://www.ricoh-imaging.co.jp/english/support/qa/gr-world/)明确说固件不能降级。原始镜像在 Linux initfs 之后的另一段数据中含 `Selected SD_BOOT MODE.`，附近还有 `B636 CPU project RX113`；此文字无法证明 GR IV 主 RTOS 有可在损坏后独立启动的恢复环境，更不能作为刷写 XPAN 的回退验证。当前唯一实机验证的恢复是运行中四字节 RAM 指针写回；对于完整菜单、预览和拍摄链代码，没有独立故障恢复入口。

**工程命令候选复核：**实机读出的 651 项工程命令表确有 `SYS_tskrun`、`SYS_script` 和 `file_dd_load`。离线反汇编 `SYS_tskrun`（`0x53052A50`）可见它比较原厂文字 `start`／`stop`、读取 `TMaxTskId` 并遍历已有任务 ID；目前没有发现把任意主机字节作为 ARM 对象载入并执行的受控 ABI。此前 `SYS_script` 的 `start`／`stop`／`pause`／`resume` 是原厂脚本控制词，`file_dd_load` 操作内部文件状态。命令名称都不能代替可执行 RAM 的所有权、入口调用、跨核缓存发布及独立卸载证明。没有向相机试发这些命令。

**统一 RAM 虚表入口核对：**继续搜索 `0x531BE070` 主菜单计数分派的静态指针及 ARM `BL` 调用：固定镜像中没有以四字节数据形式保存该函数地址，却有 25 处直接调用。四个主画面比例回调地址只出现在原厂只读描述符内。这使“复制虚表到 RAM、改一个对象指针”缺少可用的原厂虚表证据。`tools/audit_gr4_menu_dispatch.py` 已把 25 个直接调用点、零静态指针和 18 处描述表基址构造一并固定到审计报告。未发现可靠的运行时注册接口；仅靠字符串检索不足以证明不存在任何接口。本轮没有对相机再发送写命令。

**USB `RunFunc` 入口核对：**固定镜像中，USB 工厂请求分派在 `0x535A9F70` 调用 `ExecCommandRunFunc`（`0x535A9B1C`）。它只从请求参数取类别与命令两个编号，然后调用 `0x535AA068`，在只读地址 `0x53EA0A44` 的 329 项三字节表中匹配这两个编号。已知 WLAN 类别再进入 `0x535ADC24` 的固件内跳转表，目标是直接调用的原厂函数。因此已验证路径**不是**“将 `SetData` 写入的 RAM 地址交给 `RunFunc` 执行”。这不排除其他命令另有可控装载行为，也不构成没有任何 USB 装载渠道的穷尽证明。离线检查脚本为 `tools/audit_gr4_factory_runfunc_gate.py`，固定哈希报告为 `devkit-output/usb-factory-20261001/runfunc-gate-offline-audit.json`；无实机命令、RAM 写入或 SD 操作。

**目前的工程分界：**四字节 RAM 指针事务有读回与单独恢复入口；XPAN 模块则还缺可安全调用自有 RAM 代码的入口、代码／数据内存所有权、指令缓存同步，以及能覆盖菜单、预览、JPEG/DNG 的原生挂接点。第五项需要修改只读菜单数量和多个直接引用，现有 RAM 事务不能完成这些。保持原厂固件和 SD 卡原状，继续以离线调用图寻找可恢复的统一挂接点；在这些条件验证前不向相机提交模块。

**工厂服务对象补查：**固定镜像还表明懒初始化的根对象在 RAM `0x5509F370`，其 `+4` 槽保存约 `0xB60` 字节的 `FactoryCommandServer` 实例指针；实例的前三个虚表指针由构造函数设为 `0x53EA0948`、`0x53EA0970` 和 `0x53EA098C`。第一个虚表 `+0x18` 槽在只读 `0x53EA0960`，原值 `0x535A941C`，经反汇编是工厂消息类型判别短函数；`+0x1C` 为请求设置入口 `0x535A9F94`。已把这些地址加入固定哈希离线审计，并新增 `tools/mtp_factory_server_readonly.py`：只读取固定根对象，先检查动态指针落在 `0x59`–`0x5B` RAM 且四字节对齐，再读取 12 字节实例头与 32 字节原厂虚表并核对，不接受任意地址。电脑端语法和异常指针控制通过。这个 RAM 对象有指针不等于可安全替换：错误虚表会直接影响 USB 命令处理，使同一 USB 恢复通道失效。因此目前不改该指针或方法表。

**实机回读：**用户接上 GR IV 后，`ioreg` 识别到相机。macOS `ptpcamerad` 抢占接口，分开结束进程与运行探针会在进程重启后遭遇 `Access denied`；将“核对当前用户唯一 `/usr/libexec/ptpcamerad`、暂时结束它、立即执行只读探针”放进同一主机进程后成功。`0x9094 GetData` 读取根对象 `f8ffe953a819f7593826f759`，得到本次开机实例地址 `0x59F719A8`；实例前三个虚表指针与固件一致，32 字节虚表的类型判别和请求设置入口也逐字节一致。完整原始字节保存在 `devkit-output/usb-factory-20261001/live-server-readback.json`。这轮只发 `GetDeviceInfo`、`OpenSession`、三个 `GetData` 和 `CloseSession`；没有 `SetData`、`RunFunc` 或相机设置变更。实例地址只对本次开机有效，不可硬编码到安装器。虽然对象自身在 RAM，关键虚表仍在只读 `0x53` 段；改实例首指针还可能切断当前 USB 恢复通道，因此不做写入试验。

**为什么不能只靠逐项写回：**离线调用链固定核对了同一工厂服务对象的请求设置入口 `0x535A9F94` 调用 `0x535A9E88` 分派器，后者分别调用 `0x535A9CB8`（SetData）和 `0x535A9D98`（GetData）。先前成功的 `SYS_buildinfo` 四字节试验改变的是另一张 RAM 工程命令表，其改动不参与这条 USB 路径；因此主机能在 `finally` 中送回原值。如果反过来修改工厂服务实例自身的虚表并令它无法处理请求，主机端即使保存了每个原值，也可能无法发送恢复命令。分阶段备份、每步读回、逆序恢复仍是必要的正常卸载手段，但不能充当这类挂钩的**独立故障恢复**。要试验它，至少还需确认正常断电重启重建该对象的实际行为，并先准备不依赖已改 USB 对象的回退入口；没有对工厂服务对象做写入。

**正常重启的 RAM 恢复实机验证：**在用户确认方便立即重启后，使用 `tools/mtp_factory_reboot_ram_trial.py --arm` 对此前已验证的 `SYS_buildinfo` 诊断指针做一次固定四字节测试。脚本先备份原值 `0x53054854`，将其临时设为原厂 ROM 返回 3 短函数 `0x538C9760`，USB `GetData` 当场读回测试值，拍摄属性保持 `000000803f`。用户随后拔下 USB、正常关机待完全关闭、重开并重新进入影像显示 USB 模式；`--verify` 读到处理指针已回到 `0x53054854`，名称和拍摄属性亦与原值一致，因而未执行写回。USB 设备实例 ID 在前后重新枚举，符合用户报告的重启；动态命令表锚点地址恰好相同，不能单独用地址变化证明重启。完整阶段、备份和回读为 `devkit-output/usb-factory-20261001/reboot-ram-trial.json`，电脑端另外模拟验证了写后读回失败会立即尝试恢复，以及未重启时 `--verify` 会通过 USB 写回。此实验**只验证一个非 USB 服务 RAM 指针在正常重启后恢复**；不验证错误虚表导致相机无法正常重启时的回退，也不验证持久固件刷写失败的恢复。没有修改固件、SD 卡或画面比例。

**代码缓存入口离线补查：**`SYS_cache` 工程命令经 `0x538F0454`／`0x538F04C4` 到数据缓存辅助函数，不能单凭它发布刚写进 RAM 的 ARM 指令。固定镜像另有三处原厂代码按顺序调用数据缓存清理／失效 `0x53087CFC` 与指令缓存失效 `0x53087C78`，地址对为 `0x530882D8/0x530882E4`、`0x5308858C/0x53088598`、`0x5308867C/0x5308868C`。`tools/audit_xpan_runtime_loader.py` 已将这六个直接调用固定到哈希审计，报告保存在 `devkit-output/usb-factory-20261001/runtime-loader-offline-audit.json`。它证明固件内部存在这些缓存维护序列，未证明完整的代码发布协议。后续分析确认第一组位于释放路径，另外两组位于内存服务分派；详见下节。没有向相机写入或执行自有代码。

### 2026-10-01：内存服务参数核对与分配器实机读回

本轮已完成以下三层核对，未执行机内分配或改写：

1. **固件静态依据。** `0x538DD620` 从注册表 `0x5539FEF8` 取服务对象，`malloc` 包装器 `0x538E0A24` 选择服务 2，因此实际入口槽为 `0x5539FF00`。包装器接收 `r0=字节数`，调用对象虚表 `+8`，参数为 `(对象, 字节数, 0, 调用者地址)`；对应释放包装器 `0x538E0A60` 使用虚表 `+12`，接收原分配返回指针。不能将两者与底层按块分配器混用。
2. **实机只读依据。** USB `GetData` 读到入口槽指向 `0x553A0490`，对象登记 ID 为 2，虚表为 `0x53FE17F0`，前四方法 `0x538DEB60 / 0x538DEBAC / 0x538DDF48 / 0x538DE2A4` 与固定镜像逐字节一致。读取前后入口槽不变。此处对象位于固定 `0x55` RAM；报告 `allocator-live-readback.json` 保存 40 字节对象快照，不能把其中的池字段当作无人使用的可写空间。
3. **原始指令参数验证。** `0x53088834` 将系统服务 `0x11` 注册到分派器 `0x53088470`，分派器参数为 `r0=参数记录地址, r1=操作编号`。电脑端用 Unicorn 执行原始分派指令，拦截上下文检查、实际分配/释放和缓存操作，共 9 个案例通过；拦截操作属于模拟，不是机身验证。

| 系统服务操作 | 已核对参数与行为 |
| --- | --- |
| `0x02000411` | 四字记录为输入地址、字节长度、标志、输出指针地址。输入地址为零时分配；原始指令把字节数向上取整成 2048 字节块，再调用 `0x53087F98`。非零输入地址进入 VA→PA 转换与缓存路径，不能误用为新分配。 |
| `0x02010111` | 首字为待释放块基址，进入 `0x5308812C`。该函数增加可用块计数，随后调用 D-cache 和 I-cache 维护；因此早先 `0x530882D8/E4` 调用对位于释放流程。 |
| `0x01010311` | 三字记录为地址、长度、输出指针地址。保存输出地址后依次调用 D-cache、I-cache 维护，正常返回原长度，不能用“必须返回 0”判断成功。 |

两处底层缓存函数内未见 DSB/ISB。系统调用封装、跨 CPU 发布和代码执行时的权限仍待核对；不能据局部序列认定模块能够安全执行。系统服务编号与 USB `RunFunc` 类别/命令编号不是同一命名空间，当前没有把上述参数记录从 USB/SD 安全送入系统服务的已验证适配器。**原厂分配器已确认存在并正在使用；尚未为 XPAN 取得自有内存或安装第五项。**

工具与记录保存在本项目：

- `tools/audit_gr4_native_memory_abi.py`：固定哈希、指令与函数表核对；输出 `devkit-output/usb-factory-20261001/native-memory-abi-offline-audit.json`。
- `tools/mtp_factory_allocator_readonly.py`：仅固定地址 `GetData`，有范围、类、登记 ID、函数表和前后入口检查，不提供分配/写入参数。
- `tools/check_gr4_native_memory_abi.py`：电脑端 9 项参数验证；输出 `native-memory-abi-emulation.json`。首次受限制沙箱下 Unicorn 在 `init_cache_info` 崩溃，用户报告已保存为 `native-memory-abi-host-crash.txt`。正常权限重跑通过；工具新增 `hw.cachelinesize` 查询前置检查，沙箱不可读取时明确退出，避免进入已知会崩溃的备用路径。

本轮没有移动 SD 卡、改版本、写相机内存或内部存储。之前正常重启恢复诊断指针的实机结论保持有效，但不扩展为完整 XPAN 模块或固件刷写的恢复保证。

### 2026-10-01：原厂三参数转接函数与 SD/USB 配合实验

固定镜像中的 `0x53202AF0` 有一段 13 条 ARM 指令的转接函数。入口 `r0` 指向保存记录地址的一字内存；记录为 `[目标函数, 0, r2, r1, r0]`，第二字为零时加载三个参数并尾调用目标。电脑执行原始转接指令和原厂返回 3 短函数通过；另三例仅模拟 malloc、free 和内存服务目标，验证参数路由，不证明实际分配或缓存发布。审计与四例报告为 `rom-call-adapter-offline-audit.json`、`rom-call-adapter-emulation.json`。

SD 解释器初始化将回调写到 RAM `0x553B1948`（发送）和 `0x553B1A30`（回复），原值分别为 `0x538EF3C8`、`0x538EF9F0`。`sendln` 将解析后的 256 字节栈字符串传给发送回调，并将其返回值存入整数变量 `result`。整数名表由 `0x553B2AB8` 的指针与 16 位计数定位，名称宽 32 字节，对应值位于 `0x553B26A4`。

新脚本先通过 `str2code` 自检 `#144#25#59#85`。该命令与 `sendln` 字面字符串共用解析器；原始打包循环使用无符号字节、从高到低拼接，因此预期有符号值为 `-1877394603`，对应四字节 `90 19 3B 55`，其小端值为回复缓冲地址 `0x553B1990`。主机必须读到该自检值、等待阶段 1701、原回调和未知命令返回 -1，才允许实验。

`tools/mtp_factory_rom_adapter_trial.py` 默认只读，显式 `--trial` 才执行以下事务：

1. 将原回调、变量名/地址、回复缓冲前 20 字节和拍摄属性保存到电脑端日志，落盘后才写 RAM。
2. 回复回调暂指向同一个原厂返回 3 短函数；其非零返回跳过回复字符串消费者。等两个串行脚本调用完成，重新确认缓冲与备份一致。
3. 只用回复缓冲的五个字保存 `[0x538C9760, 0, 17, 13, 11]`，然后把发送回调指向 ROM 转接函数。测试目标固定为返回 3 短函数，不接受自选地址。
4. 脚本捕获返回值后不再调用工程 shell，保持 60 秒供 USB 核对。控制器先恢复发送回调，确认在途调用结束，再逐字恢复缓冲，最后恢复回复回调，全部读回确认。

写操作限定为上述七个固定 RAM 字，不改 USB 服务虚表、菜单、固件或版本。`--restore-only` 核对日志身份、变量表范围/名称和现场已知值，拒绝覆盖不相关内容。主机事务模型的十项检查覆盖成功、部分记录写入后失败、发送回调读回失败、超时、异常返回、恢复写失败后的独立重试、脚本代次变化、前置拒绝、错误二进制输入和非法日志；报告 `rom-adapter-transaction-checks.json`。代次变化等无法证明在途调用结束的情况保留有效记录，不宣称恢复成功。

**部署：**用户接入 `GR-SD`，核对为外置可移除 FAT32 `/dev/diskNsM`，根目录无旧 `script` 或 `XPGATE.TXT`。只放入 `script/startup.ttl`，2217 字节、SHA-256 `bb297ca66eead51d5ae525e9ec196eb02170ce72ea3a7c82efe20b060c85c665`；写后逐字节核对通过并安全卸载。包及部署记录位于 `devkit-output/sd-usb-call-gate-20261001-v2/`。照片、原有 ZIP 和目录保留。较早未部署候选包不再使用。

此时尚无实机转接执行结果、实际内存分配或 XPAN 安装。USB 只读上下文尝试时相机已断开，未取得现场数据。此前正常重启只验证一个诊断指针；两个脚本回调槽的正常重启恢复需要本轮核对，不能提前保证。停用 SD 实验需备份 `XPGATE.TXT` 并按部署哈希移除本项目启动脚本。离线核对另外确认 `SYS_mplt`、`SYS_mpft` 是池状态/列表查询，内部临时数组最终释放，不能当作取得长期可用 RAM 的接口。

**本轮实机结果更新：**用户放回卡并开机接 USB 后，只读核对得到名表 `0x5922EF00`、8 个全局整数，`xpg_state=1701`、`xpg_return=-1`、`xpg_calls=83`、输入自检 `-1877394603`，两个原回调及 ROM 字节全部匹配。随后限定事务成功：脚本捕获 `xpg_return=3`、阶段 1702、调用计数 114；控制器逐项恢复两个回调和缓冲 20 字节，读回一致。拍摄属性前后都是 `000000803f`。日志 `rom-adapter-trial.json` SHA-256 为 `37e10cadda46746a2edfe529fc2973b252ebc8132950d2641264d17c5cd553f7`。

独立只读会话的动态名表检查在脚本结束后拒绝访问；只读固定表头确认指针已归零而旧计数仍为 8（`000000000800`）。固定读取两个回调、20 字节缓冲、拍摄属性再次与原值一致，记录 `script-context-after-restoration-fixed.json`。据此补充只读工具对已释放表的识别：不跟随空指针，不报告活跃变量，也不允许新的调用事务。恢复工具在全部七字已恢复时直接核对并报告成功，无需访问已释放的变量表。

**已证实：**SD 四字节输入、自检、RAM 回调转接至现有 ROM 函数、返回值捕获、逐项写回原值和独立 USB 回读。尚未实机确认目标函数收到的三个参数（返回 3 短函数不使用参数）、malloc/free、缓存发布、执行新代码或 XPAN 菜单/图像链。自动恢复依赖 USB 及脚本仍可核对；未把本次正常卸载扩大为全部异常恢复或刷写回退保证。十分钟是脚本等待连接的上限，不是开机后必须等待的时长。

### 2026-10-01：连续调用协议与一轮内存生命周期实验

为合并后续测试，准备协议 1801：主机只在回调与缓冲恢复后发布下一个编号；脚本仅在 `go=done+1` 时调用一次相同四字节输入，并保存结果和完成编号，返回值为 -1 也不会重复调用。每次开机最多 16 个请求，等待约 15 分钟；编号和主机写入的随机会话标记防止断线恢复时重发，以及正常重启后使用上次的堆指针。只有主机写入调用记录、切换回调并发布编号才执行测试；SD 脚本自身不写这些 RAM 字。

`gr4_usb_call_session.py` 的目标白名单只允许返回 3 短函数、`malloc(8192)` 和对本会话确认返回地址的 `free`。调用的参数记录仍占已验证回复缓冲的五字，逐次恢复两个回调和缓冲；另外只允许改已核对名称和位置的主机编号、会话标记，以及新申请内存前 32 字节。写前日志落盘。已发布请求未完成时保留转接和参数记录，不把排队的释放变成普通 shell 命令；断线后先确认旧编号完成，再恢复和处理所有权。

追加原始指令审计：堆 vtable `+24` 为 `0x538DDF1C`，默认有效范围来自对象 `+0x24` 的基址和 `+0x1C` 的长度。只读工具核对方法与范围，返回的 malloc 指针及 8KB 尾端必须位于该范围内；读取 `pointer-8` 的分配来源，再允许自有区域数据测试。malloc 在 `0x538DE008` 保存来源，free 在 `0x538DE350` **先清空来源**再调用内核释放；成功状态转为布尔值 1，失败为 0。这意味着完成的 free 即使返回失败也不能重试，避免使用已变化的头部。

`mtp_factory_allocator_trial.py --trial` 的一轮包含：原厂返回 3 → 申请 8192 字节 → 自有区域 32 字节备份/写入/回读/原值恢复 → 配对释放（须返回 1）→ 再次返回 3。`--recover` 根据已完成请求账目处理未确认结果，不重复申请或释放，跨重启拒绝旧地址。数据恢复若失败但调用通道仍正常，也尝试释放准确的自有指针；执行或释放状态不明时保留日志，停止新请求。正常回调恢复和成功释放可验证，USB 故障、阻塞和重启后的完整恢复仍需实机验证。

电脑协议/事务模型十项通过：完整四次调用、记录部分写入失败、申请编号提交后失败、释放编号提交后失败、自有数据写入失败、分配返回零、释放返回失败、申请后 USB 中断恢复、释放后 USB 中断恢复、重启会话变化时拒绝旧指针。模型最多申请一次、释放一次，故障结果不是实机分配证据。报告和候选单文件包在 `devkit-output/sd-usb-session-20261001-v1/`；启动脚本 2059 字节，SHA-256 `221d79821b4f7cbd2028477001529b02dcb8f9bfcf016cecffa11c71cf071c59`。

**部署更新：**用户正常关机后接卡。核对旧 `startup.ttl` 哈希及 `XPGATE.TXT` 日志，逐字节备份至新包的 `card-backup/`；日志记录阶段 1702、返回 3、计数 114、自检值 `-1877394603`。只替换 `script/startup.ttl`，回读一致，删除已核对备份的旧项目日志；照片与其他文件保留。已安全卸载 `/dev/diskNsM`。新包尚未上机分配或上传代码。

离线另找到只读 CPU 编号函数 `0x53000844`（MPIDR 掩码 3）与 TTBR0 读取函数 `0x53000850`，均有原厂返回指令；尚未核实脚本调用上下文权限，未加入本轮白名单或执行。它们可用于后续核对实际 CPU/页表，不据此宣布堆可执行或跨核缓存已同步。


**连续调用实机结果：**用户开机接 USB 后，现场 12 个变量，阶段 1801，go/done 为 0，输入自检匹配。整轮四次调用编号 1～4 成功，返回依次为 3、malloc 地址 `0x5A0C20D8`、free 成功值 1、3。8KB 范围位于原厂堆 `0x59600000..0x5A5FFFF0`；来源头为 `d0200c5a7a75d57f`。32 字节测试模式回读与原值恢复均通过，四次的回调与临时缓冲全部恢复，拍摄属性前后 `000000803f`。日志 `allocator-session-trial.json` SHA-256 为 `41001e58709e9bb9632154debf27ae0bf6f3eb77be413dfcc92e18507fcd5aac`。没有保留未释放分配，也没有上传新代码或改菜单。会话编号与标记作为本轮记录保留在解释器变量中，等待后续调用或脚本结束。


### 2026-10-01：缓存服务实机批次与脚本任务／页表合并读取

**缓存批次已完成。** 复用协议 1801，固定系统调用包装器 `0x53065A8C` 查询内存信息，`0x53065A40` 执行服务 `0x01010311`。本次新会话标记 [省略]，五个请求依次为 malloc、查询、缓存维护、free、返回 3。申请指针 `0x5A0C2038`，自有对齐范围 `0x5A0C2040..0x5A0C2080`，输出位于 `0x5A0C20C0`；查询返回 0，输出 `[0x5A0C2040,0x5A0C2000,2048,64,64]`；缓存维护返回长度 64 并正确回写范围地址。2048 是内存服务粒度，不能当成 ARM 页大小。数据 32 字节与输出 20 字节均恢复，准确 free 返回 1，末次原厂诊断返回 3。全部回调、缓冲及拍摄属性恢复，无保留分配。日志 `cache-session-trial.json` SHA-256 `44465fcdafeab5af33b1f501a6f08c487bab29c9db8a96c173c5f6447180a39c`。未上传／执行新代码。主机模型扩展为 14 项，包含缓存失败、缓存期间断线和同一开机连续两批。

**任务页表路径已追到。** 原厂调度器 `0x53086C90` 根据 TCB `+0xC0` 切换 TTBR0；字段为零则保留已有 TTBR，不能据零值推成初始表。脚本构造函数 `0x538F0570` 使用任务配置行 0x4B，虚表 `0x53FE5880` 的第三槽为 `0x538F0C24`，任务名称指针 `0x53D7C12C` 为 Script。线程登记根在 `0x553A0030`，链表节点 `+8` 指向线程对象；对象 `+4` 保存 ID。内核 TCB 表由 `0x55824CE0` 定位、最大索引由 `0x55824C74` 限定，行跨度 0x500；内核任务池实际位于原厂可读的 0x57 RAM，区别于应用堆。

`mtp_factory_task_mapping_readonly.py` 一批读取上述链、脚本对象、保存栈帧、当前任务、相关页表条目、比例描述符与调用恢复状态。第一批因原有动态地址白名单没有包含内核 0x57 区域，在跟随 TCB 前拒绝；原始读取和错误完整保存为 `task-mapping-live-batch-01.json`。离线核对 0x570／0x57F 初始映射并新增独立只读内核范围后，第二批成功：脚本对象 `0x5960E048`、ID `0x01000020`、TCB `0x57098B08`；其 TTBR 字段为 0，保存 CPSR `0x600E0013`、PC `0x5307E07C`。当前三个运行任务的 TTBR 字段也为 0。**这仍不是实际 TTBR 寄存器读回。** 初始表中菜单／代码段 AP=6，堆段 AP=3、XN=0；原比例描述符逐字节相同，原回调已恢复。完整报告 `task-mapping-live-batch-02.json` SHA-256 `1677138def787003bb2ed17764b612dbd6a4f465258b6709ea28471b891999f4`。

原厂任务创建器 `0x5306AEEC..0x5306AF30` 根据属性位 8..9 建立初始执行模式：0 则 SVC 0x13，非零则 SYS 0x1F。现场脚本属性为 `0x00021003`、入口 `0x538E1F70`、exinf 等于脚本对象，支持脚本原厂执行模式的核对；睡眠期间保存的 SVC 帧单独不足以推断其上层执行模式。

**下一批工具已准备，尚无实机执行结果。** `mtp_factory_ram_leaf_trial.py` 把权限读取、申请、固定三条 RAM 指令（ISB；返回 65；BX lr）、代码发布、恢复与释放合为 16 请求；默认只读，显式 `--trial` 才执行。仅允许固定 ROM 目标与精确自有叶函数，不接受任意代码。SCTLR 候选读取使用 `0x530008B4`：唯一允许的掩码全为 1，读取后写回相同值，不改变控制位；实际 TTBR 须等于初始表，MMU／WXN／UWXN 与自有段映射须通过。代码发布序列包含自有缓存服务、DSB、原厂 ICIALLUIS、DSB 和 ISB；恢复字节同样同步后再释放。参考 [Arm ARMv7-A/R 架构手册](https://documentation-service.arm.com/static/5f8daeb7f86e16515cdb8c4e) 的代码修改缓存与同步要求；不得把本测试扩大为任意多核菜单挂钩验证。

六项本地模型检查通过，包括完整 16 请求、部分载荷写失败、错误返回、RAM 返回后断线、恢复同步期间断线及非法控制参数拒绝。恢复同步保存独立步骤编号，断线后不重发完成请求。报告 `ram-leaf-model-checks.json`；模型中的 CP15／RAM 执行属于模拟。实机调用在发送相机命令前未找到 USB 设备，故尚未写入载荷；XPAN 第五项、图标与预览／保存仍未安装。现有 SD 单文件无需修改。


**RAM 叶函数第一批实机更新：**已读取原厂 CPU 函数返回 0、实际 TTBR0 `0x53004000`、SCTLR 同值回写返回 `0x00C51C7D`，通过 MMU／WXN／UWXN 条件；申请自有内存 `0x5A0C2110`、对齐载荷地址 `0x5A0C2140`，对应段 `0x5A014C26`。三条代码已写入并回读，但**未执行**。原厂 `0x53087BF4` 使用 `(3,1)` 返回 `0xFFEF0000`，发布检查拒绝；恢复同步同样被参数拒绝。独立恢复核对无 RAM 入口调用、无指针残留后，恢复自有字节并准确 free 返回 1，回调／缓冲／拍摄属性全部恢复。日志 `ram-leaf-session-trial.json` 保留原错误和完整 11 请求，不覆盖。

参数错误来自此函数对位组合的校验，不是缓存功能不存在：ROM 分支要求 `(2,1)` 才走 `0x53087C70` 的 ICIALLUIS；`(3,1)` 在 `0x53087C4C` 的校验后返回参数错误。原始 ARM 执行检查复现两个分支（实际缓存指令拦截为模拟）；第三例执行精确三条载荷返回 65，均保存在 `ram-leaf-arm-checks.json`。同一开机利用剩余编号 12～14 实机调用修正后的 `(2,1)` 返回 0、DSB 返回 0、ISB/CCSIDR 读取返回 128，三次回调均恢复；报告 `ram-services-session-trial.json`。这验证原厂发布原语可调用，不证明 RAM 代码已运行。

**第二批与独立恢复：**用户正常重启后，CPU 返回 1（说明脚本不固定在一个核）、TTBR0 仍为 `0x53004000`，SCTLR 仍为 `0x00C51C7D`。申请 `0x5A0C20A0`、写入载荷；编号 5 的自有缓存调用已发布，但主机在多次读变量表时观察到一次不一致，立即停止 RAM 入口。独立恢复确认编号 5 返回 64，恢复字节并编号 6 free 返回 1；全部回调恢复，无保留分配。报告 `ram-leaf-session-trial-v2.json`。最初错误没有保留不一致的原始表头，不能认定真实重启、传输问题或缓存原因；现已给检查加入原始预期／实收字节记录，保持同样拒绝条件，没有放宽代次或 token 校验。

随后同一 USB 连接连续 24 次完整控制快照均成功，表头始终 `00ef22590c00`、token [省略]、go/done 6，无复现；报告 `variable-read-consistency-batch.json`。生命周期模型现为 7 项，增加发布原语拒绝：RAM 入口没有调用、临时指针已恢复时，允许恢复数据后释放，不依赖被拒绝的发布函数。新一批使用独立 v3 日志，先前两个失败批次及恢复记录保留。XPAN 菜单／图标／图像链仍未安装。
