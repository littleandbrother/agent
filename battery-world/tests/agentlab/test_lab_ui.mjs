import { readFile } from 'node:fs/promises';
import assert from 'node:assert/strict';
import test from 'node:test';

const source = await readFile(new URL('../../apps/agent-studio/architecture-v2/lab.js', import.meta.url), 'utf8');
const ui = await import('data:text/javascript;base64,' + Buffer.from(source).toString('base64'));

test('core summary counts eight current gates without counting historical receipts', () => {
  const system = { id: 'current', validations: {
    firmware_event_logic: { status: 'PASS', validation_id: 'new-firmware' },
    delivery_version: { status: 'PASS' },
    pcb_connectivity_drc: { status: 'FAIL' },
    power_load_chain: { status: 'FAIL' },
    source_domain: { status: 'UNEVALUABLE' },
    schematic_bom_pins: { status: 'UNEVALUABLE' },
    geometry_fit: { status: 'UNEVALUABLE' },
    board_firmware_interfaces: { status: 'UNEVALUABLE' },
    historical_receipt: { status: 'PASS' }
  }};
  const rows = ui.coreRecords(system);
  assert.equal(rows.length, 8);
  assert.equal(rows.filter(r => r.status === 'PASS').length, 2);
  assert.equal(rows.filter(r => r.status === 'FAIL').length, 2);
  assert.equal(rows.filter(r => r.status === 'UNEVALUABLE').length, 4);
  assert(rows.every(r => r.target === 'current'));
});

test('missing current gate remains unchecked', () => {
  const rows = ui.coreRecords({ id: 'fresh' });
  assert.equal(rows.length, 8);
  assert(rows.every(r => r.status === 'NOT_CHECKED'));
});

test('contract card and detail use the same latest candidate-bound result', () => {
  const view = { validations: [
    { id: 'old', target: 'current', kind: 'power-firmware-interface', status: 'FAIL' },
    { id: 'other', target: 'another', kind: 'power-firmware-interface', status: 'FAIL' },
    { id: 'new', target: 'current', kind: 'power-firmware-interface', status: 'PASS' },
    { id: 'review', target: 'current', kind: 'independent-review', status: 'FAIL' }
  ]};
  const system = { id: 'current', contracts: { 'power-firmware': 'IC-current' }};
  assert.equal(ui.latestInterface(view, system).id, 'new');
  assert.equal(ui.contractVerdict(view, system, { id: 'IC-current' }), 'PASS');
  assert.equal(ui.contractVerdict(view, system, { id: 'IC-other' }), 'NOT_CHECKED');
});

test('a successful validation invocation still shows an engineering failure', () => {
  assert.deepEqual(ui.operationOutcome({ status: 'SUCCEEDED', result: { result: { status: 'FAIL' }}}),
    { execution: 'SUCCEEDED', engineering: 'FAIL' });
  assert.deepEqual(ui.operationOutcome({ status: 'SUCCEEDED', result: { status: 'QUEUED' }}),
    { execution: 'SUCCEEDED', engineering: 'QUEUED' });
  assert.deepEqual(ui.operationOutcome({ status: 'FAILED', error: 'timeout' }),
    { execution: 'FAILED', engineering: null });
});

test('full tree comparison keeps earlier source edits across declaration-only commits', () => {
  const parent = { files: { 'main.c': { sha256: 'old' }, 'unchanged.h': { sha256: 'same' }, 'obsolete': { sha256: 'remove' }}};
  const current = { files: { 'main.c': { sha256: 'new' }, 'unchanged.h': { sha256: 'same' }, 'interfaces/fw.json': { sha256: 'declare' }}};
  assert.deepEqual(ui.changedFiles(current, parent).map(r => r.path), ['main.c', 'obsolete', 'interfaces/fw.json']);
  assert.deepEqual(ui.changedFiles(current, null), []);
});

