# Pixel 6 的 iOS USB 联网：当前证据与下一步

状态：**尚未验证 iOS 可访问互联网**（2026-10-28）。本页只记录已核对的源码与一次真机日志，不把 USB 日志通道等同于上网。

## 当前已成立的通路

- **读自源码：** [XNU USB ECM 补丁](../research/pixelios-kernel/xnu/patches/0073-sweet-usb-ecm.patch)创建 `ue0`，给设备侧设定 `192.168.7.2/24`；该补丁的注释指定主机侧为 `192.168.7.1`。内核接口创建代码只设置了本机地址，没有在此处添加默认路由或 DNS。
- **真机观察：** 2026-10-28 的 0121 重试 USB 记录中，`ue0` 的收包计数从 57 增至 204，发包计数从 221 增至 2993；`configd`、`mDNSResponder` 和 `networkserviceproxy` 启动。`SWEET NET` 记录只显示 `lo0` 的 `127.0.0.1` 地址及 `127.0.0.0`、`224.0.0.0` 路由，没有记录默认路由。原始日志保留在忽略的 `private/touch-xnu-source/relink-0121/gui-0121-retry-udp.log`，SHA-256 为 `7e9be109b48549d2994eb1d19be39bfaf5d2694018c2207aaec65e81061f5365`。
- **证据边界：** 日志接收证明手机与 Mac 在 USB 局域网内通信。它不证明 iOS 有到外网的路由、可用 DNS、主机转发/NAT，或任一系统 App 成功取回网络内容。日志捕获可能漏掉早期消息，不能仅凭未见到默认路由就断言它在运行时一定不存在。

## 实现与验收顺序

**读自源码的路由接入约束（2026-10-28）：** XNU-8796 的
`bsd/kern/netboot.c` 在 `default_route_add()` 中用
`rtrequest_scoped(RTM_ADD, 0.0.0.0, router, 0.0.0.0,
RTF_UP | RTF_STATIC | RTF_GATEWAY, ..., IFSCOPE_NONE)` 创建 IPv4 默认路由。
这提供了可复用的内核 API 用法，但不等于 Pixel 6 已安装路由。
当前 `bsd/dev/sweet_usb.c` 在 `ud_if_create()` 中配置 `ue0` 地址，而
`ud_link_event(true)` 只在 USB `SET_INTERFACE` 选择数据 alt-setting 1 时
调用；设备 reset/disconnect 分支仅打印事件，未调用 `ud_link_event(false)`，
`SET_INTERFACE` 返回 alt-setting 0 时也没有下线处理。因而联网补丁必须
在链路确实启用、地址配置成功后才尝试加路由，并在 alt-setting 0、
reset 和 disconnect 时撤销**自己创建**的路由、发布下线状态；
重复配置和路由已存在都不能误删别人的默认路由。先保留单独启动参数开关，
默认关闭，再用 USB 重连及拔线实测证明清理行为。

1. **设备端路由。** 在独立、默认关闭的临时启动配置中，为 `ue0` 增加经源码核对的 IPv4 默认网关 `192.168.7.1`；启动后读取实际路由表，确认默认路由确实指向该接口。若修改 XNU，须按内核补丁顺序提交，并经过异模型硬件代码复核、完整构建和临时真机启动。先验证纯 IP 目标，再处理 DNS。
2. **Mac 端出口。** 只对已核实的 Pixel 6 USB 接口配置 `192.168.7.1/24`，核对 Mac 当前可用的上行网络，再配置受限的转发/NAT。任何需要管理员权限的操作都由用户在审阅确切命令后执行；不要改动全局网络设置来掩盖设备端故障。
3. **DNS 与 iOS 策略。** 先验证设备可以到达外网 IP，再提供 DNS，并确认 `configd` 将 USB 链路视为可用服务。最终用一个系统 App 发起实际请求，同时捕获设备路由、DNS 查询、主机转发计数和 App 结果。
4. **故障收束。** 断开 USB 后不能留下错误的默认路由；临时镜像仍按现有定时器回到 Android/Recovery。网络功能的成功声明必须同时有设备侧和主机侧证据，且不能把 UDP 控制台流量当作外网流量。

Wi-Fi 驱动是另一条路线，现有 [上游研究](../research/pixelios-kernel/docs/research/20-wifi-stack-plan.md)不能证明 Pixel 6 真机 Wi-Fi 可用。USB 联网可作为更早的可测试出口，但不等于最终无线联网。

## 本地候选：0123（尚未真机验证）

