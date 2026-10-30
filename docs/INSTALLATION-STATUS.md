# Installation status

**No public installation procedure is available.** The first milestone is a developer experiment on one Pixel 6 (`oriole`), not a downloadable operating-system distribution.

| Gate | Current status | Required result |
| :--- | :--- | :--- |
| Reproducible build | The local image path uses pinned inputs in ignored `private/`. | A clean clone and documented toolchain build the tested artifacts without the author's private directory. |
| iOS root creation | The tested HFSX image is not distributed. | A reviewed workflow accepts a user's own compatible iOS inputs, checks product/build and output format, and records hashes. |
| Device preflight | Existing checks are tied to the test phone and firmware. | A public read-only preflight rejects unknown models, firmware, capacity, and bootloader states before any write. |
| Interaction | One tester entered Home and opened Settings by touch. | Repeated gesture, multi-touch, more-app, and long-session tests on physical hardware. |
| Network | Safari's Google page was blank. | Verified device address, route, DNS, and a successful request from a system app. |
| Clean display | The tested image overlays diagnostic text. | Boot-test the quieter candidate and confirm the interface and touch still work. |
| Recovery | Android may enter Recovery with the experimental `userdata`. | Document and independently test a full return to a bootable Android state. |
| Reproducibility | One phone has been tested. | A second Pixel 6 completes the documented process from a clean host. |
| Automatic boot | The iOS path requires `fastboot boot`. | Review and test an opt-in persistent boot path with a dependable fallback. |

**Data and boot boundary:** Preparing `userdata` for the iOS root erases existing Android local data. A temporary `fastboot boot` does not write boot partitions, but it also does not make iOS the default operating system. The research configuration reads the physical root volume and places runtime writes in volatile RAM. Do not infer daily-use data persistence or recovery readiness from the first milestone.

The current repository intentionally omits Apple root images, firmware, raw personal device logs, and private build inputs. Publishing the source does not make those components redistributable. The existing developer scripts are not a general-purpose installer. For the full engineering checklist, see the earlier [public-install-readiness research log](PUBLIC-INSTALL-READINESS.md) (Chinese).
