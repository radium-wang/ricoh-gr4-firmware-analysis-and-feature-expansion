# GR IV SD→Linux 桥接重复实验记录（2026-10-01）

## 目的与样本

确认 GR IV 01.11.10.07 的 SD 启动 TTL 能否通过工程命令 `lcmd` 让 Linux 执行 SD 上的脚本，为后续 XPAN 运行时装载判断提供证据。对照的本地解码固件 SHA-256 为 `c4e597c7c9ca1bc181b30e35139ed90a4fd876ddcca14f12be0e00b6702233ae`。本实验**没有安装 XPAN**，没有写入固件、相机资源、拍摄设置或 RTOS 代码。

输入包由 [`build_sd_bridge_gate.py`](../tools/build_sd_bridge_gate.py) 生成，核心文件是 `script/startup.ttl`（2866 字节，SHA-256 `a0e9db6c9878e721ac697120ee3329cc19cf944b982d4c566a94e12655b2a3d8`）和 `BRRUN.SH`（215 字节，SHA-256 `5951acb8a68428afb739d12418589911b3f2d8b4c667140311e4f5af3ea3679f`）。TTL 首先创建 `BRTEST.TXT`，后续开机遇到该文件就停止，避免重复命令。它等待约 10 秒后读取本次开机的桥对象、调用 `is_linux_boot`，就绪时发送一次 `lcmd`，再检查 Linux 脚本应创建的 `BRDONE.TXT`。两轮都使用同一输入字节；部署清单分别位于 `devkit-output/xpan-bridge-gate-20260930/deployment.json` 和 `devkit-output/xpan-bridge-gate-20261001-repeat/deployment.json`。

## 原始读回

两轮的逐字节备份、每文件 SHA-256 清单和清理记录保存在以下忽略目录，不纳入 Git：

| 轮次 | 读回目录 | `BRTEST.TXT` SHA-256 | 桥对象地址 |
| --- | --- | --- | --- |
| 1 | `devkit-output/xpan-readbacks/2026-10-01-bridge-gate-1/` | `c2e66c5a91c261bd96b241f74e6fddbd54e992606cc6d85c1961722ad41bc90a` | `0x5A080E30` |
| 2 | `devkit-output/xpan-readbacks/2026-10-01-bridge-gate-repeat/` | `c2e66c5a91c261bd96b241f74e6fddbd54e992606cc6d85c1961722ad41bc90a` | `0x5A080E38` |

两轮读回均显示：

- `BRTEST.TXT` 有完整的 `bridge gate started` 与 `bridge gate finished`；SD 启动 TTL 确实在相机上运行。
- `BRBOOT.BIN` 精确 768 字节，`BRPRE.BIN` 与 `BRPOST.BIN` 各精确 117 字节。桥对象地址均在本轮受限读取区间内。
- `is_linux_boot` 返回 1；`lcmd` 上层处理函数返回 0。响应标志 `+0x74` 前后均为 0。
- 两轮均无 `BRDONE.TXT`。桥对象前后在偏移 `64,72,92,96,109,110,111` 有变化，但字段含义未核实，不能据此解释为 Linux 执行成功或失败的具体原因。
- 输入、结果已备份并核对，再从卡上清理；`script` 目录已移除，卡安全弹出。照片 `DCIM`、`RICOH` 及来源不明的 ZIP 未改动。

[`analyze_sd_bridge_gate.py`](../tools/analyze_sd_bridge_gate.py) 仅以精确内容 `XPAN_BRIDGE_EXECUTED\n` 的 `BRDONE.TXT` 作为 Linux 脚本执行证据；两轮分析均为 `linux_execution_proven: false`。它不把 `lcmd=0` 解释成成功。

## 静态补查与结论边界

[`audit_sd_shell_path.py`](../tools/audit_sd_shell_path.py) 固定哈希核对：`is_linux_boot` 对事件位 3 作零等待查询；`lcmd` 的下层桥 `0x535CFF8C` 先调用 `0x535D7118`，后者使用不同的事件掩码 `0x80000002`；上层 `lcmd` 丢弃桥调用结果并固定返回 0。因此 `is_linux_boot=1` 不能推出 Linux 已收到或执行命令。缺少标记也不能单独确定是桥接未就绪、命令参数、SD 挂载路径还是 Linux 侧执行失败。

当前 SD→Linux 装载通道未验证。后续若继续查，应取得下层桥接结果或 Linux 侧实际输出，再决定是否研究运行时装载；不重复这套相同探针。XPAN 第五项、实时预览、保存画幅及可恢复卸载仍未在相机上安装或验证。
