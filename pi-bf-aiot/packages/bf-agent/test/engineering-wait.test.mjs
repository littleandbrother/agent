import test from 'node:test';
import assert from 'node:assert/strict';
import { waitForEngineeringJob } from '../dist/engineering-wait.js';

test('native wait preserves job identity and returns terminal facts', async () => {
  const states = ['QUEUED', 'RUNNING', 'SUCCEEDED'];
  let reads = 0, sleeps = 0, notices = 0;
  const result = await waitForEngineeringJob(
    async () => ({ id: 'eng-existing', status: states[reads++] }),
    { wait: true, sleep: async () => { sleeps++; }, progress: () => { notices++; } },
  );
  assert.deepEqual(result, { id: 'eng-existing', status: 'SUCCEEDED' });
  assert.equal(reads, 3); assert.equal(sleeps, 2); assert.equal(notices, 1);
});

test('nonblocking lookup and native failure do not retry or resubmit', async () => {
  for (const status of ['RUNNING', 'FAILED', 'UNKNOWN']) {
    let reads = 0;
    const job = await waitForEngineeringJob(async () => { reads++; return { status }; }, {
      wait: status !== 'RUNNING', sleep: async () => { throw new Error('unexpected wait'); },
    });
    assert.equal(job.status, status); assert.equal(reads, 1);
  }
});

test('cancellation stops waiting without changing the native job', async () => {
  const controller = new AbortController();
  let reads = 0;
  await assert.rejects(waitForEngineeringJob(async () => { reads++; return { status: 'RUNNING' }; }, {
    wait: true, signal: controller.signal, sleep: async () => controller.abort(),
  }), { name: 'AbortError' });
  assert.equal(reads, 1);
});

test('transport failure remains visible instead of dispatching a replacement', async () => {
  await assert.rejects(waitForEngineeringJob(async () => { throw new Error('read failed'); },
    { wait: true }), /read failed/);
});
