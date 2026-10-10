import json
from pathlib import Path

import pytest

from video_translate.interaction_language import (
    normalize_language_tag, select_interaction_language, load_language_context,
    save_language_context, ui_catalog, InteractionLanguageError,
)
from video_translate.ui_catalogs import BUILTIN_TEXT
from video_translate import cli, credential_setup


@pytest.mark.parametrize('signals, language, source', [
    ({'explicit': 'ja-JP', 'task_language': 'zh-CN', 'saved': 'pt-BR', 'agent_default': 'en-US'}, 'ja-JP', 'explicit'),
    ({'task_language': 'zh-CN', 'agent_default': 'en-US'}, 'zh-CN', 'user_message'),
    ({'task_language': 'en-US', 'agent_default': 'zh-CN'}, 'en-US', 'user_message'),
    ({'task_language': 'pt-BR', 'saved': 'zh-CN', 'agent_default': 'en'}, 'pt-BR', 'user_message'),
    ({'saved': 'fr-FR', 'agent_default': 'zh-CN'}, 'fr-FR', 'saved_task'),
    ({'agent_default': 'ko-KR'}, 'ko-KR', 'agent_default'),
    ({'agent_default': 'zh-CN'}, 'zh-CN', 'agent_default'),
    ({'agent_default': 'en-US'}, 'en-US', 'agent_default'),
    ({'task_language': 'es-ES', 'agent_default': 'zh-CN'}, 'es-ES', 'user_message'),
    ({'task_language': 'fr-FR', 'agent_default': 'en-US'}, 'fr-FR', 'user_message'),
    ({'task_language': 'ja-JP', 'agent_default': 'en-US'}, 'ja-JP', 'user_message'),
    ({}, 'en', 'fallback'),
])
def test_language_priority(signals, language, source):
    selected = select_interaction_language(**signals)
    assert (selected.language, selected.source) == (language, source)


@pytest.mark.parametrize('tag', [
    'zh-CN', 'en-US', 'pt-BR', 'es-ES', 'fr-FR', 'ja-JP', 'ko-KR', 'th-TH', 'ar-SA',
    'de-DE', 'sw-KE', 'sr-Latn-RS', 'zh-Hant-HK', 'es-419', 'en-US-u-ca-gregory',
    'sl-rozaj-biske', 'x-customer', 'i-klingon', 'qaa-Qaaa-QM',
])
def test_bcp47_has_no_language_allowlist(tag):
    assert normalize_language_tag(tag) == tag


@pytest.mark.parametrize('tag', ['zh_CN', 'en_US.UTF-8', 'C', '<script>', 'en-', 'en--US',
    'en-US-u', 'en-US-u-ca-u-nu', 'sl-rozaj-rozaj', 'en/x', 'en US', 'en-abcdefghi'])
def test_rejects_malformed_tags(tag):
    with pytest.raises(ValueError):
        normalize_language_tag(tag)


def test_context_resume_confirm_and_explicit_switch(tmp_path, capsys, monkeypatch):
    context = tmp_path / 'interaction_language.json'
    monkeypatch.setenv('LC_ALL', 'ja_JP.UTF-8')
    assert cli.main(['language-context', '--context-file', str(context),
                     '--task-language', 'pt-BR', '--agent-language', 'zh-CN']) == 0
    assert load_language_context(context) == 'pt-BR'
    # Agent passes no new task-language for a number, upload or simple confirmation.
    for _ in ('3', 'OK', 'asset-only'):
        assert cli.main(['language-context', '--context-file', str(context),
                         '--agent-language', 'en-US']) == 0
        assert load_language_context(context) == 'pt-BR'
    assert cli.main(['language-context', '--context-file', str(context),
                     '--reply-language', 'fr-FR', '--task-language', 'zh-CN']) == 0
    assert load_language_context(context) == 'fr-FR'
    assert cli.main(['language-context', '--context-file', str(context),
                     '--task-language', 'ja-JP']) == 0
    assert load_language_context(context) == 'fr-FR'
    assert cli.main(["language-context", "--context-file", str(context), "--reply-language", "ja-JP"]) == 0
    assert load_language_context(context) == "ja-JP"
    assert all('target_language' not in r for r in context.read_text().splitlines())


