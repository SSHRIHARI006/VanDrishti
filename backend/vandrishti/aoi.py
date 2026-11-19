"""Area-of-interest input: safe KML / KMZ / GeoJSON parsing and validation."""

from __future__ import annotations

import io
import json
import math
import zipfile
from dataclasses import dataclass, field

import defusedxml.ElementTree as SafeET
from pyproj import CRS, Transformer
from shapely.geometry import MultiPolygon, Polygon, mapping, shape
from shapely.ops import transform as shp_transform, unary_union
from shapely.validation import make_valid

KMZ_MAX_ENTRIES = 50
KMZ_MAX_UNCOMPRESSED = 20 * 1024 * 1024
INDIA_BBOX = (68.0, 6.0, 98.0, 37.5)


class AOIError(ValueError):
    """The uploaded boundary cannot be used; message is shown to the user."""


@dataclass
class AOI:
    name: str
    geom_wgs84: Polygon | MultiPolygon
    geom_utm: Polygon | MultiPolygon
    utm_epsg: int
    area_km2: float
    warnings: list[str]
    site_extent: dict | None = field(default=None)

    @property
    def bounds_wgs84(self) -> tuple[float, float, float, float]:
        return self.geom_wgs84.bounds

    def to_utm(self):
        return Transformer.from_crs(4326, self.utm_epsg, always_xy=True).transform

    def to_wgs84(self):
        return Transformer.from_crs(self.utm_epsg, 4326, always_xy=True).transform

    def summary(self) -> dict:
        c = self.geom_wgs84.centroid
        return {
            "name": self.name,
            "area_km2": round(self.area_km2, 3),
            "area_ha": round(self.area_km2 * 100, 1 if self.area_km2 >= 0.1 else 3),
            "bounds": list(self.bounds_wgs84),
            "centroid": [c.x, c.y],
            "utm_epsg": self.utm_epsg,
            "geojson": mapping(self.geom_wgs84),
            "site_extent": self.site_extent,
        }


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _parse_coords(text: str | None) -> list[tuple[float, float]]:
    pts = []
    for token in (text or "").split():
        parts = token.split(",")
        if len(parts) < 2:
            continue
        try:
            pts.append((float(parts[0]), float(parts[1])))
        except ValueError as exc:
            raise AOIError(f"Invalid coordinate '{token}' in KML") from exc
    return pts


def _ring_coords(boundary_el) -> list[tuple[float, float]]:
    for el in boundary_el.iter():
        if _local(el.tag) == "coordinates":
            return _parse_coords(el.text)
    return []


def parse_kml(data: bytes) -> tuple[str, list[Polygon]]:
    try:
        root = SafeET.fromstring(data)
    except Exception as exc:  # defusedxml raises several exception types
        raise AOIError(f"Could not read KML: {exc}") from exc

    name = ""
    polygons: list[Polygon] = []
    for el in root.iter():
        tag = _local(el.tag)
        if tag == "name" and not name and el.text:
            name = el.text.strip()
        if tag != "Polygon":
            continue
        outer, holes = [], []
        for child in el:
            ctag = _local(child.tag)
            if ctag == "outerBoundaryIs":
                outer = _ring_coords(child)
            elif ctag == "innerBoundaryIs":
                ring = _ring_coords(child)
                if len(ring) >= 4:
                    holes.append(ring)
        if len(outer) >= 4:
            polygons.append(Polygon(outer, holes))
    return name, polygons


def parse_kmz(data: bytes) -> tuple[str, list[Polygon]]:
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise AOIError("KMZ file is not a valid zip archive") from exc
    infos = zf.infolist()
    if len(infos) > KMZ_MAX_ENTRIES:
        raise AOIError("KMZ contains too many files")
    if sum(i.file_size for i in infos) > KMZ_MAX_UNCOMPRESSED:
        raise AOIError("KMZ is too large when uncompressed")
    kml_entries = [i for i in infos if i.filename.lower().endswith(".kml")]
    if not kml_entries:
        raise AOIError("KMZ does not contain a .kml file")
    kml_entries.sort(key=lambda i: (i.filename.lower() != "doc.kml", i.filename))
    with zf.open(kml_entries[0]) as f:
        return parse_kml(f.read(KMZ_MAX_UNCOMPRESSED + 1))


SITE_RADIUS_RANGE_M = (100.0, 5000.0)


