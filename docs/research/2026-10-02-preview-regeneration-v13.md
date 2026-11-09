# 2026-10-02：原厂尺寸重建与离线补丁推进（v13）

## 当前状态和方向

XPAN 尚未上机。用户要求减少反复取样，后续以解包固件的调用链、补丁候选和离线 ARM 检查为主，只保留候选上机前必要的实机核对。本轮没有连接相机、调用机内函数、修改相机 RAM、写 SD 或刷固件。当前相机可以关机。

固件样本 SHA-256 为 `c4e597c7c9ca1bc181b30e35139ed90a4fd876ddcca14f12be0e00b6702233ae`。现有菜单、比例和 JPEG/DNG 分析可用于将来的固件补丁；容器封装、升级校验、版本和刷机恢复是独立待验证工作。

## 修正上轮实机观察的解释

此前 USB 读到八个 recipe 槽为空，不能因此推断 USB 一定停止取景。用户已明确确认 USB 保持连接时能回到实时取景；`capture-preview-shooting-live-v3.json` 在该状态读取八槽仍为零。此集合暂不能作为已确认的活动预览挂接点。

该报告读取 JPEG 源宽高/pitch 为 `[6192,3480,6208]`，信息对象逻辑窗口为 720×405（坐标缩放 4096，中心 Y=37.5）。manager 的 source/resolution/external 为 2/3/1，与旧候选限制 0/(7,29,30)/0 不匹配。原有 native adapter 的拒绝条件保持；不把该实机模式直接纳入安装许可。

`preview-snapshot-postboot-usb-v2.json` 中 一个 JPEG 样本 为 6192×3480，DNG DefaultCropOrigin=[28,348]、DefaultCropSize=[6192,3480]，raw=6304×4224。照片前缀只解析元数据，不保存图像字节。PTP 未公开 XPV12 诊断目录。24 次名称表检查为空/count36，未调用 protocol1801，不能据此证明 SD 脚本执行完毕。

读取工具增加 `--skip-jpeg-config`：实机配置指针 0x5EF57140 超出原有动态范围保护，该选项明确省略此对象，未放宽范围或跟随高地址。

## 原厂直接调用和额外重建路径

`audit_gr4_preview_consumers.py` 扫描固定 ARM BL 指令区域 0x53000000..0x53D00000，核对 16 个调用和四条尺寸存储。它不覆盖间接调用或全部 Thumb 代码。

除 0x53647498 helper 外，0x53643800..0x536438A0 还调用原厂宽高包装器，并重写 recipe 的 BD6/BD8/BE4/BE6。因此单次 helper 后修改高度不是完整的预览接入。此路径是否当前帧使用者仍未证明。

实机 manager 模式的 12 项原 ARM 尺寸分支检查保存在 `live-preview-mode-arm-v2.json`。例如 aspect=1、flags=0/0 返回 1152×404；flags=0/1 返回 720×404；flags=1/0 返回 720×480。同一对象的缓冲区/显示查询不能混为一种尺寸，更不能把 1152 当 LCD 可见像素宽。

第一版模式报告 v1 漏传 external=1，保留为失败的建模过程记录；v2 才复现该字段。两版当前结果相同，不据此宣称所有路径中 external 无作用。

## 已实现的局部修正和恢复

`check_gr4_preview_regeneration.py` 执行原厂重建的指令片段及实际编译的 portable XPAN apply/undo。对象和任务同步为模型，未执行完整初始化器/驱动。重建会恢复原始高度，却不改已有 XPAN 居中 Y，使旧 apply/undo 正确拒绝这个混合状态。

新增 `gr4_xpan_preview_recipe_reapply_after_regeneration`，要求 owner 已暂停并排空使用者。只接受同一 target、原宽/高、factor、已知 applied Y 和合法 undo；临时还原 Y 后使用既有 apply 完成其余验证。失败还原原 Y，未知偏移不覆盖。两个模式的 ARM 检查覆盖重建、旧拒绝、新协调、错误 alignment/未知 Y 不变和完整局部撤销。alignment=2 仍是模型假设。

报告 v1 是修正前的覆盖/冲突复现，v2 包含修正后的协调和恢复。这个函数未绑定 call-site，不是安装器；原厂四比例、菜单第五项、图标、LCD/AF、JPEG/DNG、属性通知和模块卸载仍需完整接入。

## USB 文件回收工具（备用，尚未实机执行）

新增 `audit_gr4_sd_file_abi.py`、`mtp_factory_sd_file_trial.py`、`check_gr4_sd_file_trial.py`。只允许 C:\XPV12\PROCESSA.BIN（960）、COLLA.BIN（48）、PROCESSC.BIN（960），固定 ROM stat/open/read/close，不加载 RAM 执行代码。默认仅核对身份；trial 最多 16 调用，数据仅在本次 malloc 的 8192 字节内使用 2048 字节。

长度必须与原厂 stat 精确一致才可打开和读取，不读 EOF。原厂 read 成功只返回请求长度，没有独立实际读取长度，因此文件在 stat/read 之间改变的情形仍不能被此返回值完全排除。三个数据先持久化到主机 ledger，再复用 RAM。已完成的 open/close 通过序号恢复记账；close 失败不重试，保留账本并要求重启。正常路径先恢复数据/回调，再释放分配。

原厂 open flag=0 被包装为 native mode=1；固定 FAT 模式表将其映射为低层 flag=0。已执行这一段原 ARM 和服务模型；尚未执行真实 FAT I/O，也未证明当前挂载后端的完整只读语义。因此该工具本轮没有在相机运行。

离线 9 项生命周期/故障模型和 8 项原 ARM ABI 检查通过，包括断线后的 open/read/close、长度不符不打开、缺失文件不读、completed close 失败不重复和 owned RAM/回调恢复。真实服务回调仍为模型。

## 证据和下一步

`ui-source-snapshot-v13` 与 `ui-development-evidence-v13.json` 保存本轮源和报告；先核对 v12 的既有 artifact 哈希，旧证据不覆写。

下一步以解包代码继续收敛比例菜单、预览重建/发布、JPEG/DNG、资源图标的补丁点和装载/撤销方案。单个函数模型通过不能证明完整固件可刷或相机已能拍 XPAN。
