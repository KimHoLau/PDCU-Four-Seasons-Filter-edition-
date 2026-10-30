# -*- coding: utf-8 -*-
"""PENTAX 固件容器工具（K-70 / KF 一代）

支持：
  info     读取外层头、解压信息、资源表
  extract  解压主固件镜像
  spoof    把固件外层机型号改成别的机型（默认 PENTAX K-70），并修复 SYSV 校验和
  verify   校验 SYSV 和、文件大小、压缩流

格式（逆向自 fwdc234b.bin / fwdc245b.bin）：
  0x0000  24B   机型字符串，如 "PENTAX K-70"
  0x0018  u32   产品/机型编号（K-70=0x024A，KF=0x026B）
  0x001C  u32   二级编号（K-70=0x13222，KF=0x132B8）
  0x0020  u32   文件总大小
  0x0024  u32   固定 2
  0x0028  u32   版本，低字节为主版本、次字节为次版本（0x0110=1.16, 0x0121=1.33）
  0x002C  u32   构建日期（0x140B=2020-11?，仅显示用）
  0x0034  u32   解压后镜像大小
  0x0040  u32   第一段镜像大小（= 解压大小 - 0x1000000）
  0x0048  u32   资源表偏移（0x800200）
  0x01F6  u16   压缩标志（非 0 表示压缩流）
  0x01FC  u32   魔数 0xA55A5AA5
  0x0200  压缩流：一串 [u16 块长][块数据][u16 0]，块长 0 表示结束
          块数据是 LZSS：每 16 项一个 u16 位图（MSB 在前），
            位=1 → 2 字节 (长度|偏移)：len=(b0&7)+3，len==10 时继续累加；
                                 offset=((b0&0xF8)<<5)|b1
            位=0 → 1 个原样字节
          特殊块长 0xE000 → 原样拷贝 0x6000 字节（K-70/KF 的机型相关块长）
  0x800200 资源表：u32 数量，随后每项 24B 名字 + u32 偏移 + u32 长度
  文件尾 16B: [产品编号 x2][0xA55A5AA5][0][u32]
  完整性：整个文件按小端 u32 求和必须为 0（SYSV checksum）
"""
import argparse
import os
import struct
import sys

HEADER_SIZE = 0x200
BLOCK_START = 0x200
COMPRESSED_SIGN = 0x1F6
MAGIC = 0xA55A5AA5
RAW_BLOCK_MARK = 0xE000
RAW_BLOCK_LEN = 0x6000
RESOURCE_OFFSET = 0x800200


def read_u32(buf, off, endian='<'):
    return struct.unpack_from(endian + 'I', buf, off)[0]


def cstring(buf, off, maxlen=256):
    end = buf.find(b'\0', off, off + maxlen)
    if end < 0:
        end = off + maxlen
    return buf[off:end].decode('latin1', 'replace')


def u32_sum(buf):
    n = len(buf) // 4 * 4
    s = 0
    for (v,) in struct.iter_unpack('<I', buf[:n]):
        s = (s + v) & 0xFFFFFFFF
    return s


def parse_header(buf):
    return {
        'model': cstring(buf, 0, 24),
        'product_code': read_u32(buf, 0x18),
        'code2': read_u32(buf, 0x1C),
        'file_size': read_u32(buf, 0x20),
        'flag24': read_u32(buf, 0x24),
        'version_raw': read_u32(buf, 0x28),
        'version': '%d.%02d' % ((read_u32(buf, 0x28) >> 8) & 0xFF, read_u32(buf, 0x28) & 0xFF),
        'build_date': read_u32(buf, 0x2C),
        'decompressed_size': read_u32(buf, 0x34),
        'first_image_size': read_u32(buf, 0x40),
        'resource_offset': read_u32(buf, 0x48),
        'reserved_4c': read_u32(buf, 0x4C),
        'compressed_flag': struct.unpack_from('>H', buf, COMPRESSED_SIGN)[0],
        'magic': read_u32(buf, 0x1FC),
        'compressed_len': read_u32(buf, 0xA0),
        'trailer': buf[-16:],
    }


def decompress(buf, verbose=False):
    out = bytearray()
    p = BLOCK_START
    blocks = 0
    raw_blocks = 0
    while True:
        if p + 2 > len(buf):
            raise ValueError('压缩流越界：0x%x' % p)
        blen = struct.unpack_from('>H', buf, p)[0]
        p += 2
        blocks += 1
        if blen == 0:
            break
        if blen == RAW_BLOCK_MARK:
            out += buf[p:p + RAW_BLOCK_LEN]
            p += RAW_BLOCK_LEN
            raw_blocks += 1
            continue
        if blen > 0x8000:
            raise ValueError('非法块长 0x%x @0x%x' % (blen, p - 2))
        decompress_block(buf, p, blen, out)
        p += blen
    return bytes(out), p, blocks, raw_blocks


def decompress_block(buf, src, blen, out):
    end = src + blen - 2
    mask = 0
    bitmap = 0
    while src < end:
        if mask == 0:
            bitmap = struct.unpack_from('>H', buf, src)[0]
            src += 2
            mask = 0x8000
            continue
        if bitmap & mask:
            b0 = buf[src]
            b1 = buf[src + 1]
            src += 2
            length = (b0 & 0x07) + 3
            if length == 10:
                while True:
                    v = buf[src]
                    src += 1
                    length += v
                    if v != 0xFF:
                        break
            offset = ((b0 & 0xF8) << 5) | b1
            if offset == 0 or offset > len(out):
                raise ValueError('非法回溯 offset=%d @0x%x' % (offset, src))
            base = len(out) - offset
            for i in range(length):
                out.append(out[base + i])
        else:
            out.append(buf[src])
            src += 1
        mask >>= 1
    if struct.unpack_from('>H', buf, src)[0] != 0:
        raise ValueError('块尾标记缺失 @0x%x' % src)


