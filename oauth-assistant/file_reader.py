"""
Universal Google Chat File & Attachment Reader Module.
Supports:
- Spreadsheets: Excel (.xlsx, .xls), CSV (.csv), TSV (.tsv)
- Documents: PDF (.pdf), Word (.docx), Plaintext (.txt, .md, .rtf)
- Structured Code & Data: JSON, YAML, XML, HTML, Python, JS, SQL, Shell, Configs
- Images: PNG, JPEG, WEBP, GIF (metadata and dimension inspection)
"""

import csv
import io
import logging
import os
from typing import List, Optional
import requests

logger = logging.getLogger("file-reader")


def download_attachment_bytes(resource_name: str, auth_token: str) -> Optional[bytes]:
    """Downloads raw binary bytes of a Google Chat attachment via the Media API."""
    if not resource_name or not auth_token:
        return None

    url = f"https://chat.googleapis.com/v1/media/{resource_name}?alt=media"
    headers = {"Authorization": f"Bearer {auth_token}"}
    try:
        res = requests.get(url, headers=headers, timeout=25)
        if res.status_code == 200:
            return res.content
        logger.error("Failed to download attachment %s (%d): %s", resource_name, res.status_code, res.text[:120])
    except Exception:
        logger.exception("Exception downloading attachment %s.", resource_name)
    return None


def parse_spreadsheet(file_bytes: bytes, ext: str) -> str:
    """Parses Excel or CSV spreadsheets into formatted markdown tables."""
    lines = []
    if ext in (".xlsx", ".xls"):
        try:
            import openpyxl
            wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True)
            for sheet in wb.worksheets:
                rows = list(sheet.iter_rows(values_only=True))
                lines.append(f"Sheet '{sheet.title}' ({len(rows)} total rows):")
                if not rows:
                    lines.append("  (Empty sheet)")
                    continue

                # Header + up to 25 sample rows
                for idx, row in enumerate(rows[:25]):
                    row_str = " | ".join(str(c) if c is not None else "" for c in row)
                    prefix = "  [Header]" if idx == 0 else f"  Row {idx:2d}:"
                    lines.append(f"{prefix} {row_str}")

                if len(rows) > 25:
                    lines.append(f"  ... and {len(rows) - 25} more rows.")
            return "\n".join(lines)
        except Exception as e:
            logger.warning("openpyxl parsing failed: %s", e)

    # Fallback / CSV
    try:
        text = file_bytes.decode("utf-8", errors="replace")
        reader = csv.reader(io.StringIO(text))
        rows = list(reader)
        lines.append(f"Tabular Data ({len(rows)} rows):")
        for idx, row in enumerate(rows[:25]):
            prefix = "  [Header]" if idx == 0 else f"  Row {idx:2d}:"
            lines.append(f"{prefix} {' | '.join(row)}")
        if len(rows) > 25:
            lines.append(f"  ... and {len(rows) - 25} more rows.")
        return "\n".join(lines)
    except Exception:
        return "[Could not parse spreadsheet rows]"


def parse_pdf(file_bytes: bytes) -> str:
    """Extracts readable text from PDF documents using pypdf."""
    try:
        import pypdf
        reader = pypdf.PdfReader(io.BytesIO(file_bytes))
        total_pages = len(reader.pages)
        lines = [f"PDF Document ({total_pages} pages):"]
        extracted_chars = 0
        max_chars = 15000

        for i, page in enumerate(reader.pages, 1):
            page_text = (page.extract_text() or "").strip()
            if page_text:
                lines.append(f"\n--- Page {i} ---")
                lines.append(page_text)
                extracted_chars += len(page_text)
                if extracted_chars >= max_chars:
                    lines.append(f"\n[Truncated after {i} pages due to length]")
                    break

        return "\n".join(lines)
    except Exception as e:
        logger.warning("pypdf extraction failed: %s", e)
        return "[Could not extract text from PDF document]"


def parse_docx(file_bytes: bytes) -> str:
    """Extracts paragraphs and tables from Word (.docx) documents."""
    try:
        import docx
        doc = docx.Document(io.BytesIO(file_bytes))
        lines = [f"Word Document:"]
        for p in doc.paragraphs:
            t = p.text.strip()
            if t:
                lines.append(t)
        for table in doc.tables:
            lines.append("\n[Table]:")
            for row in table.rows:
                row_vals = [cell.text.strip() for cell in row.cells]
                lines.append(" | ".join(row_vals))
        return "\n".join(lines)
    except Exception as e:
        logger.warning("docx extraction failed: %s", e)
        return "[Could not extract text from Word document]"


