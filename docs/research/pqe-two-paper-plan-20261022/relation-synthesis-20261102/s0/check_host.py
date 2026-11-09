"""One saved-input check of actual serialization/paging; no API or consumer."""
from common import *
from provider import Episode, PublicObjects, p


def run():
    destination = HERE / 'host-check.json'
    if destination.exists():
        raise RuntimeError('CHECK_ALREADY_RECORDED')
    prefix = load(OUT / 'shared/prefixes/identity-progress.json.gz')
    ep = object.__new__(Episode)
    ep.family = prefix['public_contract']['tasks']
    ep.initial = prefix['family_result']
    ep.history = [ep.initial] * 6
    ep.tools = 63
    ep.objects = PublicObjects(HERE / 'host-check-objects')
    object_id = ep.objects.register({'rows': [{'count': i, 'label': 'x' * 100} for i in range(40)]})
    page = ep.objects.read(dict(object_id=object_id, section='/rows', offset=0))
    ep.pages = [deepcopy(page) for _ in range(63)]
    ep.root = HERE / 'host-check-objects'
    serialized = []
    def budget(paid=False):
        return dict(model_requests=len(serialized), output_tokens=123,
                    spent_usd=.001, wall_s=7.)
    def callback(request):
        actual = p.callback_payload(request, request['max_output_tokens'])
        serialized.append(actual)
        if len(serialized) == 1:
            payload = dict(tool_calls=[dict(name='public_object', arguments=dict(
                object_id=object_id, section='/rows', offset=6))])
        else:
            payload = dict(design=prefix['family_result']['design'])
        return dict(usage=dict(status='KNOWN'), payload=payload)
    ep.ready, ep.paid_callback = budget, callback
    nodes = [dict(id='root', design=prefix['family_result']['design'],
                  observed_verdict='FAIL')]
    ep.query(nodes=nodes, evaluated_slots=2)
    assert len(ep.pages) == 64 and ep.tools == 64
    before_second_query = deepcopy(ep.pages)
    ep.query(nodes=nodes, evaluated_slots=3)
    assert ep.pages == before_second_query
    a, b, c = [value['request'] for value in serialized]
    assert a['remaining']['public_reads'] == 1
    assert b['remaining']['public_reads'] == c['remaining']['public_reads'] == 0
    assert [v['remaining']['provider_requests'] for v in (a, b, c)] == [12, 11, 10]
    assert b['remaining']['design_slots'] == 4 and c['remaining']['design_slots'] == 3
    assert b['public_page_history'] == c['public_page_history'] == ep.pages
    assert all(len(p.encoded(v)) < 240000 for v in serialized)
    save(destination, dict(at=now(), status='PASS', provider_requests=0,
        new_scientific_inputs=0, software_checks=1, source=ref(HERE / 'provider.py'),
        cases=['64_pages_retained_verbatim_across_design_queries',
               'remaining_recomputed_per_actual_callback',
               'zero_reads_does_not_block_design_submission',
               'serialized_context_bounded'],
        serialized_sizes=[len(p.encoded(v)) for v in serialized],
        page_count=len(ep.pages), page_bytes_limit=1800, history_sha256=digest(ep.pages)))
    journal(HERE / 'software-checks.jsonl', dict(index=2,
        name='common_host_actual_serialization_and_paging_saved_input', status='PASS', at=now()))
    print(load(destination))


if __name__ == '__main__':
    run()
