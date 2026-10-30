"""Built-in Q7 four-season data calibrated from the KF style table.

The Q7 (1/1.7" sensor) has no 0x021A/0x021B and stores its private
block little-endian.  Its ColorMatrix2 differs a lot from the SLR
bodies, so the KF season style is calibrated through
Y = T(KF) * inv(T(Q7)), T = diag(1/(CM2*W)) * CM2.  This is the same
construction used for the K-01; it is an inference, not official
Pentax season data for the Q7."""

__copyright__ = "Copyright © 2026 KimHoLau X deepseek harness"

MODEL = 'PENTAX Q7'
UNIQUE_MODEL = 'PENTAX Q7'
N_PARAMS = 12
REC_SIZE = 26
BLOCK_SIZE = 18
BLOCK_COUNT = 4
PRIV_ENDIAN = '<'

# Base colour matrix implied by the bundled season matrices (M = MKF * Y).
# It lets another body recalibrate these seasons if this module is used
# as a donor.
BASE_MATRIX = (11268, -856, -2220, -2319, 14321, -3810, -79, -4295, 12565)

TABLE_PARAMS = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 128, 129]

RECORDS = {
    29: bytes.fromhex('1d00010002000300ffffffffffff00000000feff040000000000'),
    30: bytes.fromhex('1e000100080004000100ffffffff00000300fdffffff01000000'),
    31: bytes.fromhex('1f000100040001000100ffffffffffff0000ffffffff02000000'),
    32: bytes.fromhex('20000100080004000100ffffffff0300fcff0400ffff03000000'),
}

MATRICES = {
    0: bytes.fromhex('242fe506f7e9f9f05147b6e719f64205a524'),
    1: bytes.fromhex('b433c2f68af55ff6e243c0e5f602aae86134'),
    2: bytes.fromhex('d0314eefe2fe1f00c6251bfab1fd8902c61f'),
    3: bytes.fromhex('9b1db10ab4f7edf94c2ec6f779ffbe03c91c'),
}
