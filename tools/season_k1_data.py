"""Built-in K-1 four-season data extracted from sample/IMGP0709.DNG."""

__copyright__ = "Copyright © 2026 KimHoLau X deepseek harness"

MODEL = 'PENTAX K-1'
UNIQUE_MODEL = 'PENTAX K-1'
N_PARAMS = 12
REC_SIZE = 26
BLOCK_SIZE = 18
BLOCK_COUNT = 27
PRIV_ENDIAN = '<'

# Mode-0 colour matrix of the body these season matrices are calibrated on
# (9 x Q13 ints).  Lets the tool recalibrate them for another body.
BASE_MATRIX = (12032, -3872, 32, -1856, 12576, -2528, 288, -3392, 11296)

# K-1 ColorMatrix2 (DNG 0xC622, 3x3 floats).  Only used by the tool's
# base-vs-CM2 sanity check.
CM2 = (0.856583, -0.274551, -0.120148,
       -0.361176, 1.220398, 0.154984,
       -0.089325, 0.168030, 0.626404)

RECORDS = {
    29: bytes.fromhex('1d00010002000300ffffffffffff00000000feff040016000000'),
    30: bytes.fromhex('1e000100080004000100ffffffff00000300fdffffff17000000'),
    31: bytes.fromhex('1f000100040001000100ffffffffffff0000ffffffff18000000'),
    32: bytes.fromhex('20000100080004000100ffffffff0300fcff0400ffff19000000'),
}

MATRICES = {
    22: bytes.fromhex('523263f84bf5b9f2853fc2ed6cf7ad07e720'),
    23: bytes.fromhex('e136c9e956ff44f81e3b9eec710466ec292f'),
    24: bytes.fromhex('dc3434e4f0061002801f70fe3bff39038c1d'),
    25: bytes.fromhex('41209f0020ffbefb5328effb1501b1033a1b'),
}
