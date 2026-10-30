#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把机内 KYUSHU 的调色数据从“供体” DNG 移植到目标 DNG（近似方案）。

背景
----
PDCU 5.10.2.2 的「KYUSHU」菜单项本身不生成 SE 参数，它依赖相机写进 DNG
私有数据（`DNGPrivateData`，tag 0xC634）里的那套影像参数。非机内 KYUSHU 的
文件没有这套数据，所以菜单选中 KYUSHU 也只能得到 PDCU 的通用/默认结果。

在 K-3 Mark III 上实测：把机内 KYUSHU 文件私有块的**前 15,031 字节**
（`+0x0000..+0x3AB7`，即“私有 IFD + 0x021f 前 0x733 字节”）写进目标，
PDCU 就会把目标渲染成 KYUSHU（雷达图变成斜四边形）。

其他机型
--------
- **供体与目标必须是同一机型**：这套参数是机型相关的，跨机型移植没有意义。
- K-3 Mark III 的布局（`PENTAX \\0IId`，块大小 195,676）是实测的；
- 其他布局（如 K-1/K-1 II/KF）没有实测样本，工具用同一套**相对规则**估算：
  `len = tag 0x021f 的块内偏移 + 0x733`；
  结果可能需要在 PDCU 里验证；必要时用 `--len` 指定实测出来的长度。
- 645Z 等不支持四季 SE 的机型没有 KYUSHU 供体，工具会拒绝。

注意
----
这是**近似**：这段数据里同时含有供体的影调/白平衡成分，输出会带上供体的
色彩倾向（例如用日落场景的供体会让室内图偏暖/偏橙）。尽量选与目标**光线
条件接近**的供体，生成后在 PDCU 里再微调白平衡/影调。

本工具不会修改输入文件。

用法
----
    python tools/kyushu_transplant.py --donor IMGP1157.DNG --target IMGP1194.DNG \
        --out IMGP1194_KYUSHU.DNG

    # 只检查机型/布局/模式标记，不写文件
    python tools/kyushu_transplant.py --donor ... --target ... --verify-only

    # 其他机型：先按默认规则试，必要时用 --len 指定长度
    python tools/kyushu_transplant.py --donor K1_KYUSHU.DNG --target K1.DNG \
        --out K1_KYUSHU.DNG --allow-untested --len 15031
