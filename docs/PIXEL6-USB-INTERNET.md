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

**主机只读基线（2026-10-28，本机观察）：** `python3 tools/preflight_oriole_usb_host.py` 只读查询 Mac 默认路由、`192.168.7.1` 所在接口与 `1209:0001` USB gadget 数量，不启用转发、NAT 或 DNS。本次输出显示默认上行为 `en1`，没有 `192.168.7.1` 接口，也没有目标 gadget，因此主机出口尚未可测。即使以后输出 `distinct_candidate=true`，也只表示一条候选接口与上行分离，不能证明该接口属于 Pixel 6 或 iOS 已联网。Mac 的[互联网共享设置说明](https://support.apple.com/en-sg/guide/mac-help/mchlp1540/27/mac/27)提供系统支持的上行/下行选择界面；配置前仍须用真机连接前后的接口变化确认下行身份，避免选错网络口。

**主机状态复核（2026-10-28，本机观察）：** Mac 的 `net.inet.ip.forwarding` 当前为 `1`，上行仍为 `en1`，但没有 Pixel 6 USB gadget 或 `192.168.7.1` 下行接口；无管理员权限时 `pfctl -s info` 返回权限不足，NAT 状态尚未核实。只读预检现记录 IPv4 转发状态；该值为 `1` 仍不证明 NAT、DNS 或 iOS 外网可达，也不应在手机未连接时改变现有主机网络配置。

Wi-Fi 驱动是另一条路线，现有 [上游研究](../research/pixelios-kernel/docs/research/20-wifi-stack-plan.md)不能证明 Pixel 6 真机 Wi-Fi 可用。USB 联网可作为更早的可测试出口，但不等于最终无线联网。

## 本地候选：0123（尚未真机验证）

- **读自源码 / 本地构建：** `0123-oriole-usb-owned-default-route.patch` 是默认关闭的 `sweetnetroute=1` 候选。只有在 `ue0` 地址设置成功、USB 数据接口切到 alt-setting 1 后，它才尝试安装经 `192.168.7.1` 的默认路由；接口下线时仅在路由对象、网卡索引和 IPv4 网关仍匹配时撤销。插入时也核对路由实际选中的网卡。该补丁位于已推送的 `wip/oriole-usb-internet-route` 分支，尚未合入 `main`。
- **本地检查：** 补丁可在对应的 XNU 基线上 `git apply --check`，仓库门禁在本机输出 `GATE PASS 7dc299d`。`sweet_usb.c` 和 `route.c` 候选源码都已编译成对象文件。为适配现有编译头文件，补丁把 `route.c` 中对不透明 `lo_ifp` 的直接字段访问改用 XNU 的 `ifnet_index(lo_ifp)`；该 API 源码在非空时返回同一 `if_index`。这还不等于完整内核重链接或真机启动通过。
- **未验证：** 真机路由添加、断线清理、重连、DNS 和互联网访问。现有 USB 驱动在 reset/disconnect 时没有清除 `configured`，可能跳过后续端点重配。完成完整构建、异模型审查及真机临时启动结果前，不应把该候选合入 `main` 或称为可用功能。
- **重链接约束（本地对象对比）：** 新 `sweet_usb.o` 只增加预期的路由 API 引用；新 `route.o` 的公开符号增加两个预期 API。然而现有通用编译配方生成的 `route.o` 与已验证归档的未定义符号集合不同，尤其是 `memset` 与 `__memset_chk`。在重建与已验证归档等价的路由对象、审核内核布局之前，不能把该对象直接替换进真机镜像。相关比对产物留在忽略的 `private/oriole-net-route-source/`。

## 0123 离线重链接记录（2026-10-28）

- **本地构建：** 用 `NECP=1`、`MACH_ASSERT=1` 编译候选 `route.c` 后，缺失的 NECP 与锁断言引用恢复到已验证归档的形式。以 0122 归档为基线，只替换 `route.o`、`sweet_usb.o`，重链接得到 16,713,816 字节的候选内核，SHA-256 `f68406db756901338eedec463cec3bf54c063f56c817c8fb5173398fb89a89ef`。全局符号只增加 `_rtrequest_add_gateway_on_ifindex` 和 `_rtrequest_delete_if_same`，入口地址与加载命令序列未变。
- **布局差异：** `__TEXT_EXEC` 比 0122 增加 16 KiB，后续加载段地址和文件偏移随之移动 16 KiB。离线解析确认段集合、入口、加载命令序列和 `__symbolsets` 内容相同；新旧两份 Mach-O 的段虚拟地址及文件范围各自无重叠，候选映像末端从 `0xfffffe0008728000` 移到 `0xfffffe000872c000`。因此 0122 的“除 LINKEDIT 外各段布局完全相同”审计不能直接用于 0123。
- **离线模拟：** 用与 0122 相同的 ADT 和命令行，另加 `sweetnetroute=1` 构造候选 payload；QEMU 运行 12 秒。候选与 0122 基线显示完全相同的 `SWEET EARLY 1` 至 `SWEET EARLY 20` 日志，二者均返回 `incomplete_decode`。QEMU 的 `virt` 平台不模拟 Pixel 6 的实际 USB 和网卡，不能由此推断默认路由、断线清理或互联网访问可用。候选 payload SHA-256 为 `ac57f6084e49200079fc932433bef4bcaeca1da4a9c37cd02555725b8fd00e8f`，留在忽略目录，未刷写或启动真机。
- **导入差异的定位：** 旧归档 `route.o` 的 DWARF 记录编译器为 Apple clang 15；本地配方使用 Apple clang 21。用同一配方重编译**未加 0123 的基线 `route.c`**，也得到 `_memset` 而不是旧归档的 `___memset_chk`。两者都存在于 0122 已链接内核的全局符号表；因此此差异与新路由函数无关，但仍需审核替换对象的运行时契约。
- **可复现门禁：** `python3 tools/relink-oriole-netroute-xnu-0123.py` 检查固定输入哈希、在临时目录里重放 0123 补丁、重编译两个替换对象、核对对象导入和导出差异、重链接并审计段布局、符号集和最终内核哈希。它还验证既有 0123 GUI 触摸配置及 ADT，追加唯一的 `sweetnetroute=1`，重新生成相同哈希的 payload。本机分别输出 `OFFLINE RELINK PASS f68406db…` 和 `OFFLINE PAYLOAD PASS ac57f608…`。脚本只写入忽略的 `private/`，不操作手机。当前手机不在可识别的 Fastboot/ADB 状态，仍需真机临时启动和路由、触摸、联网结果。

## 0124 本地临时镜像（未真机启动）

- **本地构建：** 独立的 `oriole_touch_netroute_0124.py` 配置只接受 payload SHA-256 `ac57f6084e49200079fc932433bef4bcaeca1da4a9c37cd02555725b8fd00e8f`，内核 SHA-256 `f68406db756901338eedec463cec3bf54c063f56c817c8fb5173398fb89a89ef`，并核对触摸 ADT、启动参数和完整 AVB 镜像。`shim/build.sh` 的单独选项使用新 payload 长度 `16730160` 和内核末端 `0xfffffe000872c000` 的运行时边界；旧配置继续使用原有长度和末端地址。构建时 C 端 payload guard 的正例与截断反例均通过。
- **本地产物：** 完整镜像留在忽略目录 `private/oriole-net-route-source/relink-0123/oriole-netroute-0124-avb.img`，大小 64 MiB，SHA-256 `34951d115aa9e933bf1b2b69e8897fcd74779bb048e8693c008c82c178e692fb`。它来自本机已通过离线重链接审计的内核和 payload；镜像校验通过，不代表手机上的路由、触摸、App 或互联网访问已经通过。
- **等待真机证据：** 电脑目前没有识别到 Fastboot/ADB 设备。恢复连接后，仍须先核对唯一设备为已记录且解锁的 `oriole`、固件/槽位、镜像和 userdata 根镜像哈希，再做临时 `fastboot boot`。不应写其他分区；未经真机路由、触摸和 App 测试，不把该镜像合入稳定安装路径。
- **只读预检：** `python3 tools/preflight_oriole_touch_gui.py --trial 0124 --offline` 检查 0124 镜像和 iOS 根镜像的固定哈希及容量；手机确实处于 Fastboot 且连接后，去掉 `--offline` 才会进一步核对唯一已记录的解锁 `oriole`、槽位、bootloader 和分区容量。预检不启动或写入手机，且通过不代表触摸或联网已工作。
- **读自源码的重连缺口：** 在 0123 候选应用后的 `sweet_usb.c` 中，`ud_configure()` 一见 `ud.configured` 为真就直接返回；USB reset/disconnect 分支会调用 `ud_netroute_link(false)`，但没有清除 `ud.configured`，也没有重置未完成的 TX 状态。若控制器复位使端点失效，后续主机再次发 `SET_CONFIGURATION(1)` 时可能跳过端点重配。[Android common 的 DWC3 gadget reset 实现](https://android.googlesource.com/kernel/common/+/2b1828f3335bf6dda01d4fe72af1a3e8b3c50c40/drivers/usb/dwc3/gadget.c)在 reset 时明确停止活动传输、复位 EP0 状态；这支持必须处理在途传输的判断，但不能直接照搬其 Linux 驱动状态机。尚无本机重连记录证明故障一定发生；下一轮应分别记录首次连接、拔线、重插后的 USB 端点配置日志、设备侧路由、Mac 网络接口与实际外网请求。确认故障后，再修改端点及队列状态清理，不能只清一个标志就宣称重连已修复。
- **读自源码的修复前置条件（2026-10-28）：** 当前 `ud_start_trb()` 发送 `DEPCMD_STARTTRANSFER` 后丢弃端点命令返回的 transfer resource index，`ud_epcmd()` 也只返回成功/失败；RX、TX、通知和 EP0 的活动传输资源均未在驱动状态里记录。[同一 DWC3 源码的停止传输实现](https://android.googlesource.com/kernel/common/+/2b1828f3335bf6dda01d4fe72af1a3e8b3c50c40/drivers/usb/dwc3/gadget.c)用 `dep->resource_index` 构造 `ENDTRANSFER` 命令，且 reset 路径要求结束活动传输。因此不能仅在 reset 时把 `configured`/`tx_busy` 清零并立即复用 TRB；需要先核对本机 DWC_usb31 版本和命令返回字段，记录每个端点的资源索引，按硬件规定结束传输并处理队列/EP0，再允许重配。Linux 实现对高速/全速端点命令还有 PHY 低功耗位处理，移植前须逐项核对。此处是源码推论，不是本机重连失败的真机结论。
- **已核对的寄存器字段：** 同一固定提交的 [DWC3 `core.h`](https://android.googlesource.com/kernel/common/+/2b1828f3335bf6dda01d4fe72af1a3e8b3c50c40/drivers/usb/dwc3/core.h) 定义 `DEPCMD` 的资源索引为命令完成寄存器值的 bits 22:16（`(value >> 16) & 0x7f`），`ENDTRANSFER` opcode 为 `0x08`，资源索引作为 `DEPCMD_PARAM(index)` 送回。现有驱动的 `ud_epcmd()` 在等待命令完成后只检查状态 bits 15:12，随后直接返回 `0`；故下一版实现必须在 *STARTTRANSFER 成功之后* 保存索引，再按端点记录传输完成/取消，不能从 TRB 地址或队列长度推导索引。曾在 Tensor G1 设备日志读到 `GSNPSID=0x33313130`（`device/google/bluejay/hardware/probe-log-2026-10-21-run1.txt`）；按同一头文件的 `GSNPS_ID` 掩码，其高 16 位 `0x3331` 属 DWC31 家族。该蓝鸦记录不代替本轮 `oriole` 的现场版本核对。

## 0124 传输资源观测补丁（未真机启动）

`research/pixelios-kernel/xnu/patches/0124-oriole-usb-transfer-resource-observe.patch` 是供后续重连设计使用的**本地观测候选**，与上面的 0124 临时镜像编号相同，但尚未构建进该镜像。它保留现有端点命令接口，另外在 `STARTTRANSFER` 成功时读取返回寄存器的 bits 22:16，按物理端点 0–5 暂存资源索引；收到相应传输完成事件后清除软件记录，并在 USB reset 时打印快照。TX 快照使用现有 TX 互斥锁，避免与发送线程同时读写。补丁没有发出 `ENDTRANSFER`，也没有改动 reset、disconnect 或端点重配流程。

**本地检查：** 补丁在对应基线上 `git apply --check`、重放并与候选源码逐字节比对通过；更新后的 `sweet_usb.c` 编译为 Mach-O 对象，未定义符号清单与 0123 基线对象相同。异模型独立审查未发现高优先级问题。完整仓库门禁在提交 `44119e4` 上输出 `GATE PASS 44119e4`；这些结果不构成完整内核重链接或真机验证。

**证据边界：** 该数值是驱动的软件记录，可能受完成事件和新传输之间的时序影响，不能当作硬件当前仍有活动传输的证明，更不能直接拿来发 `ENDTRANSFER`。由于手机当前不在可识别的 USB 状态，尚无该补丁的真机启动结果。后续须先完成内核重链接和临时启动审计，再观察首次连接、reset、拔插后的命令返回及端点事件，依据现场版本设计停止传输状态机。

**离线重链接（2026-10-28）：** `python3 tools/relink-oriole-usb-resource-xnu-0124.py` 固定补丁、前后源码、编译配方、0123 归档及内核的 SHA-256，重放补丁、编译替换对象、核对导入和公开符号，然后重链接并审计 Mach-O。输出 `OFFLINE USB RESOURCE RELINK PASS 6dc7bd5d718d6292cd41aeb924c9966bc822ab2067eae41f24663b26fb04046b`；候选内核大小 16,697,408 字节，留在忽略的 `private/oriole-net-route-source/relink-0124/`。与 0123 相比，入口、加载命令、公开符号和 `__symbolsets` 未变；`__TEXT_EXEC` 缩小 16 KiB，后续段前移 16 KiB，段虚拟地址与文件范围均无重叠。上文的 0124 临时镜像仍包含旧的 0123 内核，不含此观测补丁。

**0125 本地临时镜像（未真机启动）：** 新 profile `oriole_touch_netroute_resource_0125.py` 固定内核、payload 和完整 AVB 镜像哈希，沿用已核对的触摸 ADT 与 0124 启动参数。payload 为 16,713,744 字节，SHA-256 `c87a4317c1e0ac019bfcd1723ae399ce21036bab1e36ec67e5d580540dc802d3`；独立运行时守卫采用该精确长度及 `kernel_end=0xfffffe0008728000`，正例和截断反例均通过。完整镜像留在忽略的 `private/oriole-net-route-source/relink-0124/oriole-usb-resource-0125-avb.img`，大小 64 MiB，SHA-256 `d13bf273969dff02a101f2e70c857f7bcf7f5d9b61360448dc12146a35806a4e`。`python3 tools/preflight_oriole_touch_gui.py --trial 0125 --offline` 通过镜像、16 GiB 根镜像和 sparse 几何检查。镜像只供核实设备后临时 `fastboot boot`，未刷写手机；没有真机触摸、路由、App、联网或 USB 重连结论。
