"""FITS 头部关键字解释表。

每个条目给出该关键字的用途说明，特别是标定（calibration）相关的
BZERO / BSCALE / BLANK / TSCAL / TZEROn / TNULLn 等，页面在展示头部卡片时
逐条附上解释，保证标定规则不被遗漏。
"""

import re

# 精确匹配的关键字解释
_EXACT = {
    "SIMPLE": "文件符合 FITS 标准（主 HDU 的第一个关键字，必须为 T）。",
    "BITPIX": "每个像素的位数：8/16/32/64 为整数（补码），-32/-64 为 IEEE 浮点。注意：当 BZERO=32768 时，磁盘上的 int16 实际表示 uint16。",
    "NAXIS": "数据数组的维数。0 表示本 HDU 无数据。",
    "EXTEND": "主 HDU 之后可能跟随扩展 HDU（T/F）。",
    "XTENSION": "扩展类型：IMAGE（影像）、BINTABLE（二进制表）、TABLE（ASCII 表）。",
    "EXTNAME": "扩展名称，用于在 HDU 列表中标识本扩展。",
    "EXTVER": "扩展版本号，同名扩展用版本区分。",
    "PCOUNT": "扩展数据中参数区字节数。二进制表中通常用于变长数组堆（heap）的大小。",
    "GCOUNT": "组计数，标准扩展中恒为 1。",
    "TFIELDS": "表中列（字段）的数量。",
    "BSCALE": "标定规则：物理值 = 存储值 × BSCALE + BZERO。读取时必须应用，否则得到的是未标定的原始整数。",
    "BZERO": "标定规则：物理值 = 存储值 × BSCALE + BZERO。BZERO=32768 且 BITPIX=16 是 FITS 表示无符号 uint16 的标准方式。",
    "BLANK": "整型影像的空值标记：存储值等于 BLANK 的像素为无效（空）像素，不得当作观测值。浮点影像用 NaN 表示空值。",
    "BUNIT": "物理量的单位（应用 BSCALE/BZERO 之后的单位）。",
    "CHECKSUM": "整个 HDU（头+数据）的校验和，用于完整性验证。校验失败说明文件在传输/存储中被改动。",
    "DATASUM": "仅数据部分的校验和。CHECKSUM 验证依赖它。",
    "RADESYS": "天球坐标参考架（如 ICRS、FK5）。",
    "EQUINOX": "坐标历元（儒略年），仅对 FK4/FK5 等参考架有意义。",
    "DATE-OBS": "观测开始时间（ISO 格式，UTC）。",
    "TELESCOP": "望远镜标识。",
    "INSTRUME": "仪器标识。",
    "OBJECT": "观测目标名称。",
    "EXPTIME": "曝光时间（秒）。",
    "COMMENT": "注释卡片，无数据含义。",
    "HISTORY": "历史记录卡片。",
    "END": "头部结束标记。",
}

# 带编号/下标的模式（按正则匹配）
_PATTERNS = [
    (re.compile(r"^NAXIS(\d+)$"),
     lambda m: f"第 {m.group(1)} 维的像素数。"),
    (re.compile(r"^TTYPE(\d+)$"),
     lambda m: f"第 {m.group(1)} 列的列名。导出预览中以此列名引用该列。"),
    (re.compile(r"^TFORM(\d+)$"),
     lambda m: (f"第 {m.group(1)} 列的存储格式。代码：L 逻辑 / X 位 / B 字节 / I 16位整 / J 32位整 / K 64位整 / "
                f"A 字符 / E 单精度浮点 / D 双精度浮点 / C,M 复数；前缀数字为重复次数；"
                f"P/Q 前缀表示变长数组（描述符+堆存储），每行长度独立，读取时不得补齐。")),
    (re.compile(r"^TUNIT(\d+)$"),
     lambda m: f"第 {m.group(1)} 列物理量的单位（应用 TSCAL/TZERO 之后）。"),
    (re.compile(r"^TSCAL(\d+)$"),
     lambda m: f"第 {m.group(1)} 列标定规则：物理值 = 存储值 × TSCAL{m.group(1)} + TZERO{m.group(1)}。导出前必须应用。"),
    (re.compile(r"^TZERO(\d+)$"),
     lambda m: f"第 {m.group(1)} 列标定规则：物理值 = 存储值 × TSCAL{m.group(1)} + TZERO{m.group(1)}。常用于把整数列映射为物理量。"),
    (re.compile(r"^TNULL(\d+)$"),
     lambda m: f"第 {m.group(1)} 列的空值标记：存储值等于该值的单元为无效单元，不得当作观测值（判定在应用 TSCAL/TZERO 之前进行）。"),
    (re.compile(r"^TDISP(\d+)$"),
     lambda m: f"第 {m.group(1)} 列的推荐显示格式。"),
    (re.compile(r"^TDIM(\d+)$"),
     lambda m: f"第 {m.group(1)} 列固定长度数组单元的维度形状。"),
    (re.compile(r"^CTYPE(\d+)$"),
     lambda m: (f"第 {m.group(1)} 轴的坐标类型与投影。天球轴形如 'RA---TAN'，后三个字符是投影代码。"
                f"本站仅支持有限的投影集合，不支持的投影会保留原始信息并明确标注。")),
    (re.compile(r"^CRVAL(\d+)$"),
     lambda m: f"第 {m.group(1)} 轴参考点的世界坐标值。"),
    (re.compile(r"^CRPIX(\d+)$"),
     lambda m: f"第 {m.group(1)} 轴参考点的像素坐标（FITS 约定从 1 开始计数）。"),
    (re.compile(r"^CDELT(\d+)$"),
     lambda m: f"第 {m.group(1)} 轴在参考点处的像素增量（世界坐标/像素）。"),
    (re.compile(r"^CUNIT(\d+)$"),
     lambda m: f"第 {m.group(1)} 轴世界坐标单位。"),
    (re.compile(r"^CD(\d+)_(\d+)$"),
     lambda m: f"线性变换矩阵元 CD{m.group(1)}_{m.group(2)}：像素到世界坐标的旋转+缩放（与 CDELT 二选一）。"),
    (re.compile(r"^PC(\d+)_(\d+)$"),
     lambda m: f"线性变换矩阵元 PC{m.group(1)}_{m.group(2)}：与 CDELT 配合的旋转矩阵。"),
    (re.compile(r"^PV(\d+)_(\d+)$"),
     lambda m: f"投影参数 PV{m.group(1)}_{m.group(2)}，部分投影需要。"),
    (re.compile(r"^LONPOLE$"), lambda m: "参考点处本初经线（度）。"),
    (re.compile(r"^LATPOLE$"), lambda m: "参考点处本初纬线（度）。"),
]


def explain_keyword(keyword: str) -> str | None:
    """返回关键字的解释；未知关键字返回 None。"""
    if keyword in _EXACT:
        return _EXACT[keyword]
    for pattern, fn in _PATTERNS:
        m = pattern.match(keyword)
        if m:
            return fn(m)
    return None
