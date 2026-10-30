"""Built-in MX-1 four-season data calibrated from the KF style table.

The MX-1 (2013, 1/1.7" compact) writes no 0x021A/0x021B at all, like the
K-30 / K-01 / K-50 / Q7, and its private block is little-endian.  Its DNG
ColorMatrix2 (0xC622) differs substantially from the SLR bodies: the
implied input calibration Y differs from the K-3's by 1.0e-01 (Q7 differs
by 3.7e-01), so the KF season style is calibrated through
Y = T(KF) * inv(T(MX-1)), T = diag(1/(CM2*W)) * CM2.  This is the same
construction used for the K-01 / K-50 / Q7; it is an inference, not
official Pentax season data for the MX-1.

The MX-1 private block is only 51,458 B and has 82 IFD entries; adding the
two tags relocates 0x0222 and puts the records/matrices in the free run
after the single preview JPEG (0xBBB6 / 0xBC3A in sample/MX1.dng).
"""

__copyright__ = "Copyright © 2026 KimHoLau X deepseek harness"

from season_common import (BLOCK_SIZE, N_PARAMS, Q7_MX1_RECORDS, REC_SIZE,
                           TABLE_PARAMS)

MODEL = 'PENTAX MX-1'
UNIQUE_MODEL = 'PENTAX MX-1'
BLOCK_COUNT = 4
PRIV_ENDIAN = '<'

# Base colour matrix implied by the bundled season matrices (M = MKF * Y).
# It lets another body recalibrate these seasons if this module is used
# as a donor.  The MX-1 itself has no 0x021B table to compare it against.
BASE_MATRIX = (12993, -4641, -160, -2624, 12738, -1921, 384, -4289, 12096)

# MX-1 ColorMatrix2 (DNG 0xC622, 3x3 floats).  Only used by the tool's
# base-vs-CM2 sanity check, and it is the source of the calibration above.
CM2 = (0.880447, -0.252304, -0.123764,
       -0.242310, 1.162735, 0.085953,
       -0.068161, 0.177353, 0.475311)

# KF season records in the MX-1 byte order, with param 128 (the 0x021B
# matrix index) renumbered to this bundle's 0..3.
RECORDS = dict(Q7_MX1_RECORDS)

# M(KF season) * Y, quantised to Q13 in the MX-1's little-endian byte order.
MATRICES = {
    0: bytes.fromhex('fa35f1f516f4a7ee0b414ef02bf677055e24'),
    1: bytes.fromhex('843b67e615fecaf46b3ccbee560582e82832'),
    2: bytes.fromhex('9a396ae0fd058300101f6d00bdfed1007220'),
    3: bytes.fromhex('3f227dfe44ff59f9652842feb4005801f41d'),
}
