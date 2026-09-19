# AI providers

AI analysis is optional and never automatic. Choose one with `--provider <name>` or `--local`.

```
AIProvider (providers/base.py)
├── ClaudeProvider    official `anthropic` SDK
├── OpenAIProvider    REST (stdlib), also works with OpenAI-compatible servers via OPENAI_BASE_URL
├── GeminiProvider    REST (stdlib)
└── OllamaProvider    REST to a local Ollama server
```

| Provider | Credentials | Model env | Default model* |
|---|---|---|---|
| claude | `ANTHROPIC_API_KEY` | `ANTHROPIC_MODEL` | `claude-sonnet-5` |
| openai | `OPENAI_API_KEY` | `OPENAI_MODEL` | `gpt-4o-mini` |
| gemini | `GEMINI_API_KEY` or `GOOGLE_API_KEY` | `GEMINI_MODEL` | `gemini-2.5-flash` |
| ollama | none | `OLLAMA_MODEL` | `llama3.1` |

\* Defaults are starting points and may become outdated; pass `--model` or set the env var.

Keys are read only from environment variables, never from files or the command line, and never printed,
logged, or included in the payload. Error messages do not include request headers. Gemini's key is sent in a
header, not the URL.

## Behavior

- No key: `diagnose` warns and returns the rule-based report.
- Any provider failure (network, API error, unusable output) also degrades to the rule-based report.
- `--local` = Ollama, and refuses a non-loopback `OLLAMA_HOST`.
- Cloud providers show a summary and ask before sending; `--yes` skips the prompt; non-interactive sessions
  without `--yes` do not send.
- The same prompt and validation are used for every provider.

## Local models

Small local models often produce weaker or malformed JSON. Malformed output is rejected by validation rather
than shown. The request sets `num_ctx` from the prompt size so Ollama does not silently truncate the system
prompt. CPU-only machines may be slow; the default HTTP timeout for Ollama is 300 s.

## Adding a provider

Subclass `AIProvider`, set `name`/`default_model`, implement `complete(system, user) -> str`
(plus `is_configured()`/`config_help()` if it needs credentials), register it in `PROVIDERS`, and add tests with
a mocked transport (see `tests/unit/test_providers.py`).
