import React, { useEffect, useState } from 'react'
import { api } from '../api.js'

export default function HeaderView({ fileId, hdu }) {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    setData(null)
    api.header(fileId, hdu.index).then(setData).catch((e) => setError(e.message))
  }, [fileId, hdu.index])

  if (error) return <div className="error-box">{error}</div>
  if (!data) return <p>加载头部…</p>

  const cal = data.calibration
  const hasImageCal = cal.bscale != null || cal.bzero != null || cal.blank != null
  const colScaling = Object.entries(cal.column_scaling)
  const colNulls = Object.entries(cal.column_nulls)

  return (
    <section className="panel">
      <h3>标定规则汇总</h3>
      <div className="cal-box">
        {hasImageCal && (
          <p>
            影像标定：物理值 = 存储值 × BSCALE({cal.bscale ?? 1}) + BZERO({cal.bzero ?? 0})
            {cal.blank != null && <>；BLANK = {cal.blank} 的像素为空值</>}
          </p>
        )}
        {colScaling.length > 0 && (
          <p>列标定：{colScaling.map(([k, [s, z]]) => `${k} = ${s ?? 1} / ${z ?? 0}`).join('；')}
            （物理值 = 存储值 × TSCAL + TZERO）</p>
        )}
        {colNulls.length > 0 && (
          <p>列空值：{colNulls.map(([k, v]) => `${k} = ${v}`).join('；')}
            （存储值等于该值的单元为空，判定在缩放之前）</p>
        )}
        {!hasImageCal && colScaling.length === 0 && colNulls.length === 0 && (
          <p>本 HDU 无 BZERO/BSCALE/BLANK 与 TSCAL/TZERO/TNULL 标定规则。</p>
        )}
      </div>
      <h3>头部卡片（{data.cards.length} 张）</h3>
      <table className="cards">
        <thead>
          <tr><th>关键字</th><th>值</th><th>注释</th><th>解释</th></tr>
        </thead>
        <tbody>
          {data.cards.map((c, i) => (
            <tr key={`${c.keyword}-${i}`}>
              <td className="mono">{c.keyword}</td>
              <td className="mono">{c.value === true ? 'T' : c.value === false ? 'F' : String(c.value ?? '')}</td>
              <td className="dim">{c.comment ?? ''}</td>
              <td>{c.explanation ?? <span className="dim">—</span>}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  )
}
