import hashlib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.common import ROOT, file_sha256, machine_id, read_json, utc_now, write_json

EXPERIMENT = ROOT / "mod_nailong/experiments/evolink-high131-flare-20261025"
NOTE_GROUP_CLARIFICATION = (
    "\n\nDIRECT SOURCE OBSERVATION FOR THIS UNDISPATCHED DRAFT: The exact source note has TWO separated irregular gray-mark groups in its upper row and TWO separated irregular gray-mark groups in its lower row. Restore exactly TWO source-scale groups in EACH row with their original irregular relative lengths and compact footprint. Do not substitute repeated dots, uniform short dashes, long bars, extra groups or readable writing. Keep the lower paper blank outside the original marks and retain the small right-edge tab."
)
NOTE_GROUP_CLARIFICATIONS = {
    (key, attempt): NOTE_GROUP_CLARIFICATION
    for key, attempt in (
        ("bcaa3e223619109671f12979fec27463cdeaee669f9f86fdf665ca50fb3a5bf5", "external-04"),
        ("5a160dd1e47d2a76dbf153ecf70fed66d73f3dfe21958a284cec3f4971fbfc74", "external-04"),
        ("55e631c3aaedeef562ccccf0e31ebd55de03e25b719c3ac197e677f30ecb3675", "external-04"),
        ("bccaf19c78294b83dc4ab613b8e019a23e77702e342deb376e787b16b0c12336", "external-04"),
        ("f54980009f57be78a2a931afeb1aad7251b370a8c6ca677164a7198c584cbf7d", "external-04"),
        ("889edc5a10979a25b5507640325ac122112474d07a0ca1efe99d067d5d4a5f28", "external-03"),
        ("322c66462794b3abc2eadf075a7cfed79a583a9b5c3457d17e70359edafeb469", "external-03"),
        ("8f53dc26bec02a7f1a6a617afb171d49e221fad8227b265d94e7384ce17f4bd0", "external-05"),
    )
}


def revise_undispatched_prompt(prompt_path, row, prompt, prompt_sha):
    key = row["source_sha256"]
    stem = f"{key}-{row['attempt'].removeprefix('external-')}"
    old_sha = row["prompt_sha256"]
    if old_sha == prompt_sha:
        return
    old_bytes = prompt_path.read_bytes()
    assert file_sha256(prompt_path) == old_sha
    for directory in ("outputs", "executions", "logs"):
        artifacts = list((EXPERIMENT / directory).glob(stem + "*"))
        if artifacts:
            raise RuntimeError(f"Refusing to revise an attempted or otherwise recorded prompt: {artifacts}")
    preserved = EXPERIMENT / "superseded-prompts" / f"{stem}-{old_sha}.txt"
    receipt_path = EXPERIMENT / "undispatched-prompt-revisions" / f"{stem}-{old_sha}.json"
    assert not preserved.exists() and not receipt_path.exists()
    preserved.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    preserved.write_bytes(old_bytes)
    assert file_sha256(preserved) == old_sha
    receipt = {
        "schema": "naiwa-evolink-high131-undispatched-prompt-revision-v1",
        "machine_id": machine_id(),
        "recorded_at_utc": utc_now(),
        "source_sha256": key,
        "attempt": row["attempt"],
        "reason": "Actual source viewing establishes exactly two separated irregular gray-mark groups in each of the two note rows.",
        "prior_prompt": prompt_path.relative_to(ROOT).as_posix(),
        "prior_prompt_sha256": old_sha,
        "prior_full_prompt": old_bytes.decode("utf-8"),
        "prior_preparation": dict(row),
        "preserved_prompt": preserved.relative_to(ROOT).as_posix(),
        "preserved_prompt_sha256": file_sha256(preserved),
        "replacement_prompt_sha256": prompt_sha,
        "actual_artifacts_absent_before_revision": True,
        "new_image_generation_calls": 0,
    }
    write_json(receipt_path, receipt)
    prompt_path.write_bytes(prompt.encode("utf-8"))
    assert file_sha256(prompt_path) == prompt_sha
    row["prompt_sha256"] = prompt_sha
    row["undispatched_revision_receipt"] = receipt_path.relative_to(ROOT).as_posix()


