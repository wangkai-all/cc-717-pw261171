"""逐 HDU 分析：头部、数据、标定规则与单元级可用性检查。

每个 HDU 独立检查（校验和、数据解码、WCS、表列），文件级状态取各单元
最差结果——绝不允许“第一张图正常 => 整个文件正常”。
"""

from __future__ import annotations

import numpy as np
from astropy.io import fits

from . import tables, wcs_support
from .images import image_stats
from .keywords import explain_keyword
from .tables import _jsonable


def _check(check_id: str, status: str, message: str) -> dict:
    return {"id": check_id, "status": status, "message": message}


def _worst(statuses) -> str:
    order = {"error": 3, "warning": 2, "ok": 1}
    return max(statuses, key=lambda s: order[s]) if statuses else "ok"


def _checksum_checks(hdu) -> list[dict]:
    checks = []
    for key, method, label in (
        ("CHECKSUM", hdu.verify_checksum, "HDU 整体校验和"),
        ("DATASUM", hdu.verify_datasum, "数据区校验和"),
    ):
        if key not in hdu.header:
            checks.append(_check(key.lower(), "warning",
                                 f"头部无 {key} 关键字，无法验证{label}。"))
            continue
        try:
            result = method()
        except Exception as exc:  # 数据损坏时 astropy 可能抛错
            checks.append(_check(key.lower(), "error",
                                 f"{label}验证失败：{exc}"))
            continue
        if result == 1:
            checks.append(_check(key.lower(), "ok", f"{label}（{key}）验证通过。"))
        else:
            checks.append(_check(key.lower(), "error",
                                 f"{label}（{key}）验证失败：数据或头部在传输/存储中被改动。"))
    return checks


def _image_summary(hdu, raw_hdu) -> tuple[dict, list[dict]]:
    """影像 HDU 摘要 + 相关检查。raw_hdu 为未应用 BZERO/BSCALE 的同一 HDU。"""
    checks = []
    header = hdu.header
    naxis = header.get("NAXIS", 0)
    summary = {
        "bitpix": header.get("BITPIX"),
        "naxis": naxis,
        "shape": [header.get(f"NAXIS{i}") for i in range(1, naxis + 1)],
        "bunit": header.get("BUNIT"),
    }

    # 标定规则（BZERO/BSCALE/BLANK）——必须显式报告，不能遗漏
    bscale = header.get("BSCALE", 1)
    bzero = header.get("BZERO", 0)
    blank = header.get("BLANK")
    summary["scaling"] = {
        "bscale": _jsonable(bscale),
        "bzero": _jsonable(bzero),
        "blank": _jsonable(blank),
        "has_scaling": (bscale != 1) or (bzero != 0),
        "rule": "物理值 = 存储值 × BSCALE + BZERO；存储值等于 BLANK 的像素为空值",
    }
    if summary["scaling"]["has_scaling"]:
        checks.append(_check(
            "scaling", "ok",
            f"已应用标定规则：物理值 = 存储值 × {bscale} + {bzero}"
            + ("；BLANK=%s 的像素按空值处理" % blank if blank is not None else "")))
    else:
        checks.append(_check("scaling", "ok", "无 BZERO/BSCALE 标定，存储值即物理值。"))

    # 数据解码
    try:
        data = hdu.data
        if data is None or naxis == 0:
            checks.append(_check("data_decode", "ok", "本 HDU 无数据数组。"))
            summary["stats"] = None
        else:
            arr = np.asarray(data, dtype=np.float64)
            summary["stats"] = image_stats(arr)
            nulls = summary["stats"]["null_pixels"]
            checks.append(_check(
                "data_decode", "ok",
                f"数据解码成功：{summary['stats']['shape']}，"
                f"空值像素 {nulls} / {summary['stats']['total_pixels']}。"))
            if raw_hdu is not None and raw_hdu.data is not None:
                summary["raw_dtype"] = str(np.asarray(raw_hdu.data).dtype)
    except Exception as exc:
        checks.append(_check("data_decode", "error", f"数据解码失败：{exc}"))
        summary["stats"] = None

    # WCS（有限投影白名单）
    if naxis >= 2:
        wcs_info = wcs_support.wcs_summary(header, naxis)
        summary["wcs"] = wcs_info
        if wcs_info["kind"] == "supported":
            checks.append(_check("wcs", "ok", wcs_info["reason"]))
        elif wcs_info["kind"] == "unsupported":
            checks.append(_check("wcs", "warning", wcs_info["reason"]))
        else:
            checks.append(_check("wcs", "ok", wcs_info["reason"]))
    return summary, checks


