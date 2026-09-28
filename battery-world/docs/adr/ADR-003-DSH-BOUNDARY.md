# ADR-003: DSH is a replaceable control plane

Status: accepted

DSH will call a versioned Battery World API. It will not import World provider
internals, own scientific persistence, or mount private qualification tools.
DSH session events and World events are correlated by identifiers but remain
separate logs.

