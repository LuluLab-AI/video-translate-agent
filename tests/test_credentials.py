import stat
from io import StringIO

import pytest

from video_translate import credentials
from video_translate.config import load_config


@pytest.fixture(autouse=True)
def keyring_backend(monkeypatch):
    monkeypatch.setattr(credentials, "_uses_local_user_file", lambda: False)


def test_environment_wins_over_system_keyring(monkeypatch):
    monkeypatch.setattr("video_translate.config.read_credential", lambda provider: "stored-secret")
    monkeypatch.setenv("ELEVENLABS_API_KEY", "environment-secret")
    config = load_config()
    assert config.elevenlabs_api_key.get_secret_value() == "environment-secret"


def test_system_keyring_is_fallback(monkeypatch):
    monkeypatch.delenv("MINIMAX_API_KEY", raising=False)
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    monkeypatch.setattr("video_translate.config.read_credential",
                        lambda provider: "stored-secret" if provider == "elevenlabs" else None)
    assert load_config().configured_providers() == ["elevenlabs"]


def test_explicit_environment_disables_keyring(monkeypatch):
    monkeypatch.setattr("video_translate.config.read_credential",
                        lambda provider: pytest.fail("keyring should not be read"))
    assert load_config(environ={}).configured_providers() == []


def test_store_prompts_without_command_line_secret(monkeypatch):
    saved = []
    monkeypatch.setattr(credentials, "getpass", lambda prompt: "secret-from-hidden-prompt")
    monkeypatch.setattr(credentials.keyring, "set_password",
                        lambda service, provider, value: saved.append((service, provider, value)))
    credentials.store_credential("elevenlabs")
    assert saved == [(credentials.SERVICE_NAME, "elevenlabs", "secret-from-hidden-prompt")]


def test_store_value_uses_same_secure_store(monkeypatch):
    saved = []
    monkeypatch.setattr(credentials.keyring, "set_password",
                        lambda service, provider, value: saved.append((service, provider, value)))
    credentials.store_credential_value("elevenlabs", "  supplied-secret  ")
    assert saved == [(credentials.SERVICE_NAME, "elevenlabs", "supplied-secret")]


def test_store_from_stream_uses_bounded_single_line(monkeypatch):
    saved = []
    monkeypatch.setattr(credentials, "store_credential_value",
                        lambda provider, value: saved.append((provider, value)))
    credentials.store_credential_from_stream("elevenlabs", StringIO("chat-secret\nignored"))
    assert saved == [("elevenlabs", "chat-secret\n")]


def test_store_from_stream_accepts_limit_before_newline(monkeypatch):
    saved = []
    monkeypatch.setattr(credentials, "store_credential_value",
                        lambda provider, value: saved.append((provider, value)))
    value = "x" * credentials.MAX_CREDENTIAL_CHARS
    credentials.store_credential_from_stream("elevenlabs", StringIO(value + "\n"))
    assert saved == [("elevenlabs", value + "\n")]


@pytest.mark.parametrize("value,error", [
    ("\n", "EMPTY_CREDENTIAL"),
    ("x" * (credentials.MAX_CREDENTIAL_CHARS + 1), "CREDENTIAL_INPUT_TOO_LARGE"),
])
def test_store_from_stream_rejects_invalid_input(monkeypatch, value, error):
    monkeypatch.setattr(credentials.keyring, "set_password",
                        lambda *_args: pytest.fail("invalid input must not be stored"))
    with pytest.raises(credentials.CredentialError, match=f"^{error}$"):
        credentials.store_credential_from_stream("elevenlabs", StringIO(value))


def test_read_migrates_legacy_service_credential(monkeypatch):
    stored = []
    monkeypatch.setattr(
        credentials.keyring,
        "get_password",
        lambda service, provider: "legacy-secret"
        if service == credentials.LEGACY_SERVICE_NAME
        else None,
    )
    monkeypatch.setattr(
        credentials.keyring,
        "set_password",
        lambda service, provider, value: stored.append((service, provider, value)),
    )
    assert credentials.read_credential("elevenlabs") == "legacy-secret"
    assert stored == [(credentials.SERVICE_NAME, "elevenlabs", "legacy-secret")]


def test_macos_local_file_avoids_keyring_and_enforces_permissions(monkeypatch, tmp_path):
    path = tmp_path / "credentials" / "credentials.json"
    monkeypatch.setattr(credentials, "_uses_local_user_file", lambda: True)
    monkeypatch.setattr(credentials, "_local_credential_file", lambda: path)
    monkeypatch.setattr(credentials.keyring, "get_password",
                        lambda *_args: pytest.fail("macOS keyring must not be used"))
    credentials.store_credential_value("elevenlabs", "local-secret")
    assert credentials.read_credential("elevenlabs", strict=True) == "local-secret"
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert credentials.credential_storage_name() == "local-user-file"
    assert credentials.delete_credential("elevenlabs") is True
    assert not path.exists()


