import React from 'react'
import { Badge } from '../App.jsx'

export default function HduList({ hdus, selected, onSelect }) {
  return (
    <section className="panel">
      <h2>HDU 列表（逐单元状态）</h2>
      <ul className="hdu-list">
        {hdus.map((h) => (
          <li key={h.index}>
            <button
              className={`hdu-item ${selected === h.index ? 'selected' : ''}`}
              onClick={() => onSelect(h.index)}
            >
              <span className="hdu-title">
                #{h.index} {h.name} <span className="mono dim">({h.type})</span>
              </span>
              <Badge status={h.status} />
            </button>
            <ul className="mini-checks">
              {h.checks.filter((c) => c.status !== 'ok').map((c) => (
                <li key={c.id} className={`check-${c.status}`}>{c.id}: {c.message}</li>
              ))}
            </ul>
          </li>
        ))}
      </ul>
    </section>
  )
}