@pytest.mark.parametrize('language', ['zh-CN', 'en-US', 'pt-BR', 'es-ES', 'fr-FR', 'ja-JP', 'ko-KR', 'th-TH', 'ar-SA', 'zh-Hant-TW'])
def test_bundled_catalogs_are_complete(language):
    assert set(ui_catalog(language)) == set(BUILTIN_TEXT['en'])


def test_unknown_language_requires_complete_catalog_without_english_fallback(tmp_path):
    with pytest.raises(InteractionLanguageError, match='UI_TRANSLATION_REQUIRED'):
        ui_catalog('de-DE')
    path = tmp_path / 'ui.json'
    messages = {key: 'Deutsch ' + text for key, text in BUILTIN_TEXT['en'].items()}
    messages['connect'] = '<script>alert(1)</script>'
    path.write_text(json.dumps({'language': 'de-DE', 'messages': messages}), encoding='utf-8')
    labels = ui_catalog('de-DE', path)
    page = credential_setup._setup_page('/setup/x', 'csrf', ui_language='de-DE', labels=labels).decode()
    assert 'lang="de-DE"' in page
    assert '&lt;script&gt;' in page and '<script>' not in page
    with pytest.raises(InteractionLanguageError, match='UI_CATALOG_LANGUAGE_MISMATCH'):
        ui_catalog('it-IT', path)
    messages.pop('privacy')
    path.write_text(json.dumps({'language': 'de-DE', 'messages': messages}))
    with pytest.raises(InteractionLanguageError, match='INVALID_UI_CATALOG'):
        ui_catalog('de-DE', path)


def test_saved_language_drives_credential_page_and_prompt(tmp_path, monkeypatch):
    path = tmp_path / 'interaction_language.json'
    save_language_context(path, select_interaction_language(task_language='pt-BR'))
    received = {}
    monkeypatch.setattr(cli, 'run_credential_setup', lambda **kwargs: received.update(kwargs) or {'stored': True})
    args = cli.parser().parse_args(['credential-setup', '--language-context', str(path), '--agent-language', 'ja-JP'])
    assert cli.execute(args)[1] == 0
    assert received['ui_language'] == 'pt-BR'
    monkeypatch.setattr(cli, 'store_credential', lambda provider, **kwargs: received.update(kwargs))
    args = cli.parser().parse_args(['credential-set', '--provider', 'lululab', '--language-context', str(path)])
    assert cli.execute(args)[1] == 0
    assert received['prompt'] == ui_catalog('pt-BR')['credential_prompt'].format(provider='lululab')


def test_service_message_uses_context_and_keeps_stable_code(tmp_path, monkeypatch, capsys):
    path = tmp_path / 'interaction_language.json'
    save_language_context(path, select_interaction_language(task_language='es-ES'))
    monkeypatch.setattr(cli, 'execute', lambda args: ({'error': 'SKILL_SERVICE_UNAVAILABLE'}, 1))
    assert cli.main(['preflight', '--language-context', str(path)]) == 1
    result = json.loads(capsys.readouterr().out)
    assert result['error'] == 'SKILL_SERVICE_UNAVAILABLE'
    assert result['message'] == ui_catalog('es-ES')['service_unavailable']


