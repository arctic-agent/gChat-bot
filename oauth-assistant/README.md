# Google Chat Assistant — User-Delegated OAuth Method (Path 2)

An enterprise-grade Google Chat assistant that acts under your **human user OAuth identity**, allowing it to post and listen across **any space, group chat, or DM** you belong to without installing webhooks or inviting bots.

---

## Key Characteristics

* **Attribution**: Messages appear with your personal profile avatar and your GCP App badge:  
  `[Your Name] [App Name]`
* **Universal Scope**: Works in **any space or DM** you belong to.
* **No Webhooks / No Invited Bots**: Operates via standard Google Chat user permissions.
* **Silent Auto-Refresh**: Uses a permanent refresh token (`1//...`) that renews expired access tokens in ~150ms without ever prompting you again.

---

## Quick Start

### 1. Configure the Chat App in Google Cloud Console
1. Open [Google Cloud Console](https://console.cloud.google.com/) $\rightarrow$ Select your project.
2. Search for **Google Chat API** $\rightarrow$ Click **Configuration**.
3. Set **App Name** (e.g. `Team Assistant`) $\rightarrow$ This is the badge that appears next to your name.
4. Set **Visibility** to your domain or user group $\rightarrow$ Click **Save**.

### 2. Download OAuth Client Credentials
1. Navigate to **APIs & Services $\rightarrow$ Credentials**.
2. Create an **OAuth Client ID** of type **Desktop app**.
3. Download the JSON file, rename it to `credentials.json`, and place it in this directory.

### 3. Run One-Time Browserless Authentication
```bash
python auth.py
```
* Open the printed URL in any web browser.
* Click **Allow**.
* The script catches the authorization redirect automatically and saves `token.json`.

### 4. List Your Accessible Spaces
```bash
python send.py --list-spaces
```

### 5. Send a Message to Any Space
```bash
python send.py --space spaces/YOUR_SPACE_ID "Hello team! Update from the assistant."
```

### 6. Run the 24/7 Listener
```bash
python listen.py --space spaces/YOUR_SPACE_ID
```

---

## Google Drive Integration

You can connect a designated Google Drive folder so the assistant can automatically create files, documents, reports, and spreadsheets, upload them directly to your folder, and post direct access links in chat.

### 1. Enable Google Drive API
1. In [Google Cloud Console](https://console.cloud.google.com/), go to **APIs & Services $\rightarrow$ Library**.
2. Search for **Google Drive API** and click **Enable**.

### 2. Configure Folder ID in `.env`
Open your Google Drive folder in a browser:
`https://drive.google.com/drive/folders/1abcXYZ123456789...`

Copy either the folder ID (`1abcXYZ123456789...`) or the entire URL into your `.env` file:
```env
GOOGLE_DRIVE_FOLDER_ID=1abcXYZ123456789...
```

### 3. Grant Drive Permissions
Run the one-time authentication script to grant the `drive.file` scope:
```bash
python auth.py
```
*(Note: `drive.file` scope only grants access to files created or opened by the assistant, keeping the rest of your personal Drive private and secure).*

### 4. How the Assistant Uses Drive
* When users in Google Chat ask for summaries, reports, proposals, or exports (e.g. *"Create a proposal summary doc and put it in our drive"*), Hermes automatically formats the content, uploads it to your folder, sets share permissions, and provides the direct clickable link in chat.
* Team members can ask *"List files in our drive"* to view existing files and access links.

---

---

## Advanced Capabilities

### 1. Progressive Acknowledgment ("Please Wait...")
If an inquiry takes more than 2.0 seconds (e.g. downloading attachments, parsing multi-slide decks, or creating Google Drive spreadsheets), Hermes immediately sends:
`"⏳ Please wait, let me check and prepare this for you..."`
Once finished, it delivers the answer/link. Fast answers (<2s) deliver immediately without status messages.
Configurable in `.env`:
```env
WAITING_MESSAGE=⏳ Please wait, let me check and prepare this for you...
```

### 2. Native Multi-Format File Attachments
Hermes natively extracts and analyzes space attachments directly in chat:
* **PowerPoint** (`.pptx`, `.ppt` slide-by-slide)
* **Excel** (`.xlsx`, `.xls` multi-sheet tables)
* **PDF** documents
* **Word** (`.docx`), CSV, JSON, code, and text files.

---

## Docker & 24/7 VPS Deployment

### Local Docker
Ensure `token.json` exists before starting the container:
```bash
touch token.json .thread_memory.json .permanent_facts.json

# Build and run container with auto-refresh and memory persistence
docker compose up -d --build

# Check live logs
docker compose logs -f
```

### 24/7 Cloud VPS Deployment
To run the assistant 24/7 on an Ubuntu/Debian cloud server (DigitalOcean, Hetzner, AWS EC2, Linode, Contabo):
👉 **Follow the full guide in [docs/vps-deployment-guide.md](../docs/vps-deployment-guide.md)**


