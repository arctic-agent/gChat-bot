"""
Hermes AI Autonomous Agent Module (User-Delegated OAuth Assistant).
Integrates Fireworks AI with:
1. Precision trigger filtering (only activates when called, tagged, or directly addressed).
2. Deep context ingestion (reads recent space messages to understand background discussions).
3. Tool execution engine (web fetching, fact searching, Python code execution).
4. Universal delivery across spaces via User OAuth.
"""

import hashlib
import json
import logging
import os
import re
import threading
from typing import Dict, List, Optional

import requests
import yaml
from dotenv import load_dotenv

import auth
import config
import file_reader
import memory
import messenger
import tools

load_dotenv(override=True)
logger = logging.getLogger("hermes-agent")

# Resolve LLM configuration from .env or fallback to local Hermes config.yaml
def resolve_llm_credentials():
    api_key = config.LLM_API_KEY
    base_url = config.LLM_BASE_URL
    model = config.LLM_MODEL

    if not api_key:
        hermes_cfg_path = os.path.expanduser(r"~\AppData\Local\hermes\config.yaml")
        if os.path.exists(hermes_cfg_path):
            try:
                with open(hermes_cfg_path, "r", encoding="utf-8") as f:
                    cfg = yaml.safe_load(f)
                    model_cfg = cfg.get("model", {})
                    api_key = model_cfg.get("api_key", "")
                    base_url = model_cfg.get("base_url", "https://api.fireworks.ai/inference/v1").rstrip("/")
                    model = model_cfg.get("default", "accounts/fireworks/models/minimax-m3")
                    logger.info("Loaded Fireworks AI credentials from local Hermes installation: %s", model)
            except Exception:
                logger.exception("Failed to read local Hermes config.")

    return api_key, base_url, model


API_KEY, BASE_URL, MODEL = resolve_llm_credentials()

SYSTEM_PROMPT = os.getenv(
    "SYSTEM_PROMPT",
    f"You are {config.BOT_NAME}, an autonomous AI assistant powered by Hermes & Fireworks AI. "
    "You assist the team inside Google Chat spaces on behalf of the user. "
    "You have full awareness of the recent conversation context and access to tools: "
    "- fetch_webpage: to extract readable text from any link or document shared by the team.\n"
    "- search_facts: to search quick facts, definitions, and technical summaries.\n"
    "- run_python: to calculate math, parse data, or manipulate JSON/dates.\n"
    "- remember_fact: to save important facts, user preferences, or knowledge into permanent memory.\n"
    "- create_drive_file: to create and upload documents, spreadsheets, or files to the team's connected Google Drive folder and get a direct web link.\n"
    "- list_drive_files: to list files in the team's Google Drive folder.\n"
    "\nFILE & GOOGLE DRIVE RULES:\n"
    "1. You have native parsers for files attached to the space: PowerPoint (.pptx, .ppt) presentations, Excel (.xlsx, .xls), PDF, Word (.docx), CSV, and code. You CAN natively read and parse them slide-by-slide and row-by-row. Never claim you cannot read attached PPT, PDF, or Excel files.\n"
    "2. ONLY call 'create_drive_file' if the user specifically requests to save, upload, export, or create a file/doc in Google Drive (e.g. 'save this in drive', 'make a doc in drive', 'create a spreadsheet in drive'). If the user simply asks a question or asks to summarize in chat, provide your answer/summary directly in chat without creating a Drive file unless requested.\n"
    "3. When you DO call 'create_drive_file', you MUST supply BOTH 'filename' (e.g. 'Discussion_Summary.md') AND the full, detailed 'content' text inside the function call arguments. Never call create_drive_file with empty arguments or without content!\n"
    "\nCRITICAL CONVERSATION POLICY:\n"
    "You must keep Google Chat conversations clean, focused, and free of unnecessary noise.\n"
    "1. When evaluating messages (especially replies or thread follow-ups), FIRST decide if a response from you is genuinely needed.\n"
    "2. If the user's message is an acknowledgment, casual banter, courteous closing (e.g. 'thanks', 'cool', 'noted', 'ok'), a statement directed to another team member, or does NOT require any answer, action, or clarification from you:\n"
    "   Respond ONLY with the exact text: NO_REPLY\n"
    "3. If the user is asking you a question, requesting assistance, giving feedback, or directing a task to you:\n"
    "   Provide a sharp, direct, concise, and helpful response.\n"
    "4. Never post pleasantries, conversational filler, or self-introductions when not asked."
)

