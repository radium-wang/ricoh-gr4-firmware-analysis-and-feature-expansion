# GR Shutdown Studio — user guide

## English

### Start here: what can my camera do?

This is a community test app. The complete app workflow still needs camera testing. **Being listed in Compatibility testing does not mean a camera can install an image.**

| Your camera and menu firmware | Use this route |
| --- | --- |
| GR IV or GR IV HDF, 1.11 | Main window: back up, then try image replacement |
| GR IIIx **Urban Edition**, 1.60 | Main window: back up, then try the Urban replacement workflow |
| GR IV / HDF on another version, or GR IV Monochrome | Backup experiment only, or Compatibility testing |
| GR III, Street, Diary, HDF; standard GR IIIx, IIIx HDF; Urban on another version | Compatibility testing only; no camera script yet |

Check the actual camera edition and its menu firmware. On GR III / IIIx, look under **MENU → Setup → About This Device → Firmware Info / Options**. On other bodies, use their firmware information screen. Do not change firmware just to match this table.

### A. My camera is not covered — what do I do?

You can help without modifying the camera, downloading firmware or extracting its original picture.

1. Open the app and click **Compatibility testing** in the sidebar.
2. Choose your exact edition and the version shown in its menu. Use **Other version…** if needed. Never select Urban for a standard IIIx.
3. Click **Create record…** and choose a folder on your computer, such as Documents. The app creates a new `GR-Research-…` folder there.
4. Leave **Factory menu** as **Not checked** if you have never opened it. Record whether a shutdown picture is visible during an ordinary power-off. You do not need to enter the factory menu for this report.
5. **Inspect update file…** and **Preserve extracted original…** are optional. Skip both if you do not already have those files. The app does not extract a picture from an unsupported camera. Do not import an ordinary photo or another camera's original.
6. Click **Save report…**. Send the resulting JSON file to the person who gave you the app, or attach it to a compatibility issue in the repository. You may include a cropped photo of the firmware menu with serial numbers removed.

**That is the end of this first test.** Do not select another model to get an installer. Do not copy the app's GR IV or Urban scripts to your unsupported camera. The maintainer uses your report to prepare and review a dedicated read-only method; only follow a later test package explicitly naming your edition and firmware.

Example: a **standard GR IIIx running 1.60** should choose **GR IIIx** in Compatibility testing, create a record, skip unavailable files and send the JSON. It should not choose **GR IIIx Urban** in the main window.

If your exact camera is absent from the list, send its full model name, menu firmware and normal shutdown observation directly to the distributor or a repository issue. Do not choose the closest model. This app currently targets the listed GR III / IIIx / IV editions.

### B. My combination has a replacement preview

Have a charged camera battery, a card reader, a FAT32 SD card and your own image ready. Save any card photos elsewhere first. The app does not format cards; do not format a card containing your only copies of photos. Keep one session and one working card with the same physical camera throughout.

**The repeating sequence is: computer prepares the card → safely eject → run once on the camera → wait for activity to stop → power off → reconnect the card → computer verifies.** Do not skip the computer verification between camera runs. An SD card “root” means the drive itself, not its `DCIM` folder.

#### 1. Back up the original

1. In the main window, choose **GR IV series** or **GR IIIx Urban**, then your actual menu firmware.
2. Click **Choose backup folder…** and select a folder on your computer. The app creates a new `GR-Shutdown-…` session. Keep it; it holds your original and progress.
3. Click the SD card selection button and select the card's drive. Confirm the record and card belong to the same camera, then click **Prepare card check**. The app prepares the files; you do not need to copy or edit scripts yourself.
4. Safely eject the card and insert it into the powered-off camera. Hold **MENU** while powering on. In the factory menu, set only **FW Setting1 → Script → Enable**, then power off. Leave the other settings alone. If that menu or item is missing, stop and report it.
5. Power on normally once. Wait until the camera is ready and card activity has stopped; power off, remove the card and reconnect it to the computer.
6. Click **Check result & prepare backup**. After success, safely eject, put the card back into the same camera, power on normally once, wait for activity to stop, power off and reconnect.
7. Click **Save & verify original**, then **View original backup**. The app saves and verifies `original.jpg` and `recovery/original.jpg` in the session folder. Copy the entire folder to another storage device before installation.

