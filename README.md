**Pixel 6 / oriole iOS 移植研究**

已通过真机 USB 日志验证内存、显示寄存器、只读 UFS/GPT，以及 XNU 加载器的段复制和启动参数构造。尚无真机 XNU/PID1 或 iOS 主屏执行证据。iOS 16.7.16 根文件系统已离线构建并检查，实验未刷写分区。

Android 期间完成 OTA，当前为 CP3A.261005.002.A1、Bootloader slider-17.0-15681480、槽 b；该固件的基础 inventory 已重验，手机自动返回 Android；其他实验类型仍受门禁限制。旧固件结果不能自动继承。

- [调研报告与分阶段开发方案](docs/PIXEL6-IOS-FEASIBILITY.md)
- [源码版本与下载文件校验记录](docs/source-manifest.json)
- [本机只读采集器](tools/inspect_pixel6.py)
- [实际开发状态与继续工作的记录](docs/ACTIVE-WORK.md)
- [相对固定上游版本的本地补丁](patches/)

推荐基线：iPhone X 的 iOS 16.7.16（20H392）用户态 + PixeliOS 的 XNU 8796.141.3 / GS101 补丁栈。

```sh
python3 tools/inspect_pixel6.py
```

采集器需要恰好一台已授权的 `oriole`，只读取选定硬件信息。输出存入忽略的 `private/`。它不会重启、解锁或刷机。`research/` 下的上游快照、Platform Tools 和设备信息均未纳入版本控制。
