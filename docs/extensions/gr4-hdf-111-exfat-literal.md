<!-- License: see LICENSE -->

# GR IV HDF 1.11: literal-write workaround on a 256GB exFAT card

[English](#english) · [中文](#中文) · [Family workflow](../gr4-family-shutdown-workflow.md)

## English

On one GR IV HDF running user-reported firmware 1.11, a custom shutdown image was installed using a 256GB exFAT card even though TTL `filecopy` with a card source produced empty files. The workaround writes image bytes as bounded numeric literals into a fresh internal temporary file, exports it for complete host verification, then installs it in a separate camera run using internal-to-internal copying. It does not repair the failing `filecopy` implementation.

This complements [issue #1](https://github.com/radium-wang/ricoh-gr4-firmware-analysis-and-feature-expansion/issues/1), which concerns a standard GR IV and a different resource. Capacity alone does not establish compatibility. The same-card FAT32 configuration tried during this HDF experiment was not recognized by the camera; restoring full-capacity exFAT restored normal recognition. That unsuccessful formatting attempt is not a general FAT32 incompatibility result.

### Sample and device observations

| Item | Recorded value |
| --- | --- |
| Date | 2026-10-25 |
| Body / menu firmware | GR IV HDF / 1.11, reported by owner |
| Product ID | `0x132E1`, header `A5 5A 5A A5 E1 32 01 00` |
| Card | Nominal 256GB SDXC, exFAT, 128KiB allocation unit, external reader on Windows |
| Active resource | `A:\Resource\Jpeg\GB_HDF.jpg`, 56,842 bytes, attribute 32 |
| Original SHA-256 | `d4b8554a7b71094bd6f63d87d5113b8cfe9f4db5cd5ec5317b48244a3b0cbf96` |

The header identifies the product, not an individual body or firmware version. Use separate originals and packages for each physical camera.

| Observation | Result |
| --- | --- |
| Startup TTL execution; internal original exported to card | Worked; full original verified |
| Card-source copy of 40-byte text and 131,072-byte binary | Both destination files were zero bytes |
| 1,024-byte literal-writing probe plus independent zero-extension probe | Complete data matched on the host |
| Fresh internal temporary image, current resource and internal backup exports | Complete files matched before installation |
| Separate internal-copy installation and final resource export | Complete files matched; owner confirmed the image |
| Original restoration after an earlier display failure | Complete readback and physical display verified |
| Final crop; startup script removed; Script disabled | Owner confirmed normal power-cycle display, with no black borders |

The initial failing candidate was an equal-length baseline JFIF 4:2:0 JPEG which decoded on the host. After a complete write, the camera retained the live-view frame during shutdown. Restoring the original worked. Sampling, metadata, Huffman coding and padding differed together, so this does **not** isolate 4:2:0 as the sole cause.

### Optional wrapper commands

The existing FAT32 commands and examples are unchanged. This opt-in mode is limited to the tested HDF target and 56,842-byte workflow. It reads explicitly supplied local files/readbacks and writes local packages; it does not locate, format or deploy to a card. Generated TTL can write camera resources and embeds the user's image: keep generated packages private.

Install Python 3.10+ and Pillow. Preserve the body's factory original on the host before proceeding. `current.jpg` below is the latest verified active image; it may differ from the separately retained factory original. `candidate.jpg` must already be a prepared, equal-length 720×480 baseline 8-bit 4:2:2 JPEG. The new transport does not re-encode artwork, and the old `prepare` command's 4:2:0 output is not the profile validated by this experiment.

Each numbered phase is a separate camera/card cycle. Do not execute the whole command list before obtaining the previous phase's readbacks.

Before deployment, inventory the card and record whether factory-entry files already exist and who owns them. Archive and hash-check an existing `script/startup.ttl`, and establish its restoration plan before replacing it. Never silently overwrite an unrelated startup script; preserve sibling files and directories.

1. Generate the small probe:

   ```sh
   python tools/gr4_shutdown.py exfat probe EX01 ./probe
   ```

   Copy only this package's `script/startup.ttl` to the card. With Script enabled, start normally, wait for card activity to finish, shut down and reconnect the card. The existing GR IV factory entry procedure also worked on this HDF body with exFAT. The generated probe reads the product header but writes only SD outputs.

2. Verify the probe and prepare the temporary image:

   ```sh
   python tools/gr4_shutdown.py exfat verify ./probe /path/to/card
   python tools/gr4_shutdown.py exfat temporary ./probe /path/to/card ./current.jpg ./candidate.jpg EX02 ./temporary
   ```

   Deploy only the temporary package's startup script and run it once. It preserves the current resource, creates a new internal backup and temporary image, and exports all three. It never overwrites the active image.

3. Verify all temporary readbacks before generating installation:

   ```sh
   python tools/gr4_shutdown.py exfat verify ./temporary /path/to/card
   python tools/gr4_shutdown.py exfat install ./temporary /path/to/card EX03 ./install
   ```

   Deploy the installation script, run it once, inspect the shutdown display and reconnect. Then verify the complete installation outputs:

   ```sh
   python tools/gr4_shutdown.py exfat verify ./install /path/to/card
   ```

Fresh four-character uppercase attempt IDs avoid reusing internal or SD outputs. Existing output/log guards prevent repeated camera writes. Host preparation also rejects reused IDs in the package chain and its local attempt ledger. Keep the source package and its readbacks; generated descendants snapshot the validated evidence. A verification result alone is not trusted instead of the actual bytes.

### Recovery and cleanup

Recovery uses the verified internal backup created in the temporary phase, which may be a previous custom image. It does not require a successful installation log or display. Supply a complete export of the current target as the active reference; it may be undecodable but must remain exactly 56,842 bytes:

```sh
python tools/gr4_shutdown.py exfat restore ./temporary /path/to/temporary-readbacks ./current-raw-readback.jpg EX04 ./restore
```

Deploy and execute the recovery script separately, then run `exfat verify ./restore /path/to/card` and check the physical display. Zero-length, truncated or oversized targets are outside this recovery flow. Do not keep deleting failed outputs and retrying; preserve the evidence and investigate. Detected size/attribute failures may take the installation rollback branch, but same-size corruption, display failure and interrupted writes are not guaranteed recoverable automatically.

After full final readback and visible display confirmation, archive and verify task-owned files before removing the startup script. Keep factory-entry files until Script has been set back to Disable. Confirm an ordinary power cycle still shows the image, then remove only task-owned entry files and card outputs; preserve pre-existing entry files according to the recorded restoration plan. If the entry files were removed, repeat the normal power cycle before recording that final condition as verified. Keep the computer and internal recovery backups; preserve photos, unrelated scripts and camera directories.

### JPEG findings and qualification limits

The successful original-profile encoding used 720×480, baseline 8-bit 4:2:2, 72dpi, original Huffman/frame/scan layout and Exif APP1; no COM or bytes after EOI. Retaining the full 43,394-byte APP1 left only 12,857 bytes for the main compressed image and visibly poor quality.

For the **exact original hash above**, the TIFF-relative interval `[5272,41352)` in the MakerNote was 36,080 zero bytes after the referenced private preview. Removing only that interval, reducing the MakerNote length and adjusting subsequent TIFF offsets preserved the referenced metadata and both embedded previews. APP1 then occupied 7,314 bytes and main image entropy 48,937 bytes, while the total remained 56,842. This compacted layout displayed successfully on the body. These offsets are not a generic Exif recipe: other originals need independent analysis. No extracted metadata or pictures are distributed here.

For a borderless result, resize with aspect-preserving cover/crop to 3:2. The tested 1195×896 source needed about 50 source pixels removed at the top and bottom, not at the sides. The full-width result was 12.5% larger on screen than the prior 640×480 image with side bars. Crop direction depends on the source ratio.

The fixed predecessor scripts, original restoration, image display and Script-disabled persistence have device evidence. The new parameterized wrapper, stricter package checks and synthetic control-flow tests are **host-tested**, not a newly completed physical qualification of every generated package. Its JPEG gate establishes dimensions, sampling, baseline and host decoding, not universal camera acceptance. No other capacity, filesystem, body or firmware is covered by this experiment. The precise card-source `filecopy` failure cause remains unconfirmed; do not substitute an EOF-driven `fileconcat` loop (see issue #1).

## 中文

本次在一台 GR IV HDF、用户报告的 1.11 固件和一张 256GB exFAT 卡上，成功完成关机图更换、清晰度提升、满屏裁切和关闭 Script 后的持久化验证。普通卡源 `filecopy` 对 40 字节文本与 131,072 字节二进制均产生空文件，但启动脚本、数字字面量写入、机内到卡的导出和 A: 内部复制可用。

新增入口为 `python tools/gr4_shutdown.py exfat --help`。保持原 FAT32 流程不变，按上面的 `probe → verify → temporary → verify → install → verify` 命令逐阶段进行；每阶段之间必须完成一次相机运行、关机、接回电脑的循环。相机 TTL 中的 `C:` 是 SD 卡，不是电脑 C 盘。

- 临时阶段只备份当前图并写新的机内临时文件，活动关机图不被覆盖。新图、当前图、备份与日志全部通过后才准备安装。
- 字面量每条最多 42 个非零字节，每行小于 256 字符；零字节来自新文件的零扩展，无解释器倒跳循环。仅安装/恢复阶段允许活动资源被 A: 内部文件复制覆盖。
- 原图备份与“上一版自定义图备份”分别保存。`restore` 使用临时阶段已验证的机内备份，支持同长度但不可解码的活动图；不修复空、截短或超长目标。
- 部署前归档并核验已有启动脚本，记录入口文件归属，不静默覆盖其他任务的文件。最终文件匹配和用户实际显示都通过后，归档测试文件、移除本次启动脚本、关闭 Script，并确认普通开关机后仍显示新图，再仅移出本任务创建的入口文件；移出后再核验普通开关机。保护 DCIM、其他脚本和用户照片。
- 成功 JPEG 是 baseline、8 位、4:2:2、56,842 字节；失败的 4:2:0 候选还同时改变了其他编码细节，不能认定采样是唯一根因。原 `prepare` 的 4:2:0 输出并非本次验证的图像配置。
- 36,080 字节 Exif 零区压缩只适用于上面哈希的原图，所有有效引用和偏移必须保留/修正。清晰版和满屏版均有实机证据；新版可配置 wrapper 仅完成电脑测试。

这是一项单机、单卡验证的替代传输方法，不是 exFAT `filecopy` 修复，也不证明所有 256GB 卡、其他机型或固件兼容。生成的脚本包含用户图像字节，不要上传。公开内容只包含代码、合成测试和整理后的证据；照片、机身读回、原图与固件均由操作者自行保留。
