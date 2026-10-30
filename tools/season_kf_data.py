"""Built-in KF four-season data extracted from sample/KF.DNG."""

__copyright__ = "Copyright © 2026 KimHoLau X deepseek harness"

from season_common import BLOCK_SIZE, N_PARAMS, REC_SIZE

MODEL = 'PENTAX KF'
UNIQUE_MODEL = 'PENTAX KF'
BLOCK_COUNT = 27
PRIV_ENDIAN = '<'

# Mode-0 colour matrix of the body these season matrices are calibrated on
# (9 x Q13 ints).  Lets the tool recalibrate them for another body.
BASE_MATRIX = (12800, -5248, 640, -1664, 12256, -2400, 320, -3648, 11520)

# KF ColorMatrix2 (DNG 0xC622, 3x3 floats).  Only used by the tool's
# base-vs-CM2 sanity check.
CM2 = (0.82346, -0.21082, -0.12932,
       -0.43587, 1.29533, 0.15146,
       -0.10701, 0.19185, 0.59303)

RECORDS = {
    0: bytes.fromhex('00000100010001000100ffffffff000000000000ffff00000000'),
    1: bytes.fromhex('01000100040004000100ffffffff000000000000ffff01000000'),
    16: bytes.fromhex('10000100010001000100ffffffff000000000000ffff02000000'),
    17: bytes.fromhex('11000100040004000100ffffffff000000000000ffff03000000'),
    18: bytes.fromhex('12000100010001000100ffffffff000000000000ffff04000000'),
    20: bytes.fromhex('1400010005000000ffffffffffff040000000000000005000000'),
    23: bytes.fromhex('1700ffffffff0100ffffffffffff000000000000ffff06000100'),
    24: bytes.fromhex('1800010008000300fffffffffffffcff00000000010007000000'),
    25: bytes.fromhex('19000100060004000100ffffffff020000000000ffff08000000'),
    27: bytes.fromhex('1b000100070001000100ffffffff000000000000ffff0a000000'),
    19: bytes.fromhex('1300ffff01000100ffff00000400000000000000ffff0b000000'),
    2: bytes.fromhex('02000100010001000100ffffffff000000000000ffff02000000'),
    3: bytes.fromhex('03000100040004000100ffffffff000000000000ffff03000000'),
    4: bytes.fromhex('04000100010001000100ffffffff000000000000ffff00000000'),
    5: bytes.fromhex('05000100010004000100ffffffff000000000000ffff01000000'),
    6: bytes.fromhex('06000100010001000100ffffffff000000000000ffff02000000'),
    7: bytes.fromhex('07000100010004000100ffffffff000000000000ffff01000000'),
    8: bytes.fromhex('08000100040004000100ffffffff000000000000ffff01000000'),
    9: bytes.fromhex('09000100020006000100ffffffff000000000000ffff01000000'),
    10: bytes.fromhex('0a000100040004000100ffffffff000000000000ffff01000000'),
    11: bytes.fromhex('0b000100040004000100ffffffff000000000000ffff02000000'),
    12: bytes.fromhex('0c000100040004000100ffffffff000000000000ffff01000000'),
    13: bytes.fromhex('0d000100040004000100ffffffff000000000000ffff01000000'),
    14: bytes.fromhex('0e000100010001000100ffffffff000000000000ffff00000000'),
    15: bytes.fromhex('0f000100040004000100ffffffff000000000000ffff01000000'),
    21: bytes.fromhex('15000100040004000400ffffffff000000000000ffff03000000'),
    22: bytes.fromhex('16000100040004000100ffffffff000000000000ffff01000000'),
    26: bytes.fromhex('1a000200010001000100ffffffff000000000000ffff04000000'),
    28: bytes.fromhex('1c000100020001000100ffffffff000000000000ffff15000000'),
    29: bytes.fromhex('1d00010002000300ffffffffffff00000000feff040016000000'),
    30: bytes.fromhex('1e000100080004000100ffffffff00000300fdffffff17000000'),
    31: bytes.fromhex('1f000100040001000100ffffffffffff0000ffffffff18000000'),
    32: bytes.fromhex('20000100080004000100ffffffff0300fcff0400ffff19000000'),
    33: bytes.fromhex('21000100010005000100ffffffff000000000000ffff1a000000'),
}

MATRICES = {
    0: bytes.fromhex('003280eb800280f9e02fa0f64001c0f1002d'),
    1: bytes.fromhex('ff374eeab3fd59f8433864ef84ff25ed5733'),
    2: bytes.fromhex('8e3231ec410107f52c38cdf2a2fe9df7c129'),
    3: bytes.fromhex('833963e81afe9df6fe3a65eeb2fcb1ea9d38'),
    4: bytes.fromhex('c54040e1fbfdb8f6aa419ee798fe86f3e22d'),
    5: bytes.fromhex('632382fa1b027efbee2894fb94ffaafdc222'),
    6: bytes.fromhex('b033fce65405f9fa98316ff33f01c8ebf932'),
    7: bytes.fromhex('351b7f074cfd46fea72113002e07ccff0619'),
    8: bytes.fromhex('823b65e2190231ed894646ecb8f52dd11b59'),
    9: bytes.fromhex('003280eb800280f9e02fa0f64001c0f1002d'),
    10: bytes.fromhex('2032fcebe401b0fd662beaf6a90204f3532a'),
    11: bytes.fromhex('003280eb800280f9e02fa0f64001c0f1002d'),
    12: bytes.fromhex('5f0b46145b005f0b46145b005f0b46145b00'),
    13: bytes.fromhex('58030c209cfc58030c209cfc58030c209cfc'),
    14: bytes.fromhex('c00d401300ffc00d401300ffc00d401300ff'),
    15: bytes.fromhex('df2122fcff01df2122fcff01df2122fcff01'),
    16: bytes.fromhex('b4286cf2e004b4286cf2e004b4286cf2e004'),
    17: bytes.fromhex('de1b30fcf207de1b30fcf207de1b30fcf207'),
    18: bytes.fromhex('f5f9a4036722f6f9a3036722f6f9a4036622'),
    19: bytes.fromhex('66fa2612741366fa2612741366fa26127413'),
    20: bytes.fromhex('f11fa62669d9f11fa62669d9f11fa62669d9'),
    21: bytes.fromhex('fd2a0cf5f7ff1c02621f82fe91042dfd421e'),
    22: bytes.fromhex('ab3591f2c4f75cf39a3e0aee51f741076e21'),
    23: bytes.fromhex('403ac5e3fb012cf9be3916eda80430eb2830'),
    24: bytes.fromhex('00387ade86091303a81d45ff8bff2002551e'),
    25: bytes.fromhex('9c2266fcfe0085fcef268cfc85016902121c'),
    26: bytes.fromhex('ec2ec5ee4f02f8f8982e70f8faff38f3ce2c'),
}
