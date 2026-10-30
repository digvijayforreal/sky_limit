# OmniAgent AI V1.2

Local-first personal AI: FastAPI, vanilla HTML/CSS/JS, Groq and Google AI Studio model APIs, SQLite chats, persistent API key storage, global/temporary explicit memory, web search and page extraction, and an approval-gated SMTP email tool.

## Windows setup (uv)

```powershell
uv venv .venv --python 3.12
uv pip install --python .venv/Scripts/python.exe -r requirements.txt
uv run --active uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
```

Open http://127.0.0.1:8000 for the landing page; `/workspace` is the chat UI.

## Project structure

```text
backend/
  api/          FastAPI application and endpoint routers
  core/         Shared paths, configuration, and application lifecycle
  repositories/ SQLite persistence for chats, memories, and saved API keys
  services/    Chat workflows and model-provider routing
  tools/        Email, web search/page extraction, and design integrations
  main.py       Uvicorn-compatible application entry point
frontend/       Browser interface
data/           Local SQLite databases
```

The existing launch command (`uvicorn backend.main:app`) remains supported. SQLite database files stay in `data/` at the project root.

## Migrating from V1

Keep your old `data/chats.db`! **Copy it into V1.2's `data/` folder with the server stopped**; conversations and messages will be preserved. If your database is in SQLite WAL mode, stop your server before moving it, and copy any corresponding `-wal`/`-shm` files if present. Use V1.2 folder as your project folder or copy the updated backend/frontend/requirements into the original project directory. Back up the original first.

## Groq and Google AI Studio keys

Create a Google AI Studio API key in [Google AI Studio](https://aistudio.google.com/apikey), then open **Engine Control > API Credentials**, choose **Google AI Studio**, paste the key, and connect it. OmniAgent validates the key and discovers models that support text generation, excluding image, audio, embedding, and other non-chat models. Gemini chat requests use Google's OpenAI-compatible API endpoint. Groq keys are added from the same form by choosing **Groq**. Search by provider or model name in the chat model search field; each entry identifies its provider so switching models uses the matching API and key. The failover test uses another key for that selected provider/model when available.

Enable **Save key on this computer** to restore keys on server restart. The local-only SQLite file `data/api_keys.db` contains keys **in plaintext**: do not share, commit, or back up to insecure locations. Uncheck saving for temporary keys. No API key is included in project files.

**Upgrade from V1.1:** its old `data/vault.db` cannot be decrypted without the previous master password and is left untouched. Existing Groq keys and conversations remain supported; the key databse adds a provider field with existing keys defaulting to Groq. Copy your old `data/chats.db` to keep conversations and explicitly saved memories.

## Memory

Each chat stores its own full transcript. The model only receives recent messages within a bounded budget. Under Engine Control > Memory, explicitly add global facts as permanent or expiring memories. These are included in prompts in new chats; memory is **not** automatically extracted from old conversation messages. You can delete memories in the dashboard.

## API usage

Engine Control shows successful provider requests handled by this app, reported input/output token totals, the latest response time per API key, and the 24-hour, 7-day, 30-day, or all-time totals. This local usage history is stored separately in `data/usage.db`; it does not include usage of the same key outside OmniAgent. Token totals appear only when the provider includes token counts. Groq request/token limits and reset details appear only when returned in response headers. Gemini does not provide a reliable remaining-quota value in these responses; check Google AI Studio for project quota.

## Web search and page extraction

When asked to research current information, the assistant can search the web and display source titles, URLs, and snippets in a structured results card. Configure an optional Tavily API key under **Engine Control > Web Search** to use Tavily; without it, the app uses the DDGS search library. Requests to inspect a public URL use the page extraction tool and show the page title, source, extracted text, and metadata. Scraping is limited to public HTTP/HTTPS pages on standard ports, rejects private/local addresses and redirects, and caps downloaded page size and displayed text. Tavily credentials are stored unencrypted in local `data/search_settings.db`.

## Email

Configure SMTP under **Engine Control > SMTP Email** (for example, port 587 with STARTTLS or port 465 with SSL/TLS). The assistant can prepare email drafts when asked, but sending always requires you to review the recipient, subject, and body and click **Approve & Send**. A preview can be cancelled without sending. SMTP settings, including the password, are stored unencrypted in the local-only `data/email_settings.db`; do not share or commit this file. Use an app password where your provider supports it. Removing the SMTP configuration disables the email tool.

## Live design assistant

Use the floating **Design Bot** in the workspace to request visual changes in plain language. It previews CSS changes on the current page immediately; click **Approve & Save** to keep them across visits, or **Discard** to restore the last saved design. **Reset Approved Design** removes all saved overrides. The assistant can change only allowlisted CSS properties on known workspace elements; it does not write source files, HTML, JavaScript, or execute generated code. Design instructions use the selected chat model and may incur provider API usage. If Google's OpenAI-compatible chat endpoint does not recognize a listed model, OmniAgent retries that request through Google's native `generateContent` endpoint; models unavailable there report a specific error so you can choose another model.

## Scope and limitations

- Backup test deliberately skips the first eligible key. Provider rate limits may apply.
- Model discovery depends on the selected provider's connectivity and API availability.
- Web Search requires network access. DDGS may be unavailable or rate-limited; a configured Tavily key uses Tavily instead.
- Email sending is SMTP-only; inbox reading, attachments, image analysis, semantic memory, login, and streaming are not supported.
- Local-only server middleware restricts remote access. Do not expose this application publicly without authentication, HTTPS, CSRF protections, and proper vault/session isolation.
