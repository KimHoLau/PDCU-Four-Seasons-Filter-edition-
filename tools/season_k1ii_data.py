"""Built-in K-1 Mark II four-season data (the K-1's native season table).

The K-1 Mark II (2018) uses the same 36.4 MP sensor and colour filter as the
K-1, and its private block carries the same 28 mode records and the same 21
3x3 matrices: every one of the 21 matrices in sample/K1ii.dng is
byte-identical to sample/K1.dng, and both DNG ColorMatrix2 values imply the
same input calibration to 2.1e-05.  The four native K-1 season matrices are
therefore an exact transplant for the K-1 Mark II (Y = I), not an
approximation.

The K-1 Mark II private block is 160,372 B (496 B larger than the K-1's) and
its 0x021A keeps the same 390-byte reserved tail, so the rebuilt 32-record
table still fits in place; 0x021B then moves into the freed tail directly
after the new table because only two bytes separate the old matrix table
from 0x021C.  Preview, raw pixels and every other tag are left untouched.
"""

__copyright__ = "Copyright © 2026 KimHoLau X deepseek harness"

# The season records and matrices are the K-1's native values.  Importing
# them keeps the two bundles from drifting apart; the K-1 Mark II writes the
# exact same bytes for all 28 modes and all 21 base matrices.
from season_k1_data import (  # noqa: F401
    BLOCK_COUNT,
    MATRICES,
    PRIV_ENDIAN,
    RECORDS,
)
from season_common import BLOCK_SIZE, N_PARAMS, REC_SIZE, TABLE_PARAMS

MODEL = 'PENTAX K-1 Mark II'
UNIQUE_MODEL = 'PENTAX K-1 Mark II'

# Mode-0 colour matrix of the K-1 Mark II (9 x Q13 ints).  It is byte-identical
# to the K-1's, so the bundled season matrices need no run-time recalibration.
BASE_MATRIX = (12032, -3872, 32, -1856, 12576, -2528, 288, -3392, 11296)

# K-1 Mark II ColorMatrix2 (DNG 0xC622, 3x3 floats).  Only used by the tool's
# base-vs-CM2 sanity check; it matches the K-1's implied calibration to
# 2.1e-05.
CM2 = (0.893494, -0.286377, -0.125320,
       -0.361176, 1.220398, 0.154984,
       -0.090485, 0.170227, 0.634583)
