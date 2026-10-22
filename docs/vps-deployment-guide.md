# VPS 24/7 Deployment Guide

This comprehensive guide walks you through deploying your Google Chat Assistant to a Linux VPS (Virtual Private Server) such as **DigitalOcean, Hetzner, AWS EC2, Linode, Contabo, or Vultr** so it runs autonomously 24 hours a day, 7 days a week.

---

## Architecture Overview on VPS

```
┌─────────────────────────────────────────────────────────────┐
│ Linux VPS (Ubuntu 22.04 / 24.04 LTS)                        │
│                                                             │
│  ┌───────────────────────────────────────────────────────┐  │
│  │ Docker Engine / Systemd Service                       │  │
│  │                                                       │  │
│  │  gchat-oauth-assistant container (24/7 daemon)        │  │
│  │  ├── Space Listener (spaces.messages.list polling)   │  │
│  │  ├── Fireworks AI LLM Reasoning Engine               │  │
│  │  ├── Google Drive API Integration                     │  │
│  │  ├── Native PPTX / PDF / Excel Parser                 │  │
│  │  └── Silent Auto-Renewal Loop (~150ms token refresh)  │  │
│  └──────────────────────────┬────────────────────────────┘  │
│                             │ Volume Mounts                 │
│              ┌──────────────┴──────────────┐                │
│              ▼                             ▼                │
│       token.json (rw)             .thread_memory.json (rw)  │
│       credentials.json (ro)       .permanent_facts.json (rw)│
└─────────────────────────────────────────────────────────────┘
```

---

## Deployment Option A: Docker & Docker Compose (Recommended)

### Step 1: Install Docker on Your VPS

Connect to your VPS via SSH:
```bash
ssh root@YOUR_VPS_IP
```

Update your system and install Docker and Docker Compose plugin:
```bash
# 1. Update packages
apt update && apt upgrade -y

# 2. Install official Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sh get-docker.sh

# 3. Verify installation
docker --version
docker compose version

# 4. Enable Docker to start automatically on system boot
systemctl enable docker
```

---

### Step 2: Clone the Repository to the VPS

```bash
# Clone your repository
git clone https://github.com/YOUR_USERNAME/hermes-chat-assistant.git /opt/hermes-chat-assistant
cd /opt/hermes-chat-assistant/oauth-assistant
```

---

### Step 3: Configure Environment Variables

Create your `.env` file from the template:
```bash
cp .env.example .env
nano .env
```

Fill in your configuration:
```env
# Target Google Chat Space
GC_SPACE_NAME=spaces/YOUR_SPACE_ID

# Credentials & Token
CREDENTIALS_FILE=credentials.json
TOKEN_FILE=token.json

# Assistant Persona
BOT_NAME=Team Assistant
USER_ALIASES=assistant,agent,bot,abhay
BOT_USER_ID=users/YOUR_BOT_USER_ID
TRIGGER_MODE=smart
REPLY_IN_THREAD=false

# LLM Inference (Fireworks AI)
LLM_API_KEY=your_fireworks_api_key
LLM_BASE_URL=https://api.fireworks.ai/inference/v1
LLM_MODEL=accounts/fireworks/models/minimax-m3

# Google Drive Integration (Folder ID or URL)
GOOGLE_DRIVE_FOLDER_ID=your_google_drive_folder_id

# Progressive Acknowledgment
WAITING_MESSAGE=⏳ Please wait, let me check and prepare this for you...

# Performance
POLL_INTERVAL_SECONDS=2.0
MESSAGE_HISTORY_PAGE_SIZE=25
```

Save and exit in `nano` with `Ctrl + O`, `Enter`, then `Ctrl + X`.

---

### Step 4: Add Google Credentials & Authenticate

You have two easy ways to set up `credentials.json` and `token.json` on the VPS:

#### Choice 1: Transfer Existing Files from Local Machine (Fastest)
If you already authenticated locally and have `credentials.json` and `token.json`:
From your **local computer's terminal**:
```powershell
# In PowerShell / local terminal:
scp credentials.json token.json root@YOUR_VPS_IP:/opt/hermes-chat-assistant/oauth-assistant/
```