If the camera had already been modified, this backs up its current picture; it cannot recover a factory picture that was lost earlier.

#### 2. Choose and install your image

1. Click **Choose photo…**, select your image, choose **Fill frame** or **Fit with borders**, and adjust the framing if needed.
2. Click **Prepare my image** and inspect the encoded preview. If encoding fails, try simpler artwork; do not alter the original or bypass the size check.
3. Confirm the same card and camera, then click **Prepare installation**.
4. Follow the numbered camera steps: safely eject, run once on the same camera, wait, power off and reconnect.
5. GR IV: click **Verify camera readback**. Urban needs an extra temporary-image pass: click **Verify temporary image & prepare installation**, perform another camera run, then click **Verify camera readback**. Follow the app's current step rather than skipping ahead.
6. After the complete readback matches, put the card back in the camera. Hold **MENU** while powering on and set **FW Setting1 → Script → Disable**. Check the actual shutdown picture during normal use.
7. Reconnect the card. Check **The screen looks correct. Script is now disabled.**, then click the final action. Keep the session folder and its extra copy.

#### 3. Restore the saved original later

1. Click **Open saved session** and select `session.json` in this camera's `GR-Shutdown-…` folder. Use the same physical camera, firmware and working card.
2. Select the card and click **Restore original image**. If Script is disabled, use MENU-power-on to set only **FW Setting1 → Script → Enable**, then power off before the normal run.
3. Follow the current numbered steps and reconnect for verification. Urban first exports and checks the internal original; only after that check does the app prepare the actual restoration pass.
4. After restoration readback matches, set **Script → Disable** and check the restored shutdown picture. Reconnect, confirm the screen and finish.

Restoration needs intact backups and the matching camera. Never restore another user's original or use another camera's session.

### C. GR IV backup-only test

Only volunteers testing the existing GR IV read path should use this route. Follow section B's **Back up the original** steps with the real menu version; Monochrome users may need **Other version…**. Versions 1.04 and 1.03 are labelled **backup test**.

At **Backup test complete**, stop. Use **Save test report…**; there is no image installation for this combination. Before ordinary use, safely eject the card, use MENU-power-on to set **Script → Disable**, power off and confirm normal operation. Do not select 1.11 to bypass this limit. Unknown-model or missing-output errors end the test too.

### If something goes wrong

Stop on any error, missing output, backup mismatch, unexpected shutdown or **Card preparation interrupted** message. Do not repeatedly power-cycle a pending script, delete result files to force a retry, or format the card. If the app says not to run the script, do not put that card back into the camera. Keep the session and card files; send the error text and your camera/firmware/app versions to the distributor. Share only the metadata report, not the whole folder, pictures or artwork scripts.

macOS users open the `.app`; Windows users extract the whole ZIP and open the `.exe`, keeping `_internal` beside it. No Python installation is needed. These preview packages are not notarized/signed for general distribution; if the OS blocks opening, send the exact message to the distributor rather than changing security settings blindly.

## 中文操作说明

### 先看：我的相机能做到哪一步？

这是网友测试预览版，完整 App 流程仍待实机验证。**“适配测试”里能选到某台相机，不等于已经支持更换图片。**

| 相机及菜单固件 | 应该怎么操作 |
| --- | --- |
| GR IV 普通版 / GR IV HDF，1.11 | 主页面：先备份，再试更换 |
| GR IIIx **Urban Edition**，1.60 | 主页面：先备份，再试 Urban 更换流程 |
| GR IV / HDF 其他版本，或 GR IV Monochrome | 只做备份实验，或进入“适配测试”提交资料 |
| GR III 普通版、Street、Diary、HDF；GR IIIx 普通版、HDF；Urban 其他版本 | 只做“适配测试”，目前没有对应相机脚本 |