def _table_summary(hdu) -> tuple[dict, list[dict]]:
    checks = []
    header = hdu.header
    try:
        cols = tables.column_infos(hdu)
        nrows = len(hdu.data) if hdu.data is not None else 0
    except Exception as exc:
        return {}, [_check("columns", "error", f"表列解析失败：{exc}")]

    var_cols = [c["name"] for c in cols if c["variable_length"]]
    scaled_cols = [c["name"] for c in cols if c["scaled"]]
    null_cols = [c["name"] for c in cols if c["tnull"] is not None]
    summary = {
        "rows": nrows,
        "columns": cols,
        "variable_length_columns": var_cols,
        "scaled_columns": scaled_cols,
        "null_marked_columns": null_cols,
    }
    checks.append(_check(
        "columns", "ok",
        f"{len(cols)} 列 × {nrows} 行解析成功。"
        + (f" 变长列 {var_cols} 按每行实际长度读取，不补齐。" if var_cols else "")
        + (f" 列标定 TSCAL/TZERO 应用于 {scaled_cols}。" if scaled_cols else "")
        + (f" 空值标记 TNULL 作用于 {null_cols}。" if null_cols else "")))
    return summary, checks


def analyze_file(path: str, name: str) -> dict:
    """生成文件级报告：逐 HDU 状态 + 汇总。"""
    hdul = fits.open(path)
    raw_hdul = fits.open(path, do_not_scale_image_data=True)
    try:
        hdu_reports = []
        for idx, hdu in enumerate(hdul):
            if isinstance(hdu, fits.BinTableHDU) or isinstance(hdu, fits.TableHDU):
                hdu_type = "BINTABLE" if isinstance(hdu, fits.BinTableHDU) else "TABLE"
            elif idx == 0:
                hdu_type = "PRIMARY"
            else:
                hdu_type = "IMAGE"

            checks = _checksum_checks(hdu)
            summary = {}
            if hdu_type in ("PRIMARY", "IMAGE"):
                img_summary, img_checks = _image_summary(hdu, raw_hdul[idx])
                summary["image"] = img_summary
                checks.extend(img_checks)
            if hdu_type in ("BINTABLE", "TABLE"):
                tbl_summary, tbl_checks = _table_summary(hdu)
                summary["table"] = tbl_summary
                checks.extend(tbl_checks)

            status = _worst([c["status"] for c in checks])
            hdu_reports.append({
                "index": idx,
                "name": hdu.name,
                "type": hdu_type,
                "status": status,
                "checks": checks,
                **summary,
            })

        file_status = _worst([h["status"] for h in hdu_reports])
        counts = {"ok": 0, "warning": 0, "error": 0}
        for h in hdu_reports:
            counts[h["status"]] += 1
        return {
            "name": name,
            "status": "ok" if file_status == "ok" else "degraded",
            "worst_unit_status": file_status,
            "summary": {"total_hdus": len(hdu_reports), **counts},
            "status_note": (
                "文件级状态取所有 HDU 中最差的单元状态；"
                "任一 HDU 校验失败都会使文件降级，不因首个 HDU 正常而判整文件正常。"
            ),
            "hdus": hdu_reports,
        }
    finally:
        hdul.close()
        raw_hdul.close()


def header_cards(path: str, hdu_index: int) -> dict:
    """头部卡片 + 逐条解释 + 标定规则汇总。"""
    with fits.open(path) as hdul:
        hdu = hdul[hdu_index]
        cards = []
        for card in hdu.header.cards:
            if card.keyword in ("", "END"):
                continue
            value = card.value
            cards.append({
                "keyword": card.keyword,
                "value": _jsonable(value),
                "comment": card.comment or None,
                "explanation": explain_keyword(card.keyword),
            })
        header = hdu.header
        calibration = {
            "bscale": _jsonable(header.get("BSCALE")),
            "bzero": _jsonable(header.get("BZERO")),
            "blank": _jsonable(header.get("BLANK")),
            "column_scaling": {
                f"TSCAL{i}/TZERO{i}": [ _jsonable(header.get(f"TSCAL{i}")),
                                        _jsonable(header.get(f"TZERO{i}")) ]
                for i in range(1, header.get("TFIELDS", 0) + 1)
                if f"TSCAL{i}" in header or f"TZERO{i}" in header
            },
            "column_nulls": {
                f"TNULL{i}": _jsonable(header[f"TNULL{i}"])
                for i in range(1, header.get("TFIELDS", 0) + 1)
                if f"TNULL{i}" in header
            },
        }
        return {"hdu": hdu_index, "name": hdu.name, "cards": cards,
                "calibration": calibration}
