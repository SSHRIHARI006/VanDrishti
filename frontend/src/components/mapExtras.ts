import type { Map as MLMap } from 'maplibre-gl'

export type LonLat = [number, number]
export interface SiteExtent { center: LonLat; radius_m: number }

// Free global terrain (SRTM / ETOPO / national DEMs), terrarium-encoded PNG tiles.
const TERRAIN_TILES = ['https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png']
export const TERRAIN_EXAGGERATION = 1.5

export function addTerrain(map: MLMap, beforeLayer?: string) {
  const dem = { type: 'raster-dem' as const, tiles: TERRAIN_TILES, tileSize: 256, maxzoom: 15, encoding: 'terrarium' as const,
    attribution: 'Terrain: AWS Terrain Tiles (SRTM, ETOPO)' }
  // separate sources for 3D mesh and hillshade, as MapLibre recommends
  map.addSource('terrain-dem', dem)
  map.addSource('hillshade-dem', dem)
  map.addLayer({
    id: 'hillshade', type: 'hillshade', source: 'hillshade-dem',
    paint: { 'hillshade-exaggeration': 0.45, 'hillshade-shadow-color': '#1b2a1f', 'hillshade-highlight-color': '#ffffff' },
  }, beforeLayer)
  map.setTerrain({ source: 'terrain-dem', exaggeration: TERRAIN_EXAGGERATION })
}

export function setTerrainVisible(map: MLMap, on: boolean) {
  if (!map.getSource('terrain-dem')) return
  map.setTerrain(on ? { source: 'terrain-dem', exaggeration: TERRAIN_EXAGGERATION } : null)
  if (map.getLayer('hillshade')) map.setLayoutProperty('hillshade', 'visibility', on ? 'visible' : 'none')
}

export function elevationAt(map: MLMap, ll: LonLat): number | null {
  const e = map.getTerrain() ? map.queryTerrainElevation(ll) : null
  return e == null ? null : e / TERRAIN_EXAGGERATION
}

const M_PER_DEG = 111320

export function distM(a: LonLat, b: LonLat): number {
  const k = Math.cos(((a[1] + b[1]) / 2) * (Math.PI / 180))
  return Math.hypot((a[0] - b[0]) * M_PER_DEG * k, (a[1] - b[1]) * M_PER_DEG)
}

export function circleRing(c: LonLat, r: number, n = 128): LonLat[] {
  const dLat = r / M_PER_DEG
  const dLon = r / (M_PER_DEG * Math.cos((c[1] * Math.PI) / 180))
  const ring: LonLat[] = []
  for (let i = 0; i <= n; i++) {
    const a = (i / n) * 2 * Math.PI
    ring.push([c[0] + dLon * Math.cos(a), c[1] + dLat * Math.sin(a)])
  }
  return ring
}

export function circleBounds(c: LonLat, r: number, pad = 1): [LonLat, LonLat] {
  const dLat = (r * pad) / M_PER_DEG
  const dLon = (r * pad) / (M_PER_DEG * Math.cos((c[1] * Math.PI) / 180))
  return [[c[0] - dLon, c[1] - dLat], [c[0] + dLon, c[1] + dLat]]
}

// Everything outside the site circle: a world polygon with the circle as a hole.
export function siteMask(e: SiteExtent): GeoJSON.FeatureCollection {
  const world: LonLat[] = [[-180, -85], [180, -85], [180, 85], [-180, 85], [-180, -85]]
  const ring = circleRing(e.center, e.radius_m)
  return {
    type: 'FeatureCollection',
    features: [
      { type: 'Feature', properties: { kind: 'mask' }, geometry: { type: 'Polygon', coordinates: [world, [...ring].reverse()] } },
      { type: 'Feature', properties: { kind: 'rim' }, geometry: { type: 'LineString', coordinates: ring } },
    ],
  }
}

export function addSiteMask(map: MLMap, e: SiteExtent) {
  map.addSource('site-mask', { type: 'geojson', data: siteMask(e) })
  map.addLayer({ id: 'site-mask', type: 'fill', source: 'site-mask', filter: ['==', ['get', 'kind'], 'mask'],
    paint: { 'fill-color': '#eef2ef', 'fill-opacity': 1 } })
  map.addLayer({ id: 'site-rim', type: 'line', source: 'site-mask', filter: ['==', ['get', 'kind'], 'rim'],
    paint: { 'line-color': '#1f5f3b', 'line-width': 2, 'line-dasharray': [3, 2] } })
}

// Old assessments (uploaded KML) have no drawn circle: fit one around the boundary with a margin.
export function extentForBounds(b: [number, number, number, number]): SiteExtent {
  const c: LonLat = [(b[0] + b[2]) / 2, (b[1] + b[3]) / 2]
  const r = distM(c, [b[2], b[3]])
  return { center: c, radius_m: Math.max(80, r * 1.4 + 50) }
}
