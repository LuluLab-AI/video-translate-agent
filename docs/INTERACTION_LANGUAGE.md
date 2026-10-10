# Interaction language contract (v2.3.2)

The current Agent detects substantive task prose with its own model. The Python CLI does not inspect task media, API output, filenames or OS locale. Tags follow [BCP-47 / RFC 5646](https://www.rfc-editor.org/rfc/rfc5646) syntax; validation checks well-formedness, not IANA registration. No fixed language whitelist or new external service is used.

## Resolve and persist

Priority: explicit reply preference → current substantive user-message language → saved task language → Agent default reply language → `en`. Pass no `--task-language` for a number, an upload, a command-only reply or a simple confirmation. Keep an explicit reply preference active across turns until the user changes it in the saved context (an `explicit` source is reused at the highest priority). Pass a new `--reply-language` to replace it. These rules are identical in Codex, Claude Code and WorkBuddy.

```text
python <skill-root>/scripts/video_translate.py language-context --context-file <absolute-task-context-path> --task-language pt-BR --agent-language en-US --json
```

The optional `--reply-language` overrides all other signals. `--ui-language` is a backward-compatible alias for an already resolved selection. `--agent-language` supplies the Agent's default reply language, never a machine locale. If no message, saved context or default is available, the result is `en`.

The file contains only:

```json
{
  "interactionLocale": "pt-BR",
  "interactionLanguageSource": "user_message"
}
```

Source values: `explicit`, `user_message`, `saved_task`, `agent_default`, `fallback`. A legacy `interaction_language` field can be read for migration; new writes use the fields above. The media languages already exist as `source_language` and `target_language` in `manifest.json`: reuse them rather than adding duplicate source/target fields to the sidecar.

Use a task-local file before a job exists. Pass `--language-context <path>` to `create`; it copies the selected interaction language into `jobs/<id>/interaction_language.json`. After creation resolve future turns against that job file. Job commands load it automatically for human service messages; pass it explicitly to credential commands. Recovery keeps this file even in FAILED jobs. An explicit reply preference survives number/confirmation turns and substantive messages in another language until the user replaces that preference. Switching locale updates only this sidecar; never rewrite the manifest, media-language choices, subtitles, TTS, policy consent or caches.

```text
python <skill-root>/scripts/video_translate.py credential-setup --language-context <absolute-context-path> --json
python <skill-root>/scripts/video_translate.py credential-set --provider lululab --language-context <absolute-context-path> --json
```

`--ui-language <BCP-47-tag>` accepts any well-formed tag and overrides a saved context for that command. Omit it to reuse the task selection. An unknown tag is not converted to English. No `LC_ALL`, `LC_MESSAGES`, `LANG` or Python OS-locale detection is consulted.

## Local browser text

Complete catalogs are bundled for Chinese (Simplified and Traditional), English, Portuguese, Spanish, French, Japanese, Korean, Thai and Arabic. These are convenience catalogs, not an allowed-language list. Regional tags remain intact in the page's `lang` attribute. Arabic pages use right-to-left layout.

For another language, or a regional wording override, the current Agent generates a complete local catalog with its own model and passes `--ui-text <absolute-json-path>`. Read the English `BUILTIN_TEXT['en']` in `video_translate/ui_catalogs.py` as the semantic template; translate every value, preserve all keys, service names and technical scope identifiers, and preserve `{link}` and `{provider}` in their respective strings. This file contains only UI text, never API keys, media text or translations of video segments. No external translation API is used. JSON format:

```json
{
  "language": "de-DE",
  "messages": {
    "connect": "ElevenLabs verbinden"
  }
}
```

This example shows the envelope only; an actual catalog must contain **all** template keys, not just `connect`. Run local validation before opening the wizard:

```text
python -c "from pathlib import Path; from video_translate.interaction_language import ui_catalog; ui_catalog('de-DE', Path('<absolute-json-path>'))"
```

Use the skill's Python interpreter and package environment. Values are plain text, not HTML. The renderer escapes all text, and inserts only its own safe link in `{link}`. Partial catalogs, mismatched language tags or unexpected format fields fail with structured codes. Missing text for a selected language produces `UI_TRANSLATION_REQUIRED` before browser opening; the Agent supplies the complete catalog and resumes, without silently changing the locale or asking a new approval question.

## User-facing versus technical output

All human prose uses `interactionLocale`: startup, credentials, consent, input requests, language questions, subtitles/dubbing/options, confirmation, progress, errors, recovery and final delivery. Local credential prompts and browser errors use the same catalog. Existing workflows have only their existing checkpoints; this internationalization does not add subtitle, parameter or cleanup approvals.

CLI help, machine JSON, diagnostic logs, scope identifiers, error codes, paths and Node protocol parameters stay in their original technical form. The Agent explains technical failures in `interactionLocale` and retains the exact stable code, stage and relevant non-secret parameters/failure reason. Browser validation displays the translated explanation plus its stable error code. Do not hide failure causes or raw-code context to make a message look successful. Never disclose secrets or raw LuluLab account/billing responses. For languages without a local service-error catalog the CLI keeps the error code and stage; the Agent supplies the localized explanation from the saved context.

An API returning Chinese prose does not change `interactionLocale`. Reference-document language does not dictate output language. The source and target translation languages remain in the existing manifest and are passed unchanged to the existing workflow; neither is inferred from `interactionLocale`.
