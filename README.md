# OmniAgent AI V1.2

Local-first personal AI: FastAPI, vanilla HTML/CSS/JS, Groq API router, SQLite chats, persistent API key storage, global/temporary explicit memory, and an approval-gated SMTP email tool.

## Windows setup (uv)

```powershell
uv venv .venv --python 3.12
uv pip install --python .venv/Scripts/python.exe -r requirements.txt
uv run --active uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
```

Open http://127.0.0.1:8000 for the landing page; `/workspace` is the chat UI.

## Migrating from V1

Keep your old `data/chats.db`! **Copy it into V1.2's `data/` folder with the server stopped**; conversations and messages will be preserved. If your database is in SQLite WAL mode, stop your server before moving it, and copy any corresponding `-wal`/`-shm` files if present. Use V1.2 folder as your project folder or copy the updated backend/frontend/requirements into the original project directory. Back up the original first.

## Saved Groq keys (no master password)

Add API keys in **Engine Control**, with **Save key on this computer** checked. Keys automatically load when FastAPI starts again. The local-only SQLite file `data/api_keys.db` contains keys **in plaintext**: do not share, commit, or back up to insecure locations. For temporary keys, uncheck Save key before connecting. No API key is included in project files.

**Upgrade from V1.1:** its old `data/vault.db` cannot be decrypted without the previous master password and is left untouched. Add your Groq keys once again and they will then restore automatically. Copy your old `data/chats.db` to keep conversations and explicitly saved memories.

## Memory

Each chat stores its own full transcript. The model only receives recent messages within a bounded budget. Under Engine Control > Memory, explicitly add global facts as permanent or expiring memories. These are included in prompts in new chats; memory is **not** automatically extracted from old conversation messages. You can delete memories in the dashboard.

## Email

Configure SMTP under **Engine Control > SMTP Email** (for example, port 587 with STARTTLS or port 465 with SSL/TLS). The assistant can prepare email drafts when asked, but sending always requires you to review the recipient, subject, and body and click **Approve & Send**. A preview can be cancelled without sending. SMTP settings, including the password, are stored unencrypted in the local-only `data/email_settings.db`; do not share or commit this file. Use an app password where your provider supports it. Removing the SMTP configuration disables the email tool.

## Scope and limitations

- Backup test deliberately skips the first eligible key. Groq organization-level rate limits may apply to both keys.
- Model discovery depends on Groq connectivity.
- Email sending is SMTP-only; inbox reading, attachments, image analysis, semantic memory, login, and streaming are not supported.
- Local-only server middleware restricts remote access. Do not expose this application publicly without authentication, HTTPS, CSRF protections, and proper vault/session isolation.
