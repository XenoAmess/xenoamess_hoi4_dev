"""Keep inherited legacy image evidence separate from modern pre-call proof."""

def classify_returned_attempt(attempt, committed_attempts, indexed_outputs, machine):
    assert attempt.get("fullsize_sha256"), "Only actual returned images have this boundary"
    assert attempt.get("method") == "built-in imagegen", "Unexpected image tool"
    proof = attempt.get("actual_request_verification")
    if proof:
        assert proof.get("actual_recorded_before_call") is True
        assert proof.get("machine_id") == machine
        return "modern_pre_call_proof"
    matches = [a for a in committed_attempts if a.get("number") == attempt["number"]]
    assert len(matches) == 1 and matches[0] == attempt, "Legacy returned attempt changed or was never committed"
    assert attempt["fullsize_sha256"] in indexed_outputs, "Legacy original is not in the immutable parent index"
    return "unchanged_committed_legacy_return"
