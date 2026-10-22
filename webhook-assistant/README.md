# Google Chat Assistant — Webhook Method (Path 1)

A lightweight Google Chat assistant that uses **Space Incoming Webhooks** for zero-friction outbound messaging, combined with a real-time space watcher for intelligent auto-replies.

---

## Key Characteristics

* **Attribution**: Messages appear with the creator's avatar and a custom badge:  
  `[Your Name] [Assistant Name]`
* **Scope**: Tied to a **single target space**.
* **Prerequisites**: No Google Workspace admin approval required. Works in any space where you can create webhooks.
* **Replies**: Can post as a new top-level message or reply inside the original thread.

---

## Quick Start

### 1. Create Webhook in Google Chat
1. Open your target Google Chat space.
2. Click Space Name header $\rightarrow$ **Apps & integrations** $\rightarrow$ **Manage webhooks** $\rightarrow$ **Add webhook**.
3. Set the name (e.g. `Team Assistant`) and save.
4. Copy the webhook URL.

### 2. Configure `.env`
```bash
cp .env.example .env
```
Fill in:
```env
GC_SPACE_NAME=spaces/YOUR_SPACE_ID
CHAT_WEBHOOK_URL=https://chat.googleapis.com/v1/spaces/YOUR_SPACE_ID/messages?key=...&token=...
LLM_API_KEY=your_api_key
```

### 3. Send a Message
```bash
python send.py "Hello team! Update from the assistant."
```

### 4. Run the 24/7 Listener
```bash
python listen.py
```

---

## Advanced Capabilities

* **Google Drive Integration**: Automatically creates documents, reports, and spreadsheets in your connected folder (`GOOGLE_DRIVE_FOLDER_ID`) and replies with direct clickable links.
* **Native File Attachments**: Reads and analyzes uploaded PowerPoint (`.pptx`, `.ppt`), Excel (`.xlsx`, `.xls`), PDF, and Word (`.docx`) files.
* **Progressive Acknowledgment**: Automatically sends a "Please wait..." message if tasks take >2s (configurable via `WAITING_MESSAGE`).
* **Persistent Memory**: Remembers thread conversation context across restarts.

---

## Docker & 24/7 VPS Deployment

```bash
# Pre-create state files
touch .thread_memory.json .permanent_facts.json

# Build and run with Docker Compose
docker compose up -d --build

# View live logs
docker compose logs -f
```

For full 24/7 cloud server deployment instructions, see [docs/vps-deployment-guide.md](../docs/vps-deployment-guide.md).

