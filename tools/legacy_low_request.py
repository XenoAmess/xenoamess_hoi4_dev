"""Four audited historical LOW cache requests; this never authorizes image calls."""
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path

from tools.common import read_json

SCHEMA = 'naiwa-recovered-low-cached-actual-request-v2'
CONTRACT_FILE = Path(__file__).with_name('legacy_low_request_contracts.json')


def digest(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def moment(event):
    return datetime.fromisoformat(event['timestamp'].replace('Z', '+00:00'))


def contract_for(key):
    database = read_json(CONTRACT_FILE)
    assert database['schema'] == 'naiwa-audited-four-low-cache-contracts-v2'
    assert key in database['contracts'], 'Unknown historical LOW cache remains held'
    return database, database['contracts'][key]


def validate_cached_job(key, archive, events):
    database, contract = contract_for(key)
    assert archive['schema'] == SCHEMA
    assert archive['machine_id'] == database['machine_id']
    assert archive['failed_attempt'] == contract['failed_attempt']
    assert archive['cache_name'] == contract['cache_name']
    assert archive['cache_interval_proof'] == contract['interval']
    records = archive['events']
    assert set(records) == set(contract['events']) == set(events)
    for name, frozen in contract['events'].items():
        record = records[name]
        assert all(record[field] == value for field, value in frozen.items())
        assert digest(record['raw_utf8']) == frozen['raw_line_sha256']
        assert json.loads(record['raw_utf8']) == events[name]

    accesses = archive['cache_accesses']
    assert len(accesses) == len(contract['accesses'])
    for access, frozen in zip(accesses, contract['accesses']):
        assert all(access[field] == value for field, value in frozen.items())
        assert digest(access['raw_utf8']) == frozen['raw_line_sha256']
        event = json.loads(access['raw_utf8'])
        caller = event['payload']
        assert event['type'] == 'response_item'
        assert caller['type'] == 'custom_tool_call' and caller['name'] == 'exec'
        assert digest(caller['input']) == frozen['code_sha256']
        assert archive['cache_name'] in caller['input']
    assert accesses[0]['raw_utf8'] == records['cache_loader']['raw_utf8']
    assert accesses[-1]['raw_utf8'] == records['dispatch']['raw_utf8']
    interval = archive['cache_interval_proof']
    assert interval['start_byte_offset'] == records['cache_loader']['source_byte_offset']
    assert interval['end_byte_offset'] == records['dispatch']['source_byte_offset'] + len(records['dispatch']['raw_utf8'].encode('utf-8'))
    assert interval['end_byte_offset'] - interval['start_byte_offset'] == interval['interval_bytes']
    assert interval['matching_tool_call_line_sha256'] == [a['raw_line_sha256'] for a in accesses]

    exported = events['pre_call_job']
    item = exported['payload']['item']
    assert exported['payload']['type'] == 'item_completed'
    assert item['type'] == 'CommandExecution' and item['status'] == 'completed'
    assert item['exit_code'] == 0 and item['command'][-1] == contract['command']
    jobs = json.loads(item['stdout'])
    assert isinstance(jobs, list) and len(jobs) == contract['list_length']
    job = jobs[contract['index']]
    assert job['key'] == key and isinstance(job['transparent'], bool)
    assert digest(job['prompt']) == contract['prompt_sha256']
    assert moment(events['cache_loader']) < moment(exported) < moment(events['dispatch']) < moment(events['failed_extension'])
    return job


def validate_refusal(key, attempt, events):
    _, contract = contract_for(key)
    refusal_event = events['refusal_receipt']
    payload = refusal_event['payload']
    if payload['type'] == 'custom_tool_call_output':
        assert payload['call_id'] == events['dispatch']['payload']['call_id']
        errors = [block['text'] for block in payload['output'] if block['type'] == 'input_text' and 'moderation_blocked' in block.get('text', '')]
    else:
        assert payload['type'] == 'item_completed'
        item = payload['item']
        assert item['type'] == 'FileChange' and item['status'] == 'completed'
        errors = [v['content'] for path, v in item['changes'].items() if key in path and path.endswith('.txt') and v['type'] == 'add']
    assert len(errors) == 1 and 'moderation_blocked' in errors[0]
    request_id = contract['request_id']
    ids = re.findall(r'[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}', attempt['error'])
    assert ids == [request_id] and ('request ID ' + request_id) in errors[0]
    assert moment(events['failed_extension']) <= moment(refusal_event)
    assert moment(refusal_event) <= datetime.fromisoformat(attempt['observed_at_utc'].replace('Z', '+00:00'))
