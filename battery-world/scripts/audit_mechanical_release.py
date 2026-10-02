#!/usr/bin/env python3
"""Audit sealed inputs; write a new diagnostic directory without native dispatch."""
import argparse
import json
from bfworld.agentlab.mechanical_review import audit

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--run',required=True);p.add_argument('--cache',required=True);p.add_argument('--output',required=True)
    a=p.parse_args();r=audit(a.run,a.cache,a.output)
    print(json.dumps({'controls':r['controls'],'fractions':r['fractions_of_initial_elastic_energy'],
                      'sampled_equilibrium_counts':r['sampled_equilibrium_counts']},indent=2))
