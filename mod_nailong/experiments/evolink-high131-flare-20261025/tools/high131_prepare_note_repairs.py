import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.common import ROOT, file_sha256, machine_id, read_json, utc_now, write_json

EXPERIMENT = ROOT / "mod_nailong/experiments/evolink-high131-flare-20261025"
SOURCES = [
    ("d71bdab0746b4d919b4d7a19e9542dacd79929b2b61ace29ee30dc0074f3b657", "review-23-agent.json", ""),
    ("6355b646e7c1efec0bc345942b76423ff8c98f7b9412cb8ec7c9d6e8ee52b094", "review-24-agent.json", ""),
    ("f65b7f58c47c9d9e40333f281fc0e1a7ef9fb5a2414a915c253a0dc949fab165", "review-25-agent.json", ""),
    ("43bc5ceca43f001280b05f196f0fe027938c5f2bd321f6cc3699ddc861dff7a6", "review-26-agent.json", "Also restore the source's close-cropped brown/gray-brown side hair around the high bald crown without adding crown density, and two clearly visible dark eyebrows above the eyes. Never leave a completely smooth bald head or bare brow area. "),
    ("4d60c4894af702661107e61ebcad643e353d28664d32cd33d3dae299983f122d", "review-27-agent.json", ""),
]


def main():
    target = EXPERIMENT / "note-repair-preparation.json"
    existing = read_json(target) if target.exists() else {"entries": []}
    entries = list(existing["entries"])
    known = {(row["source_sha256"], row["attempt"]): row for row in entries}
    for key, report_name, extra_correction in SOURCES:
        report_path = EXPERIMENT / report_name
        report = read_json(report_path)
        decision = report["entries"][0]
        assert decision["source_sha256"] == key and decision["decision"] == "rejected_for_production"
        original_result = read_json(EXPERIMENT / "outputs" / f"{key}-01.result.json")
        assert original_result["sha256"] == decision["output_sha256"]
        old_prompt_path = EXPERIMENT / "outputs" / f"{key}-01.prompt.txt"
        old_prompt = old_prompt_path.read_text(encoding="utf-8")
        reason = " ".join(decision["remaining_reasons"])
        prompt = (
            "ACTUAL OBSERVED CORRECTION: The exact source note has exactly TWO compact upper rows of faint gray marks and no lower-left third mark. "
            "The previous returned note added a separate lower-left gray dash/third row and expanded the upper marks into denser or larger gray blobs. "
            "Remove that invented third mark and restore ONLY the original two source-scale upper rows in their original compact footprint and faint contrast. "
            "Keep the lower paper largely blank. Do not add stains, dots, extra writing or readable text. "
            + extra_correction
            + "Preserve every unrelated source-visible hair, eyebrow, facial-hair, eyewear, clothing, expression, pose, lighting, frame, backing and collar feature exactly as in the following frozen source contract.\n\n"
            + old_prompt
            + "\n\nFINAL PRIORITY: exactly TWO compact upper gray-mark rows and no lower-left third mark, with largely blank lower paper. Keep the complete original tilted frame, opaque photographic backing and genuine transparent exterior outside the complete card/note silhouette. Do not trade this note correction for a new hair, clothing, face, pose or collar defect."
        )
        prompt_path = EXPERIMENT / "prompts" / f"{key}-02.txt"
        prompt_sha = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
        if (key, "external-02") in known:
            assert prompt_path.is_file()
            assert known[(key, "external-02")]["prompt_sha256"] == prompt_sha
            continue
        assert not prompt_path.exists()
        prompt_path.write_bytes(prompt.encode("utf-8"))
        entries.append({
            "source_sha256": key,
            "attempt": "external-02",
            "review": report_path.relative_to(ROOT).as_posix(),
            "review_sha256": file_sha256(report_path),
            "rejected_output_sha256": decision["output_sha256"],
            "previous_prompt": old_prompt_path.relative_to(ROOT).as_posix(),
            "previous_prompt_sha256": file_sha256(old_prompt_path),
            "prompt_file": prompt_path.relative_to(ROOT).as_posix(),
            "prompt_sha256": prompt_sha,
            "output": f"mod_nailong/experiments/evolink-high131-flare-20261025/outputs/{key}-02.png",
            "model": "gpt-image-2.5-flare",
            "background": "transparent",
            "size": "1:1",
            "resolution": "2K",
            "quality": "high",
            "ordered_inputs": ["original source PNG", "user mascot reference"],
            "reason": reason,
        })
        known[(key, "external-02")] = entries[-1]
    write_json(target, {
        "schema": "naiwa-evolink-high131-note-repair-preparation-v1",
        "machine_id": machine_id(),
        "prepared_at_utc": existing.get("prepared_at_utc", utc_now()),
        "updated_at_utc": utc_now(),
        "entries": entries,
        "scope": "New art attempts after actual SHA-bound visual rejections. Previous prompts, outputs, tasks and rejected reviews remain unchanged. No image call has occurred for these new prompts.",
    })
    print(json.dumps({"prepared": len(entries), "prompt_sha256": {row["source_sha256"]: row["prompt_sha256"] for row in entries}}, ensure_ascii=True))


if __name__ == "__main__":
    main()
