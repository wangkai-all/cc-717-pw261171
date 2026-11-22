"""导出预览与 CSV：可追溯到原始头部字段与行号。

- 每行带 FITS 行号（0 基，与表数据端点一致）；
- 每列列出其解释所依据的原始头字段（TTYPEn/TFORMn/TUNITn/TSCALn/TZEROn/TNULLn）；
- 物理值已应用 TSCAL/TZERO，空值（TNULL/NaN）导出为空；
- 变长数组列按每行实际长度导出（JSON 数组 / CSV 中以空格分隔），不补齐。
"""

from __future__ import annotations

import csv
import io
from datetime import datetime, timezone

from astropy.io import fits

from . import tables


def _selected_columns(hdu, names: list[str] | None) -> list[dict]:
    infos = tables.column_infos(hdu)
    if not names:
        return infos
    by_name = {c["name"]: c for c in infos}
    missing = [n for n in names if n not in by_name]
    if missing:
        raise KeyError(f"列不存在: {missing}")
    return [by_name[n] for n in names]


def export_preview(path: str, hdu_index: int, columns: list[str] | None,
                   max_rows: int = 50) -> dict:
    """生成导出预览（JSON），含完整溯源信息。"""
    with fits.open(path) as hdul:
        hdu = hdul[hdu_index]
        if not isinstance(hdu, (fits.BinTableHDU, fits.TableHDU)):
            raise TypeError(f"HDU {hdu_index}（{hdu.name}）不是表，无法按列导出。")
        selected = _selected_columns(hdu, columns)
        data = tables.table_rows(hdu, start=0, count=max_rows)

        col_names = [c["name"] for c in selected]
        col_idx = {c["name"]: c["index"] - 1 for c in selected}
        rows = []
        for row in data["rows"]:
            rows.append({
                "row": row["row"],
                "values": {
                    name: row["cells"][col_idx[name]]["value"] for name in col_names
                },
                "nulls": [name for name in col_names
                          if row["cells"][col_idx[name]]["is_null"]],
                "lengths": {name: row["cells"][col_idx[name]]["length"]
                            for name in col_names
                            if "length" in row["cells"][col_idx[name]]},
            })

        return {
            "hdu": hdu_index,
            "hdu_name": hdu.name,
            "columns": [
                {
                    "name": c["name"],
                    "unit": c["unit"],
                    "format": c["format"],
                    "variable_length": c["variable_length"],
                    "scaled": c["scaled"],
                    "header_refs": c["header_refs"],
                }
                for c in selected
            ],
            "total_rows": data["total_rows"],
            "returned_rows": len(rows),
            "rows": rows,
            "provenance": {
                "hdu_index": hdu_index,
                "hdu_name": hdu.name,
                "row_numbering": "0 基 FITS 行号，与表数据端点一致",
                "scaling_rule": "物理值 = 存储值 × TSCALn + TZEROn（已应用）；TNULLn/NaN 导出为空",
                "variable_length_rule": "变长数组列按每行实际长度导出，不补齐",
                "generated_at": datetime.now(timezone.utc).isoformat(),
            },
        }


def export_csv(path: str, hdu_index: int, columns: list[str] | None,
               max_rows: int = 100000) -> str:
    """生成 CSV 文本：首列 fits_row，头部注释行携带溯源信息。"""
    preview = export_preview(path, hdu_index, columns, max_rows)
    buf = io.StringIO()
    buf.write(f"# provenance: hdu={preview['hdu']} ({preview['hdu_name']}), "
              f"generated_at={preview['provenance']['generated_at']}\n")
    for col in preview["columns"]:
        refs = ", ".join(f"{k}={v}" for k, v in col["header_refs"].items())
        buf.write(f"# column {col['name']}: {refs}\n")
    buf.write(f"# scaling: {preview['provenance']['scaling_rule']}\n")

    writer = csv.writer(buf)
    names = [c["name"] for c in preview["columns"]]
    units = {c["name"]: c["unit"] for c in preview["columns"]}
    writer.writerow(["fits_row"] + names)
    writer.writerow([""] + [units[n] or "" for n in names])
    for row in preview["rows"]:
        out = [row["row"]]
        for name in names:
            v = row["values"][name]
            if v is None:
                out.append("")
            elif isinstance(v, list):
                out.append(" ".join("" if x is None else str(x) for x in v))
            else:
                out.append(v)
        writer.writerow(out)
    return buf.getvalue()