thread_memories: Dict[str, List[dict]] = memory.load_thread_memories()
thread_lock = threading.Lock()

sent_message_hashes = set()
sent_hashes_lock = threading.Lock()


def hash_text(text: str) -> str:
    return hashlib.sha256(text.strip().encode("utf-8")).hexdigest()


def record_outgoing_message(text: str) -> None:
    with sent_hashes_lock:
        sent_message_hashes.add(hash_text(text))
        if len(sent_message_hashes) > 1000:
            sent_message_hashes.pop()


def is_bot_message(m: dict) -> bool:
    """Checks if a given message was sent by the bot."""
    if not m:
        return False
    sender = m.get("sender", {})
    sender_id = (sender.get("name") or "").lower()
    display_name = (sender.get("displayName") or "").lower()

    if config.BOT_USER_ID and config.BOT_USER_ID.lower() == sender_id:
        return True
    bot_name = (config.BOT_NAME or "").lower().strip()
    if bot_name and bot_name in display_name:
        return True
    text = (m.get("text") or "").strip()
    if text:
        with sent_hashes_lock:
            if hash_text(text) in sent_message_hashes:
                return True
    return False


def is_self_or_loop(msg: dict) -> bool:
    text = (msg.get("text") or "").strip()
    if not text:
        return True

    with sent_hashes_lock:
        if hash_text(text) in sent_message_hashes:
            return True

    return is_bot_message(msg)


def is_simple_acknowledgment(text: str) -> bool:
    """Detects simple acknowledgments, courtesies, or emojis that require no response."""
    cleaned = re.sub(r"[^\w\s]", "", text).strip().lower()
    ack_words = {
        "thanks", "thank you", "thx", "ty", "ok", "okay", "k", "got it", "noted",
        "cool", "great", "perfect", "good", "awesome", "nice", "understood", "sure",
        "yep", "yes", "done", "will do", "alright", "all right", "np", "no problem"
    }
    if cleaned in ack_words:
        return True
    # Emojis only check
    text_stripped = text.strip()
    if text_stripped in ("👍", "👌", "🙏", "✅", "🙌", "❤️", "😊", "🎉", "🔥", "💯", "👋"):
        return True
    return False


def is_reply_to_bot(msg: dict, thread_id: str, recent_space_history: List[dict] = None) -> bool:
    """
    Detects if this incoming message is a reply to the bot:
    1. Active in-memory thread where assistant has previously responded.
    2. Google Chat quotedMessageMetadata quoting a bot message.
    3. Thread history where the parent message or previous message was sent by the bot.
    """
    # 1. In-memory assistant participation
    with thread_lock:
        if thread_id in thread_memories and any(m.get("role") == "assistant" for m in thread_memories[thread_id]):
            return True

    # 2. Quoted message metadata
    quoted_meta = msg.get("quotedMessageMetadata") or {}
    quoted_name = quoted_meta.get("name")
    if quoted_name and recent_space_history:
        for prev in recent_space_history:
            if prev.get("name") == quoted_name and is_bot_message(prev):
                return True

    # 3. Thread history from recent space messages
    thread_obj = msg.get("thread", {})
    thread_name = thread_obj.get("name") or msg.get("name")
    if thread_name and recent_space_history:
        thread_msgs = [
            m for m in recent_space_history
            if (m.get("thread", {}).get("name") == thread_name or m.get("name") == thread_name)
            and m.get("name") != msg.get("name")
        ]
        if thread_msgs:
            thread_msgs.sort(key=lambda x: x.get("createTime", ""))
            # Check if immediately previous message in this thread was from bot
            if is_bot_message(thread_msgs[-1]):
                return True
            # Check if root message of this thread was from bot
            if is_bot_message(thread_msgs[0]):
                return True

    return False


