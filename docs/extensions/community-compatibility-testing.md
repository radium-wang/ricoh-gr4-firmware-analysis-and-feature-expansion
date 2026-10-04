# Community compatibility testing

The maintainer does not need every camera body to start an adaptation. Firmware inspection and desktop tests can be done locally; volunteers supply the observations that require hardware. Each edition and menu firmware remains a separate target.

## Participant workflow

1. Open **Compatibility testing** in GR Shutdown Studio 0.3.0. Select the exact edition and the firmware shown in the camera menu. All ten catalog editions are available; **Other version** accepts versions missing from the selection. The update-history list is a convenience, not proof that an older release applies to an edition.
2. Create a record on your computer. Record whether the factory menu has already been opened and whether a shutdown graphic is visible. “Not checked” is a valid answer; this intake does not ask you to run another model's factory script.
3. Optionally select an existing, unpacked official `.bin` update file for that camera family. The app records its header and SHA-256. A different family is rejected. A matching version string still does not authenticate the firmware installed on the camera.
4. If a shutdown JPEG has already been extracted through a reviewed method for that exact model, use **Preserve extracted original**. The app keeps identical `original.jpg` and `recovery/original.jpg`, refuses different existing copies, and verifies both when exporting. Copy the whole record folder to another storage device. An ordinary photo imported here does not prove a camera resource or enable an installer.
5. Use **Save report** and attach the JSON to a [compatibility issue](https://github.com/radium-wang/ricoh-gr4-firmware-analysis-and-feature-expansion/issues/new). Keep firmware, JPEGs and the record folder private. The report contains selected observations, hashes, sizes and JPEG structure metadata; it omits EXIF, pictures, file paths and body identifiers. Nothing is uploaded automatically.

Research records can be reopened with **Open record**. They use `research.json`, not `session.json`, and cannot be opened as installer sessions. The imported original's source is explicitly marked as user-supplied rather than camera-attested.

## Tests currently available on a camera

The main **GR IV series** workflow accepts other menu versions for backup experiments, including the known Monochrome model/target mapping. The firmware menu also lists 1.04 and 1.03 as backup tests. These use the existing SD copy preflight and read-only resource-export path. A failed preflight, unknown model, missing output or invalid JPEG stops the sequence. Successful backup of an unqualified combination ends at **Backup test complete**, with report export as the next action; no image installer or restoration writer is generated.

The new intake can collect evidence for GR III, Street, Diary, HDF, GR IIIx and IIIx HDF, but does not yet supply their camera backup scripts. Urban's existing camera workflow remains specific to 1.60. Do not use its factory entry, resource drive or JPEG assumptions for another body. The catalog's installation preview still consists of GR IV / HDF 1.11 and Urban 1.60; the complete app needs hardware qualification.

## Maintainer workflow without owning the bodies

1. Group issues by exact edition and declared menu version. Begin with the current official versions, then work through older versions requested by volunteers. Separate user observations, container-header inspection, resource reads and actual write/readback results.
2. Inspect existing firmware inputs with `tools/audit_shutdown_compatibility.py`. A decoded payload can help locate candidate resource names and relevant file/JPEG routines; its correspondence to the container must be established separately. Resource strings and a common update package alone do not identify a body's selected resource.
3. For a missing model, review its factory entry, product identification and resource drive/path before distributing a dedicated read-only probe. Use a small SD-to-SD copy check first. Then export the resource to SD and preserve it on the volunteer's computer. Repeated-read evidence needs a fresh camera export, not a second hash of the same old SD output.
4. Review original length, JPEG structure, copy/truncation semantics and the exact restoration target. Only then prepare a limited write experiment for that model/version and one volunteer. Require the computer original and recovery copy before writing. Complete readback, the visible shutdown screen, restoration, another complete readback and restored-screen confirmation are separate results.
5. Prefer cross-checking the same combination on a second body. Identical original hashes are not proof of independent bodies; no body identifier is collected by these reports. Review the evidence in a PR before adding an exact version to `tested_versions`. Submitted reports never update the installer catalog automatically.

Synthetic desktop tests check backup preservation, refusal paths and script generation. Firmware inspection or emulation can reduce uncertainty, but cannot establish physical filesystem behavior, shutdown JPEG acceptance or recovery after an interrupted camera write. Those observations still need volunteers or a temporarily borrowed/rented body.

## 中文

不用先买齐所有机型。维护者负责固件分析、桌面验证和审核探测脚本，网友提供必须在相机上完成的观察结果。每个特别版、每个菜单固件版本单独记录。

### 发给网友的操作步骤

1. 在 0.3.0 的侧栏打开 **适配测试**，选择准确机型及相机菜单显示的固件。10 类机型均可建立记录，列表没有的版本用“其他版本”填写。历史版本列表不代表每个特别版都能使用这些更新包。
2. 在电脑上建立记录，记录工厂菜单是否已成功打开、关机时是否有图片。不确定就选“未检查”，不要拿另一机型的工厂脚本来试。
3. 可分析已有的官方更新 `.bin` 文件，记录包头版本与哈希。不同系列会被拒绝；版本字符串相同也不能证明相机实际安装的固件。
4. 如果已经通过该机型的已审核方法读出关机 JPEG，可用“保存已读出的原图”保留两份完整副本。已有不同备份不会被覆盖，导出报告前会再次核对。再将整个目录复制到另一存储位置。随便导入一张图片不会开放安装，也不能证明资源路径。
5. 保存 JSON 报告并提交[兼容性 issue](https://github.com/radium-wang/ricoh-gr4-firmware-analysis-and-feature-expansion/issues/new)。报告不含图片、EXIF、文件路径或机身标识；固件、原图和整个记录目录保留在自己电脑上。App 不会自动上传文件。

研究记录用 `research.json`，可重新打开继续；安装记录用 `session.json`。两者不能混用。导入 JPEG 明确标为用户提供的文件，不当作相机自动读回证据。

### 当前能测到哪一步

GR IV 系列其他菜单版本可走已有的 SD 复制检查和只读资源导出流程，菜单增加了 1.04、1.03 的“备份测试”入口。Monochrome 也可按已有的机型和资源映射做备份实验。复制检查失败、型号未知、输出缺失或 JPEG 无效时停止。未确认组合完成后停在“备份测试完成”，下一步是导出报告，不生成安装或恢复写入脚本。

GR III 普通版、Street、Diary、HDF，以及 GR IIIx 普通版、HDF 目前开放资料收集，尚无它们专用的相机备份脚本。不能套用 Urban 的入口、资源盘符或 JPEG 参数。安装预览仍限于 GR IV / HDF 1.11、Urban 1.60，完整 App 流程还需实机验证。

### 维护者怎么推进适配

先按“机型＋菜单固件”整理报告，从官网当前版本优先做起，再处理网友实际使用的旧版本。我们分析固件中的入口、机型识别、资源路径和 JPEG 调用，再给对应志愿者提供专用只读探测包。先测 SD 到 SD 的复制，再读出资源、保留电脑原图。重复读取必须重新从相机导出，不能只对旧 SD 文件再算一次哈希。

确认目标、文件长度、复制与截断行为、恢复路径后，再安排单个组合的小范围写入实验。依次记录替换、完整读回、真实关机显示、恢复、恢复后的完整读回及显示。最好再由另一台相同组合交叉验证；相同原图哈希不能证明是两台机身。证据经过 PR 审核后才增加精确安装版本，报告不会自动解锁安装。

固件分析、模拟和桌面测试可以提前排除问题，但相机文件系统行为、JPEG 显示及写入中断后的恢复仍需志愿者或借来的机身验证。备份不能保证相机内部写入是原子的，也不能找回测试前已经丢失的出厂原图。
