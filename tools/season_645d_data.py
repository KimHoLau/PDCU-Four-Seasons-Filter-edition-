"""Built-in 645D four-season data calibrated from the KF style table.

The 645D (2010) writes 0x021A/0x021B, but with an older layout than the
K-3/KF generation: nParams is 11 instead of 12, records are 24 bytes
instead of 26, and the table is packed (no 390-byte reserve after the
records).  PDCU 5.10.2.2 only offers the four seasons when the table uses
the 12-parameter, 26-byte layout, so this bundle is written that way: the
645D's own records are re-encoded with the extra parameter 10 slot,
and the four season records are the KF ones.

Its 0x021B base matrix and its DNG ColorMatrix2 (0xC622) agree to 4e-5,
so Y = inv(M(KF)[0]) * M(645D)[0] is the body's input calibration and
M(645D season) = M(KF season) * Y is the exact transplant: the relative
season style R = M * inv(M_base) is unchanged.  BASE_MATRIX below is the
645D mode-0 matrix, so a 645D target needs no run-time recalibration.

Record parameter 10 does not exist in the camera's own table; the tool
writes the "unset" value 0xFFFF for it.  Measured in PDCU: 0xFFFF and 0
render identically for the existing modes.
"""

__copyright__ = "Copyright © 2026 KimHoLau X deepseek harness"

from season_common import BLOCK_SIZE, N_PARAMS, REC_SIZE, TABLE_PARAMS

MODEL = 'PENTAX 645D'
UNIQUE_MODEL = 'PENTAX 645D'
BLOCK_COUNT = 4
PRIV_ENDIAN = '>'

# Mode-0 colour matrix of the 645D (9 x Q13 ints).  Because the bundled
# season matrices are already expressed in the 645D colour space, a 645D
# target needs no run-time recalibration; another body would get Y from
# this base.
BASE_MATRIX = (12556, -4344, -20, -1407, 11584, -1985, 326, -5836, 13702)

# 645D ColorMatrix2 (DNG 0xC622, 3x3 floats).  Only used by the tool's
# base-vs-CM2 sanity check; it agrees with BASE_MATRIX to 4.0e-05.
CM2 = (0.954895, -0.264297, -0.140045,
       -0.504913, 1.390701, 0.116577,
       -0.183914, 0.385498, 0.573364)

# KF season records in the 645D byte order, with param 128 (the 0x021B
# matrix index) renumbered to this bundle's 0..3.
RECORDS = {
    29: bytes.fromhex('001d000100020003ffffffffffff00000000fffe000400000000'),
    30: bytes.fromhex('001e0001000800040001ffffffff00000003fffdffff00010000'),
    31: bytes.fromhex('001f0001000400010001ffffffffffff0000ffffffff00020000'),
    32: bytes.fromhex('00200001000800040001ffffffff0003fffc0004ffff00030000'),
}

# M(KF season) * Y, quantised to Q13 in the 645D's big-endian byte order.
MATRICES = {
    0: bytes.fromhex('34bef7f9f349f4ad3c3eef15f7d0fed72959'),
    1: bytes.fromhex('390be87dfe78fa51384ced640487e2b338c6'),
    2: bytes.fromhex('36c3e1ec075103a81b39011fffd2fb3a24f4'),
    3: bytes.fromhex('222bfe08ffcefd5923f6feb101c3fc12222a'),
}
