"""Shared layout constants and record sets for the bundled season tables.

Every built-in donor is a 12-parameter / 26-byte `_PEF_MODEPRM_SET` record
table with 18-byte 3x3 color matrices.  Keeping the layout and the identical
K-30-series record bytes here means a data module only carries what makes it
different: its model name, byte order, matrix count and matrices.
"""

__copyright__ = "Copyright © 2026 KimHoLau X deepseek harness"

N_PARAMS = 12
REC_SIZE = 26
BLOCK_SIZE = 18
TABLE_PARAMS = (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 128, 129)

# K-30 / K-01 / K-50 write the same four season records, in the same big-endian
# byte order.  The matrix index is parameter 128, renumbered to 0..3.
K30_SERIES_RECORDS = {
    29: bytes.fromhex('001d000100020003ffffffffffff00000000fffe000400000000'),
    30: bytes.fromhex('001e0001000800040001ffffffff00000003fffdffff00010000'),
    31: bytes.fromhex('001f0001000400010001ffffffffffff0000ffffffff00020000'),
    32: bytes.fromhex('00200001000800040001ffffffff0003fffc0004ffff00030000'),
}

# Q7 / MX-1 use the same little-endian records as each other.
Q7_MX1_RECORDS = {
    29: bytes.fromhex('1d00010002000300ffffffffffff00000000feff040000000000'),
    30: bytes.fromhex('1e000100080004000100ffffffff00000300fdffffff01000000'),
    31: bytes.fromhex('1f000100040001000100ffffffffffff0000ffffffff02000000'),
    32: bytes.fromhex('20000100080004000100ffffffff0300fcff0400ffff03000000'),
}