SOURCES = [
    ("d71bdab0746b4d919b4d7a19e9542dacd79929b2b61ace29ee30dc0074f3b657", "review-23-repair-agent.json"),
    ("6355b646e7c1efec0bc345942b76423ff8c98f7b9412cb8ec7c9d6e8ee52b094", "review-24-repair-agent.json"),
    ("f65b7f58c47c9d9e40333f281fc0e1a7ef9fb5a2414a915c253a0dc949fab165", "review-25-repair-agent.json"),
    ("43bc5ceca43f001280b05f196f0fe027938c5f2bd321f6cc3699ddc861dff7a6", "review-26-repair-agent.json"),
    ("4d60c4894af702661107e61ebcad643e353d28664d32cd33d3dae299983f122d", "review-27-repair-agent.json"),
    ("f4ba5196d4820da6097506c2fe74199ee160d69959cb54a41e4df24c6c1d2a53", "review-35-agent.json"),
    ("75d2deb866615aa1a226c1c611b56c7161e1b5035167c4dee9178b34410debb5", "review-36-agent.json"),
    ("18a4420622a213050b393649b40bebcfb6699dff52ab277ebd8376792ab56716", "review-37-agent.json"),
    ("75d2deb866615aa1a226c1c611b56c7161e1b5035167c4dee9178b34410debb5", "review-36-repair-agent.json"),
    ("85177bcdadce2164206d33cd29d60d7aa7689f247b69d32f0523c8044fc22d01", "review-38-agent.json"),
    ("2a6394fc8d1b68a7150b114a47923cac16e60e4931cd49ba82ac2f4982355b79", "review-40-agent.json"),
    ("8d7f23b2344474cbaff4987106b956986154abae2793052bf47498e513cd3135", "review-42-agent.json"),
    ("d845e916fa2c812f0aa11ca1e907ce9c4dbd26b5dfc00c6c1faf3badf4b35dd4", "review-44-agent.json"),
    ("b77b3f3f9edc43648e721aa822a613b72dba11b9ea6a55fef479e565f769adf9", "review-45-agent.json"),
    ("698fc8825afff83e11f88b16ca8801f2083faab08b2f2b487f06a33f7e8757f6", "review-46-agent.json"),
    ("845889cbc06604dcc16b5df54917dc4b4c217542bbaf4f5cc7d73afd4755b84e", "review-47-agent.json"),
    ("0c50b52126e86af765d8829cbda7ccd28b8f68c68ff533d1619aed4f15f22f5b", "review-48-agent.json"),
    ("75a27d6f75b2c13b41236a67e617181ab1bed11c6940af3e6b73798eb5ed1353", "review-49-agent.json"),
    ("6355b646e7c1efec0bc345942b76423ff8c98f7b9412cb8ec7c9d6e8ee52b094", "review-24-third-agent.json"),
    ("f65b7f58c47c9d9e40333f281fc0e1a7ef9fb5a2414a915c253a0dc949fab165", "review-25-third-agent.json"),
    ("eb54e379f1d4875e9aab7088c847de5adf113fa97fe5ef4df6fe302a292fbf48", "review-50-agent.json"),
    ("cf0abd76a2108fe11586d962113ceb417a51b7ab0464bfdc72c20aee65aee287", "review-51-agent.json"),
    ("581dd8fc38811eeca36e65fcfb5093d743744adbcb44be6f160e63af7e450b90", "review-52-agent.json"),
    ("54b4ec4ae9b53cd9fdb29065ddafcd8fea67e1d360023c1d6ae55dc6e2e4162b", "review-53-agent.json"),
    ("85177bcdadce2164206d33cd29d60d7aa7689f247b69d32f0523c8044fc22d01", "review-38-repair-agent.json"),
    ("2a6394fc8d1b68a7150b114a47923cac16e60e4931cd49ba82ac2f4982355b79", "review-40-repair-agent.json"),
    ("d845e916fa2c812f0aa11ca1e907ce9c4dbd26b5dfc00c6c1faf3badf4b35dd4", "review-44-repair-agent.json"),
    ("698fc8825afff83e11f88b16ca8801f2083faab08b2f2b487f06a33f7e8757f6", "review-46-repair-agent.json"),
    ("eb54e379f1d4875e9aab7088c847de5adf113fa97fe5ef4df6fe302a292fbf48", "review-50-repair-agent.json"),
    ("581dd8fc38811eeca36e65fcfb5093d743744adbcb44be6f160e63af7e450b90", "review-52-repair-agent.json"),
    ("85177bcdadce2164206d33cd29d60d7aa7689f247b69d32f0523c8044fc22d01", "review-38-third-agent.json"),
    ("5770c09b8367c798fe5be23ae82ac30a4f162f41fa0e58da70b29bb757e3e59f", "review-54-agent.json"),
    ("2a6394fc8d1b68a7150b114a47923cac16e60e4931cd49ba82ac2f4982355b79", "review-40-third-agent.json"),
    ("698fc8825afff83e11f88b16ca8801f2083faab08b2f2b487f06a33f7e8757f6", "review-46-third-agent.json"),
    ("54b4ec4ae9b53cd9fdb29065ddafcd8fea67e1d360023c1d6ae55dc6e2e4162b", "review-53-repair-agent.json"),
    ("9e6a006d88aaebe1849c546d093a3a70326fd4ac3b3275a7fe7a8e4dd0a80945", "review-55-agent.json"),
    ("a81ad355f0771758fa159c29138a4a65840813ae56fba34eec6ec267672a0037", "review-56-agent.json"),
    ("8f53dc26bec02a7f1a6a617afb171d49e221fad8227b265d94e7384ce17f4bd0", "review-57-agent.json"),
    ("a2cc6a2af5a297af965c9d56015509a0c99645731aea11b8a5fd7a921d76e8ab", "review-58-agent.json"),
    ("581dd8fc38811eeca36e65fcfb5093d743744adbcb44be6f160e63af7e450b90", "review-52-third-agent.json"),
    ("8f38d5eed0d346e8a3390b4e9adf8b852d47e6d421578f5feb38d49dd673f552", "review-59-agent.json"),
    ("bcaa3e223619109671f12979fec27463cdeaee669f9f86fdf665ca50fb3a5bf5", "review-60-agent.json"),
    ("5a160dd1e47d2a76dbf153ecf70fed66d73f3dfe21958a284cec3f4971fbfc74", "review-61-agent.json"),
    ("55e631c3aaedeef562ccccf0e31ebd55de03e25b719c3ac197e677f30ecb3675", "review-62-agent.json"),
    ("bccaf19c78294b83dc4ab613b8e019a23e77702e342deb376e787b16b0c12336", "review-63-agent.json"),
    ("f54980009f57be78a2a931afeb1aad7251b370a8c6ca677164a7198c584cbf7d", "review-64-agent.json"),
    ("b23f38a53df05e6f07fb386f01bc746c349f1653f4afce69209efec7e15acb67", "review-70-agent.json"),
    ("5a6d534f04d1d8488908b3d86c6c6bcc9614e303d5130828b8555aac0d90a142", "review-71-agent.json"),
    ("889edc5a10979a25b5507640325ac122112474d07a0ca1efe99d067d5d4a5f28", "review-65-agent.json"),
    ("322c66462794b3abc2eadf075a7cfed79a583a9b5c3457d17e70359edafeb469", "review-67-agent.json"),
    ("cd4eecb5863a93790cdb8fc7da3d5c6989da9acedddd7037d2f427a76dd440fc", "review-73-agent.json"),
    ("c10336fda4d300f97dc2934072947fc1b5f4697d54ba0c9e2d7f3f60aa009bbb", "review-76-agent.json"),
    ("2a6394fc8d1b68a7150b114a47923cac16e60e4931cd49ba82ac2f4982355b79", "review-recovery-40-agent.json"),
    ("581dd8fc38811eeca36e65fcfb5093d743744adbcb44be6f160e63af7e450b90", "review-recovery-52-agent.json"),
    ("54b4ec4ae9b53cd9fdb29065ddafcd8fea67e1d360023c1d6ae55dc6e2e4162b", "review-recovery-53-agent.json"),
    ("5770c09b8367c798fe5be23ae82ac30a4f162f41fa0e58da70b29bb757e3e59f", "review-recovery-54-agent.json"),
    ("8f53dc26bec02a7f1a6a617afb171d49e221fad8227b265d94e7384ce17f4bd0", "review-recovery-57-agent.json"),
    ("bcaa3e223619109671f12979fec27463cdeaee669f9f86fdf665ca50fb3a5bf5", "review-recovery-60-agent.json"),
    ("5a160dd1e47d2a76dbf153ecf70fed66d73f3dfe21958a284cec3f4971fbfc74", "review-recovery-61-agent.json"),
    ("55e631c3aaedeef562ccccf0e31ebd55de03e25b719c3ac197e677f30ecb3675", "review-recovery-62-agent.json"),
    ("bccaf19c78294b83dc4ab613b8e019a23e77702e342deb376e787b16b0c12336", "review-recovery-63-agent.json"),
    ("f54980009f57be78a2a931afeb1aad7251b370a8c6ca677164a7198c584cbf7d", "review-recovery-64-agent.json"),
    ("d7725f680e18c079a84378f5371754e0e4585167f902a022ff67167d4f39cfdf", "review-recovery-77-agent.json"),
    ("ad5ffa52d5fb95b0eef577f04a20d20727f83f962ec6f7d00180030b92b6abac", "review-recovery-79-agent.json"),
    ("4fa501cb8f3c7b28737b2c916381c48e6f9a87201aea23d41e799956ecc1ba95", "review-recovery-84-agent.json"),
    ("740efb5d01b4d2aa9f298b7fe96a08911244967007befce43be7137e37fafe8e", "review-recovery-86-agent.json"),
    ("cf7a9fd32cfd5d4765b8290883e08f7c1edd190fbf63a02398f954985e329666", "review-recovery-87-agent.json"),
    ("85e7118cda394b05b1c7353ed054bfc79cdd96aef549837f2a44e2af8440b91f", "review-recovery-90-agent.json"),
    ("d0acdab0a6f97cbe90d3d1a37952c5a6ed8f5d380bd5fbd13d06de5323a44793", "review-recovery-94-agent.json"),
    ("40e67743a097a1b24850283690f7a810de74ef78005fee60480434f28d881ccb", "review-recovery-96-agent.json"),
    ("cf4d28bdfe17a2b07ac55be334f08e1e354bf25e607e0b4d314c7bcfd32b6abc", "review-recovery-98-agent.json"),
    ("e75979068852197b71a1042f9497d5dba6eccd7a66ed2db7fd481f788058e106", "review-recovery-99-agent.json"),
    ("b3ba713347dc9620fee391ab93275dc036d6d6067ee25b73564497926f8fbac8", "review-recovery-101-agent.json"),
    ("729c7a0fe213577f6ba80dcee2e437c45699944235b54f4930443dd7dc9abf29", "review-recovery-102-agent.json"),
    ("3ace702fb60162e5d1635ad3b920e95865c84229ea6277e29057aa6b1238eb56", "review-recovery-103-agent.json"),
    ("a0b92bb14298586d7c54cc420b9a3ba3ea899ea72e5c72abf7841352049382d7", "review-recovery-108-agent.json"),
    ("237cd6bf2e2ee2200f1b175d0634eeb065eb5bdb1d82f2dbf924267681cc2778", "review-recovery-105-agent.json"),
    ("87e69987a114bcf3a64e6cfa88e02b84c11efecb228bf3354f87d2553ea6151c", "review-recovery-106-agent.json"),
    ("7b1631616a39370f7aa8e5af556314cb7ada26bd226707546a9bc1d76ed42450", "review-recovery-112-agent.json"),
    ("7c1ce977d30ec0c6aba6f882534b18d6ed91f836c13fb0b2eac6e741b30ecf0f", "review-recovery-113-agent.json"),
    ("2a6394fc8d1b68a7150b114a47923cac16e60e4931cd49ba82ac2f4982355b79", "review-recovery-40-repair-05-agent.json"),
    ("581dd8fc38811eeca36e65fcfb5093d743744adbcb44be6f160e63af7e450b90", "review-recovery-52-repair-05-agent.json"),
    ("54b4ec4ae9b53cd9fdb29065ddafcd8fea67e1d360023c1d6ae55dc6e2e4162b", "review-recovery-53-repair-04-agent.json"),
    ("5770c09b8367c798fe5be23ae82ac30a4f162f41fa0e58da70b29bb757e3e59f", "review-recovery-54-repair-03-agent.json"),
    ("8f53dc26bec02a7f1a6a617afb171d49e221fad8227b265d94e7384ce17f4bd0", "review-recovery-57-repair-03-agent.json"),
    ("bcaa3e223619109671f12979fec27463cdeaee669f9f86fdf665ca50fb3a5bf5", "review-recovery-60-repair-03-agent.json"),
    ("5a160dd1e47d2a76dbf153ecf70fed66d73f3dfe21958a284cec3f4971fbfc74", "review-recovery-61-repair-03-agent.json"),
    ("55e631c3aaedeef562ccccf0e31ebd55de03e25b719c3ac197e677f30ecb3675", "review-recovery-62-repair-03-agent.json"),
    ("bccaf19c78294b83dc4ab613b8e019a23e77702e342deb376e787b16b0c12336", "review-recovery-63-repair-03-agent.json"),
    ("f54980009f57be78a2a931afeb1aad7251b370a8c6ca677164a7198c584cbf7d", "review-recovery-64-repair-03-agent.json"),
    ("889edc5a10979a25b5507640325ac122112474d07a0ca1efe99d067d5d4a5f28", "review-recovery-65-repair-02-agent.json"),
    ("322c66462794b3abc2eadf075a7cfed79a583a9b5c3457d17e70359edafeb469", "review-recovery-67-repair-02-agent.json"),
    ("0a76535500bad74580ae0661421c514fa157a9af0476a730cc2892cd4678d5fd", "review-recovery-121-agent.json"),
    ("e2dddf0ec8c8581f804729f41ab267f84387cc970ed96ea2b5785ecbb5508ebd", "review-recovery-122-agent.json"),
    ("b3ba713347dc9620fee391ab93275dc036d6d6067ee25b73564497926f8fbac8", "review-recovery-101-repair-02-agent.json"),
    ("87e69987a114bcf3a64e6cfa88e02b84c11efecb228bf3354f87d2553ea6151c", "review-recovery-106-repair-02-agent.json"),
    ("2a6394fc8d1b68a7150b114a47923cac16e60e4931cd49ba82ac2f4982355b79", "review-recovery-40-repair-06-agent.json"),
    ("581dd8fc38811eeca36e65fcfb5093d743744adbcb44be6f160e63af7e450b90", "review-recovery-52-repair-06-agent.json"),
    ("54b4ec4ae9b53cd9fdb29065ddafcd8fea67e1d360023c1d6ae55dc6e2e4162b", "review-recovery-53-repair-05-agent.json"),
    ("5770c09b8367c798fe5be23ae82ac30a4f162f41fa0e58da70b29bb757e3e59f", "review-recovery-54-repair-04-agent.json"),
    ("8f53dc26bec02a7f1a6a617afb171d49e221fad8227b265d94e7384ce17f4bd0", "review-recovery-57-repair-04-agent.json"),
    ("87e69987a114bcf3a64e6cfa88e02b84c11efecb228bf3354f87d2553ea6151c", "review-recovery-106-repair-03-agent.json"),
]