def get_trigger_identifiers() -> List[str]:
    """Dynamically builds list of trigger names and aliases from configuration."""
    identifiers = {"assistant", "bot", "hermes"}
    bot_clean = (config.BOT_NAME or "").strip().lower()
    if bot_clean:
        identifiers.add(bot_clean)
        for part in bot_clean.split():
            if len(part) > 2:
                identifiers.add(part)
    for alias in getattr(config, "USER_ALIASES", []):
        if alias:
            identifiers.add(alias.lower())
    return sorted(list(identifiers), key=len, reverse=True)


def should_respond(msg: dict, thread_id: str, recent_space_history: List[dict] = None) -> bool:
    """
    Precision Trigger Filter:
    Only activates when the user/assistant is called or tagged, or replying to the bot.
    Ignores general chatter between other team members.
    """
    text = (msg.get("text") or "").strip()
    if not text or is_self_or_loop(msg):
        return False

    if config.TRIGGER_MODE == "always":
        return True

    text_lower = text.lower()
    trigger_names = get_trigger_identifiers()

    # 1. Check Google Chat annotations for explicit user mentions
    is_explicitly_mentioned = False
    annotations = msg.get("annotations") or []
    for ann in annotations:
        if ann.get("type") == "USER_MENTION":
            um = ann.get("userMention", {})
            user_obj = um.get("user", {})
            mentioned_id = (user_obj.get("name") or "").lower()
            mentioned_display = (user_obj.get("displayName") or "").lower()

            if config.BOT_USER_ID and config.BOT_USER_ID.lower() == mentioned_id:
                is_explicitly_mentioned = True
                break
            if any(name in mentioned_display for name in trigger_names):
                is_explicitly_mentioned = True
                break
            if "all" in mentioned_id or "all" in mentioned_display:
                is_explicitly_mentioned = True
                break

    # 2. Direct user mention tag matching configured BOT_USER_ID in raw text
    has_bot_user_tag = bool(config.BOT_USER_ID and config.BOT_USER_ID.lower() in text_lower)

    # 3. Explicit @ tag for any configured identifier (e.g. @assistant, @bot, @alex)
    has_at_tag = any(f"@{name}" in text_lower for name in trigger_names)

    # 4. Direct name call or salutation at beginning of text (e.g. "Assistant, can you check...", "Hey Alex...")
    escaped_names = "|".join(re.escape(name) for name in trigger_names)
    is_direct_address = bool(re.search(
        rf"^(hey|hi|hello)?\s*({escaped_names})[\s,:]+",
        text_lower
    ))

    # 5. Explicit command or keyword invocation
    has_keyword = any(re.search(rf"\b{re.escape(name)}\b", text_lower) for name in trigger_names)
    has_command_prefix = text.startswith("!") or text.startswith("/ask") or text_lower.startswith("ai:")

    # 6. Replying to a message sent by the bot
    is_reply = is_reply_to_bot(msg, thread_id, recent_space_history)

    # STRICT FILTER: Only trigger if explicitly called/tagged, command, or replying to the bot
    return (
        is_explicitly_mentioned
        or has_bot_user_tag
        or has_at_tag
        or is_direct_address
        or has_keyword
        or has_command_prefix
        or is_reply
    )