- **读自源码 / 本地构建：** `0123-oriole-usb-owned-default-route.patch` 是默认关闭的 `sweetnetroute=1` 候选。只有在 `ue0` 地址设置成功、USB 数据接口切到 alt-setting 1 后，它才尝试安装经 `192.168.7.1` 的默认路由；接口下线时仅在路由对象、网卡索引和 IPv4 网关仍匹配时撤销。插入时也核对路由实际选中的网卡。该补丁仍留在本地 `wip/oriole-usb-internet-route` 分支，未推送。
- **本地检查：** 补丁可在对应的 XNU 基线上 `git apply --check`，仓库门禁在本机输出 `GATE PASS 7dc299d`。`sweet_usb.c` 和 `route.c` 候选源码都已编译成对象文件。为适配现有编译头文件，补丁把 `route.c` 中对不透明 `lo_ifp` 的直接字段访问改用 XNU 的 `ifnet_index(lo_ifp)`；该 API 源码在非空时返回同一 `if_index`。这还不等于完整内核重链接或真机启动通过。
- **未验证：** 真机路由添加、断线清理、重连、DNS 和互联网访问。现有 USB 驱动在 reset/disconnect 时没有清除 `configured`，可能跳过后续端点重配。完成完整构建、异模型审查及真机临时启动结果前，不应把该候选合入 `main` 或称为可用功能。
- **重链接约束（本地对象对比）：** 新 `sweet_usb.o` 只增加预期的路由 API 引用；新 `route.o` 的公开符号增加两个预期 API。然而现有通用编译配方生成的 `route.o` 与已验证归档的未定义符号集合不同，尤其是 `memset` 与 `__memset_chk`。在重建与已验证归档等价的路由对象、审核内核布局之前，不能把该对象直接替换进真机镜像。相关比对产物留在忽略的 `private/oriole-net-route-source/`。

## 0123 离线重链接记录（2026-10-28）

- **本地构建：** 用 `NECP=1`、`MACH_ASSERT=1` 编译候选 `route.c` 后，缺失的 NECP 与锁断言引用恢复到已验证归档的形式。以 0122 归档为基线，只替换 `route.o`、`sweet_usb.o`，重链接得到 16,713,816 字节的候选内核，SHA-256 `f68406db756901338eedec463cec3bf54c063f56c817c8fb5173398fb89a89ef`。全局符号只增加 `_rtrequest_add_gateway_on_ifindex` 和 `_rtrequest_delete_if_same`，入口地址与加载命令序列未变。
- **布局差异：** `__TEXT_EXEC` 比 0122 增加 16 KiB，后续加载段地址和文件偏移随之移动 16 KiB。离线解析确认段集合、入口、加载命令序列和 `__symbolsets` 内容相同；新旧两份 Mach-O 的段虚拟地址及文件范围各自无重叠，候选映像末端从 `0xfffffe0008728000` 移到 `0xfffffe000872c000`。因此 0122 的“除 LINKEDIT 外各段布局完全相同”审计不能直接用于 0123。
- **离线模拟：** 用与 0122 相同的 ADT 和命令行，另加 `sweetnetroute=1` 构造候选 payload；QEMU 运行 12 秒。候选与 0122 基线显示完全相同的 `SWEET EARLY 1` 至 `SWEET EARLY 20` 日志，二者均返回 `incomplete_decode`。QEMU 的 `virt` 平台不模拟 Pixel 6 的实际 USB 和网卡，不能由此推断默认路由、断线清理或互联网访问可用。候选 payload SHA-256 为 `ac57f6084e49200079fc932433bef4bcaeca1da4a9c37cd02555725b8fd00e8f`，留在忽略目录，未刷写或启动真机。
- **导入差异的定位：** 旧归档 `route.o` 的 DWARF 记录编译器为 Apple clang 15；本地配方使用 Apple clang 21。用同一配方重编译**未加 0123 的基线 `route.c`**，也得到 `_memset` 而不是旧归档的 `___memset_chk`。两者都存在于 0122 已链接内核的全局符号表；因此此差异与新路由函数无关，但仍需审核替换对象的运行时契约。
- **可复现门禁：** `python3 tools/relink-oriole-netroute-xnu-0123.py` 检查固定输入哈希、在临时目录里重放 0123 补丁、重编译两个替换对象、核对对象导入和导出差异、重链接并审计段布局、符号集和最终内核哈希；本机输出 `OFFLINE RELINK PASS f68406db…`。脚本只写入忽略的 `private/`，不操作手机。当前手机不在可识别的 Fastboot/ADB 状态，仍需真机临时启动和路由、触摸、联网结果。
