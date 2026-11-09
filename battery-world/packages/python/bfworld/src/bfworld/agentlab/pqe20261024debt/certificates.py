"""Scope-bound empty-interval certificates, never simulation-failure proofs.

The fact issuer must independently validate every necessary bound over the
*whole* declared mode/domain.  This module checks its exact rational interval
consequence.  Without that validator it returns UNKNOWN and search continues.
It neither integrates a trajectory nor estimates a loaded-source energy bound.
"""
from copy import deepcopy
from fractions import Fraction
import hashlib
import json

VERSION = "codebt-interval-certificate-v1"


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


def _q(value):
    if isinstance(value, bool) or value is None:
        raise ValueError("EXACT_FINITE_BOUND_REQUIRED")
    return Fraction(str(value))


def _scope(scope):
    required = {"mode", "domain", "conditions", "service_sha256", "source_sha256", "assumptions"}
    if (not isinstance(scope, dict) or not required <= set(scope)
            or not isinstance(scope["mode"], dict) or not isinstance(scope["domain"], dict)
            or not scope["conditions"] or not scope["service_sha256"]
            or not scope["source_sha256"] or not scope["assumptions"]):
        raise ValueError("EXPLICIT_MODE_DOMAIN_CONDITIONS_SERVICE_SOURCE_ASSUMPTIONS_REQUIRED")
    if set(scope["mode"]) & set(scope["domain"]):
        raise ValueError("MODE_AND_FREE_DOMAIN_MUST_BE_DISJOINT")
    for spec in scope["domain"].values():
        if not isinstance(spec, dict):
            raise ValueError("DOMAIN_SPEC_REQUIRED")
        if "min" in spec and "max" in spec:
            if _q(spec["min"]) > _q(spec["max"]):
                raise ValueError("EMPTY_DECLARED_DOMAIN")
        elif not isinstance(spec.get("values"), list) or not spec["values"]:
            raise ValueError("FINITE_OR_INTERVAL_DOMAIN_REQUIRED")
    return deepcopy(scope)


def build_certificate(scope, bound_facts=(), *, verify_fact=None):
    """Return CERTIFIED_EMPTY or UNKNOWN, using only issuer-checked facts.

    Fact shape: id, variable, lower/upper (one or both), lower_strict/
    upper_strict, scope_sha256, necessary=True, evidence_refs and derivation.
    ``verify_fact(fact, scope)`` must return literal True after checking the
    physical/equation assumptions and uniform domain coverage. A flag in the
    supplied fact is deliberately insufficient. Unsupported facts cannot prune.
    """
    scope = _scope(scope)
    bound_facts = list(deepcopy(bound_facts))
    result = {"schema": VERSION, "status": "UNKNOWN", "scope": scope,
              "scope_sha256": digest(scope), "facts": [], "rejected": [],
              "submitted_facts": bound_facts,
              "meaning": "No exclusion without uniformly valid necessary facts and an empty exact outer interval."}
    if verify_fact is None:
        result["reason"] = "NECESSARY_FACT_VALIDATOR_UNAVAILABLE"
        return result
    intervals = {}
    for name, spec in scope["domain"].items():
        if "min" in spec and "max" in spec:
            intervals[name] = [_q(spec["min"]), _q(spec["max"]), False, False]
    for original in bound_facts:
        fact = deepcopy(original)
        reason = None
        try:
            if (not isinstance(fact, dict) or fact.get("necessary") is not True
                    or not fact.get("id") or not fact.get("evidence_refs")
                    or not fact.get("derivation") or fact.get("scope_sha256") != digest(scope)
                    or fact.get("variable") not in intervals
                    or not ({"lower", "upper"} & set(fact))):
                raise ValueError("BOUND_FACT_OR_FULL_SCOPE_BINDING")
            if verify_fact(deepcopy(fact), deepcopy(scope)) is not True:
                raise ValueError("NECESSARY_FACT_NOT_VERIFIED_FOR_DECLARED_DOMAIN")
            interval = list(intervals[fact["variable"]])
            for field, index, strict_index, comparison in (
                    ("lower", 0, 2, lambda a, b: a > b),
                    ("upper", 1, 3, lambda a, b: a < b)):
                if field not in fact:
                    continue
                value = _q(fact[field])
                strict = fact.get(field + "_strict", False)
                if type(strict) is not bool:
                    raise ValueError("BOUND_STRICTNESS_MUST_BE_BOOLEAN")
                if comparison(value, interval[index]):
                    interval[index], interval[strict_index] = value, strict
                elif value == interval[index]:
                    interval[strict_index] = interval[strict_index] or strict
            intervals[fact["variable"]] = interval
            result["facts"].append(fact)
        except Exception as exc:
            reason = str(exc)
        if reason:
            result["rejected"].append({"id": fact.get("id") if isinstance(fact, dict) else None,
                                       "reason": reason})
    result["outer_intervals"] = {name: {"lower": str(v[0]), "upper": str(v[1]),
                                         "lower_strict": v[2], "upper_strict": v[3]}
                                  for name, v in intervals.items()}
    empty = [name for name, (lo, hi, ls, hs) in intervals.items()
             if lo > hi or (lo == hi and (ls or hs))]
    if empty and result["facts"]:
        result.update(status="CERTIFIED_EMPTY", empty_variables=empty,
                      reason="Verified necessary outer intervals have empty intersection inside the declared domain.")
    else:
        result["reason"] = "NECESSARY_OUTER_INTERSECTION_NOT_PROVEN_EMPTY"
    result["certificate_sha256"] = digest(result)
    return result


def verify_certificate(certificate, *, verify_fact=None):
    """Replay a saved certificate; a saved status string grants no authority."""
    try:
        replay = build_certificate(certificate["scope"], certificate.get("submitted_facts", ()),
                                   verify_fact=verify_fact)
    except (KeyError, TypeError, ValueError):
        return False
    return (replay.get("status") == "CERTIFIED_EMPTY"
            and certificate.get("status") == "CERTIFIED_EMPTY"
            and replay.get("outer_intervals") == certificate.get("outer_intervals")
            and replay.get("empty_variables") == certificate.get("empty_variables")
            and replay.get("certificate_sha256") == certificate.get("certificate_sha256"))


def covers_design(certificate, design, *, conditions=None):
    """Membership only; caller must first verify the certificate's authority."""
    if certificate.get("status") != "CERTIFIED_EMPTY":
        return False
    scope = certificate.get("scope", {})
    if conditions is not None and set(conditions) != set(scope.get("conditions", [])):
        return False
    if any(design.get(k) != v for k, v in scope.get("mode", {}).items()):
        return False
    for name, spec in scope.get("domain", {}).items():
        value = design.get(name)
        try:
            if "values" in spec:
                if value not in spec["values"]:
                    return False
            elif not _q(spec["min"]) <= _q(value) <= _q(spec["max"]):
                return False
        except (ValueError, TypeError, ZeroDivisionError):
            return False
    return True
