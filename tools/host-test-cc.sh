#!/bin/sh
# These upstream host tests treat __aarch64__ as bare metal and execute EL1 MRS.
# Use the pre-existing Rosetta x86_64 environment for host-only fake-hardware tests.
case " $* " in
  *" -shared "*)
    # Python loads the QR fixture library in-process, so match native Python.
    exec /usr/bin/clang -Wno-unknown-attributes "$@" ;;
  *" usbprobe_host_test.c "*)
    script=$0
    [ ! -L "$script" ] || script=$(readlink "$script")
    root=$(CDPATH= cd "$(dirname "$script")/.." && pwd)
    # The test models linker image bounds using _head and _end atoms.
    # Mach-O otherwise orders these zero-fill symbols differently than ELF.
    exec /usr/bin/clang -arch x86_64 -Wno-unknown-attributes -Wl,-order_file,"$root/tools/host-image.order" "$@" ;;
esac
# GCC-only noipa annotations control the audited target object, built by GCC.
# Clang host fixtures don't need that attribute; all behavioral checks stay on.
exec /usr/bin/clang -arch x86_64 -Wno-unknown-attributes "$@"
