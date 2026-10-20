import json
import sys

def observe(facts):
    return ((min((facts['initial_energy_uj'] + (facts['source_power_uw'] * facts['source_end_s'])), (0.5 * (facts['capacitance_uf'] * (facts['clamp_v'] ** 2)))) - (0.5 * (facts['capacitance_uf'] * (facts['min_v'] ** 2)))) - facts['service_energy_uj'])

if __name__ == '__main__':
    with open(sys.argv[1]) as stream:
        facts = json.load(stream)
    print(json.dumps({'energy_headroom_uj': observe(facts)}))
