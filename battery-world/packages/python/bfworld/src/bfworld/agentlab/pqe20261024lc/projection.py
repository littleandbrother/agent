"""Bounded, factual public views; complete objects live outside the prompt.

No scientific result, candidate ranking or accounting authority is computed here.
RFC6901 sections identify every original field; pages limit both rows and bytes.
"""
from copy import deepcopy
from pathlib import Path
import hashlib
import json

VERSION = "LC-public-objects-v2"
PAGE_BYTES = 14000
PAGE_ROWS = 24
PROMPT_BYTES = 220000


def encoded(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(encoded(value)).hexdigest()


def component(key):
    return str(key).replace("~", "~0").replace("/", "~1")


class PublicObjects:
    def __init__(self, folder):
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=True)
        self.objects = {}
        self.results = {}

    def register(self, value, *, path=None):
        identifier = "pub-" + digest(value)
        original_path = Path(path) if path is not None else None
        if identifier not in self.objects:
            if path is None:
                target = self.folder / (identifier + ".json")
                if not target.exists():
                    target.write_bytes(encoded(value))
                path = target
            self.objects[identifier] = {"path": str(path), "sha256": digest(value),
                                        "serialized_bytes": len(encoded(value))}
        if (original_path is not None and original_path.name == "public-result.json"
                and isinstance(value, dict) and value.get("result_sha256") and "facts" in value):
            # Legacy known_result uses this index for CURRENT original results.
            # Registering a compact prompt view must never usurp that lookup.
            self.results[value["result_sha256"]] = identifier
        return identifier

    def _get(self, identifier):
        if identifier not in self.objects:
            raise ValueError("UNKNOWN_PUBLIC_OBJECT")
        value = json.loads(Path(self.objects[identifier]["path"]).read_text())
        if digest(value) != self.objects[identifier]["sha256"]:
            raise ValueError("PUBLIC_OBJECT_CONTENT_CHANGED")
        return value

    @staticmethod
    def _section(value, section):
        if section in (None, ""):
            return value
        if not isinstance(section, str) or not section.startswith("/"):
            raise ValueError("RFC6901_SECTION_REQUIRED")
        for item in section[1:].split("/"):
            key = item.replace("~1", "/").replace("~0", "~")
            if isinstance(value, list):
                value = value[int(key)]
            elif isinstance(value, dict):
                value = value[key]
            else:
                raise ValueError("PUBLIC_SECTION_NOT_A_CONTAINER")
        return value

    def reference(self, identifier, section, value):
        return {"public_object_ref": identifier, "section": section,
                "type": type(value).__name__,
                "count": len(value) if isinstance(value, (dict, list, str)) else None,
                "read": {"name": "public_object", "arguments": {
                    "object_id": identifier, "section": section, "offset": 0}}}

    def summary(self, identifier, section="", value=None):
        """Retain scalar facts/unknown/conditions; index all bulky collections.

        Lists have original counts and full read addresses; short scalar lists
        remain verbatim. No top-k selection or scientific answer filtering.
        """
        if value is None:
            value = self._section(self._get(identifier), section)
        if isinstance(value, dict):
            if len(value) > 100:
                return self.reference(identifier, section, value)
            return {key: self.summary(identifier, section + "/" + component(key), item)
                    for key, item in value.items()}
        if isinstance(value, list):
            if len(value) <= 32 and all(not isinstance(x, (list, dict)) for x in value) and len(encoded(value)) <= 2000:
                return deepcopy(value)
            return self.reference(identifier, section, value)
        if isinstance(value, str) and len(encoded(value)) > 3000:
            return self.reference(identifier, section, value)
        return deepcopy(value)

    def read(self, arguments):
        identifier = arguments.get("object_id", arguments.get("public_object_ref"))
        section = arguments.get("section", "")
        offset = arguments.get("offset", 0)
        if type(offset) is not int or offset < 0:
            raise ValueError("NONNEGATIVE_PUBLIC_OFFSET_REQUIRED")
        value = self._section(self._get(identifier), section)
        response = {"version": VERSION, "object_id": identifier, "section": section,
                    "offset": offset, "visibility": "PUBLIC_ONLY", "next_offset": None}
        if isinstance(value, str):
            # Character offsets reconstruct Unicode exactly; bytes remain bounded.
            end = min(len(value), offset + 2000)
            response.update(type="string", total=len(value), text=value[offset:end],
                            next_offset=end if end < len(value) else None)
        elif isinstance(value, (dict, list)):
            keys = list(value) if isinstance(value, dict) else list(range(len(value)))
            response.update(type="dict" if isinstance(value, dict) else "list", total=len(keys), rows=[])
            index = offset
            while index < min(len(keys), offset + PAGE_ROWS):
                key = keys[index]
                item = value[key]
                target = section + "/" + component(key)
                row = {"key" if isinstance(value, dict) else "index": key, "value": deepcopy(item)}
                if len(encoded(row)) > PAGE_BYTES // 2:
                    row["value"] = self.reference(identifier, target, item)
                trial = {**response, "rows": response["rows"] + [row],
                         "next_offset": index + 1 if index + 1 < len(keys) else None}
                if len(encoded(trial)) > PAGE_BYTES:
                    break
                response["rows"].append(row)
                index += 1
            if index == offset and offset < len(keys):
                raise ValueError("PUBLIC_PAGE_CANNOT_MAKE_PROGRESS")
            response["next_offset"] = index if index < len(keys) else None
        else:
            if offset:
                raise ValueError("SCALAR_OFFSET_MUST_BE_ZERO")
            response.update(type="scalar", value=value)
        if len(encoded(response)) > PAGE_BYTES:
            raise ValueError("PUBLIC_PAGE_BYTES_CAP")
        return response

    def project(self, request):
        seen = set()

        def object_view(value):
            identifier = self.register(value)
            canonical = self._get(identifier)
            ref = self.reference(identifier, "", canonical)
            if identifier not in seen:
                seen.add(identifier)
                ref["summary"] = self.summary(identifier, value=canonical)
            return ref

        def walk(value, key=""):
            if isinstance(value, dict):
                if value.get("version") == VERSION and value.get("visibility") == "PUBLIC_ONLY":
                    if len(encoded(value)) > PAGE_BYTES:
                        raise ValueError("PUBLIC_PAGE_BYTES_CAP")
                    return deepcopy(value)
                # Public results/materials/predictions each have one factual view.
                if value.get("view_schema") == "LC-public-result-view-v1" or (
                    "facts" in value and value.get("result_sha256")) or key in {
                    "materials", "prediction", "conditional_prediction", "service_prediction"}:
                    return object_view(value)
                if key == "result" or (key not in {"", "context", "state", "request", "visible_before"}
                                       and len(encoded(value)) > 7000):
                    return object_view(value)
                return {k: walk(v, k) for k, v in value.items()}
            if isinstance(value, list):
                if key in {"trace", "activity", "records", "packets", "receiver_records"}:
                    return object_view(value)
                # Tool/history lists contain projected object references, never
                # copies of all previous full predictions in a prompt registry.
                return [walk(v) for v in value]
            if isinstance(value, str) and len(encoded(value)) > 3000 and key not in {"json_instructions", "public_tool_instruction"}:
                return object_view(value)
            return deepcopy(value)

        projected = walk(request)
        # These IDs have different roles. Keep the legal citation ID and the
        # catalog lookup ID in-line even when history/results are paged.
        incident_map = incident_source_map(request)
        if incident_map:
            projected["incident_source_map"] = incident_map
            projected["source_incidents_legal_field"] = "incident_id"
        projected["public_paging"] = {
            "version": VERSION, "tool": "public_object", "row_cap": PAGE_ROWS,
            "byte_cap": PAGE_BYTES, "section_syntax": "RFC6901 JSON pointer",
            "rule": "Every referenced original public field is readable. Scalar facts, unknowns and validity conditions are factual summaries; no recommended actions. Pages may refer to a large row; read its section."
        }
        if len(encoded(projected)) > PROMPT_BYTES:
            raise ValueError("LOCAL_PUBLIC_PROJECTION_BYTES_CAP_PRE_FORWARD")
        self.save_index()
        return projected

    def save_index(self):
        (self.folder / "index.json").write_text(json.dumps({"version": VERSION,
            "objects": self.objects, "result_objects": self.results}, ensure_ascii=False, indent=2) + "\n")


