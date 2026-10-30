#!/usr/bin/env python3
r"""Add missing Pentax four-season mode records to a DNG.

PDCU decides whether the HARUBENI / KATEN / KYUSHU / FUYUNO entries appear in
the "Custom Image" menu by scanning the Pentax private IFD tag 0x021A
(_PEF_MODEPRM_SET table).  A DNG that was shot without the extra season
records only has one of them, so PDCU only offers that one mode.

Each 26-byte record also contains a matrix index (the last-but-one u16).
That index selects an 18-byte 3x3 color matrix in tag 0x021B.  A camera that
only shot one season writes only that one matrix; copying just the 0x021A
records would make the new modes point at the wrong matrices (or out of
range), which produces wrong colors and wrong radar charts.

This tool copies both the missing 26-byte records and their 3x3 matrices from
a donor DNG, remaps the matrix indices, updates both tag counts/lengths, and
verifies the result.  It normally appends records and matrices into the unused
gaps directly after 0x021A and 0x021B.

A donor from another body is calibrated into the target's colour space
whenever both sides have a 0x021B matrix table: the tool reads each body's
mode-0 matrix and applies Y = inv(M_donor[0]) * M_target[0] to every copied
season matrix.  Pentax builds its per-body tables exactly this way (the same
style table times one input calibration), so this is an exact transplant, not
an approximation.  The style tables are compared first; when they do not look
like the same table the tool asks for --allow-cross-model (and says so).

PENTAX KF and K-70 share the identical 21 base matrices, so Y is the identity
there; K-3, K-3 II, K-5 II, K-5 II s and 645Z share the KF style table but
differ by Y, which makes a KF donor exact for them too.  The K-1 Mark II
carries the same 28 mode records and 21 base matrices as the K-1, so the K-1's
native season table is its exact built-in source (Y = I).  Bodies without any
0x021B table (K-30, K-01, K-50, Q7) keep using bundled tables that were
calibrated offline from each body's own DNG ColorMatrix2.

PENTAX K-30 / K-01 / K-50 / Q7 / MX-1 have no 0x021A/0x021B in their
private blocks; K-30, K-01 and K-50 store those blocks big-endian, the Q7
and MX-1 store theirs little-endian.  --builtin k30 / k01 / k50 / q7 / mx1
add both tags, relocate the small tags that sit under the expanded IFD,
convert the season records and matrices to the target byte order, and use a
target color-space calibration derived from the target DNG ColorMatrix2.

PENTAX 645D does have 0x021A/0x021B, but in an older shape: 11 parameters per
record (24 bytes) instead of 12 (26 bytes), big-endian, and the record table
is packed, so it has to move into free space when it grows.  PDCU 5.10.2.2
only lists the four seasons for the 12-parameter layout, so the tool rebuilds
the whole table in that layout (existing records keep every field they had;
the missing parameter 10 slot is written as 0xFFFF).  --builtin 645d carries
the 645D-calibrated season matrices.

Older K-1 firmware (for example v1.50) may reserve a padded 0x021A block and
leave no gap after 0x021B.  In that case the tool treats the trailing 0x021A
bytes as reserved and relocates the whole 0x021B matrix table to a safe free
area inside the private block, updating its offset/length.  Preview images,
other tags and raw pixels are never changed.

Examples
--------
    python tools/dng_season_params.py --target sample\IMGP0719_KYUSHU.DNG \
        --donor sample\IMGP0709.DNG --out out.dng

    # inspect only
    python tools/dng_season_params.py --target sample\IMGP0719_KYUSHU.DNG --list

    # dry run
    python tools/dng_season_params.py --target sample\IMGP0719_KYUSHU.DNG \
        --donor sample\IMGP0709.DNG --out out.dng --dry-run

The tool does not execute the DNG and does not need ExifTool.
"""
from __future__ import annotations

__copyright__ = "Copyright © 2026 KimHoLau X deepseek harness"

import argparse
import os
import shutil
import struct
import sys
import time

import dng_report
import season_645d_data
import season_k01_data
import season_k1_data
import season_k1ii_data
import season_k30_data
import season_k50_data
import season_kf_data
import season_mx1_data
import season_q7_data

SEASON_NAMES = {
    0x1D: "HARUBENI",
    0x1E: "KATEN",
    0x1F: "KYUSHU",
    0x20: "FUYUNO",
}
SEASON_IDS = tuple(SEASON_NAMES)

# Camera model pairs that share the same base 0x021B color matrices.  KF and
# K-70 use an identical 21-matrix base; KF only appends six extra modes and
# calibrates them on that same base.  A donor from one is therefore an exact
# match for the other, not an experimental cross-model approximation.
COMPATIBLE_MODEL_PAIRS = {
    frozenset(("PENTAX KF", "PENTAX K-70")),
}

# One registry for every model -> built-in donor decision.  The GUI's source
# rows, its automatic selection, the worker and the hidden selftest entry all
# read this table instead of keeping their own if/elif ladders.
MODEL_TO_DONOR_KIND = {
    "PENTAX K-1": "k1",
    "PENTAX K-1 Mark II": "k1ii",
    "PENTAX KF": "kf",
    "PENTAX K-70": "kf",
    "PENTAX K-3": "kf",
    "PENTAX K-3 II": "kf",
    "PENTAX K-5 II": "kf",
    "PENTAX K-5 II s": "kf",
    "PENTAX 645Z": "kf",
    "PENTAX KP": "kf",
    "PENTAX K-S2": "kf",
    "PENTAX 645D": "645d",
    "PENTAX K-30": "k30",
    "PENTAX K-01": "k01",
    "PENTAX K-50": "k50",
    "PENTAX Q7": "q7",
    "PENTAX MX-1": "mx1",
}


class BuiltinSource:
    """A GUI source row: label, donor kinds, and exact GUI log line."""

    def __init__(self, key, label, kinds, log_text):
        self.key = key
        self.label = label
        self.kinds = tuple(kinds)
        self.log_text = log_text

    def __repr__(self):
        return "BuiltinSource(%r, %r)" % (self.key, self.label)


CUSTOM_DONOR_MODE = "file"

BUILTIN_SOURCES = {
    "builtin": BuiltinSource(
        "builtin", "内置 K-1 / K-1 Mark II", ("k1", "k1ii"),
        "季节来源：内置 K-1 / K-1 Mark II 四季参数"),
    "builtin_kf": BuiltinSource(
        "builtin_kf", "内置 KF / K-70", ("kf",),
        "季节来源：内置 KF / K-70 四季参数"),
    "builtin_645d": BuiltinSource(
        "builtin_645d", "内置 645D", ("645d",),
        "季节来源：内置 645D 四季参数"),
    "builtin_k30": BuiltinSource(
        "builtin_k30", "内置 K-30 系列", ("k30", "k01", "k50", "q7", "mx1"),
        "季节来源：内置 K-30 系列四季参数"),
}
BUILTIN_SOURCE_MODELS = {
    source.key: frozenset(
        model for model, kind in MODEL_TO_DONOR_KIND.items()
        if kind in source.kinds
    )
    for source in BUILTIN_SOURCES.values()
}

# Automatic selection keeps the old family boundaries: a batch that mixes KF
# with a calibrated K-3 body is deliberately left to the user instead of being
# silently collapsed into the wider "KF / K-70" source.
AUTO_SELECT_GROUPS = (
    ("builtin", frozenset(("PENTAX K-1", "PENTAX K-1 Mark II"))),
    ("builtin_kf", frozenset(("PENTAX KF", "PENTAX K-70"))),
    ("builtin_k30", frozenset(("PENTAX K-30", "PENTAX K-01", "PENTAX K-50",
                               "PENTAX Q7", "PENTAX MX-1"))),
    ("builtin_645d", frozenset(("PENTAX 645D",))),
    ("builtin_kf", frozenset(("PENTAX K-3", "PENTAX K-3 II", "PENTAX K-5 II",
                              "PENTAX K-5 II s", "PENTAX 645Z", "PENTAX KP",
                              "PENTAX K-S2"))),
)

# Hidden build-test switches.  --selftest-cross is the K-1 donor with the
# cross-model opt-in and is not a donor selector itself.
SELFTEST_DONOR_FLAGS = {
    "--selftest": "k1",
    "--selftest-k1ii": "k1ii",
    "--selftest-kf": "kf",
    "--selftest-645d": "645d",
    "--selftest-k30": "k30",
    "--selftest-k01": "k01",
    "--selftest-k50": "k50",
    "--selftest-q7": "q7",
    "--selftest-mx1": "mx1",
}
SELFTEST_FLAGS = tuple(SELFTEST_DONOR_FLAGS) + ("--selftest-cross",)


