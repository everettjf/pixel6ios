"""One-off local HFSX root experiment: clear only journaled bit in both headers."""

import hashlib
from pathlib import Path
import sys

EXPECTED = '7298086eb69b8491780c26e61bfe4cae6a6da9d0014a6fba2435217eb8e0ed24'
SIZE = 16 * 1024**3
OLD = 0x80002100
NEW = OLD & ~(1 << 13)
path = Path(sys.argv[1])
assert path.stat().st_size == SIZE
h = hashlib.sha256()
with path.open('rb') as f:
    while b := f.read(1024 * 1024):
        h.update(b)
assert h.hexdigest() == EXPECTED, 'Input image digest mismatch'
with path.open('r+b', buffering=0) as f:
    positions = (1024, SIZE - 1024)
    for pos in positions:
        f.seek(pos)
        b = f.read(16)
        assert b[:4] == b'HX\x00\x05'
        assert int.from_bytes(b[4:8], 'big') == OLD
        assert int.from_bytes(b[12:16], 'big') == 0x81
    for pos in positions:
        f.seek(pos + 4)
        assert f.write(NEW.to_bytes(4, 'big')) == 4
    f.flush()
    import os
    os.fsync(f.fileno())
print(f'Cleared HFS journaled bit in two volume headers; {OLD:#x} -> {NEW:#x}')
