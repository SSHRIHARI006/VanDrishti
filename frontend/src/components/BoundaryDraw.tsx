import * as maplibregl from 'maplibre-gl'
import type { GeoJSONSource, Map as MLMap, MapMouseEvent } from 'maplibre-gl'
import { useEffect, useRef, useState } from 'react'
import { addSiteMask, addTerrain, circleBounds, distM, elevationAt, siteMask, type LonLat, type SiteExtent } from './mapExtras'

maplibregl.setWorkerUrl(new URL('/maplibre/maplibre-gl-worker.mjs', window.location.href).href)

type Pt = LonLat
type Tool = 'polygon' | 'rectangle'

const MIN_HA = 1
const MAX_KM2 = 10

// Equirectangular projection around the ring's mean latitude: under 1 % error at block scale.
function areaHa(ring: Pt[]): number {
  if (ring.length < 3) return 0
  const lat0 = (ring.reduce((s, p) => s + p[1], 0) / ring.length) * (Math.PI / 180)
  const xy = ring.map(([lon, lat]) => [lon * 111320 * Math.cos(lat0), lat * 110574])
  let a = 0
  for (let i = 0; i < xy.length; i++) {
    const [x1, y1] = xy[i]
    const [x2, y2] = xy[(i + 1) % xy.length]
    a += x1 * y2 - x2 * y1
  }
  return Math.abs(a) / 2 / 10000
}

const rect = (a: Pt, b: Pt): Pt[] => [a, [b[0], a[1]], b, [a[0], b[1]]]
const EMPTY: GeoJSON.FeatureCollection = { type: 'FeatureCollection', features: [] }

