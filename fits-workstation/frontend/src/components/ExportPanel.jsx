import React, { useState } from 'react'
import { api } from '../api.js'

export default function ExportPanel({ fileId, hdu }) {
  const allCols = hdu.table.columns.map((c) => c.name)
  const [selected, setSelected] = useState(allCols)
  const [maxRows, setMaxRows] = useState(50)
  const [preview, setPreview] = useState(null)
  const [error, setError] = useState(null)

  function toggle(name) {
    setSelected((s) => (s.includes(name) ? s.filter((n) => n !== name) : [...s, name]))
  }

  async function run() {
    setError(null)
    try {
      setPreview(await api.exportPreview(fileId, { hdu: hdu.index, columns: selected, max_rows: maxRows }))
    } catch (e) { setError(e.message) }
  }

  async function downloadCsv() {
    setError(null)
    try {
      const blob = await api.exportCsv(fileId, { hdu: hdu.index, columns: selected, max_rows: 100000 })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `hdu${hdu.index}_export.csv`
      a.click()
      URL.revokeObjectURL(url)
    } catch (e) { setError(e.message) }
  }

  return (
    <section className="panel">
      <h3>选择导出字段（HDU {hdu.index} — {hdu.name}）</h3>
      <div className="col-picker">
        {hdu.table.columns.map((c) => (
          <label key={c.name} className="col-option">
            <input type="checkbox" checked={selected.includes(c.name)} onChange={() => toggle(c.name)} />
            <span className="mono">{c.name}</span>
            {c.unit && <span className="dim"> [{c.unit}]</span>}
            {c.variable_length && <span className="tag">变长</span>}
            {c.scaled && <span className="tag">标定</span>}
            {c.tnull !== null && <span className="tag">空值规则</span>}
          </label>
        ))}
      </div>
      <div className="export-controls">
        <label>
          预览行数
          <input type="number" min="1" max="10000" value={maxRows}
                 onChange={(e) => setMaxRows(Number(e.target.value))} />
        </label>
        <button onClick={run} disabled={selected.length === 0}>生成导出预览</button>
        <button onClick={downloadCsv} disabled={selected.length === 0}>下载 CSV（全量）</button>
      </div>
      {error && <div className="error-box">{error}</div>}
      {preview && (
        <>
          <h3>导出预览（{preview.returned_rows} / {preview.total_rows} 行）</h3>
          <div className="table-scroll">
            <table className="cards">
              <thead>
                <tr>
                  <th className="mono">fits_row</th>
                  {preview.columns.map((c) => (
                    <th key={c.name} className="mono">{c.name}{c.unit ? ` (${c.unit})` : ''}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {preview.rows.map((row) => (
                  <tr key={row.row}>
                    <td className="mono dim">{row.row}</td>
                    {preview.columns.map((c) => {
                      const v = row.values[c.name]
                      return (
                        <td key={c.name} className={`mono ${row.nulls.includes(c.name) ? 'null-cell' : ''}`}>
                          {v === null ? '空' : Array.isArray(v)
                            ? `[${v.map((x) => (x === null ? '空' : +Number(x).toFixed(4))).join(', ')}] n=${v.length}`
                            : typeof v === 'number' ? +v.toPrecision(8) : String(v)}
                        </td>
                      )
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <h3>溯源信息</h3>
          <div className="cal-box">
            <p>来源：HDU {preview.provenance.hdu_index}（{preview.provenance.hdu_name}），
              行号为{preview.provenance.row_numbering}。</p>
            <p>{preview.provenance.scaling_rule}</p>
            <p>{preview.provenance.variable_length_rule}</p>
            <p>生成时间：{preview.provenance.generated_at}</p>
            {preview.columns.map((c) => (
              <p key={c.name} className="mono">
                {c.name} ⇐ {Object.entries(c.header_refs).map(([k, v]) => `${k}=${v}`).join(', ')}
              </p>
            ))}
          </div>
        </>
      )}
    </section>
  )
}
