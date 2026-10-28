const test = require('node:test');
const assert = require('node:assert/strict');
const decide = require('../tools/builtin_transport_policy.cjs');
const connection = 'image generation failed: connection failed: error sending request';
const network = 'image generation failed: network error: error sending request';

test('a known terminal connection result permits another source only within the limit', () => {
  assert.deepEqual(decide(connection, 0), { consecutive: 1, continueOtherSources: true });
  assert.deepEqual(decide('Error: ' + network, 1), { consecutive: 2, continueOtherSources: true });
  assert.deepEqual(decide(connection, 2), { consecutive: 3, continueOtherSources: false });
});
test('a successful result resets an intermittent failure streak', () => {
  const first = decide(connection, 0);
  const success = decide(null, first.consecutive);
  assert.deepEqual(success, { consecutive: 0, continueOtherSources: true });
  assert.equal(decide(network, success.consecutive).consecutive, 1);
});
test('refusals, authentication errors and ambiguous result failures stop', () => {
  for (const message of ['moderation_blocked', 'authentication failed', 'connection timed out',
    'Actual result retained; inspect without another call', 'unexpected error']) {
    assert.equal(decide(message, 0).continueOtherSources, false, message);
  }
});
test('an error merely containing a known error is not accepted', () => {
  assert.equal(decide(connection + '; unknown result', 0).continueOtherSources, false);
});
test('invalid failure counters cannot reopen the budget', () => {
  for (const counter of [-1, 0.5, NaN, undefined]) assert.throws(() => decide(connection, counter));
});