def format_space_context(recent_messages: List[dict]) -> str:
    """Formats recent space messages into a coherent background context transcript."""
    if not recent_messages:
        return ""

    lines = ["[RECENT SPACE CONVERSATION CONTEXT]:"]
    for m in recent_messages[-15:]:
        sender = m.get("sender", {}).get("displayName", "Team Member")
        text = (m.get("text") or "").strip()
        time_str = m.get("createTime", "")[:19].replace("T", " ")
        if text:
            lines.append(f"• [{time_str}] {sender}: {text}")

    lines.append("[END OF SPACE CONTEXT]\n")
    return "\n".join(lines)


def clean_param_value(val: str) -> str:
    val = val.strip()
    md_match = re.match(r"^\[([^\]]+)\]\(([^)]+)\)$", val)
    if md_match:
        return md_match.group(2).strip()
    return val


def parse_args_flexible(raw: Any) -> dict:
    """Parses tool arguments from JSON string, XML parameter tags, or element tags."""
    if not raw:
        return {}
    if isinstance(raw, dict):
        return raw
    if not isinstance(raw, str):
        return {}
    raw = raw.strip()

    # 1. Try standard JSON
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            return data
    except Exception:
        pass

    args = {}
    # 2. Try XML parameter tags: <parameter name="key">value</parameter>
    param_matches = re.finditer(
        r'<parameter\s+name=["\']([^"\']+)["\']>(.*?)(?:</parameter>|$)',
        raw,
        re.DOTALL | re.IGNORECASE,
    )
    found_any = False
    for pm in param_matches:
        found_any = True
        k = pm.group(1).strip()
        v = clean_param_value(pm.group(2))
        if v.lower() == "true":
            args[k] = True
        elif v.lower() == "false":
            args[k] = False
        else:
            args[k] = v

    if found_any:
        return args

    # 3. Try XML element tags: <key>value</key>
    tag_matches = re.finditer(r'<([a-zA-Z0-9_]+)>(.*?)(?:</\1>|$)', raw, re.DOTALL | re.IGNORECASE)
    for tm in tag_matches:
        k = tm.group(1).strip()
        if k in ("tool_call", "invoke", "function", "function_call", "parameters"):
            continue
        v = clean_param_value(tm.group(2))
        if v.lower() == "true":
            args[k] = True
        elif v.lower() == "false":
            args[k] = False
        else:
            args[k] = v

    return args


def parse_embedded_tool_calls(text: str) -> List[dict]:
    """Parses raw text-embedded tool calls emitted by models like Minimax."""
    if not text:
        return []
    cleaned = re.sub(r"\]<\][a-zA-Z0-9_\-\.]+\[>\[?", "", text)
    calls = []
    # Match <invoke name="..."> or <function_call name="...">
    matches = re.finditer(
        r'<(?:invoke|function_call)\s+name=["\']([^"\']+)["\']>(.*?)(?:</(?:invoke|function_call)>|$)',
        cleaned,
        re.DOTALL | re.IGNORECASE,
    )
    for m in matches:
        tool_name = m.group(1).strip()
        body = m.group(2)
        args = parse_args_flexible(body)
        calls.append({"name": tool_name, "arguments": args})
    return calls


def clean_model_output(text: str) -> str:
    """Strips internal tool tokens, Minimax markers, invoke tags, and parameter blocks from output text."""
    if not text:
        return ""
    # Strip Minimax token wrappers like ]<]minimax[>[
    cleaned = re.sub(r"\]<\][a-zA-Z0-9_\-\.]+\[>\[?", "", text)
    # Strip complete invoke/tool_call/function_call blocks
    cleaned = re.sub(r"<invoke\s+[^>]*>.*?</invoke>", "", cleaned, flags=re.DOTALL | re.IGNORECASE)
    cleaned = re.sub(r"<function_call\s+[^>]*>.*?</function_call>", "", cleaned, flags=re.DOTALL | re.IGNORECASE)
    cleaned = re.sub(r"<tool_call>.*?</tool_call>", "", cleaned, flags=re.DOTALL | re.IGNORECASE)
    # Strip parameter blocks (including unclosed trailing ones)
    cleaned = re.sub(r'<parameter\s+name=["\'][^"\']+["\']>.*?(?:</parameter>|$)', "", cleaned, flags=re.DOTALL | re.IGNORECASE)
    # Strip standalone/unclosed XML tags
    cleaned = re.sub(r"</?(?:tool_call|invoke|function_call|parameter|parameters)[^>]*>", "", cleaned, flags=re.IGNORECASE)
    # Strip incomplete unclosed tags at the end of text
    cleaned = re.sub(r"<[a-zA-Z0-9_]+(?:\s+[^>]*)?$", "", cleaned)
    return cleaned.strip()