def incident_source_map(value):
    """Public mapping only; never infer that a source_id is a legal incident_id."""
    found = {}
    def visit(node):
        if isinstance(node, dict):
            incident_id = node.get("incident_id")
            if isinstance(incident_id, str) and incident_id:
                source_id = node.get("source_id")
                if source_id is None and isinstance(node.get("record_ref"), dict):
                    source_id = node["record_ref"].get("source_id")
                found[incident_id] = {"incident_id": incident_id,
                                      "source_id": source_id,
                                      "legal_for_source_incidents": True}
            for child in node.values():
                visit(child)
        elif isinstance(node, list):
            for child in node:
                visit(child)
    visit(value)
    return list(found.values())


def project_public_result(full_public, public_object_ref, *, world_kind):
    """Typed factual view bound to, but distinct from, the original Result."""
    if world_kind not in {"DOOR", "LC_PV"}:
        raise ValueError("PUBLIC_WORLD_KIND_REQUIRED")
    from ..pqe20261023bold.contracts import compact_feedback
    compact = compact_feedback(full_public, public_object_ref)
    facts = compact.get("facts", {})
    counts = facts.get("activity_counts")
    projection = facts.get("projection", {})
    coverage = "COMPLETE" if isinstance(counts, dict) else (
        "SAMPLED" if projection.get("observed_activity_row_counts") else "UNKNOWN")
    view = {"view_schema": "LC-public-result-view-v1", "view_scope": world_kind,
            "result_identity": {"result_sha256": compact["result_sha256"],
                                "task_id": compact.get("task_id")},
            "original_public_object_ref": deepcopy(public_object_ref),
            "activity_coverage": coverage,
            "activity_vocabulary": "original event action labels; no cross-world boot inference",
            "typed_public_result": compact}
    view["view_sha256"] = digest(view)
    return view


def project_history(history, *, world_kind=None):
    """Return exact incident records and an in-line, role-labelled ID map."""
    if not isinstance(history, list):
        raise ValueError("PUBLIC_HISTORY_LIST_REQUIRED")
    return {"history": deepcopy(history), "incident_source_map": incident_source_map(history),
            "source_incidents_legal_field": "incident_id",
            "source_id_role": "public catalog lookup only", "view_scope": world_kind or "MIXED"}


def dispatch_classification(*, trusted_pre_forward, forwarded, request_rows, usage_known):
    """Empty request IDs alone never establish a no-charge local rejection."""
    if trusted_pre_forward and not forwarded and request_rows == 0:
        return "LOCAL_TOOL_NOT_EXECUTED"
    if usage_known:
        return "SETTLED_PROVIDER_REQUEST"
    return "NEW_PROVIDER_USAGE_UNKNOWN_STOP"
