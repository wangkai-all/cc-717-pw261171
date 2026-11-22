"""WCS 支持策略：有限且明确的投影白名单。

设计原则（对应需求）：
- 仅支持白名单内的投影，用 astropy.wcs 计算像素 -> 天球坐标；
- 不支持的投影：保留头部中的原始坐标信息（CTYPE/CRVAL/CRPIX/...），
  明确说明原因，绝不给出猜测的天空位置；
- 非天球坐标（无 CTYPE 或 LINEAR 等）：只报告像素坐标。
"""

from __future__ import annotations

from astropy.wcs import WCS

# 明确支持的投影代码（CTYPE 后 3 个字符）
SUPPORTED_PROJECTIONS = {"TAN", "SIN", "ZEA", "CAR"}

# 参与像素->世界坐标计算的头字段，用于“使用了哪些头字段”的溯源展示
_WCS_KEYWORDS = [
    "CTYPE1", "CTYPE2", "CRVAL1", "CRVAL2", "CRPIX1", "CRPIX2",
    "CDELT1", "CDELT2", "CUNIT1", "CUNIT2",
    "CD1_1", "CD1_2", "CD2_1", "CD2_2",
    "PC1_1", "PC1_2", "PC2_1", "PC2_2",
    "PV1_0", "PV1_1", "PV1_2", "PV2_0", "PV2_1", "PV2_2",
    "RADESYS", "EQUINOX", "LONPOLE", "LATPOLE",
]


def projection_of(ctype: str | None) -> str | None:
    """从 CTYPE（如 'RA---TAN'）提取投影代码（'TAN'）。非天球轴返回 None。"""
    if not ctype or not isinstance(ctype, str):
        return None
    if "-" not in ctype:
        return None
    return ctype.rsplit("-", 1)[-1].strip() or None


def collect_wcs_fields(header) -> dict:
    """收集头部中实际存在的 WCS 相关字段及其值，用于溯源展示。"""
    fields = {}
    for key in _WCS_KEYWORDS:
        if key in header:
            fields[key] = header[key]
    return fields


def wcs_summary(header, naxis: int) -> dict:
    """对影像 HDU 的 WCS 可用性给出结论。

    返回 dict:
      kind: "none" | "unsupported" | "supported"
      projection: 投影代码或 None
      reason: 面向用户的说明
      fields: 头部中原始的 WCS 字段（不支持时也要完整保留展示）
    """
    fields = collect_wcs_fields(header)
    ctype1 = header.get("CTYPE1")
    ctype2 = header.get("CTYPE2")

    if naxis < 2 or not ctype1 or not ctype2:
        return {
            "kind": "none",
            "projection": None,
            "reason": "该影像没有完整的天球坐标描述（缺少 CTYPE1/CTYPE2），仅提供像素坐标。",
            "fields": fields,
        }

    proj1 = projection_of(ctype1)
    proj2 = projection_of(ctype2)
    if proj1 is None or proj2 is None:
        return {
            "kind": "none",
            "projection": None,
            "reason": f"CTYPE1/CTYPE2（{ctype1!r}/{ctype2!r}）不是天球投影轴，仅提供像素坐标。",
            "fields": fields,
        }

    projection = proj1
    if proj1 != proj2:
        return {
            "kind": "unsupported",
            "projection": projection,
            "reason": f"两个轴投影不一致（{proj1} vs {proj2}），无法可靠计算天空位置。",
            "fields": fields,
        }

    if projection not in SUPPORTED_PROJECTIONS:
        return {
            "kind": "unsupported",
            "projection": projection,
            "reason": (
                f"投影 {projection!r} 不在本站支持的投影集合 "
                f"{sorted(SUPPORTED_PROJECTIONS)} 内。已保留头部原始坐标信息，"
                f"不提供猜测的天空位置。"
            ),
            "fields": fields,
        }

    return {
        "kind": "supported",
        "projection": projection,
        "reason": f"投影 {projection} 受支持，可点击像素查询天球坐标。",
        "fields": fields,
    }


def pixel_to_world(header, x: float, y: float) -> dict:
    """FITS 1 基像素坐标 -> 世界坐标。

    仅在投影受支持时调用。返回坐标及计算所用的头字段。
    """
    w = WCS(header)
    if not w.has_celestial:
        raise ValueError("该 WCS 不含天球坐标轴。")
    world = w.all_pix2world([[x, y]], 1)[0]
    celestial = w.celestial
    return {
        "lon": float(world[0]),
        "lat": float(world[1]),
        "lon_type": celestial.wcs.ctype[0],
        "lat_type": celestial.wcs.ctype[1],
        "lon_unit": str(celestial.wcs.cunit[0] or "deg"),
        "lat_unit": str(celestial.wcs.cunit[1] or "deg"),
        "fields_used": collect_wcs_fields(header),
    }
