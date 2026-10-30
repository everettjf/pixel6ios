# Archived root-volume experiments

These scripts are the small source-only snapshot retained from the local Linux VM used during the Pixel 6 research. They are **historical research material**, not a reviewed public root-image builder or an installation procedure. The tested image also depended on Apple-supplied iOS inputs, a pinned local toolchain, and private validation steps that are not part of a clean clone. No Apple image, firmware, device dump, or key is included here.

`mkiosroot.sh`, `sweet-root-tweaks.py`, `patch-launchd-plist.py`, `mkinit.py`, and `sweet-init.S` came from the local userland worktree and carry its MIT license, included as `LICENSE`. `disable_hfs_journal.py` and `sparse_compare.py` were one-off validation utilities from the same VM session. The former is tied to one exact 16 GiB input hash and modifies that file in place; it must not be treated as a generic HFS repair tool.

The verified hardware result and the remaining public-build gates are documented in [Milestone 1](../../../docs/MILESTONE-ONE.md) and [Installation status](../../../docs/INSTALLATION-STATUS.md). Future work should turn these snapshots into a separately reviewed, reproducible workflow before anyone uses them on a device.
