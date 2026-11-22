const BASE = '/api'

async function request(path, options = {}) {
  const r = await fetch(BASE + path, options)
  if (!r.ok) {
    let detail = r.statusText
    try { detail = (await r.json()).detail ?? detail } catch { /* 非 JSON */ }
    throw new Error(detail)
  }
  return r.json()
}

export const api = {
  samples: () => request('/samples'),
  loadSample: (name) => request(`/samples/${encodeURIComponent(name)}/load`, { method: 'POST' }),
  upload: async (file) => {
    const fd = new FormData()
    fd.append('file', file)
    return request('/files', { method: 'POST', body: fd })
  },
  report: (fid) => request(`/files/${fid}`),
  header: (fid, hdu) => request(`/files/${fid}/hdus/${hdu}/header`),
  table: (fid, hdu, start = 0, count = 100) =>
    request(`/files/${fid}/hdus/${hdu}/table?start=${start}&count=${count}`),
  pixel: (fid, hdu, x, y) =>
    request(`/files/${fid}/hdus/${hdu}/pixel?x=${x}&y=${y}`),
  exportPreview: (fid, body) =>
    request(`/files/${fid}/export`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
  exportCsv: async (fid, body) => {
    const r = await fetch(`${BASE}/files/${fid}/export.csv`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    if (!r.ok) throw new Error((await r.json()).detail ?? r.statusText)
    return r.blob()
  },
  imageUrl: (fid, hdu) => `${BASE}/files/${fid}/hdus/${hdu}/image.png`,
}
