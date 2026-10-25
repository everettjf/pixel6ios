#!/usr/bin/env python3
"""Rebuild the reviewed Oriole storage objects without linking a kernel.

The input policy is fixed at docs/oriole-storage-build-inputs.json.  This
tool reconstructs the two sources from the numbered patch series, compiles
the unmodified 0102 baseline and explicit 0103/0104 draft, and refuses any
unreviewed input, dependency, object, or ABI delta.  Its only output is a
new directory below artifacts/.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "docs/oriole-storage-build-inputs.json"
ARTIFACTS = ROOT / "artifacts"
XCODE = Path("/Applications/Xcode.app")
DEFAULT_OUTPUT = ARTIFACTS / "fullroot-build-review/storage-objects"
TARGETS = {"ufs": "sweet_ufs.c", "usb": "sweet_usb.c"}
LOCAL_HEADERS = {
    "osfmk/arm/caches_internal.h",
    "osfmk/arm64/proc_reg.h",
    "pexpert/pexpert/arm64/board_config.h",
    "pexpert/pexpert/arm64/SWEET.h",
}
DENY_ENV = {
    "CPATH", "C_INCLUDE_PATH", "CPLUS_INCLUDE_PATH", "OBJC_INCLUDE_PATH",
    "SDKROOT", "DEVELOPER_DIR", "MACOSX_DEPLOYMENT_TARGET",
    "IPHONEOS_DEPLOYMENT_TARGET", "TVOS_DEPLOYMENT_TARGET",
    "WATCHOS_DEPLOYMENT_TARGET", "DRIVERKIT_DEPLOYMENT_TARGET",
}


class Refusal(RuntimeError):
    pass


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def tree_sha256(root: Path) -> str:
    h = hashlib.sha256()
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        h.update(path.relative_to(root).as_posix().encode() + b"\0")
        h.update(path.read_bytes())
    return h.hexdigest()


def expand(value: str) -> Path:
    return Path(value.replace("${ROOT}", str(ROOT)).replace("${XCODE}", str(XCODE)))


def require(condition: bool, message: str) -> None:
    if not condition:
        raise Refusal(message)


def clean_env() -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k not in DENY_ENV}
    env.update({"LC_ALL": "C", "LANG": "C"})
    return env


def run(argv: list[str], *, cwd: Path | None = None, data: bytes | None = None,
        ok: tuple[int, ...] = (0,)) -> subprocess.CompletedProcess[bytes]:
    result = subprocess.run(argv, cwd=cwd, input=data, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, env=clean_env())
    if result.returncode not in ok:
        command = " ".join(argv)
        raise Refusal(f"command failed ({result.returncode}): {command}\n"
                      + result.stdout.decode(errors="replace"))
    return result


def git_bytes(git: Path, repo: Path, commit: str, path: str) -> bytes:
    return run([str(git), "-C", str(repo), "show", f"{commit}:{path}"]).stdout


def load_policy() -> dict:
    policy = json.loads(POLICY_PATH.read_text())
    require(policy.get("schema") == 1, "unsupported policy schema")
    require(policy.get("status") ==
            "offline object-build input policy; does not authorize linking, payload creation, or hardware boot",
            "policy status is not the reviewed offline-only status")
    if "builder" in policy:
        builder = expand(policy["builder"]["path"])
        require(builder == Path(__file__).resolve() and
                sha256_file(builder) == policy["builder"]["sha256"],
                "builder source differs from policy")
    return policy


def verify_tools(policy: dict) -> dict[str, Path]:
    tools: dict[str, Path] = {}
    for name, record in policy["tools"].items():
        path = expand(record["path"])
        require(path.is_file(), f"missing pinned tool {name}: {path}")
        require(sha256_file(path) == record["sha256"], f"pinned tool drift: {name}")
        tools[name] = path
    version = run([str(tools["clang"]), "--version"]).stdout.decode()
    require(version.startswith(policy["tools"]["clang"]["version_prefix"]),
            "clang version text differs from policy")
    return tools


def verify_revision(git: Path, record: dict, *, clean: bool,
                    head_must_match: bool = True) -> Path:
    repo = expand(record["path"])
    run([str(git), "-C", str(repo), "cat-file", "-e", f"{record['commit']}^{{commit}}"])
    head = run([str(git), "-C", str(repo), "rev-parse", "HEAD"]).stdout.decode().strip()
    if head_must_match:
        require(head == record["commit"], f"source revision drift: {repo}: {head}")
    if clean:
        status = run([str(git), "-C", str(repo), "status", "--porcelain"]).stdout
        require(not status, f"source tree is modified: {repo}")
    return repo


def verify_patch_inventory(policy: dict, git: Path, patch_repo: Path, commit: str) -> None:
    listing = run([str(git), "-C", str(patch_repo), "ls-tree", "-r", "--name-only",
                   commit, "xnu/patches"]).stdout.decode().splitlines()
    numbered = []
    for path in listing:
        match = re.fullmatch(r"xnu/patches/(\d{4})-[^/]+\.(?:patch|sh)", path)
        if match and int(match.group(1)) <= 102:
            numbered.append(path)
    expected = [item["path"] for item in policy["baseline_patches"]]
    require(numbered == expected, "committed patch inventory through 0102 differs from policy")
    for record in policy["baseline_patches"]:
        blob = git_bytes(git, patch_repo, commit, record["path"])
        require(sha256_bytes(blob) == record["sha256"],
                f"committed patch content drift: {record['path']}")


def reconstruct_sources(policy: dict, tools: dict[str, Path], patch_repo: Path,
                        work: Path) -> tuple[Path, Path]:
    source = work / "source"
    source.mkdir()
    # The staging directory deliberately lives below artifacts/.  Give it an
    # inner repository so git-apply cannot discover and target the outer
    # project worktree.
    run([str(tools["git"]), "-C", str(source), "init", "-q"])
    include_args = []
    for path in ("bsd/dev/sweet_ufs.c", "bsd/dev/sweet_usb.c",
                 "bsd/dev/oriole_ufs_guard.h"):
        include_args.append(f"--include={path}")
    commit = policy["source_revisions"]["patches"]["commit"]
    for record in policy["baseline_patches"]:
        blob = git_bytes(tools["git"], patch_repo, commit, record["path"])
        if not record["path"].endswith(".patch"):
            continue
        run([str(tools["git"]), "-C", str(source), "apply", *include_args], data=blob)

    baseline = work / "baseline-source"
    baseline.mkdir()
    shutil.copytree(source / "bsd", baseline / "bsd")
    verify_source_hashes(baseline, policy["source_outputs"]["baseline"])

    for record in policy["draft_patches"]:
        patch = expand(record["path"])
        require(patch.is_file(), f"missing explicit draft patch: {patch}")
        blob = patch.read_bytes()
        require(sha256_bytes(blob) == record["sha256"],
                f"draft patch content drift: {patch}")
        run([str(tools["git"]), "-C", str(source), "apply", *include_args], data=blob)
    shutil.rmtree(source / ".git")
    verify_source_hashes(source, policy["source_outputs"]["patched"])
    return baseline, source


def verify_source_hashes(root: Path, expected: dict[str, str]) -> None:
    actual_files = sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file())
    require(actual_files == sorted(expected), f"reconstructed source file set differs: {actual_files}")
    for relative, digest in expected.items():
        require(sha256_file(root / relative) == digest,
                f"reconstructed source hash differs: {relative}")


def build_overlay(policy: dict, tools: dict[str, Path], patch_repo: Path,
                  xnu_repo: Path, work: Path) -> Path:
    overlay = work / "overlay"
    overlay.mkdir()
    run([str(tools["git"]), "-C", str(overlay), "init", "-q"])
    for path_text, digest in policy["overlay"]["inputs"].items():
        path = expand(path_text)
        require(path.is_file() and sha256_file(path) == digest,
                f"overlay input drift: {path}")

    master = xnu_repo / "config/MASTER"
    master_text = master.read_text()
    for option in ("CONFIG_DTRACE", "LOCK_STATS"):
        require(re.search(rf"(?m)^options\s+{option}(?:\s|$)", master_text) is not None,
                f"official DEVELOPMENT option is absent: {option}")

    for relative in ("osfmk/arm64/proc_reg.h",
                     "pexpert/pexpert/arm64/board_config.h"):
        destination = overlay / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(xnu_repo / relative, destination)

    patch_record = next(item for item in policy["baseline_patches"]
                        if item["path"].startswith("xnu/patches/0004-"))
    patch = git_bytes(tools["git"], patch_repo,
                      policy["source_revisions"]["patches"]["commit"], patch_record["path"])
    run([str(tools["git"]), "-C", str(overlay), "apply",
         "--include=osfmk/arm64/proc_reg.h",
         "--include=pexpert/pexpert/arm64/board_config.h",
         "--include=pexpert/pexpert/arm64/SWEET.h"], data=patch)

    caches = overlay / "osfmk/arm/caches_internal.h"
    caches.parent.mkdir(parents=True, exist_ok=True)
    filtered = run([str(tools["unifdef"]), "-DMACH_KERNEL_PRIVATE",
                    str(xnu_repo / "osfmk/arm/caches_internal.h")], ok=(0, 1)).stdout
    caches.write_bytes(filtered)
    shutil.rmtree(overlay / ".git")

    actual = sorted(p.relative_to(overlay).as_posix() for p in overlay.rglob("*") if p.is_file())
    require(actual == sorted(policy["overlay"]["outputs"]),
            f"overlay file set differs from policy: {actual}")
    for relative, digest in policy["overlay"]["outputs"].items():
        require(sha256_file(overlay / relative) == digest,
                f"derived overlay differs: {relative}")
    sweet = (overlay / "pexpert/pexpert/arm64/SWEET.h").read_text()
    require(re.search(r"(?m)^#define\s+__ARM_16K_PG__\s+1\s*$", sweet) is not None,
            "SWEET overlay does not select 16K pages")
    return overlay


def parse_dependencies(path: Path) -> list[Path]:
    text = path.read_text().replace("\\\n", " ")
    require(":" in text, f"malformed dependency file: {path}")
    words = text.split(":", 1)[1].split()
    # Keep framework symlink spellings: the policy pins the exact compiler
    # search result as emitted, while file hashes separately pin its target.
    return [Path(os.path.abspath(word.replace("\\ ", " "))) for word in words]


def normalized_external(path: Path) -> str:
    for prefix, token in ((ROOT, "${ROOT}"), (XCODE, "${XCODE}")):
        try:
            relative = path.relative_to(prefix)
            return f"{token}/{relative.as_posix()}"
        except ValueError:
            pass
    raise Refusal(f"dependency escaped pinned roots: {path}")


def verify_dependencies(kind: str, depfile: Path, source_root: Path, overlay: Path,
                        expected: dict[str, str]) -> None:
    local_expected = {source_root / f"bsd/dev/{TARGETS[kind]}"}
    if kind == "ufs" and source_root.name == "source":
        local_expected.add(source_root / "bsd/dev/oriole_ufs_guard.h")
    local_expected.update(overlay / item for item in LOCAL_HEADERS)
    dependencies = set(parse_dependencies(depfile))
    require(local_expected <= dependencies,
            f"compiler omitted expected local inputs for {kind}: {local_expected - dependencies}")
    external = dependencies - local_expected
    actual: dict[str, str] = {}
    for path in external:
        require(path.is_file(), f"dependency is not a regular file: {path}")
        actual[normalized_external(path)] = sha256_file(path)
    if actual != expected:
        missing = sorted(set(expected) - set(actual))[:8]
        extra = sorted(set(actual) - set(expected))[:8]
        changed = sorted(path for path in set(actual) & set(expected)
                         if actual[path] != expected[path])[:8]
        raise Refusal(f"{kind} compiler dependency graph differs from policy; "
                      f"missing={missing}, extra={extra}, changed={changed}")


def include_flags(overlay: Path, xnu_repo: Path, policy: dict) -> list[str]:
    framework = expand(policy["installed_header_tree"]["path"]).parent.parent
    sdk = XCODE / "Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk"
    toolchain = XCODE / "Contents/Developer/Toolchains/XcodeDefault.xctoolchain"
    includes = [
        overlay, overlay / "osfmk", overlay / "pexpert",
        xnu_repo / "bsd", xnu_repo / "osfmk", xnu_repo / "libkern",
        xnu_repo / "iokit", xnu_repo / "pexpert", xnu_repo / "security", xnu_repo,
        framework / "PrivateHeaders", framework / "Headers",
        sdk / "usr/include", toolchain / "usr/lib/clang/21/include",
    ]
    result: list[str] = []
    for path in includes:
        result.extend(["-I", str(path)])
    return result


def compile_object(kind: str, variant: str, source_root: Path, overlay: Path,
                   xnu_repo: Path, policy: dict, tools: dict[str, Path], work: Path) -> dict:
    output = work / "objects" / variant / f"sweet_{kind}.o"
    depfile = work / "dependencies" / variant / f"sweet_{kind}.d"
    logfile = work / "logs" / f"{variant}-sweet_{kind}.log"
    output.parent.mkdir(parents=True, exist_ok=True)
    depfile.parent.mkdir(parents=True, exist_ok=True)
    logfile.parent.mkdir(parents=True, exist_ok=True)
    source = source_root / "bsd/dev" / TARGETS[kind]
    command = [str(tools["clang"]), *policy["compile_flags"],
               *include_flags(overlay, xnu_repo, policy),
               "-MD", "-MF", str(depfile), "-c", str(source), "-o", str(output)]
    result = run(command)
    logfile.write_bytes(result.stdout)
    verify_dependencies(kind, depfile, source_root, overlay, policy["dependencies"][kind])
    expected = policy["expected_objects"][variant][f"sweet_{kind}.o"]
    require(sha256_file(output) == expected,
            f"{variant} sweet_{kind}.o differs from reviewed object")
    return {"path": output, "command": command, "log": logfile, "depfile": depfile}


class MachObject:
    def __init__(self, path: Path):
        self.path = path
        self.data = path.read_bytes()
        require(len(self.data) >= 32, f"truncated Mach-O object: {path}")
        magic, cputype, cpusubtype, filetype, ncmds, sizeofcmds, flags, reserved = \
            struct.unpack_from("<IIIIIIII", self.data, 0)
        self.header = {"magic": magic, "cputype": cputype, "cpusubtype": cpusubtype,
                       "filetype": filetype, "ncmds": ncmds, "sizeofcmds": sizeofcmds,
                       "flags": flags, "reserved": reserved}
        require(32 + sizeofcmds <= len(self.data), f"Mach-O command area out of bounds: {path}")
        self.sections: dict[str, int] = {}
        self.symbol_records: list[tuple[str, int, int, int, int]] = []
        symtab: tuple[int, int, int, int] | None = None
        offset = 32
        for _ in range(ncmds):
            require(offset + 8 <= 32 + sizeofcmds, f"truncated Mach-O command: {path}")
            cmd, cmdsize = struct.unpack_from("<II", self.data, offset)
            require(cmdsize >= 8 and offset + cmdsize <= 32 + sizeofcmds,
                    f"invalid Mach-O command size: {path}")
            if cmd == 0x19:
                require(cmdsize >= 72, f"truncated LC_SEGMENT_64: {path}")
                nsects = struct.unpack_from("<I", self.data, offset + 64)[0]
                require(72 + nsects * 80 <= cmdsize, f"truncated section list: {path}")
                for index in range(nsects):
                    section = offset + 72 + index * 80
                    sectname = self.data[section:section + 16].split(b"\0", 1)[0].decode()
                    segname = self.data[section + 16:section + 32].split(b"\0", 1)[0].decode()
                    size = struct.unpack_from("<Q", self.data, section + 40)[0]
                    require(f"{segname},{sectname}" not in self.sections,
                            f"duplicate Mach-O section: {segname},{sectname}")
                    self.sections[f"{segname},{sectname}"] = size
            elif cmd == 0x2:
                require(cmdsize == 24 and symtab is None, f"invalid/duplicate LC_SYMTAB: {path}")
                symtab = struct.unpack_from("<IIII", self.data, offset + 8)
            offset += cmdsize
        require(offset == 32 + sizeofcmds and symtab is not None,
                f"invalid Mach-O command coverage/symbol table: {path}")
        symoff, nsyms, stroff, strsize = symtab
        require(symoff + nsyms * 16 <= len(self.data) and stroff + strsize <= len(self.data),
                f"Mach-O symbol/string table out of bounds: {path}")
        strings = self.data[stroff:stroff + strsize]
        for index in range(nsyms):
            strx, n_type, n_sect, n_desc, value = struct.unpack_from("<IBBHQ", self.data,
                                                                     symoff + index * 16)
            require(strx < len(strings), f"Mach-O symbol string index out of bounds: {path}")
            end = strings.find(b"\0", strx)
            require(end >= 0, f"unterminated Mach-O symbol name: {path}")
            name = strings[strx:end].decode(errors="strict")
            self.symbol_records.append((name, n_type, n_sect, n_desc, value))

    def globals(self) -> set[str]:
        return {name for name, n_type, _, _, _ in self.symbol_records
                if n_type & 1 and n_type & 0x0e}

    def undefined(self) -> set[str]:
        return {name for name, n_type, _, _, _ in self.symbol_records
                if n_type & 1 and not n_type & 0x0e}

    def values(self) -> dict[str, int]:
        return {name: value for name, _, _, _, value in self.symbol_records}


def extract_reference(policy: dict, tools: dict[str, Path], work: Path) -> dict[str, Path]:
    archive = expand(policy["reference_archive"]["path"])
    require(archive.is_file() and sha256_file(archive) == policy["reference_archive"]["sha256"],
            "pinned CI reference archive differs")
    output = work / "reference"
    output.mkdir()
    run([str(tools["ar"]), "-x", str(archive), *policy["reference_archive"]["members"]],
        cwd=output)
    result = {}
    for member, digest in policy["reference_archive"]["members"].items():
        path = output / member
        require(path.is_file() and sha256_file(path) == digest,
                f"reference archive member differs: {member}")
        result[member.removeprefix("sweet_").removesuffix(".o")] = path
    return result


def verify_abi(policy: dict, reference: dict[str, Path], built: dict[tuple[str, str], dict]) -> None:
    header_policy = policy["abi_policy"]["mach_header"]
    expected_header = {"magic": int(header_policy["magic"], 16),
                       "cputype": int(header_policy["cputype"], 16),
                       "cpusubtype": header_policy["cpusubtype"],
                       "filetype": header_policy["filetype"],
                       "reserved": header_policy["reserved"]}
    originals = {kind: MachObject(path) for kind, path in reference.items()}
    objects = {(variant, kind): MachObject(record["path"])
               for (variant, kind), record in built.items()}
    for (variant, kind), obj in objects.items():
        for field, value in expected_header.items():
            require(obj.header[field] == value,
                    f"{variant} {kind} is not the reviewed plain ARM64 object format: {field}")
        require(obj.globals() == originals[kind].globals(),
                f"{variant} {kind} defined global symbols differ from CI member")
        require(set(policy["abi_policy"]["required_undefined"]) <= obj.undefined(),
                f"{variant} {kind} is missing strong stack-canary imports")

    for kind in TARGETS:
        original_imports = originals[kind].undefined()
        delta = policy["abi_policy"]["baseline_import_delta"][kind]
        expected = (original_imports | set(delta["add"])) - set(delta["remove"])
        baseline = objects[("baseline", kind)].undefined()
        require(baseline == expected, f"baseline {kind} import delta differs from policy")
        delta = policy["abi_policy"]["patched_import_delta_from_baseline"][kind]
        expected = (baseline | set(delta["add"])) - set(delta["remove"])
        require(objects[("patched", kind)].undefined() == expected,
                f"patched {kind} import delta differs from policy")

    for variant in ("baseline", "patched"):
        ufs = objects[(variant, "ufs")]
        for section, size in policy["abi_policy"]["ufs_sections"].items():
            require(ufs.sections.get(section) == size,
                    f"{variant} UFS DEVELOPMENT/startup section differs: {section}")
        values = ufs.values()
        require(values.get("_sweet_log_total", 0) - values.get("_sweet_ufs_lock", 0)
                == policy["abi_policy"]["ufs_mutex_bytes"],
                f"{variant} UFS mutex footprint differs")


def verify_all_declared_dependencies(policy: dict) -> None:
    header_root = expand(policy["installed_header_tree"]["path"])
    require(header_root.is_dir(), f"installed Kernel header tree missing: {header_root}")
    require(tree_sha256(header_root) == policy["installed_header_tree"]["sha256"],
            "installed Kernel header tree differs from policy")
    for kind, records in policy["dependencies"].items():
        for path_text, digest in records.items():
            path = expand(path_text)
            require(path.is_file() and sha256_file(path) == digest,
                    f"declared {kind} header dependency drift: {path}")


def sanitize_command(command: list[str], staging: Path) -> list[str]:
    return [item.replace(str(staging), "${BUILD}") for item in command]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    output = args.output_dir.expanduser().resolve()
    try:
        output.relative_to(ARTIFACTS.resolve())
    except ValueError as error:
        raise Refusal("output directory must be below the repository artifacts directory") from error
    require(not output.exists(), f"refusing to replace existing output: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)

    policy = load_policy()
    tools = verify_tools(policy)
    patch_repo = verify_revision(tools["git"], policy["source_revisions"]["patches"],
                                 clean=False, head_must_match=False)
    xnu_repo = verify_revision(tools["git"], policy["source_revisions"]["xnu"], clean=True)
    verify_patch_inventory(policy, tools["git"], patch_repo,
                           policy["source_revisions"]["patches"]["commit"])
    verify_all_declared_dependencies(policy)

    with tempfile.TemporaryDirectory(prefix="oriole-storage-", dir=output.parent) as temporary:
        staging = Path(temporary)
        baseline_source, patched_source = reconstruct_sources(policy, tools, patch_repo, staging)
        overlay = build_overlay(policy, tools, patch_repo, xnu_repo, staging)
        reference = extract_reference(policy, tools, staging)
        built: dict[tuple[str, str], dict] = {}
        for variant, source in (("baseline", baseline_source), ("patched", patched_source)):
            for kind in TARGETS:
                built[(variant, kind)] = compile_object(kind, variant, source, overlay,
                                                         xnu_repo, policy, tools, staging)
        verify_abi(policy, reference, built)

        record = {
            "schema": 1,
            "status": policy["status"],
            "policy": str(POLICY_PATH.relative_to(ROOT)),
            "policy_sha256": sha256_file(POLICY_PATH),
            "objects": {},
        }
        for (variant, kind), item in built.items():
            record["objects"].setdefault(variant, {})[f"sweet_{kind}.o"] = {
                "sha256": sha256_file(item["path"]),
                "command": sanitize_command(item["command"], staging),
            }
        (staging / "build-record.json").write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
        (staging / "OFFLINE-ONLY.txt").write_text(
            "These are compiler outputs only. This directory is not a kernel, payload, "
            "boot image, or authorization for hardware use.\n")
        staging.rename(output)

    print(json.dumps({"output": str(output), "status": "verified offline objects"}, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Refusal as error:
        raise SystemExit(f"REFUSED: {error}")
