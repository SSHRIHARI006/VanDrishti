import * as maplibregl from 'maplibre-gl'
import type { ExpressionSpecification, Map as MLMap, MapMouseEvent } from 'maplibre-gl'
import { useEffect, useRef, useState } from 'react'
import { fileUrl } from '../api'
import type { Job, Legend } from '../types'
import type { FeatureCollection, Point } from 'geojson'
import { buildTreeModels, speciesPresent, type SpeciesStyle } from './trees3d'
import { addSiteMask, addTerrain, circleBounds, elevationAt, extentForBounds, setTerrainVisible } from './mapExtras'

const abs = (p: string) => new URL(p, window.location.href).href

maplibregl.setWorkerUrl(abs('/maplibre/maplibre-gl-worker.mjs'))

export const HEIGHT_STOPS: [number, string][] = [
  [5, '#d9f0a3'],
  [10, '#78c679'],
  [15, '#31a354'],
  [20, '#006837'],
  [30, '#00441b'],
]
const heightColor: ExpressionSpecification = [
  'interpolate', ['linear'], ['get', 'height_m'], ...HEIGHT_STOPS.flat(),
] as ExpressionSpecification

const FSI_COLORS: ExpressionSpecification = [
  'match', ['get', 'fsi_class'],
  'VDF', '#0b5d1e', 'MDF', '#3f9b35', 'OF', '#a7d46f', '#e8dcb5',
] as ExpressionSpecification

const CMAP_CSS: Record<string, string> = {
  YlGn: 'linear-gradient(90deg,#ffffe5,#d9f0a3,#78c679,#238443,#004529)',
  RdYlGn: 'linear-gradient(90deg,#a50026,#f46d43,#fee08b,#a6d96a,#1a9850,#006837)',
  viridis: 'linear-gradient(90deg,#440154,#3b528b,#21918c,#5ec962,#fde725)',
}

const RASTER_ORDER = ['ortho', 'chm', 'ndvi', 'leaf_fall', 's2_truecolor', 'landcover']
const EXTRA_POPUP_FIELDS: [string, string][] = [
  ['height_m', 'Height (m)'],
  ['crown_area_m2', 'Crown area (m²)'],
  ['crown_diameter_m', 'Crown diameter (m)'],
  ['local_canopy_density_pct', 'Local canopy density (%)'],
  ['fsi_density_class', 'Density class'],
  ['ndvi', 'NDVI'],
  ['ground_elevation_m', 'Ground elevation (m)'],
  ['detection_score', 'Detection confidence'],
]

export interface MapFocus {
  treeId: string
  lon: number
  lat: number
  key: number
}

