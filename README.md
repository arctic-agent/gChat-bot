# Google Chat Autonomous Assistant Platform

An enterprise-ready, multi-path platform for building and deploying automated Google Chat assistants that post with custom user-attributed identity badges:

$$\mathbf{\text{[User Display Name]}} \quad \mathbf{\text{[Assistant Badge]}}$$

This repository provides two complete, production-ready implementation paths:
1. **`webhook-assistant/` (Path 1 — Incoming Webhook Method)**: Quick, zero-OAuth setup for monitoring and messaging within a single space.
2. **`oauth-assistant/` (Path 2 — User-Delegated OAuth Method)**: Universal, multi-space setup that acts on behalf of a human user across all spaces, group chats, and direct messages without webhooks or bot invitations.

---

## Architecture Comparison

| Feature | Path 1: Webhook Method (`webhook-assistant/`) | Path 2: User-Delegated OAuth (`oauth-assistant/`) |
| :--- | :--- | :--- |
| **Identity Display** | `[Creator Name] [Webhook Name]` | `[User Name] [GCP App Name]` |
| **Scope** | Single Space (tied to webhook URL) | **Universal** (all spaces/DMs user belongs to) |
| **GCP Setup Required** | None for messaging | Yes (OAuth Client + Chat API App Name) |
| **Space Administration** | Requires permission to add webhooks | **Zero** space administration needed |
| **Token Expiry** | Never expires (static URL) | Permanent silent refresh (~150ms renewal) |
| **Outbound Messaging** | HTTP POST to webhook URL | Chat REST API with Bearer token |
| **Multi-Space Discovery** | Manual per space | Automatic via `spaces.list` API |
| **Containerization** | Docker & Compose ready | Docker & Compose ready (with volume sync) |

---

## Directory Structure

```
hermes-chat-assistant/
├── docs/
│   ├── vps-deployment-guide.md     # Complete step-by-step 24/7 VPS deployment guide
│   ├── user-oauth-method.md        # Deep dive into user-delegated OAuth & token renewal
│   └── webhook-method.md           # Deep dive into incoming webhook architecture
│
├── webhook-assistant/              # PATH 1: Single-space Webhook Implementation
│   ├── .env.example
│   ├── config.py
│   ├── drive_manager.py            # Google Drive API manager (create docs, sheets, files)
│   ├── file_reader.py              # Native parser for PPTX, XLSX, PDF, DOCX, CSV
│   ├── memory.py                   # Persistent thread memory & learned facts
│   ├── messenger.py                # Posts messages via webhook
│   ├── tools.py                    # Hermes Agent tools (Drive, web, facts, python)
│   ├── agent.py                    # Multi-turn LLM agent with progressive status & context
│   ├── listen.py                   # 24/7 background space listener
│   ├── send.py                     # CLI tool to post top-level messages
│   ├── requirements.txt
│   ├── Dockerfile
│   ├── docker-compose.yml
│   └── README.md
│
├── oauth-assistant/                # PATH 2: Universal Multi-space OAuth Implementation
│   ├── .env.example
│   ├── config.py
│   ├── auth.py                     # Headless OAuth authenticator with PKCE & silent refresh
│   ├── drive_manager.py            # Google Drive API manager (create docs, sheets, files)
│   ├── file_reader.py              # Native parser for PPTX, XLSX, PDF, DOCX, CSV
│   ├── memory.py                   # Persistent thread memory & learned facts
│   ├── messenger.py                # Posts via spaces.messages.create as user
│   ├── tools.py                    # Hermes Agent tools (Drive, web, facts, python)
│   ├── agent.py                    # Multi-turn LLM agent with progressive status & context
│   ├── listen.py                   # Multi-space listener with silent token refresh
│   ├── send.py                     # Universal sender (CLI, multi-space, list spaces)
│   ├── requirements.txt
│   ├── Dockerfile
│   ├── docker-compose.yml
│   └── README.md
│
├── .gitignore                      # Strict, leak-proof secret exclusions
└── README.md                       # Master platform documentation
```

---

## Hermes Agent Intelligence & Engine Capabilities

Both paths integrate the **Hermes Autonomous Agent Engine**:

1. **Selective Activation (Zero Spam)**:
   * **Only triggers** when called, mentioned, or replying:
     * Google Chat user mentions (`<users/...>`)
     * Explicit `@` tags (e.g. `@Assistant`, `@BotName`)
     * Direct name calls (e.g. *"Assistant, can you..."*, *"Hey Alex..."*)
     * In-thread follow-up replies in active assistant discussions
   * **Stays completely silent** (`NO_REPLY`) for casual banter or conversations between other teammates.

2. **Progressive "Please Wait" Acknowledgment**:
   * If an inquiry takes longer than 2.0s (downloading large PPTX/PDF presentations, multi-turn reasoning, or Google Drive uploads), the bot immediately posts:
     `"⏳ Please wait, let me check and prepare this for you..."`
   * Once finished, it delivers the complete answer or file link. Quick answers (<2s) deliver directly without status clutter.

3. **Google Drive Integration**:
   * Autonomous file and document creation inside your designated Google Drive folder (`GOOGLE_DRIVE_FOLDER_ID`).
   * Converts markdown/text to interactive **Google Docs** and CSV to native **Google Sheets**.
   * Automatically configures link permissions and returns clickable direct web links (`webViewLink`) in chat.

