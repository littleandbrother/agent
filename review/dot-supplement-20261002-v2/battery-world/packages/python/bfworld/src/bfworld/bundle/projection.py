"""Standalone, dependency-free, read-only RunBundle projection."""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any


def render_replay(
    output: Path,
    rows: list[dict[str, Any]],
    evidence: dict[str, Any],
    views: dict[str, Any],
    scientific_hash: str,
) -> None:
    sampled = [row for index, row in enumerate(rows) if index % 5 == 0]
    payload = {
        "run_id": views["run_id"],
        "event_head": views["event_head"],
        "scientific_hash": scientific_hash,
        "rows": sampled,
        "claims": evidence["claims"],
        "limitations": evidence["limitations"],
    }
    data = json.dumps(payload, ensure_ascii=False, sort_keys=True).replace("</", "<\\/")
    title = html.escape(f"Battery World Replay — {views['run_id']}")
    document = f"""<!doctype html>
<html lang=\"en\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width\">
<title>{title}</title>
<style>
body{{font:14px system-ui;margin:0;background:#0b1020;color:#e8eefc}}main{{max-width:1120px;margin:auto;padding:24px}}
.card{{background:#141c31;border:1px solid #2b3a60;border-radius:12px;padding:16px;margin:12px 0}}
canvas{{width:100%;height:360px;background:#0e1629;border-radius:8px}}code{{word-break:break-all;color:#9bdcff}}
table{{border-collapse:collapse;width:100%}}td,th{{border-bottom:1px solid #2b3a60;padding:8px;text-align:left}}
.pass{{color:#82e6a6}}.fail{{color:#ff8a92}}.muted{{color:#aab6d3}}
</style></head><body><main>
<h1>Battery World — A Replay</h1><p class=\"muted\">Read-only projection; no physics or verdict is computed in this page.</p>
<section class=\"card\"><b>Run</b> <code id=\"run\"></code><br><b>Event head</b> <code id=\"head\"></code><br><b>Scientific hash</b> <code id=\"science\"></code></section>
<section class=\"card\"><h2>Storage voltage</h2><canvas id=\"chart\" width=\"1050\" height=\"360\"></canvas></section>
<section class=\"card\"><h2>Evidence matrix</h2><table><thead><tr><th>Claim</th><th>Verdict</th><th>Scope</th></tr></thead><tbody id=\"claims\"></tbody></table></section>
<section class=\"card\"><h2>Claim boundary</h2><ul id=\"limits\"></ul></section>
</main><script>
const data={data};
run.textContent=data.run_id;head.textContent=data.event_head;science.textContent=data.scientific_hash;
claims.innerHTML=data.claims.map(c=>`<tr><td>${{c.claim_id}}</td><td class=\"${{c.verdict?'pass':'fail'}}\">${{c.verdict?'PASS':'FAIL'}}</td><td>${{c.scope}}</td></tr>`).join('');
limits.innerHTML=data.limitations.map(x=>`<li>${{x}}</li>`).join('');
const canvas=document.getElementById('chart'),ctx=canvas.getContext('2d');
const colors={{baseline:'#ff7b86',revised:'#64d6ff',fine_validation:'#8ce99a'}};
ctx.strokeStyle='#354567';ctx.lineWidth=1;for(let y=40;y<340;y+=60){{ctx.beginPath();ctx.moveTo(48,y);ctx.lineTo(1020,y);ctx.stroke();}}
for(const phase of Object.keys(colors)){{const rows=data.rows.filter(r=>r.phase===phase);ctx.strokeStyle=colors[phase];ctx.lineWidth=2;ctx.beginPath();rows.forEach((r,i)=>{{const x=48+r.time_s/2*972;const y=330-(r.capacitor_voltage_v/5)*290;i?ctx.lineTo(x,y):ctx.moveTo(x,y)}});ctx.stroke();}}
ctx.font='13px system-ui';let x=60;for(const [name,color] of Object.entries(colors)){{ctx.fillStyle=color;ctx.fillRect(x,14,16,4);ctx.fillText(name,x+22,20);x+=190;}}
</script></body></html>"""
    (output / "replay.html").write_text(document, encoding="utf-8")