先看清相机的具体版本，不只看“GR3 / GR4”。GR III / IIIx 可在 **MENU → 设置 → 关于本设备 → 固件信息 / 选项** 查看；其他机型在自己的固件信息页查看。不要为了凑列表里的版本先升级或降级固件。

### 一、我的机型没有覆盖，怎么办？

**不用改相机，不用下载固件，也不用自己提取原图。** 先按这 6 步提供基本资料即可。

1. 打开软件，点击左侧 **“适配测试”**。
2. 选择准确机型和相机菜单里的固件版本。列表没有就选 **“其他版本…”**。普通 IIIx 不要选 Urban。
3. 点击 **“建立记录…”**，选择电脑里的一个文件夹，例如“文稿”。软件会在里面新建一个 `GR-Research-…` 文件夹。
4. 没进过工厂菜单，就把 **“工厂菜单”留在“未检查”**。按正常方式关机，看看有没有显示图片，在“关机图片”里记录。不要求你为了这份报告进入工厂菜单。
5. **“分析更新文件…”和“保存已读出的原图…”都是可选项。没有这些文件就跳过。** 软件目前不能从未支持的机型里自动提取原图。不要拿普通照片或别人的原图来填。
6. 点击 **“保存报告…”**，把生成的 JSON 文件发给提供软件的人，或附到仓库的兼容性 issue。可以再附一张固件菜单照片，裁掉序列号等个人信息。

**第一轮测试到这里就结束。** 不要改选其他型号来找安装按钮，也不要把 GR IV / Urban 的脚本放进这台未支持的相机。维护者拿到报告后会研究并审核专用只读方法；后续只使用明确写着你的“机型＋固件版本”的测试包。

举例：用户有一台 **GR IIIx 普通版，固件 1.60**。在“适配测试”里选 **GR IIIx**，建立记录，没有固件文件和原图就跳过，最后发送 JSON。**不能因为同样是 1.60，就在主页面选 GR IIIx Urban。**

如果连准确机型都不在列表里，直接把完整型号、菜单固件版本和正常关机时的观察结果发给提供软件的人，或写到仓库 issue。不要选最接近的型号。目前 App 面向列表中的 GR III / IIIx / IV 各版本。

### 二、我的组合已有更换预览，怎么换？

准备充足电量的相机、读卡器、FAT32 SD 卡和自己的图片。先把卡上的照片另存到电脑；软件不会格式化卡，不要格式化唯一保存照片的卡。整个过程保持同一台机身、同一固件、同一张工作卡。

反复操作的顺序只有这一条：**电脑准备卡 → 安全弹出 → 相机正常开机执行一次 → 等读写结束再关机 → 卡接回电脑 → 点击校验。** 每轮都要回电脑核对，不要连续跳过校验。选择“SD 卡根目录”就是选择卡本身，不是里面的 `DCIM` 文件夹。

#### 1. 先备份原图

1. 在主页面选 **“GR IV 系列”** 或 **“GR IIIx Urban”**，选择自己的实际菜单固件版本。
2. 点击 **“选择备份文件夹…”**，选电脑里的文件夹。软件会新建 `GR-Shutdown-…` 操作记录，保存原图和进度。以后不要删。
3. 选择读卡器里的 SD 卡，勾选“此记录和 SD 卡用于同一台相机”，点击 **“准备 SD 卡检查”**。软件负责准备文件，不需要自己复制或编辑脚本。
4. 在电脑上安全弹出卡，插入已关机的相机。**按住 MENU 再开机**，进入工厂菜单，仅把 **FW Setting1 → Script 改为 Enable**，然后关机。其他项目不动；菜单或该选项没有出现就停下来反馈。
5. 再正常开机一次。等进入正常界面且卡读写结束，再关机取卡，接回电脑。
6. 点击 **“校验结果并准备备份”**。通过后，再安全弹出卡、插回同一台相机、正常开机一次、等读写结束关机，卡接回电脑。
7. 点击 **“保存并核对原图”**，再点左侧 **“查看原图备份”** 确认内容。软件在记录目录保存 `original.jpg` 和 `recovery/original.jpg` 两份完整副本。**安装前，把整个记录文件夹再复制到另一存储位置。**

