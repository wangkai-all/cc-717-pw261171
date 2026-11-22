"""影像预览：物理值（应用 BZERO/BSCALE 后）渲染为 PNG，空值像素单独着色。

PNG 编码用标准库 zlib 手写，避免额外依赖。
"""

from __future__ import annotations

import struct
import zlib

import numpy as np

# 空值（BLANK/NaN）像素在预览中的颜色 (R, G, B)
NULL_COLOR = (200, 40, 160)


def _png_chunk(tag: bytes, payload: bytes) -> bytes:
    return (struct.pack(">I", len(payload)) + tag + payload
            + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF))


def encode_png_rgb(rgb: np.ndarray) -> bytes:
    """rgb: (H, W, 3) uint8 -> PNG 字节串。"""
    h, w, _ = rgb.shape
    raw = b"".join(b"\x00" + rgb[row].tobytes() for row in range(h))
    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n"
            + _png_chunk(b"IHDR", ihdr)
            + _png_chunk(b"IDAT", zlib.compress(raw, 6))
            + _png_chunk(b"IEND", b""))


def image_stats(data: np.ndarray) -> dict:
    """物理值统计（忽略空值像素）。"""
    mask = ~np.isfinite(data)
    valid = data[~mask]
    stats = {
        "shape": list(data.shape),
        "null_pixels": int(mask.sum()),
        "total_pixels": int(data.size),
    }
    if valid.size:
        stats.update({
            "min": float(valid.min()),
            "max": float(valid.max()),
            "mean": float(valid.mean()),
        })
    else:
        stats.update({"min": None, "max": None, "mean": None})
    return stats


def render_preview(data: np.ndarray, lo_pct: float = 1.0, hi_pct: float = 99.0) -> bytes:
    """把 2D 物理值数组按分位数拉伸渲染为灰度 PNG，空值像素用 NULL_COLOR。"""
    if data.ndim != 2:
        raise ValueError(f"仅支持 2D 影像预览，当前为 {data.ndim} 维。")
    mask = ~np.isfinite(data)
    valid = data[~mask]
    if valid.size == 0:
        lo, hi = 0.0, 1.0
    else:
        lo, hi = (float(np.percentile(valid, lo_pct)),
                  float(np.percentile(valid, hi_pct)))
        if not hi > lo:
            lo, hi = float(valid.min()), float(valid.max())
        if not hi > lo:
            hi = lo + 1.0
    gray = np.clip((np.nan_to_num(data, nan=lo) - lo) / (hi - lo), 0, 1)
    gray8 = (gray * 255).astype(np.uint8)
    rgb = np.stack([gray8] * 3, axis=-1)
    rgb[mask] = NULL_COLOR
    return encode_png_rgb(rgb)
