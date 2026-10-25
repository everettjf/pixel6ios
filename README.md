**Pixel 6 / oriole iOS 移植研究**

已通过真机 USB 日志验证内存、显示寄存器、只读 UFS/GPT，以及 XNU 加载器的段复制和启动参数构造。真机屏幕照片和 USB 日志已确认 XNU 启动 RAM 用户进程 PID1，完成睡眠系统调用；完整 iOS 主屏尚未验证。

Pixel 6 当前固件为 CP3A.261005.002.A1、Bootloader slider-17.0-15681480、槽 b。经用户分别确认，两版 iOS 16.7.16 HFSX 根镜像先后刷入 `userdata`；其余分区未刷写。第一版真机启动已由 USB 日志证明 XNU 找到 `ufsroot0`，但只读 UFS 拒绝 HFS 日志写入，根目录未挂载。第二版移除 HFS 日志标志，离线校验通过并已刷入；首次临时启动期间电脑未收到 USB 日志，真机启动阶段尚待屏幕或其他日志确认。完整 iOS 尚未启动。详见[真机诊断记录](docs/UFS-TIMEOUT-DIAG.md)。

- [调研报告与分阶段开发方案](docs/PIXEL6-IOS-FEASIBILITY.md)
- [源码版本与下载文件校验记录](docs/source-manifest.json)
- [本机只读采集器](tools/inspect_pixel6.py)
- [实际开发状态与继续工作的记录](docs/ACTIVE-WORK.md)
- [相对固定上游版本的本地补丁](patches/)

推荐基线：iPhone X 的 iOS 16.7.16（20H392）用户态 + PixeliOS 的 XNU 8796.141.3 / GS101 补丁栈。

```sh
python3 tools/inspect_pixel6.py
```

采集器需要恰好一台已授权的 `oriole`，只读取选定硬件信息。输出存入忽略的 `private/`。它不会重启、解锁或刷机。移植源码和补丁现已纳入本仓库的 [research/pixelios-kernel](research/pixelios-kernel)，与原源码提交 `579ed5e` 的 486 个受版本控制文件逐字节一致；原提交历史保存在 `source-history` 分支。源码树中的 `.upstream/`、`shim/out/`、`logs/`、第三方下载，以及根目录的 `artifacts/`、`private/` 和 Platform Tools 仍被忽略。
