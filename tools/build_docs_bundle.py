"""Build a shareable zip of the documentation and presentation evidence.

Every Markdown file becomes a styled HTML page (links between documents, images and the architecture
diagrams work offline in any browser), alongside the original Markdown, the presentation evidence pack and the
validation results. Open index.html first.

Usage:
    python tools/build_docs_bundle.py [--out ../Vandrishti-AI_docs.zip]
"""

from __future__ import annotations

import argparse
import re
import shutil
import tempfile
import zipfile
from pathlib import Path

import markdown

ROOT = Path(__file__).resolve().parents[1]
INCLUDE = ["README.md", "docs", "presentation", "results"]

CSS = """
:root { --ink:#1b2a21; --muted:#5d6b62; --line:#dde5de; --brand:#1f5f3a; --soft:#e7f1e9; }
* { box-sizing: border-box; }
body { margin:0; background:#f4f6f3; color:var(--ink);
       font: 15px/1.6 "Segoe UI", Inter, system-ui, -apple-system, sans-serif; }
header { background:var(--brand); color:#fff; padding:12px 24px; display:flex; gap:16px; align-items:center; }
header a { color:#cfe6d5; text-decoration:none; font-size:14px; }
header strong { font-size:17px; }
main { max-width:980px; margin:24px auto; background:#fff; border:1px solid var(--line); border-radius:10px;
       padding:28px 36px; }
h1 { color:var(--brand); font-size:28px; margin-top:0; }
h2 { color:var(--brand); border-bottom:1px solid var(--line); padding-bottom:4px; margin-top:32px; }
h3 { margin-top:24px; }
a { color:#2f7d4c; }
table { border-collapse:collapse; width:100%; margin:12px 0; font-size:14px; display:block; overflow-x:auto; }
th, td { border:1px solid var(--line); padding:6px 10px; text-align:left; vertical-align:top; }
th { background:var(--soft); }
code { background:#f1f4f1; padding:1px 5px; border-radius:4px; font-size:13px; }
pre { background:#f1f4f1; padding:12px 14px; border-radius:8px; overflow-x:auto; font-size:13px; }
pre code { background:none; padding:0; }
blockquote { border-left:4px solid #b46a00; background:#fff4e0; margin:12px 0; padding:8px 14px; }
img { max-width:100%; border:1px solid var(--line); border-radius:8px; }
@media (max-width:700px) { main { margin:0; border-radius:0; padding:18px 16px; } }
"""

PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} · Vandrishti AI</title><style>{css}</style></head>
<body><header><strong>Vandrishti AI</strong><a href="{home}">Documentation home</a></header>
<main>{body}</main>
</body></html>"""


def md_to_html(md_path: Path, bundle_root: Path) -> None:
    text = md_path.read_text(encoding="utf-8")
    body = markdown.markdown(text, extensions=["tables", "fenced_code", "sane_lists"])
    # Link to the HTML version of other Markdown documents.
    body = re.sub(r'href="([^"#:]+?)\.md(#[^"]*)?"', lambda m: f'href="{m.group(1)}.html{m.group(2) or ""}"', body)
    title_match = re.search(r"^#\s+(.+)$", text, flags=re.M)
    title = title_match.group(1).strip() if title_match else md_path.stem
    home = Path("index.html") if md_path.parent == bundle_root else Path(
        *[".."] * len(md_path.parent.relative_to(bundle_root).parts), "index.html")
    md_path.with_suffix(".html").write_text(
        PAGE.format(title=title, css=CSS, body=body, home=home.as_posix()), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=ROOT.parent / "Vandrishti-AI_docs.zip")
    args = ap.parse_args()

    with tempfile.TemporaryDirectory() as tmp:
        bundle = Path(tmp) / "Vandrishti-AI_docs"
        bundle.mkdir()
        for item in INCLUDE:
            src = ROOT / item
            if src.is_dir():
                shutil.copytree(src, bundle / item)
            elif src.exists():
                shutil.copy(src, bundle / item)
        for md in bundle.rglob("*.md"):
            md_to_html(md, bundle)

        index = bundle / "index.html"
        index.write_text(PAGE.format(title="Documentation", css=CSS, home="index.html", body="""
<h1>Vandrishti AI documentation</h1>
<p>AI/ML GIS tree inventory for forest clearance: upload a KML boundary, get a georeferenced tree inventory.</p>
<h2>Read in this order</h2>
<table><tr><th>#</th><th>Document</th><th>What it covers</th></tr>
<tr><td>1</td><td><a href="docs/GUIDE.html"><b>Complete guide (start here)</b></a></td>
<td>The problem, concepts from zero, how a run works, accuracy, limitations</td></tr>
<tr><td>2</td><td><a href="presentation/README.html">Presentation evidence pack</a></td>
<td>Key numbers, screenshots, and the proof for every claim</td></tr>
<tr><td>3</td><td><a href="docs/FAQ.html">FAQ and demo script</a></td><td>Likely questions with answers</td></tr>
<tr><td>4</td><td><a href="docs/SOP.html">Standard operating procedure</a></td><td>How a WCL team runs an assessment</td></tr>
<tr><td>5</td><td><a href="docs/drone_survey_spec.html">Drone survey specification</a></td><td>What to fly and deliver</td></tr>
<tr><td>6</td><td><a href="docs/architecture.html">Architecture, deployment and cost</a></td><td>System design, integration, security</td></tr>
<tr><td>7</td><td><a href="docs/methodology.html">Methodology</a></td><td>Algorithms, validation tables, rare-event rules</td></tr>
<tr><td>8</td><td><a href="README.html">Software README</a></td><td>Installing and running the system</td></tr>
</table>
<h2>Evidence at a glance</h2>
<p><img src="presentation/2_validation/detection_recall.png" alt="Crown detection recall by method"></p>
<p><img src="presentation/2_validation/satellite_vs_lidar.png" alt="Satellite vs LiDAR canopy cover and height"></p>
<p>Sample outputs (PDF reports, KMZ for Google Earth, CSV, Shapefile) are in
<code>presentation/3_sample_outputs/</code>. The Markdown originals sit next to each HTML page.</p>
"""), encoding="utf-8")

        args.out.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(args.out, "w", zipfile.ZIP_DEFLATED) as z:
            for f in sorted(bundle.rglob("*")):
                if f.is_file():
                    z.write(f, f.relative_to(bundle.parent))
    print(f"Wrote {args.out} ({args.out.stat().st_size / 1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