#### Choice 2: Run Headless Authentication Directly on the VPS over SSH
If starting fresh directly on the VPS:
1. Upload just `credentials.json`:
   ```powershell
   scp credentials.json root@YOUR_VPS_IP:/opt/hermes-chat-assistant/oauth-assistant/
   ```
2. On the VPS, run the headless authenticator:
   ```bash
   python3 -m pip install google-auth google-auth-oauthlib requests
   python3 auth.py
   ```
3. The script prints an authorization URL:
   ```
   >> OPEN THIS URL IN ANY BROWSER TO LOG IN:
   https://accounts.google.com/o/oauth2/auth?...
   ```
4. Open that URL on your laptop/phone, select your Google account, and click **Allow**.
5. When your browser tries to redirect to `http://localhost:8080/?code=4/0A...` and shows "This site can't be reached", **copy the full URL from the browser address bar**.
6. Paste the URL into the VPS terminal prompt:
   ```
   Paste redirect URL or Code: http://localhost:8080/?code=4/0A...
   ```
7. `token.json` is instantly generated on the VPS with a permanent refresh token!

---

### Step 5: Pre-create State Files for Docker

Ensure memory files exist on the host so Docker mounts them as files (not directories):
```bash
touch token.json .thread_memory.json .permanent_facts.json
```

---

### Step 6: Start the Assistant Daemon

Build and start the container in detached mode:
```bash
docker compose up -d --build
```

Verify that the assistant is running:
```bash
docker compose ps
```

View real-time streaming logs:
```bash
docker compose logs -f
```

You should see:
```text
INFO | Starting User-Delegated Space Listener...
INFO | Target Space: spaces/XXXXXXXXXXX
INFO | Live space sync loop active for spaces/XXXXXXXXXXX (every 2.0s)...
INFO | Assistant is monitoring messages...
```

---

## Deployment Option B: Native Systemd Service (Without Docker)

If you prefer running natively with Python and `systemd`:

### Step 1: Install Python & Create Virtualenv
```bash
apt update && apt install -y python3 python3-pip python3-venv git

cd /opt/hermes-chat-assistant/oauth-assistant
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### Step 2: Create a Systemd Service
Create the service unit file:
```bash
nano /etc/systemd/system/hermes-assistant.service
```

Paste the following definition:
```ini
[Unit]
Description=Hermes Google Chat Assistant Daemon
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/hermes-chat-assistant/oauth-assistant
EnvironmentFile=/opt/hermes-chat-assistant/oauth-assistant/.env
ExecStart=/opt/hermes-chat-assistant/oauth-assistant/.venv/bin/python listen.py
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

### Step 3: Enable and Start the Service
```bash
# Reload systemd
systemctl daemon-reload

# Enable service to start on every server boot
systemctl enable hermes-assistant

# Start the assistant service now
systemctl start hermes-assistant

# Check status
systemctl status hermes-assistant

# View live logs
journalctl -u hermes-assistant -f
```

---

## Maintenance & Common Operations

### How to Update the Code on VPS
Whenever you push updates to GitHub:
```bash
cd /opt/hermes-chat-assistant/oauth-assistant
git pull

# For Docker:
docker compose down
docker compose up -d --build

# For Systemd:
systemctl restart hermes-assistant
```

### Checking Bot Health & Logs
```bash
# Docker:
docker compose logs -f --tail=100

# Systemd:
journalctl -u hermes-assistant -f -n 100
```

### How the Permanent Token Refresh Works on VPS
The token file contains a permanent refresh token (`"refresh_token": "1//..."`). When the 1-hour access token expires:
1. `auth.py` automatically sends a renewal request to Google's OAuth endpoint.
2. Google returns a fresh access token in ~150ms.
3. The new token is written to `token.json` on the disk volume.
4. **No human login or browser interaction is ever needed again.**

---

## Security Best Practices for VPS

1. **Firewall (UFW)**: The assistant is an outbound polling client. It does not require any open inbound ports (like 80 or 443). You can keep your firewall locked down:
   ```bash
   ufw default deny incoming
   ufw default allow outgoing
   ufw allow ssh
   ufw enable
   ```
2. **File Permissions**: Keep credential files restricted:
   ```bash
   chmod 600 .env credentials.json token.json
   ```
3. **Internal OAuth Consent Screen**: In Google Cloud Console, ensure your OAuth consent screen is configured as **Internal** (Workspace) so refresh tokens never expire.
