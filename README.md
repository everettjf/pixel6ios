**Pixel 6 / oriole iOS 移植研究**

当前阶段：Pixel 6 真机移植。已在已解锁的 oriole 上两次临时启动只读探测镜像，通过 USB 采到内存布局，手机自动回到 Android。iOS 16.7.16 实验根文件系统已在隔离 Linux 虚拟机中构建并通过离线检查。尚未在本机启动 XNU 或 iOS；尚未刷写分区。

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
