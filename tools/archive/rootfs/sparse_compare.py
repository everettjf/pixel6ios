import struct
import sys

raw_path, sparse_path = sys.argv[1:]
with open(raw_path, 'rb') as raw, open(sparse_path, 'rb') as sparse:
    head = sparse.read(28)
    magic, major, minor, file_hdr, chunk_hdr, block, blocks, chunks, checksum = struct.unpack('<IHHHHIIII', head)
    assert (magic, major, file_hdr, chunk_hdr) == (0xED26FF3A, 1, 28, 12)
    assert block == 4096
    assert sparse.seek(file_hdr) == file_hdr
    done = 0
    for _ in range(chunks):
        kind, reserved, count, total = struct.unpack('<HHII', sparse.read(12))
        size = count * block
        assert reserved == 0
        if kind == 0xCAC1:
            assert total == chunk_hdr + size
            for part in range(0, size, 1024 * 1024):
                n = min(1024 * 1024, size - part)
                assert sparse.read(n) == raw.read(n), f'RAW mismatch at {done + part}'
        elif kind == 0xCAC2:
            assert total == chunk_hdr + 4
            fill = sparse.read(4)
            for part in range(0, size, 1024 * 1024):
                n = min(1024 * 1024, size - part)
                assert raw.read(n) == (fill * ((n + 3) // 4))[:n], f'FILL mismatch at {done + part}'
        elif kind == 0xCAC3:
            assert total == chunk_hdr
            for part in range(0, size, 1024 * 1024):
                n = min(1024 * 1024, size - part)
                assert raw.read(n) == bytes(n), f'DONT_CARE mismatch at {done + part}'
        else:
            raise AssertionError(f'Unsupported chunk type {kind:#x}')
        done += size
    assert done == blocks * block
    assert not raw.read(1)
    assert not sparse.read(1)
    print(f'PASS: sparse expands byte-for-byte to raw image ({done} bytes, {chunks} chunks)')
