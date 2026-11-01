"""Dispatch frozen development text tasks through the sibling shared caller.

This adapter never executes candidates or implements its own model HTTP retry.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import threading
import uuid

ROOT = Path(__file__).resolve().parents[1]
TEXT_SUFFIXES = {'.json', '.py', '.md', '.txt', '.lua', '.yml', '.yaml', '.toml', '.ini', '.cfg', '.cjs', '.js', '.xml', '.gui', '.gfx'}


def utc():
    return datetime.now(timezone.utc).isoformat()


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def save(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')


def text_file(value, relative_to):
    if not isinstance(value, str) or not value:
        raise ValueError('Expected a nonempty material path')
    path = (relative_to / value).resolve()
    if not path.is_relative_to(ROOT.resolve()) or not path.is_file():
        raise ValueError('Material must be a file inside this project: ' + str(path))
    if path.suffix.lower() not in TEXT_SUFFIXES:
        raise ValueError('Only explicit development text materials are allowed: ' + str(path))
    if any(p.lower() in {'.git', '.ssh', '.aws', '.azure', 'credentials'} or p.lower().startswith('.env') for p in path.parts):
        raise ValueError('Credential or repository-internal material is not allowed')
    path.read_text(encoding='utf-8-sig')  # Reject nontext before any dispatch.
    return path


def shared_client(operations):
    operations = Path(operations).resolve()
    files = {name: operations / name for name in ['AGENTS.md', 'config/executor.json', 'scripts/call.py', 'scripts/check_opencode.py']}
    if not all(path.is_file() for path in files.values()):
        raise ValueError('Read the complete sibling local-model-operations checkout first')
    spec = importlib.util.spec_from_file_location('_hoi4_shared_model_caller', files['scripts/call.py'])
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, read_json(files['config/executor.json']), files, {name: digest(path) for name, path in files.items()}


def prepare_plan(plan_path, caller, config):
    plan_path = Path(plan_path).resolve()
    plan = read_json(plan_path)
    if not isinstance(plan, dict):
        raise ValueError('Plan must be a JSON object')
    tasks = plan.get('tasks')
    if not isinstance(tasks, list) or not tasks:
        raise ValueError('Plan needs a nonempty tasks list')
    seen_ids, specs, outputs, prepared = set(), set(), set(), []
    for item in tasks:
        if not isinstance(item, dict) or set(item) != {'task_id', 'spec', 'output'}:
            raise ValueError('Each task needs only task_id, spec, output')
        key = item['task_id']
        if not isinstance(key, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,95}', key) or key in seen_ids:
            raise ValueError('Invalid or duplicate task_id')
        seen_ids.add(key)
        spec_path = text_file(item['spec'], plan_path.parent)
        if spec_path in specs:
            raise ValueError('Duplicate task spec')
        specs.add(spec_path)
        data = read_json(spec_path)
        if not isinstance(data, dict) or any(k in data for k in ['messages', 'body', 'request']):
            raise ValueError('Use an explicit source/task spec, not an opaque request')
        has_stable, has_list = 'stable_source_path' in data, 'source_files' in data
        if has_stable == has_list or 'task_path' not in data:
            raise ValueError('Specify stable_source_path XOR source_files, and task_path')
        names = [data['stable_source_path']] if has_stable else data['source_files']
        if not isinstance(names, list) or not names:
            raise ValueError('Source materials must be a nonempty list')
        materials = [text_file(name, spec_path.parent) for name in names]
        materials.append(text_file(data['task_path'], spec_path.parent))
        budget = data.get('max_tokens')
        if type(budget) is not int or not 1 <= budget <= 16000:
            raise ValueError('Finite max_tokens must be 1..16000')
        if not isinstance(item['output'], str) or not item['output']:
            raise ValueError('Expected an output path')
        output = (plan_path.parent / item['output']).resolve()
        allowed = (ROOT / 'runtime/local-model-operations').resolve()
        if output == allowed or not output.is_relative_to(allowed) or output.exists():
            raise ValueError('Output must be a new directory below runtime/local-model-operations')
        if any(output == old or output.is_relative_to(old) or old.is_relative_to(output) for old in outputs):
            raise ValueError('Duplicate or overlapping task outputs')
        outputs.add(output)
        versions = {str(p): digest(p) for p in [spec_path, *materials]}
        request, _ = caller.prepare_request(spec_path, config)
        if versions != {str(p): digest(p) for p in [spec_path, *materials]}:
            raise ValueError('Input changed while freezing the plan')
        prepared.append({'task_id': key, 'spec': spec_path, 'output': output, 'request': request, 'input_sha256': versions})
    return prepared


def run_batch(plan, operations, machine_id, owner, jobs=4):
    if not isinstance(machine_id, str) or not machine_id.strip() or not isinstance(owner, str) or not owner.strip():
        raise ValueError('Explicit nonempty machine_id and owner are required')
    if type(jobs) is not int or not 1 <= jobs <= 32:
        raise ValueError('jobs must be 1..32')
    caller, config, files, hashes = shared_client(operations)
    tasks = prepare_plan(plan, caller, config)  # Whole-plan validation before writes/maintenance/POST.
    batch = ROOT / 'runtime/local-model-operations/batches' / uuid.uuid4().hex
    batch.mkdir(parents=True, exist_ok=False)
    config_path = batch / 'executor.json'
    save(config_path, config)
    receipt = {'started_at_utc': utc(), 'machine_id': machine_id, 'owner': owner, 'mode_id': 'http-candidate', 'shared_file_sha256': hashes, 'maintenance_log': str(batch / 'maintenance.log'), 'adopted': False, 'results': []}
    env = os.environ.copy()
    env.update(PYTHONIOENCODING='utf-8', PYTHONUTF8='1')
    from urllib.parse import urlparse
    host = urlparse(config['base_url']).hostname
    if host:
        env['NO_PROXY'] = env.get('NO_PROXY', '') + ',' + host
        env['no_proxy'] = env['NO_PROXY']
    flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
    with (batch / 'maintenance.log').open('xb') as log:
        check = subprocess.run([sys.executable, '-X', 'utf8', str(files['scripts/check_opencode.py']), '--config', str(config_path)], env=env, stdout=log, stderr=subprocess.STDOUT, shell=False, creationflags=flags)
    receipt['maintenance_exit_code'] = check.returncode
    if check.returncode:
        receipt.update(ended_at_utc=utc(), status='maintenance_failed_ai_repair_required')
        save(batch / 'result.json', receipt)
        return check.returncode, batch
    stop = threading.Event()

    def run(task):
        if stop.is_set():
            return {'task_id': task['task_id'], 'status': 'not_started_after_maintenance_failure', 'adopted': False}
        if any(digest(files[name]) != sha for name, sha in hashes.items()):
            stop.set()
            return {'task_id': task['task_id'], 'exit_code': 2, 'status': 'shared_source_changed_before_dispatch', 'adopted': False}
        output = task['output']
        output.mkdir(parents=True, exist_ok=False)
        frozen = output / 'FROZEN-SPEC.json'
        save(frozen, task['request'])
        save(output / 'INPUT-PROVENANCE.json', {'task_id': task['task_id'], 'input_sha256': task['input_sha256'], 'shared_file_sha256': hashes, 'frozen_spec_sha256': digest(frozen)})
        command = [sys.executable, '-X', 'utf8', str(files['scripts/call.py']), str(frozen), task['task_id'], '--output', str(output), '--config', str(config_path), '--machine-id', machine_id, '--owner', owner]
        started = utc()
        with (output / 'caller.log').open('xb') as log:
            process = subprocess.run(command, env=env, stdout=log, stderr=subprocess.STDOUT, shell=False, creationflags=flags)
        if process.returncode == 75:
            stop.set()
        result = {'task_id': task['task_id'], 'started_at_utc': started, 'ended_at_utc': utc(), 'exit_code': process.returncode, 'output': str(output), 'adopted': False, 'review': 'owner_required'}
        save(output / 'RUNNER-RESULT.json', result)
        return result

    with ThreadPoolExecutor(max_workers=jobs) as pool:
        futures = {pool.submit(run, task): task for task in tasks}
        for future in as_completed(futures):
            try:
                result = future.result()
            except Exception as error:
                result = {'task_id': futures[future]['task_id'], 'exit_code': 2, 'error': repr(error), 'adopted': False}
            receipt['results'].append(result)
            save(batch / 'result.json', receipt)
    receipt.update(ended_at_utc=utc(), status='processes_ended_candidates_require_owner_review')
    save(batch / 'result.json', receipt)
    codes = [r.get('exit_code', 2) for r in receipt['results']]
    return (75 if 75 in codes else 1 if any(codes) else 0), batch


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('plan', type=Path)
    parser.add_argument('--operations-repo', type=Path, default=ROOT.parent / 'local-model-operations')
    parser.add_argument('--machine-id', required=True)
    parser.add_argument('--owner', required=True)
    parser.add_argument('--jobs', type=int, default=4)
    args = parser.parse_args(argv)
    try:
        code, path = run_batch(args.plan, args.operations_repo, args.machine_id, args.owner, args.jobs)
    except (ValueError, OSError, KeyError, TypeError) as error:
        print(str(error), file=sys.stderr)
        return 2
    print(json.dumps({'batch_receipt': str(path / 'result.json'), 'exit_code': code, 'adopted': False}))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
