<!-- License: see LICENSE (earlier Apache-2.0 grants remain in force) -->

# GR IIIx HDF 1.60 shutdown-image method

## English

### Source and result

[ZIBLEEEEE's PR #9](https://github.com/radium-wang/ricoh-gr4-firmware-analysis-and-feature-expansion/pull/9), reviewed at [`79f77e3`](https://github.com/radium-wang/ricoh-gr4-firmware-analysis-and-feature-expansion/commit/79f77e3415a0d5c8322a1fe7990cb54ea5bb33b6), reports a successful replacement on one **GR IIIx HDF running menu firmware 1.60**. The contributor reports complete byte comparisons of the original, internal backup, staged candidate and installed target, followed by visible shutdown-image confirmation after disabling Script. No firmware was flashed.

This note collects the reported mechanism for further model-specific work. The maintainer has not repeated the camera experiment. Original bytes, hashes, artwork and device readbacks were not supplied with the PR; the device result is attributed to the contributor. The result does not establish another body's or firmware version's compatibility.

### Recorded setup

| Item | Reported value |
| --- | --- |
| Camera / firmware | GR IIIx HDF / 1.60 |
| Factory entry | `00078490.609` and `DEVELOP.MOD` |
| Active shutdown resource | `B:\Resource\Jpeg\GoodBye.jpg` |
| Original JPEG | 720×480, baseline JPEG, 7,264 bytes |
| Internal original backup | `B:\Resource\Jpeg\HD41OL.JPG` |
| Internal temporary image | `B:\Resource\Jpeg\HD81NW.JPG` |
| SD-card drive in TTL | `C:` |

`GB_Urban.jpg`, `GB_Diary.jpg` and `GB_ING.jpg` were also readable on the reported body. Their presence did not identify the active HDF shutdown resource. The write, full readback and changed display identified `GoodBye.jpg` on this body. The entry files match Urban 1.60; its resource path and original-image profile do not.

### Reported sequence

The experiment separated backup, temporary-image staging and target installation into different camera runs, with computer checks between them.

1. **Enter the factory menu.** Generate the reported entry files locally:

   ```sh
   python3 tools/create_factory_entry.py ./entry-hdf --model gr3x-hdf-160
   ```

   Place the two entry files in the SD-card root. Use the documented MENU-power-on entry and enable only `FW Setting1 → Script`, leaving other settings unchanged. Each camera run uses `script/startup.ttl`; safely eject before insertion and power off after storage activity stops before removing the card.

2. **Preserve the original.** The [reported backup example](../examples/gr3x-hdf-160-backup.ttl.example) copies `GoodBye.jpg` to `C:\HDFBK0.JPG`, creates `HD41OL.JPG` internally, then exports it as `C:\HDFOLD.JPG`. It refuses existing backup destinations and checks the reported length. Save both readbacks on the computer, open them and compare their complete bytes before continuing. Keep another copy of the whole working folder elsewhere. File length alone does not verify an original. An already modified resource only supplies its current image.

3. **Stage the candidate internally.** The contributor created a *new* `HD81NW.JPG`, extended it to 7,264 bytes, then used `fileseek` and short numeric `filewrite` literals to write the candidate JPEG. The temporary image, original and internal backup were exported and compared with their computer references before installation. The artwork, encoding parameters and generated payload-writing script were not published, so this record does not provide a complete HDF image generator. A plain SD-to-camera JPEG copy is not the reported staging method. Do not substitute Urban's generator: it pins a different original length and SHA-256.

4. **Copy the verified internal candidate to the target.** The reported final operations were:

   ```text
   filecopy 'B:\Resource\Jpeg\HD81NW.JPG' 'B:\Resource\Jpeg\GoodBye.jpg'
   filecopy 'B:\Resource\Jpeg\GoodBye.jpg' 'C:\HDFRD9.JPG'
   ```

   These lines explain the observed write scope; they are not a complete guarded installer. Archive previous attempts and use fresh readback destinations so an old file cannot stand in for a failed copy. Compare the entire new target readback with the exact candidate. The contributor also checked the target's size and attributes, but the report does not publish the attribute value.

5. **Confirm display and finish.** The contributor reported that the new image displayed after Script was set back to Disable and the camera was power-cycled. Remove the startup script, disable Script and check normal operation. Keep the original backups; clean only files belonging to this experiment.

### What is still missing

- The encoding/staging implementation and original SHA-256 are needed for a reproducible tool, without publishing the original JPEG or private artwork.
- The internal backup is a proposed restoration source. Restoration and automatic rollback were not exercised in this submission. They are not recorded as successful recovery methods.
- The PR's installation and recovery wrappers are not included here: review found that stale outputs could mask copy failures, rollback status could be misleading and the recovery wrapper refused a truncated target. The installation wrapper also required a pre-created empty `HDFLOG9.TXT` not described in its guide. Those issues do not invalidate the separately reported successful path.
- The first backup attempt produced no output. Removing task-created `._startup.ttl` metadata was followed by successful diagnostics and backup; the cause remains unresolved.

Other-model contributions can be recorded in the same way: exact edition and menu firmware, entry files, active resource path, original dimensions/length/hash, backup and staging commands, fresh full readbacks, visible display and a separate recovery result. Mark untested steps explicitly. A useful device finding can be collected before a complete reusable tool exists.

## 中文

### 来源与结果

[ZIBLEEEEE 的 PR #9](https://github.com/radium-wang/ricoh-gr4-firmware-analysis-and-feature-expansion/pull/9)，审核版本为 [`79f77e3`](https://github.com/radium-wang/ricoh-gr4-firmware-analysis-and-feature-expansion/commit/79f77e3415a0d5c8322a1fe7990cb54ea5bb33b6)，报告在一台**菜单固件为 1.60 的 GR IIIx HDF** 上成功更换了关机画面。贡献者报告原图、机内备份、临时图和最终目标均与电脑参考文件完整逐字节一致；关闭 Script 并重新开关机后，新图仍正常显示。过程没有刷固件。

这里收录的是实现方法，供后续按机型复现。维护者没有重复实机实验；PR 没有提供原图字节、哈希、图稿或机身读回文件，实机结果注明来自贡献者。不能据此推广到其他机身或固件。

### 已记录的信息

| 项目 | 本次报告 |
| --- | --- |
| 机型／固件 | GR IIIx HDF／1.60 |
| 工厂菜单入口 | `00078490.609` 和 `DEVELOP.MOD` |
| 实际关机资源 | `B:\Resource\Jpeg\GoodBye.jpg` |
| 原图 | 720×480、baseline JPEG、7,264 字节 |
| 机内原图备份 | `B:\Resource\Jpeg\HD41OL.JPG` |
| 机内临时新图 | `B:\Resource\Jpeg\HD81NW.JPG` |
| TTL 中的 SD 卡盘符 | `C:` |

本机还能读到 `GB_Urban.jpg`、`GB_Diary.jpg` 和 `GB_ING.jpg`。文件存在不代表它就是活动资源；本次通过写入、完整读回和实际显示改变，确认使用的是 `GoodBye.jpg`。入口文件与 Urban 1.60 相同，但资源路径和原图参数不同。

### 提取出的实现方法

整个过程分为备份、写入临时图、安装三轮，每轮之间回电脑核对。

1. **开启脚本入口。** 在电脑执行上面的 `create_factory_entry.py --model gr3x-hdf-160` 命令，把两个入口文件放到卡根目录。按已有说明用 MENU 加开机进入工厂菜单，仅开启 `FW Setting1 → Script`，其他设置不动。每轮以 `script/startup.ttl` 运行；先安全弹出卡，执行后等读写结束、关机再取卡。
2. **备份本机原图。** [贡献者的备份示例](../examples/gr3x-hdf-160-backup.ttl.example)把 `GoodBye.jpg` 导出为 `C:\HDFBK0.JPG`，创建机内 `HD41OL.JPG`，再导出为 `C:\HDFOLD.JPG`。已有同名备份时停止，并检查本次记录的长度。两份都要另存电脑、能正常打开、完整内容一致，再将整个工作目录另存一份。长度相同不能代替内容核对；已修改的相机只能备份当前图片。
3. **在机内生成临时图。** 本次新建 `HD81NW.JPG`，扩展到 7,264 字节，用 `fileseek` 和短段数字字面量 `filewrite` 写入 JPEG。把临时图、当前原图及机内备份读回电脑，分别完整核对后才继续。图稿、编码参数和生成的 payload 脚本未提交，因此还没有完整可复用的 HDF 编码／写入生成器。这里采用机内暂存写入，不是直接把 SD 卡 JPEG 复制进相机；也不能套用固定了不同长度和哈希的 Urban 生成器。
4. **把已验证的机内新图复制到目标。** 实测最后执行的操作就是上面的两条 `filecopy`：`HD81NW.JPG → GoodBye.jpg → C:\HDFRD9.JPG`。这是写入原理，不是完整的安装保护脚本。旧尝试先归档，每轮使用新的读回输出，避免旧文件冒充本次结果。最终读回必须与候选图完整一致。本次还检查了目标属性和长度，但报告没有公开具体属性值。
5. **检查画面并收尾。** 贡献者确认关闭 Script、重新开关机后显示新图。完成后移除启动脚本，关闭 Script，检查正常使用，保留原图备份，只清理本次任务文件。

### 尚待补充

- 要做成可复用工具，还需要补充编码／临时图生成方法及原图 SHA-256，无需公开原图或私人图稿。
- 机内备份只是拟定的恢复来源。本次没有测试恢复及自动回滚，不登记为“已验证恢复方法”。
- 不收录 PR 中的安装及恢复包装脚本：审核发现旧输出可能掩盖复制失败、回滚状态可能误报，恢复包装也拒绝目标已被截短的情况；安装包装还需要指南未交代的空 `HDFLOG9.TXT`。这些问题不否定另行报告的成功操作路径。
- 首次备份没有输出；清理本任务生成的 `._startup.ttl` 后诊断与备份成功，失败原因仍未确定。

其他机型也按这些信息提交即可：准确机型和菜单固件、入口文件、活动资源路径、原图尺寸／长度／哈希、备份与临时写入命令、本轮完整读回、实际显示和单独的恢复结果。没有测的步骤注明未测。可以先收录有用的实机发现，再逐步完善复现工具。
