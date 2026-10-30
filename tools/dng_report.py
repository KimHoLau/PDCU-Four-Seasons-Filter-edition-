"""Human-readable reports for the DNG season patcher.

The DNG parser, patch planner and file writer stay silent.  This module is the
single place that turns their data into the CLI text (and the GUI reuses the
same calibration helpers), so the core can be imported without producing
stdout side effects.
"""
from __future__ import annotations

__copyright__ = "Copyright © 2026 KimHoLau X deepseek harness"


def matrix_text(matrix):
    rows = []
    for row in matrix:
        rows.append("[" + " ".join("%+.5f" % v for v in row) + "]")
    return " ".join(rows)


def describe_cm2(cal):
    """Base-vs-ColorMatrix2 verdict, or '' when the check was skipped."""
    cm2 = cal.get("cm2") if cal else None
    if not cm2:
        return ""
    if cm2["ok"]:
        return "CM2 check: pass (0x021B base vs ColorMatrix2, dY %.1e)" % cm2["delta"]
    return ("CM2 check: WARNING - the target's 0x021B base and its "
            "ColorMatrix2 imply different Y (dY %.1e); using the 0x021B base"
            % cm2["delta"])


def describe_calibration(cal):
    """One-line summary used by the CLI and the GUI log."""
    if cal is None:
        return "no calibration (donor/target has no 0x021B base matrix)"
    if cal["identity"]:
        return "no correction needed (same base colour matrix)"
    if not cal["style_known"]:
        return ("Y = %s  (style check: n/a - the donor has no mode records; "
                "bundled data assumed to match the KF style)"
                % matrix_text(cal["y"]))
    text = ("Y = %s  style: median %.1e, max %.1e over %d modes"
            % (matrix_text(cal["y"]), cal["style_median"] or 0.0,
               cal["style_max"] or 0.0, cal["modes"]))
    if not cal["style_ok"]:
        text += "  [WARNING: style tables differ]"
    return text


def describe_dng_lines(dng, names):
    lines = ["file          : %s" % dng.path,
             "size          : %d bytes" % len(dng.data),
             "camera        : %s" % (dng.model or "?")]
    if dng.unique_model and dng.unique_model != dng.model:
        lines.append("unique model  : %s" % dng.unique_model)
    label = ("private block" if dng.container == "private"
             else "maker note")
    lines.append("%-13s : %s, file 0x%X..0x%X (%d bytes)"
                 % (label, ("DNGPrivateData 0xC634"
                            if dng.container == "private"
                            else "EXIF MakerNote 0x927C"),
                    dng.priv_off, dng.priv_end, dng.priv_len))
    if dng.table_len:
        lines.append("tag 0x021A    : file 0x%X..0x%X (%d bytes)"
                     % (dng.table_off, dng.table_off + dng.table_len,
                        dng.table_len))
        lines.append("table         : nParams=%d nRecords=%d recordSize=%d"
                     % (dng.n_params, dng.n_records, dng.rec_size))
    else:
        lines.append("tag 0x021A    : absent")
        lines.append("table         : nParams=%d (default) nRecords=0"
                     % dng.n_params)
    if dng.table_padding:
        lines.append("table padding : %d bytes after records (reserved, ignored)"
                     % dng.table_padding)
    if dng.blocks_len:
        lines.append("tag 0x021B    : file 0x%X..0x%X (%d bytes), "
                     "matrices=%d x %d B"
                     % (dng.blocks_off, dng.blocks_off + dng.blocks_len,
                        dng.blocks_len, dng.block_count, dng.block_size))
    else:
        lines.append("tag 0x021B    : absent")
    lines.append("mode ids      : %s" % ",".join(str(i) for i in dng.ids))
    if dng.seasons:
        lines.append("season records: %s" % ", ".join(
            "%d/%s" % (i, names[i]) for i in dng.seasons))
        lines.append("season matrices: %s" % ", ".join(
            "%d/%s->#%d" % (i, names[i], dng.record_block_index(dng.record(i)))
            for i in dng.seasons))
    else:
        lines.append("season records: none")
    if dng.missing:
        lines.append("missing       : %s" % ", ".join(
            "%d/%s" % (i, names[i]) for i in dng.missing))
    else:
        lines.append("missing       : none")
    if dng.has_mode_table and dng.n_params < 12:
        lines.append("layout note   : this body writes an %d-parameter 0x021A "
                     "table; PDCU 5.10.2.2 only lists the four seasons in the "
                     "12-parameter layout, so the tool rebuilds it"
                     % dng.n_params)
    return lines


def describe_dng(dng, names):
    return "\n".join(describe_dng_lines(dng, names))


def target_report(target, names):
    return ["== target =="] + describe_dng_lines(target, names)


def donor_report(donor, names):
    return ["== donor =="] + describe_dng_lines(donor, names)


def builtin_donor_report(kind, donor=None):
    lines = ["== donor =="]
    if donor is None:
        lines.append("built-in %s season data" % kind)
    else:
        lines.append("built-in %s season data (model %s, endian %s)"
                     % (kind, donor.model, donor.priv_endian))
    return lines


def nothing_to_do_report():
    return ["Nothing to do: all four season records are already present."]


def dry_run_report():
    return "dry run: no file written"


