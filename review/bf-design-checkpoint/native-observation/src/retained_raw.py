"""Strict retained-data reader. Parsing is not proof of native execution.
Supports real, non-FastAccess LTspice point-major binary (float32 or double)
and real ASCII Values. Rejects duplicate/negative time, missing bytes, extra
payload, stepped/complex flags and unrecognized layouts instead of repairing data.
"""
from dataclasses import dataclass
from pathlib import Path
import re
import numpy as np

class EvidenceError(ValueError):
    pass

@dataclass
class Raw:
    time: np.ndarray
    columns: dict
    header: str
    metadata: dict

def read_raw(path):
    path = Path(path)
    if not path.is_file():
        raise EvidenceError("RAW_MISSING")
    if path.stat().st_size > 1073741824:
        raise EvidenceError("RAW_BYTE_BUDGET_EXCEEDED")
    data = path.read_bytes()
    matches = []
    for encoding in ("utf-16-le", "utf-8"):
        for marker in ("Binary:\n", "Binary:\r\n", "Values:\n", "Values:\r\n"):
            b = marker.encode(encoding); i = data.find(b)
            if i >= 0:
                matches.append((i, encoding, marker, i + len(b)))
    if not matches:
        raise EvidenceError("UNRECOGNIZED_RAW_LAYOUT")
    i, encoding, marker, offset = min(matches)
    try:
        header = data[:i].decode(encoding).lstrip("\ufeff").replace("\r\n", "\n")
    except UnicodeError as e:
        raise EvidenceError("INVALID_HEADER_ENCODING") from e
    def field(name):
        matches = re.findall(r"^" + re.escape(name) + r":\s*(.*?)\s*$", header, re.M)
        if len(matches) != 1:
            raise EvidenceError("MISSING_OR_DUPLICATE_HEADER_" + name)
        return matches[0]
    flags = field("Flags").lower().split()
    if "real" not in flags or set(flags) - {"real", "forward", "double"}:
        raise EvidenceError("UNSUPPORTED_RAW_FLAGS:" + " ".join(flags))
    try:
        nv, count = int(field("No. Variables")), int(field("No. Points"))
    except ValueError as e:
        raise EvidenceError("INVALID_RAW_COUNTS") from e
    if nv < 2 or count < 2 or nv > 100000 or count > 100000000:
        raise EvidenceError("UNBOUNDED_RAW_COUNTS")
    sections = header.split("Variables:\n")
    if len(sections) != 2:
        raise EvidenceError("INVALID_VARIABLE_TABLE")
    names, kinds = [], []
    for line in sections[1].splitlines():
        if not line.strip():
            continue
        parts = line.split()
        if len(parts) != 3 or parts[0] != str(len(names)):
            raise EvidenceError("INVALID_VARIABLE_ROW")
        names.append(parts[1].lower()); kinds.append(parts[2].lower())
    if len(names) != nv or names[0] != "time" or kinds[0] != "time" or len(set(names)) != nv:
        raise EvidenceError("INVALID_OR_DUPLICATE_VARIABLES")
    for name, kind in zip(names[1:], kinds[1:]):
        if name.startswith("v(") and kind != "voltage":
            raise EvidenceError("VOLTAGE_CHANNEL_TYPE_MISMATCH:" + name)
        if name.startswith("i(") and kind not in {"device_current", "current"}:
            raise EvidenceError("CURRENT_CHANNEL_TYPE_MISMATCH:" + name)
    if marker.startswith("Values") and len(data)-offset > 67108864:
        raise EvidenceError("ASCII_RAW_MEMORY_BUDGET_EXCEEDED")
    payload = data[offset:]
    if marker.startswith("Binary"):
        dtype = np.dtype([("t", "<f8"), ("v", "<f8" if "double" in flags else "<f4", (nv-1,))])
        if len(payload) != count * dtype.itemsize:
            raise EvidenceError("RAW_PAYLOAD_SIZE_MISMATCH")
        a = np.frombuffer(payload, dtype=dtype, count=count)
        t = a["t"].copy()
        columns = {name: a["v"][:, k].astype(float) for k, name in enumerate(names[1:])}
    else:
        try:
            words = payload.decode(encoding).split()
            if len(words) != count * (nv+1):
                raise EvidenceError("ASCII_RAW_PAYLOAD_SIZE_MISMATCH")
            rows = np.empty((count, nv), float)
            for j in range(count):
                segment = words[j*(nv+1):(j+1)*(nv+1)]
                if segment[0] != str(j):
                    raise EvidenceError("ASCII_POINT_INDEX_MISMATCH")
                rows[j] = [float(v) for v in segment[1:]]
        except (UnicodeError, ValueError) as e:
            if isinstance(e, EvidenceError): raise
            raise EvidenceError("INVALID_ASCII_VALUES") from e
        t = rows[:, 0]; columns = {name: rows[:, k+1] for k, name in enumerate(names[1:])}
    validate_trace(t, columns)
    return Raw(t, columns, header, {"encoding": encoding, "flags": flags, "points": count,
        "variables": nv, "format": "binary" if marker.startswith("Binary") else "ascii",
        "raw_path": str(path), "variable_kinds": dict(zip(names,kinds)), "native_execution_authenticated": False})

def validate_trace(t, columns):
    if len(t) < 2 or not np.isfinite(t).all() or (t < 0).any() or (np.diff(t) <= 0).any():
        raise EvidenceError("NONFINITE_NEGATIVE_DUPLICATE_OR_NONMONOTONIC_TIME")
    if any(len(a) != len(t) or not np.isfinite(a).all() for a in columns.values()):
        raise EvidenceError("INVALID_TRACE_VALUES")

def require_columns(raw, names):
    missing = [n.lower() for n in names if n.lower() not in raw.columns]
    if missing:
        raise EvidenceError("MISSING_SAVED_VARIABLES:" + ",".join(missing))

def require_finished_log(path, measure_names):
    p = Path(path)
    if not p.is_file():
        raise EvidenceError("LOG_MISSING")
    b = p.read_bytes()
    encoding = "utf-16" if b.startswith((b"\xff\xfe", b"\xfe\xff")) else ("utf-16-le" if b[:32].count(b"\x00") > 5 else "utf-8")
    try:
        s = b.decode(encoding)
    except UnicodeError:
        encoding = "cp1252"; s = b.decode(encoding)
    if "Total elapsed time:" not in s:
        raise EvidenceError("NATIVE_LOG_NOT_COMPLETE")
    if re.search(r"\b(fatal|error|unknown parameter|unknown device|singular matrix|timestep too small|convergence failed)\b", s, re.I):
        raise EvidenceError("NATIVE_LOG_ERROR")
    measures = {}
    for name in measure_names:
        rows = re.findall(r"^" + re.escape(name) + r":(.*)$", s, re.I | re.M)
        if len(rows) != 1:
            raise EvidenceError("NATIVE_MEASUREMENT_MISSING_OR_DUPLICATE:" + name)
        m = re.search(r"=\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)(?=\s|$)", rows[0])
        if not m:
            raise EvidenceError("NATIVE_MEASUREMENT_MALFORMED:" + name)
        measures[name] = float(m.group(1))
        if not np.isfinite(measures[name]):
            raise EvidenceError("NONFINITE_MEASUREMENT")
    return {"encoding": encoding, "measures": measures, "warnings": [l for l in s.splitlines() if "warning" in l.lower()]}

