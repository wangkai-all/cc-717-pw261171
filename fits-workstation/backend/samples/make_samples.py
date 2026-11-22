"""生成项目自带的 FITS 样例（不连接任何观测机构，全部由代码合成）。

样例覆盖：
  demo_multiext.fits        多扩展：主影像(TAN) + 影像扩展(SIN) + 源表（列标定/空值）
  demo_scaled_ints.fits     缩放整数：uint16(BZERO=32768) + int16(BSCALE/BZERO/BLANK)
  demo_varlen.fits          变长数组列：每行长度不同
  demo_bad_checksum.fits    坏校验：中间 HDU 数据被篡改，其余 HDU 正常
  demo_unsupported_wcs.fits 不支持的投影（COP），保留原始坐标信息

用法：python -m backend.samples.make_samples [输出目录]
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from astropy.io import fits

RNG = np.random.default_rng(20261122)


def _sky_image(n=101, sources=((30, 40, 5000.0), (70, 65, 9000.0), (50, 20, 3000.0))):
    """合成天空影像：缓变背景 + 高斯点源 + 噪声。"""
    y, x = np.mgrid[0:n, 0:n]
    img = 100.0 + 0.3 * x + 0.2 * y
    for sx, sy, amp in sources:
        img += amp * np.exp(-((x - sx) ** 2 + (y - sy) ** 2) / (2 * 2.5 ** 2))
    img += RNG.normal(0, 8, img.shape)
    return img


def _tan_wcs(header, n):
    header["CTYPE1"] = "RA---TAN"
    header["CTYPE2"] = "DEC--TAN"
    header["CRVAL1"] = 180.0
    header["CRVAL2"] = 45.0
    header["CRPIX1"] = (n + 1) / 2
    header["CRPIX2"] = (n + 1) / 2
    header["CDELT1"] = -0.01
    header["CDELT2"] = 0.01
    header["CUNIT1"] = "deg"
    header["CUNIT2"] = "deg"
    header["RADESYS"] = "ICRS"


def make_multiext(out: Path) -> Path:
    """多扩展文件：主影像 + 影像扩展 + 二进制表（含列标定与空值）。"""
    n = 101
    img = _sky_image(n).astype(np.float32)

    primary = fits.PrimaryHDU(img)
    primary.header["TELESCOP"] = "SIM-1"
    primary.header["INSTRUME"] = "SIMCAM"
    primary.header["OBJECT"] = "SYNTH-FIELD"
    primary.header["DATE-OBS"] = "2026-11-22T01:02:03"
    primary.header["EXPTIME"] = 300.0
    primary.header["BUNIT"] = "adu"
    _tan_wcs(primary.header, n)

    # 影像扩展：SIN 投影的背景图，含 NaN 空值像素
    bkg = (100 + 0.3 * np.mgrid[0:n, 0:n][1] + 0.2 * np.mgrid[0:n, 0:n][0]).astype(np.float32)
    bkg[10:14, 20:26] = np.nan
    ext = fits.ImageHDU(bkg, name="BACKGROUND")
    ext.header["BUNIT"] = "adu"
    ext.header["CTYPE1"] = "RA---SIN"
    ext.header["CTYPE2"] = "DEC--SIN"
    ext.header["CRVAL1"] = 180.0
    ext.header["CRVAL2"] = 45.0
    ext.header["CRPIX1"] = (n + 1) / 2
    ext.header["CRPIX2"] = (n + 1) / 2
    ext.header["CDELT1"] = -0.01
    ext.header["CDELT2"] = 0.01

    # 源表：物理列 + 带 TSCAL/TZERO/TNULL 的原始计数列 + 浮点空值列
    nsrc = 8
    ra = 180.0 + RNG.uniform(-0.4, 0.4, nsrc)
    dec = 45.0 + RNG.uniform(-0.4, 0.4, nsrc)
    flux = RNG.uniform(50, 5000, nsrc).astype(np.float32)
    raw_counts = RNG.integers(0, 20000, nsrc).astype(np.int32)
    raw_counts[3] = -1                      # TNULL 空值
    flags = RNG.integers(0, 4, nsrc).astype(np.int16)
    flags[5] = -1                           # TNULL 空值
    mag = (23.0 - 2.5 * np.log10(flux)).astype(np.float32)
    mag[6] = np.nan                         # 浮点列空值
    cols = [
        fits.Column(name="SRC_ID", format="J", array=np.arange(1, nsrc + 1)),
        fits.Column(name="RA", format="D", unit="deg", array=ra),
        fits.Column(name="DEC", format="D", unit="deg", array=dec),
        fits.Column(name="FLUX", format="E", unit="mJy", array=flux),
        fits.Column(name="RAW_COUNTS", format="J", unit="adu", array=raw_counts, null=-1),
        fits.Column(name="FLAGS", format="I", array=flags, null=-1),
        fits.Column(name="MAG", format="E", unit="mag", array=mag),
        fits.Column(name="LABEL", format="8A",
                    array=np.array([f"src-{i:03d}" for i in range(1, nsrc + 1)], dtype="S8")),
    ]
    table = fits.BinTableHDU.from_columns(cols, name="SOURCES")
    # 列标定：物理计数 = 存储值 × 0.5 + 100（TNULL=-1 判定在缩放之前）
    table.header["TSCAL5"] = 0.5
    table.header["TZERO5"] = 100.0

    path = out / "demo_multiext.fits"
    fits.HDUList([primary, ext, table]).writeto(path, overwrite=True, checksum=True)
    return path


def make_scaled_ints(out: Path) -> Path:
    """缩放整数样例：uint16（BZERO=32768）与 int16（BSCALE/BZERO/BLANK）。"""
    n = 64
    # uint16：物理值 0..65535，磁盘上存 int16 + BZERO=32768
    u = (RNG.uniform(0, 65535, (n, n))).astype(np.uint16)
    u[5, 5] = 65535
    u[0, 0] = 0
    primary = fits.PrimaryHDU(u)
    primary.header["BUNIT"] = "adu"
    primary.header["CTYPE1"] = "RA---CAR"
    primary.header["CTYPE2"] = "DEC--CAR"
    primary.header["CRVAL1"] = 10.0
    primary.header["CRVAL2"] = -20.0
    primary.header["CRPIX1"] = 32.0
    primary.header["CRPIX2"] = 32.0
    primary.header["CDELT1"] = -0.005
    primary.header["CDELT2"] = 0.005

    # int16 + BSCALE=0.1 + BZERO=1.5，BLANK=-32768 标记坏像素
    physical = RNG.uniform(-3000, 3000, (n, n))
    stored = np.round((physical - 1.5) / 0.1).astype(np.int16)
    stored[10, 10] = -32768
    stored[20, 21] = -32768
    img = fits.ImageHDU(stored, name="GAIN")
    img.header["BSCALE"] = 0.1
    img.header["BZERO"] = 1.5
    img.header["BLANK"] = -32768
    img.header["BUNIT"] = "electron"

    path = out / "demo_scaled_ints.fits"
    fits.HDUList([primary, img]).writeto(path, overwrite=True, checksum=True)
    return path


def make_varlen(out: Path) -> Path:
    """变长数组列样例：每行长度不同，读取时不得补齐。"""
    primary = fits.PrimaryHDU()
    lengths = [3, 7, 1, 12, 5]
    spectra = [RNG.uniform(0, 100, ln).astype(np.float32) for ln in lengths]
    peaks = [RNG.integers(100, 900, ln).astype(np.int32) for ln in lengths]
    cols = [
        fits.Column(name="OBJ_ID", format="J", array=np.arange(1, len(lengths) + 1)),
        fits.Column(name="WAVELEN", format="PE()", unit="nm", array=spectra),
        fits.Column(name="PEAKS", format="PJ()", unit="adu", array=peaks),
        fits.Column(name="QUALITY", format="J",
                    array=np.array([0, 1, -1, 0, 2], dtype=np.int32), null=-1),
    ]
    table = fits.BinTableHDU.from_columns(cols, name="SPECTRA")
    path = out / "demo_varlen.fits"
    fits.HDUList([primary, table]).writeto(path, overwrite=True, checksum=True)
    return path


def make_bad_checksum(out: Path) -> Path:
    """坏校验样例：3 个 HDU，中间一个数据被篡改，前后正常。"""
    n = 32
    ok1 = fits.PrimaryHDU(_sky_image(n).astype(np.float32))
    ok1.header["BUNIT"] = "adu"
    bad = fits.ImageHDU(RNG.uniform(0, 100, (n, n)).astype(np.float32), name="CORRUPT")
    cols = [fits.Column(name="IDX", format="J", array=np.arange(5))]
    ok2 = fits.BinTableHDU.from_columns(cols, name="LOG")

    path = out / "demo_bad_checksum.fits"
    fits.HDUList([ok1, bad, ok2]).writeto(path, overwrite=True, checksum=True)

    # 篡改第 2 个 HDU 的数据区：翻转若干字节，使 CHECKSUM/DATASUM 失效
    with fits.open(path) as hdul:
        offset = hdul[1].fileinfo()["datLoc"]
    with open(path, "r+b") as fh:
        fh.seek(offset)
        fh.write(b"\xde\xad\xbe\xef" * 4)
    return path


def make_unsupported_wcs(out: Path) -> Path:
    """不支持的投影样例：COP（圆锥投影，FITS 标准内但不在本站白名单）。"""
    n = 64
    img = _sky_image(n).astype(np.float32)
    primary = fits.PrimaryHDU(img)
    primary.header["CTYPE1"] = "RA---COP"
    primary.header["CTYPE2"] = "DEC--COP"
    primary.header["CRVAL1"] = 250.0
    primary.header["CRVAL2"] = 60.0
    primary.header["CRPIX1"] = 32.0
    primary.header["CRPIX2"] = 32.0
    primary.header["CDELT1"] = -0.02
    primary.header["CDELT2"] = 0.02
    primary.header["PV2_1"] = 45.0
    primary.header["PV2_2"] = 30.0
    path = out / "demo_unsupported_wcs.fits"
    fits.HDUList([primary]).writeto(path, overwrite=True, checksum=True)
    return path


def make_all(out_dir: str | Path) -> list[Path]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    makers = [make_multiext, make_scaled_ints, make_varlen,
              make_bad_checksum, make_unsupported_wcs]
    paths = [m(out) for m in makers]
    return paths


if __name__ == "__main__":
    dest = sys.argv[1] if len(sys.argv) > 1 else str(Path(__file__).resolve().parents[2] / "samples")
    for p in make_all(dest):
        print("generated:", p)
