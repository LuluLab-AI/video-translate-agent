# Changelog

## 2.4.0 — 2026-10-10 (release candidate)

- Combine the local Node.js CLI and multilingual changes with bilingual GitHub installation documentation.
- Make the source release include the Node.js client and both READMEs while omitting runtime STTN weights.
- Preserve GPL-3.0-only licensing, policy workflows, media algorithms and task recovery.

## 2.3.2 — 2026-10-10

- Resolve interaction language from explicit reply preference, current user task language, saved task context, Agent default, then English. Remove OS-locale fallback and non-Chinese-to-English coercion.
- Preserve BCP-47 tags and persist `interactionLocale` / `interactionLanguageSource` in a task sidecar, independently of existing source/target media language fields.
- Add complete multilingual credential UI catalogs, Arabic RTL layout and validated Agent-generated catalogs for any additional language. Preserve structured credential failure codes alongside localized explanations.
- Reuse the task context for credential guidance, service errors, retries, recovery and final delivery.
- Add multilingual, media-language independence and actual Node-subprocess/local-HTTP-mock regression coverage.
- Retain existing LuluLab Node client, raw-key stdin transport, VideoTranslatePolicyV1 submit/poll/cache behavior and all media algorithms. Distributed ZIP continues to omit STTN model weights.
