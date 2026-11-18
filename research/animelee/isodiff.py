#!/usr/bin/env python3
"""Compare two GameCube ISOs: header, DOL (per section), and the file system.

    python3 isodiff.py VANILLA.iso MODDED.iso

Used to answer "does this mod change anything our Gecko codes depend on?" (the DOL), and
"which game files does it replace?" (the FST).
"""
import struct
import sys
import hashlib
from collections import Counter


def be32(b, o):
    return struct.unpack(">I", b[o:o + 4])[0]


class Iso:
    def __init__(self, path):
        self.f = open(path, "rb")
        self.path = path
        h = self.read(0, 0x440)
        self.id = h[:6].decode()
        self.rev = h[7]
        self.dol_off = be32(h, 0x420)
        fst_off, fst_size = be32(h, 0x424), be32(h, 0x428)
        fst = self.read(fst_off, fst_size)
        n = be32(fst, 8)
        names_off = n * 12
        self.files = {}
        stack = []  # (end_index, path)
        path_parts = []
        for i in range(1, n):
            e = fst[i * 12:i * 12 + 12]
            is_dir = e[0] == 1
            name_off = int.from_bytes(e[1:4], "big")
            end = fst[names_off + name_off:].split(b"\0", 1)[0].decode("latin1")
            while stack and stack[-1][0] <= i:
                stack.pop()
                path_parts.pop()
            if is_dir:
                stack.append((be32(e, 8), end))
                path_parts.append(end)
            else:
                self.files["/".join(path_parts + [end])] = (be32(e, 4), be32(e, 8))

    def read(self, off, n):
        self.f.seek(off)
        return self.f.read(n)

    def dol(self):
        h = self.read(self.dol_off, 0x100)
        offs = struct.unpack(">18I", h[:0x48])
        addrs = struct.unpack(">18I", h[0x48:0x90])
        sizes = struct.unpack(">18I", h[0x90:0xD8])
        secs = []
        for i in range(18):
            if sizes[i]:
                secs.append((i, addrs[i], self.read(self.dol_off + offs[i], sizes[i])))
        return h, secs

    def file(self, name):
        off, size = self.files[name]
        return self.read(off, size)


def main():
    a, b = Iso(sys.argv[1]), Iso(sys.argv[2])
    print(f"header: {a.id} rev{a.rev}  vs  {b.id} rev{b.rev}")
    ha, sa = a.dol()
    hb, sb = b.dol()
    print(f"DOL header identical: {ha == hb}")
    total = 0
    for (i, addr, da), (j, addr2, db) in zip(sa, sb):
        if (i, addr, len(da)) != (j, addr2, len(db)):
            print(f"  section {i}: layout differs")
            continue
        diff = [k for k in range(0, len(da), 4) if da[k:k + 4] != db[k:k + 4]]
        total += len(diff)
        if diff:
            print(f"  section {i} @0x{addr:08X} len 0x{len(da):X}: {len(diff)} words differ,"
                  f" first 0x{addr + diff[0]:08X} last 0x{addr + diff[-1]:08X}")
        else:
            print(f"  section {i} @0x{addr:08X}: identical")
    print(f"DOL words changed: {total}")

    only_a = sorted(set(a.files) - set(b.files))
    only_b = sorted(set(b.files) - set(a.files))
    changed, same = [], 0
    for name in sorted(set(a.files) & set(b.files)):
        if a.files[name][1] != b.files[name][1] or a.file(name) != b.file(name):
            changed.append(name)
        else:
            same += 1
    print(f"files: {len(a.files)} vs {len(b.files)}; identical {same}, changed {len(changed)},"
          f" removed {len(only_a)}, added {len(only_b)}")
    print("removed:", only_a)
    print("added:", only_b)
    print("changed:")
    for n in changed:
        print(f"  {n}  {a.files[n][1]} -> {b.files[n][1]}")


main()
