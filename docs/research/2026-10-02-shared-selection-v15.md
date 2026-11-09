# 2026-10-02：菜单选择、共用裁切计划与退出恢复（v15）

## 本轮状态

沿离线代码推进，补上菜单选择和共用裁切计划的连接。新增 `xpan_selection.c/h`、设置菜单的可选计划 binding 和 `gr4_xpan_settings_deactivate`。同一份计划可供已有预览、JPEG、DNG adapter 使用；第五项仍投影为原厂菜单索引0，原四项顺序和三种焦距裁切保留。

本轮没有连接相机、改相机 RAM、写 SD 或刷固件。XPAN 尚未上机。菜单安装/消息通知/实际显示与编码、图标、原生暂停/排空、缓存和完整卸载尚未完成，不能把模型包当升级包使用。

## 选择提交的实现

`gr4_xpan_selection_prepare` 在本地生成下一份 state/plan。XPAN 要求 source geometry 的 crop_choice 与 state 一致、源/RAW范围和对齐有效；失败不修改调用者输出。普通比例生成完整清零的 disabled plan，不保留上一幅 XPAN 裁切。

`gr4_xpan_selection_commit` 再核对状态/计划启用、native menu index、倍率和计划有效性；随后先复制共用计划，再复制 state。在原厂 setter 回调执行前两者均已完成。**结构复制不是硬件原子发布**：调用者必须已经停止并排空全部计划读者，保持锁直到原厂通知和后续绑定处理完成。

`gr4_xpan_settings_bind_selection` 绑定 state、稳定 shared_plan 地址和当前 geometry；已有列表/按钮/事件三个确认入口都进入同一个 `gr4_xpan_settings_select`，因此共享这一提交逻辑。未绑定时保留以前的 state-only adapter 路径；它不能据此宣称输出已连通。

geometry 仍须由原生 owner 从当前 source/RAW/mode 获取，不能拿上次照片的尺寸填入生产运行时。切换焦距、分辨率、拍摄任务时还须重新取得合法 snapshot；本轮没有自动实现这些原生通知。

## 退出恢复顺序

1. native owner 停止新调用，并排空旧预览/编码使用者。
2. 在旧计划和 undo 仍有效时完成局部 preview/image 参数撤销；未知对象状态拒绝覆盖。
3. 调用 `gr4_xpan_settings_deactivate`，通过同一 setter 恢复进入 XPAN 前的 last_regular_aspect；清除共用计划后才调用原厂属性观察者。普通恢复不需要重新计算 XPAN，因此失效 geometry 不阻止退出。
4. 撤回第五项展示，恢复原指令/虚表并发布，清除各 binding，确认没有回调在执行后才释放 code/对象。

本轮实现第3步和其与已有局部 undo 的模型连接。其余步骤的全模块原生同步/通知/装载恢复仍待完成，不能把此函数当作完整卸载器。

## 同一 ARM 模块中的验证

`check_gr4_shared_selection.py` 将设置菜单、selection、preview recipe/native、JPEG/native、DNG/native 以及核心一起链接为 hard-float ARM。

`shared-selection-arm-v3/checks.json`：53项检查通过。实际执行原厂 JPEG calculator、recipe helper 和新菜单/计划/adapter ARM；原厂 UI setter 和 DNG leaf 仍为服务模型。source与RAW对象、锁/排空、alignment和帧来源均为合成 fixture，无像素编码。

- OFF、35、50对应照片裁切尺寸分别为6192×2288、4944×1824、3504×1292，alignment=1/4/2仅为模型输入。
- 每次先由菜单第五项更新状态/计划，再调用预览、JPEG和DNG；三个binding的plan指针为同一个地址，原厂setter观察者检查已更新的两者。
- 四个普通菜单索引均清除计划并委托原厂尺寸，保留焦距crop。
- 退出恢复覆盖所有历史普通画幅×三个crop；geometry失效仍可清除覆盖并恢复native索引。
- 错误crop geometry、alignment、源尺寸、state binding及索引，不改state/plan，不触发原厂setter。

`settings-routes-native-v2/checks.json`：56项旧刷新、导航、确认路线检查通过；`settings-native-backend-v2/checks.json`：33项标签/ASCII allocation及委托ABI检查通过。

`portable-module-selection-v15/checks.json`：portable unity module的全部函数以ARM链接，未解析符号为0。为实际ARM编译器生成的结构复制/清零加入 `xpan_memory.c` 两个EABI helper，使用volatile byte stores避免自身重新降成运行库调用。最初soft-float后端链接暴露缺少memcpy/memclr，已修复，失败记录保留。

## 证据和下一步

本轮源/依赖/失败/检查归档到 `ui-source-snapshot-v15` 和 `ui-development-evidence-v15.json`，先逐项核对v14旧94项hash不变。v1=35项，v2=41项，v3=53项，均保留。

下一步继续实现实际UI改道和几何来源/任务通知，使共用计划更新发生在正确owner上；同时补齐图标和完整装载/卸载。最后用必要的少量实机批次验证真实取景与保存，当前不要求用户取卡。
