import type { Job, SiteSpeciesSummary } from '../types'

const FSI = [
  { code: 'VDF', name: 'Very Dense Forest (≥70%)', color: '#0b5d1e' },
  { code: 'MDF', name: 'Moderately Dense (40–70%)', color: '#3f9b35' },
  { code: 'OF', name: 'Open Forest (10–40%)', color: '#a7d46f' },
  { code: 'NF', name: 'Scrub / Non-forest (<10%)', color: '#d9c99a' },
]
const NDVI = [
  { code: 'dense', name: 'Dense healthy', color: '#1f7a2e' },
  { code: 'moderate', name: 'Moderate', color: '#8fc45a' },
  { code: 'sparse', name: 'Sparse / stressed', color: '#e6d36a' },
  { code: 'non_vegetated', name: 'Non-vegetated', color: '#b9a27a' },
]

const LEAF_HABIT = [
  { code: 'evergreen', name: 'Evergreen', color: '#0b5d1e' },
  { code: 'semi_deciduous', name: 'Semi-deciduous', color: '#c9a227' },
  { code: 'deciduous', name: 'Deciduous', color: '#b5651d' },
]

function Kpi({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <div className="kpi">
      <div className="label">{label}</div>
      <div className="value">{value}</div>
      {note && <div className="note">{note}</div>}
    </div>
  )
}

export function Bars({ rows, unit = '', max }: { rows: { label: string; value: number; color?: string }[]; unit?: string; max?: number }) {
  const top = max ?? Math.max(1, ...rows.map((r) => r.value))
  return (
    <div className="bars">
      {rows.map((r) => (
        <div key={r.label} className="bar-row">
          <span>{r.label}</span>
          <div className="bar-track">
            <div className="bar-fill" style={{ width: `${(r.value / top) * 100}%`, background: r.color ?? '#3f9b35' }} />
          </div>
          <span className="bar-val">{r.value.toLocaleString()}{unit}</span>
        </div>
      ))}
    </div>
  )
}

function SiteSpeciesPanel({ site }: { site: SiteSpeciesSummary }) {
  const top = site.species.slice(0, 8)
  return (
    <div className="panel site-species">
      <div className="panel-head">
        <h2>Likely species</h2>
      </div>
      <div className="panel-body">
        <div className="bars">
          {top.map((sp) => (
            <div key={sp.name} className="bar-row species-row">
              <span title={`${sp.name}${sp.family ? ` · ${sp.family}` : ''}`}>
                {sp.local_name ?? sp.english_name ?? sp.name}
                {sp.often_planted && <span className="tag-planted"> · planted</span>}
              </span>
              <div className="bar-track">
                <div className="bar-fill" style={{ width: `${(sp.share_pct / top[0].share_pct) * 100}%`, background: 'var(--brand-600)' }} />
              </div>
              <span className="bar-val">{sp.share_pct}%</span>
            </div>
          ))}
        </div>
        <p className="caption" title={site.method}>
          {site.ecoregion ? `${site.ecoregion}. ` : ''}Predicted from climate, soil and land cover, not counted.
        </p>
      </div>
    </div>
  )
}

const n = (v: number | null | undefined, suffix = '') => (v === null || v === undefined ? '–' : `${v.toLocaleString()}${suffix}`)

export default function StatsView({ job }: { job: Job }) {
  const s = job.summary
  const tc = s.tree_count
  const d = s.density
  const area = job.aoi?.area_ha ?? 0
  const survey = s.mode === 'survey'
  const species = Object.entries(s.species ?? {})
  const named = species.filter(([k]) => k !== 'Unknown')

  return (
    <div className="panel-body">
      <div className="kpis">
        <Kpi label="Area" value={`${n(area)} ha`} />
        <Kpi label="Trees mapped" value={n(tc?.detected)}
          note={!survey && tc ? `≈ ${(tc.estimated_low / 1000).toFixed(0)}k–${(tc.estimated_high / 1000).toFixed(0)}k in total` : undefined} />
        <Kpi label="Canopy cover" value={n(d?.canopy_cover_pct, '%')} />
        {survey ? (
          <Kpi label="Species" value={species.length ? String(named.length) : '–'} />
        ) : (
          <Kpi label="Forest class" value={d?.dominant_fsi_class ?? '–'}
            note={FSI.find((f) => f.code === d?.dominant_fsi_class)?.name.replace(/\s*\(.*\)$/, '')} />
        )}
      </div>

      <div className="grid-2">
        {s.site_species ? (
          <SiteSpeciesPanel site={s.site_species} />
        ) : species.length > 0 ? (
          <div className="panel">
            <div className="panel-head"><h2>Species</h2></div>
            <div className="panel-body">
              <Bars rows={species.map(([k, v]) => ({ label: k, value: v, color: k === 'Unknown' ? '#c4cdc7' : 'var(--brand-600)' }))} />
            </div>
          </div>
        ) : null}
        <div className="panel">
          <div className="panel-head"><h2>Forest density</h2></div>
          <div className="panel-body">
            <Bars unit=" ha" rows={FSI.map((f) => ({ label: f.name.replace(/\s*\(.*\)$/, ''), value: d?.fsi_area_ha[f.code] ?? 0, color: f.color }))} />
          </div>
        </div>
      </div>

      <details className="more">
        <summary>More statistics</summary>
        <div className="grid-2">
          {s.site_species && species.length > 0 && (
            <div className="panel">
              <div className="panel-head"><h2>Species per tree</h2></div>
              <div className="panel-body">
                <Bars rows={species.map(([k, v]) => ({ label: k, value: v, color: k === 'Unknown' ? '#c4cdc7' : 'var(--brand-600)' }))} />
              </div>
            </div>
          )}
          <div className="panel">
            <div className="panel-head"><h2>Tree heights</h2></div>
            <div className="panel-body">
              <Bars rows={(s.height?.histogram ?? []).map((h) => ({ label: h.label, value: h.count }))} />
            </div>
          </div>
          {s.ndvi?.available && (
            <div className="panel">
              <div className="panel-head"><h2>Vegetation condition</h2></div>
              <div className="panel-body">
                <Bars unit="%" max={100} rows={NDVI.map((c) => ({ label: c.name, value: s.ndvi?.class_pct?.[c.code] ?? 0, color: c.color }))} />
              </div>
            </div>
          )}
          {s.leaf_fall?.available && (
            <div className="panel">
              <div className="panel-head"><h2>Seasonal leaf fall</h2></div>
              <div className="panel-body">
                <Bars unit="%" max={100} rows={LEAF_HABIT.map((c) => ({ label: c.name, value: s.leaf_fall?.class_pct?.[c.code] ?? 0, color: c.color }))} />
                <p className="small muted" style={{ marginTop: 10 }}>
                  Share of tree cover, from the drop in Sentinel-2 greenness between the leaf-on and dry seasons.
                </p>
              </div>
            </div>
          )}
          {s.landcover && (
            <div className="panel">
              <div className="panel-head"><h2>Land cover</h2></div>
              <div className="panel-body">
                <Bars unit="%" max={100} rows={Object.entries(s.landcover).map(([k, v]) => ({ label: k, value: v, color: '#6f9a7c' }))} />
              </div>
            </div>
          )}
        </div>
      </details>
    </div>
  )
}
