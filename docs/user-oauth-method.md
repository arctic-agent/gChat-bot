# Deep Dive: User-Delegated OAuth Architecture (Path 2)

This document explains the technical architecture of building a **Universal Google Chat Assistant** that operates under a human user's OAuth 2.0 identity without requiring space-by-space webhooks or installed bots.

---

## 1. How User-Delegated Attribution Works

Google Chat allows calling the `spaces.messages.create` REST API method using **User Credentials** (an OAuth 2.0 access token issued to a human user account).

```
   [ User OAuth Token: Jane Doe ] + [ GCP Chat API Config: "Release Assistant" ]
                                  │
                                  ▼
      Rendered UI: Jane Doe [Release Assistant] (with Jane's Google avatar)
```

### The Attribution Formula
* **Author Identity**: Google Chat inspects the `Authorization: Bearer <user_token>` header. The author is identified as the authenticated human user.
* **Badge Chip**: Google Chat inspects the OAuth Client's parent Google Cloud project. If the **Google Chat API** is configured in that project with an **App Name**, that name is displayed in the badge pill.
* **Permissions**: Because the authenticated entity is the human user, **no bot needs to be installed into the space**. As long as the user is already a member of the space, group chat, or DM, message creation succeeds immediately.

---

## 2. Token Lifecycle & The Silent Refresh Protocol

OAuth 2.0 access tokens expire after **60 minutes (3,600 seconds)**. Rather than forcing the user to log in through the browser repeatedly, the system uses a **Refresh Token**:

```
Initial One-Time Setup:
  InstalledAppFlow (access_type='offline', prompt='consent')
          │
          ▼
    token.json:
    ├── access_token (Valid for 1 hour)
    └── refresh_token (Permanent secret key: 1//04...)

Runtime Loop (Every API Request):
  1. Check token.json expiry timestamp
  2. If expired:
     POST https://oauth2.googleapis.com/token
     Body: refresh_token + client_id + client_secret
     (Takes ~150ms over TLS — zero user interruption)
  3. Overwrite token.json with new 1-hour access_token
  4. Dispatch Chat API request with fresh Bearer token
```

---

## 3. Crucial GCP Configuration: Internal vs. External

In the Google Cloud Console (**APIs & Services $\rightarrow$ OAuth consent screen**), the **User Type** setting is critical:

| Setting | Token Expiration Behavior | Best For |
| :--- | :--- | :--- |
| **Internal** (Workspace) | **Never expires**. Refresh token remains valid permanently until explicitly revoked. | Company Google Workspace domains (`@yourcompany.com`) |
| **External** ("Testing") | **Expires after 7 days**. User must re-authenticate every week. | Testing with `@gmail.com` personal accounts |
| **External** ("In Production") | **Never expires**, but requires Google OAuth verification if sensitive scopes are used. | Public consumer applications |

> **Recommendation**: For internal company tools, always select **Internal**.

---

## 4. Headless & Remote Authentication

For servers, Docker containers, and remote SSH environments where an automatic browser popup is impossible, the authentication script uses a **Dual-Mode Headless Listener**:

1. **Local Background Listener**: Binds to `http://localhost:8080/`. If the user opens the authorization URL on the local machine, the redirect is captured automatically upon consent.
2. **Manual Paste Fallback**: If the user approves the prompt on a separate device (e.g. mobile phone or laptop), they can copy the redirected localhost URL containing `code=4/0A...` and paste it directly into the terminal prompt.
3. The script exchanges the authorization code for tokens using PKCE verification and writes `token.json`.

---

## 5. Multi-Space Discovery & Dispatch

Because the user token inherits all space memberships of the user, the assistant can discover and post to any space dynamically:

```python
# 1. Discover all spaces the user belongs to
GET https://chat.googleapis.com/v1/spaces?pageSize=100
Authorization: Bearer <user_token>

# 2. Post to any discovered space ID
POST https://chat.googleapis.com/v1/spaces/{ANY_SPACE_ID}/messages
Authorization: Bearer <user_token>
{
  "text": "Your automated update across spaces."
}
```

---

## 6. Advantages & Limitations

### Advantages
* **Universal Access**: Works across all spaces, group chats, and DMs where the user is present.
* **Zero Space Maintenance**: No need to create webhooks when new spaces are created.
* **Single Credential Set**: One `token.json` powers messaging and listening across the entire workspace.
* **Google Drive & File Integration**: Can create and format documents, spreadsheets, and reports in Drive, and read attachments directly.

### Limitations
* **Prerequisite GCP Setup**: Requires creating an OAuth Client ID and configuring the Chat API in Google Cloud Console.
* **Token File Management**: Requires securely storing and persisting `token.json` across container restarts.

---

## 7. 24/7 VPS Deployment

Because Path 2 uses silent background token renewal, it is the recommended path for 24/7 VPS deployment.

For step-by-step instructions on setting up Docker, systemd, and headless authentication on Ubuntu/Debian cloud servers:
👉 **Read the [VPS 24/7 Deployment Guide](vps-deployment-guide.md)**

