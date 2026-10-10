from html import unescape
import re
import threading
from types import SimpleNamespace as NS
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pytest

from video_translate import credential_setup


class Session:
    def request(self, _method, url, **_kwargs):
        payload = ([{"model_id": "eleven_multilingual_v2"}]
                   if url.endswith("/models") else {"voices": [{"voice_id": "v1", "name": "Voice"}]})
        return NS(status_code=200, json=lambda: payload)


def _start(monkeypatch, *, opener=lambda *_args, **_kwargs: True, session=None, timeout=3, ui_language="zh"):
    urls, stored, outcome = [], [], {}

    def open_url(url, **_kwargs):
        urls.append(url)
        return opener(url)

    monkeypatch.setattr(credential_setup.webbrowser, "open", open_url)
    monkeypatch.setattr(credential_setup, "store_credential_value",
                        lambda provider, value: stored.append((provider, value)))

    def run():
        try:
            outcome["result"] = credential_setup.run_credential_setup(
                timeout_seconds=timeout, session=session or Session(), ui_language=ui_language)
        except Exception as exc:
            outcome["error"] = str(exc)

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    for _ in range(100):
        local = next((url for url in urls if url.startswith("http://127.0.0.1:")), None)
        if local:
            return thread, local, stored, outcome
        threading.Event().wait(0.01)
    pytest.fail("wizard URL was not opened")


def _csrf(local_url):
    with urlopen(local_url, timeout=2) as response:
        body = response.read().decode()
        assert response.headers["Cache-Control"].startswith("no-store")
        assert "default-src 'none'" in response.headers["Content-Security-Policy"]
    return unescape(re.search(r'name="csrf" value="([^"]+)"', body).group(1))


def _post(local_url, fields, **headers):
    data = urlencode(fields).encode()
    return urlopen(Request(local_url, data=data, headers=headers), timeout=2)


@pytest.mark.parametrize("ui_language, success_text", [("zh", "连接成功"), ("en", "Connected successfully")])
def test_success_validates_before_store_and_never_prints_secret(monkeypatch, capsys, ui_language, success_text):
    secret = "private-browser-key"
    thread, url, stored, outcome = _start(monkeypatch, ui_language=ui_language)
    with urlopen(url, timeout=2) as response:
        page = response.read().decode()
        assert f'lang="{ui_language}"' in page
        assert ("连接 ElevenLabs" if ui_language == "zh" else "Connect ElevenLabs") in page
    csrf = _csrf(url)
    with _post(url, {"csrf": csrf, "action": "connect", "api_key": secret}) as response:
        assert success_text in response.read().decode()
    thread.join(2)
    assert outcome["result"] == {"provider": "elevenlabs", "stored": True,
                                  "access_verified": True,
                                  "storage": credential_setup.credential_storage_name()}
    assert stored == [("elevenlabs", secret)]
    captured = capsys.readouterr()
    assert secret not in captured.out + captured.err


def test_bad_csrf_is_rejected_without_storing(monkeypatch):
    secret = "private-browser-key"
    thread, url, stored, outcome = _start(monkeypatch)
    csrf = _csrf(url)
    with pytest.raises(HTTPError) as error:
        _post(url, {"csrf": "wrong", "action": "connect", "api_key": secret})
    assert error.value.code == 403
    with _post(url, {"csrf": csrf, "action": "cancel"}):
        pass
    thread.join(2)
    assert outcome["error"] == "CREDENTIAL_SETUP_CANCELLED"
    assert stored == []


def test_oversized_request_and_wrong_host_are_rejected(monkeypatch):
    secret = "host-check-key"
    thread, url, stored, outcome = _start(monkeypatch)
    csrf = _csrf(url)
    with pytest.raises(HTTPError) as error:
        _post(url, {"csrf": csrf, "api_key": "x" * credential_setup.MAX_REQUEST_BYTES})
    assert error.value.code == 413
    with pytest.raises(HTTPError) as error:
        _post(url, {"csrf": csrf, "action": "connect", "api_key": secret}, Host="localhost")
    assert error.value.code == 404
    with _post(url, {"csrf": csrf, "action": "cancel"}):
        pass
    thread.join(2)
    assert stored == [] and outcome["error"] == "CREDENTIAL_SETUP_CANCELLED"


@pytest.mark.parametrize("status", [401, 403, 429])
def test_remote_failures_do_not_store(monkeypatch, status):
    secret = "private-browser-key"
    class FailedSession:
        def request(self, *_args, **_kwargs):
            return NS(status_code=status)

    thread, url, stored, outcome = _start(monkeypatch, session=FailedSession(), timeout=1)
    csrf = _csrf(url)
    with pytest.raises(HTTPError) as error:
        _post(url, {"csrf": csrf, "action": "connect", "api_key": secret})
    assert error.value.code == 400
    thread.join(2)
    assert stored == [] and outcome["error"] == "CREDENTIAL_SETUP_TIMEOUT"