def _site_extent(props: dict, geom: dict | None) -> dict | None:
    """Circle the user drew around the site on the map: a Point centre plus radius_m."""
    try:
        lon, lat = (float(v) for v in (geom or {}).get("coordinates", [])[:2])
        r = float(props.get("radius_m"))
    except (TypeError, ValueError):
        return None
    lo, hi = SITE_RADIUS_RANGE_M
    if not (math.isfinite(lon) and math.isfinite(lat) and -180 <= lon <= 180 and -90 <= lat <= 90 and lo <= r <= hi):
        return None
    return {"center": [lon, lat], "radius_m": round(r, 1)}


def parse_geojson(data: bytes) -> tuple[str, list[Polygon], dict | None]:
    try:
        obj = json.loads(data)
    except json.JSONDecodeError as exc:
        raise AOIError(f"Could not read GeoJSON: {exc}") from exc
    feats = obj.get("features") if obj.get("type") == "FeatureCollection" else [obj]
    polygons = []
    extent = None
    boundary_feats = []
    for f in feats or []:
        props = (f.get("properties") or {}) if isinstance(f, dict) else {}
        if props.get("role") == "site_extent":
            extent = _site_extent(props, f.get("geometry"))
            continue
        boundary_feats.append(f)
        geom = f.get("geometry", f) if isinstance(f, dict) else None
        if not geom:
            continue
        g = shape(geom)
        if isinstance(g, Polygon):
            polygons.append(g)
        elif isinstance(g, MultiPolygon):
            polygons.extend(g.geoms)
    name = (boundary_feats[0].get("properties") or {}).get("name", "") if boundary_feats else ""
    return name, polygons, extent


def utm_epsg_for(lon: float, lat: float) -> int:
    zone = int((math.floor((lon + 180.0) / 6.0) % 60) + 1)
    return (32700 if lat < 0 else 32600) + zone


def load_aoi(
    filename: str,
    data: bytes,
    max_km2: float,
    warn_km2: float,
    min_km2: float = 0.01,
) -> AOI:
    lower = filename.lower()
    extent = None
    if lower.endswith(".kmz"):
        name, polys = parse_kmz(data)
    elif lower.endswith(".kml"):
        name, polys = parse_kml(data)
    elif lower.endswith((".geojson", ".json")):
        name, polys, extent = parse_geojson(data)
    else:
        raise AOIError("Unsupported file type: upload a .kml, .kmz or .geojson boundary")

    if not polys:
        raise AOIError("No polygon found. The boundary must be a closed polygon, not points or lines")

    geom = make_valid(unary_union([make_valid(p) for p in polys]))
    if isinstance(geom, (Polygon, MultiPolygon)):
        pass
    else:
        parts = [g for g in getattr(geom, "geoms", []) if isinstance(g, (Polygon, MultiPolygon))]
        if not parts:
            raise AOIError("Boundary geometry is invalid")
        geom = unary_union(parts)

    minx, miny, maxx, maxy = geom.bounds
    if not (-180 <= minx <= 180 and -90 <= miny <= 90 and -180 <= maxx <= 180 and -90 <= maxy <= 90):
        raise AOIError("Coordinates are not longitude/latitude (WGS84)")

    c = geom.centroid
    epsg = utm_epsg_for(c.x, c.y)
    to_utm = Transformer.from_crs(4326, epsg, always_xy=True).transform
    geom_utm = shp_transform(to_utm, geom)
    area_km2 = geom_utm.area / 1e6

    warnings = []
    if area_km2 < min_km2:
        raise AOIError(f"Area is too small ({area_km2 * 100:.2f} ha); minimum is {min_km2 * 100:g} ha")
    if area_km2 > max_km2:
        raise AOIError(
            f"Area is {area_km2:.1f} km², above the {max_km2:g} km² limit for one run. "
            "Split the boundary into smaller blocks"
        )
    if area_km2 > warn_km2:
        warnings.append(f"Large area ({area_km2:.1f} km²): processing may take several minutes")
    ix0, iy0, ix1, iy1 = INDIA_BBOX
    if not (ix0 <= c.x <= ix1 and iy0 <= c.y <= iy1):
        warnings.append("Boundary is outside India: Forest Survey of India density classes may not apply")
    if len(polys) > 1:
        warnings.append(f"{len(polys)} polygons found; they are merged into one assessment area")

    return AOI(
        name=name or filename.rsplit(".", 1)[0],
        geom_wgs84=geom,
        geom_utm=geom_utm,
        utm_epsg=epsg,
        area_km2=area_km2,
        warnings=warnings,
        site_extent=extent,
    )


def utm_crs(epsg: int) -> CRS:
    return CRS.from_epsg(epsg)
