# ADR-002: LiveRun, RunBundle, and QualifiedBundle are distinct

Status: accepted

Operational recovery state is not a portable scientific result. A RunBundle is
created only after close and seal. Independent qualification produces a
separate QualifiedBundle so hidden verdict details never enter participant
artifacts.