def test_browser_failure_emits_safe_fallback_url(monkeypatch, capsys):
    thread, url, _stored, outcome = _start(monkeypatch, opener=lambda _url: False)
    csrf = _csrf(url)
    with _post(url, {"csrf": csrf, "action": "cancel"}):
        pass
    thread.join(2)
    diagnostic = capsys.readouterr().err
    assert "BROWSER_OPEN_FAILED" in diagnostic and url in diagnostic
    assert outcome["error"] == "CREDENTIAL_SETUP_CANCELLED"


@pytest.mark.parametrize("value", ["zh-CN", "en-US", "pt-BR", "es-ES", "fr-FR", "ja-JP", "ko-KR", "th-TH", "ar-SA", "de-DE", "x-local"])
def test_bcp47_tags_preserved_without_os_locale(monkeypatch, value):
    monkeypatch.setenv("LC_ALL", "zh_CN.UTF-8")
    monkeypatch.setenv("LANG", "ja_JP.UTF-8")
    assert credential_setup.resolve_ui_language(value) == value
    assert credential_setup.resolve_ui_language() == "en"


def test_english_validation_and_cancel_pages(monkeypatch):
    thread, url, stored, outcome = _start(monkeypatch, ui_language="en")
    csrf = _csrf(url)
    with pytest.raises(HTTPError) as error:
        _post(url, {"csrf": csrf, "action": "connect", "api_key": ""})
    page = error.value.read().decode()
    assert "Please enter your ElevenLabs API Key." in page
    assert "请输入" not in page
    with _post(url, {"csrf": csrf, "action": "cancel"}) as response:
        assert "No API key was saved." in response.read().decode()
    thread.join(2)
    assert stored == [] and outcome["error"] == "CREDENTIAL_SETUP_CANCELLED"


def test_cli_passes_agent_ui_language(monkeypatch):
    from video_translate import cli
    received = {}
    def setup(**kwargs):
        received.update(kwargs)
        return {"stored": True}
    monkeypatch.setattr(cli, "run_credential_setup", setup)
    result, code = cli.execute(cli.parser().parse_args([
        "credential-setup", "--ui-language", "ja-JP", "--json",
    ]))
    assert code == 0 and result == {"stored": True}
    assert received["ui_language"] == "ja-JP"


@pytest.mark.parametrize("language, expected", [
    ("pt-BR", "Conexão concluída"), ("es-ES", "Conexión correcta"),
    ("fr-FR", "Connexion réussie"), ("ja-JP", "接続しました"),
    ("ko-KR", "연결 완료"), ("th-TH", "เชื่อมต่อสำเร็จ"),
    ("ar-SA", "تم الاتصال بنجاح"), ("zh-TW", "連接成功"),
])
def test_multilingual_wizard_success(monkeypatch, language, expected):
    thread, url, stored, outcome = _start(monkeypatch, ui_language=language)
    with urlopen(url, timeout=2) as response:
        body = response.read().decode()
        assert f'lang="{language}"' in body
        assert 'dir="rtl"' in body if language == "ar-SA" else 'dir="ltr"' in body
    csrf = _csrf(url)
    with _post(url, {"csrf": csrf, "action": "connect", "api_key": "fixture-key"}) as response:
        assert expected in response.read().decode()
    thread.join(2)
    assert outcome["result"]["stored"] is True


@pytest.mark.parametrize("language", ["pt-BR", "es-ES", "fr-FR", "ja-JP", "ko-KR", "th-TH", "ar-SA"])
def test_all_wizard_error_paths_use_selected_language(monkeypatch, language):
    from video_translate.interaction_language import ui_catalog
    labels = ui_catalog(language)
    class FailedSession:
        def request(self, *_args, **_kwargs):
            return NS(status_code=401)
    thread, url, stored, outcome = _start(monkeypatch, ui_language=language, session=FailedSession())
    csrf = _csrf(url)
    for fields, expected in [
        ({"csrf": "wrong", "action": "connect"}, labels["forbidden"]),
        ({"csrf": csrf, "action": "connect", "api_key": ""}, labels["empty"]),
        ({"csrf": csrf, "action": "connect", "api_key": "fixture-key"}, labels["CREDENTIAL_PERMISSION_INSUFFICIENT"]),
    ]:
        with pytest.raises(HTTPError) as error:
            _post(url, fields)
        assert expected in unescape(error.value.read().decode())
    with _post(url, {"csrf": csrf, "action": "cancel"}) as response:
        assert labels["cancel_detail"] in unescape(response.read().decode())
    thread.join(2)
    assert not stored and outcome["error"] == "CREDENTIAL_SETUP_CANCELLED"