如果相机以前已经被改过，此处备份的是当前图片，不能找回之前没保存的出厂原图。

#### 2. 选图并安装

1. 点击 **“选择图片…”**，选择自己的图片。用 **“填满画面”** 或 **“完整显示，保留边框”** 调整构图。
2. 点击 **“处理我的图片”**，确认处理后的预览。处理失败可换一张更简单的图；不要修改原图或绕过长度检查。
3. 确认还是同一张卡、同一台相机，点击 **“准备安装”**。
4. 按界面的编号操作：安全弹出卡，插回相机，正常开机执行一次，等读写结束关机，卡接回电脑。
5. GR IV 点 **“校验相机读回”**。Urban 会多一轮：先点 **“校验临时图并准备安装”**，再跑一次相机流程，最后点 **“校验相机读回”**。按当前页面做，不跳步。
6. 完整读回通过后，把卡插回相机，**按住 MENU 开机，把 FW Setting1 → Script 改回 Disable**。正常开关机，确认屏幕真的显示了自己的图片。
7. 卡接回电脑，勾选 **“关机画面显示正确，Script 已设回 Disable”**，点击最后的完成按钮。保留备份目录及其另存副本。

#### 3. 以后怎么恢复原图？

1. 点击左侧 **“打开已有记录”**，选择这台相机 `GR-Shutdown-…` 文件夹里的 `session.json`。使用原来那台机身、同一固件和工作卡。
2. 选择卡，点击 **“恢复原始画面”**。若 Script 已关闭，先按住 MENU 开机，仅将 **FW Setting1 → Script 设为 Enable**，关机后再正常开机执行。
3. 按当前编号完成相机操作，再接回电脑校验。Urban 会先读回并核对机内原图，通过后才准备真正的恢复步骤，需多跑一轮。
4. 恢复读回通过后，把 **Script 设回 Disable**，正常关机确认原图显示，再接回电脑勾选确认并完成。

恢复需要完整备份和对应机身。不要用别人的原图，也不要把另一台相机的操作记录拿来恢复。

### 三、GR IV 的“备份测试”怎么做？

愿意协助验证已有 GR IV 读取路径的用户，按上面 **“先备份原图”** 完成即可，固件必须选真实版本。Monochrome 的版本可用“其他版本…”填写；1.04、1.03 在菜单中标为“备份测试”。

出现 **“备份测试完成”** 就停下来，点 **“保存测试报告…”**。这个组合暂时没有安装步骤。恢复普通使用前，安全弹出卡、插回相机，按住 MENU 开机，把 **Script 设回 Disable**，关机后确认正常使用。不要改选 1.11 绕过限制；出现机型未知、输出缺失等错误也要结束测试。

### 四、报错了怎么办？

报错、输出缺失、备份不一致、相机异常关机，或出现 **“SD 卡准备中断”**，就先停下来。不要反复开机运行待执行脚本，不要删校验文件强行重试，也不要格式化卡。软件提示不要运行脚本时，暂时不要把这张卡插回相机。

保留记录目录和卡上文件，把错误文字、机型、固件版本、App 版本发给提供软件的人。只分享元数据报告，不发整个备份目录、原图或包含图片的脚本。

macOS 打开 `.app`；Windows 先完整解压 ZIP，再打开里面的 `.exe`，旁边的 `_internal` 文件夹必须保留。不用安装 Python。这些预览包尚未做正式分发签名／公证；系统拦截时把具体提示发给提供软件的人，不要盲目关闭安全设置。