"""

from __future__ import annotations

import argparse
import hashlib
import struct
import sys
from pathlib import Path

PRIVATE_TAG = 0xC634

# 私有块固定开头；紧随其后的 2 个字节是 Pentax IFD 的条目数，不是 magic：
#   K-3 Mark III = 100（0x64，看起来像 'd'），645Z = 113（0x71，像 'q'）。
PRIVATE_PREFIX = b"PENTAX \x00II"
K3III_ENTRIES = 100
K3III_BLOCK = 195676
K3III_LEN = 0x3EB5 - 0x3FE  # 15031

# 通用估算规则：私有 IFD 的全部内容 + tag 0x021f 的前 0x733 字节
TAIL_IN_021F = 0x733

# K-3 III 机内 KYUSHU 的模式标记（十进制）
K3III_MARKERS = {"0x0014": 21, "0x0016": 50}


def _u16(data: bytes, off: int, bo: str) -> int:
    return struct.unpack_from(bo + "H", data, off)[0]


def _u32(data: bytes, off: int, bo: str) -> int:
    return struct.unpack_from(bo + "I", data, off)[0]


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest().upper()


def _tiff_byte_order(data: bytes) -> str:
    if data[:2] == b"II":
        return "<"
    if data[:2] == b"MM":
        return ">"
    raise ValueError("not a TIFF/DNG file (missing II/MM header)")


def _ifd_tag(data: bytes, bo: str, ifd: int, tag_wanted: int):
    """在指定 IFD 里找 tag，返回 (type, count, value_field_off) 或 None。"""
    n = _u16(data, ifd, bo)
    for i in range(n):
        o = ifd + 2 + i * 12
        tag = _u16(data, o, bo)
        if tag == tag_wanted:
            typ = _u16(data, o + 2, bo)
            cnt = _u32(data, o + 4, bo)
            return typ, cnt, o + 8
    return None


def find_private_block(data: bytes) -> tuple[int, int, str]:
    bo = _tiff_byte_order(data)
    ifd = _u32(data, 4, bo)
    hit = _ifd_tag(data, bo, ifd, PRIVATE_TAG)
    if not hit:
        raise ValueError("no DNGPrivateData (tag 0xC634)")
    _, cnt, vo = hit
    return _u32(data, vo, bo), cnt, bo


def camera_model(data: bytes) -> str:
    bo = _tiff_byte_order(data)
    ifd = _u32(data, 4, bo)
    hit = _ifd_tag(data, bo, ifd, 0x0110)  # Model
    if not hit:
        return "?"
    typ, cnt, vo = hit
    raw = data[vo:vo + 4] if cnt <= 4 else data[_u32(data, vo, bo):][:cnt]
    return raw.split(b"\0")[0].decode("latin1", "replace").strip()


def private_ifd(data: bytes, base: int) -> tuple[dict[int, bytes], dict[int, int]]:
    """读私有块里的 Pentax IFD，返回 (tag -> 值字节, tag -> 块内偏移)。"""
    if not data[base:base + 7] == b"PENTAX ":
        raise ValueError(f"private block does not start with PENTAX: {data[base:base + 12]!r}")
    bo = "<"
    count = _u16(data, base + 10, bo)
    values: dict[int, bytes] = {}
    offsets: dict[int, int] = {}
    for i in range(count):
        o = base + 12 + i * 12
        tag, typ, cnt = struct.unpack_from(bo + "HHI", data, o)
        size = {1: 1, 2: 1, 3: 2, 4: 4, 5: 8, 6: 1, 7: 1, 8: 2,
                9: 4, 10: 8, 11: 4, 12: 8}.get(typ, 1) * cnt
        val = data[o + 8:o + 12]
        if size <= 4:
            values[tag] = val[:size]
            offsets[tag] = o + 8 - base
        else:
            rel = struct.unpack(bo + "I", val)[0]
            values[tag] = data[base + rel:base + rel + size]
            offsets[tag] = rel
    return values, offsets


def shorts(raw: bytes) -> list[int]:
    return list(struct.unpack("<" + "H" * (len(raw) // 2), raw[:len(raw) // 2 * 2]))


def describe(tags: dict[int, bytes]) -> str:
    def one(tag):
        s = shorts(tags.get(tag, b""))
        return s[0] if s else "?"
    a = shorts(tags.get(0x0200, b""))
    c = shorts(tags.get(0x024c, b""))
    return f"0x0014={one(0x0014)}  0x0016={one(0x0016)}  0x0200={a}  0x024c={c}"


def is_k3iii_layout(header: bytes, size: int) -> bool:
    """K-3 Mark III：前缀 + 100 个 IFD 条目 + 195,676 字节的私有块。"""
    return (header.startswith(PRIVATE_PREFIX)
            and len(header) >= 12
            and struct.unpack_from("<H", header, 10)[0] == K3III_ENTRIES
            and size == K3III_BLOCK)


def is_k3iii_kyushu(tags: dict[int, bytes]) -> bool:
    q = shorts(tags.get(0x0014, b""))
    m = shorts(tags.get(0x0016, b""))
    return bool(q and m and q[0] == K3III_MARKERS["0x0014"] and m[0] == K3III_MARKERS["0x0016"])


def plan_transplant(header: bytes, size: int, tags: dict[int, bytes], offsets: dict[int, int],
                    model: str, override: int | None) -> tuple[int, str]:
    if override is not None:
        if not (0 < override <= size):
            raise ValueError(f"--len {override} is outside the private block (0..{size})")
        return override, "user-specified --len"
    if is_k3iii_layout(header, size):
        return K3III_LEN, "K-3 Mark III (tested)"
    if 0x021F not in tags:
        raise ValueError("private block has no tag 0x021f; cannot estimate the transplant length")
    length = offsets[0x021F] + TAIL_IN_021F
    if length > size:
        raise ValueError(f"estimated length {length} exceeds block size {size}")
    return length, f"untested heuristic for {model} (0x021f+0x{TAIL_IN_021F:X})"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Transplant in-camera KYUSHU tuning data into another DNG of the same "
                    "camera model (approximate; the output inherits the donor's tone/WB bias).")
    ap.add_argument("--donor", required=True, type=Path,
                    help="donor DNG shot in-camera with KYUSHU (same model as target)")
    ap.add_argument("--target", required=True, type=Path,
                    help="target DNG to receive KYUSHU (never modified)")
    ap.add_argument("--out", type=Path, help="output DNG; default <target>_KYUSHU.dng")
    ap.add_argument("--len", type=int, dest="length",
                    help="override the transplant length (bytes from the private block start)")
    ap.add_argument("--allow-untested", action="store_true",
                    help="allow models other than K-3 Mark III (heuristic length)")
    ap.add_argument("--force", action="store_true",
                    help="continue even if the donor lacks the expected mode markers")
    ap.add_argument("--force-cross-model", action="store_true",
                    help="allow donor/target on different models (NOT recommended)")
    ap.add_argument("--verify-only", action="store_true", help="check, write nothing")
    args = ap.parse_args(argv)

    donor = args.donor.resolve()
    target = args.target.resolve()
    if not donor.is_file() or not target.is_file():
        print("ERROR: donor/target not found", file=sys.stderr)
        return 2

    d = donor.read_bytes()
    t = target.read_bytes()
    do, dn, _ = find_private_block(d)
    to, tn, _ = find_private_block(t)
    dm, tm = camera_model(d), camera_model(t)
    dh, th = d[do:do + 12], t[to:to + 12]

    print(f"donor : {donor.name}  model={dm!r}  private offset=0x{do:X} size={dn}")
    print(f"target: {target.name}  model={tm!r}  private offset=0x{to:X} size={tn}")

    if dm != tm:
        print(f"ERROR: donor and target are different models ({dm!r} vs {tm!r}); "
              "the KYUSHU data is model-specific.", file=sys.stderr)
        if not args.force_cross_model:
            return 3
        print("WARNING: --force-cross-model set; the output may be broken.", file=sys.stderr)

    if dh != th or dn != tn:
        print("ERROR: donor/target private block layouts differ "
              f"(header {dh!r} vs {th!r}, size {dn} vs {tn}).", file=sys.stderr)
        return 3

    dtags, doffs = private_ifd(d, do)
    ttags, toffs = private_ifd(t, to)
    print(f"donor  markers: {describe(dtags)}")
    print(f"target markers: {describe(ttags)}")

    length, why = plan_transplant(dh, dn, dtags, doffs, dm, args.length)
    print(f"plan  : copy {length} bytes from the private block start ({why})")

    tested = is_k3iii_layout(dh, dn)
    if not tested and not args.allow_untested:
        print(f"ERROR: model {dm!r} is untested; re-run with --allow-untested "
              "after checking the output in PDCU.", file=sys.stderr)
        return 3
    if tested and not is_k3iii_kyushu(dtags) and not args.force:
        print("ERROR: donor does not look like an in-camera KYUSHU file "
              "(0x0014 should be 21/0x15, 0x0016 should be 50/0x32). "
              "Use --force to override.", file=sys.stderr)
        return 3
    if not tested:
        print("WARNING: untested layout; the length is estimated. Verify the result in PDCU.")
    if is_k3iii_kyushu(ttags):
        print("NOTE: target already carries the KYUSHU markers; its params will still be overwritten.")

    if args.verify_only:
        print("verify-only: nothing written")
        return 0

    out = args.out or target.with_name(target.stem + "_KYUSHU.dng")
    out = out.resolve()
    if out in (donor, target):
        print("ERROR: output path must differ from inputs", file=sys.stderr)
        return 2

    buf = bytearray(t)
    buf[to:to + length] = d[do:do + length]
    out.write_bytes(buf)

    print(f"\nwrote {length} bytes (private block +0x0000..+0x{length:X})")
    print(f"output: {out}")
    print(f"SHA-256: {_sha256(out)}")
    print("\nNOTE: the output inherits the donor's tone/WB bias (may look warmer).")
    print("      Correct WB/tone in PDCU afterwards; a donor shot under similar light works better.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
