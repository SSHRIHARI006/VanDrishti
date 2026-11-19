"""Inventory exports: CSV, KMZ (Google Earth), Shapefile (QGIS/ArcGIS), PDF report."""

from __future__ import annotations

import csv
import io
import json
import zipfile
from xml.sax.saxutils import escape

import numpy as np
import shapefile  # pyshp
from pyproj import CRS

CSV_FIELDS = [
    "tree_id", "latitude", "longitude", "height_m", "crown_area_m2", "crown_diameter_m",
    "local_canopy_density_pct", "fsi_density_class", "ndvi", "vegetation_condition",
    "ground_elevation_m", "species", "species_confidence", "species_status",
    "detection_method", "height_source", "quality_flags",
]

HEIGHT_BINS = [0, 5, 10, 15, 20, 25, 30, 200]
HEIGHT_STYLES = [  # (max height, KML colour aabbggrr, label)
    (10, "ff7fd6a7", "5–10 m"),
    (15, "ff35a64f", "10–15 m"),
    (20, "ff1e7a1e", "15–20 m"),
    (999, "ff0b4d0b", "20 m +"),
]


def height_histogram(heights: np.ndarray) -> list[dict]:
    if heights.size == 0:
        return []
    counts, edges = np.histogram(heights, bins=HEIGHT_BINS)
    labels = [f"{int(edges[i])}–{int(edges[i + 1])} m" for i in range(len(edges) - 2)] + [f"{int(edges[-2])}+ m"]
    return [{"label": lab, "count": int(c)} for lab, c in zip(labels, counts)]


def write_csv(path, records: list[dict]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS, extrasaction="ignore")
        w.writeheader()
        for r in records:
            w.writerow({**r, "quality_flags": ";".join(r.get("quality_flags") or [])})


# ---------------------------------------------------------------------------
# KMZ
# ---------------------------------------------------------------------------

def _kml_coords(ring) -> str:
    return " ".join(f"{x:.7f},{y:.7f},0" for x, y in ring)


def _kml_polygon(geom: dict) -> str:
    polys = [geom["coordinates"]] if geom["type"] == "Polygon" else geom["coordinates"]
    out = []
    for poly in polys:
        inner = "".join(
            f"<innerBoundaryIs><LinearRing><coordinates>{_kml_coords(r)}</coordinates></LinearRing></innerBoundaryIs>"
            for r in poly[1:]
        )
        out.append(f"<Polygon><outerBoundaryIs><LinearRing><coordinates>{_kml_coords(poly[0])}"
                   f"</coordinates></LinearRing></outerBoundaryIs>{inner}</Polygon>")
    return out[0] if len(out) == 1 else f"<MultiGeometry>{''.join(out)}</MultiGeometry>"


def write_kmz(path, name: str, aoi_geom: dict, records: list[dict], density_fc: dict | None) -> None:
    styles = "".join(
        f'<Style id="h{i}"><IconStyle><color>{color}</color><scale>0.5</scale>'
        f"<Icon><href>http://maps.google.com/mapfiles/kml/shapes/placemark_circle.png</href></Icon></IconStyle></Style>"
        for i, (_, color, _) in enumerate(HEIGHT_STYLES)
    )
    fsi_colors = {"VDF": "a01e5d0b", "MDF": "a0359b3f", "OF": "a06fd4a7", "NF": "a0b5dce8"}
    styles += "".join(
        f'<Style id="fsi_{k}"><LineStyle><width>0</width></LineStyle><PolyStyle><color>{c}</color></PolyStyle></Style>'
        for k, c in fsi_colors.items()
    )
    styles += ('<Style id="aoi"><LineStyle><color>ff00d7ff</color><width>3</width></LineStyle>'
               "<PolyStyle><fill>0</fill></PolyStyle></Style>")

    trees = []
    for r in records:
        idx = next(i for i, (mx, _, _) in enumerate(HEIGHT_STYLES) if r["height_m"] < mx)
        desc = "<br/>".join(f"{k}: {escape(str(r.get(k)))}" for k in
                            ("height_m", "crown_area_m2", "local_canopy_density_pct", "fsi_density_class", "ndvi"))
        trees.append(f"<Placemark><name>{r['tree_id']}</name><description><![CDATA[{desc}]]></description>"
                     f"<styleUrl>#h{idx}</styleUrl><Point><coordinates>{r['longitude']},{r['latitude']},0"
                     f"</coordinates></Point></Placemark>")

    cells = []
    for f in (density_fc or {}).get("features", []):
        p = f["properties"]
        if f["geometry"]["type"] not in ("Polygon", "MultiPolygon"):
            continue
        cells.append(f"<Placemark><name>{p['fsi_class']} {p['canopy_cover_pct']}%</name>"
                     f"<styleUrl>#fsi_{p['fsi_class']}</styleUrl>{_kml_polygon(f['geometry'])}</Placemark>")

    kml = (
        '<?xml version="1.0" encoding="UTF-8"?><kml xmlns="http://www.opengis.net/kml/2.2"><Document>'
        f"<name>{escape(name)} – Vandrishti AI tree inventory</name>{styles}"
        f'<Placemark><name>Assessment boundary</name><styleUrl>#aoi</styleUrl>{_kml_polygon(aoi_geom)}</Placemark>'
        f"<Folder><name>Canopy density (FSI class)</name><visibility>0</visibility>{''.join(cells)}</Folder>"
        f"<Folder><name>Trees ({len(records)})</name>{''.join(trees)}</Folder>"
        "</Document></kml>"
    )
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("doc.kml", kml)