def donor_kind_for_model(model):
    """The bundled donor kind for a camera body, or None when unknown."""
    return MODEL_TO_DONOR_KIND.get((model or "").strip())


def source_for_models(models):
    """The one source that can auto-serve a whole batch, or None.

    Mixed families (for example KF + K-3) intentionally return None: the old
    GUI asked the user to split the batch, and that choice is preserved.
    """
    models = frozenset((model or "").strip() for model in models)
    if not models or "" in models:
        return None
    for source_key, group in AUTO_SELECT_GROUPS:
        if models <= group:
            return BUILTIN_SOURCES[source_key]
    return None


def builtin_source_allows(source, model):
    """True when a built-in GUI source is allowed for this camera body."""
    model = (model or "").strip()
    allowed = BUILTIN_SOURCE_MODELS.get(source)
    return bool(model and allowed and model in allowed)


def selftest_donor_kind(argv):
    """Map the hidden --selftest flag to its bundled donor kind."""
    for flag, kind in SELFTEST_DONOR_FLAGS.items():
        if flag in argv:
            return kind
    return None

# KF / K-1 share this _PEF_MODEPRM_SET parameter id list.  It is only used
# when a target has no 0x021A table yet; existing tables keep their own.
DEFAULT_TABLE_PARAMS = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 128, 129]


def _convert_matrix(raw, src_endian, dst_endian):
    """Rebuild an 18-byte 3x3 int16 matrix for a new byte order."""
    if src_endian == dst_endian:
        return bytes(raw)
    values = struct.unpack_from(src_endian + "9h", raw, 0)
    return struct.pack(dst_endian + "9h", *values)


def models_compatible(target_model, donor_model):
    """Return True when two model names are known to share the base matrices."""
    target = (target_model or "").strip()
    donor = (donor_model or "").strip()
    if not target or not donor:
        return False
    if target == donor:
        return True
    return frozenset((target, donor)) in COMPATIBLE_MODEL_PAIRS


TYPE_SIZES = {
    1: 1, 2: 1, 3: 2, 4: 4, 5: 8, 6: 1, 7: 1,
    8: 2, 9: 4, 10: 8, 11: 4, 12: 8, 13: 4,
}


class DngError(Exception):
    pass


def _u16(buf, off, endian):
    if off < 0 or off + 2 > len(buf):
        raise DngError("u16 read outside file at 0x%X" % off)
    return struct.unpack_from(endian + "H", buf, off)[0]


def _u32(buf, off, endian):
    if off < 0 or off + 4 > len(buf):
        raise DngError("u32 read outside file at 0x%X" % off)
    return struct.unpack_from(endian + "I", buf, off)[0]


def _cstring(buf, off, size):
    raw = bytes(buf[off:off + size])
    return raw.split(b"\0", 1)[0].decode("ascii", "replace").strip()


def _align_up(value, alignment):
    if alignment <= 1:
        return value
    return (value + alignment - 1) // alignment * alignment


# ---------------------------------------------------------------------------
# Colour-space calibration
#
# Pentax writes each body's 0x021B table as the *same* style table times one
# 3x3 input calibration Y:  M(target) = M(donor) * Y, with
# Y = inv(M_donor[mode 0]) * M_target[mode 0].  A transplanted season matrix
# therefore has to be expressed in the target's colour space:
#
#     M_target_season = M_donor_season * inv(M_donor_base) * M_target_base
#
# which keeps the season style R = M_season * inv(M_base) exactly equal to the
# donor's while landing in the target's space.  Some bodies (K-3, K-3 II,
# K-5 II, K-5 II s, 645Z, ...) share the style table and differ only by Y, so
# this turns a cross-model copy into an exact transplant.
# ---------------------------------------------------------------------------

Q13 = 8192.0
# Median per-mode |R_target - R_donor| accepted as "same style table".
STYLE_TOLERANCE = 3.0e-3
# |Y - I| below this means no recalibration is needed (identical base).
IDENTITY_TOLERANCE = 2.0e-4

# D65 white point used by the ColorMatrix2 cross-check.
D65_WHITE = (0.95047, 1.0, 1.08883)
# A 0x021B base matrix and the body's own ColorMatrix2 normally imply the same
# Y to <=2e-5 (K-3, K-3 II, K-70, KP).  645Z and K-S2 are the known outliers
# (2.6e-3 and 1.3e-2); above this the tool prints a warning but still trusts
# the 0x021B table, which is what PDCU actually multiplies.
CM2_TOLERANCE = 1.0e-3


def _mat_rows(values):
    return [list(values[0:3]), list(values[3:6]), list(values[6:9])]


def _mat_mul(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)]
            for i in range(3)]


def _mat_inv(m):
    a, b, c = m[0]
    d, e, f = m[1]
    g, h, i = m[2]
    det = a * (e * i - f * h) - b * (d * i - f * g) + c * (d * h - e * g)
    if abs(det) < 1e-12:
        raise DngError("singular 3x3 matrix in colour calibration")
    return [
        [(e * i - f * h) / det, (c * h - b * i) / det, (b * f - c * e) / det],
        [(f * g - d * i) / det, (a * i - c * g) / det, (c * d - a * f) / det],
        [(d * h - e * g) / det, (b * g - a * h) / det, (a * e - b * d) / det],
    ]


def _cm2_transform(cm):
    """DNG ColorMatrix2 -> D65 input transform diag(1/(CM2*W)) * CM2."""
    rows = [list(row) for row in cm]
    scale = [row[0] * D65_WHITE[0] + row[1] * D65_WHITE[1]
             + row[2] * D65_WHITE[2] for row in rows]
    if any(abs(s) < 1e-9 for s in scale):
        return None
    return [[row[j] / scale[i] for j in range(3)]
            for i, row in enumerate(rows)]


def _mat_decode(raw, endian):
    """18-byte Q13 matrix -> 3x3 floats."""
    return _mat_rows([v / Q13 for v in struct.unpack(endian + "9h", bytes(raw))])


def _mat_encode(m, endian):
    """3x3 floats -> 18-byte Q13 matrix, clipped to int16."""
    vals = []
    for row in m:
        for v in row:
            q = int(round(v * Q13))
            vals.append(-32768 if q < -32768 else (32767 if q > 32767 else q))
    return struct.pack(endian + "9h", *vals)


def _mat_maxdiff(a, b):
    return max(abs(a[i][j] - b[i][j]) for i in range(3) for j in range(3))


def _mat_identity(m):
    return _mat_maxdiff(m, [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]])


def _base_matrix(holder):
    """The mode-0 3x3 of a DNG or a builtin donor, or None."""
    baked = getattr(holder, "base_matrix", None)
    if baked:
        return _mat_rows([v / Q13 for v in baked])
    record = getattr(holder, "record", None)
    if record is None:
        return None
    rec = record(0)
    if rec is None:
        return None
    blocks = getattr(holder, "blocks", None) or []
    idx = holder.record_block_index(rec)
    if not 0 <= idx < len(blocks) or len(blocks[idx]) != 18:
        return None
    return _mat_decode(blocks[idx], holder.priv_endian)


def _holder_cm2(holder):
    """ColorMatrix2 of a Dng or a DonorData, or None."""
    cm2 = getattr(holder, "cm2", None)
    if cm2 is None:
        cm2 = getattr(holder, "color_matrix2", None)
    return cm2