4. **Native Multi-Format File Reader**:
   * Directly extracts and analyzes attachments uploaded to the space:
     * PowerPoint (`.pptx`, `.ppt` slide-by-slide)
     * Excel (`.xlsx`, `.xls` multi-sheet tables)
     * PDF documents
     * Word (`.docx`), CSV, JSON, code, and text files.

5. **Permanent Memory & Learned Knowledge**:
   * Remembers thread history across restarts (`.thread_memory.json`).
   * Retains user preferences and project facts permanently via `remember_fact` (`.permanent_facts.json`).

6. **Executable Agent Tools**:
   * `create_drive_file(filename, content, convert_to_google_doc)`: Creates and uploads files/docs directly to Drive.
   * `list_drive_files()`: Lists files in the connected Drive folder.
   * `fetch_webpage(url)`: Reads and extracts text from documentation or links shared in chat.
   * `search_facts(query)`: Instant facts, technical lookups, and definitions.
   * `run_python(code)`: Real-time math calculations, data manipulation, and table processing.
   * `remember_fact(key, value)`: Stores critical facts in permanent memory.

---

## Which Path Should You Choose?

```
Do you only need to monitor and post into ONE specific space?
  ├── YES ──► Use Path 1 (webhook-assistant/)
  │           • Takes 30 seconds to set up.
  │           • Requires no GCP OAuth configuration.
  │           • Webhook URL never expires.
  │
  └── NO  ──► Use Path 2 (oauth-assistant/)
              • Operates across all 20+ spaces and DMs you belong to.
              • No webhooks or bot invitations needed in any space.
              • Authenticate once headlessly; runs forever via silent refresh.
```

---

## Getting Started: Path 1 (Webhook Method)

### 1. Generate Webhook in Google Chat
1. Navigate to your target space $\rightarrow$ Click space name $\rightarrow$ **Apps & integrations** $\rightarrow$ **Manage webhooks**.
2. Click **Add webhook**, give it a name (e.g. `Release Assistant`), and copy the URL.

### 2. Configure & Run
```bash
cd webhook-assistant
cp .env.example .env

# Edit .env with your CHAT_WEBHOOK_URL and LLM_API_KEY
python send.py "Hello from Webhook Assistant!"

# Launch continuous space monitor
python listen.py
```

*For detailed instructions, see [docs/webhook-method.md](docs/webhook-method.md).*

---

## Getting Started: Path 2 (User-Delegated OAuth Method)

### 1. One-Time Google Cloud Setup
1. In [Google Cloud Console](https://console.cloud.google.com/), enable the **Google Chat API**.
2. In **Google Chat API $\rightarrow$ Configuration**, enter your **App Name** (e.g. `Team Assistant`). This is the badge that appears in Google Chat.
3. In **APIs & Services $\rightarrow$ OAuth consent screen**, set User Type to **Internal** (for permanent refresh tokens).
4. In **Credentials**, create an **OAuth client ID** of type **Desktop app** and download it as `credentials.json`.

### 2. Configure & Authenticate Headlessly
```bash
cd oauth-assistant
cp .env.example .env
cp /path/to/credentials.json .

# Run one-time browserless authentication
python auth.py
```
Open the generated link in any web browser, click **Allow**, and `token.json` will be saved with a permanent refresh token.

### 3. Send & Listen Across Any Space
```bash
# List all spaces you are in
python send.py --list-spaces

# Send to any space without webhooks
python send.py --space spaces/YOUR_SPACE_ID "Automated update"

# Run 24/7 listener with silent token auto-refresh
python listen.py --space spaces/YOUR_SPACE_ID
```

*For detailed instructions, see [docs/user-oauth-method.md](docs/user-oauth-method.md).*

---

---

## 24/7 VPS Cloud Deployment

For deploying the assistant 24/7 on a cloud VPS (Ubuntu, Debian, DigitalOcean, Hetzner, AWS EC2, Linode, Contabo, etc.):

👉 **See the complete step-by-step guide: [docs/vps-deployment-guide.md](docs/vps-deployment-guide.md)**

It covers:
* Installing Docker & Docker Compose on Ubuntu.
* Headless OAuth verification over SSH (no local browser needed on the VPS).
* Persistent volume storage for `token.json`, thread memories, and facts.
* Running with system auto-start on server reboot (`restart: unless-stopped` or `systemd`).
* Silent ~150ms token auto-renewal running permanently in the background.

---

## Docker Deployment (Local or Server)

Both paths include production-ready Docker configurations.

### Deploying Path 1 (Webhook Container)
```bash
cd webhook-assistant
docker compose up -d
docker compose logs -f
```

### Deploying Path 2 (OAuth Container with Auto-Refresh)
```bash
cd oauth-assistant
# Ensure token.json exists before starting
docker compose up -d
docker compose logs -f
```
The volume mounts in `docker-compose.yml` ensure that when the container silently refreshes tokens in the background, the updated `token.json` and conversation memories persist seamlessly across container restarts.

---

## Security & Best Practices

1. **Secret Isolation**: Never commit `.env`, `credentials.json`, `token.json`, or service account keys. The included [`.gitignore`](.gitignore) strictly enforces exclusion of all token, credential, and environment files.
2. **Infinite Loop Safeguards**: Both paths include message hashing and sender-name detection to guarantee that the assistant never responds to its own outputs.
3. **Workspace Session Policies**: For Path 2, keeping the OAuth Consent Screen set to **Internal** ensures that refresh tokens remain valid indefinitely without 7-day timeouts.
4. **Firewall Security**: The assistant operates strictly via outbound polling and webhook calls. No inbound ports (like 80 or 443) need to be open on your VPS firewall.

