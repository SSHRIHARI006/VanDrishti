import type { FeatureCollection, Point, Polygon } from 'geojson'

// A tree model = trunk + a crown built from stacked discs. The crown spans crownBase..1 of the
// tree height; profile(t) gives the disc radius (fraction of crown radius) at t = 0 (crown
// bottom) .. 1 (crown top). fill-extrusion renders each disc as a short solid cylinder.
interface Shape { trunkTop: number; trunkWidth: number; crownBase: number; width: number; profile: (t: number) => number }

const ellipse = (t: number) => Math.sqrt(Math.max(0, 1 - (2 * t - 1) ** 2))

const SHAPES: Record<string, Shape> = {
  round: { trunkTop: 0.45, trunkWidth: 0.12, crownBase: 0.3, width: 1, profile: (t) => Math.max(0.2, ellipse(t)) },
  oval: { trunkTop: 0.35, trunkWidth: 0.11, crownBase: 0.25, width: 0.85, profile: (t) => Math.max(0.2, ellipse(t * 0.9 + 0.05)) },
  spreading: { trunkTop: 0.35, trunkWidth: 0.15, crownBase: 0.3, width: 1.1, profile: (t) => Math.max(0.25, ellipse(t) ** 0.5) },
  columnar: { trunkTop: 0.4, trunkWidth: 0.1, crownBase: 0.3, width: 0.6, profile: (t) => Math.max(0.2, ellipse(t)) },
  cone: { trunkTop: 0.15, trunkWidth: 0.1, crownBase: 0.1, width: 0.9, profile: (t) => 1 - 0.9 * t },
  pyramid: { trunkTop: 0.2, trunkWidth: 0.12, crownBase: 0.15, width: 1, profile: (t) => 0.15 + 0.85 * (1 - t) ** 0.8 },
  tuft: { trunkTop: 0.8, trunkWidth: 0.09, crownBase: 0.66, width: 0.7, profile: (t) => Math.max(0.2, ellipse(t)) },
  umbrella: { trunkTop: 0.62, trunkWidth: 0.1, crownBase: 0.58, width: 1.1, profile: (t) => (t < 0.7 ? 0.55 + 0.45 * (t / 0.7) : 1 - ((t - 0.7) / 0.3) * 0.5) },
}

export interface SpeciesStyle { key: string; label: string; shape: keyof typeof SHAPES; color: string }

// Order matters: first pattern that matches the species code or name wins.
const STYLES: [RegExp, SpeciesStyle][] = [
  [/^pipa2$|palustris|longleaf/i, { key: 'longleaf', label: 'Longleaf pine', shape: 'tuft', color: '#2f5d46' }],
  [/^pi[a-z]{2}\d?$|pinus|abies|picea|cedrus|cupressus|conifer/i, { key: 'conifer', label: 'Pine / conifer', shape: 'cone', color: '#24553a' }],
  [/^qu|quercus|oak/i, { key: 'oak', label: 'Oak', shape: 'spreading', color: '#5f7f2c' }],
  [/^acru$|^ac[a-z]{2}\d?$|acer|maple/i, { key: 'maple', label: 'Maple', shape: 'oval', color: '#b0452a' }],
  [/^amla$|amelanchier|serviceberry/i, { key: 'serviceberry', label: 'Serviceberry', shape: 'round', color: '#c28a2c' }],
  [/^litu$|liriodendron|tulip/i, { key: 'tulip', label: 'Tulip poplar', shape: 'columnar', color: '#9bbf3a' }],
  [/^magno$|magnolia/i, { key: 'magnolia', label: 'Magnolia', shape: 'pyramid', color: '#1f4f2f' }],
  [/^nysy$|nyssa|black ?gum/i, { key: 'gum', label: 'Black gum', shape: 'oval', color: '#6b3d5a' }],
  [/tectona|teak|sagwan|sagaun/i, { key: 'teak', label: 'Teak', shape: 'umbrella', color: '#8fae3e' }],
  [/shorea|\bsal\b/i, { key: 'sal', label: 'Sal', shape: 'columnar', color: '#2e6b34' }],
  [/madhuca|mahua|mahuwa/i, { key: 'mahua', label: 'Mahua', shape: 'spreading', color: '#3f6a2a' }],
  [/azadirachta|neem/i, { key: 'neem', label: 'Neem', shape: 'round', color: '#4f9a3a' }],
  [/mangifera|mango|\baam\b/i, { key: 'mango', label: 'Mango', shape: 'spreading', color: '#2d5a2a' }],
  [/eucalyptus|nilgiri/i, { key: 'eucalyptus', label: 'Eucalyptus', shape: 'columnar', color: '#8fa8a0' }],
  [/diospyros|tendu/i, { key: 'tendu', label: 'Tendu', shape: 'round', color: '#46703a' }],
  [/acacia|babul|prosopis|vachellia/i, { key: 'babul', label: 'Babul / acacia', shape: 'umbrella', color: '#7a8f45' }],
  [/^unknown$/i, { key: 'unknown', label: 'Unknown (low confidence)', shape: 'round', color: '#6f8f5c' }],
]
const OTHER: SpeciesStyle = { key: 'other', label: 'Other species', shape: 'oval', color: '#7aa05a' }
const GENERIC: SpeciesStyle = { key: 'generic', label: 'Species not determined', shape: 'round', color: '' }

