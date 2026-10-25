**Pixel 6 / oriole iOS 移植研究**

已通过真机 USB 日志验证内存、显示寄存器、只读 UFS/GPT，以及 XNU 加载器的段复制和启动参数构造。真机屏幕照片和 USB 日志已确认 XNU 启动 RAM 用户进程 PID1，完成睡眠系统调用并正常返回 Android；完整 iOS 主屏尚未验证。iOS 16.7.16 根文件系统已离线构建并检查，实验未刷写分区。

Android 期间完成 OTA，当前为 CP3A.261005.002.A1、Bootloader slider-17.0-15681480、槽 b；该固件的基础/显示 inventory、新载荷复制检查及原生 RAM+USB 启动实验均已完成并返回 Android。Mac 解锁后日志通道已打通，当前固件的只读 UFS/GPT 复测也已通过。专用根启动路径已在真机进入 XNU，但首个 UFS `TEST UNIT READY` 命令超时并触发找不到根设备的 panic；手机已强制重启并确认回到相同 Android 固件与槽位。完整 iOS 尚未启动。旧固件结果不能自动继承。

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
