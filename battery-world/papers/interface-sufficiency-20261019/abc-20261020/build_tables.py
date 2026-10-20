#!/usr/bin/env python3
"""Generate descriptive tables from the extracted eighteen-row paper view."""
from pathlib import Path
import csv
import json

ROOT = Path(__file__).resolve().parent
OUT = ROOT/"generated/tables"
ARMS = ("complete_information", "fixed_rule", "observation_refinement")
NAMES = ("Complete information", "Fixed conservative rules", "Observation refinement")


def table(name, caption, label, headers, rows):
    text = "\\begin{table}[tbp]\n\\centering\\small\n\\setlength{\\tabcolsep}{4.5pt}\n"
    text += "\\caption{"+caption+"}\n\\label{"+label+"}\n"
    text += "\\begin{tabular}{l"+"r"*(len(headers)-1)+"}\n\\toprule\n"
    text += " & ".join(headers)+r" \\"+"\n\\midrule\n"
    text += "\n".join(" & ".join(str(v) for v in row)+r" \\" for row in rows)
    text += "\n\\bottomrule\n\\end{tabular}\n\\end{table}\n"
    (OUT/(name+".tex")).write_text(text)


def main():
    stats=json.loads((ROOT/"data/aggregate.json").read_text())["B"]
    rows=list(csv.DictReader((ROOT/"data/formal-episodes.csv").open()))
    table("abc-outcomes", "New formal outcomes, each out of six assigned attempts (three tasks, two fresh contexts each). Actual submission is distinct from normal budget completion. Pred., Dec. and Svc. denote correct intervention prediction, correct adopt/retain decision and selected-service PASS. Typed is only a path statistic.",
          "tab:abc-outcomes", ["Assigned arm","Actual sub.","Pred.","Dec.","Svc.","Budget","Typed"],
          [[name,*[f"{stats[arm][key]}/6" for key in ("actual_artifact_submissions","prediction_correct","decision_correct","service_pass","within_budget_service_pass","real_typed_consumer")]] for arm,name in zip(ARMS,NAMES)])
    table("abc-costs", "New formal resource totals over six attempts per arm. Tokens are total input/output usage; reasoning tokens are not added a second time. USD is the conservative fixed-rate estimate, not an invoice. Acquired bytes are logical source-response bytes, not disk I/O or total context volume.",
          "tab:abc-costs", ["Assigned arm","Requests","Input tokens","Output tokens","Est. USD","Acquired B"],
          [[name,stats[arm]["requests"],f'{stats[arm]["input_tokens"]:,}',f'{stats[arm]["output_tokens"]:,}',f'{stats[arm]["charge_upper_usd"]:.7f}',f'{stats[arm]["acquisition_read_bytes"]:,}'] for arm,name in zip(ARMS,NAMES)])
    short=("Complete", "Fixed", "Refine")
    table("abc-accounting", "Operational and execution accounting. Initial B is summed initial payload bytes; PF/rej. count preflights/rejected actions. Wall includes host evaluation; no separate host-only duration was recorded. Eval/cache/new count evaluated-input references, cache hits and new scientific computations, respectively. Cache order prevents an algorithmic-savings interpretation.",
          "tab:abc-accounting", ["Arm","Initial B","PF","Rej.","Tool s","Wall s","Eval","Cache","New"],
          [[name,f'{sum(int(r["context_payload_bytes"]) for r in rows if r["arm"]==arm):,}',stats[arm]["preflight_calls"],stats[arm]["rejected_actions"],f'{stats[arm]["tool_wall_s"]:.3f}',f'{sum(float(r["wall_s"]) for r in rows if r["arm"]==arm):.1f}',stats[arm]["evaluated_input_count"],stats[arm]["exact_input_cache_reuses"],stats[arm]["scientific_executions"]] for arm,name in zip(ARMS,short)])
    table("abc-attempts", "Every new formal attempt, with no deletion or replacement. C/F/R denote complete information, fixed rules and refinement. S is normal ACTUAL\_SUBMITTED completion; X is original INCOMPLETE\_OR\_STOPPED. Every row has an actual artifact, correct prediction/decision and selected-service PASS; T indicates actual typed use.",
          "tab:abc-attempts", ["Mechanism","Arm","Repeat","Status","T","Requests","PF","Rejects"],
          [[r["task_id"].replace("-", " "),dict(zip(ARMS,("C","F","R")))[r["arm"]],r["episode_id"][-1],"S" if r["status"]=="ACTUAL_SUBMITTED" else "X","1" if r["real_typed_consumer"]=="True" else "0",r["requests"],r["preflight_calls"],r["rejected_actions"]] for r in rows])


if __name__ == "__main__":
    main()
