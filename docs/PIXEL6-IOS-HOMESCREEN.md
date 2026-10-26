# Pixel 6 真机 iOS 主屏里程碑与复现记录

更新：2026-10-25 PDT。本文只针对本仓库的 Pixel 6（`oriole`）实验；参考项目对 Pixel 6a（`bluejay`）的触摸等结果不能直接算作本机结果。较早失败的逐次记录保留在 [UFS-TIMEOUT-DIAG.md](UFS-TIMEOUT-DIAG.md)。

## 已证实的范围

| 判定 | 结果与证据 |
|---|---|
| **真机观察** | 临时 `fastboot boot` 进入 XNU，挂载 `userdata` 中的 iOS HFSX 根卷，运行 launchd、SpringBoard 和 backboardd；USB 内核日志与物理面板采样相互印证。 |
| **真机观察** | `serial=0` 的前一轮试验显示锁屏、时钟、墙纸和底部指示条。最终试验先显示锁屏；软件注入 Home/Menu 按下与释放后，两次相隔约两分钟的面板采样显示 iOS 图标网格、分页点和 Dock。由此确认该临时启动**到达主屏**。 |
| **读源码** | `sweethidtest=1300` 触发定时的 Consumer-page Menu/Home 事件，并在约 100 ms 后释放；这不是 Pixel 6 实体触摸输入。`sweetrestart=1800` 设置正常测试的自动重启时限。 |
| **未验证** | Pixel 6 实体触摸、点击应用、锁屏密码/解锁交互、Wi-Fi、GPU 加速、音频、相机、蜂窝通信、持续运行稳定性和长期数据持久性。面板采样只能分类界面，不能证明完整交互。 |

启动链：`fastboot boot` → GS101 shim → 修补后的 XNU 8796.141.3 → 只读物理 UFS 上的 `userdata` HFSX 根卷 + 512 MiB 易失 RAM 写时复制层 → launchd → SpringBoard 锁屏 → 软件 Home/Menu 事件 → 主屏。iOS 用户态来自 iPhone X 的 iOS 16.7.16（20H392）；启动的是移植版开源 XNU，不是原厂 iPhone kernelcache。

## 可核对的真机证据

最终试验使用的 AVB 临时启动镜像 SHA-256 为 `6ffe8c3a53f928d00d556bf223ec745c33509932771dbf0a82493403ce109adf`；内含 payload SHA-256 为 `97cef6179801eef92599b3017d8ccbb4a852840b86610f48d9ef1b7c1373b63e`；固定本地 relink 的内核 SHA-256 为 `822584e5de35ff7172102ef43352c0f6ddfc6ffcff254836645740c7d0e49b2a`。构建配置由提交 `994cf09` 加入，自动恢复记录见 `b2580d9`。

**真机观察：**原始 USB 捕获保存在忽略的 `private/fbsnap-work/trial-3/udp.log`，SHA-256 `9b0cd5f32325b6df31b2bfcce81678db3b3c58715edbdd496ff3ba0b4e3032ae`。第 3 个完整面板采样于 Unix 时间 `1792978415.819` 开始，显示锁屏。内核在 `1792978512.988` 记录 `SWEET HID: key 0x40 down (1 clients)`，在 `1792978513.089` 记录释放。第 4 个采样于 `1792978537.256` 开始，显示主屏；第 5 个于 `1792978658.754` 开始，仍显示主屏。捕获中未见 XNU panic 或 RAM COW 错误。到达配置的时限后，设备回到 Android Recovery，ADB 再次识别为 `oriole`。

采样来自**物理面板**的 60×134 RGB332 滚动读取，由 `tools/decode-fb-snap.py` 解码；每张图跨约 1.34 秒，不是完整分辨率的瞬时截图。第 4、5 张解码图的 SHA-256 分别为 `efbfd38591e4212687decbfcf4249afdcfb076dc985061a207d0755a1832af84` 和 `1473f22f52ca426da56c937d93aaa4faf243253536394f173828a29bab308100`。原始日志和图片可能包含设备上的私人内容，故不提交；哈希和时间点用于在本机核对。此前照片只显示苹果进度条，不能算主屏证据；这里的结论仅来自后续完成的试验。

## 本地构建与再现边界

本项目已移除 GitHub 构建 CI。构建与校验在本机执行；需要 Python 及 `lz4.frame`、AArch64 裸机交叉编译器、仓库门禁所需工具，以及 `private/` 中已固定哈希的 Apple ADT 和 XNU 对象输入。专有输入不会随仓库发布；本地脚本会在缺失或哈希不符时拒绝继续。`tools/relink-oriole-fbsnap-xnu.py` 是基于固定对象的**离线 relink**，不等于从全套 XNU 源码重新编译整个内核。

在仓库根目录，先运行 `research/pixelios-kernel/tools/check-all.sh` 并确认 `GATE PASS`；它会覆盖 `research/pixelios-kernel/shim/out/`，因此随后再运行：

```sh
tools/build-oriole-fbsnap-local.sh --home-test
shasum -a 256 research/pixelios-kernel/shim/out/shim-boot-avb.img
```

固定测试参数包含 `serial=0 cpus=1 sweetrestart=1800 sweetusb=2 sweetremote=0 ufsrw=0 rootrw=1 ufscow=1 sweetfbsnap=1 sweethidtest=1300`。其中 `ufsrw=0` 禁止 XNU 的物理 UFS 写入；`rootrw=1` 的根卷写入由 `ufscow=1` 路由到 512 MiB 易失内存层。正常情况下只会在 1800 秒时限前产生一对测试按键事件；源码的测试定时器会周期性重复，若自动重启失效，约 2600 秒可能再次发出按键。`serial=0` 使帧缓冲串口文本不覆盖 GUI，USB 日志仍能捕获。无 `sweethidtest` 的 `--silent` 只用于观察锁屏。

**操作约束：**构建脚本只生成镜像，不会访问手机。真机启动前必须逐项核对仅有一台目标设备、`fastboot getvar product` 为 `oriole`、bootloader 已解锁、固件/槽位与当前实验基线一致，以及输出镜像的哈希和类型。随后仅用 `fastboot boot` 临时启动；本轮复现不需要再刷 `userdata`，更不应刷 boot、vbmeta、dtbo、bootloader、radio、persist、efs 或分区表。任何后续重新刷入 `userdata` 都要另行核对镜像并在操作前确认。不要因为启动慢、闪屏或进度条长时间停留，就推断已进入主屏；以面板图像和日志共同判定。

当前 `userdata` 是 iOS 根镜像，Android Recovery 的 “Could not load Android system” 提示是可预期现象。若继续 iOS 实验，不要选择 Recovery 的 Factory data reset。若要恢复 Android，应另拟适配当前 bootloader/anti-rollback 状态的官方恢复方案；本里程碑没有验证该恢复过程。下一阶段先在本机验证实体触摸和单个应用启动，再处理服务、性能与持久化；每项都需要独立真机证据。
