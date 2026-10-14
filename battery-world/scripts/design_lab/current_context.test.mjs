import assert from 'node:assert/strict';
import test from 'node:test';
import { inspectCurrentContext } from '../../../pi-bf-aiot/packages/bf-agent/src/current-context.ts';

test('each inspection fetches changed current facts through the exact GET route', async () => {
  const calls = [];
  const first = { owner: 'original', eda: { job_id: 'old', status: 'SUCCEEDED' } };
  const second = { owner: 'original', eda: { job_id: 'new', status: 'UNKNOWN' }, full_product_passed: false };
  const responses = [first, second];
  const api = async (...args) => { calls.push(args); return responses.shift(); };
  assert.equal(await inspectCurrentContext({ action: 'context_inspect' }, api), first);
  assert.equal(await inspectCurrentContext({ action: 'context_inspect' }, api), second);
  assert.deepEqual(calls, [['/api/product-context'], ['/api/product-context']]);
  assert.equal(second.eda.status, 'UNKNOWN');
  assert.equal(second.full_product_passed, false);
});

test('unexpected operation, scope and mutation arguments refuse before API entry', async () => {
  let entered = 0;
  const api = async () => { entered++; };
  for (const args of [null, [], {}, { action: 'bind' },
    { action: 'context_inspect', owner: 'foreign' },
    { action: 'context_inspect', job_ids: ['job'] },
    { action: 'context_inspect', payload: { status: 'PASS' } }]) {
    await assert.rejects(inspectCurrentContext(args, api), /PRODUCT_CONTEXT_INSPECT_ARGUMENTS/);
  }
  assert.equal(entered, 0);
});

test('actual server identity or permission refusal is retained without cached fallback', async () => {
  const refusal = new Error('OWNER_OR_PROJECT_BINDING_MISMATCH');
  await assert.rejects(inspectCurrentContext({ action: 'context_inspect' }, async () => { throw refusal; }),
    error => error === refusal);
});
