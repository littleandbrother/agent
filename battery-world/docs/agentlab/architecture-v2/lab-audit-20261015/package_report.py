"""Package this read-only UI audit; no runtime or engineering writes."""
from pathlib import Path
import hashlib
import html
import json
import re
import zipfile
from datetime import datetime, timezone
from PIL import Image

ROOT = Path(__file__).resolve().parent
APP = ROOT.parents[3]


def inline(value):
    value = html.escape(value)
    value = re.sub(r"`([^`]+)`", r"<code>\1</code>", value)
    value = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", value)
    value = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', value)
    return value


def render_md(text):
    result, code, table = [], None, False
    for line in text.splitlines():
        if line.startswith("```"):
            if code is None:
                code = []
            else:
                result.append("<pre>" + html.escape("\n".join(code)) + "</pre>")
                code = None
            continue
        if code is not None:
            code.append(line)
            continue
        if line.startswith("|"):
            cells = [v.strip() for v in line.strip().strip("|").split("|")]
            if all(re.fullmatch(r"[:\- ]+", v) for v in cells):
                continue
            if not table:
                result.append('<div class="table-wrap"><table>')
                table = True
                tag = "th"
            else:
                tag = "td"
            result.append("<tr>" + "".join(f"<{tag}>{inline(v)}</{tag}>" for v in cells) + "</tr>")
            continue
        if table:
            result.append("</table></div>")
            table = False
        heading = re.match(r"^(#{1,3}) (.+)$", line)
        if heading:
            level = len(heading[1])
            result.append(f"<h{level}>{inline(heading[2])}</h{level}>")
        elif line:
            result.append("<p>" + inline(line) + "</p>")
    if table:
        result.append("</table></div>")
    return "\n".join(result)


shots = sorted(ROOT.glob("*.jpg"))
assert len(shots) == 16, f"Expected 16 screenshots, got {len(shots)}"
for shot in shots:
    with Image.open(shot) as im:
        assert im.width >= 1000 and im.height >= 700, (shot, im.size)
        im.verify()

body = render_md((ROOT / "LAB-UI-REVIEW.md").read_text())
gallery = "\n".join(
    f'<details><summary>{html.escape(s.stem)}</summary><a href="{s.name}"><img src="{s.name}" alt="{html.escape(s.stem)}" loading="lazy"></a></details>'
    for s in shots
)
style = """
body{margin:0;background:#f4f6f9;color:#253347;font:15px/1.8 -apple-system,BlinkMacSystemFont,'PingFang SC',sans-serif}
main{max-width:1100px;margin:30px auto;background:white;padding:36px 42px;border-radius:14px}
h1{font-size:30px;line-height:1.4}h2{font-size:23px;margin-top:40px;padding-top:12px;border-top:1px solid #e3e8ef}
h3{font-size:18px;margin-top:28px}a{color:#1266ca}code{font-size:.9em;background:#f1f4f8;padding:2px 4px;border-radius:4px;overflow-wrap:anywhere}
pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f3f6fa;padding:18px;border-radius:8px;font:13px/1.7 ui-monospace,monospace}
.table-wrap{overflow:auto}table{border-collapse:collapse;width:100%;font-size:14px}td,th{border:1px solid #e0e6ee;padding:10px 12px;text-align:left;vertical-align:top}th{background:#f2f6fb}
.notice{color:#526782;background:#eef5fd;border-radius:8px;padding:12px 16px}.logic{width:100%;height:auto;border:1px solid #dbe2ea;border-radius:8px}
details{margin:14px 0;border:1px solid #dbe2ea;padding:12px;border-radius:8px}summary{cursor:pointer;font-weight:600}details img{max-width:100%;height:auto;display:block;margin-top:10px}
@media(max-width:760px){main{margin:0;padding:20px 16px;border-radius:0}body{font-size:15px}}
"""
output = f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Lab UI 审查与改版方案</title><style>{style}</style></head><body><main><p class="notice">2026-10-15 · 现场 UI 审查 · 改版方案待确认</p><h2>改版后的内容排布</h2><p>下图说明信息如何组织。当前产品页面保持原样。</p><img class="logic" src="DISPLAY-LOGIC.svg" alt="Lab 改版后的展示逻辑示意">{body}<h2>现场截图原图</h2>{gallery}</main></body></html>"""
(ROOT / "LAB-UI-REVIEW.html").write_text(output)

source_files = [
    "apps/agent-studio/architecture-v2/index.html",
    "apps/agent-studio/architecture-v2/lab.js",
    "apps/agent-studio/architecture-v2/lab.css",
    "packages/python/bfworld/src/bfworld/agentlab/design_lab/repository_view.py",
]
manifest = {
    "audit": "lab-ui-readonly-20261015",
    "created_utc": datetime.now(timezone.utc).isoformat(),
    "head": "4e5eb35332f498f9aabeac7dc1f877bce30803f5",
    "url": "http://127.0.0.1:8768/lab",
    "viewports": [[1280, 720], [1024, 768], [1440, 900]],
    "pages": ["system", "runs", "validation", "environment", "harness", "experiments"],
    "runtime_writes": False,
    "pi_resumed": False,
    "model_or_native_dispatch": False,
    "source_sha256": {p: hashlib.sha256((APP / p).read_bytes()).hexdigest() for p in source_files},
    "artifacts": [],
}
for p in sorted(ROOT.iterdir()):
    if p.suffix in {".jpg", ".svg", ".md", ".html"}:
        item = {"path": p.name, "bytes": p.stat().st_size, "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
        if p.suffix == ".jpg":
            with Image.open(p) as im:
                item["pixels"] = list(im.size)
        manifest["artifacts"].append(item)
(ROOT / "audit-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
archive = Path.home() / "Downloads/BF_Lab_UI_审查与改版方案_20261015.zip"
with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
    for name in [r["path"] for r in manifest["artifacts"]] + ["audit-manifest.json", "package_report.py"]:
        z.write(ROOT / name, "BF_Lab_UI_审查与改版方案/" + name)
with zipfile.ZipFile(archive) as z:
    assert z.testzip() is None
print(json.dumps({"report": str(ROOT / "LAB-UI-REVIEW.html"), "screenshots": len(shots), "zip": str(archive), "zip_bytes": archive.stat().st_size}, ensure_ascii=False))