export function styleFor(species: unknown): SpeciesStyle {
  if (species == null || species === '') return GENERIC
  const s = String(species)
  return STYLES.find(([re]) => re.test(s))?.[1] ?? OTHER
}

const HEIGHT_GREENS: [number, string][] = [[5, '#8cc152'], [10, '#5a9e3a'], [15, '#3b7f2c'], [20, '#2a6424'], [30, '#1d4a1c']]
const heightGreen = (h: number) => (HEIGHT_GREENS.find(([m]) => h <= m) ?? HEIGHT_GREENS[HEIGHT_GREENS.length - 1])[1]

function shade(hex: string, f: number): string {
  const n = parseInt(hex.slice(1), 16)
  const ch = (v: number) => Math.round(f >= 0 ? v + (255 - v) * f : v * (1 + f))
  return `#${[n >> 16, (n >> 8) & 255, n & 255].map((v) => ch(v).toString(16).padStart(2, '0')).join('')}`
}

function disc(lon: number, lat: number, rM: number, seg: number): number[][] {
  const dLat = rM / 111320
  const dLon = rM / (111320 * Math.cos((lat * Math.PI) / 180))
  const ring = []
  for (let i = 0; i <= seg; i++) {
    const a = (i / seg) * 2 * Math.PI
    ring.push([lon + dLon * Math.cos(a), lat + dLat * Math.sin(a)])
  }
  return ring
}

export const VERTICAL_EXAGGERATION = 1.2

// Stable per-tree number in [0, 1) so each tree keeps its colour tint between reloads.
function hash01(s: string): number {
  let h = 2166136261
  for (let i = 0; i < s.length; i++) h = Math.imul(h ^ s.charCodeAt(i), 16777619)
  return ((h >>> 0) % 1000) / 1000
}

export function buildTreeModels(trees: FeatureCollection<Point>): FeatureCollection<Polygon> {
  const n = trees.features.length
  const seg = n > 20000 ? 6 : 12
  const tiers = n > 20000 ? 4 : n > 3000 ? 6 : 9
  const out: FeatureCollection<Polygon>['features'] = []
  for (const f of trees.features) {
    const p = f.properties ?? {}
    const [lon, lat] = f.geometry.coordinates
    const h = Number(p.height_m) || 5
    const H = h * VERTICAL_EXAGGERATION
    const st = styleFor(p.species)
    const shape = SHAPES[st.shape]
    const r = Math.min(8, Math.max(1, (Number(p.crown_diameter_m) || Math.sqrt(Number(p.crown_area_m2) || 12)) / 2)) * shape.width
    const id = String(p.tree_id ?? '')
    const base = shade(st.color || heightGreen(h), (hash01(id) - 0.5) * 0.16)
    // tall trees with narrow crowns: keep the crown no deeper than ~2.2x its width, trunk fills the rest
    const cb = Math.max(H * shape.crownBase, H - 2.2 * 2 * r)
    const trunkTop = Math.max(H * shape.trunkTop, cb + (H - cb) * (shape.trunkTop - shape.crownBase + 0.05))
    out.push({
      type: 'Feature',
      properties: { tree_id: id, base: 0, top: Math.min(trunkTop, H * 0.95), color: '#5e4128' },
      geometry: { type: 'Polygon', coordinates: [disc(lon, lat, Math.max(0.15, (r / shape.width) * shape.trunkWidth), 6)] },
    })
    const step = (H - cb) / tiers
    for (let i = 0; i < tiers; i++) {
      const rf = shape.profile((i + 0.5) / tiers)
      out.push({
        type: 'Feature',
        // lower discs darker, upper lighter: a cheap stand-in for sunlight from above
        properties: { tree_id: id, base: cb + step * i, top: cb + step * (i + 1), color: shade(base, -0.2 + (0.32 * i) / tiers) },
        geometry: { type: 'Polygon', coordinates: [disc(lon, lat, Math.max(0.2, r * rf), seg)] },
      })
    }
  }
  return { type: 'FeatureCollection', features: out }
}

export function speciesPresent(trees: FeatureCollection<Point>): SpeciesStyle[] {
  const seen = new Map<string, SpeciesStyle>()
  for (const f of trees.features) {
    const st = styleFor(f.properties?.species)
    if (st !== GENERIC) seen.set(st.key, st)
  }
  return [...seen.values()]
}
