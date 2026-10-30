# Pixel 6 USB Internet trial, 2026-10-29

**Result: Internet access remains unverified.** The verified 0134 image was temporarily booted on one unlocked Pixel 6 (`oriole`). The Mac and phone exchanged packets over USB, but no phone-originated public HTTP request, DNS lookup, or Safari result was observed. No host NAT, DHCP, or DNS configuration was applied in this trial.

## Evidence from this run

| Observation | Evidence and limit |
| --- | --- |
| Temporary boot | Read-only preflight matched the pinned 0134 boot image and 16 GiB sparse root image, the recorded unlocked `oriole`, firmware slot, and partition geometry. `fastboot boot` succeeded; no partition was flashed. |
| USB local link | The Mac detected one `1209:0001` gadget and a new `en9` interface with `192.168.7.1/24`. Two ICMP probes to `192.168.7.2` received replies after iOS `configd` had started. This proves local IP exchange, not external routing. |
| Host uplink | Wi‑Fi `en1` was the default uplink. The Mac resolved `example.com` through its configured `192.168.1.254` DNS server and received HTTP 200 over HTTPS. This tests the Mac, not the phone. |
| iOS boot log | The captured log contains `exec SpringBoard`, `exec configd`, `exec mDNSResponder`, `exec addNetworkInterface`, and successful touch HID client opens. It also logs `configd` **requests** to delete the `0.0.0.0` route through `192.168.7.1` and the `ue0` address. The address printed by the tracing hook is known to be misdecoded, and these lines do not prove that deletion succeeded. The later ICMP replies show that the phone's local USB address remained reachable. |
| Host services | `net.inet.ip.forwarding=1` and macOS `bootpd` DHCP was disabled. The unprivileged PF query was denied, so NAT state was not established. A forwarding flag alone does not prove NAT. |

The private USB capture is `private/network-0134-20261029/udp.log` (SHA-256 `69677e99e08f1d8e9551f9444aa7720255c6656e19cc855bf00801d30f62b0e1`); its watcher result and USB-interface transitions are alongside it. No device identifier or Apple image is included in the public repository.

## Scoped host preparation

The live-state generator produced an **unapplied** plan in ignored `private/network-0134-host-plan-20261029/`: DHCP and DNS only on `en9`, gateway `192.168.7.1`, upstream resolver `192.168.1.254`, and a PF NAT rule for `192.168.7.0/24` out of `en1`. `dnsmasq 2.93 --test` and `/sbin/pfctl -vnf` accepted the generated syntax. Seven focused unit tests with mocked probe traffic passed for the host preflight, plan generator, and local HTTP probe. This plan must be regenerated if the USB interface, uplink, or resolver changes. Its successful syntax checks say nothing about runtime DHCP, DNS, NAT, or Safari.

The next phone-side split test is `tools/probe_oriole_usb_http.py`, which serves a random local HTTP URL on `192.168.7.1:18080`. A successful Safari request would prove phone-to-Mac TCP without requiring DNS or NAT. Only after that should a scoped DHCP/DNS/NAT trial be applied and a phone-originated request to an external IP and domain be measured. The tester was away from the phone during this run, so no Safari URL was entered.

## Why the iOS service still needs inspection

The root image's SystemConfiguration preferences contain no USB `NetworkServices`, IPv4, or DNS service entry. The image does contain the `addNetworkInterface` launch job, and the 0134 log confirms its process started. We have not observed whether it created and activated a service for `ue0`, whether `configd` ultimately removed or replaced the default route, or what DNS resolver the running phone selected. Apple's [System Configuration API](https://developer.apple.com/documentation/systemconfiguration/scnetworkserviceestablishdefaultconfiguration%28_%3A%29?language=objc) documents how default network protocols are created for a service; process launch alone is insufficient evidence that this completed. These device-side states need direct runtime evidence before changing XNU routing or declaring Safari fixed.

When a human is at the phone, use the same pinned image and capture from before boot. First test the local HTTP challenge in Safari, then correlate the result with device USB logs. If the local HTTP test succeeds, test the host-scoped configuration and confirm a real phone-originated public request, DNS answer, and App result. Preserve a working Android return path and do not interpret the USB log stream as Internet traffic.
