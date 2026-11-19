"""PDF assessment report (reportlab + matplotlib charts)."""

from __future__ import annotations

import io
from datetime import datetime

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from reportlab.lib import colors  # noqa: E402
from reportlab.lib.pagesizes import A4  # noqa: E402
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet  # noqa: E402
from reportlab.lib.units import mm  # noqa: E402
from reportlab.platypus import (  # noqa: E402
    Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

from .processing.density import FSI_CLASSES  # noqa: E402

GREEN = colors.HexColor("#1f5f3a")
LIGHT = colors.HexColor("#eef4ef")


def _styles():
    ss = getSampleStyleSheet()
    ss.add(ParagraphStyle("H1x", parent=ss["Title"], textColor=GREEN, fontSize=18, spaceAfter=4))
    ss.add(ParagraphStyle("H2x", parent=ss["Heading2"], textColor=GREEN, spaceBefore=10, spaceAfter=4))
    ss.add(ParagraphStyle("Small", parent=ss["BodyText"], fontSize=8, leading=10))
    ss.add(ParagraphStyle("Cell", parent=ss["BodyText"], fontSize=8.5, leading=10.5))
    return ss


def _table(rows, widths, header=True):
    t = Table(rows, colWidths=widths, repeatRows=1 if header else 0)
    style = [
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#c9d6cc")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 1 if header else 0), (-1, -1), [colors.white, LIGHT]),
    ]
    if header:
        style += [("BACKGROUND", (0, 0), (-1, 0), GREEN), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                  ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold")]
    t.setStyle(TableStyle(style))
    return t


def _png(fig) -> io.BytesIO:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return buf


def _height_chart(hist: list[dict]):
    fig, ax = plt.subplots(figsize=(5.5, 2.3))
    ax.bar([h["label"] for h in hist], [h["count"] for h in hist], color="#3f9b35")
    ax.set_ylabel("Trees")
    ax.set_title("Detected tree height distribution", fontsize=9)
    ax.tick_params(labelsize=7)
    ax.spines[["top", "right"]].set_visible(False)
    return _png(fig)


def _fmt(v, suffix=""):
    if v is None:
        return "–"
    if isinstance(v, float):
        return f"{v:,.1f}{suffix}"
    if isinstance(v, int):
        return f"{v:,}{suffix}"
    return f"{v}{suffix}"


def write_report(job, records: list[dict]) -> None:
    ss = _styles()
    st = job.state
    s = st["summary"]
    aoi = st["aoi"]
    tc = s.get("tree_count", {})
    d = s.get("density", {})
    h = s.get("height", {})
    story = []

    story.append(Paragraph("Vandrishti AI – Forest Tree Inventory Assessment", ss["H1x"]))
    story.append(Paragraph(
        f"<b>{aoi['name']}</b> &nbsp;·&nbsp; Job {st['id']} &nbsp;·&nbsp; "
        f"{datetime.fromisoformat(st['created_at']).strftime('%d %b %Y %H:%M UTC')} &nbsp;·&nbsp; "
        f"Mode: satellite (KML only)", ss["BodyText"]))
    story.append(Spacer(1, 4 * mm))

    story.append(Paragraph("1. Summary", ss["H2x"]))
    ndvi = s.get("ndvi", {})
    rows = [
        ["Indicator", "Value", "Notes"],
        ["Assessment area", f"{aoi['area_ha']:,} ha", f"Centroid {aoi['centroid'][1]:.5f}N, {aoi['centroid'][0]:.5f}E"],
        ["Trees detected (individually mapped)", _fmt(tc.get("detected")), "Crowns resolvable in 1 m canopy height"],
        ["Estimated total canopy trees", f"{_fmt(tc.get('estimated_low'))} – {_fmt(tc.get('estimated_high'))}",
         "Includes canopy not separable into crowns (extrapolated)"],
        ["Canopy cover", _fmt(d.get("canopy_cover_pct"), " %"), "Pixels with canopy ≥ threshold height"],
        ["Dominant density class", {c[0]: c[1] for c in FSI_CLASSES}.get(d.get("dominant_fsi_class"), "–"),
         "Forest Survey of India classes"],
        ["Tree height (median / max)", f"{_fmt(h.get('median_m'), ' m')} / {_fmt(h.get('max_m'), ' m')}",
         "Canopy height model"],
        ["Median crown area", _fmt(s.get("crown_area_median_m2"), " m²"), ""],
        ["Mean NDVI", f"{ndvi['mean_ndvi']:.2f}" if ndvi.get("available") else "–", "Sentinel-2, post-monsoon"],
    ]
    story.append(_table([[Paragraph(str(c), ss["Cell"]) for c in r] for r in rows], [55 * mm, 45 * mm, 70 * mm]))

    imgs = []
    for fname, caption in (("chm.png", "Canopy height (m)"), ("density.png", "Forest density class")):
        p = job.path(fname)
        if p.exists():
            imgs.append([Image(str(p), width=80 * mm, height=80 * mm, kind="proportional"),
                         Paragraph(caption, ss["Small"])])
    if imgs:
        story.append(Spacer(1, 4 * mm))
        story.append(Table([[i[0] for i in imgs], [i[1] for i in imgs]]))

    story.append(Paragraph("2. Canopy density (Forest Survey of India classes)", ss["H2x"]))
    rows = [["Class", "Canopy cover", "Area (ha)", "Share"]]
    for code, name, lo, hi, _ in FSI_CLASSES:
        rows.append([name, f"{lo:g}–{min(hi, 100):g} %", _fmt(d.get("fsi_area_ha", {}).get(code)),
                     _fmt(d.get("fsi_area_pct", {}).get(code), " %")])
    story.append(_table(rows, [60 * mm, 35 * mm, 35 * mm, 30 * mm]))

    if h.get("histogram"):
        story.append(Spacer(1, 3 * mm))
        story.append(Image(_height_chart(h["histogram"]), width=150 * mm, height=62 * mm, kind="proportional"))

    lc = s.get("landcover") or {}
    terrain = s.get("terrain") or {}
    if lc or terrain.get("available"):
        story.append(Paragraph("3. Land cover and terrain", ss["H2x"]))
        rows = [["Land cover (ESA WorldCover)", "Share"]] + [[k, f"{v} %"] for k, v in list(lc.items())[:6]]
        if terrain.get("available"):
            rows += [["Elevation range", f"{terrain['elevation_min_m']}–{terrain['elevation_max_m']} m"],
                     ["Mean / max slope", f"{terrain['slope_mean_deg']}° / {terrain['slope_max_deg']}°"]]
        story.append(_table(rows, [100 * mm, 60 * mm]))

    site = s.get("site_species")
    if site:
        story.append(Paragraph("Likely tree species at this site (predicted, not counted)", ss["H2x"]))
        c, soil = site["climate"], site["soil"]
        story.append(Paragraph(
            f"<b>{site.get('ecoregion') or '–'}</b> ({site.get('biome') or '–'}). Climate: {c['mean_temp_c']} °C mean, "
            f"{c['min_temp_c']}–{c['max_temp_c']} °C, {c['annual_rain_mm']:,} mm rain per year, "
            f"{c['dry_quarter_rain_mm']} mm in the driest quarter. Topsoil: {soil['sand_pct']} % sand, "
            f"{soil['clay_pct']} % clay, pH {soil['ph']}.", ss["BodyText"]))
        rows = [["Species", "Local name", "Share of similar-site records", "Records"]] + [
            [Paragraph(f"<i>{sp['name']}</i>" + (f" ({sp['english_name']})" if sp.get("english_name") else ""), ss["Cell"]),
             sp.get("local_name") or "–", f"{sp['share_pct']} %", f"{sp['similar_site_records']:,}"]
            for sp in site["species"][:10]
        ]
        story.append(_table(rows, [70 * mm, 38 * mm, 32 * mm, 30 * mm]))
        story.append(Paragraph(f"{site['caveat']} {site['method']}.", ss["Small"]))

    story.append(PageBreak())
    story.append(Paragraph("4. Events during processing", ss["H2x"]))
    evs = [e for e in job.events() if e["level"] in ("warning", "error")]
    if evs:
        rows = [["Level", "Event", "Details / action"]] + [
            [e["level"].upper(), e["code"], Paragraph(f"{e['message']}" + (f"<br/><i>{e['action']}</i>" if e["action"] else ""),
                                                      ss["Cell"])] for e in evs
        ]
        story.append(_table(rows, [20 * mm, 40 * mm, 110 * mm]))
    else:
        story.append(Paragraph("No warnings or errors.", ss["BodyText"]))

    story.append(Paragraph("5. Data sources", ss["H2x"]))
    rows = [["Dataset", "Resolution", "Licence / notes"]] + [
        [Paragraph(p["dataset"], ss["Cell"]), f"{p['resolution_m']} m" if p.get("resolution_m") else "–",
         Paragraph(f"{p['license']}. {p.get('notes', '')} {p.get('period', '')}", ss["Cell"])]
        for p in st.get("provenance", [])
    ]
    story.append(_table(rows, [55 * mm, 22 * mm, 93 * mm]))

    story.append(Paragraph("6. Method and limitations", ss["H2x"]))
    for text in [
        "Tree tops are local maxima of the 1 m canopy height model with a height-dependent search window; crowns are "
        "delineated by marker-controlled watershed and capped at a plausible crown radius for the tree's height.",
        "Canopy density is the share of pixels at or above the canopy height threshold within each grid cell, "
        "classified with Forest Survey of India classes (VDF ≥ 70 %, MDF 40–70 %, OF 10–40 %).",
        "Satellite mode cannot separate touching crowns in closed canopy, so the detected count is a lower bound; "
        "the estimated total is an extrapolation and must not be used as a legal enumeration.",
        "Species are not assigned to individual trees in satellite mode; the site list of likely species is "
        "predicted from climate, soil and worldwide occurrence records and is not a count. Per-tree species, girth "
        "and a full enumeration require a drone survey (orthophoto + surface/terrain model) and field sample plots.",
        "Canopy heights come from a model trained on global satellite imagery (mostly 2018–2020); recent clearing or "
        "growth may not be reflected. Field verification is recommended before regulatory use.",
    ]:
        story.append(Paragraph("• " + text, ss["BodyText"]))

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.grey)
        canvas.drawString(15 * mm, 10 * mm, "Vandrishti AI – decision-support estimate; verify in the field before regulatory use.")
        canvas.drawRightString(195 * mm, 10 * mm, f"Page {doc.page}")
        canvas.restoreState()

    doc = SimpleDocTemplate(str(job.path("assessment_report.pdf")), pagesize=A4,
                            leftMargin=15 * mm, rightMargin=15 * mm, topMargin=15 * mm, bottomMargin=18 * mm,
                            title=f"Tree inventory – {aoi['name']}")
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
