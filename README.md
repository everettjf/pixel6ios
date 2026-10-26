# Pixel 6 / oriole iOS 移植研究

**真机里程碑（2026-10-25 PDT）：**在已解锁的 Pixel 6 上，通过 `fastboot boot` 临时启动移植版 XNU 和 iPhone X 的 iOS 16.7.16 用户态，已观察到 iOS 锁屏。随后，一个定时注入的**软件 Home/Menu 按键事件**使画面进入 iOS 主屏；两次相隔约两分钟的物理面板采样均显示图标网格、分页点和 Dock。证据、构建哈希及观察边界见[真机里程碑与复现记录](docs/PIXEL6-IOS-HOMESCREEN.md)。这不是可日用的 iOS 安装：Pixel 6 的实体触摸、打开应用、无线网络、GPU、音频、相机和蜂窝通信仍未验证。

当前实验将 iOS 根镜像放在 `userdata`；这已经清空了原 Android 本机数据。每轮 iOS 启动仍使用临时 `fastboot boot`，不刷写启动分区。测试计时结束后手机返回 Android Recovery，提示无法加载 Android，因为 `userdata` 已不是 Android 文件系统。若要保留当前 iOS 根镜像，**不要在 Recovery 中选择 Factory data reset**。

推荐基线为 iPhone X 的 iOS 16.7.16（20H392）用户态，配合 PixeliOS 的 XNU 8796.141.3 / GS101 补丁栈。代码、补丁、测试和本地构建工具在本仓库；Apple 镜像、设备原始日志、固件和私有构建输入不会提交到 Git。

- [当前真机结果、构建方法与注意事项](docs/PIXEL6-IOS-HOMESCREEN.md)
- [逐次存储与启动诊断记录](docs/UFS-TIMEOUT-DIAG.md)
- [最初调研与方案（历史快照）](docs/PIXEL6-IOS-FEASIBILITY.md)
- [开发交接与历史工作记录](docs/ACTIVE-WORK.md)
- [源码版本与下载文件校验记录](docs/source-manifest.json)
- [Pixel 6 移植源码](research/pixelios-kernel/)

本地质量门禁为 `research/pixelios-kernel/tools/check-all.sh`；Pixel 6 的固定离线诊断构建入口为 `tools/build-oriole-fbsnap-local.sh [--silent|--home-test]`。构建依赖已校验的本机私有 XNU 对象和 Apple ADT；刚克隆的公开仓库不能凭空生成这些专有输入。构建脚本不会接触手机，须在确认设备身份和镜像哈希后才由操作者另行执行临时启动。GitHub 构建 CI 已移除，本项目以本机门禁和构建为准。

只读硬件信息采集器可用 `python3 tools/inspect_pixel6.py` 运行；它要求恰好一台已授权的 `oriole`，不会重启、解锁或刷机。输出保存到忽略的 `private/`。移植源码原始快照为提交 `579ed5e`，原提交历史保存在 `source-history` 分支。
