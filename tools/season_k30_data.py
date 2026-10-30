"""Built-in K-30 four-season data calibrated from the KF style table.

The K-30 has no 0x021A/0x021B, like the K-01 and K-50.  Its bundled
matrices use the same construction as those two bodies: read the body's
own DNG ColorMatrix2, form T = diag(1/(CM2*W)) * CM2 (D65), solve
Y = T(KF) * inv(T(K-30)), and write M(K-30 season) = M(KF season) * Y.
The K-30 ColorMatrix2 comes from sample/K30.DNG (firmware 1.06).
"""

__copyright__ = "Copyright © 2026 KimHoLau X deepseek harness"

from season_common import (BLOCK_SIZE, K30_SERIES_RECORDS, N_PARAMS,
                           REC_SIZE, TABLE_PARAMS)

MODEL = 'PENTAX K-30'
UNIQUE_MODEL = 'PENTAX K-30'
BLOCK_COUNT = 4
PRIV_ENDIAN = '>'

# Base colour matrix implied by the bundled season matrices (M = MKF * Y).
# At Q13 it quantises to exactly the K-3 base matrix, so these four seasons
# stay on the K-3 calibration line to the last LSB.
BASE_MATRIX = (12512, -4352, 32, -1728, 12832, -2912, 288, -3392, 11296)

RECORDS = dict(K30_SERIES_RECORDS)

MATRICES = {
    0: bytes.fromhex('346ff675f51cf32b40eaebebf74d084a2069'),
    1: bytes.fromhex('38fde783ff80f8e23c3eeae1047eec322f50'),
    2: bytes.fromhex('36d0e1f4073d02b51ff0fd5bff6103791d26'),
    3: bytes.fromhex('21bbff83fec2fc3f291cfaa5015003e01ad0'),
}