def call_hermes_agent(messages: List[dict]) -> Optional[str]:
    """
    Executes the Fireworks AI reasoning loop with function calling tools.
    Supports both native API tool_calls and text-embedded model markup (e.g. Minimax).
    Never outputs raw XML tool calls or exits silently without answering.
    """
    if not API_KEY:
        logger.error("No LLM API key configured for Fireworks AI.")
        return None

    url = f"{BASE_URL}/chat/completions"
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }

    current_messages = list(messages)
    max_turns = 6

    # Tool execution loop
    for turn in range(max_turns):
        is_last_turn = (turn == max_turns - 1)
        payload = {
            "model": MODEL,
            "messages": current_messages,
            "max_tokens": 1500,
            "temperature": 0.5,
        }
        # On the last turn, omit tools to force the model to synthesize a final answer
        if not is_last_turn:
            payload["tools"] = tools.TOOL_SCHEMAS

        try:
            res = requests.post(url, headers=headers, json=payload, timeout=35)
            if res.status_code != 200:
                logger.error("Fireworks API error (%d): %s", res.status_code, res.text)
                break

            choice = res.json()["choices"][0]
            message_obj = choice["message"]
            content = message_obj.get("content") or ""

            parsed_args_by_id = {}
            tool_calls = message_obj.get("tool_calls") or []
            # Parse and normalize tool_calls arguments for Fireworks
            for tc in tool_calls:
                call_id = tc.get("id") or ""
                func = tc.get("function", {})
                raw_args = func.get("arguments")
                parsed_args = parse_args_flexible(raw_args)

                # If parsed_args is empty or missing content/filename, check message_obj["content"]
                if content and (not parsed_args or "content" not in parsed_args):
                    content_args = parse_args_flexible(content)
                    if content_args:
                        for k, v in content_args.items():
                            if k not in parsed_args or not parsed_args[k]:
                                parsed_args[k] = v

                # Save valid JSON string in func["arguments"] for Fireworks compatibility
                func["arguments"] = json.dumps(parsed_args)
                parsed_args_by_id[call_id] = parsed_args

            current_messages.append(message_obj)

            # 1. Native API tool calls
            if not is_last_turn and (choice.get("finish_reason") == "tool_calls" or tool_calls):
                for tool_call in tool_calls:
                    tool_id = tool_call.get("id")
                    func = tool_call.get("function", {})
                    name = func.get("name")
                    args = parsed_args_by_id.get(tool_id)
                    if args is None:
                        args = parse_args_flexible(func.get("arguments"))

                    logger.info("Agent requested tool: %s with args: %r", name, args)
                    tool_output = tools.execute_tool(name, args)

                    current_messages.append({
                        "role": "tool",
                        "tool_call_id": tool_id,
                        "name": name,
                        "content": str(tool_output),
                    })
                continue

            # 2. Check for text-embedded markup tool calls (e.g. Minimax tokens)
            embedded_calls = parse_embedded_tool_calls(content) if not is_last_turn else []
            if embedded_calls:
                for tc in embedded_calls:
                    name = tc["name"]
                    args = tc["arguments"]
                    logger.info("Agent requested embedded tool: %s with args: %r", name, args)
                    tool_output = tools.execute_tool(name, args)
                    current_messages.append({
                        "role": "user",
                        "content": f"[TOOL RESULT for {name} with args {args}]:\n{tool_output}",
                    })
                continue

            # 3. Clean any residual markup and check for valid user-facing text
            cleaned = clean_model_output(content)
            if cleaned:
                return cleaned

        except Exception:
            logger.exception("Inference failed during turn %d.", turn)
            break

    # Failsafe: If loop completed without final text, force a final synthesis response
    try:
        logger.info("Triggering final synthesis turn for Hermes agent...")
        # Clean current_messages for fallback call to ensure no broken tool_call sequences
        clean_fallback_messages = []
        for m in current_messages:
            role = m.get("role")
            if role == "tool":
                clean_fallback_messages.append({
                    "role": "user",
                    "content": f"[Tool Result for {m.get('name', 'tool')}]:\n{m.get('content', '')}",
                })
            elif role == "assistant" and m.get("tool_calls"):
                clean_fallback_messages.append({
                    "role": "assistant",
                    "content": m.get("content") or "I examined the requested tools and documents.",
                })
            else:
                clean_fallback_messages.append(m)

        clean_fallback_messages.append({
            "role": "user",
            "content": "Please synthesize all information above and provide a clear, comprehensive final answer now.",
        })
        fallback_res = requests.post(
            url,
            headers=headers,
            json={
                "model": MODEL,
                "messages": clean_fallback_messages,
                "max_tokens": 1500,
                "temperature": 0.5,
            },
            timeout=35,
        )
        if fallback_res.status_code == 200:
            final_content = fallback_res.json()["choices"][0]["message"].get("content") or ""
            cleaned_final = clean_model_output(final_content)
            if cleaned_final:
                return cleaned_final
        else:
            logger.error("Fallback synthesis API error (%d): %s", fallback_res.status_code, fallback_res.text)
    except Exception:
        logger.exception("Fallback synthesis failed.")

    return None


