"""端到端 API 测试：逐单元验证、标定规则、变长列、WCS 策略、导出溯源。"""

import io

import numpy as np
import pytest

SAMPLES = [
    "demo_multiext.fits",
    "demo_scaled_ints.fits",
    "demo_varlen.fits",
    "demo_bad_checksum.fits",
    "demo_unsupported_wcs.fits",
]


def test_all_samples_present(loaded):
    assert set(loaded) == set(SAMPLES)


# ---------- 多扩展与逐单元状态 ----------

def test_multiext_structure(loaded):
    _, report = loaded["demo_multiext.fits"]
    assert report["status"] == "ok"
    assert [h["type"] for h in report["hdus"]] == ["PRIMARY", "IMAGE", "BINTABLE"]
    assert [h["name"] for h in report["hdus"]] == ["PRIMARY", "BACKGROUND", "SOURCES"]
    for h in report["hdus"]:
        assert h["status"] == "ok"


def test_bad_checksum_flags_only_corrupt_hdu(loaded):
    """坏校验样例：只有被篡改的 HDU 报错，其余 HDU 保持正常，文件整体降级。"""
    _, report = loaded["demo_bad_checksum.fits"]
    assert report["status"] == "degraded"
    by_name = {h["name"]: h for h in report["hdus"]}
    assert by_name["PRIMARY"]["status"] == "ok"
    assert by_name["LOG"]["status"] == "ok"
    corrupt = by_name["CORRUPT"]
    assert corrupt["status"] == "error"
    failed = {c["id"] for c in corrupt["checks"] if c["status"] == "error"}
    assert "checksum" in failed and "datasum" in failed
    # 文件级汇总不允许被首个正常 HDU 掩盖
    assert report["summary"]["error"] == 1
    assert report["worst_unit_status"] == "error"


# ---------- BZERO/BSCALE 与空值 ----------

def test_uint16_bzero_documented(loaded):
    _, report = loaded["demo_scaled_ints.fits"]
    primary = report["hdus"][0]
    scaling = primary["image"]["scaling"]
    assert scaling["bzero"] == 32768
    assert scaling["has_scaling"] is True
    assert primary["image"]["raw_dtype"] == ">i2"  # 磁盘上仍是 int16


def test_scaled_pixel_values_and_blank(client, loaded):
    fid, _ = loaded["demo_scaled_ints.fits"]
    # GAIN 扩展：BSCALE=0.1, BZERO=1.5, BLANK=-32768
    r = client.get(f"/api/files/{fid}/hdus/1/pixel", params={"x": 1, "y": 1})
    assert r.status_code == 200
    body = r.json()
    assert body["scaling"] == {"bscale": 0.1, "bzero": 1.5, "blank": -32768}
    assert body["physical_value"] == pytest.approx(
        body["raw_value"] * 0.1 + 1.5, rel=1e-6)
    # BLANK 像素（存储值 -32768，位于 FITS 坐标 (11, 11) 与 (22, 21)）
    for x, y in [(11, 11), (22, 21)]:
        b = client.get(f"/api/files/{fid}/hdus/1/pixel",
                       params={"x": x, "y": y}).json()
        assert b["raw_value"] == -32768
        assert b["is_null"] is True
        assert b["physical_value"] is None


def test_uint16_extremes(client, loaded):
    fid, _ = loaded["demo_scaled_ints.fits"]
    # 写入时 u[5,5]=65535（FITS 坐标 x=6,y=6），u[0,0]=0
    b = client.get(f"/api/files/{fid}/hdus/0/pixel", params={"x": 6, "y": 6}).json()
    assert b["physical_value"] == 65535
    b = client.get(f"/api/files/{fid}/hdus/0/pixel", params={"x": 1, "y": 1}).json()
    assert b["physical_value"] == 0


# ---------- 表：列标定、空值、变长数组 ----------

def test_table_column_scaling_and_nulls(client, loaded):
    fid, _ = loaded["demo_multiext.fits"]
    r = client.get(f"/api/files/{fid}/hdus/2/table", params={"count": 50})
    assert r.status_code == 200
    body = r.json()
    cols = {c["name"]: c for c in body["columns"]}
    rc = cols["RAW_COUNTS"]
    assert rc["scaled"] is True and rc["tscale"] == 0.5 and rc["tzero"] == 100.0
    assert rc["tnull"] == -1
    idx = [c["name"] for c in body["columns"]].index("RAW_COUNTS")
    for row in body["rows"]:
        cell = row["cells"][idx]
        if cell["raw"] == -1:
            assert cell["is_null"] is True and cell["value"] is None
        else:
            assert cell["is_null"] is False
            assert cell["value"] == pytest.approx(cell["raw"] * 0.5 + 100.0)
    # 浮点列 NaN 空值
    midx = [c["name"] for c in body["columns"]].index("MAG")
    nulls = [row["row"] for row in body["rows"] if row["cells"][midx]["is_null"]]
    assert nulls == [6]