def plan_calibration(target, donor):
    """Work out the donor -> target colour calibration.

    Returns None when it cannot be computed (no mode-0 matrix on either side),
    otherwise a dict describing Y and how well the two style tables agree.
    When both sides expose a DNG ColorMatrix2, the dict also carries a
    "cm2" sub-dict comparing that route's Y with the 0x021B one.
    """
    donor_base = _base_matrix(donor)
    target_base = _base_matrix(target)
    if donor_base is None or target_base is None:
        return None
    y = _mat_mul(_mat_inv(donor_base), target_base)

    target_recs = {r["id"]: r for r in (getattr(target, "records", None) or [])}
    donor_recs = {r["id"]: r for r in (getattr(donor, "records", None) or [])}
    t_blocks = getattr(target, "blocks", None) or []
    d_blocks = getattr(donor, "blocks", None) or []

    t_inv = _mat_inv(target_base)
    d_inv = _mat_inv(donor_base)
    deltas = []
    for rid in sorted(set(target_recs) & set(donor_recs)):
        ti = target.record_block_index(target_recs[rid])
        di = donor.record_block_index(donor_recs[rid])
        if not (0 <= ti < len(t_blocks) and 0 <= di < len(d_blocks)):
            continue
        if len(t_blocks[ti]) != 18 or len(d_blocks[di]) != 18:
            continue
        r_target = _mat_mul(_mat_decode(t_blocks[ti], target.priv_endian), t_inv)
        r_donor = _mat_mul(_mat_decode(d_blocks[di], donor.priv_endian), d_inv)
        deltas.append(_mat_maxdiff(r_target, r_donor))

    delta_sorted = sorted(deltas)
    median = delta_sorted[len(delta_sorted) // 2] if delta_sorted else None

    # Cross-check: the target's own ColorMatrix2 should imply the same Y that
    # its 0x021B base matrix does.  Both are per-body data, so a large gap
    # means the two disagree (645Z / K-S2 are the known cases).  The 0x021B
    # table still wins, because that is what PDCU multiplies.
    cm2 = None
    target_cm2 = _holder_cm2(target)
    donor_cm2 = _holder_cm2(donor)
    if target_cm2 is not None and donor_cm2 is not None:
        t_cm2 = _cm2_transform(target_cm2)
        d_cm2 = _cm2_transform(donor_cm2)
        if t_cm2 is not None and d_cm2 is not None:
            try:
                y_cm2 = _mat_mul(d_cm2, _mat_inv(t_cm2))
            except DngError:
                y_cm2 = None
            if y_cm2 is not None:
                cm2_delta = _mat_maxdiff(y, y_cm2)
                cm2 = {
                    "y": y_cm2,
                    "delta": cm2_delta,
                    "ok": cm2_delta <= CM2_TOLERANCE,
                }

    return {
        "y": y,
        "cm2": cm2,
        "donor_base": donor_base,
        "target_base": target_base,
        "modes": len(deltas),
        "style_median": median,
        "style_max": max(deltas) if deltas else None,
        "style_known": bool(deltas),
        "style_ok": bool(deltas) and median is not None and median <= STYLE_TOLERANCE,
        "trusted": bool(getattr(donor, "trusted", False)),
        "identity": _mat_identity(y) <= IDENTITY_TOLERANCE,
    }


def calibration_allows_cross(calibration):
    """True when the calibration proves the transplant is safe."""
    if calibration is None:
        return False
    if calibration["style_ok"]:
        return True
    return calibration["trusted"] and not calibration["style_known"]


def describe_cm2(cal):
    """Backwards-compatible wrapper around the reporter."""
    return dng_report.describe_cm2(cal)


def describe_calibration(cal):
    """Backwards-compatible wrapper around the reporter."""
    return dng_report.describe_calibration(cal)


def check_cross_model(target, donor, allow_cross_model, calibration):
    """Return (compatible_pair, calibrated_cross, error_message)."""
    donor_model = getattr(donor, "model", "")
    if not target.model or not donor_model or target.model == donor_model:
        return False, False, None
    if models_compatible(target.model, donor_model):
        return True, False, None
    if allow_cross_model:
        return False, False, None
    if calibration_allows_cross(calibration):
        return False, True, None
    return (False, False,
            "camera model mismatch: target %r, donor %r "
            "(use a donor of the same model)" % (target.model, donor_model))


def parse_ifd(buf, off, endian, base=0, limit=None):
    """Parse a normal TIFF IFD.  Returns {tag: entry}."""
    n = _u16(buf, off, endian)
    entries = {}
    for i in range(n):
        eoff = off + 2 + i * 12
        tag = _u16(buf, eoff, endian)
        typ = _u16(buf, eoff + 2, endian)
        cnt = _u32(buf, eoff + 4, endian)
        if typ not in TYPE_SIZES:
            raise DngError("unsupported TIFF type %d for tag 0x%04X" % (typ, tag))
        size = TYPE_SIZES[typ] * cnt
        if size <= 4:
            voff = eoff + 8
            inline = True
        else:
            voff = _u32(buf, eoff + 8, endian) + base
            inline = False
        if limit is not None and (voff < limit[0] or voff + size > limit[1]):
            raise DngError("tag 0x%04X data outside private block" % tag)
        entries[tag] = {
            "tag": tag,
            "type": typ,
            "count": cnt,
            "size": size,
            "entry_off": eoff,
            "value_off": voff,
            "inline": inline,
        }
    return entries


class Dng:
    """Minimal read-only view of a Pentax DNG."""

    def __init__(self, path, data=None):
        self.path = path
        self.data = bytearray(open(path, "rb").read()) if data is None else bytearray(data)
        if self.data[:2] not in (b"II", b"MM"):
            raise DngError("%s: not a TIFF/DNG file" % path)
        self.endian = "<" if self.data[:2] == b"II" else ">"
        if _u16(self.data, 2, self.endian) != 42:
            raise DngError("%s: bad TIFF magic" % path)
        self.ifd0_off = _u32(self.data, 4, self.endian)
        self.ifd0 = parse_ifd(self.data, self.ifd0_off, self.endian)
        self.model = self._ifd0_string(0x0110)
        self.unique_model = self._ifd0_string(0xC614)
        # Pentax stores its maker note in two different containers:
        #   * camera DNGs: IFD0 tag 0xC634 (DNGPrivateData), header "PENTAX \0",
        #     tag data offsets are relative to the block start;
        #   * DNGs written by Digital Camera Utility 5: EXIF tag 0x927C
        #     (MakerNote), header "AOC\0", tag data offsets are absolute.
        # Both use the same private IFD layout after the 8/12-byte header.
        self.private_entry = self.ifd0.get(0xC634)
        self.makernote_entry = None
        self.container = "private"
        if self.private_entry is not None and self.private_entry["size"] > 4:
            self.priv_off = self.private_entry["value_off"]
            self.priv_len = self.private_entry["size"]
            self.priv_header_len = 12
            self.priv_dir_off = self.priv_off + 12
            self.priv_count_off = self.priv_off + 10
            self.priv_abs = False
        else:
            exif_entry = self.ifd0.get(0x8769)
            exif_ifd = {}
            if exif_entry is not None:
                exif_off = _u32(self.data, exif_entry["value_off"], self.endian)
                if exif_off:
                    exif_ifd = parse_ifd(self.data, exif_off, self.endian)
            mn = exif_ifd.get(0x927C)
            if mn is None or mn["size"] <= 4:
                raise DngError(
                    "%s: DNGPrivateData (tag 0xC634) / EXIF MakerNote "
                    "(tag 0x927C) not found" % path)
            self.container = "makernote"
            self.makernote_entry = mn
            self.priv_off = mn["value_off"]
            self.priv_len = mn["size"]
            self.priv_header_len = 8
            self.priv_dir_off = self.priv_off + 8
            self.priv_count_off = self.priv_off + 6
            self.priv_abs = True
        self.priv_end = self.priv_off + self.priv_len
        if self.priv_off < 0 or self.priv_end > len(self.data):
            raise DngError("%s: private block exceeds file size" % path)
        if self.container == "private":
            if bytes(self.data[self.priv_off:self.priv_off + 8]) != b"PENTAX \0":
                raise DngError("%s: private block is not a PENTAX block" % path)
            inner_bo = bytes(self.data[self.priv_off + 8:self.priv_off + 10])
        else:
            if bytes(self.data[self.priv_off:self.priv_off + 4]) != b"AOC\0":
                raise DngError("%s: EXIF MakerNote is not a Pentax AOC block" % path)
            inner_bo = bytes(self.data[self.priv_off + 4:self.priv_off + 6])
        if inner_bo not in (b"II", b"MM"):
            raise DngError("%s: bad PENTAX private byte order" % path)
        self.priv_endian = "<" if inner_bo == b"II" else ">"
        self.priv_entries = self._parse_private_entries()
        self.table_entry = self.priv_entries.get(0x021A)
        self.blocks_entry = self.priv_entries.get(0x021B)
        self.has_mode_table = (self.table_entry is not None
                               and self.table_entry["size"] > 4)
        self.has_matrix_table = (self.blocks_entry is not None
                                 and self.blocks_entry["size"] > 4)

        # K-30-era bodies do not write 0x021A/0x021B at all.  Keep a
        # zero-record view so callers can tell "no season data" from a
        # malformed table and add both tags later.
        if self.has_mode_table:
            self.table_off = self.table_entry["value_off"]
            self.table_len = self.table_entry["size"]
            self.table = bytes(self.data[self.table_off:self.table_off + self.table_len])
            self._parse_table()
        else:
            self.table_off = 0
            self.table_len = 0
            self.table = b""
            self.n_params = 12
            self.n_records = 0
            self.rec_size = 26
            self.nrec_off = 2 + 2 * self.n_params
            self.rec_start = self.nrec_off + 2
            self.table_data_len = 0
            self.table_padding = 0
            self.records = []
            self.index_offset = self.rec_size - 4

        if self.has_matrix_table:
            self._parse_blocks()
        else:
            self.blocks_off = 0
            self.blocks_len = 0
            self.block_count = 0
            self.block_size = 18
            self.blocks = []

    def _ifd0_string(self, tag):
        e = self.ifd0.get(tag)
        if e is None:
            return ""
        return _cstring(self.data, e["value_off"], e["size"])

    def _parse_private_entries(self):
        n = _u16(self.data, self.priv_count_off, self.priv_endian)
        entries = {}
        for i in range(n):
            eoff = self.priv_dir_off + i * 12
            tag = _u16(self.data, eoff, self.priv_endian)
            typ = _u16(self.data, eoff + 2, self.priv_endian)
            cnt = _u32(self.data, eoff + 4, self.priv_endian)
            if typ not in TYPE_SIZES:
                raise DngError("unsupported private type %d for tag 0x%04X" % (typ, tag))
            size = TYPE_SIZES[typ] * cnt
            if size <= 4:
                voff = eoff + 8
                inline = True
                rel = None
            else:
                value = _u32(self.data, eoff + 8, self.priv_endian)
                voff = value if self.priv_abs else self.priv_off + value
                rel = voff - self.priv_off
                inline = False
            if size > 4 and (voff < self.priv_off or voff + size > self.priv_end):
                raise DngError("private tag 0x%04X data outside block" % tag)
            entries[tag] = {
                "tag": tag,
                "type": typ,
                "count": cnt,
                "size": size,
                "entry_off": eoff,
                "value_off": voff,
                "rel_off": rel,
                "inline": inline,
            }
        return entries

    def _parse_table(self):
        t = self.table
        if len(t) < 4:
            raise DngError("mode table too short")
        self.n_params = _u16(t, 0, self.priv_endian)
        self.nrec_off = 2 + 2 * self.n_params
        if self.nrec_off + 2 > len(t):
            raise DngError("mode table header truncated")
        self.n_records = _u16(t, self.nrec_off, self.priv_endian)
        self.rec_start = self.nrec_off + 2
        body = len(t) - self.rec_start
        # A record is one u16 mode id plus one u16 per parameter.  Some
        # firmware revisions reserve a fixed-size 0x021A block and leave
        # 0xFF padding after the last record, so the tag length can be much
        # larger than nRecords * recordSize.  Prefer the structurally exact
        # size first, then fall back to the historical "tag body divided by
        # count" rule for tables that are packed exactly.
        expected_rec_size = 2 * (self.n_params + 1)
        if self.n_records:
            if body % self.n_records == 0:
                self.rec_size = body // self.n_records
            elif body >= self.n_records * expected_rec_size:
                self.rec_size = expected_rec_size
            else:
                raise DngError(
                    "mode table size %d cannot hold %d records of %d bytes"
                    % (body, self.n_records, expected_rec_size)
                )
        else:
            self.rec_size = 0
        self.table_data_len = self.rec_start + self.n_records * self.rec_size
        self.table_padding = len(t) - self.table_data_len
        if self.table_padding < 0:
            raise DngError("mode table records exceed tag length")
        self.records = []
        for i in range(self.n_records):
            off = self.rec_start + i * self.rec_size
            rec = bytes(t[off:off + self.rec_size])
            rid = _u16(rec, 0, self.priv_endian)
            self.records.append({"id": rid, "bytes": rec, "off": off})

    def _parse_blocks(self):
        """Parse 0x021B: u32 count + count x 18-byte color matrices."""
        e = self.priv_entries.get(0x021B)
        if e is None or e["size"] < 4:
            raise DngError("%s: Pentax color-matrix table 0x021B not found" % self.path)
        self.blocks_entry = e
        self.blocks_off = e["value_off"]
        self.blocks_len = e["size"]
        raw = bytes(self.data[self.blocks_off:self.blocks_off + self.blocks_len])
        self.block_count = _u32(raw, 0, self.priv_endian)
        if self.block_count <= 0:
            raise DngError("%s: 0x021B has no matrices" % self.path)
        if (self.blocks_len - 4) % self.block_count != 0:
            raise DngError(
                "%s: 0x021B size %d is not 4 + %d x N"
                % (self.path, self.blocks_len, self.block_count)
            )
        self.block_size = (self.blocks_len - 4) // self.block_count
        self.blocks = [
            raw[4 + i * self.block_size:4 + (i + 1) * self.block_size]
            for i in range(self.block_count)
        ]
        # Last-but-one u16 of a _PEF_MODEPRM_SET is the matrix index.
        self.index_offset = self.rec_size - 4
        if self.index_offset < 0:
            raise DngError("%s: mode record too short" % self.path)

    def record_block_index(self, rec):
        return _u16(rec["bytes"], self.index_offset, self.priv_endian)

    @property
    def ids(self):
        return [r["id"] for r in self.records]

    @property
    def seasons(self):
        return [i for i in self.ids if i in SEASON_NAMES]

    @property
    def missing(self):
        have = set(self.ids)
        return [i for i in SEASON_IDS if i not in have]

    @property
    def color_matrix2(self):
        """DNG ColorMatrix2 (tag 0xC622) as a 3x3 list, or None."""
        if hasattr(self, "_cm2_cache"):
            return self._cm2_cache
        self._cm2_cache = None
        entry = self.ifd0.get(0xC622)
        if entry is not None and entry["type"] in (5, 10) and entry["count"] == 9:
            try:
                values = []
                for i in range(9):
                    num, den = struct.unpack_from(
                        self.endian + "ii", self.data,
                        entry["value_off"] + 8 * i)
                    values.append(num / den if den else 0.0)
                self._cm2_cache = _mat_rows(values)
            except struct.error:
                self._cm2_cache = None
        return self._cm2_cache

    def record(self, rid):
        for r in self.records:
            if r["id"] == rid:
                return r
        return None

    @property
    def table_params(self):
        """The 0x021A parameter-id list, or the default when there is none.

        645D-era layout: 11 ids (1-9, 128, 129).  KF/K-3-era layout: 12 ids
        (1-10, 128, 129).  A donor record can only be written into a target
        whose list is a subset of the donor's.
        """
        if not self.has_mode_table:
            return list(DEFAULT_TABLE_PARAMS)
        return list(struct.unpack_from(
            self.priv_endian + "%dH" % self.n_params, self.table, 2))

    def describe(self):
        """Return the inspection report; never writes to stdout."""
        return dng_report.describe_dng(self, SEASON_NAMES)

    def preview_jpeg(self):
        """Embedded Pentax private-block JPEG preview, or None."""
        try:
            ranges = self._precise_preview_ranges()
        except Exception:
            return None
        for start, end, _label in ranges:
            raw = bytes(self.data[start:end])
            if raw.startswith(b"\xff\xd8") and raw.rstrip().endswith(b"\xff\xd9"):
                return raw
        return None

    def next_used_start(self, tag):
        """First private-block data range that starts at/after the given tag."""
        entry = self.priv_entries[tag]
        end = entry["value_off"] + entry["size"]
        candidates = []
        # Header + private IFD + entries (+ next-IFD pointer, if present).
        ifd_end = self.priv_off + self.priv_header_len + len(self.priv_entries) * 12 + 4
        if ifd_end >= end:
            candidates.append(ifd_end)
        for t, e in self.priv_entries.items():
            if t == tag or e["inline"]:
                continue
            start = e["value_off"]
            range_end = start + e["size"]
            if start < end < range_end:
                raise DngError(
                    "private tag 0x%04X overlaps tag 0x%04X" % (t, tag)
                )
            if start >= end:
                candidates.append(start)
        # Preview image referenced by tags 0x0003 (length) / 0x0004 (offset).
        p_len_e = self.priv_entries.get(0x0003)
        p_off_e = self.priv_entries.get(0x0004)
        if p_len_e and p_off_e and p_len_e["size"] == 4 and p_off_e["size"] == 4:
            p_len = _u32(self.data, p_len_e["value_off"], self.priv_endian)
            p_off = _u32(self.data, p_off_e["value_off"], self.priv_endian)
            start = p_off if self.priv_abs else self.priv_off + p_off
            range_end = start + p_len
            if start < end < range_end:
                raise DngError("preview image overlaps tag 0x%04X" % tag)
            if start >= end:
                candidates.append(start)
        return min(candidates) if candidates else self.priv_end

    def _preview_start(self):
        """Conservative start of the preview/thumbnail tail, if present."""
        len_entry = self.priv_entries.get(0x0003)
        if len_entry is None or len_entry["size"] != 4:
            return None
        starts = []
        for tag in (0x0004, 0x0005):
            e = self.priv_entries.get(tag)
            if e is not None and e["size"] == 4:
                off = _u32(self.data, e["value_off"], self.priv_endian)
                start = off if self.priv_abs else self.priv_off + off
                if self.priv_off <= start < self.priv_end:
                    starts.append(start)
        return min(starts) if starts else None

    def _precise_preview_ranges(self, exclude_tags=()):
        """Preview ranges measured from the JPEG markers and 0x0003 length.

        K-30 leaves a large 0xFF gap after its only JPEG preview.  Treating
        the whole tail as used would needlessly reject that space.
        """
        ranges = []
        len_entry = self.priv_entries.get(0x0003)
        length = None
        if len_entry is not None and len_entry["size"] == 4:
            length = _u32(self.data, len_entry["value_off"], self.priv_endian)
        for tag in (0x0004, 0x0005):
            e = self.priv_entries.get(tag)
            if e is None or e["size"] != 4:
                continue
            value = _u32(self.data, e["value_off"], self.priv_endian)
            start = value if self.priv_abs else self.priv_off + value
            if start < self.priv_off or start >= self.priv_end:
                continue
            if (bytes(self.data[start:start + 2]) == b"\xff\xd8"
                    and length):
                ranges.append((start, min(start + length, self.priv_end),
                               "preview 0x%04X" % tag))
            else:
                # Unknown/secondary offset: reserve a small guard area only.
                ranges.append((start, min(start + 64, self.priv_end),
                               "preview guard 0x%04X" % tag))
        return ranges

    def private_used_ranges(self, exclude_tags=(), precise_previews=False):
        """Data ranges owned by private tags, plus preview data.

        By default the tail from the first preview/thumbnail offset to the end
        of the block is treated as used.  precise_previews=True measures the
        actual JPEG length instead, which is required for K-30.
        """
        ranges = []
        # Header, private IFD entries and the next-IFD pointer are live data.
        ifd_end = self.priv_off + self.priv_header_len + len(self.priv_entries) * 12 + 4
        ranges.append((self.priv_off, min(ifd_end, self.priv_end),
                       "private IFD"))
        for tag, e in self.priv_entries.items():
            if tag in exclude_tags or e["inline"]:
                continue
            ranges.append((e["value_off"], e["value_off"] + e["size"],
                           "tag 0x%04X" % tag))
        if precise_previews:
            ranges.extend(self._precise_preview_ranges(exclude_tags))
        else:
            preview = self._preview_start()
            if preview is not None and preview < self.priv_end:
                ranges.append((preview, self.priv_end, "preview"))
        ranges.sort(key=lambda r: (r[0], r[1]))
        return ranges

    def range_conflicts(self, start, length, *, exclude_tags=(),
                        extra_ranges=(), precise_previews=False):
        end = start + length
        if start < self.priv_off or end > self.priv_end:
            return True
        ranges = (self.private_used_ranges(exclude_tags, precise_previews)
                  + list(extra_ranges))
        for r in ranges:
            if start < r[1] and r[0] < end:
                return True
        return False

    def find_free_space(self, length, *, exclude_tags=(), extra_ranges=(),
                        preferred=None, align=2, precise_previews=False):
        """Find a non-overlapping range inside the private block.

        The caller may exclude 0x021A/0x021B because those ranges are being
        rewritten/moved, and pass the new 0x021A range in extra_ranges.
        """
        def fits(start):
            return not self.range_conflicts(
                start, length, exclude_tags=exclude_tags,
                extra_ranges=extra_ranges,
                precise_previews=precise_previews)

        if preferred is not None:
            start = _align_up(preferred, align)
            if fits(start):
                return start

        ranges = sorted(self.private_used_ranges(exclude_tags, precise_previews)
                        + list(extra_ranges), key=lambda r: (r[0], r[1]))
        cursor = self.priv_off
        for start, end, _label in ranges:
            if end <= cursor:
                continue
            if start > cursor:
                candidate = _align_up(cursor, align)
                if candidate + length <= start and fits(candidate):
                    return candidate
            if end > cursor:
                cursor = end

        candidate = _align_up(cursor, align)
        if candidate + length <= self.priv_end and fits(candidate):
            return candidate
        return None


def plan_add_private_tags(target, table, blocks, added):
    """Plan adding 0x021A/0x021B to a private IFD that has neither.

    K-30's 100-entry IFD ends exactly where its data begins.  Two new
    entries need 24 bytes, so the first 0x0200/0x0201/0x0205 values are
    relocated to a free gap and the IFD is rebuilt in place.  New tag data
    also goes into that gap.
    """
    entries = sorted(target.priv_entries.values(), key=lambda e: e["tag"])
    new_count = len(entries) + 2
    new_ifd_end = target.priv_off + 12 + new_count * 12 + 4

    relocate = [
        e for e in entries
        if e["size"] > 4 and e["value_off"] < new_ifd_end
    ]
    total = len(table) + len(blocks) + sum(e["size"] for e in relocate)
    if total:
        total += 2 * (len(relocate) + 2)
    exclude_tags = tuple(e["tag"] for e in relocate)
    start = target.find_free_space(
        total,
        exclude_tags=exclude_tags,
        extra_ranges=((target.priv_off, new_ifd_end, "new private IFD"),),
        precise_previews=True,
        align=2,
    )
    if start is None:
        raise DngError(
            "not enough free space to add 0x021A/0x021B: need %d bytes "
            "in the private block" % total)

    cursor = start
    relocated = {}
    for e in relocate:
        raw = bytes(target.data[e["value_off"]:e["value_off"] + e["size"]])
        relocated[e["tag"]] = (cursor - target.priv_off, raw)
        cursor = _align_up(cursor + e["size"], 2)
    table_rel = cursor - target.priv_off
    cursor += len(table)
    cursor = _align_up(cursor, 2)
    blocks_rel = cursor - target.priv_off
    cursor += len(blocks)

    new_entries = []
    for e in entries:
        ent = dict(e)
        if e["tag"] in relocated:
            ent["rel_off"] = relocated[e["tag"]][0]
        new_entries.append(ent)

    for ent in (
        {
            "tag": 0x021A, "type": 7, "count": len(table),
            "size": len(table), "rel_off": table_rel, "inline": False,
        },
        {
            "tag": 0x021B, "type": 7, "count": len(blocks),
            "size": len(blocks), "rel_off": blocks_rel, "inline": False,
        },
    ):
        pos = next((i for i, e in enumerate(new_entries)
                    if e["tag"] > ent["tag"]), len(new_entries))
        new_entries.insert(pos, ent)

    inline_values = {}
    for e in entries:
        if e["inline"]:
            inline_values[e["tag"]] = bytes(
                target.data[e["entry_off"] + 8:e["entry_off"] + 12])

    return {
        "kind": "add_tags",
        "new_table": table,
        "nrec": _u16(table, target.nrec_off, target.priv_endian),
        "added": added,
        "new_block_count": _u32(blocks, 0, target.priv_endian),
        "new_blocks_len": len(blocks),
        "new_matrix_table": blocks,
        "new_entries": new_entries,
        "new_entry_count": len(new_entries),
        "relocated": relocated,
        "inline_values": inline_values,
        "table_off": target.priv_off + table_rel,
        "new_table_off": target.priv_off + table_rel,
        "table_relocated": True,
        "blocks_off": target.priv_off + blocks_rel,
        "new_blocks_off": target.priv_off + blocks_rel,
        "blocks_relocated": True,
        "table_growth": len(table),
        "need": len(table),
        "table_gap": 0,
    }


class DonorData:
    """A donor's season records + 3x3 matrices, without a full DNG file."""

    def __init__(self, model, n_params, rec_size, block_size, block_count,
                 priv_endian, records, matrices, unique_model="",
                 table_params=None, base_matrix=None, cm2=None):
        self.model = model
        self.unique_model = unique_model
        self.n_params = n_params
        self.rec_size = rec_size
        self.block_size = block_size
        self.block_count = block_count
        self.priv_endian = priv_endian
        self.table_params = (list(table_params) if table_params is not None
                             else list(DEFAULT_TABLE_PARAMS))
        self.records = [{"id": rid, "bytes": bytes(rec)}
                        for rid, rec in sorted(records.items())]
        self.blocks = [bytes(matrices.get(i, b"")) for i in range(block_count)]
        # Mode-0 colour matrix of the body these season matrices were
        # calibrated on (9 Q13 ints).  Used for target-side recalibration.
        self.base_matrix = tuple(base_matrix) if base_matrix else None
        # DNG ColorMatrix2 of the body this bundle was built for, when known.
        # Used only for the base-vs-CM2 sanity check in plan_calibration().
        self.cm2 = _mat_rows(cm2) if cm2 else None
        # Bundled tables come from real Pentax data, so their style is known
        # even when they carry no mode-0 record to compare against.
        self.trusted = False

    def record(self, rid):
        for r in self.records:
            if r["id"] == rid:
                return r
        return None

    def record_block_index(self, rec):
        return _u16(rec["bytes"], self.rec_size - 4, self.priv_endian)


_BUILTIN_DATA_MODULES = {
    "k1": season_k1_data,
    "k1ii": season_k1ii_data,
    "kf": season_kf_data,
    "645d": season_645d_data,
    "k30": season_k30_data,
    "k01": season_k01_data,
    "k50": season_k50_data,
    "q7": season_q7_data,
    "mx1": season_mx1_data,
}
BUILTIN_DONOR_KINDS = tuple(_BUILTIN_DATA_MODULES)


def builtin_donor(kind):
    """Build a DonorData from one of the bundled season tables."""
    data = _BUILTIN_DATA_MODULES.get(kind)
    if data is None:
        raise DngError("unknown built-in donor %r" % kind)
    donor = DonorData(
        data.MODEL,
        data.N_PARAMS,
        data.REC_SIZE,
        data.BLOCK_SIZE,
        data.BLOCK_COUNT,
        data.PRIV_ENDIAN,
        data.RECORDS,
        data.MATRICES,
        data.UNIQUE_MODEL,
        getattr(data, "TABLE_PARAMS", None),
        getattr(data, "BASE_MATRIX", None),
        getattr(data, "CM2", None),
    )
    donor.trusted = True
    return donor


def _param_ids(holder):
    """The 0x021A parameter ids of a DNG or a built-in donor."""
    params = getattr(holder, "table_params", None)
    if params:
        return list(params)
    return list(DEFAULT_TABLE_PARAMS)


def project_record(raw, src_params, src_endian, dst_params, dst_endian,
                   fill=0xFFFF):
    """Re-encode one 0x021A record for another parameter list.

    The 645D writes 11 parameter slots (1-9, 128, 129) where the newer bodies
    write 12 (1-10, 128, 129).  PDCU only recognises the four seasons in the
    12-slot layout, so a 645D table is rebuilt with the extra slot filled by
    'fill' (0xFFFF, the "unset" value these tables use).  Selecting by
    parameter id keeps every other slot in place instead of shifting it; the
    mode id and the matrix index (param 128) keep their meaning.
    """
    words = struct.unpack(src_endian + "%dH" % (len(raw) // 2), bytes(raw))
    if len(words) != len(src_params) + 1:
        raise DngError(
            "record has %d parameters, expected %d for tag 0x021A"
            % (len(words) - 1, len(src_params)))
    by_id = dict(zip(src_params, words[1:]))
    out = [words[0]]
    for pid in dst_params:
        out.append(by_id[pid] if pid in by_id else fill)
    return struct.pack(dst_endian + "%dH" % len(out), *out)


def trim_record_padding(raw, n_params):
    """Drop reserved padding after a record's real parameter words."""
    want = 2 * (n_params + 1)
    if len(raw) <= want:
        return bytes(raw)
    extra = bytes(raw[want:])
    if any(b not in (0x00, 0xFF) for b in extra):
        raise DngError(
            "a 0x021A record has %d bytes of non-padding data after its %d "
            "parameters; refusing to truncate it" % (len(extra), n_params))
    return bytes(raw[:want])


def plan_record_layout(target, donor):
    """Parameter list / record size the rebuilt 0x021A table has to use.

    A body whose parameter list is a subset of the donor's (645D: 11 of the
    12 KF slots) adopts the donor's list, which is the layout PDCU needs to
    list the four seasons.  Slots the body never had are written as 0xFFFF in
    its existing records.  Returns (param ids, record size, index offset).
    """
    donor_params = _param_ids(donor)
    if target.has_mode_table:
        target_params = _param_ids(target)
        expected = 2 * (len(target_params) + 1)
        if target.rec_size != expected:
            raise DngError(
                "unexpected 0x021A record size %d for %d parameters "
                "(expected %d)" % (target.rec_size, len(target_params), expected))
        if set(target_params) <= set(donor_params):
            params = list(donor_params)
        elif set(donor_params) <= set(target_params):
            params = list(target_params)
        else:
            raise DngError(
                "the donor and this body use different 0x021A parameter "
                "lists (%s vs %s)" % (donor_params, target_params))
    else:
        if len(donor_params) != target.n_params:
            raise DngError(
                "donor parameter count %d does not match target %d"
                % (len(donor_params), target.n_params))
        params = list(donor_params)
    rec_size = 2 * (len(params) + 1)
    return params, rec_size, rec_size - 4


def build_new_table(target, donor, missing, xform=None):
    """Return (new 0x021A bytes, nRecords, added, layout info).

    xform, when given, is a 3x3 float matrix applied to every copied season
    matrix (donor space -> target space) before it is quantised and packed.

    Every record - the body's own ones as well as the transplanted ones - is
    re-encoded for the selected parameter layout, so a 645D table is upgraded
    from 24-byte to 26-byte records in the same step.
    """
    target_endian = target.priv_endian
    donor_endian = donor.priv_endian
    target_params = _param_ids(target)
    donor_params = _param_ids(donor)
    params, rec_size, index_offset = plan_record_layout(target, donor)

    new_records = []
    for r in target.records:
        src = trim_record_padding(r["bytes"], len(target_params))
        raw = project_record(src, target_params, target_endian,
                             params, target_endian)
        new_records.append({"id": r["id"], "bytes": raw})
    added = []
    for rid in missing:
        src = donor.record(rid)
        if src is None:
            raise DngError("donor has no record for mode %d (%s)"
                           % (rid, SEASON_NAMES[rid]))
        rec = project_record(trim_record_padding(src["bytes"], len(donor_params)),
                             donor_params, donor_endian, params, target_endian)
        if len(rec) != rec_size:
            raise DngError(
                "record size mismatch: target %d, donor %d after conversion"
                % (rec_size, len(rec))
            )
        donor_idx = donor.record_block_index(src)
        if donor_idx >= donor.block_count:
            raise DngError(
                "donor record %d points to matrix #%d, but donor only has %d"
                % (rid, donor_idx, donor.block_count)
            )
        matrix = donor.blocks[donor_idx]
        if len(matrix) != target.block_size:
            raise DngError(
                "matrix size mismatch: target %d, donor %d"
                % (target.block_size, len(matrix))
            )
        # K-30 stores its private block big-endian while KF/K-70 and K-1
        # store theirs little-endian.  The record above is already packed in
        # the target's byte order; the matrix is re-encoded here.
        if xform is None:
            matrix = _convert_matrix(matrix, donor_endian, target_endian)
        else:
            # Decode in the donor's byte order, calibrate, re-encode for the
            # target's byte order in one step.
            matrix = _mat_encode(
                _mat_mul(_mat_decode(matrix, donor_endian), xform),
                target_endian)
        new_idx = target.block_count + len(added)
        rec = bytearray(rec)
        struct.pack_into(target_endian + "H", rec, index_offset, new_idx)
        added.append((new_idx, matrix))
        pos = len(new_records)
        for i, r in enumerate(new_records):
            if r["id"] > rid:
                pos = i
                break
        new_records.insert(pos, {"id": rid, "bytes": bytes(rec)})
    nrec = len(new_records)
    header = (
        struct.pack(target_endian + "H", len(params))
        + struct.pack(target_endian + "%dH" % len(params), *params)
        + struct.pack(target_endian + "H", nrec)
    )
    info = {
        "n_params": len(params),
        "rec_size": rec_size,
        "index_offset": index_offset,
        "nrec_off": 2 + 2 * len(params),
        "params": list(params),
        "layout_upgraded": bool(target.has_mode_table
                                and list(params) != target_params),
    }
    return header + b"".join(r["bytes"] for r in new_records), nrec, added, info

def plan_patch(target, donor, missing, xform=None):
    """Compute the 0x021A/0x021B rewrite plan without touching the file."""
    new_table, nrec, added, info = build_new_table(target, donor, missing, xform)

    if target.has_mode_table and not target.has_matrix_table:
        raise DngError(
            "target has a 0x021A mode table but no 0x021B matrix table; "
            "refusing to guess where to put the season matrices")

    if not target.has_mode_table:
        if getattr(target, "container", "private") == "makernote":
            raise DngError(
                "EXIF MakerNote without 0x021A/0x021B is not supported yet; "
                "this path only handles MakerNotes that already carry both tags")
        new_block_count = target.block_count + len(added)
        new_matrix_table = (
            struct.pack(target.priv_endian + "I", new_block_count)
            + b"".join(target.blocks)
            + b"".join(matrix for _idx, matrix in added)
        )
        plan = plan_add_private_tags(target, new_table, new_matrix_table, added)
        plan.update(info)
        plan["xform"] = xform
        return plan

    table_old_end = target.table_off + target.table_len
    table_growth = len(new_table) - target.table_len
    need = max(0, table_growth)
    table_next = target.next_used_start(0x021A)
    table_gap = table_next - table_old_end

    new_block_count = target.block_count + len(added)
    new_blocks_len = 4 + new_block_count * target.block_size
    new_matrix_table = (
        struct.pack(target.priv_endian + "I", new_block_count)
        + b"".join(target.blocks)
        + b"".join(matrix for _idx, matrix in added)
    )

    blocks_old_end = target.blocks_off + target.blocks_len
    blocks_next = target.next_used_start(0x021B)
    blocks_gap = blocks_next - blocks_old_end
    block_need = target.block_size * len(added)
    blocks_in_place = blocks_gap >= block_need

    # 0x021A usually keeps a reserve after its records, so growing it writes
    # into that reserve and the tag even shrinks.  When the table is packed
    # (645D: 602 B with a 2 B gap before 0x021B) it has to move instead: the
    # grown table and, if 0x021B cannot grow in place either, both tables are
    # put into one contiguous free run inside the private block.
    table_relocated = need > table_gap
    new_table_off = target.table_off
    new_blocks_off = target.blocks_off
    if table_relocated:
        reserve_blocks = not blocks_in_place
        length = len(new_table) + (2 + new_blocks_len if reserve_blocks else 0)
        exclude = (0x021A, 0x021B) if reserve_blocks else (0x021A,)
        extra = ()
        if not reserve_blocks:
            # Do not drop the relocated table into the bytes 0x021B grows into.
            extra = ((target.blocks_off, blocks_old_end + block_need,
                      "0x021B growth"),)
        start = target.find_free_space(
            length,
            exclude_tags=exclude,
            extra_ranges=extra,
            precise_previews=True,
            align=2,
        )
        if start is None:
            raise DngError(
                "not enough free space to move 0x021A: need %d bytes in the "
                "private block; refusing to overwrite preview or other tags"
                % length)
        new_table_off = start
        if reserve_blocks:
            new_blocks_off = _align_up(start + len(new_table), 2)
            if new_blocks_off + new_blocks_len > start + length:
                raise DngError(
                    "not enough free space to move 0x021A and 0x021B "
                    "together (%d bytes)" % length)
    elif not blocks_in_place:
        # No room to append.  Reclaim the old 0x021B area and, when the
        # 0x021A tag was padded, the freed tail after the new record table.
        new_blocks_off = target.find_free_space(
            new_blocks_len,
            exclude_tags=(0x021A, 0x021B),
            extra_ranges=((new_table_off, new_table_off + len(new_table),
                           "new 0x021A"),),
            preferred=table_old_end + len(new_table),
            align=2,
        )
        if new_blocks_off is None:
            raise DngError(
                "not enough free space for 0x021B: need %d bytes in the "
                "private block; refusing to overwrite preview or other tags"
                % new_blocks_len)
    blocks_relocated = new_blocks_off != target.blocks_off

    table_fill = b""
    if not table_relocated and need:
        table_fill = bytes(target.data[table_old_end:table_old_end + need])
    blocks_fill = b""
    if not blocks_relocated:
        blocks_fill = bytes(target.data[blocks_old_end:blocks_old_end + block_need])

    plan = {
        "new_table": new_table,
        "nrec": nrec,
        "added": added,
        "table_old_end": table_old_end,
        "table_new_end": new_table_off + len(new_table),
        "table_growth": table_growth,
        "need": need,
        "table_gap": table_gap,
        "table_next": table_next,
        "new_table_off": new_table_off,
        "table_relocated": table_relocated,
        "new_block_count": new_block_count,
        "new_blocks_len": new_blocks_len,
        "new_matrix_table": new_matrix_table,
        "blocks_old_end": blocks_old_end,
        "blocks_next": blocks_next,
        "blocks_gap": blocks_gap,
        "new_blocks_off": new_blocks_off,
        "blocks_relocated": blocks_relocated,
        "table_fill": table_fill,
        "blocks_fill": blocks_fill,
    }
    plan.update(info)
    return plan


def check_plan_fills(plan, force):
    """Reject non-empty gaps when appending, unless --force was requested."""
    if plan.get("kind") == "add_tags":
        return None
    bad = []
    if plan["table_fill"] and any(b not in (0x00, 0xFF) for b in plan["table_fill"]):
        bad.append("0x021A")
    if plan["blocks_fill"] and any(b not in (0x00, 0xFF) for b in plan["blocks_fill"]):
        bad.append("0x021B")
    if not bad:
        return None
    msg = ("gap after %s is not empty (contains non-00/non-FF bytes)"
           % "/".join(bad))
    if not force:
        raise DngError(msg + "; use --force to overwrite it")
    return msg


def write_patch(target, plan, out):
    """Apply a plan to a mutable bytearray."""
    if plan.get("kind") == "add_tags":
        # Data first, then the rebuilt IFD (its new entries overlap the old
        # 0x0200/0x0201/0x0205 bytes, which have already been relocated).
        for _tag, (rel, raw) in plan["relocated"].items():
            off = target.priv_off + rel
            out[off:off + len(raw)] = raw
        out[plan["table_off"]:plan["table_off"] + len(plan["new_table"])] = (
            plan["new_table"])
        out[plan["blocks_off"]:plan["blocks_off"] + plan["new_blocks_len"]] = (
            plan["new_matrix_table"])

        struct.pack_into(target.priv_endian + "H", out,
                         target.priv_off + 10, plan["new_entry_count"])
        for i, ent in enumerate(plan["new_entries"]):
            eoff = target.priv_off + 12 + i * 12
            struct.pack_into(target.priv_endian + "HHI", out, eoff,
                             ent["tag"], ent["type"], ent["count"])
            if ent["inline"]:
                out[eoff + 8:eoff + 12] = plan["inline_values"].get(
                    ent["tag"], b"\x00" * 4)
            else:
                struct.pack_into(target.priv_endian + "I", out, eoff + 8,
                                 ent["rel_off"])
        next_off = target.priv_off + 12 + plan["new_entry_count"] * 12
        out[next_off:next_off + 4] = b"\x00" * 4
        return

    new_table = plan["new_table"]
    table_off = plan["new_table_off"]
    out[table_off:table_off + len(new_table)] = new_table
    struct.pack_into(target.priv_endian + "I", out,
                     target.table_entry["entry_off"] + 4, len(new_table))
    if plan["table_relocated"]:
        value = table_off if target.priv_abs else table_off - target.priv_off
        struct.pack_into(target.priv_endian + "I", out,
                         target.table_entry["entry_off"] + 8, value)
    struct.pack_into(target.priv_endian + "H", out,
                     table_off + plan["nrec_off"], plan["nrec"])

    off = plan["new_blocks_off"]
    out[off:off + plan["new_blocks_len"]] = plan["new_matrix_table"]
    struct.pack_into(target.priv_endian + "I", out,
                     target.blocks_entry["entry_off"] + 4,
                     plan["new_blocks_len"])
    if plan["blocks_relocated"]:
        value = off if target.priv_abs else off - target.priv_off
        struct.pack_into(target.priv_endian + "I", out,
                         target.blocks_entry["entry_off"] + 8,
                         value)


def verify_output(out_path, plan):
    check = Dng(out_path)
    if check.missing:
        raise DngError("verification failed: still missing %s" % check.missing)
    if check.table_off != plan["new_table_off"]:
        raise DngError("verification failed: 0x021A offset 0x%X != 0x%X"
                       % (check.table_off, plan["new_table_off"]))
    if plan.get("kind") == "add_tags":
        for tag, (rel, raw) in plan["relocated"].items():
            ent = check.priv_entries.get(tag)
            if ent is None:
                raise DngError("verification failed: relocated tag 0x%04X missing" % tag)
            got = bytes(check.data[ent["value_off"]:ent["value_off"] + ent["size"]])
            if got != raw:
                raise DngError(
                    "verification failed: relocated tag 0x%04X changed" % tag)
    if check.n_records != plan["nrec"]:
        raise DngError("verification failed: nRecords %d != %d"
                       % (check.n_records, plan["nrec"]))
    if check.table_len != len(plan["new_table"]):
        raise DngError("verification failed: 0x021A length %d != %d"
                       % (check.table_len, len(plan["new_table"])))
    if check.n_params != plan["n_params"] or check.rec_size != plan["rec_size"]:
        raise DngError(
            "verification failed: 0x021A layout nParams %d / %d bytes != "
            "%d / %d" % (check.n_params, check.rec_size,
                         plan["n_params"], plan["rec_size"]))
    if check.block_count != plan["new_block_count"]:
        raise DngError("verification failed: matrix count %d != %d"
                       % (check.block_count, plan["new_block_count"]))
    if check.blocks_len != plan["new_blocks_len"]:
        raise DngError("verification failed: 0x021B length %d != %d"
                       % (check.blocks_len, plan["new_blocks_len"]))
    if check.blocks_off != plan["new_blocks_off"]:
        raise DngError("verification failed: 0x021B offset 0x%X != 0x%X"
                       % (check.blocks_off, plan["new_blocks_off"]))
    for new_idx, matrix in plan["added"]:
        if check.blocks[new_idx] != matrix:
            raise DngError("verification failed: matrix #%d differs" % new_idx)
    for rec in check.records:
        idx = check.record_block_index(rec)
        if idx >= check.block_count:
            raise DngError(
                "verification failed: mode %d points to matrix #%d"
                % (rec["id"], idx))
    return check


def convert_file(target_path, out_path, donor, *, overwrite=False, force=False,
                 allow_cross_model=False, calibrate=True):
    """Patch one target DNG and write out_path.  Returns a summary dict.

    donor may be a Dng or a DonorData.  Raises DngError on any problem.

    When the target has its own 0x021B base matrix, the donor's season
    matrices are recalibrated into the target's colour space (see
    plan_calibration).  cross-model transplants are allowed without
    allow_cross_model when that calibration also shows the two bodies share
    the same style table.
    """
    target = Dng(target_path)
    missing = target.missing
    if not missing:
        return {
            "target": target_path,
            "output": None,
            "changed": False,
            "message": "already has all four season records",
            "seasons": target.seasons,
            "n_records": target.n_records,
            "matrices": target.block_count,
        }
    donor_model = getattr(donor, "model", "")
    calibration = plan_calibration(target, donor) if calibrate else None
    xform = None
    if calibration is not None and not calibration["identity"]:
        xform = calibration["y"]

    compatible_cross, calibrated_cross, mismatch = check_cross_model(
        target, donor, allow_cross_model, calibration)
    if mismatch:
        raise DngError(mismatch)

    plan = plan_patch(target, donor, missing, xform)
    check_plan_fills(plan, force)

    if os.path.exists(out_path) and not overwrite:
        raise DngError("output exists: %s" % out_path)
    out_dir = os.path.dirname(os.path.abspath(out_path))
    if out_dir and not os.path.isdir(out_dir):
        os.makedirs(out_dir, exist_ok=True)

    out = bytearray(target.data)
    write_patch(target, plan, out)

    tmp = out_path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(out)
    os.replace(tmp, out_path)

    verify_output(out_path, plan)
    return {
        "target": target_path,
        "output": out_path,
        "changed": True,
        "missing": missing,
        "n_records": plan["nrec"],
        "new_block_count": plan["new_block_count"],
        "table_len": len(plan["new_table"]),
        "table_off": plan["new_table_off"],
        "table_relocated": bool(plan.get("table_relocated")),
        "n_params": plan["n_params"],
        "rec_size": plan["rec_size"],
        "target_n_params": target.n_params,
        "target_rec_size": target.rec_size,
        "layout_upgraded": bool(plan.get("layout_upgraded")),
        "blocks_len": plan["new_blocks_len"],
        "blocks_relocated": plan["blocks_relocated"],
        "blocks_off": plan["new_blocks_off"],
        "donor_model": donor_model,
        "compatible_cross_model": compatible_cross,
        "calibrated_cross_model": calibrated_cross,
        "calibration": calibration,
        "calibration_applied": xform is not None,
        "container": target.container,
    }


def patch(args):
    target = Dng(args.target)
    print("\n".join(dng_report.target_report(target, SEASON_NAMES)))
    print()

    if args.list:
        return 0
    builtin = getattr(args, "builtin", None)
    if args.verify_only:
        if builtin:
            print("\n".join(dng_report.builtin_donor_report(builtin)))
        elif args.donor:
            print("\n".join(dng_report.donor_report(Dng(args.donor),
                                                     SEASON_NAMES)))
        return 0

    missing = target.missing
    if not missing:
        print("\n".join(dng_report.nothing_to_do_report()))
        return 0

    if builtin:
        donor = builtin_donor(builtin)
        print("\n".join(dng_report.builtin_donor_report(builtin, donor)))
        print()
    elif args.donor:
        donor = Dng(args.donor)
        print("\n".join(dng_report.donor_report(donor, SEASON_NAMES)))
        print()
    else:
        raise DngError("--donor or --builtin is required when records are missing")

    calibration = plan_calibration(target, donor) if not args.no_calibrate else None
    xform = None
    if calibration is not None and not calibration["identity"]:
        xform = calibration["y"]

    compatible_cross, calibrated_cross, mismatch = check_cross_model(
        target, donor, args.allow_cross_model, calibration)
    if mismatch:
        raise DngError(mismatch + " (use --allow-cross-model to override)")
    print("\n".join(dng_report.calibration_report(
        target, donor, compatible_cross, calibrated_cross, calibration)))
    print()

    plan = plan_patch(target, donor, missing, xform)
    warning = check_plan_fills(plan, args.force)

    print("\n".join(dng_report.plan_report(
        target, plan, missing, SEASON_NAMES, warning)))

    if args.dry_run:
        print(dng_report.dry_run_report())
        return 0

    out_path = args.out
    backup = None
    if args.in_place:
        out_path = args.target
        if not args.no_backup:
            backup = args.target + ".bak"
            if os.path.exists(backup):
                backup = args.target + ".%s.bak" % time.strftime("%Y%m%d-%H%M%S")
            shutil.copy2(args.target, backup)
    elif not out_path:
        raise DngError("--out is required (or use --in-place)")
    if os.path.exists(out_path) and not (args.overwrite or args.in_place):
        raise DngError("output exists: %s (use --overwrite)" % out_path)

    out = bytearray(target.data)
    write_patch(target, plan, out)
    tmp = out_path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(out)
    os.replace(tmp, out_path)
    print("\n".join(dng_report.written_report(
        out_path, len(out), backup)))
    print()

    check = verify_output(out_path, plan)
    mismatches = []
    for sid in check.seasons:
        rec = check.record(sid)
        idx = check.record_block_index(rec)
        if idx >= check.block_count:
            raise DngError("verification failed: %s points to matrix #%d"
                           % (SEASON_NAMES[sid], idx))
        drec = donor.record(sid)
        if drec is not None:
            didx = donor.record_block_index(drec)
            if xform is None:
                expected = _convert_matrix(donor.blocks[didx], donor.priv_endian,
                                           check.priv_endian)
            else:
                expected = _mat_encode(
                    _mat_mul(_mat_decode(donor.blocks[didx], donor.priv_endian),
                             xform), check.priv_endian)
            if check.blocks[idx] != expected:
                mismatches.append((sid, idx))
    print("\n".join(dng_report.verify_report(
        check, SEASON_NAMES, mismatches)))
    print()
    print("\n".join(dng_report.completion_report()))
    return 0

def main(argv=None):
    p = argparse.ArgumentParser(
        description="Add missing Pentax four-season mode records (tag 0x021A) to a DNG.")
    p.add_argument("--target", required=True, help="DNG to patch")
    p.add_argument("--donor", help="DNG that contains the missing season records")
    p.add_argument("--builtin", choices=BUILTIN_DONOR_KINDS,
                   help="use bundled season data instead of a donor DNG "
                        "(k1 for K-1, k1ii for K-1 Mark II, kf; "
                        "k30/k01/k50/q7/mx1 for bodies with no "
                        "0x021A/0x021B table; 645d for the 11-parameter "
                        "record layout)")
    p.add_argument("--out", help="output DNG path")
    p.add_argument("--in-place", action="store_true", help="modify the target file")
    p.add_argument("--no-backup", action="store_true",
                   help="with --in-place, do not create a .bak copy")
    p.add_argument("--overwrite", action="store_true", help="overwrite existing output")
    p.add_argument("--dry-run", action="store_true", help="show the plan, write nothing")
    p.add_argument("--list", action="store_true", help="inspect the target only")
    p.add_argument("--verify-only", action="store_true",
                   help="inspect target (and donor if given), write nothing")
    p.add_argument("--force", action="store_true",
                   help="allow writing into a non-empty gap")
    p.add_argument("--allow-cross-model", action="store_true",
                   help="allow a donor from an unrelated camera model "
                        "(KF/K-70 is auto-detected; targets with a 0x021B "
                        "base matrix are auto-calibrated when the style table "
                        "matches)")
    p.add_argument("--no-calibrate", action="store_true",
                   help="copy the donor matrices verbatim instead of "
                        "recalibrating them into the target's colour space")
    args = p.parse_args(argv)
    try:
        return patch(args)
    except DngError as e:
        print("ERROR: %s" % e, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
