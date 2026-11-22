import React, { useState } from 'react'
import { api } from '../api.js'

export default function ImageView({ fileId, hdu }) {
  const [pixel, setPixel] = useState(null)
  const [error, setError] = useState(null)
  const img = hdu.image
  const [nx, ny] = img.stats ? [img.shape[0], img.shape[1]] : [0, 0]

  async function onClick(ev) {
    const rect = ev.currentTarget.getBoundingClientRect()
    // 点击位置 -> 数组下标 -> FITS 1 基像素坐标（预览图第 1 行对应 FITS y=1）
    const col = Math.floor(((ev.clientX - rect.left) / rect.width) * nx)
    const row = Math.floor(((ev.clientY - rect.top) / rect.height) * ny)
    try {
      setPixel(await api.pixel(fileId, hdu.index, col + 1, row + 1))
      setError(null)
    } catch (e) {
      setError(e.message)
    }
  }

  return (
    <section className="panel">
      <h3>影像预览（物理值，已应用 BZERO/BSCALE；空值像素为品红色）</h3>
      {img.scaling?.has_scaling && (
        <p className="note">
          标定规则：物理值 = 存储值 × {img.scaling.bscale} + {img.scaling.bzero}
          {img.scaling.blank != null && <>；BLANK = {img.scaling.blank} 为空值</>}
          {img.raw_dtype && <>；磁盘存储类型 {img.raw_dtype}</>}
        </p>
      )}
      {img.stats && (
        <p className="note">
          范围 [{img.stats.min?.toPrecision(5)}, {img.stats.max?.toPrecision(5)}]，
          空值像素 {img.stats.null_pixels} / {img.stats.total_pixels}
          {img.bunit && <>，单位 {img.bunit}</>}
        </p>
      )}
      <div className="image-wrap">
        <img
          src={api.imageUrl(fileId, hdu.index)}
          alt={`HDU ${hdu.index} 预览`}
          onClick={onClick}
          crossOrigin="anonymous"
        />
      </div>
      <p className="note">点击像素查询坐标。预览图左上角为 FITS (1,1)，x 向右、y 向下。</p>
      {error && <div className="error-box">{error}</div>}
      {pixel && (
        <div className="pixel-box">
          <h4>像素查询结果</h4>
          <table className="kv">
            <tbody>
              <tr><td>FITS 像素（1 基）</td><td className="mono">({pixel.fits_pixel.x}, {pixel.fits_pixel.y})</td></tr>
              <tr><td>数组下标（0 基）</td><td className="mono">行 {pixel.array_index.row}, 列 {pixel.array_index.col}</td></tr>
              <tr><td>原始存储值</td><td className="mono">{String(pixel.raw_value)}</td></tr>
              <tr>
                <td>物理值</td>
                <td className="mono">
                  {pixel.is_null ? '空值（BLANK/NaN）' : pixel.physical_value}
                  {!pixel.is_null && img.scaling?.has_scaling &&
                    ` = ${pixel.raw_value} × ${pixel.scaling.bscale} + ${pixel.scaling.bzero}`}
                </td>
              </tr>
            </tbody>
          </table>
          {pixel.world ? (
            <>
              <h4>天球坐标（投影 {pixel.wcs.projection}）</h4>
              <table className="kv">
                <tbody>
                  <tr><td className="mono">{pixel.world.lon_type}</td><td className="mono">{pixel.world.lon.toFixed(7)} {pixel.world.lon_unit}</td></tr>
                  <tr><td className="mono">{pixel.world.lat_type}</td><td className="mono">{pixel.world.lat.toFixed(7)} {pixel.world.lat_unit}</td></tr>
                </tbody>
              </table>
              <h4>计算所用的头字段</h4>
              <table className="kv">
                <tbody>
                  {Object.entries(pixel.world.fields_used).map(([k, v]) => (
                    <tr key={k}><td className="mono">{k}</td><td className="mono">{String(v)}</td></tr>
                  ))}
                </tbody>
              </table>
            </>
          ) : (
            <div className="warn-box">
              <p>{pixel.wcs.reason}</p>
              {pixel.wcs.fields && Object.keys(pixel.wcs.fields).length > 0 && (
                <>
                  <h4>头部保留的原始坐标信息（不提供猜测的天空位置）</h4>
                  <table className="kv">
                    <tbody>
                      {Object.entries(pixel.wcs.fields).map(([k, v]) => (
                        <tr key={k}><td className="mono">{k}</td><td className="mono">{String(v)}</td></tr>
                      ))}
                    </tbody>
                  </table>
                </>
              )}
            </div>
          )}
        </div>
      )}
    </section>
  )
}
