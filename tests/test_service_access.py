import json
import subprocess
from pathlib import Path
from types import SimpleNamespace as NS

import pytest
from video_translate import policy_client as policy, cli
from video_translate.service_access import SERVICE_ERROR, SERVICE_MESSAGE, service_blocked

@pytest.mark.parametrize('response', [
    {'error_code': 'INSUFFICIENT_CREDITS', 'balance': 0},
    {'error': {'message': '积分不足，请充值'}},
    {'output': json.dumps({'success': False, 'error_code': 'QUOTA_EXCEEDED'})},
    {'message': 'insufficient balance'},
])
def test_service_denial_is_neutral(monkeypatch, response):
    calls = []
    monkeypatch.setattr(policy, 'find_node', lambda: Path('/fixture/node'))
    monkeypatch.setattr(policy, '_api_key', lambda: 'fixture-key')
    def run(command, **kwargs):
        calls.append(command)
        return NS(returncode=1, stdout=json.dumps(response), stderr='')
    monkeypatch.setattr(policy.subprocess, 'run', run)
    with pytest.raises(policy.PolicyError, match=SERVICE_ERROR):
        policy.request_task({}, workflow_id='fixture')
    assert len(calls) == 1


def test_poll_failure_and_normal_metadata(monkeypatch):
    calls = []
    records = iter([{'id': 'same', 'credits': 99},
                    {'status': 'completed', 'output': {'success': True, 'balance': 50, 'value': 3}}])
    monkeypatch.setattr(policy, 'find_node', lambda: Path('/fixture/node'))
    monkeypatch.setattr(policy, '_api_key', lambda: 'fixture-key')
    def run(command, **kwargs):
        calls.append(command)
        return NS(returncode=0, stdout=json.dumps(next(records)), stderr='')
    monkeypatch.setattr(policy.subprocess, 'run', run)
    assert policy.request_task({}, workflow_id='fixture') == {'success': True, 'value': 3}
    assert [c[2:4] for c in calls] == [['task', 'submit'], ['task', 'fetch']]
    monkeypatch.setattr(policy, '_run_cli', lambda *a, **k: {'status': 'failed', 'error': '积分耗尽'})
    with pytest.raises(policy.PolicyError, match=SERVICE_ERROR):
        policy._poll('same', timeout=1, interval=0)


def test_technical_errors_and_content_are_not_authorization(monkeypatch):
    assert not service_blocked({'text': '积分不足', 'balance': 0})
    assert not service_blocked({'error': 'network timeout'})
    monkeypatch.setattr(policy, 'find_node', lambda: Path('/fixture/node'))
    monkeypatch.setattr(policy, '_api_key', lambda: 'fixture-key')
    def run(*a, **k):
        raise subprocess.TimeoutExpired('fixture', 1)
    monkeypatch.setattr(policy.subprocess, 'run', run)
    with pytest.raises(policy.PolicyError, match='POLICY_CLI_TIMEOUT'):
        policy._run_cli(['task', 'submit'], timeout=1)


def test_node_client_receives_key_only_through_stdin(monkeypatch):
    monkeypatch.setattr(policy, 'find_node', lambda: Path('/fixture/node'))
    monkeypatch.setattr(policy, '_api_key', lambda: 'fixture-key')
    captured = {}
    def run(command, **kwargs):
        captured.update(command=command, kwargs=kwargs)
        return NS(returncode=0, stdout='{"id":"task-1"}', stderr='')
    monkeypatch.setattr(policy.subprocess, 'run', run)
    policy._run_cli(['task', 'submit', '--workflow-id', 'fixture', '--input', '{}'], timeout=1)
    assert 'fixture-key' not in captured['command']
    assert '--api-key-stdin' in captured['command']
    assert captured['kwargs']['input'] == 'fixture-key\n'


def test_cli_does_not_leak(monkeypatch, capsys):
    def execute(args):
        raise policy.PolicyError(SERVICE_ERROR)
    monkeypatch.setattr(cli, 'execute', execute)
    assert cli.main(['align', '--job', '0' * 32, '--json']) == 1
    result = json.loads(capsys.readouterr().out)
    assert result == {'ok': False, 'error': SERVICE_ERROR, 'stage': 'align', 'message': 'Skill authorization error. Please contact the administrator via WeChat: marlon1102'}


def test_failed_stage_preserves_artifacts_and_resumes(job):
    from video_translate.models import Phase
    from video_translate.workflow import stage
    store, manifest = job
    path = store.directory(manifest.job_id) / "completed.wav"
    path.write_bytes(b"completed fixture")
    store.record_artifact(manifest.job_id, "audio", "completed.wav")
    store.transition(manifest.job_id, Phase.LANG_CONFIRMED, source_language="auto", target_language="en")
    def denied(manifest):
        raise policy.PolicyError(SERVICE_ERROR)
    with pytest.raises(policy.PolicyError, match=SERVICE_ERROR):
        stage(store, manifest.job_id, Phase.TRANSCRIBED, denied)
    failed = store.load(manifest.job_id)
    assert failed.error == SERVICE_ERROR
    assert failed.last_successful_phase == Phase.LANG_CONFIRMED
    assert store.verify(failed) == []
    done = stage(store, manifest.job_id, Phase.TRANSCRIBED,
                 lambda m: store.transition(m.job_id, Phase.TRANSCRIBED))
    assert done.error is None and "audio" in done.artifacts
    assert path.read_bytes() == b"completed fixture"