export default function BoundaryDraw({ onChange }: { onChange: (f: File | null) => void }) {
  const el = useRef<HTMLDivElement>(null)
  const mapRef = useRef<MLMap | null>(null)
  const [site, setSite] = useState<SiteExtent | null>(null)
  const [radius, setRadius] = useState(1000)
  const [tool, setTool] = useState<Tool>('polygon')
  const [pts, setPts] = useState<Pt[]>([])
  const [closed, setClosed] = useState(false)
  const [query, setQuery] = useState('')
  const [msg, setMsg] = useState<string | null>(null)
  const [elev, setElev] = useState<number | null>(null)
  const [loaded, setLoaded] = useState(false)
  const state = useRef({ tool, pts, closed, site, radius, cursor: null as Pt | null })
  Object.assign(state.current, { tool, pts, closed, site, radius })

  const ha = areaHa(closed ? pts : pts.length >= 3 ? pts : [])
  const tooBig = ha / 100 > MAX_KM2
  const tooSmall = closed && ha < MIN_HA

  const redraw = () => {
    const map = mapRef.current
    const src = map?.getSource('draw') as GeoJSONSource | undefined
    const preview = map?.getSource('site-preview') as GeoJSONSource | undefined
    if (!src || !preview) return
    const { pts: p, closed: c, cursor, tool: t, site: s, radius: r } = state.current
    // before the site is placed, preview the circle at the cursor, or at the map centre when the mouse is elsewhere
    const c0 = map!.getCenter()
    preview.setData(!s ? siteMask({ center: cursor ?? [c0.lng, c0.lat], radius_m: r }) : EMPTY)
    if (!s) { src.setData(EMPTY); return }
    const live: Pt[] = !c && cursor
      ? t === 'rectangle' && p.length === 1 ? rect(p[0], cursor) : [...p, cursor]
      : p
    const feats: GeoJSON.Feature[] = []
    if (live.length >= 3) feats.push({ type: 'Feature', properties: { kind: 'area' }, geometry: { type: 'Polygon', coordinates: [[...live, live[0]]] } })
    if (live.length >= 2) feats.push({ type: 'Feature', properties: { kind: 'edge' }, geometry: { type: 'LineString', coordinates: c || t === 'rectangle' ? [...live, live[0]] : live } })
    p.forEach((pt, i) => feats.push({ type: 'Feature', properties: { kind: i === 0 ? 'first' : 'vertex' }, geometry: { type: 'Point', coordinates: pt } }))
    src.setData({ type: 'FeatureCollection', features: feats })
  }

  useEffect(() => {
    if (!el.current || mapRef.current) return
    const map = new maplibregl.Map({
      container: el.current,
      attributionControl: { compact: true },
      style: {
        version: 8,
        sources: {
          sat: {
            type: 'raster', tileSize: 256, maxzoom: 18,
            tiles: ['https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'],
            attribution: 'Imagery © Esri, Maxar, Earthstar Geographics',
          },
          labels: {
            type: 'raster', tileSize: 256, maxzoom: 18,
            tiles: ['https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}'],
          },
        },
        layers: [{ id: 'sat', type: 'raster', source: 'sat' }, { id: 'labels', type: 'raster', source: 'labels' }],
      },
      center: [79.3, 20.0],
      zoom: 9,
      maxZoom: 19,
      maxPitch: 75,
      doubleClickZoom: false,
    })
    map.addControl(new maplibregl.NavigationControl({ visualizePitch: true }), 'top-right')
    map.addControl(new maplibregl.ScaleControl({ unit: 'metric' }), 'bottom-left')
    mapRef.current = map
    map.getCanvas().style.cursor = 'crosshair'

    map.on('load', () => {
      el.current?.querySelector('.maplibregl-ctrl-attrib')?.classList.remove('maplibregl-compact-show')
      addTerrain(map, 'labels')
      map.addSource('site-preview', { type: 'geojson', data: EMPTY })
      map.addLayer({ id: 'site-preview-fill', type: 'fill', source: 'site-preview', filter: ['==', ['get', 'kind'], 'mask'], paint: { 'fill-color': '#000', 'fill-opacity': 0.25 } })
      map.addLayer({ id: 'site-preview-rim', type: 'line', source: 'site-preview', filter: ['==', ['get', 'kind'], 'rim'], paint: { 'line-color': '#ffffff', 'line-width': 2, 'line-dasharray': [3, 2] } })
      map.addSource('draw', { type: 'geojson', data: EMPTY })
      map.addLayer({ id: 'draw-fill', type: 'fill', source: 'draw', filter: ['==', ['get', 'kind'], 'area'], paint: { 'fill-color': '#ffd400', 'fill-opacity': 0.18 } })
      map.addLayer({ id: 'draw-line', type: 'line', source: 'draw', filter: ['==', ['get', 'kind'], 'edge'], paint: { 'line-color': '#ffd400', 'line-width': 2.5 } })
      map.addLayer({
        id: 'draw-pts', type: 'circle', source: 'draw', filter: ['in', ['get', 'kind'], ['literal', ['vertex', 'first']]],
        paint: {
          'circle-radius': ['case', ['==', ['get', 'kind'], 'first'], 7, 5],
          'circle-color': ['case', ['==', ['get', 'kind'], 'first'], '#1f5f3b', '#ffffff'],
          'circle-stroke-color': '#ffd400', 'circle-stroke-width': 2,
        },
      })
      setLoaded(true)
    })

    map.on('mousemove', (e: MapMouseEvent) => {
      const ll: Pt = [e.lngLat.lng, e.lngLat.lat]
      state.current.cursor = ll
      setElev(elevationAt(map, ll))
      redraw()
    })
    map.on('mouseout', () => { state.current.cursor = null; setElev(null); redraw() })
    map.on('move', () => { if (!state.current.cursor) redraw() })
    map.on('click', (e: MapMouseEvent) => {
      const { pts: p, closed: c, tool: t, site: s, radius: r } = state.current
      const pt: Pt = [e.lngLat.lng, e.lngLat.lat]
      if (!s) {
        setSite({ center: pt, radius_m: r })
        return
      }
      if (c) return
      if (distM(pt, s.center) > s.radius_m) { setMsg('That point is outside the site circle. Draw inside it.'); return }
      setMsg(null)
      if (t === 'rectangle') {
        if (p.length === 0) { setPts([pt]); return }
        const box = rect(p[0], pt)
        if (box.some((q) => distM(q, s.center) > s.radius_m)) { setMsg('Part of that rectangle falls outside the site circle.'); return }
        setPts(box)
        setClosed(true)
        return
      }
      if (p.length >= 3) {
        // project both through the same path; e.point alone ignores terrain height and misses when tilted
        const first = map.project(p[0])
        const here = map.project(pt)
        if (Math.hypot(first.x - here.x, first.y - here.y) < 14) { setClosed(true); return }
      }
      setPts([...p, pt])
    })
    map.on('dblclick', () => {
      if (state.current.site && state.current.tool === 'polygon' && state.current.pts.length >= 3) setClosed(true)
    })
    return () => { map.remove(); mapRef.current = null }
  }, [])

  // Lock the map to the site once it is set: mask outside, fit, and stop panning away.
  useEffect(() => {
    const map = mapRef.current
    if (!map || !loaded) return
    if (map.getLayer('site-mask')) { map.removeLayer('site-mask'); map.removeLayer('site-rim'); map.removeSource('site-mask') }
    if (!site) { map.setMaxBounds(null); map.setMinZoom(0); return }
    addSiteMask(map, site)
    map.setMaxBounds(circleBounds(site.center, site.radius_m, 2.2))
    map.fitBounds(circleBounds(site.center, site.radius_m), { padding: 8, pitch: 30, duration: 1200 })
  }, [site, loaded])

  useEffect(redraw, [pts, closed, tool, site, radius, loaded])

  // Slider moved: zoom so the whole preview circle stays in view.
  const firstRadius = useRef(true)
  useEffect(() => {
    if (firstRadius.current) { firstRadius.current = false; return }
    const map = mapRef.current
    if (!map || site) return
    const c = map.getCenter()
    map.fitBounds(circleBounds([c.lng, c.lat], radius, 1.15), { duration: 250 })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [radius])

  useEffect(() => {
    if (!site || !closed || ha < MIN_HA || ha / 100 > MAX_KM2) { onChange(null); return }
    const fc = {
      type: 'FeatureCollection',
      features: [
        { type: 'Feature', properties: { name: 'Drawn boundary' }, geometry: { type: 'Polygon', coordinates: [[...pts, pts[0]]] } },
        { type: 'Feature', properties: { role: 'site_extent', radius_m: site.radius_m }, geometry: { type: 'Point', coordinates: site.center } },
      ],
    }
    onChange(new File([JSON.stringify(fc)], 'drawn_boundary.geojson', { type: 'application/geo+json' }))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [closed, pts, site])

  const clear = () => { setPts([]); setClosed(false); setMsg(null) }
  const undo = () => {
    if (closed && tool === 'polygon') setClosed(false)
    else if (tool === 'rectangle') clear()
    else setPts(pts.slice(0, -1))
  }
  const switchTool = (t: Tool) => { setTool(t); clear() }
  const resetSite = () => { clear(); setSite(null) }

  const search = async () => {
    const q = query.trim()
    if (!q) return
    const ll = q.match(/^\s*(-?\d+(?:\.\d+)?)\s*[, ]\s*(-?\d+(?:\.\d+)?)\s*$/)
    if (ll) {
      mapRef.current?.flyTo({ center: [Number(ll[2]), Number(ll[1])], zoom: 14 })
      setMsg(null)
      return
    }
    setMsg('Searching…')
    try {
      const r = await fetch(`https://nominatim.openstreetmap.org/search?format=json&limit=1&countrycodes=in&q=${encodeURIComponent(q)}`)
      const hits = (await r.json()) as { boundingbox: string[]; display_name: string }[]
      if (!hits.length) { setMsg('Place not found. Try a nearby town, or type "lat, lon"'); return }
      const [s, n, w, e] = hits[0].boundingbox.map(Number)
      mapRef.current?.fitBounds([[w, s], [e, n]], { maxZoom: 14, duration: 1200 })
      setMsg(hits[0].display_name.split(',').slice(0, 3).join(','))
    } catch {
      setMsg('Search needs an internet connection. You can also type "lat, lon"')
    }
  }

  const hint = !site
    ? 'Click the site centre'
    : closed
      ? null
      : tool === 'rectangle'
        ? pts.length === 0 ? 'Click a corner' : 'Click the opposite corner'
        : pts.length < 3 ? 'Click to add points' : 'Click the first point to finish'

  return (
    <div className="draw-box">
      {(
        <div className="draw-search">
          <input disabled={!!site} value={query} onChange={(e) => setQuery(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && search()}
            placeholder="Search a place or lat, lon" />
          <button className="btn" onClick={search} disabled={!!site}>Go</button>
        </div>
      )}
      {(
        <div className="draw-radius">
          <label htmlFor="site-r">Radius</label>
          <input id="site-r" disabled={!!site} type="range" min={250} max={2500} step={50} value={radius} onChange={(e) => setRadius(Number(e.target.value))} />
          <strong>{radius >= 1000 ? `${(radius / 1000).toFixed(2)} km` : `${radius} m`}</strong>
        </div>
      )}
      {msg && <div className="small muted" style={{ margin: '4px 0' }}>{msg}</div>}
      <div className="draw-map-wrap">
        <div ref={el} className="draw-map" />
        {hint && <div className="draw-hint">{hint}</div>}
        {elev != null && <div className="draw-elev">Elevation {Math.round(elev)} m</div>}
      </div>
      {site && (
        <div className="draw-tools">
          <div className="segmented">
            <button className={tool === 'polygon' ? 'on' : ''} onClick={() => switchTool('polygon')}>Polygon</button>
            <button className={tool === 'rectangle' ? 'on' : ''} onClick={() => switchTool('rectangle')}>Rectangle</button>
          </div>
          <button className="btn" onClick={undo} disabled={!pts.length}>Undo</button>
          <button className="btn" onClick={clear} disabled={!pts.length}>Clear</button>
          {!closed && tool === 'polygon' && pts.length >= 3 && <button className="btn" onClick={() => setClosed(true)}>Finish</button>}
          <button className="btn" onClick={resetSite}>Change site</button>
          <span className={`draw-area ${tooBig || tooSmall ? 'bad' : closed ? 'ok' : ''}`}>
            {ha > 0 ? (ha >= 100 ? `${(ha / 100).toFixed(2)} km²` : `${ha.toFixed(1)} ha`) : ''}
          </span>
        </div>
      )}
      {tooBig && <div className="error-box">Too large: max {MAX_KM2} km² per run.</div>}
      {tooSmall && <div className="error-box">Too small: min {MIN_HA} ha.</div>}
      {closed && !tooBig && !tooSmall && <div className="file-picked">✓ Boundary ready</div>}
    </div>
  )
}