# ---------------------------------------------------------------------------
# Shapefile
# ---------------------------------------------------------------------------

def write_shapefile_zip(path, records: list[dict], crowns_fc: dict | None) -> None:
    prj = CRS.from_epsg(4326).to_wkt(version="WKT1_ESRI")
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        shp, shx, dbf = io.BytesIO(), io.BytesIO(), io.BytesIO()
        w = shapefile.Writer(shp=shp, shx=shx, dbf=dbf, shapeType=shapefile.POINT)
        for name, typ, size, dec in [("tree_id", "C", 10, 0), ("height_m", "N", 6, 1), ("crown_m2", "N", 8, 1),
                                     ("crown_dm", "N", 6, 1), ("cover_pct", "N", 5, 1), ("fsi_class", "C", 4, 0),
                                     ("ndvi", "N", 6, 3), ("ground_m", "N", 7, 1), ("species", "C", 30, 0),
                                     ("flags", "C", 60, 0)]:
            w.field(name, typ, size, dec)
        for r in records:
            w.point(r["longitude"], r["latitude"])
            w.record(r["tree_id"], r["height_m"], r["crown_area_m2"], r["crown_diameter_m"],
                     r["local_canopy_density_pct"], r["fsi_density_class"] or "", r["ndvi"], r["ground_elevation_m"],
                     r["species"] or "", ";".join(r["quality_flags"]))
        w.close()
        for ext, buf in (("shp", shp), ("shx", shx), ("dbf", dbf)):
            z.writestr(f"trees.{ext}", buf.getvalue())
        z.writestr("trees.prj", prj)

        if crowns_fc and crowns_fc["features"]:
            shp, shx, dbf = io.BytesIO(), io.BytesIO(), io.BytesIO()
            w = shapefile.Writer(shp=shp, shx=shx, dbf=dbf, shapeType=shapefile.POLYGON)
            w.field("tree_id", "C", 10)
            w.field("height_m", "N", 6, 1)
            w.field("crown_m2", "N", 8, 1)
            for f in crowns_fc["features"]:
                g = f["geometry"]
                rings = g["coordinates"] if g["type"] == "Polygon" else [r for p in g["coordinates"] for r in p]
                w.poly(rings)
                p = f["properties"]
                w.record(p["tree_id"], p["height_m"], p["crown_area_m2"])
            w.close()
            for ext, buf in (("shp", shp), ("shx", shx), ("dbf", dbf)):
                z.writestr(f"crowns.{ext}", buf.getvalue())
            z.writestr("crowns.prj", prj)


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def _read_json(path):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def write_all(job, records: list[dict]) -> list[str]:
    made = []
    write_csv(job.path("tree_inventory.csv"), records)
    job.set_export("csv", "tree_inventory.csv", "Tree inventory (CSV)")
    made.append("CSV")

    job.set_export("geojson", "trees.geojson", "Tree inventory (GeoJSON)")
    made.append("GeoJSON")

    aoi_geom = job.state["aoi"]["geojson"]
    density_fc = _read_json(job.path("density_grid.geojson"))
    write_kmz(job.path("tree_inventory.kmz"), job.state["aoi"]["name"], aoi_geom, records, density_fc)
    job.set_export("kmz", "tree_inventory.kmz", "Google Earth (KMZ)")
    made.append("KMZ")

    write_shapefile_zip(job.path("tree_inventory_shapefile.zip"), records, _read_json(job.path("crowns.geojson")))
    job.set_export("shapefile", "tree_inventory_shapefile.zip", "Shapefile (QGIS / ArcGIS)")
    made.append("Shapefile")

    from .report import write_report

    try:
        write_report(job, records)
        job.set_export("pdf", "assessment_report.pdf", "Assessment report (PDF)")
        made.append("PDF")
    except Exception as exc:  # a report failure must not lose the inventory
        job.event("warning", "REPORT_FAILED", f"PDF report could not be generated: {exc}",
                  action="Other exports are available")
    return made