def test_legacy_alias_persists_as_lululab_and_preserves_tts(monkeypatch, tmp_path):
    path = tmp_path / 'credentials' / 'credentials.json'
    monkeypatch.setattr(credentials, '_uses_local_user_file', lambda: True)
    monkeypatch.setattr(credentials, '_local_credential_file', lambda: path)
    credentials.store_credential_value('elevenlabs', 'fixture-key')
    credentials.store_credential_from_stream('lzstudio', StringIO('fixture-key\n'))
    assert credentials.read_credential('lululab', strict=True) == 'fixture-key'
    assert credentials.read_credential('lingzhi', strict=True) == 'fixture-key'
    assert credentials.read_credential('lzstudio', strict=True) == 'fixture-key'
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert credentials.delete_credential('lzstudio')
    assert credentials.read_credential('lululab') is None
    assert credentials.read_credential('elevenlabs') == 'fixture-key'


@pytest.mark.parametrize('variable', ['LULULAB_API_KEY', 'LINGZHI_API_KEY', 'LZSTUDIO_API_KEY'])
def test_lululab_environment_overrides_saved(monkeypatch, variable):
    from video_translate import policy_client
    monkeypatch.delenv('LULULAB_API_KEY', raising=False)
    monkeypatch.delenv('LINGZHI_API_KEY', raising=False)
    monkeypatch.delenv('LZSTUDIO_API_KEY', raising=False)
    monkeypatch.setenv(variable, 'environment-secret')
    monkeypatch.setattr(policy_client, 'read_credential', lambda *a, **kw: pytest.fail('environment must win'))
    assert policy_client._api_key() == 'environment-secret'


def test_lululab_saved_key_drives_preflight(monkeypatch):
    from video_translate import policy_client
    monkeypatch.delenv('LULULAB_API_KEY', raising=False)
    monkeypatch.delenv('LINGZHI_API_KEY', raising=False)
    monkeypatch.setenv('LZSTUDIO_API_KEY', '  ')
    monkeypatch.setattr(policy_client, 'read_credential', lambda *a, **kw: 'fixture-key')
    assert policy_client._api_key() == 'fixture-key'
    assert policy_client.capabilities()['policy_credential_available']


def test_lululab_cli_stdin_and_status_are_secret_free(monkeypatch, capsys):
    import sys
    from video_translate import cli
    saved = []
    monkeypatch.setattr(sys, 'stdin', StringIO('fixture-key\n'))
    monkeypatch.setattr(credentials, 'store_credential_value', lambda name, value: saved.append((name, value.strip())))
    assert cli.main(['credential-set', '--provider', 'lululab', '--stdin', '--json']) == 0
    assert saved == [('lululab', 'fixture-key')]
    assert 'fixture-key' not in capsys.readouterr().out
    monkeypatch.setattr(cli, 'read_credential', lambda name, **kw: 'fixture-key' if name == 'lululab' else None)
    assert cli.main(['credential-status', '--json']) == 0
    output = capsys.readouterr().out
    assert 'lululab' in output and 'fixture-key' not in output
    with pytest.raises(SystemExit):
        cli.parser().parse_args(['preflight', '--provider', 'lingzhi'])


def test_local_legacy_policy_credential_is_migrated(monkeypatch, tmp_path):
    path = tmp_path / 'credentials' / 'credentials.json'
    monkeypatch.setattr(credentials, '_uses_local_user_file', lambda: True)
    monkeypatch.setattr(credentials, '_local_credential_file', lambda: path)
    credentials._write_local_credentials({'lingzhi': 'fixture-key'})
    assert credentials.read_credential('lululab', strict=True) == 'fixture-key'
    values = credentials._read_local_credentials(strict=True)
    assert values['lululab'] == 'fixture-key'
    assert 'lingzhi' not in values


def test_lululab_node_override_precedes_path(monkeypatch, tmp_path):
    from video_translate import policy_client
    primary = tmp_path / 'node-primary'
    secondary = tmp_path / 'node-secondary'
    monkeypatch.setenv('LULULAB_NODE', str(primary))
    monkeypatch.setenv('NODE_BINARY', str(secondary))
    monkeypatch.setattr(policy_client.shutil, 'which', lambda _name: '/fixture/node')
    candidates = policy_client._candidate_node_binaries()
    assert candidates == [primary, secondary, policy_client.Path('/fixture/node')]


def test_policy_workflow_id_is_unchanged(monkeypatch):
    from video_translate import policy_client
    monkeypatch.delenv('VIDEO_TRANSLATE_POLICY_WORKFLOW_ID', raising=False)
    assert policy_client._workflow_id() == 'VideoTranslatePolicyV1'