test('round and owner filters use the same requests for totals and detail rows', () => {
  const requests = [
    { owner: 'lead', created: 10, status: 'SETTLED', charged: 1 },
    { owner: 'power', created: 20, status: 'SETTLED', charged: 2 },
    { owner: 'lead', created: 30, status: 'UNKNOWN', reserved: 3 },
    { owner: 'power', created: 40, status: 'SETTLED', charged: 4 }
  ];
  const round = ui.scopeRequests(requests, { start: 20, end: 40 });
  assert.equal(round.length, 2);
  assert.equal(ui.usageTotals(round).requests, 2);
  assert.equal(ui.usageTotals(round).ledger, 5);
  const owner = ui.scopeRequests(requests, { owner: 'lead' });
  assert.equal(owner.length, 2);
  assert.equal(ui.usageTotals(owner).ledger, 4);
});

test('UNKNOWN keeps its full reservation; cache estimate is separately totalled', () => {
  const totals = ui.usageTotals([
    { status: 'SETTLED', charged: 2, reserved: 8, usage: { total_tokens: 10 }, cost_estimate: { cache_aware_estimate_usd: 1 } },
    { status: 'UNKNOWN', charged: 0, reserved: 5 }
  ]);
  assert.equal(totals.ledger, 7);
  assert.equal(totals.estimate, 1);
  assert.equal(totals.estimated, 1);
  assert.equal(totals.unknown, 1);
  assert.equal(totals.tokens, 10);
});

test('candidate title and creation time refer to integration, not a later close operation', () => {
  const integration = { created: 10, request: { action: 'repository_integrate', rationale: 'change load' }, result: { id: 'IR', system_commit: 'SC' }};
  const view = { operations: [
    { created: 20, request: { action: 'repository_close' }, result: { system_commit: 'SC' } }, integration
  ]};
  assert.equal(ui.sourceOperation(view, 'SC'), integration);
});

test('BF decision is read from its target and nested public record', () => {
  const view = { decisions: [
    { id: 'DA1', to_design: 'SC', rationale: JSON.stringify({ decision: 'REVISE', rationale: 'first' }) },
    { id: 'DA2', to_design: 'SC', rationale: JSON.stringify({ decision: 'RETAIN_FOR_REVIEW', rationale: 'new result' }) },
    { id: 'DA3', to_design: 'other', rationale: 'other design' }
  ]};
  const decision = ui.designDecision(view, 'SC');
  assert.equal(decision.id, 'DA2');
  assert.equal(decision.decision, 'RETAIN_FOR_REVIEW');
  assert.equal(decision.rationale, 'new result');
  assert.equal(ui.designDecision(view, 'absent'), null);
});

test('round uses the parent task base and ends when work from this candidate begins', () => {
  const view = { systems: [{ id: 'SC0' }, { id: 'SC1', parent: 'SC0' }, { id: 'SC2', parent: 'SC1' }], operations: [],
    professional_task_history: [{ base_system: 'SC0', created: 100 }],
    professional_tasks: [{ base_system: 'SC1', created: 200 }, { base_system: 'SC1', created: 205 }] };
  assert.deepEqual(ui.roundScope(view, view.systems[1]), { start: 100, end: 200 });
  assert.deepEqual(ui.roundScope(view, view.systems[2]), { start: 200, end: null });
});

test('search uses public object labels rather than arbitrary raw payloads', () => {
  const text = ui.publicSearchText({ title: '供能检查', path: 'project-chain/load.json', internal: { hidden: 'do not index' }});
  assert(text.includes('供能检查'));
  assert(!text.includes('do not index'));
});

test('historical execution files open through a system with the exact artifact hash', () => {
  const old = { id: 'old', jobs: { job1: { artifacts: { 'result.json': { sha256: 'old-hash' }}}}};
  const current = { id: 'current', jobs: { job1: { artifacts: { 'result.json': { sha256: 'new-hash' }}}}};
  const view = { systems: [old, current] };
  assert.equal(ui.jobArtifactSystem(view, current, 'job1', 'result.json', 'old-hash').id, 'old');
  assert.equal(ui.jobArtifactSystem(view, current, 'job1', 'result.json', 'new-hash').id, 'current');
  assert.equal(ui.jobArtifactSystem(view, current, 'job2', 'result.json', 'old-hash'), undefined);
});
