import { useEffect, useMemo, useState } from 'react'
import { fileUrl } from '../api'
import type { Job, TreeProps } from '../types'

const COLS: { key: keyof TreeProps; label: string; num?: boolean }[] = [
  { key: 'tree_id', label: 'Tree ID' },
  { key: 'species', label: 'Species' },
  { key: 'species_confidence', label: 'Species conf.', num: true },
  { key: 'detection_score', label: 'Detection conf.', num: true },
  { key: 'height_m', label: 'Height (m)', num: true },
  { key: 'crown_area_m2', label: 'Crown (m²)', num: true },
  { key: 'crown_diameter_m', label: 'Crown ⌀ (m)', num: true },
  { key: 'local_canopy_density_pct', label: 'Local density (%)', num: true },
  { key: 'fsi_density_class', label: 'Class' },
  { key: 'ndvi', label: 'NDVI', num: true },
  { key: 'latitude', label: 'Latitude', num: true },
  { key: 'longitude', label: 'Longitude', num: true },
]
const PAGE = 100

export default function TreeTable({ job, onLocate }: { job: Job; onLocate: (t: TreeProps) => void }) {
  const cols = job.mode === 'survey' ? COLS : COLS.filter((c) => !['species', 'species_confidence', 'detection_score'].includes(c.key))
  const [trees, setTrees] = useState<TreeProps[] | null>(null)
  const [sort, setSort] = useState<{ key: keyof TreeProps; desc: boolean }>({ key: 'height_m', desc: true })
  const [query, setQuery] = useState('')
  const [page, setPage] = useState(0)

  useEffect(() => {
    const layer = job.outputs.layers.trees
    if (!layer) return
    fetch(fileUrl(job.id, layer.file))
      .then((r) => r.json())
      .then((fc) => setTrees(fc.features.map((f: { properties: TreeProps }) => f.properties)))
  }, [job])

  const rows = useMemo(() => {
    if (!trees) return []
    const q = query.trim().toUpperCase()
    const filtered = q ? trees.filter((t) => t.tree_id.includes(q) || (t.fsi_density_class ?? '').includes(q) || (t.species ?? '').toUpperCase().includes(q)) : trees
    return [...filtered].sort((a, b) => {
      const x = a[sort.key] as number | string | null
      const y = b[sort.key] as number | string | null
      if (x === y) return 0
      if (x === null) return 1
      if (y === null) return -1
      return (x < y ? -1 : 1) * (sort.desc ? -1 : 1)
    })
  }, [trees, sort, query])

  if (!trees) return <div className="panel-body muted">Loading trees…</div>
  const pages = Math.max(1, Math.ceil(rows.length / PAGE))
  const shown = rows.slice(page * PAGE, page * PAGE + PAGE)

  return (
    <div className="panel-body">
      <div style={{ display: 'flex', gap: 10, alignItems: 'center', marginBottom: 10, flexWrap: 'wrap' }}>
        <input className="search-input" type="search" style={{ minWidth: 300 }} placeholder="Search tree ID, class or species (e.g. T000012, VDF)"
          value={query} onChange={(e) => { setQuery(e.target.value); setPage(0) }} />
        <span className="muted small">{rows.length.toLocaleString()} trees · click a row to locate it on the map</span>
        <span style={{ marginLeft: 'auto' }} className="small">
          <button className="btn" disabled={page === 0} onClick={() => setPage(page - 1)}>‹</button>{' '}
          page {page + 1} / {pages}{' '}
          <button className="btn" disabled={page >= pages - 1} onClick={() => setPage(page + 1)}>›</button>
        </span>
      </div>
      <div className="table-wrap">
        <table className="data-table">
          <thead>
            <tr>
              {cols.map((c) => (
                <th key={c.key} onClick={() => setSort({ key: c.key, desc: sort.key === c.key ? !sort.desc : true })}>
                  {c.label} {sort.key === c.key ? (sort.desc ? '▾' : '▴') : ''}
                </th>
              ))}
              <th>Flags</th>
            </tr>
          </thead>
          <tbody>
            {shown.map((t) => (
              <tr key={t.tree_id} className="clickable" style={{ cursor: 'pointer' }} onClick={() => onLocate(t)}>
                {cols.map((c) => (
                  <td key={c.key} className={c.num ? 'num' : ''}>{t[c.key] === null ? '–' : String(t[c.key])}</td>
                ))}
                <td>{t.quality_flags.length ? <span className="chip chip-warning">{t.quality_flags.join(', ')}</span> : ''}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