def handle_incoming_message(
    msg: dict,
    target_space: str = None,
    recent_space_history: List[dict] = None,
    is_edit: bool = False
) -> None:
    text = (msg.get("text") or "").strip()
    attachments = msg.get("attachment", [])
    if not text and not attachments:
        return
    if not text and attachments:
        text = "Please examine and summarize this attached file."

    sender_info = msg.get("sender", {})
    sender_name = sender_info.get("displayName") or sender_info.get("name", "Team Member")
    space_name = target_space or msg.get("space", {}).get("name") or config.SPACE_NAME

    thread_obj = msg.get("thread", {})
    thread_name = thread_obj.get("name") or msg.get("name")
    thread_id = thread_name.split("/")[-1] if thread_name else "default"

    # Strict check: only respond when called, tagged, or replying to the bot
    if not should_respond(msg, thread_id, recent_space_history):
        logger.debug("Message skipped (not called/tagged/reply): %r", text[:40])
        return

    # Check for attached files in this message OR recently in the space
    try:
        creds = auth.get_valid_credentials()
        token_str = creds.token if creds else None
        if token_str:
            if attachments:
                attached_files_text = file_reader.extract_all_attachments_text(msg, token_str)
                if attached_files_text:
                    logger.info("Successfully extracted text from %d file attachments in current message.", len(attachments))
                    text += "\n\n" + attached_files_text
            elif recent_space_history:
                # If current message doesn't have an attachment, check if user is asking about a file/document
                lower_text = text.lower()
                file_keywords = ("ppt", "file", "doc", "document", "pdf", "excel", "sheet", "presentation", "proposal", "above", "attached", "upload")
                if any(kw in lower_text for kw in file_keywords):
                    for prev_msg in reversed(recent_space_history):
                        prev_atts = prev_msg.get("attachment", [])
                        if prev_atts and prev_msg.get("name") != msg.get("name"):
                            recent_file_text = file_reader.extract_all_attachments_text(prev_msg, token_str)
                            if recent_file_text:
                                logger.info("Resolved recent file attachment from space for user inquiry.")
                                text += "\n\n[REFERENCED RECENT ATTACHED FILE FROM SPACE]:\n" + recent_file_text
                                break
    except Exception:
        logger.exception("Error extracting message attachments.")

    # Fast smart check: Ignore simple acknowledgments/closings (e.g. 'thanks', 'ok', 'got it', '👍')
    if is_simple_acknowledgment(text):
        lower = text.lower()
        if "?" not in text and not any(kw in lower for kw in ["can you", "what", "how", "why", "check", "please", "help"]):
            logger.info("Smart filter: Simple acknowledgment from [%s] (%r). Silently staying quiet.", sender_name, text)
            return

    msg_type = "EDITED MSG" if is_edit else "MSG"
    logger.info("Agent activated for [%s] (%s) in thread [%s]: %r", sender_name, msg_type, thread_id, text[:60])

    context_str = format_space_context(recent_space_history) if recent_space_history else ""

    with thread_lock:
        if thread_id not in thread_memories:
            thread_memories[thread_id] = []

        history = thread_memories[thread_id]
        role_label = f"{sender_name} (edited message)" if is_edit else sender_name
        history.append({"role": "user", "content": f"{role_label}: {text}"})

        if len(history) > 15:
            history = history[-15:]
            thread_memories[thread_id] = history

        # Persist updated thread memory immediately to disk
        memory.save_thread_memories(thread_memories)

        system_instruction = SYSTEM_PROMPT

        # Inject permanent accumulated knowledge & facts
        facts_context = memory.get_permanent_facts_context()
        if facts_context:
            system_instruction += "\n\n" + facts_context

        if context_str:
            system_instruction += "\n\n" + context_str

        if is_edit:
            system_instruction += (
                "\n\n[NOTICE]: The latest user message was EDITED. Evaluate the updated message. "
                "If the edit is trivial (like fixing a typo) and was already answered, reply with NO_REPLY. "
                "If it changes requirements or asks something new, answer it."
            )

        conversation_payload = [{"role": "system", "content": system_instruction}] + history

    target_thread = thread_name if config.REPLY_IN_THREAD else None
    ack_sent = [False]

    def send_progress_ack():
        try:
            ack_msg = os.getenv("WAITING_MESSAGE", "⏳ Please wait, let me check and prepare this for you...")
            logger.info("Task in progress (>2s). Sending progress acknowledgment to %s...", space_name)
            record_outgoing_message(ack_msg)
            messenger.send_user_message(
                space_name=space_name,
                text=ack_msg,
                thread_name=target_thread,
            )
            ack_sent[0] = True
        except Exception:
            logger.exception("Failed to send progress acknowledgment.")

    ack_timer = threading.Timer(2.0, send_progress_ack)
    ack_timer.daemon = True
    ack_timer.start()

    try:
        reply_text = call_hermes_agent(conversation_payload)
    finally:
        ack_timer.cancel()

    if not reply_text:
        return

    # Smart evaluation check: If model determined no reply is needed, stay silent
    clean_reply = reply_text.strip()
    if clean_reply in ("NO_REPLY", "<NO_REPLY>") or clean_reply.startswith("NO_REPLY"):
        logger.info("Smart filter: Agent evaluated message and decided no reply is needed (NO_REPLY).")
        return

    record_outgoing_message(reply_text)

    with thread_lock:
        thread_memories[thread_id].append({"role": "assistant", "content": reply_text})
        memory.save_thread_memories(thread_memories)

    # Reply in-thread only if REPLY_IN_THREAD is enabled in config (.env)
    target_thread = thread_name if config.REPLY_IN_THREAD else None

    success = messenger.send_user_message(
        space_name=space_name,
        text=reply_text,
        thread_name=target_thread,
    )
    if success:
        dest = f"thread [{thread_id}]" if target_thread else "new top-level message"
        logger.info("Successfully delivered user-delegated Hermes reply as %s!", dest)
