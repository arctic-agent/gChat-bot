"""
Google Drive Integration Module for Webhook Assistant.
Allows the assistant to create, upload, and share files to a designated Google Drive folder.
"""

import io
import json
import logging
import mimetypes
import os
from typing import Any, Dict, List, Optional
import requests

import config

logger = logging.getLogger("drive-manager")

DRIVE_FILES_URL = "https://www.googleapis.com/drive/v3/files"
DRIVE_UPLOAD_URL = "https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart"


def resolve_drive_folder_id(folder_id: Optional[str] = None) -> Optional[str]:
    """Resolves target folder ID from argument or config (.env)."""
    fid = (folder_id or getattr(config, "GOOGLE_DRIVE_FOLDER_ID", "") or "").strip()
    if "folders/" in fid:
        fid = fid.split("folders/")[-1].split("?")[0].split("/")[0]
    return fid if fid else None


def get_drive_auth_token() -> Optional[str]:
    """Retrieves valid OAuth access token for Google Drive API calls."""
    try:
        import listen
        return listen.get_access_token()
    except Exception:
        logger.error("No valid credentials found for Google Drive API.")
        return None


def create_file_in_drive(
    filename: str,
    content: str,
    folder_id: Optional[str] = None,
    convert_to_doc: bool = False,
    mime_type: Optional[str] = None,
) -> Dict[str, Any]:
    token = get_drive_auth_token()
    if not token:
        return {
            "success": False,
            "error": "Authentication failed. Could not acquire valid OAuth credentials."
        }

    target_folder = resolve_drive_folder_id(folder_id)
    content_bytes = content.encode("utf-8") if isinstance(content, str) else content

    detected_mime, _ = mimetypes.guess_type(filename)
    upload_mime = mime_type or detected_mime or "text/plain; charset=UTF-8"

    metadata: Dict[str, Any] = {"name": filename}
    if target_folder:
        metadata["parents"] = [target_folder]

    if convert_to_doc or filename.endswith(".gdoc") or (convert_to_doc and filename.endswith((".md", ".txt"))):
        metadata["mimeType"] = "application/vnd.google-apps.document"
        if not mime_type:
            upload_mime = "text/plain; charset=UTF-8"
    elif convert_to_doc and filename.endswith((".csv", ".gsheet")):
        metadata["mimeType"] = "application/vnd.google-apps.spreadsheet"
        if not mime_type:
            upload_mime = "text/csv; charset=UTF-8"

    boundary = "===============HermesDriveBoundary=="
    body = io.BytesIO()
    
    body.write(f"--{boundary}\r\n".encode("utf-8"))
    body.write(b"Content-Type: application/json; charset=UTF-8\r\n\r\n")
    body.write(json.dumps(metadata).encode("utf-8"))
    body.write(b"\r\n")

    body.write(f"--{boundary}\r\n".encode("utf-8"))
    body.write(f"Content-Type: {upload_mime}\r\n\r\n".encode("utf-8"))
    body.write(content_bytes)
    body.write(b"\r\n")
    body.write(f"--{boundary}--\r\n".encode("utf-8"))

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": f"multipart/related; boundary={boundary}",
        "Content-Length": str(body.tell()),
    }

    try:
        res = requests.post(DRIVE_UPLOAD_URL, headers=headers, data=body.getvalue(), timeout=30)
        
        if res.status_code == 403:
            err_data = res.json().get("error", {})
            err_msg = err_data.get("message", "Insufficient Permission")
            return {
                "success": False,
                "error": (
                    f"Google Drive permission error: {err_msg}. "
                    "Ensure 'Google Drive API' is enabled in Google Cloud Console, "
                    "and run 'python auth.py' in oauth-assistant to grant the drive.file scope."
                )
            }

        if res.status_code not in (200, 201):
            return {
                "success": False,
                "error": f"Drive API returned HTTP {res.status_code}: {res.text[:200]}"
            }

        file_data = res.json()
        file_id = file_data.get("id")

        perm_url = f"{DRIVE_FILES_URL}/{file_id}/permissions"
        perm_headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        perm_payload = {"role": "reader", "type": "anyone"}
        try:
            requests.post(perm_url, headers=perm_headers, json=perm_payload, timeout=10)
        except Exception:
            pass

        meta_url = f"{DRIVE_FILES_URL}/{file_id}?fields=id,name,webViewLink,webContentLink,mimeType"
        meta_res = requests.get(meta_url, headers={"Authorization": f"Bearer {token}"}, timeout=10)
        if meta_res.status_code == 200:
            final_meta = meta_res.json()
            web_view_link = final_meta.get("webViewLink") or f"https://drive.google.com/file/d/{file_id}/view"
        else:
            web_view_link = f"https://drive.google.com/file/d/{file_id}/view"

        return {
            "success": True,
            "file_id": file_id,
            "filename": filename,
            "web_view_link": web_view_link,
            "folder_id": target_folder,
            "message": f"Successfully created '{filename}' in Google Drive!\nDirect Link: {web_view_link}"
        }

    except Exception as e:
        return {"success": False, "error": f"Exception uploading file to Drive: {e}"}


def list_files_in_folder(folder_id: Optional[str] = None, page_size: int = 15) -> Dict[str, Any]:
    token = get_drive_auth_token()
    if not token:
        return {"success": False, "error": "No valid credentials found for Google Drive API."}

    target_folder = resolve_drive_folder_id(folder_id)
    query = f"'{target_folder}' in parents and trashed=false" if target_folder else "trashed=false"

    url = f"{DRIVE_FILES_URL}"
    headers = {"Authorization": f"Bearer {token}"}
    params = {
        "q": query,
        "pageSize": page_size,
        "fields": "files(id, name, mimeType, webViewLink, modifiedTime, size)",
        "orderBy": "modifiedTime desc",
    }

    try:
        res = requests.get(url, headers=headers, params=params, timeout=15)
        if res.status_code != 200:
            return {"success": False, "error": f"Drive API returned HTTP {res.status_code}: {res.text[:200]}"}

        files = res.json().get("files", [])
        return {"success": True, "files": files, "count": len(files)}
    except Exception as e:
        return {"success": False, "error": f"Error listing Drive files: {e}"}
