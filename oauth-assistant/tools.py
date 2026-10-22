"""
Hermes Agent Tools Module.
Provides executable tools for the Fireworks AI model (web fetch, facts search, Python calculation).
"""

import json
import logging
import re
import subprocess
import sys
from html import unescape
from typing import Any, Dict, List

import requests

logger = logging.getLogger("hermes-tools")

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "fetch_webpage",
            "description": "Fetch and extract readable text from a URL or documentation link.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "The HTTP or HTTPS URL to fetch.",
                    }
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_facts",
            "description": "Search DuckDuckGo instant answers for facts, definitions, tech terms, or entities.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search term or entity to look up.",
                    }
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_python",
            "description": "Execute a short Python snippet to calculate, parse data, or manipulate JSON/dates.",
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "The Python code to execute (use print() to output results).",
                    }
                },
                "required": ["code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "remember_fact",
            "description": "Store an important fact, user preference, project detail, or key finding into permanent memory across restarts.",
            "parameters": {
                "type": "object",
                "properties": {
                    "key": {
                        "type": "string",
                        "description": "A descriptive topic or identifier (e.g. 'project_tech_stack', 'user_preference').",
                    },
                    "value": {
                        "type": "string",
                        "description": "The information to remember permanently.",
                    },
                },
                "required": ["key", "value"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_drive_file",
            "description": "Create and upload a new document, report, summary, spreadsheet, or code file directly to the team's connected Google Drive folder. Automatically configures sharing and returns the direct access web link.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {
                        "type": "string",
                        "description": "Name of the file with extension (e.g. 'Proposal_Summary.md', 'Market_Analysis.docx', 'Client_List.csv', 'Report.txt').",
                    },
                    "content": {
                        "type": "string",
                        "description": "The full text, markdown, or CSV content to write into the file.",
                    },
                    "convert_to_google_doc": {
                        "type": "boolean",
                        "description": "If true, converts the file into an interactive native Google Doc or Google Sheet.",
                    },
                },
                "required": ["filename", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_drive_files",
            "description": "List files currently stored in the team's connected Google Drive folder.",
            "parameters": {
                "type": "object",
                "properties": {
                    "page_size": {
                        "type": "integer",
                        "description": "Maximum number of files to list (default 15).",
                    }
                },
            },
        },
    },
]


def tool_fetch_webpage(url: str) -> str:
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) HermesAssistant/1.0"}
        res = requests.get(url, headers=headers, timeout=8)
        if res.status_code != 200:
            return f"Error: Webpage returned HTTP status {res.status_code}"

        html = res.text
        text = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", html, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<[^>]+>", " ", text)
        text = unescape(re.sub(r"\s+", " ", text)).strip()
        return text[:2000] if text else "Page loaded but no readable text found."
    except Exception as e:
        return f"Failed to fetch URL: {e}"


def tool_search_facts(query: str) -> str:
    try:
        url = f"https://api.duckduckgo.com/?q={requests.utils.quote(query)}&format=json&no_html=1&skip_disambig=1"
        res = requests.get(url, timeout=6).json()
        abstract = res.get("AbstractText") or res.get("Answer")
        if abstract:
            return f"Result: {abstract[:1000]}"

        related = res.get("RelatedTopics", [])
        snippets = []
        for item in related[:3]:
            if isinstance(item, dict) and item.get("Text"):
                snippets.append(item["Text"])

        if snippets:
            return "Related Information:\n" + "\n".join(f"- {s}" for s in snippets)
        return "No direct factual summary found for this query."
    except Exception as e:
        return f"Search error: {e}"


def tool_run_python(code: str) -> str:
    try:
        proc = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            timeout=5,
        )
        out = (proc.stdout or "").strip()
        err = (proc.stderr or "").strip()
        if err:
            return f"Output: {out}\nErrors: {err}"[:1000]
        return out[:1000] if out else "Execution finished with no output."
    except subprocess.TimeoutExpired:
        return "Error: Code execution timed out (5s limit)."
    except Exception as e:
        return f"Execution error: {e}"


def execute_tool(tool_name: str, arguments: Dict[str, Any]) -> str:
    logger.info("Executing tool [%s] with args: %r", tool_name, arguments)
    if tool_name == "fetch_webpage":
        return tool_fetch_webpage(arguments.get("url", ""))
    elif tool_name == "search_facts":
        return tool_search_facts(arguments.get("query", ""))
    elif tool_name == "run_python":
        return tool_run_python(arguments.get("code", ""))
    elif tool_name == "remember_fact":
        import memory
        k = arguments.get("key", "")
        v = arguments.get("value", "")
        if k and v:
            success = memory.save_fact(k, v)
            return f"Saved fact to permanent memory: {k} = {v}" if success else "Failed to save fact."
        return "Error: 'key' and 'value' parameters are required."
    elif tool_name == "create_drive_file":
        import drive_manager
        fn = (arguments.get("filename") or "").strip() or "Team_Document.md"
        content = (arguments.get("content") or "").strip()
        convert_to_doc = arguments.get("convert_to_google_doc", False)
        if not content:
            return "Error: Cannot create an empty file. Please provide the full document text in the 'content' argument to save into Google Drive."
        res = drive_manager.create_file_in_drive(filename=fn, content=content, convert_to_doc=convert_to_doc)
        if res.get("success"):
            return f"File successfully created in Google Drive!\nFile: {res.get('filename')}\nDirect Link: {res.get('web_view_link')}"
        return f"Failed to create Google Drive file: {res.get('error')}"
    elif tool_name == "list_drive_files":
        import drive_manager
        ps = arguments.get("page_size", 15)
        res = drive_manager.list_files_in_folder(page_size=ps)
        if res.get("success"):
            files = res.get("files", [])
            if not files:
                return "The Google Drive folder is currently empty."
            lines = [f"Files in Google Drive folder ({len(files)} items):"]
            for f in files:
                lines.append(f"- {f.get('name')} | Link: {f.get('webViewLink')}")
            return "\n".join(lines)
        return f"Failed to list Drive files: {res.get('error')}"
    else:
        return f"Unknown tool: {tool_name}"