def list_resources(buf):
    off = RESOURCE_OFFSET
    n = read_u32(buf, off)
    res = []
    for i in range(n):
        p = off + 16 + 32 * i
        name = cstring(buf, p, 24)
        r_off = read_u32(buf, p + 24)
        r_len = read_u32(buf, p + 28)
        res.append((name, r_off, r_len))
    return res


def fix_checksum_inplace(data, spare_offset=0xB8):
    """就地调整一个保留字，使全文件 u32 小端和归零。返回调整前的和。"""
    s = u32_sum(bytes(data))
    if s:
        old = read_u32(bytes(data), spare_offset)
        struct.pack_into('<I', data, spare_offset, (old - s) & 0xFFFFFFFF)
    assert u32_sum(bytes(data)) == 0, '校验和修复失败'
    return s


def spoof_model(src_path, dst_path, new_model='PENTAX K-70', spare_offset=0xB8):
    data = bytearray(open(src_path, 'rb').read())
    old_model = cstring(bytes(data), 0, 24)
    if len(new_model.encode('latin1')) > 23:
        raise ValueError('机型名太长（最多 23 字节）')
    name = new_model.encode('latin1') + b'\0' * (24 - len(new_model))
    data[0:24] = name
    s = fix_checksum_inplace(data, spare_offset)
    open(dst_path, 'wb').write(bytes(data))
    return old_model, s


def verify(path):
    buf = open(path, 'rb').read()
    h = parse_header(buf)
    problems = []
    if h['file_size'] != len(buf):
        problems.append('头里的文件大小 0x%X != 实际 0x%X' % (h['file_size'], len(buf)))
    if u32_sum(buf) != 0:
        problems.append('SYSV 校验和不为 0（0x%08X）' % u32_sum(buf))
    if h['magic'] != MAGIC:
        problems.append('魔数不是 0xA55A5AA5')
    if h['compressed_flag'] == 0:
        problems.append('压缩标志为 0')
    out, end, blocks, raws = decompress(buf)
    if len(out) != h['decompressed_size']:
        problems.append('解压大小 0x%X != 头里 0x%X' % (len(out), h['decompressed_size']))
    if h['compressed_len'] != end - BLOCK_START:
        problems.append('压缩流长度 0x%X != 头里 0x%X' % (end - BLOCK_START, h['compressed_len']))
    return h, problems, (len(out), end, blocks, raws)


def main():
    ap = argparse.ArgumentParser(description='PENTAX 固件容器工具')
    sub = ap.add_subparsers(dest='cmd', required=True)

    p = sub.add_parser('info', help='查看头部与压缩信息')
    p.add_argument('firmware')

    p = sub.add_parser('extract', help='解压主镜像')
    p.add_argument('firmware')
    p.add_argument('-o', '--out')

    p = sub.add_parser('resources', help='列出资源表')
    p.add_argument('firmware')

    p = sub.add_parser('spoof', help='改外层机型号并修校验和')
    p.add_argument('firmware')
    p.add_argument('-o', '--out', required=True)
    p.add_argument('--model', default='PENTAX K-70')

    p = sub.add_parser('verify', help='校验')
    p.add_argument('firmware')

    a = ap.parse_args()
    if a.cmd == 'info':
        buf = open(a.firmware, 'rb').read()
        h = parse_header(buf)
        print('文件      :', a.firmware)
        print('大小      : 0x%X (%d)' % (len(buf), len(buf)))
        print('机型      : %r' % h['model'])
        print('产品编号  : 0x%04X' % h['product_code'])
        print('二级编号  : 0x%05X' % h['code2'])
        print('版本      : %s (raw 0x%08X)' % (h['version'], h['version_raw']))
        print('解压大小  : 0x%X' % h['decompressed_size'])
        print('压缩长度  : 0x%X' % h['compressed_len'])
        print('资源表    : 0x%X, %d 项' % (h['resource_offset'], read_u32(buf, RESOURCE_OFFSET)))
        print('SYSV 和   : 0x%08X' % u32_sum(buf))
        print('尾 16 字节:', h['trailer'].hex(' '))
    elif a.cmd == 'extract':
        buf = open(a.firmware, 'rb').read()
        out, end, blocks, raws = decompress(buf)
        dst = a.out or (os.path.splitext(a.firmware)[0] + '.dec.bin')
        open(dst, 'wb').write(out)
        print('解压 %d 字节，块 %d（原样块 %d），压缩流止于 0x%X -> %s'
              % (len(out), blocks, raws, end, dst))
    elif a.cmd == 'resources':
        buf = open(a.firmware, 'rb').read()
        for name, off, ln in list_resources(buf):
            print('%-40s 0x%08X %8d' % (name, off, ln))
    elif a.cmd == 'spoof':
        old, delta = spoof_model(a.firmware, a.out, a.model)
        print('机型 %r -> %r' % (old, a.model))
        print('补齐校验和写入 0xB8，原 delta 0x%08X' % delta)
        print('输出:', a.out)
    elif a.cmd == 'verify':
        h, problems, info = verify(a.firmware)
        print('机型 %r 版本 %s 解压 0x%X 块 %d 原样块 %d 压缩流止于 0x%X'
              % (h['model'], h['version'], info[0], info[2], info[3], info[1]))
        print('OK' if not problems else '\n'.join(problems))


if __name__ == '__main__':
    main()