@pytest.mark.parametrize("interaction, source, target", [
    ("zh-CN", "en", "es"), ("en-US", "zh-CN", "ja"), ("pt-BR", "ja", "en"),
])
def test_video_languages_remain_independent_through_failure_and_resume(tmp_path, interaction, source, target):
    from video_translate.config import load_config
    from video_translate.models import Phase
    from video_translate.state import JobStore
    from video_translate.files import write_json
    video = tmp_path / "source.mp4"
    video.write_bytes(b"unchanged-source-fixture")
    store = JobStore(tmp_path)
    manifest = store.create(video, load_config(runtime_root=tmp_path).snapshot())
    # Supply the same source/target choices that transcribe persists; no paid/media work.
    manifest = manifest.model_copy(update={"source_language": source, "target_language": target,
        "phase": Phase.LANG_CONFIRMED, "last_successful_phase": Phase.LANG_CONFIRMED})
    write_json(store.directory(manifest.job_id) / "manifest.json", manifest.model_dump(mode="json"))
    context_path = store.directory(manifest.job_id) / "interaction_language.json"
    save_language_context(context_path, select_interaction_language(task_language=interaction))
    before = (store.directory(manifest.job_id) / "manifest.json").read_bytes()
    failed = manifest.model_copy(update={"phase": Phase.FAILED, "failed_stage": Phase.TRANSCRIBED,
                                         "error": "NETWORK_REQUEST_FAILED"})
    write_json(store.directory(manifest.job_id) / "manifest.json", failed.model_dump(mode="json"))
    args = cli.parser().parse_args(["status", "--job", manifest.job_id, "--runtime-root", str(tmp_path)])
    assert cli.interaction_context(args).language == interaction
    result, _ = cli.execute(args)
    assert result["manifest"]["source_language"] == source
    assert result["manifest"]["target_language"] == target
    # Changing only the interaction locale leaves failed state and video choices byte-identical.
    failed_bytes = (store.directory(manifest.job_id) / "manifest.json").read_bytes()
    save_language_context(context_path, select_interaction_language(explicit="fr-FR"))
    assert (store.directory(manifest.job_id) / "manifest.json").read_bytes() == failed_bytes
    assert cli.interaction_context(args).language == "fr-FR"
    assert video.read_bytes() == b"unchanged-source-fixture"


def test_chinese_api_error_cannot_change_interaction_language(tmp_path, monkeypatch, capsys):
    context_path = tmp_path / "interaction_language.json"
    save_language_context(context_path, select_interaction_language(task_language="pt-BR"))
    monkeypatch.setattr(cli, "execute", lambda args: ({"error": "NETWORK_REQUEST_FAILED", "message": "中文服务提示"}, 1))
    assert cli.main(["preflight", "--language-context", str(context_path)]) == 1
    assert load_language_context(context_path) == "pt-BR"


@pytest.mark.parametrize("interaction, source, target", [
    ("zh-CN", "en", "es"), ("en-US", "zh-CN", "ja"), ("pt-BR", "ja", "en"),
])
def test_cli_passes_media_language_choices_without_using_interaction_locale(tmp_path, monkeypatch, interaction, source, target):
    from video_translate.config import load_config
    from video_translate.state import JobStore
    video = tmp_path / "source.mp4"
    video.write_bytes(b"unchanged-source-fixture")
    store = JobStore(tmp_path)
    manifest = store.create(video, load_config(runtime_root=tmp_path).snapshot())
    save_language_context(store.directory(manifest.job_id) / "interaction_language.json",
                          select_interaction_language(task_language=interaction))
    seen = []
    def transcribe(store, job, config, media, actual_source, actual_target):
        seen.append((actual_source, actual_target))
        return manifest.model_copy(update={"source_language": actual_source, "target_language": actual_target})
    monkeypatch.setattr(cli, "transcribe_job", transcribe)
    args = cli.parser().parse_args(["transcribe", "--job", manifest.job_id, "--runtime-root", str(tmp_path),
                                   "--source", source, "--target", target])
    result, code = cli.execute(args)
    assert code == 0 and seen == [(source, target)]
    assert result["manifest"]["source_language"] == source
    assert result["manifest"]["target_language"] == target
    assert cli.interaction_context(args).language == interaction
