# Shutdown-image compatibility

The target is coverage of GR III, GR IIIx and GR IV editions and firmware versions. Current repository evidence supports only the preview workflows below. A shared official update package, resource filename or successful computer JPEG decode does not qualify another body or firmware.

| Camera | Firmware recorded in repository evidence | Desktop installation |
| --- | --- | --- |
| GR III | — | Pending |
| GR III Street Edition | — | Pending |
| GR III Diary Edition | — | Pending |
| GR III HDF | — | Pending |
| GR IIIx | — | Pending |
| GR IIIx Urban Edition | 1.60 | Preview two-stage workflow |
| GR IIIx HDF | — | Pending |
| GR IV | 1.11 | Preview family workflow |
| GR IV HDF | 1.11 | Preview family workflow |
| GR IV Monochrome | Not recorded | Model/target known; installation disabled until version evidence is supplied |

The full desktop workflow has not been camera-qualified. Version entry comes from the user's camera menu; it is not an automatic firmware read or a physical-body identity check. Same-model camera swaps cannot be detected from the session marker. Keep one session with one physical body and do not update firmware during it. Earlier sessions require their firmware to be recorded before installation or restoration can proceed.

Evidence: [GR IV product/target identification](../gr4-model-identification.md), [GR IV workflow](../gr4-family-shutdown-workflow.md), [Urban 1.60 experiment](../gr3x-urban-160-shutdown-image.md). The application catalog is [compatibility.py](../../apps/gr_shutdown_studio/compatibility.py); pending entries have no guessed target, factory entry or installer.

## Original preservation

The app saves `original.jpg` and `recovery/original.jpg` on the computer and checks their complete bytes. An existing different original or recovery copy is never replaced. Both must validate before preparation, installation or restoration. These two files are in the same session folder; copy that whole folder to another drive to protect against drive failure or deletion of the folder. They do not restore a factory picture that was lost before the session.

For Urban restoration, the first camera pass only exports the internal original backup and current target. The app compares the entire internal backup with the saved computer original before preparing the separate restore script. Failed and partial exports are archived. Final restoration still needs a complete readback and visible-screen confirmation.

`Save test report` exports the declared firmware, model label, sizes, hashes and workflow status. It excludes pictures, embedded-image scripts, device identifiers and local paths. A report records a participant's observation; it does not automatically authorize another installer or establish support for every body.

## Adding a model or version

A contributor must supply an evidence report for the exact model and menu firmware, factory entry, product selection, resource drive/path, backup readback, copy and truncation behavior, accepted JPEG structure, one-shot installation, visible screen and restoration. Preserve a computer original before every write experiment. Start with resource reads and backup tests; enable installation in the catalog only after the relevant model-specific evidence is reviewed. Tests with synthetic JPEGs check application behavior, not camera compatibility.

Do not publish firmware, factory JPEGs, private artwork, complete manufacturing blocks or generated TTL containing artwork. Metadata-only test reports can accompany an issue. Keep resource bytes and original backups with their owners.

## Offline firmware inventory

Use existing local inputs; this tool neither downloads firmware nor produces an installable image or camera script:

```sh
python tools/audit_shutdown_compatibility.py local-update.bin \
  --decoded local-decoded.bin --output new-audit.json
```

The container's model/version/hash and candidate resource names are evidence only. A separately supplied decoded payload is not authenticated against its update container by this tool. The existing GR IV sample has header `1.11.10.7`, container SHA-256 `a2f664dfca034059eb0fd6e18ab08684c326b4a034d85c164dad7e1ec9b5655f`, and decoded SHA-256 `c4e597c7c9ca1bc181b30e35139ed90a4fd876ddcca14f12be0e00b6702233ae`. Its decoded bytes contain `GoodBye.jpg`, `GB_HDF.jpg`, `GB_Mono.jpg` and `GB_20th.jpg`; this does not identify which resource is selected on a body or establish a product corresponding to every name.

The official pages checked on 2026-10-04 list [GR III 2.10](https://www.ricoh-imaging.co.jp/english/support/digital/gr3_s.html), [GR IIIx 1.60](https://www.ricoh-imaging.co.jp/english/support/digital/gr3x_s.html) and [GR IV / HDF 1.11](https://www.ricoh-imaging.co.jp/english/support/digital/gr4_s.html). They are references for update versions, not evidence that this app can replace shutdown images on all their applicable products. The GR IV page's applicable list does not include Monochrome. Street, Diary and Urban retain their dedicated power-off graphics across updates according to the GR III / IIIx pages.

## 中文

目标是逐步覆盖 GR III、GR IIIx、GR IV 的各机型和固件版本，目前不能宣称全版本兼容。仓库已有依据对应 GR IV / HDF 1.11、GR IIIx Urban 1.60；Monochrome 的机型与目标路径有记录，但当时未记录固件版本，因此本次网友测试版不开放它的安装。其他 GR III、IIIx 型号也不套用 Urban 脚本。

App 要求填写相机菜单显示的固件版本，并按机型与版本检查安装条件。版本由用户填写，不能证明实际固件或区分同型号的两台机身。旧操作记录需要补录原版本，操作途中不要升级固件。

原图保存为电脑上的 `original.jpg` 和 `recovery/original.jpg`，逐字节核对，拒绝覆盖已有的不同备份。两份文件在同一记录文件夹内，不防硬盘损坏或整目录删除；请另将整个文件夹复制到其他存储位置。Urban 恢复增加一次机内备份读回核对，核对通过后才准备真正的恢复脚本，最后仍须完整读回和实机显示确认。

兼容表将“已有预览流程”和“待验证”分开显示。网友可导出不含图片、机身标识、本地路径的测试报告。扩大支持前需要该机型、该固件的备份、写入、显示和恢复证据；报告不会自动启用未知机型写入。不能找回测试前就已丢失的出厂原图，也不能保证断电时相机内部写入是原子的。
