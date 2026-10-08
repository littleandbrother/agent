import assert from 'node:assert/strict';
import test from 'node:test';
import { assertEdaExecution } from '../dist/eda-outcome.js';

test('nonzero native CLI exit is an execution error with its receipt and partial-effects boundary', () => {
  assert.throws(() => assertEdaExecution({ id: 'eda-1', status: 'SUCCEEDED', result: {
    exit_code: 1, stderr: 'unknown flag: --summary', receipt_path: 'eda-receipts/1.json'
  }}), error => {
    const d = JSON.parse(error.message);
    assert.equal(d.error, 'EDA_EXECUTION_FAILED');
    assert.equal(d.receipt_path, 'eda-receipts/1.json');
    assert.equal(d.partial_effects_possible, true);
    return true;
  });
});

test('a valid negative DRC result remains an ordinary fact, not a tool failure', () => {
  const d = { status: 'SUCCEEDED', result: { exit_code: 0,
    stdout: JSON.stringify({ ok: true, result: { passed: false, violations: [1] } }) } };
  assert.equal(assertEdaExecution(d), d);
});

test('native API ok=false and terminal failure remain visible', () => {
  assert.throws(() => assertEdaExecution({ status: 'SUCCEEDED', result: { exit_code: 0,
    stdout: JSON.stringify({ ok: false, error: 'EDA_CALL_FAILED' }) } }), /EDA_CALL_FAILED/);
  assert.throws(() => assertEdaExecution({ status: 'FAILED', error: 'connector timeout' }), /connector timeout/);
});

test('pending jobs and plain text help are not re-dispatched or rejected', () => {
  const pending = { id: 'eda-pending', status: 'RUNNING' };
  assert.equal(assertEdaExecution(pending), pending);
  assert.doesNotThrow(() => assertEdaExecution({ status: 'SUCCEEDED', result: { exit_code: 0, stdout: 'Usage: easyeda sch' } }));
});