export default function MapView({ job, focus, visible }: { job: Job; focus?: MapFocus | null; visible: boolean }) {
  const el = useRef<HTMLDivElement>(null)
  const mapRef = useRef<MLMap | null>(null)
  const [ready, setReady] = useState(false)
  const [species, setSpecies] = useState<SpeciesStyle[]>([])
  const [terrain, setTerrain] = useState(true)
  const [showLayers, setShowLayers] = useState(() => window.innerWidth > 700)
  const [elev, setElev] = useState<number | null>(null)
  const [three, setThree] = useState(false)
  const [basemap, setBasemap] = useState<'satellite' | 'streets'>('satellite')
  const [vis, setVis] = useState<Record<string, boolean>>({
    aoi: true,
    crowns: true,
    trees: true,
    density: false,
    chm: false,
    ndvi: false,
    s2_truecolor: false,
    landcover: false,
    ortho: job.mode === 'survey',
  })

  const rasters = RASTER_ORDER.filter((k) => job.outputs.rasters[k])
  const hasCrowns = !!job.outputs.layers.crowns
  const hasTrees = !!job.outputs.layers.trees

  useEffect(() => {
    if (!el.current || mapRef.current) return
    const b = job.aoi!.bounds
    const site = job.aoi!.site_extent ?? extentForBounds(b)
    const [sw, ne] = circleBounds(site.center, site.radius_m)
    const side = Math.min(260, el.current.clientWidth * 0.3)
    const map = new maplibregl.Map({
      container: el.current,
      attributionControl: { compact: true },
      style: {
        version: 8,
        sources: {
          satellite: {
            type: 'raster',
            tiles: ['https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'],
            tileSize: 256,
            maxzoom: 17,
            attribution: 'Imagery © Esri, Maxar, Earthstar Geographics',
          },
          streets: {
            type: 'raster',
            tiles: ['https://tile.openstreetmap.org/{z}/{x}/{y}.png'],
            tileSize: 256,
            maxzoom: 19,
            attribution: '© OpenStreetMap contributors',
          },
        },
        layers: [
          { id: 'satellite', type: 'raster', source: 'satellite' },
          { id: 'streets', type: 'raster', source: 'streets', layout: { visibility: 'none' } },
        ],
      },
      bounds: [sw[0], sw[1], ne[0], ne[1]],
      maxBounds: circleBounds(site.center, site.radius_m, 2.2),
      fitBoundsOptions: { padding: { top: 30, bottom: 30, left: side, right: 30 }, maxZoom: 20 },
      maxZoom: 21,
      maxPitch: 85,
    })
    map.addControl(new maplibregl.NavigationControl({ visualizePitch: true }), 'top-right')
    map.addControl(new maplibregl.ScaleControl({ unit: 'metric' }), 'bottom-left')
    mapRef.current = map

    map.on('load', () => {
      el.current?.querySelector('.maplibregl-ctrl-attrib')?.classList.remove('maplibregl-compact-show')
      addTerrain(map)
      for (const key of RASTER_ORDER) {
        const r = job.outputs.rasters[key]
        if (!r) continue
        map.addSource(`r-${key}`, {
          type: 'image',
          url: abs(fileUrl(job.id, r.file)),
          coordinates: r.corners as [[number, number], [number, number], [number, number], [number, number]],
        })
        map.addLayer({
          id: `r-${key}`,
          type: 'raster',
          source: `r-${key}`,
          paint: { 'raster-opacity': key === 's2_truecolor' ? 1 : 0.85, 'raster-resampling': 'nearest' },
          layout: { visibility: 'none' },
        })
      }

      if (job.outputs.layers.density) {
        map.addSource('density', { type: 'geojson', data: abs(fileUrl(job.id, job.outputs.layers.density.file)) })
        map.addLayer({
          id: 'density',
          type: 'fill',
          source: 'density',
          paint: { 'fill-color': FSI_COLORS, 'fill-opacity': 0.6, 'fill-outline-color': 'rgba(255,255,255,0.25)' },
          layout: { visibility: 'none' },
        })
      }
      if (hasCrowns) {
        map.addSource('crowns', { type: 'geojson', data: abs(fileUrl(job.id, job.outputs.layers.crowns.file)) })
        map.addLayer({
          id: 'crowns',
          type: 'fill',
          source: 'crowns',
          paint: { 'fill-color': heightColor, 'fill-opacity': 0.75, 'fill-outline-color': 'rgba(0,0,0,0.35)' },
        })
      }
      if (hasTrees) {
        map.addSource('trees', { type: 'geojson', data: abs(fileUrl(job.id, job.outputs.layers.trees.file)) })
        map.addLayer({
          id: 'trees',
          type: 'circle',
          source: 'trees',
          paint: {
            'circle-color': heightColor,
            'circle-radius': ['interpolate', ['linear'], ['zoom'], 13, 1.5, 17, 4, 19, 7],
            'circle-stroke-color': '#fff',
            'circle-stroke-width': ['interpolate', ['linear'], ['zoom'], 14, 0, 17, 1],
          },
          layout: { visibility: 'none' },
        })
        map.addLayer({
          id: 'tree-focus',
          type: 'circle',
          source: 'trees',
          filter: ['==', ['get', 'tree_id'], ''],
          paint: { 'circle-radius': 10, 'circle-color': 'rgba(0,0,0,0)', 'circle-stroke-color': '#ffd400', 'circle-stroke-width': 3 },
        })
      }
      if (hasTrees) {
        map.addSource('trees-3d', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } })
        map.addLayer({
          id: 'trees-3d',
          type: 'fill-extrusion',
          source: 'trees-3d',
          paint: {
            'fill-extrusion-color': ['get', 'color'],
            'fill-extrusion-base': ['get', 'base'],
            'fill-extrusion-height': ['get', 'top'],
            'fill-extrusion-opacity': 1,
            'fill-extrusion-vertical-gradient': true,
          },
          layout: { visibility: 'none' },
        })
        fetch(abs(fileUrl(job.id, job.outputs.layers.trees.file)))
          .then((r) => r.json())
          .then((fc: FeatureCollection<Point>) => {
            ;(map.getSource('trees-3d') as maplibregl.GeoJSONSource | undefined)?.setData(buildTreeModels(fc))
            setSpecies(speciesPresent(fc))
          })
          .catch(() => {})
      }
      map.addSource('aoi', { type: 'geojson', data: abs(fileUrl(job.id, job.outputs.layers.aoi.file)) })
      map.addLayer({ id: 'aoi', type: 'line', source: 'aoi', paint: { 'line-color': '#ffd400', 'line-width': 2.5 } })
      addSiteMask(map, site)
      map.on('mousemove', (e: MapMouseEvent) => setElev(elevationAt(map, [e.lngLat.lng, e.lngLat.lat])))
      map.on('mouseout', () => setElev(null))

      const treeLayers = ['trees', 'crowns', 'trees-3d']
      for (const layer of treeLayers) {
        map.on('mouseenter', layer, () => (map.getCanvas().style.cursor = 'pointer'))
        map.on('mouseleave', layer, () => (map.getCanvas().style.cursor = ''))
      }
      map.on('click', (e: MapMouseEvent) => {
        const feats = map.queryRenderedFeatures(e.point, {
          layers: [...treeLayers, 'density'].filter((l) => map.getLayer(l) && map.getLayoutProperty(l, 'visibility') !== 'none'),
        })
        if (!feats.length) return
        const f = feats[0]
        const p = f.properties as Record<string, unknown>
        let html: string
        if (f.layer.id === 'density') {
          html = `<strong>Grid cell</strong><table class="popup-table">
            <tr><td>Canopy cover</td><td>${p.canopy_cover_pct}%</td></tr>
            <tr><td>Density class</td><td>${p.fsi_class}</td></tr>
            <tr><td>Trees detected</td><td>${p.detected_trees}</td></tr>
            <tr><td>Trees / ha</td><td>${p.trees_per_ha}</td></tr>
            <tr><td>Mean height</td><td>${p.mean_tree_height_m ?? '–'} m</td></tr></table>`
        } else {
          const treeFeat = hasTrees
            ? map.querySourceFeatures('trees', { filter: ['==', ['get', 'tree_id'], p.tree_id as string] })[0]
            : undefined
          const tp = (treeFeat?.properties ?? p) as Record<string, unknown>
          const rows = EXTRA_POPUP_FIELDS.filter(([k]) => tp[k] !== undefined && tp[k] !== null)
            .map(([k, lab]) => `<tr><td>${lab}</td><td>${k === 'species_status' ? 'Not determined (satellite)' : tp[k]}</td></tr>`)
            .join('')
          const sp = tp.species
            ? `${tp.species}${tp.species_confidence != null ? ` (${Math.round(Number(tp.species_confidence) * 100)}%)` : ''}`
            : 'Not determined (satellite mode)'
          html = `<strong>Tree ${p.tree_id}</strong><table class="popup-table"><tr><td>Species</td><td>${sp}</td></tr>${rows}</table>`
        }
        new maplibregl.Popup({ closeButton: true, maxWidth: '280px' }).setLngLat(e.lngLat).setHTML(html).addTo(map)
      })
      setReady(true)
    })
    return () => {
      map.remove()
      mapRef.current = null
    }
  }, [job, hasCrowns, hasTrees])

  useEffect(() => {
    const map = mapRef.current
    if (!map || !ready) return
    const set = (id: string, on: boolean) => map.getLayer(id) && map.setLayoutProperty(id, 'visibility', on ? 'visible' : 'none')
    for (const k of rasters) set(`r-${k}`, vis[k])
    set('density', vis.density)
    set('crowns', vis.crowns && !three)
    set('trees-3d', (vis.crowns || vis.trees) && three)
    set('trees', vis.trees && !three)
    set('aoi', vis.aoi)
    set('satellite', basemap === 'satellite')
    set('streets', basemap === 'streets')
    setTerrainVisible(map, terrain)
  }, [vis, three, ready, basemap, rasters, terrain])

  useEffect(() => {
    const map = mapRef.current
    if (!map || !ready) return
    map.easeTo({ pitch: three ? 60 : 0, bearing: three ? -20 : 0, duration: 900 })
  }, [three, ready])

  // The map lives in a hidden tab; resize when it becomes visible so camera maths uses the real size.
  useEffect(() => {
    if (visible && ready) mapRef.current?.resize()
  }, [visible, ready])

  useEffect(() => {
    const map = mapRef.current
    if (!map || !ready || !focus || !visible) return
    setVis((v) => ({ ...v, trees: true }))
    if (map.getLayer('tree-focus')) map.setFilter('tree-focus', ['==', ['get', 'tree_id'], focus.treeId])
    map.resize()
    map.flyTo({ center: [focus.lon, focus.lat], zoom: 18.5, duration: 1200 })
  }, [focus, ready, visible])

  const toggle = (k: string) => setVis((v) => ({ ...v, [k]: !v[k] }))
  const activeRaster = [...rasters].reverse().find((k) => vis[k])
  const legend: Legend | null | undefined = activeRaster ? job.outputs.rasters[activeRaster].legend : null

  return (
    <div className="map-wrap">
      <div ref={el} className="map" />
      {terrain && elev != null && <div className="map-elev">Elevation {Math.round(elev)} m</div>}
      <button className="layers-toggle" onClick={() => setShowLayers(!showLayers)} aria-expanded={showLayers}>
        {showLayers ? '✕ Close' : '☰ Layers'}
      </button>
      <div className={`map-controls ${showLayers ? '' : 'hidden'}`}>
        <h3>View</h3>
        <label>
          <input type="checkbox" checked={three} onChange={() => setThree(!three)} /> 3D trees
        </label>
        <label>
          <input type="checkbox" checked={basemap === 'streets'}
            onChange={() => setBasemap(basemap === 'satellite' ? 'streets' : 'satellite')} /> Street map
        </label>
        <label>
          <input type="checkbox" checked={terrain} onChange={() => setTerrain(!terrain)} /> Terrain
        </label>
        <h3>Trees</h3>
        <label><input type="checkbox" checked={vis.aoi} onChange={() => toggle('aoi')} /> Boundary</label>
        {hasCrowns && <label><input type="checkbox" checked={vis.crowns} onChange={() => toggle('crowns')} /> Crowns</label>}
        {hasTrees && <label><input type="checkbox" checked={vis.trees} onChange={() => toggle('trees')} /> Tree tops</label>}
        {job.outputs.layers.density && (
          <label><input type="checkbox" checked={vis.density} onChange={() => toggle('density')} /> Density class</label>
        )}
        {rasters.length > 0 && <h3>Layers</h3>}
        {rasters.map((k) => (
          <label key={k}>
            <input type="checkbox" checked={vis[k]} onChange={() => toggle(k)} /> {job.outputs.rasters[k].label.replace(/\s*\(.*\)$/, '')}
          </label>
        ))}
      </div>

      <div className="legend">
        {three && species.length > 0 && (vis.crowns || vis.trees) && (
          <div>
            <strong>Species (3D trees)</strong>
            {species.map((s) => (
              <div key={s.key} className="legend-row"><span className="swatch" style={{ background: s.color }} />{s.label}</div>
            ))}
          </div>
        )}
        {vis.density && (
          <div>
            <strong>Forest density (FSI)</strong>
            {[['#0b5d1e', 'Very dense ≥70%'], ['#3f9b35', 'Moderately dense 40–70%'], ['#a7d46f', 'Open 10–40%'], ['#e8dcb5', 'Scrub / non-forest']].map(([c, l]) => (
              <div key={l} className="legend-row"><span className="swatch" style={{ background: c }} />{l}</div>
            ))}
          </div>
        )}
        {legend && activeRaster && (
          <div style={{ marginTop: 6 }}>
            <strong>{job.outputs.rasters[activeRaster].label}</strong>
            {legend.type === 'continuous' ? (
              <>
                <div className="ramp" style={{ background: CMAP_CSS[legend.cmap ?? 'YlGn'] }} />
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span>{legend.min}</span><span>{legend.max} {legend.unit}</span>
                </div>
              </>
            ) : (
              legend.items?.map((it) => (
                <div key={it.label} className="legend-row"><span className="swatch" style={{ background: it.color }} />{it.label}</div>
              ))
            )}
          </div>
        )}
      </div>
    </div>
  )
}
