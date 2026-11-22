# FITS 接收工作站

从零实现的 FITS 文件接收与检查工作站：网页上传、HDU 列表、影像预览、表格导出。
样例文件全部由项目代码合成（`backend/samples/make_samples.py`），不连接任何观测机构。

技术栈：**astropy + FastAPI + React**。

## 快速开始

```bash
# 1. 后端环境
python3 -m venv .venv
.venv/bin/pip install -r backend/requirements.txt

# 2. 生成样例（输出到 samples/）
.venv/bin/python -m backend.samples.make_samples samples

# 3. 运行测试（21 项）
.venv/bin/python -m pytest backend/tests -q

# 4. 构建前端（或直接跳到 5 用 API）
cd frontend && npm install && npm run build && cd ..

# 5. 启动（前端已构建时由 FastAPI 直接托管）
.venv/bin/python -m uvicorn backend.app.main:app --port 8000
# 打开 http://127.0.0.1:8000
```

前端开发模式：`cd frontend && npm run dev`（Vite 代理 `/api` 到 8000 端口）。

## 内置样例（项目生成）

| 文件 | 覆盖点 |
|---|---|
| `demo_multiext.fits` | 多扩展：主影像(TAN 投影) + 影像扩展(SIN，含 NaN 空值) + 源表（TSCAL/TZERO 列标定、TNULL、NaN 空值） |
| `demo_scaled_ints.fits` | 缩放整数：uint16（BZERO=32768）+ int16（BSCALE=0.1 / BZERO=1.5 / BLANK=-32768） |
| `demo_varlen.fits` | 变长数组列 PE/PJ：5 行长度分别为 3/7/1/12/5 |
| `demo_bad_checksum.fits` | 坏校验：中间 HDU 数据被篡改，前后 HDU 正常 |
| `demo_unsupported_wcs.fits` | COP 圆锥投影：不在白名单内，保留原始坐标信息 |

## 需求实现对照

### 逐单元可用性检查（不因第一张图正常而判整文件正常）
`backend/app/analysis.py` 对每个 HDU 独立执行：CHECKSUM/DATASUM 校验、数据解码、
标定规则报告、WCS 白名单判定、表列解析。文件级状态取所有 HDU 的**最差**单元状态
（`demo_bad_checksum.fits` 中 PRIMARY 与 LOG 正常、CORRUPT 错误、文件整体降级）。

### 标定规则不遗漏（BZERO/BSCALE、空值、列缩放）
- 影像：物理值 = 存储值 × BSCALE + BZERO；BLANK 像素为空值。头部页有“标定规则汇总”，
  像素查询同时返回原始存储值与物理值。
- 表列：TSCALn/TZEROn 已应用于导出值；TNULLn 判定在**原始存储值**上进行
  （`backend/app/tables.py` 通过底层 recarray 取未缩放列），浮点列 NaN 为空值。
- 注意：astropy 应用缩放读取 `.data` 后会从头部移除 BSCALE/BZERO/BLANK，
  代码中一律先取标定关键字再访问数据。

### 变长数组列不补齐
P/Q 描述符列逐行返回原数组与 `length`（样例中 3/7/1/12/5），
导出与页面均按每行实际长度展示，绝不把填充值当作观测值。

### 有限且明确的 WCS 投影
白名单：`TAN / SIN / ZEA / CAR`（`backend/app/wcs_support.py`）。
- 支持：点击像素返回天球坐标 + 计算所用的全部头字段（CTYPE/CRVAL/CRPIX/CDELT/…）。
- 不支持：返回 `kind=unsupported` 与原因，保留头部原始坐标字段，`world` 恒为 null，
  绝不给出猜测的天空位置。

### 导出可追溯
导出预览每行带 0 基 FITS 行号；每列列出其解释依据的原始头字段
（TTYPEn/TFORMn/TUNITn/TSCALn/TZEROn/TNULLn）；CSV 文件头以注释行携带同样的溯源信息。

## API 一览

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/samples` | 样例列表 |
| POST | `/api/samples/{name}/load` | 加载样例，返回逐 HDU 报告 |
| POST | `/api/files` | 上传 FITS（multipart），返回报告 |
| GET | `/api/files/{fid}` | 重新生成报告 |
| GET | `/api/files/{fid}/hdus/{i}/header` | 头部卡片 + 逐条解释 + 标定汇总 |
| GET | `/api/files/{fid}/hdus/{i}/image.png` | 影像预览 PNG（物理值拉伸，空值品红色） |
| GET | `/api/files/{fid}/hdus/{i}/pixel?x=&y=` | 像素查询（FITS 1 基坐标） |
| GET | `/api/files/{fid}/hdus/{i}/table?start=&count=` | 表数据（含原始值/空值/变长长度） |
| POST | `/api/files/{fid}/export` | 导出预览 JSON（含溯源） |
| POST | `/api/files/{fid}/export.csv` | 导出 CSV |

## 已知限制（明确声明）

- 影像预览与像素查询仅支持 2D 影像（多维取第一片预览，像素查询拒绝）。
- WCS 仅白名单四投影；其余保留原始信息不猜测。
- 文件存储为内存登记 + 本地磁盘，重启后需重新上传。