def calibration_report(target, donor, compatible_cross, calibrated_cross,
                       calibration):
    lines = []
    if target.model and donor.model and target.model != donor.model:
        msg = ("camera model mismatch: target %r, donor %r"
               % (target.model, donor.model))
        if compatible_cross:
            lines.append("NOTE: " + msg)
            lines.append("      KF / K-70 share the same 21 base color "
                         "matrices; this transplant is exact.")
        elif calibrated_cross:
            lines.append("NOTE: " + msg)
            lines.append("      same style table (checked below); transplant "
                         "is calibrated into the target's colour space.")
        else:
            lines.append("WARNING: " + msg)
    if (target.unique_model and donor.unique_model
            and target.unique_model != donor.unique_model):
        if compatible_cross or calibrated_cross:
            lines.append("NOTE: UniqueCameraModel differs: %r vs %r"
                         % (target.unique_model, donor.unique_model))
        else:
            lines.append("WARNING: UniqueCameraModel mismatch: %r vs %r"
                         % (target.unique_model, donor.unique_model))

    lines.append("== calibration ==")
    lines.append("target base    : %s"
                 % ("" if calibration is None
                    else matrix_text(calibration["target_base"])))
    lines.append("donor base     : %s"
                 % ("" if calibration is None
                    else matrix_text(calibration["donor_base"])))
    lines.append("result         : %s" % describe_calibration(calibration))
    if calibration is not None and calibration["style_ok"]:
        lines.append("style check    : pass (%d common modes, median %.1e)"
                     % (calibration["modes"], calibration["style_median"]))
    elif calibration is not None and not calibration["style_known"]:
        lines.append("style check    : n/a (donor has no mode records; "
                     "bundled data assumed to match the KF style)")
    elif calibration is not None:
        lines.append("style check    : WARNING - the two tables do not look "
                     "like the same style (median %.1e)"
                     % (calibration["style_median"] or 0.0))
    if calibration is not None:
        cm2_text = describe_cm2(calibration)
        if cm2_text:
            lines.append("CM2 check      : %s" % cm2_text.split(": ", 1)[1])
    return lines


def plan_report(target, plan, missing, names, warning):
    lines = ["== plan ==",
             "insert modes   : %s" % ", ".join(
                 "%d/%s" % (i, names[i]) for i in missing)]
    if plan.get("kind") == "add_tags":
        lines.append("mode table     : absent -> %d B, nRecords 0 -> %d "
                     "(new tag)" % (len(plan["new_table"]), plan["nrec"]))
        lines.append("matrix table   : absent -> %d B, matrices 0 -> %d "
                     "(new tag)" % (plan["new_blocks_len"],
                                    plan["new_block_count"]))
        lines.append("tag data       : 0x021A at 0x%X, 0x021B at 0x%X"
                     % (plan["table_off"], plan["blocks_off"]))
        for tag, (rel, raw) in sorted(plan["relocated"].items()):
            lines.append("relocate       : tag 0x%04X -> private +0x%X (%d B)"
                         % (tag, rel, len(raw)))
    else:
        lines.append("mode table     : %d -> %d B (%+d), nRecords %d -> %d"
                     % (target.table_len, len(plan["new_table"]),
                        plan["table_growth"], target.n_records, plan["nrec"]))
        if plan.get("layout_upgraded"):
            lines.append("record layout  : %d params / %d B -> %d params / "
                         "%d B (PDCU needs the 12-parameter layout for the "
                         "four seasons)"
                         % (target.n_params, target.rec_size,
                            plan["n_params"], plan["rec_size"]))
        if plan["table_relocated"]:
            lines.append("mode move      : file 0x%X -> 0x%X "
                         "(0x021A gap was %d B; table moved to free space)"
                         % (target.table_off, plan["new_table_off"],
                            plan["table_gap"]))
        else:
            lines.append("mode space     : old tag end 0x%X, new table end "
                         "0x%X, gap after old tag %d B"
                         % (plan["table_old_end"], plan["table_new_end"],
                            plan["table_gap"]))
        lines.append("matrix table   : %d -> %d B, matrices %d -> %d"
                     % (target.blocks_len, plan["new_blocks_len"],
                        target.block_count, plan["new_block_count"]))
        if plan["blocks_relocated"]:
            lines.append("matrix move    : file 0x%X -> 0x%X "
                         "(0x021B gap was %d B; old matrix area reused)"
                         % (target.blocks_off, plan["new_blocks_off"],
                            plan["blocks_gap"]))
        else:
            lines.append("matrix gap     : file 0x%X..0x%X (%d bytes)"
                         % (plan["blocks_old_end"], plan["blocks_next"],
                            plan["blocks_gap"]))
    for new_idx, _matrix in plan["added"]:
        lines.append("  + matrix #%d" % new_idx)
    if warning:
        lines.append("WARNING: " + warning)
    return lines


def written_report(out_path, out_len, backup=None):
    lines = []
    if backup:
        lines.append("backup         : %s" % backup)
    lines.append("wrote          : %s (%d bytes)" % (out_path, out_len))
    return lines


def verify_report(check, names, mismatches):
    lines = ["== verify =="] + describe_dng_lines(check, names)
    for sid, idx in mismatches:
        lines.append("WARNING: existing %s matrix #%d was not written by this run"
                     % (names[sid], idx))
    return lines


def completion_report():
    return [
        "OK: all four season records are present, and each points to a "
        "3x3 color matrix.",
        "PDCU should now list HARUBENI, KATEN, KYUSHU and FUYUNO, and use "
        "the donor's season color matrices.",
        "Note: per-image data such as 0x021F is not changed; the radar "
        "shape also depends on the target image itself.",
    ]
