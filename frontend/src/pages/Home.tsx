import { useEffect, useRef, useState } from 'react'
import { api } from '../api'
import BoundaryDraw from '../components/BoundaryDraw'
import StatusChip from '../components/StatusChip'
import type { JobListItem, SurveyInput, SurveySample } from '../types'

type Mode = 'satellite' | 'survey'

const SURVEY_INPUTS: { key: SurveyInput; label: string; help: string; required?: boolean }[] = [
  { key: 'ortho', label: 'Orthophoto', help: 'Required', required: true },
  { key: 'dsm', label: 'Surface (DSM)', help: 'Optional' },
  { key: 'dtm', label: 'Terrain (DTM)', help: 'Optional' },
  { key: 'chm', label: 'Canopy height', help: 'Optional' },
]

function FilePick({ label, help, file, accept, required, onPick }: {
  label: string; help: string; file?: File; accept: string; required?: boolean; onPick: (f: File | undefined) => void
}) {
  const input = useRef<HTMLInputElement>(null)
  return (
    <>
      <button type="button" className={`file-tile ${file ? 'set' : ''}`} title={file?.name}
        onClick={() => input.current?.click()}>
        <span className="file-label">{label}{required && <span className="req"> *</span>}</span>
        <span className="small muted file-state">{file ? `✓ ${file.name}` : help}</span>
      </button>
      <input ref={input} type="file" accept={accept} hidden onChange={(e) => onPick(e.target.files?.[0])} />
    </>
  )
}