def test_variable_length_rows_keep_own_length(client, loaded):
    fid, _ = loaded["demo_varlen.fits"]
    body = client.get(f"/api/files/{fid}/hdus/1/table", params={"count": 50}).json()
    cols = {c["name"]: c for c in body["columns"]}
    assert cols["WAVELEN"]["variable_length"] is True
    assert cols["PEAKS"]["variable_length"] is True
    expected = [3, 7, 1, 12, 5]
    wi = [c["name"] for c in body["columns"]].index("WAVELEN")
    pi = [c["name"] for c in body["columns"]].index("PEAKS")
    for row, ln in zip(body["rows"], expected):
        wcell = row["cells"][wi]
        pcell = row["cells"][pi]
        # 每行自己的长度，绝不补齐到最大长度 12
        assert wcell["length"] == ln
        assert len(wcell["value"]) == ln
        assert pcell["length"] == ln
        assert len(pcell["value"]) == ln


def test_varlen_null_column(client, loaded):
    fid, _ = loaded["demo_varlen.fits"]
    body = client.get(f"/api/files/{fid}/hdus/1/table", params={"count": 50}).json()
    qi = [c["name"] for c in body["columns"]].index("QUALITY")
    nulls = [row["row"] for row in body["rows"] if row["cells"][qi]["is_null"]]
    assert nulls == [2]  # 写入时 quality[2] = -1 = TNULL


# ---------- WCS：支持 / 不支持 ----------

def test_wcs_supported_tan(client, loaded):
    fid, _ = loaded["demo_multiext.fits"]
    # 参考点像素 (51, 51) 应映射到 CRVAL (180, 45)
    r = client.get(f"/api/files/{fid}/hdus/0/pixel", params={"x": 51, "y": 51})
    body = r.json()
    assert body["wcs"]["kind"] == "supported"
    assert body["wcs"]["projection"] == "TAN"
    assert body["world"]["lon"] == pytest.approx(180.0, abs=1e-9)
    assert body["world"]["lat"] == pytest.approx(45.0, abs=1e-9)
    used = body["world"]["fields_used"]
    for key in ("CTYPE1", "CRVAL1", "CRPIX1", "CDELT1"):
        assert key in used


def test_wcs_unsupported_keeps_original_no_guess(client, loaded):
    fid, _ = loaded["demo_unsupported_wcs.fits"]
    r = client.get(f"/api/files/{fid}/hdus/0/pixel", params={"x": 32, "y": 32})
    body = r.json()
    assert body["wcs"]["kind"] == "unsupported"
    assert body["wcs"]["projection"] == "COP"
    assert body["world"] is None  # 绝不给出猜测的天空位置
    fields = body["wcs"]["fields"]
    assert fields["CTYPE1"] == "RA---COP"
    assert fields["CRVAL1"] == 250.0  # 原始坐标信息完整保留


def test_wcs_status_in_report(loaded):
    _, report = loaded["demo_unsupported_wcs.fits"]
    hdu = report["hdus"][0]
    assert hdu["image"]["wcs"]["kind"] == "unsupported"
    wcs_check = [c for c in hdu["checks"] if c["id"] == "wcs"][0]
    assert wcs_check["status"] == "warning"


# ---------- 头部解释与标定规则展示 ----------

def test_header_explanations(client, loaded):
    fid, _ = loaded["demo_scaled_ints.fits"]
    body = client.get(f"/api/files/{fid}/hdus/1/header").json()
    by_kw = {c["keyword"]: c for c in body["cards"]}
    assert "物理值" in by_kw["BSCALE"]["explanation"]
    assert "空值" in by_kw["BLANK"]["explanation"]
    cal = body["calibration"]
    assert cal["bscale"] == 0.1 and cal["bzero"] == 1.5 and cal["blank"] == -32768


