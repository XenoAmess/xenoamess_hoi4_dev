function terminalTransportDecision(error, consecutive) {
  if (!Number.isInteger(consecutive) || consecutive < 0) {
    throw new Error('Expected a nonnegative consecutive transport failure count');
  }
  if (error == null) return { consecutive: 0, continueOtherSources: true };
  const message = String(error).replace(/^Error: /, '');
  const known = [
    'image generation failed: connection failed: error sending request',
    'image generation failed: network error: error sending request',
  ].includes(message);
  if (!known) return { consecutive: 0, continueOtherSources: false };
  const next = consecutive + 1;
  return { consecutive: next, continueOtherSources: next < 3 };
}

if (typeof module !== 'undefined') module.exports = terminalTransportDecision;
