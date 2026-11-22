import React, { useEffect, useState } from 'react'
import { api } from '../api.js'

const PAGE = 50

function Cell({ cell, col }) {
  if (cell.is_null) return <td className="null-cell">空</td>
  if (col.variable_length) {
    return (
      <td className="mono varlen" title="变长数组：每行长度独立，未补齐">
        [{cell.value.map((v) => (v === null ? '空' : typeof v === 'number' ? +v.toFixed(4) : v)).join(', ')}]
        <span className="dim"> n={cell.length}</span>
      </td>
    )
  }
  const shown = typeof cell.value === 'number' ? +cell.value.toPrecision(8) : cell.value
  return (
    <td className="mono" title={cell.raw !== null && cell.raw !== undefined ? `存储值: ${cell.raw}` : undefined}>
      {String(shown)}
      {cell.raw !== null && cell.raw !== undefined && <span className="dim"> ({cell.raw})</span>}
    </td>
  )
}

export default function TableView({ fileId, hdu }) {
  const [start, setStart] = useState(0)
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    api.table(fileId, hdu.index, start, PAGE).then(setData).catch((e) => setError(e.message))
  }, [fileId, hdu.index, start])

  if (error) return <div className="error-box">{error}</div>
  if (!data) return <p>加载表格…</p>

  return (
    <section className="panel">
      <h3>列定义（含标定与空值规则）</h3>
      <table className="cards">
        <thead>
          <tr><th>#</th><th>列名</th><th>格式</th><th>单位</th><th>标定 TSCAL/TZERO</th><th>空值 TNULL</th><th>变长</th></tr>
        </thead>
        <tbody>
          {data.columns.map((c) => (
            <tr key={c.index}>
              <td className="mono">{c.index}</td>
              <td className="mono">{c.name}</td>
              <td className="mono">{c.format}</td>
              <td>{c.unit ?? ''}</td>
              <td className="mono">{c.scaled ? `${c.tscale ?? 1} / ${c.tzero ?? 0}` : '—'}</td>
              <td className="mono">{c.tnull ?? '—'}</td>
              <td>{c.variable_length ? '是（每行长度独立）' : ''}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="note">
        单元格显示物理值（已应用 TSCAL/TZERO）；括号内为原始存储值（仅对有标定或空值规则的列显示）。
        “空”表示 TNULL/NaN 空值，不是观测值。
      </p>
      <h3>
        数据行 {data.start}–{data.start + data.rows.length - 1} / 共 {data.total_rows} 行
      </h3>
      <div className="pager">
        <button disabled={start === 0} onClick={() => setStart(Math.max(0, start - PAGE))}>上一页</button>
        <button disabled={start + PAGE >= data.total_rows} onClick={() => setStart(start + PAGE)}>下一页</button>
      </div>
      <div className="table-scroll">
        <table className="cards">
          <thead>
            <tr>
              <th>行号</th>
              {data.columns.map((c) => <th key={c.index} className="mono">{c.name}</th>)}
            </tr>
          </thead>
          <tbody>
            {data.rows.map((row) => (
              <tr key={row.row}>
                <td className="mono dim">{row.row}</td>
                {row.cells.map((cell, i) => (
                  <Cell key={i} cell={cell} col={data.columns[i]} />
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}