def test_header_table_calibration(client, loaded):
    fid, _ = loaded["demo_multiext.fits"]
    body = client.get(f"/api/files/{fid}/hdus/2/header").json()
    by_kw = {c["keyword"]: c for c in body["cards"]}
    assert "TSCAL5" in by_kw and "标定" in by_kw["TSCAL5"]["explanation"]
    assert "TNULL5" in by_kw and "空值" in by_kw["TNULL5"]["explanation"]
    assert body["calibration"]["column_scaling"]["TSCAL5/TZERO5"] == [0.5, 100.0]
    assert body["calibration"]["column_nulls"]["TNULL5"] == -1


# ---------- 影像预览 ----------

def test_image_preview_png(client, loaded):
    fid, _ = loaded["demo_multiext.fits"]
    r = client.get(f"/api/files/{fid}/hdus/0/image.png")
    assert r.status_code == 200
    assert r.content[:8] == b"\x89PNG\r\n\x1a\n"
    # 表 HDU 无影像
    r = client.get(f"/api/files/{fid}/hdus/2/image.png")
    assert r.status_code == 400


# ---------- 导出与溯源 ----------

def test_export_preview_provenance(client, loaded):
    fid, _ = loaded["demo_multiext.fits"]
    r = client.post(f"/api/files/{fid}/export",
                    json={"hdu": 2, "columns": ["SRC_ID", "RAW_COUNTS"], "max_rows": 8})
    assert r.status_code == 200
    body = r.json()
    assert body["hdu"] == 2 and body["hdu_name"] == "SOURCES"
    # 行号可追溯
    assert [row["row"] for row in body["rows"]] == list(range(8))
    # 列溯源到头字段
    rc = [c for c in body["columns"] if c["name"] == "RAW_COUNTS"][0]
    assert rc["header_refs"]["TSCAL5"] == 0.5
    assert rc["header_refs"]["TZERO5"] == 100.0
    assert rc["header_refs"]["TNULL5"] == -1
    # 空值行（raw=-1 在第 3 行）导出为空并标注
    row3 = body["rows"][3]
    assert row3["values"]["RAW_COUNTS"] is None
    assert "RAW_COUNTS" in row3["nulls"]
    # 物理值已缩放
    row0 = body["rows"][0]
    assert row0["values"]["RAW_COUNTS"] is not None


def test_export_varlen_not_padded(client, loaded):
    fid, _ = loaded["demo_varlen.fits"]
    body = client.post(f"/api/files/{fid}/export",
                       json={"hdu": 1, "columns": ["OBJ_ID", "WAVELEN"]}).json()
    lengths = [len(row["values"]["WAVELEN"]) for row in body["rows"]]
    assert lengths == [3, 7, 1, 12, 5]
    assert body["rows"][0]["lengths"]["WAVELEN"] == 3


def test_export_csv(client, loaded):
    fid, _ = loaded["demo_multiext.fits"]
    r = client.post(f"/api/files/{fid}/export.csv",
                    json={"hdu": 2, "columns": ["SRC_ID", "RA"], "max_rows": 5})
    assert r.status_code == 200
    text = r.text
    assert "# provenance: hdu=2" in text
    assert "TTYPE2" in text  # RA 列的头字段溯源
    lines = [ln for ln in text.splitlines() if not ln.startswith("#")]
    assert lines[0].startswith("fits_row,")
    assert len(lines) == 2 + 5  # 表头 + 单位行 + 5 行数据


def test_export_rejects_image_hdu(client, loaded):
    fid, _ = loaded["demo_multiext.fits"]
    r = client.post(f"/api/files/{fid}/export", json={"hdu": 0})
    assert r.status_code == 400


# ---------- 上传 ----------

def test_upload_roundtrip(client, loaded, tmp_path):
    from astropy.io import fits
    data = np.arange(16, dtype=np.int16).reshape(4, 4)
    h = fits.PrimaryHDU(data)
    buf = io.BytesIO()
    h.writeto(buf)
    buf.seek(0)
    r = client.post("/api/files", files={"file": ("rt.fits", buf, "application/fits")})
    assert r.status_code == 200
    body = r.json()
    assert body["report"]["hdus"][0]["type"] == "PRIMARY"
    fid = body["file_id"]
    p = client.get(f"/api/files/{fid}/hdus/0/pixel", params={"x": 4, "y": 4}).json()
    assert p["physical_value"] == 15


def test_upload_rejects_non_fits(client):
    r = client.post("/api/files", files={"file": ("x.fits", io.BytesIO(b"not fits"), "application/fits")})
    assert r.status_code == 422
