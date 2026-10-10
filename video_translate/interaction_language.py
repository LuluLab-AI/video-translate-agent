"""Agent-owned interaction language, independent of media and OS locale."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

from .files import read_json, write_json

# RFC 5646 syntax. This validates well-formedness, not IANA registration.
_TAG = re.compile(
    r"(?:[a-z]{2,3}(?:-[a-z]{3}){0,3}|[a-z]{4}|[a-z]{5,8})"
    r"(?:-[a-z]{4})?(?:-(?:[a-z]{2}|[0-9]{3}))?"
    r"(?:-(?:[a-z0-9]{5,8}|[0-9][a-z0-9]{3}))*"
    r"(?:-[0-9a-wy-z](?:-[a-z0-9]{2,8})+)*"
    r"(?:-x(?:-[a-z0-9]{1,8})+)?|x(?:-[a-z0-9]{1,8})+", re.I | re.ASCII,
)
_GRANDFATHERED = {
    "en-gb-oed", "i-ami", "i-bnn", "i-default", "i-enochian", "i-hak",
    "i-klingon", "i-lux", "i-mingo", "i-navajo", "i-pwn", "i-tao",
    "i-tay", "i-tsu", "sgn-be-fr", "sgn-be-nl", "sgn-ch-de", "art-lojban",
    "cel-gaulish", "no-bok", "no-nyn", "zh-guoyu", "zh-hakka", "zh-min",
    "zh-min-nan", "zh-xiang",
}


def normalize_language_tag(value: str) -> str:
    """Preserve any well-formed BCP-47 tag; no language allowlist or coercion."""
    if not isinstance(value, str):
        raise ValueError("INVALID_INTERACTION_LANGUAGE")
    tag = value.strip()
    if tag.lower() not in _GRANDFATHERED and not _TAG.fullmatch(tag):
        raise ValueError("INVALID_INTERACTION_LANGUAGE")
    # Repeated variants or extension singletons are forbidden by RFC 5646.
    parts = tag.lower().split("-")
    if parts[0] != "x" and tag.lower() not in _GRANDFATHERED:
        seen_variants, seen_extensions = set(), set()
        extension = False
        for part in parts[1:]:
            if part == "x":
                break
            if len(part) == 1:
                if part in seen_extensions:
                    raise ValueError("INVALID_INTERACTION_LANGUAGE")
                seen_extensions.add(part)
                extension = True
            elif not extension and (len(part) >= 5 or (len(part) == 4 and part[0].isdigit())):
                if part in seen_variants:
                    raise ValueError("INVALID_INTERACTION_LANGUAGE")
                seen_variants.add(part)
    return tag


@dataclass(frozen=True)
class InteractionLanguage:
    language: str
    source: str

    def as_dict(self) -> dict:
        return {"interactionLocale": self.language, "interactionLanguageSource": self.source}


def select_interaction_language(*, explicit: str | None = None,
                                task_language: str | None = None,
                                saved: str | None = None,
                                agent_default: str | None = None) -> InteractionLanguage:
    """Agent identifies task prose; number/asset/confirmation replies supply None."""
    for source, value in (("explicit", explicit), ("user_message", task_language),
                          ("saved_task", saved), ("agent_default", agent_default)):
        if value:
            return InteractionLanguage(normalize_language_tag(value), source)
    return InteractionLanguage("en", "fallback")


def load_language_context(path: Path | None) -> str | None:
    if path is None or not path.exists():
        return None
    record = read_json(path)
    if not isinstance(record, dict):
        raise ValueError("INVALID_LANGUAGE_CONTEXT")
    return normalize_language_tag(record.get("interactionLocale", record.get("interaction_language")))


def saved_reply_preference(path: Path | None) -> str | None:
    """Reuse a persisted explicit reply choice until the user replaces it."""
    if path is None or not path.exists():
        return None
    record = read_json(path)
    if isinstance(record, dict) and record.get("interactionLanguageSource", record.get("language_source")) == "explicit":
        return load_language_context(path)
    return None


def save_language_context(path: Path, context: InteractionLanguage) -> None:
    # Sidecar only: never modify manifests, language choices, media or policy payloads.
    write_json(path, context.as_dict())


class InteractionLanguageError(ValueError):
    """A stable, secret-free language/UI configuration error."""


def ui_catalog(language: str, catalog_path: Path | None = None) -> dict[str, str]:
    """Never change the selected language to fit the set of bundled catalogs."""
    from string import Formatter
    from .ui_catalogs import BUILTIN_TEXT
    language = normalize_language_tag(language)
    if catalog_path:
        record = read_json(catalog_path)
        if not isinstance(record, dict) or not isinstance(record.get("language"), str):
            raise InteractionLanguageError("INVALID_UI_CATALOG")
        if normalize_language_tag(record["language"]).lower() != language.lower():
            raise InteractionLanguageError("UI_CATALOG_LANGUAGE_MISMATCH")
        labels = record.get("messages")
    else:
        parts = language.lower().split("-")
        key = parts[0]
        if key == "zh":
            if "hant" in parts or ("hans" not in parts and any(p in parts for p in ("tw", "hk", "mo"))):
                key = "zh-Hant"
            elif any(len(p) == 4 and p.isalpha() and p != "hans" for p in parts[1:]):
                key = language  # Unknown script: require a matching catalog.
        labels = BUILTIN_TEXT.get(key)
    required = BUILTIN_TEXT["en"]
    if labels is None:
        raise InteractionLanguageError("UI_TRANSLATION_REQUIRED")
    if not isinstance(labels, dict) or set(labels) != set(required):
        raise InteractionLanguageError("INVALID_UI_CATALOG")
    for key, text in labels.items():
        if not isinstance(text, str) or not text.strip():
            raise InteractionLanguageError("INVALID_UI_CATALOG")
        allowed = {"link"} if key == "step_open" else ({"provider"} if key == "credential_prompt" else set())
        try:
            parsed = list(Formatter().parse(text))
        except ValueError:
            raise InteractionLanguageError("INVALID_UI_CATALOG") from None
        fields = {field for _, field, _, _ in parsed if field is not None}
        if fields != allowed or any(spec or conversion for _, _, spec, conversion in parsed):
            raise InteractionLanguageError("INVALID_UI_CATALOG")
    return dict(labels)


def text_direction(language: str) -> str:
    parts = normalize_language_tag(language).lower().split("-")
    script = next((p for p in parts[1:] if len(p) == 4 and p.isalpha()), None)
    if script:
        return "rtl" if script in {"arab", "hebr", "thaa", "nkoo", "adlm", "rohg", "syrc", "samr", "mand"} else "ltr"
    return "rtl" if parts[0] in {"ar", "he", "fa", "ur", "ps", "dv", "yi"} else "ltr"
