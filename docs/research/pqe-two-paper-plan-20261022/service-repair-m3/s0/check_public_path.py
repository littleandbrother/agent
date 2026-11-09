"""One offline affected-path check; saved observations, zero predictor/model calls."""
from copy import deepcopy
import ast
import json
from pathlib import Path
import shutil
from public_projection import PublicObjects, encoded, dispatch_classification, PAGE_BYTES

HERE = Path(__file__).resolve().parent
OUT = HERE.parent
BASE = OUT.parent


def run():
    folder = HERE / "offline-scratch"
    if folder.exists():
        raise ValueError("OFFLINE_SCRATCH_ALREADY_EXISTS_REVIEW_FIRST")
    objects = PublicObjects(folder)
    checks, sizes = {}, []
    for source in [HERE / "run_m3.py", HERE / "public_projection.py"]:
        ast.parse(source.read_text())
    checks["new_sources_parse"] = True
    common = json.loads((OUT / "shared/common-start.json").read_text())
    public = json.loads(Path(common["first_public_result"]["path"]).read_text())
    full_id = objects.register(public, path=common["first_public_result"]["path"])
    materials = json.loads((BASE / "dynamic-decision-m2/a/public/source-materials.json").read_text())
    materials_id = objects.register(materials)
    baseline = json.loads((OUT / "a/prediction-baseline.json").read_text())
    state = json.loads((OUT / "shared/common-before-update.json").read_text())
    state["last_result"] = deepcopy(public)
    request = {"site": "H-GEN", "context": {"state": state, "public_tool_results": []}}
    try:
        for index in range(24):
            prediction = deepcopy(baseline)
            prediction["offline_projection_probe"] = index
            request["context"]["public_tool_results"].append({"id": str(index), "name": "predict_candidate", "status": "OK", "result": prediction})
            projected = objects.project(request)
            sizes.append(len(encoded(projected)))
        checks["24_tool_rounds_bounded"] = max(sizes) <= 220000

        max_page = [0]
        def rebuild(identifier, section=""):
            offset, result, kind = 0, None, None
            while True:
                page = objects.read({"object_id": identifier, "section": section, "offset": offset})
                max_page[0] = max(max_page[0], len(encoded(page)))
                assert len(encoded(page)) <= PAGE_BYTES
                kind = page["type"]
                if kind == "scalar":
                    return page["value"]
                if result is None:
                    result = "" if kind == "string" else {} if kind == "dict" else []
                if kind == "string":
                    result += page["text"]
                else:
                    for row in page["rows"]:
                        value = row["value"]
                        if isinstance(value, dict) and "public_object_ref" in value:
                            value = rebuild(value["public_object_ref"], value["section"])
                        if kind == "dict":
                            result[row["key"]] = value
                        else:
                            result.append(value)
                if page["next_offset"] is None:
                    return result
                offset = page["next_offset"]
        checks["full_public_result_lossless_readback"] = rebuild(full_id) == public
        checks["full_materials_lossless_readback"] = rebuild(materials_id) == materials
        page = objects.read({"object_id": full_id, "section": "/facts/records", "offset": 0})
        projected = objects.project({"context": {"public_tool_results": [{"id": "read", "result": page}]}})
        checks["requested_page_visible_verbatim"] = projected["context"]["public_tool_results"][0]["result"] == page
        checks["trusted_local_rejection_not_executed"] = dispatch_classification(trusted_pre_forward=True, forwarded=False, request_rows=0, usage_known=False) == "LOCAL_TOOL_NOT_EXECUTED"
        checks["forwarded_empty_ids_still_stops"] = dispatch_classification(trusted_pre_forward=False, forwarded=True, request_rows=0, usage_known=False) == "NEW_PROVIDER_USAGE_UNKNOWN_STOP"
        checks["empty_ids_alone_never_free"] = dispatch_classification(trusted_pre_forward=False, forwarded=False, request_rows=0, usage_known=False) == "NEW_PROVIDER_USAGE_UNKNOWN_STOP"
        checks["settled_usage_known"] = dispatch_classification(trusted_pre_forward=False, forwarded=True, request_rows=1, usage_known=True) == "SETTLED_PROVIDER_REQUEST"
        status = "PASS" if all(checks.values()) else "FAIL"
        receipt = {"status": status, "checks": checks, "prompt_bytes_by_tool_count": sizes,
                   "maximum_page_bytes": max_page[0], "calls": {"new_full": 0, "new_cheap": 0, "model": 0},
                   "scratch_content_readback_complete": True, "scratch_deleted": True}
        shutil.rmtree(folder)
    except Exception as exc:
        receipt = {"status": "FAIL", "checks": checks, "prompt_bytes_by_tool_count": sizes,
                   "error": type(exc).__name__ + ":" + str(exc), "scratch_retained_for_review": str(folder),
                   "calls": {"new_full": 0, "new_cheap": 0, "model": 0}}
    target = HERE / "offline-path-check.json"
    target.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(receipt, ensure_ascii=False))


if __name__ == "__main__":
    run()
