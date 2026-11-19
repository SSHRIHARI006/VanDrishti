export type StageStatus = 'pending' | 'running' | 'done' | 'skipped' | 'failed'
export type JobStatus = 'queued' | 'running' | 'completed' | 'failed'
export type EventLevel = 'info' | 'warning' | 'error'

export interface Stage {
  id: string
  name: string
  description: string
  status: StageStatus
  started_at: string | null
  finished_at: string | null
  summary: string | null
  metrics: Record<string, unknown>
  preview: string | null
}

export interface JobEvent {
  time: string
  level: EventLevel
  code: string
  stage: string | null
  message: string
  action: string | null
}

export interface AOISummary {
  name: string
  area_km2: number
  area_ha: number
  bounds: [number, number, number, number]
  centroid: [number, number]
  utm_epsg: number
  geojson: { type: string; coordinates: unknown }
  site_extent?: { center: [number, number]; radius_m: number } | null
}

export interface Legend {
  type: 'continuous' | 'categorical'
  cmap?: string
  min?: number
  max?: number
  unit?: string
  items?: { label: string; color: string }[]
}

export interface RasterOutput {
  file: string
  corners: [number, number][]
  label: string
  legend: Legend | null
}

export interface FileOutput {
  file: string
  label: string
}

export interface Provenance {
  dataset: string
  source: string
  resolution_m?: number
  license: string
  notes?: string
  period?: string
  scenes?: number
}

export interface Confidence {
  level: string
  reason: string
}

export interface SiteSpecies {
  name: string
  english_name: string | null
  local_name: string | null
  family: string | null
  share_pct: number
  similar_site_records: number
  often_planted: boolean
  recorded_nearby: boolean
}

export interface SiteSpeciesSummary {
  ecoregion: string | null
  biome: string | null
  realm: string | null
  climate: { mean_temp_c: number; max_temp_c: number; min_temp_c: number; annual_rain_mm: number; dry_quarter_rain_mm: number; rain_seasonality: number }
  soil: { sand_pct: number; clay_pct: number; ph: number; organic_carbon_g_kg: number }
  species: SiteSpecies[]
  n_candidates: number
  n_suitable: number
  n_reference_records: number | null
  in_india?: boolean
  n_records: number | null
  table_built: string | null
  method: string
  caveat: string
}

export interface Summary {
  area_ha?: number
  mode?: string
  tree_count?: {
    detected: number
    estimated_total: number
    estimated_low: number
    estimated_high: number
    method: string
  }
  density?: {
    canopy_cover_pct: number
    canopy_area_ha: number
    fsi_area_ha: Record<string, number>
    fsi_area_pct: Record<string, number>
    dominant_fsi_class: string
  }
  height?: {
    mean_m: number | null
    median_m: number | null
    max_m: number | null
    histogram: { label: string; count: number }[]
  }
  crown_area_median_m2?: number | null
  species?: Record<string, number>
  site_species?: SiteSpeciesSummary
  ndvi?: { available: boolean; mean_ndvi?: number; class_pct?: Record<string, number> }
  leaf_fall?: {
    available: boolean
    mean_drop_pct?: number
    class_pct?: Record<string, number>
    dominant?: string
    leaf_on?: string
    dry?: string
  }
  landcover?: Record<string, number>
  terrain?: {
    available: boolean
    elevation_min_m?: number
    elevation_max_m?: number
    elevation_mean_m?: number
    slope_mean_deg?: number
    slope_max_deg?: number
    steep_area_pct?: number
  }
  quality?: { confidence: Record<string, Confidence>; flagged_trees: number }
  s2?: { scenes?: number; start?: string; end?: string; valid_pct?: number }
}

export interface Job {
  id: string
  name: string
  mode: string
  created_at: string
  finished_at: string | null
  status: JobStatus
  current_stage?: string
  options: Record<string, unknown>
  aoi: AOISummary | null
  stages: Stage[]
  outputs: {
    layers: Record<string, FileOutput>
    rasters: Record<string, RasterOutput>
    exports: Record<string, FileOutput>
  }
  summary: Summary
  provenance: Provenance[]
  event_counts: Record<EventLevel, number>
  events: JobEvent[]
}

export interface JobListItem {
  id: string
  name: string
  mode: string
  status: JobStatus
  created_at: string
  finished_at: string | null
  summary: Summary
  aoi: AOISummary | null
  event_counts: Record<EventLevel, number>
}

export interface TreeProps {
  tree_id: string
  latitude: number
  longitude: number
  height_m: number
  crown_area_m2: number
  crown_diameter_m: number
  local_canopy_density_pct: number
  fsi_density_class: string | null
  ndvi: number | null
  vegetation_condition: string | null
  ground_elevation_m: number | null
  species: string | null
  species_confidence: number | null
  species_status: string
  detection_score: number | null
  quality_flags: string[]
}

export type SurveyInput = 'ortho' | 'dsm' | 'dtm' | 'chm'

export interface SurveySample {
  id: string
  name: string
  description: string
  attribution: string
  inputs: SurveyInput[]
}
