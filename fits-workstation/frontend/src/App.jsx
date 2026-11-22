import React, { useEffect, useState } from 'react'
import { api } from './api.js'
import HduList from './components/HduList.jsx'
import HeaderView from './components/HeaderView.jsx'
import ImageView from './components/ImageView.jsx'
import TableView from './components/TableView.jsx'
import ExportPanel from './components/ExportPanel.jsx'

const STATUS_LABEL = { ok: '正常', warning: '警告', error: '错误' }

export function Badge({ status }) {
  return <span className={`badge badge-${status}`}>{STATUS_LABEL[status] ?? status}</span>
}

export default function App() {
  const [samples, setSamples] = useState([])
  const [fileId, setFileId] = useState(null)
  const [report, setReport] = useState(null)
  const [selected, setSelected] = useState(0)
  const [tab, setTab] = useState('image')
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    api.samples().then((r) => setSamples(r.samples)).catch((e) => setError(e.message))
  }, [])

  async function accept(result) {
    setFileId(result.file_id)
    setReport(result.report)
    setSelected(0)
    setError(null)
    const first = result.report.hdus[0]
    setTab(first && first.image && first.image.stats ? 'image' : first?.table ? 'table' : 'header')
  }

  async function onUpload(ev) {
    const f = ev.target.files?.[0]
    if (!f) return
    setBusy(true)
    try { accept(await api.upload(f)) } catch (e) { setError(e.message) } finally { setBusy(false) }
  }

  async function onSample(name) {
    setBusy(true)
    try { accept(await api.loadSample(name)) } catch (e) { setError(e.message) } finally { setBusy(false) }
  }

  const hdu = report?.hdus[selected]
  const tabs = []
  if (hdu) {
    if (hdu.image && hdu.image.stats) tabs.push(['image', '影像预览'])
    if (hdu.table) tabs.push(['table', '表格数据'])
    tabs.push(['header', '头部与标定'])
    tabs.push(['checks', '单元检查'])
    if (hdu.table) tabs.push(['export', '导出'])
  }

  return (
    <div className="layout">
      <aside className="sidebar">
        <h1>FITS 接收工作站</h1>
        <section className="panel">
          <h2>接收文件</h2>
          <label className="upload-btn">
            {busy ? '处理中…' : '上传 FITS 文件'}
            <input type="file" accept=".fits,.fit,.fts" onChange={onUpload} hidden />
          </label>
          <h3>内置样例（项目生成）</h3>
          <ul className="sample-list">
            {samples.map((s) => (
              <li key={s.name}>
                <button onClick={() => onSample(s.name)}>{s.name}</button>
                <span className="size">{(s.size / 1024).toFixed(1)} KB</span>
              </li>
            ))}
          </ul>
        </section>
        {error && <div className="error-box">{error}</div>}
        {report && (
          <>
            <section className={`panel file-status file-${report.status}`}>
              <h2>文件级状态：{report.status === 'ok' ? '正常' : '降级'}</h2>
              <p className="mono">{report.name}</p>
              <p>
                共 {report.summary.total_hdus} 个 HDU：
                正常 {report.summary.ok} / 警告 {report.summary.warning} / 错误 {report.summary.error}
              </p>
              <p className="note">{report.status_note}</p>
            </section>
            <HduList hdus={report.hdus} selected={selected} onSelect={(i) => {
              setSelected(i)
              const h = report.hdus[i]
              setTab(h.image && h.image.stats ? 'image' : h.table ? 'table' : 'header')
            }} />
          </>
        )}
      </aside>
      <main className="main">
        {!report && <p className="placeholder">上传 FITS 文件或加载内置样例开始检查。</p>}
        {report && hdu && (
          <>
            <nav className="tabs">
              {tabs.map(([key, label]) => (
                <button key={key} className={tab === key ? 'active' : ''} onClick={() => setTab(key)}>
                  {label}
                </button>
              ))}
            </nav>
            <div className="hdu-heading">
              <h2>HDU {hdu.index} — {hdu.name} <span className="mono">({hdu.type})</span></h2>
              <Badge status={hdu.status} />
            </div>
            {tab === 'image' && <ImageView fileId={fileId} hdu={hdu} />}
            {tab === 'table' && <TableView fileId={fileId} hdu={hdu} />}
            {tab === 'header' && <HeaderView fileId={fileId} hdu={hdu} />}
            {tab === 'export' && <ExportPanel fileId={fileId} hdu={hdu} />}
            {tab === 'checks' && (
              <section className="panel">
                <h3>本 HDU 的单元检查</h3>
                <ul className="check-list">
                  {hdu.checks.map((c) => (
                    <li key={c.id} className={`check check-${c.status}`}>
                      <Badge status={c.status} />
                      <span className="mono check-id">{c.id}</span> {c.message}
                    </li>
                  ))}
                </ul>
              </section>
            )}
          </>
        )}
      </main>
    </div>
  )
}