export default function Home() {
  const [mode, setMode] = useState<Mode>('satellite')
  const [file, setFile] = useState<File | null>(null)
  const [source, setSource] = useState<'upload' | 'draw'>('upload')
  const [survey, setSurvey] = useState<Partial<Record<SurveyInput, File>>>({})
  const [name, setName] = useState('')
  const [minHeight, setMinHeight] = useState(5)
  const [canopy, setCanopy] = useState(5)
  const [cell, setCell] = useState(25)
  const [drag, setDrag] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [samples, setSamples] = useState<{ filename: string; name: string }[]>([])
  const [surveySamples, setSurveySamples] = useState<SurveySample[]>([])
  const [jobs, setJobs] = useState<JobListItem[]>([])
  const input = useRef<HTMLInputElement>(null)

  useEffect(() => {
    api.samples().then(setSamples).catch(() => {})
    api.surveySamples().then(setSurveySamples).catch(() => {})
    api.jobs().then(setJobs).catch(() => {})
  }, [])

  const pick = (f: File | undefined) => {
    if (!f) return
    setError(null)
    if (!/\.(kml|kmz|geojson|json)$/i.test(f.name)) {
      setError('Please choose a .kml, .kmz or .geojson boundary file')
      return
    }
    setFile(f)
    if (!name) setName(f.name.replace(/\.[^.]+$/, '').replace(/[_-]+/g, ' '))
  }

  const pickRaster = (key: SurveyInput, f: File | undefined) => {
    if (!f) return
    if (!/\.tiff?$/i.test(f.name)) {
      setError(`The ${key.toUpperCase()} must be a GeoTIFF (.tif)`)
      return
    }
    setError(null)
    setSurvey((s) => ({ ...s, [key]: f }))
  }

  const go = (id: string) => {
    window.location.hash = `#/jobs/${id}`
  }

  const options = { min_tree_height_m: minHeight, canopy_threshold_m: canopy, grid_cell_m: cell }
  const ready = !!file && (mode === 'satellite' || !!survey.ortho)

  const submit = async () => {
    if (!file) return
    setBusy(true)
    setError(null)
    try {
      const { id } = mode === 'satellite'
        ? await api.createJob(file, name, options)
        : await api.createSurveyJob(file, survey, name, options)
      go(id)
    } catch (e) {
      setError((e as Error).message)
      setBusy(false)
    }
  }

  const run = async (start: () => Promise<{ id: string }>) => {
    setBusy(true)
    try {
      go((await start()).id)
    } catch (e) {
      setError((e as Error).message)
      setBusy(false)
    }
  }

  return (
    <main>
      <section className="hero">
        <div className="hero-intro">
          <h1>Tree inventory for forest clearance.</h1>
          <p>Draw or upload a boundary. Get every tree mapped, measured and reported.</p>

          <div className="mode-compare">
            <div className={`mode-card ${mode === 'satellite' ? 'on' : ''}`}>
              <span className="mode-name">Satellite</span>
              <span className="mode-detail">Meta canopy height · Sentinel-2 · Copernicus DEM · WorldCover</span>
            </div>
            <div className={`mode-card ${mode === 'survey' ? 'on' : ''}`}>
              <span className="mode-name">Drone survey</span>
              <span className="mode-detail">Orthophoto · DSM/DTM canopy height · field species labels</span>
            </div>
          </div>
        </div>

        <div className="panel form-card">
          <div className="form-top">
            <div className="segmented">
              <button className={mode === 'satellite' ? 'on' : ''} onClick={() => setMode('satellite')}>Satellite</button>
              <button className={mode === 'survey' ? 'on' : ''} onClick={() => setMode('survey')}>Drone survey</button>
            </div>
            <div className="segmented">
              <button className={source === 'upload' ? 'on' : ''} onClick={() => { setSource('upload'); setFile(null) }}>
                Upload
              </button>
              <button className={source === 'draw' ? 'on' : ''} onClick={() => { setSource('draw'); setFile(null) }}>
                Draw
              </button>
            </div>
          </div>

          {source === 'draw' ? (
            <BoundaryDraw onChange={(f) => {
              setFile(f)
              if (f && !name) setName(`Drawn area ${new Date().toLocaleDateString()}`)
            }} />
          ) : (
            <div
              className={`dropzone ${drag ? 'drag' : ''} ${mode === 'survey' ? 'compact' : ''}`}
              onClick={() => input.current?.click()}
              onDragOver={(e) => {
                e.preventDefault()
                setDrag(true)
              }}
              onDragLeave={() => setDrag(false)}
              onDrop={(e) => {
                e.preventDefault()
                setDrag(false)
                pick(e.dataTransfer.files[0])
              }}
            >
              <strong>{file ? file.name : 'Drop a boundary file'}</strong>
              <span className="muted small">{file ? 'Click to change' : 'KML, KMZ or GeoJSON · or click to browse'}</span>
              <input ref={input} type="file" accept=".kml,.kmz,.geojson,.json" hidden
                onChange={(e) => pick(e.target.files?.[0])} />
            </div>
          )}

          {mode === 'survey' && (
            <div className="survey-files">
              {SURVEY_INPUTS.map((s) => (
                <FilePick key={s.key} label={s.label} help={s.help} required={s.required} file={survey[s.key]}
                  accept=".tif,.tiff" onPick={(f) => pickRaster(s.key, f)} />
              ))}
            </div>
          )}

          <div className="form-row">
            <input id="name" aria-label="Assessment name" value={name} onChange={(e) => setName(e.target.value)}
              placeholder="Assessment name" />
          </div>

          <details>
            <summary>Advanced</summary>
            <div className="options-grid">
              <div className="form-row">
                <label>Min tree height (m)</label>
                <input type="number" min={2} max={20} step={0.5} value={minHeight}
                  onChange={(e) => setMinHeight(Number(e.target.value))} />
              </div>
              <div className="form-row">
                <label>Canopy threshold (m)</label>
                <input type="number" min={1} max={20} step={0.5} value={canopy}
                  onChange={(e) => setCanopy(Number(e.target.value))} />
              </div>
              <div className="form-row">
                <label>Density cell (m)</label>
                <input type="number" min={10} max={100} step={5} value={cell}
                  onChange={(e) => setCell(Number(e.target.value))} />
              </div>
            </div>
          </details>

          {error && <div className="error-box">{error}</div>}

          <button className="btn btn-primary btn-block" disabled={!ready || busy} onClick={submit}>
            {busy ? (mode === 'survey' ? 'Uploading…' : 'Starting…') : 'Run assessment'}
          </button>

          {mode === 'satellite' && samples.length > 0 && (
            <div className="samples">
              <span className="muted small">Try a sample</span>
              {samples.map((s) => (
                <button key={s.filename} className="link-btn" disabled={busy}
                  onClick={() => run(() => api.createFromSample(s.filename))}>
                  {s.name.replace(/^Chandrapur /, '')}
                </button>
              ))}
            </div>
          )}
          {mode === 'survey' && surveySamples.length > 0 && (
            <div className="samples">
              <span className="muted small">Try a sample</span>
              {surveySamples.map((s) => (
                <button key={s.id} className="link-btn" disabled={busy}
                  onClick={() => run(() => api.createFromSurveySample(s.id))}>
                  {s.name}
                </button>
              ))}
            </div>
          )}
        </div>
      </section>

      <section className="page" id="assessments">
        <div className="section-head">
          <h2>Assessments</h2>
        </div>
        {jobs.length === 0 ? (
          <div className="empty muted">No assessments yet.</div>
        ) : (
          <div className="panel list-panel">
            <table className="job-list">
              <tbody>
                {jobs.map((j) => (
                  <tr key={j.id} className="clickable" onClick={() => go(j.id)}>
                    <td className="job-name">{j.name}</td>
                    <td className="muted">{j.mode === 'survey' ? 'Drone survey' : 'Satellite'}</td>
                    <td><StatusChip status={j.status} /></td>
                    <td className="muted nowrap num">
                      {new Date(j.created_at).toLocaleDateString([], { day: 'numeric', month: 'short' })}
                    </td>
                    <td className="row-go">›</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </main>
  )
}
