# Deep Dive: Google Chat Incoming Webhook Architecture (Path 1)

This document provides a technical explanation of how Google Chat Incoming Webhooks function, how identity badges are generated, and how to automate message delivery and monitoring.

---

## 1. How the Webhook Attribution Badge Works

In Google Chat, incoming webhooks use a unique attribution model:

```
[ Creator: Jane Doe ] + [ Webhook Name: Release Bot ]
                 │
                 ▼
Rendered UI: Jane Doe [Release Bot] (with Jane's Google avatar)
```

1. **Avatar & Display Name**: Google Chat stamps the message with the profile photo and full name of the **human user who generated the webhook token**.
2. **Pill Badge**: Directly adjacent to the creator's name, Google Chat displays a gray chip containing the **Webhook Name** specified during creation.
3. **Space Scope**: A webhook token is strictly scoped to the single space where it was created. It cannot post into any other space.

---

## 2. API Endpoint & Payload Schema

### Endpoint Structure
```http
POST https://chat.googleapis.com/v1/spaces/{SPACE_ID}/messages?key={API_KEY}&token={WEBHOOK_TOKEN}
Content-Type: application/json
```

### Top-Level Message (New Conversation)
To create a brand-new message card at the root of the space, omit the `thread` object:
```json
{
  "text": "Hello team! Deployment completed successfully."
}
```

### In-Thread Reply
To reply inside an existing discussion thread, pass the `threadKey` (or thread resource name) and specify `messageReplyOption=REPLY_MESSAGE_FALLBACK_TO_NEW_THREAD`:
```http
POST https://chat.googleapis.com/v1/spaces/{SPACE_ID}/messages?key={KEY}&token={TOKEN}&messageReplyOption=REPLY_MESSAGE_FALLBACK_TO_NEW_THREAD
Content-Type: application/json

{
  "text": "Here is the follow-up answer in this thread.",
  "thread": {
    "name": "spaces/{SPACE_ID}/threads/{THREAD_ID}",
    "threadKey": "{THREAD_ID}"
  }
}
```

---

## 3. Architecture for 24/7 Monitoring + Auto-Reply

Because incoming webhooks are **outbound-only** (they can send messages, but cannot listen to events), the automated assistant architecture operates in two complementary halves:

```
┌─────────────────────────────────────────────────────────────┐
│ 1. INBOUND LISTENER (listen.py)                             │
│    • Polls Chat REST API spaces.messages.list every 2s      │
│    • Or streams events via Google Workspace Events API      │
│    • Deduplicates messages using message resource IDs       │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│ 2. REASONING ENGINE (agent.py)                              │
│    • Loop Guard: Checks if sender matches bot badge         │
│    • Evaluates trigger conditions (mentions / questions)    │
│    • Passes thread context to LLM (OpenAI / Fireworks)      │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│ 3. OUTBOUND DISPATCH (messenger.py)                         │
│    • Posts payload to CHAT_WEBHOOK_URL                      │
│    • Displays as: [Creator Name] [Webhook Badge]            │
└─────────────────────────────────────────────────────────────┘
```

---

## 4. Advantages & Limitations

### Advantages
* **Zero Admin Approval**: Any user with permission to create webhooks in a space can deploy this immediately.
* **No Token Expiration**: Webhook URLs remain active indefinitely until deleted.
* **No OAuth Flow**: No browser logins or credentials refresh cycles required.

### Limitations
* **Space-Isolated**: You must manually create a webhook inside each space where you want the assistant to post.
* **Outbound Only**: Requires a separate reading mechanism (User OAuth or Service Account) to monitor incoming messages.