def parse_presentation(file_bytes: bytes, ext: str = ".pptx") -> str:
    """Extracts slide text, tables, and notes from PowerPoint presentations (.pptx, .ppt)."""
    # 1. Try python-pptx
    try:
        import pptx
        prs = pptx.Presentation(io.BytesIO(file_bytes))
        total_slides = len(prs.slides)
        lines = [f"PowerPoint Presentation ({total_slides} slides):"]
        extracted_chars = 0
        max_chars = 20000

        for idx, slide in enumerate(prs.slides, 1):
            slide_lines = [f"\n--- Slide {idx} ---"]
            for shape in slide.shapes:
                if shape.has_text_frame:
                    for p in shape.text_frame.paragraphs:
                        t = p.text.strip()
                        if t:
                            slide_lines.append(t)
                elif shape.has_table:
                    slide_lines.append("[Table]:")
                    for row in shape.table.rows:
                        row_vals = [c.text.strip() for c in row.cells]
                        slide_lines.append(" | ".join(row_vals))

            slide_text = "\n".join(slide_lines)
            lines.append(slide_text)
            extracted_chars += len(slide_text)
            if extracted_chars >= max_chars:
                lines.append(f"\n[Truncated after {idx} slides due to length]")
                break

        return "\n".join(lines)
    except Exception as e:
        logger.warning("python-pptx extraction failed (%s), attempting XML fallback...", e)

    # 2. Resilient fallback using standard library zipfile + XML parser
    try:
        import zipfile
        import xml.etree.ElementTree as ET
        with zipfile.ZipFile(io.BytesIO(file_bytes)) as z:
            slide_files = sorted(
                [f for f in z.namelist() if f.startswith("ppt/slides/slide") and f.endswith(".xml")],
                key=lambda x: int("".join(filter(str.isdigit, x)) or "0")
            )
            lines = [f"PowerPoint Presentation ({len(slide_files)} slides):"]
            for idx, sfile in enumerate(slide_files, 1):
                xml_data = z.read(sfile)
                root = ET.fromstring(xml_data)
                slide_texts = []
                for elem in root.iter():
                    if elem.tag.endswith("}t") and elem.text:
                        t = elem.text.strip()
                        if t:
                            slide_texts.append(t)
                if slide_texts:
                    lines.append(f"\n--- Slide {idx} ---")
                    lines.append("\n".join(slide_texts))
            return "\n".join(lines)
    except Exception as e:
        logger.warning("Fallback XML PPTX extraction failed: %s", e)
        return "[Could not extract text from PowerPoint presentation]"


def parse_image_info(file_bytes: bytes, ext: str) -> str:
    """Extracts dimensions, format, and metadata from images."""
    try:
        from PIL import Image
        img = Image.open(io.BytesIO(file_bytes))
        size_kb = len(file_bytes) / 1024.0
        return f"Image File: format={img.format}, dimensions={img.width}x{img.height} px, mode={img.mode}, size={size_kb:.1f} KB"
    except Exception:
        return f"Image File: extension={ext}, size={len(file_bytes)/1024.0:.1f} KB"


def parse_attachment_content(content_name: str, content_type: str, file_bytes: bytes) -> str:
    """Dispatches binary bytes to the appropriate format parser."""
    ext = os.path.splitext(content_name)[1].lower() if content_name else ""
    ctype = (content_type or "").lower()

    if ext in (".xlsx", ".xls", ".csv", ".tsv") or "spreadsheet" in ctype or "csv" in ctype:
        return parse_spreadsheet(file_bytes, ext)

    if ext == ".pdf" or "pdf" in ctype:
        return parse_pdf(file_bytes)

    if ext == ".docx" or "wordprocessingml" in ctype:
        return parse_docx(file_bytes)

    if ext in (".pptx", ".ppt", ".ppsx", ".odp") or "presentation" in ctype or "powerpoint" in ctype:
        return parse_presentation(file_bytes, ext)

    if ext in (".png", ".jpg", ".jpeg", ".webp", ".gif") or ctype.startswith("image/"):
        return parse_image_info(file_bytes, ext)

    # General text, code, JSON, logs, markdown
    text_exts = (
        ".txt", ".md", ".json", ".yaml", ".yml", ".xml", ".html", ".css", ".js",
        ".ts", ".py", ".sh", ".sql", ".log", ".env", ".toml", ".ini", ".conf"
    )
    if ext in text_exts or "text" in ctype or "json" in ctype or "javascript" in ctype:
        try:
            decoded = file_bytes.decode("utf-8", errors="replace")
            if len(decoded) > 15000:
                decoded = decoded[:15000] + "\n... [Remaining content truncated]"
            return decoded
        except Exception:
            pass

    size_kb = len(file_bytes) / 1024.0
    return f"Binary File: {content_name} ({ctype}), size: {size_kb:.1f} KB"


def extract_all_attachments_text(msg: dict, auth_token: str) -> str:
    """
    Downloads and extracts readable text from all files attached to a Google Chat message.
    """
    attachments = msg.get("attachment", [])
    if not attachments or not auth_token:
        return ""

    blocks = []
    for idx, att in enumerate(attachments, 1):
        content_name = att.get("contentName") or f"attachment_{idx}"
        content_type = att.get("contentType") or "application/octet-stream"
        ref = att.get("attachmentDataRef", {}).get("resourceName")

        if not ref:
            continue

        logger.info("Downloading attached file: %r (%s)...", content_name, content_type)
        file_bytes = download_attachment_bytes(ref, auth_token)
        if not file_bytes:
            blocks.append(f"• [Attachment {idx}: {content_name} (Failed to download file content)]")
            continue

        parsed = parse_attachment_content(content_name, content_type, file_bytes)
        blocks.append(f"\n[ATTACHED FILE {idx}: {content_name} ({content_type})]:\n{parsed}\n[END OF FILE {content_name}]")

    return "\n".join(blocks)
