"""Built-in K-50 four-season data calibrated from the KF style table.

The K-50 has no 0x021A/0x021B, like the K-30.  Its DNG ColorMatrix2
gives the same calibration as the K-3 (Y differs by 1.4e-5), so the
season matrices land within one Q13 LSB of the K-30 bundle.
Y = T(KF) * inv(T(K-50)), with T = diag(1/(CM2*W)) * CM2."""

__copyright__ = "Copyright © 2026 KimHoLau X deepseek harness"

from season_common import (BLOCK_SIZE, K30_SERIES_RECORDS, N_PARAMS,
                           REC_SIZE, TABLE_PARAMS)

MODEL = 'PENTAX K-50'
UNIQUE_MODEL = 'PENTAX K-50'
BLOCK_COUNT = 4
PRIV_ENDIAN = '>'

# Base colour matrix implied by the bundled season matrices (M = MKF * Y).
# It lets another body recalibrate these seasons if this module is used
# as a donor.
BASE_MATRIX = (12512, -4352, 32, -1728, 12832, -2912, 288, -3392, 11296)

RECORDS = dict(K30_SERIES_RECORDS)

MATRICES = {
    0: bytes.fromhex('346ff675f51cf32b40eaebebf74d084a2068'),
    1: bytes.fromhex('38fde783ff80f8e23c3eeae1047eec332f50'),
    2: bytes.fromhex('36cfe1f4073d02b51ff0fd5bff6103791d26'),
    3: bytes.fromhex('21bbff83fec2fc3f291cfaa5015003e01ad0'),
}
