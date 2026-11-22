"""FastAPI 入口：上传、HDU 列表、头部、影像预览、像素坐标、表数据、导出。"""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np
from astropy.io import fits
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import analysis, export, tables, wcs_support
from .images import render_preview
from .store import FileStore
from .tables import _jsonable

BASE_DIR = Path(__file__).resolve().parent.parent
PROJECT_DIR = BASE_DIR.parent

app = FastAPI(title="FITS 接收工作站", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

store = FileStore(
    upload_dir=os.environ.get("FITS_UPLOAD_DIR", PROJECT_DIR / "data" / "uploads"),
    samples_dir=os.environ.get("FITS_SAMPLES_DIR", PROJECT_DIR / "samples"),
)


def _entry(file_id: str) -> dict:
    try:
        return store.get(file_id)
    except KeyError:
        raise HTTPException(404, f"文件不存在: {file_id}")


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/samples")
def list_samples():
    return {"samples": store.list_samples()}


@app.post("/api/samples/{name}/load")
def load_sample(name: str):
    try:
        file_id = store.register_sample(name)
    except FileNotFoundError:
        raise HTTPException(404, f"样例不存在: {name}")
    entry = store.get(file_id)
    return {"file_id": file_id, "report": analysis.analyze_file(entry["path"], entry["name"])}


@app.post("/api/files")
def upload(file: UploadFile = File(...)):
    file_id = store.save_upload(file.filename or "uploaded.fits", file.file)
    entry = store.get(file_id)
    try:
        report = analysis.analyze_file(entry["path"], entry["name"])
    except Exception as exc:
        raise HTTPException(422, f"无法解析为 FITS 文件：{exc}")
    return {"file_id": file_id, "report": report}


@app.get("/api/files/{file_id}")
def get_report(file_id: str):
    entry = _entry(file_id)
    return analysis.analyze_file(entry["path"], entry["name"])


@app.get("/api/files/{file_id}/hdus/{hdu_index}/header")
def get_header(file_id: str, hdu_index: int):
    entry = _entry(file_id)
    try:
        return analysis.header_cards(entry["path"], hdu_index)
    except IndexError:
        raise HTTPException(404, f"HDU {hdu_index} 不存在")


@app.get("/api/files/{file_id}/hdus/{hdu_index}/image.png")
def get_image_preview(file_id: str, hdu_index: int, lo: float = 1.0, hi: float = 99.0):
    entry = _entry(file_id)
    with fits.open(entry["path"]) as hdul:
        try:
            hdu = hdul[hdu_index]
        except IndexError:
            raise HTTPException(404, f"HDU {hdu_index} 不存在")
        if isinstance(hdu, (fits.BinTableHDU, fits.TableHDU)):
            raise HTTPException(400, "表 HDU 无影像预览")
        data = hdu.data
        if data is None:
            raise HTTPException(400, "该 HDU 无影像数据")
        arr = np.asarray(data, dtype=np.float64)
        if arr.ndim > 2:
            arr = arr.reshape(-1, arr.shape[-2], arr.shape[-1])[0]
        try:
            png = render_preview(arr, lo, hi)
        except ValueError as exc:
            raise HTTPException(400, str(exc))
    return Response(content=png, media_type="image/png")


@app.get("/api/files/{file_id}/hdus/{hdu_index}/pixel")
def get_pixel(file_id: str, hdu_index: int, x: float, y: float):
    """像素查询：x/y 为 FITS 1 基像素坐标。

    返回原始存储值、物理值（应用 BZERO/BSCALE）、空值标记，
    以及（投影受支持时）天球坐标与计算所用的头字段。
    """
    entry = _entry(file_id)
    with fits.open(entry["path"]) as hdul, \
            fits.open(entry["path"], do_not_scale_image_data=True) as raw_hdul:
        try:
            hdu = hdul[hdu_index]
            raw_hdu = raw_hdul[hdu_index]
        except IndexError:
            raise HTTPException(404, f"HDU {hdu_index} 不存在")

        # 注意：astropy 在应用缩放读取 .data 后会从头部移除 BSCALE/BZERO/BLANK，
        # 必须先取出标定关键字，再访问数据。
        header = hdu.header
        scaling = {
            "bscale": _jsonable(header.get("BSCALE", 1)),
            "bzero": _jsonable(header.get("BZERO", 0)),
            "blank": _jsonable(header.get("BLANK")),
        }
        wcs_info = wcs_support.wcs_summary(header, header.get("NAXIS", 0))

        data = hdu.data
        if data is None or data.ndim != 2:
            raise HTTPException(400, "像素查询仅支持 2D 影像 HDU")

        # FITS 1 基 -> numpy 0 基（注意轴序：x 对应 NAXIS1/列，y 对应 NAXIS2/行）
        col = int(round(x)) - 1
        row = int(round(y)) - 1
        ny, nx = data.shape
        if not (0 <= col < nx and 0 <= row < ny):
            raise HTTPException(400, f"像素 ({x}, {y}) 超出影像范围 {nx}×{ny}")

        physical = _jsonable(data[row, col])
        raw = _jsonable(raw_hdu.data[row, col]) if raw_hdu.data is not None else None
        is_null = physical is None or (
            isinstance(physical, float) and not np.isfinite(physical))
        result = {
            "fits_pixel": {"x": x, "y": y, "convention": "FITS 1 基"},
            "array_index": {"row": row, "col": col, "convention": "numpy 0 基"},
            "raw_value": raw,
            "physical_value": None if is_null else physical,
            "is_null": bool(is_null),
            "scaling": scaling,
        }
        result["wcs"] = {"kind": wcs_info["kind"], "projection": wcs_info["projection"],
                         "reason": wcs_info["reason"]}
        if wcs_info["kind"] == "supported":
            try:
                result["world"] = wcs_support.pixel_to_world(header, x, y)
            except Exception as exc:
                result["wcs"] = {"kind": "unsupported", "projection": wcs_info["projection"],
                                 "reason": f"WCS 计算失败：{exc}。保留原始头字段，不给出猜测坐标。"}
                result["world"] = None
        else:
            # 不支持的投影：保留原始坐标信息，绝不猜测
            result["world"] = None
            result["wcs"]["fields"] = wcs_info["fields"]
        return result


@app.get("/api/files/{file_id}/hdus/{hdu_index}/table")
def get_table(file_id: str, hdu_index: int, start: int = 0, count: int = 100):
    entry = _entry(file_id)
    with fits.open(entry["path"]) as hdul:
        try:
            hdu = hdul[hdu_index]
        except IndexError:
            raise HTTPException(404, f"HDU {hdu_index} 不存在")
        if not isinstance(hdu, (fits.BinTableHDU, fits.TableHDU)):
            raise HTTPException(400, f"HDU {hdu_index}（{hdu.name}）不是表")
        return tables.table_rows(hdu, start=start, count=count)


class ExportRequest(BaseModel):
    hdu: int
    columns: list[str] | None = None
    max_rows: int = 50


@app.post("/api/files/{file_id}/export")
def post_export(file_id: str, req: ExportRequest):
    entry = _entry(file_id)
    try:
        return export.export_preview(entry["path"], req.hdu, req.columns, req.max_rows)
    except (IndexError, KeyError, TypeError) as exc:
        raise HTTPException(400, str(exc))


@app.post("/api/files/{file_id}/export.csv")
def post_export_csv(file_id: str, req: ExportRequest):
    entry = _entry(file_id)
    try:
        text = export.export_csv(entry["path"], req.hdu, req.columns, req.max_rows)
    except (IndexError, KeyError, TypeError) as exc:
        raise HTTPException(400, str(exc))
    return Response(
        content=text, media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="export.csv"'})


# 若前端已构建，直接由 FastAPI 托管静态页面
_dist = PROJECT_DIR / "frontend" / "dist"
if _dist.is_dir():
    app.mount("/", StaticFiles(directory=_dist, html=True), name="frontend")