def main():
    target = EXPERIMENT / "card-repair-preparation.json"
    existing = read_json(target) if target.exists() else {"entries": []}
    entries = list(existing["entries"])
    known = {(row["source_sha256"], row["attempt"]): row for row in entries}
    routes = {row["source_sha256"]: row for row in read_json(EXPERIMENT / "prepared.json")["entries"]}
    recoveries = []
    for key, report_name in SOURCES:
        route = routes[key]
        report_path = EXPERIMENT / report_name
        report = read_json(report_path)
        decision = report["entries"][0]
        assert decision["source_sha256"] == key and decision["decision"] == "rejected_for_production"
        match = re.fullmatch(r"external-(\d+)", decision["attempt"])
        assert match
        previous_number = int(match.group(1))
        number = previous_number + 1
        attempt = f"external-{number:02}"
        result_path = EXPERIMENT / "outputs" / f"{key}-{previous_number:02}.result.json"
        assert read_json(result_path)["sha256"] == decision["output_sha256"]
        old_prompt_path = EXPERIMENT / "outputs" / f"{key}-{previous_number:02}.prompt.txt"
        old_prompt = old_prompt_path.read_text(encoding="utf-8")
        reasons = " ".join(decision["remaining_reasons"])
        note_clarification = NOTE_GROUP_CLARIFICATIONS.get((key, attempt), "")
        prompt = (
            "ACTUAL OBSERVED CORRECTION: The previous returned image was rejected for the following specific visible defects. Correct every one simultaneously without introducing a replacement defect:\n"
            + reasons
            + note_clarification
            + "\n\nThe output must convert the person into the actual yellow 奶龙 mascot identity, never leave an unconverted human face or merely recolor human skin. Use a compact rounded golden-yellow mascot head, green-ringed solid black eyes and no white sclera, one source-appropriate small mouth, no human nose/ears/skin, and a short broad neck. Preserve every unrelated source-visible feature, composition and alpha/exterior contract. Apply the noted frame/note corrections exactly, including the original compact note-mark rows rather than invented extra writing.\n\n"
            + old_prompt
            + "\n\nFINAL PRIORITY: the output must be a yellow mascot, not a human, and must satisfy all of the observed corrections while retaining the original identity features, clothing, composition, backing and transparency. Do not repeat the rejected frame, hardware, note-row or facial conversion defects."
        )
        prompt_path = EXPERIMENT / "prompts" / f"{key}-{number:02}.txt"
        prompt_sha = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
        if (key, attempt) in known:
            revise_undispatched_prompt(prompt_path, known[(key, attempt)], prompt, prompt_sha)
            if prompt_path.is_file():
                assert file_sha256(prompt_path) == prompt_sha
            else:
                actual_prompt_path = EXPERIMENT / "outputs" / f"{key}-{number:02}.prompt.txt"
                if not actual_prompt_path.is_file():
                    raise RuntimeError(f"Prepared prompt is missing before dispatch: {prompt_path}")
                assert file_sha256(actual_prompt_path) == prompt_sha
                prompt_path.write_bytes(actual_prompt_path.read_bytes())
                assert file_sha256(prompt_path) == prompt_sha
                recoveries.append({
                    "source_sha256": key,
                    "attempt": attempt,
                    "recovered_at_utc": utc_now(),
                    "planned_prompt": prompt_path.relative_to(ROOT).as_posix(),
                    "actual_prompt": actual_prompt_path.relative_to(ROOT).as_posix(),
                    "prompt_sha256": prompt_sha,
                })
            continue
        assert not prompt_path.exists()
        prompt_path.write_bytes(prompt.encode("utf-8"))
        entries.append({
            "source_sha256": key,
            "attempt": attempt,
            "review": report_path.relative_to(ROOT).as_posix(),
            "review_sha256": file_sha256(report_path),
            "rejected_output_sha256": decision["output_sha256"],
            "previous_prompt": old_prompt_path.relative_to(ROOT).as_posix(),
            "previous_prompt_sha256": file_sha256(old_prompt_path),
            "prompt_file": prompt_path.relative_to(ROOT).as_posix(),
            "prompt_sha256": prompt_sha,
            "output": f"mod_nailong/experiments/evolink-high131-flare-20261025/outputs/{key}-{number:02}.png",
            "model": route["model"],
            "background": route["background"],
            "size": route["size"],
            "resolution": route["resolution"],
            "quality": route["quality"],
            "ordered_inputs": ["original source PNG", "user mascot reference"],
            "reason": reasons,
        })
        known[(key, attempt)] = entries[-1]
    if recoveries:
        audit_path = EXPERIMENT / "prompt-sidecar-recovery.json"
        audit = read_json(audit_path) if audit_path.exists() else {"entries": []}
        audit_entries = list(audit["entries"])
        audit_known = {(row["source_sha256"], row["attempt"]): row for row in audit_entries}
        for row in recoveries:
            identity = (row["source_sha256"], row["attempt"])
            if identity in audit_known:
                assert audit_known[identity] == row
            else:
                audit_entries.append(row)
        write_json(audit_path, {
            "schema": "naiwa-evolink-high131-prompt-sidecar-recovery-v1",
            "machine_id": machine_id(),
            "created_at_utc": audit.get("created_at_utc", utc_now()),
            "updated_at_utc": utc_now(),
            "entries": audit_entries,
            "scope": "A missing planned prompt was observed during continuation and restored byte-identically from the existing actual client sidecar after matching the independently recomputed expected prompt. This is not evidence that the planned file existed before the earlier call. Actual task, request and result records remain unchanged.",
        })
    write_json(target, {
        "schema": "naiwa-evolink-high131-card-repair-preparation-v1",
        "machine_id": machine_id(),
        "prepared_at_utc": existing.get("prepared_at_utc", utc_now()),
        "updated_at_utc": utc_now(),
        "entries": entries,
        "scope": "Preparation records bound to actual SHA-bound visual rejections. Earlier prompts, outputs, tasks and rejected reviews remain unchanged. Any actual call is established only by its own output sidecars, never by this preparation record.",
    })
    print(json.dumps({"prepared": len(entries), "recovered_planned_prompts": len(recoveries), "prompt_sha256": {row["source_sha256"]: row["prompt_sha256"] for row in entries}}, ensure_ascii=True))


if __name__ == "__main__":
    main()
