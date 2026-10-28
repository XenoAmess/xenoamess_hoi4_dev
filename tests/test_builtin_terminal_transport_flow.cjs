const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const decision = require('../tools/builtin_transport_policy.cjs');
const frozen = JSON.parse(fs.readFileSync(path.join(__dirname, '../docs/handoffs/2026-10-28-low-v33-helper-sources.json'), 'utf8'));
const network = 'image generation failed: connection failed: error sending request';

function harness(outcomes, failImport = false) {
  const history = [];
  let activeKey;
  let calls = 0;
  const tools = {
    async exec_command({ cmd }) {
      history.push(cmd);
      let output = '';
      if (cmd.includes('batch-keys.py')) {
        activeKey = `source-${calls + 1}`;
        output = JSON.stringify([activeKey]);
      } else if (cmd.startsWith('type ')) {
        output = JSON.stringify({source: activeKey, prompt: 'exact test prompt', references: ['original.png', 'reference.png'], transparent: true});
      } else if (cmd.includes('guard-dispatch-family.py')) {
        output = JSON.stringify({eligible: true});
      }
      return {exit_code: failImport && cmd.includes('generation_requests.py fail') ? 1 : 0, output};
    },
    async apply_patch() { history.push('persist-payload-or-result'); },
    async image_gen__imagegen(job) {
      history.push(`invoke-${activeKey}`);
      assert.deepEqual(job, {prompt: 'exact test prompt', referenced_image_paths: ['original.png', 'reference.png'], transparent_background: true});
      const outcome = outcomes[calls++];
      if (outcome !== null) throw new Error(outcome);
      return {output_hint: 'saved as C:\\fake\\raw.png by default.'};
    },
  };
  const producer = new Function('tools', 'notify', 'yield_control', 'store', 'generatedImage', 'terminalTransportDecision',
    'let terminalNetworkFailureStreak=0; return (' + frozen.sources.producer + ');'
  )(tools, () => {}, async () => {}, () => {}, () => {}, decision);
  return {
    history,
    calls: () => calls,
    async run() {
      await producer('fake-jobs.json', `test-${calls + 1}`, '', {
        logicalBoundary: true,
        onEvent: event => history.push(`event-${event.phase}`),
        renderResult: async () => {},
      });
    },
  };
}

test('known terminal connection failure is imported before completed boundary, without PNG finish or replay', async () => {
  const h = harness([network]);
  await h.run();
  assert.equal(h.calls(), 1);
  const returned = h.history.findIndex(x => x.includes('production_queue.py returned'));
  const failed = h.history.findIndex(x => x.includes('generation_requests.py fail'));
  const accounted = h.history.indexOf('event-terminal_connection_error_accounted');
  const completed = h.history.indexOf('event-batch_completed');
  assert.ok(returned >= 0 && returned < failed && failed < accounted && accounted < completed);
  assert.ok(!h.history.some(x => x.includes('generation_requests.py finish')));
});

test('first two distinct terminal transport failures complete, third stops after durable import', async () => {
  const h = harness([network, network, network]);
  await h.run();
  await h.run();
  await assert.rejects(h.run(), /connection failed/);
  assert.equal(h.calls(), 3);
  assert.equal(h.history.filter(x => x === 'event-batch_completed').length, 2);
  assert.equal(h.history.filter(x => x.includes('generation_requests.py fail')).length, 3);
  assert.deepEqual(h.history.filter(x => x.startsWith('invoke-')), ['invoke-source-1', 'invoke-source-2', 'invoke-source-3']);
});

test('successful PNG resets the consecutive transport failure count', async () => {
  const h = harness([network, network, null, network, network]);
  for (let i = 0; i < 5; i++) await h.run();
  assert.equal(h.calls(), 5);
  assert.equal(h.history.filter(x => x === 'event-batch_completed').length, 5);
  assert.equal(h.history.filter(x => x.includes('generation_requests.py finish')).length, 1);
});

test('unknown and authentication failures stop after durable import', async () => {
  for (const failure of ['401 unauthorized', 'ambiguous or unknown outcome']) {
    const h = harness([failure]);
    await assert.rejects(h.run(), new RegExp(failure));
    assert.equal(h.calls(), 1);
    assert.ok(h.history.some(x => x.includes('generation_requests.py fail')));
    assert.ok(!h.history.includes('event-batch_completed'));
  }
});

test('failed error accounting cannot advance the boundary', async () => {
  const h = harness([network], true);
  await assert.rejects(h.run(), /exit_code/);
  assert.equal(h.calls(), 1);
  assert.ok(!h.history.includes('event-terminal_connection_error_accounted'));
  assert.ok(!h.history.includes('event-batch_completed'));
});
