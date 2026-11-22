"""二进制表读取：列元数据、标定（TSCAL/TZERO）、空值（TNULL）、变长数组。

原则：
- 物理值 = 存储值 × TSCAL + TZERO（astropy 读取时已应用，这里同时给出原始存储值以便核对）；
- TNULL 判定在原始存储值上进行（缩放之前），命中的单元导出为 null；
- 变长数组列（TFORM 为 P/Q 描述符）每行长度独立，逐行返回原数组与长度，
  绝不补齐、绝不把填充值当作观测值。
"""

from __future__ import annotations

import math

import numpy as np
from astropy.io.fits.fitsrec import FITS_rec, _get_recarray_field


def _jsonable(value):
    """把 numpy/bytes 值转成 JSON 可序列化的 Python 值；NaN/Inf -> None。"""
    if value is None:
        return None
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        f = float(value)
        return f if math.isfinite(f) else None
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, bytes):
        return value.decode("ascii", "replace").rstrip()
    if isinstance(value, str):
        return value.rstrip()
    if isinstance(value, np.ndarray):
        return [_jsonable(v) for v in value.tolist()]
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    return value


def _raw_base(fits_rec):
    """取 FITS_rec 底层未做 TSCAL/TZERO 缩放的 recarray。"""
    base = fits_rec
    while isinstance(base, FITS_rec) and isinstance(base.base, np.recarray):
        base = base.base
    return base


def is_variable_format(fmt: str) -> bool:
    """TFORM 是否为变长数组（P/Q 描述符）。"""
    fmt = (fmt or "").strip().upper()
    return fmt.startswith("P") or fmt.startswith("Q")


def column_infos(hdu) -> list[dict]:
    """逐列元数据：名称、格式、单位、标定与空值规则、是否变长。"""
    header = hdu.header
    infos = []
    for i, col in enumerate(hdu.columns, start=1):
        fmt = col.format or ""
        tscale = header.get(f"TSCAL{i}")
        tzero = header.get(f"TZERO{i}")
        tnull = header.get(f"TNULL{i}")
        scaled = (tscale is not None and tscale != 1) or (tzero is not None and tzero != 0)
        infos.append({
            "index": i,
            "name": col.name,
            "format": str(fmt),
            "unit": col.unit or None,
            "variable_length": is_variable_format(str(fmt)),
            "scaled": bool(scaled),
            "tscale": _jsonable(tscale),
            "tzero": _jsonable(tzero),
            "tnull": _jsonable(tnull),
            "dim": col.dim or None,
            # 溯源：该列解释所依据的原始头字段
            "header_refs": {
                k: _jsonable(header[k])
                for k in (f"TTYPE{i}", f"TFORM{i}", f"TUNIT{i}", f"TSCAL{i}",
                          f"TZERO{i}", f"TNULL{i}", f"TDIM{i}")
                if k in header
            },
        })
    return infos


def _cell_from_fixed(raw_value, scaled_value, tnull):
    """固定长度列单元：返回 (value, raw, is_null)。

    空值判定：整型列看原始存储值是否等于 TNULL；浮点列看物理值是否 NaN。
    """
    raw_arr = np.asarray(raw_value)
    is_null = False
    if tnull is not None and raw_arr.dtype.kind in "biu":
        is_null = bool(np.any(raw_arr == tnull))
    if not is_null:
        sv = np.asarray(scaled_value)
        if sv.dtype.kind == "f":
            is_null = bool(np.all(~np.isfinite(sv))) and sv.size > 0
    if is_null:
        return None, _jsonable(raw_value), True
    return _jsonable(scaled_value), _jsonable(raw_value), False


def table_rows(hdu, start: int = 0, count: int = 100) -> dict:
    """读取表行。

    返回 {"columns": [...], "total_rows": N, "start": s,
          "rows": [{"row": 行号(0基), "cells": [{value, raw, is_null, length?}]}]}
    """
    data = hdu.data
    if data is None:
        return {"columns": column_infos(hdu), "total_rows": 0, "start": 0, "rows": []}

    nrows = len(data)
    start = max(0, min(start, nrows))
    stop = min(start + max(1, count), nrows)
    header = hdu.header
    infos = column_infos(hdu)
    base = _raw_base(data)

    # 预取各列的缩放值与原始值
    scaled_cols = {}
    raw_cols = {}
    for i, col in enumerate(hdu.columns, start=1):
        name = col.name
        scaled_cols[name] = data[name]
        if is_variable_format(str(col.format or "")):
            raw_cols[name] = None  # 变长列的原始描述符无展示价值
        else:
            try:
                raw_cols[name] = _get_recarray_field(base, name)
            except Exception:
                raw_cols[name] = None

    rows = []
    for r in range(start, stop):
        cells = []
        for i, col in enumerate(hdu.columns, start=1):
            name = col.name
            fmt = str(col.format or "")
            tnull = header.get(f"TNULL{i}")
            scaled = scaled_cols[name][r]
            if is_variable_format(fmt):
                # 变长数组：每行自己的长度，原样返回，不补齐
                arr = np.asarray(scaled) if scaled is not None else np.array([])
                if tnull is not None and arr.dtype.kind in "biu":
                    arr = np.where(arr == tnull, np.nan, arr.astype(float))
                cells.append({
                    "value": _jsonable(arr),
                    "raw": None,
                    "is_null": scaled is None,
                    "length": int(arr.shape[0]) if arr.ndim >= 1 else 1,
                })
            else:
                raw = raw_cols[name][r] if raw_cols[name] is not None else None
                value, raw_v, is_null = _cell_from_fixed(
                    raw if raw is not None else scaled, scaled, tnull)
                # 只在有标定或空值规则时附带原始值，避免冗余
                info = infos[i - 1]
                cells.append({
                    "value": value,
                    "raw": raw_v if (info["scaled"] or info["tnull"] is not None) else None,
                    "is_null": is_null,
                })
        rows.append({"row": r, "cells": cells})

    return {"columns": infos, "total_rows": nrows, "start": start, "rows": rows}
