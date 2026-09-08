import csv
import io
import re
import quopri
import logging
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Query, Response
from app.database import get_db
from app.security import get_current_user, log_audit_event
from app.schemas import (
    ContactCreateRequest,
    ContactUpdateRequest,
    ContactBatchCreateRequest,
    ContactBatchDeleteRequest
)

logger = logging.getLogger("mydrive.contacts")
router = APIRouter(prefix="/api/contacts", tags=["contacts"])

def unfold_vcard_lines(content: str) -> List[str]:
    """Unfold vCard lines according to RFC 6350 (lines starting with space/tab continue previous line)."""
    raw_lines = content.splitlines()
    unfolded: List[str] = []
    for line in raw_lines:
        line_clean = line.rstrip("\r\n")
        if not line_clean:
            continue
        if (line_clean.startswith(" ") or line_clean.startswith("\t")) and unfolded:
            unfolded[-1] += line_clean[1:]
        else:
            unfolded.append(line_clean)
    return unfolded

def parse_vcards(vcard_text: str) -> List[Dict[str, str]]:
    """Parse a vCard string (supporting vCard 2.1, 3.0, and 4.0) into structured contacts."""
    lines = unfold_vcard_lines(vcard_text)
    contacts: List[Dict[str, str]] = []
    current_card: Optional[Dict[str, Any]] = None
    in_vcard = False

    for line in lines:
        upper = line.strip().upper()
        if upper == "BEGIN:VCARD":
            in_vcard = True
            current_card = {
                "name": "",
                "phone": "",
                "email": "",
                "organization": "",
                "notes": "",
                "phones_list": [],
                "emails_list": [],
                "raw_lines": [line]
            }
            continue
        elif upper == "END:VCARD":
            if in_vcard and current_card:
                current_card["raw_lines"].append(line)
                name = current_card["name"].strip()
                if not name and current_card.get("n_parts"):
                    name = " ".join(part for part in current_card["n_parts"] if part).strip()
                if not name:
                    if current_card["phones_list"]:
                        name = f"Contact ({current_card['phones_list'][0]})"
                    elif current_card["emails_list"]:
                        name = current_card["emails_list"][0]
                    else:
                        name = "Unnamed Contact"

                primary_phone = current_card["phones_list"][0] if current_card["phones_list"] else ""
                additional_phones = current_card["phones_list"][1:]
                notes = current_card["notes"].strip()
                if additional_phones:
                    alt_str = f"Other phones: {', '.join(additional_phones)}"
                    notes = f"{notes}\n{alt_str}".strip() if notes else alt_str

                primary_email = current_card["emails_list"][0] if current_card["emails_list"] else ""
                additional_emails = current_card["emails_list"][1:]
                if additional_emails:
                    alt_emails = f"Other emails: {', '.join(additional_emails)}"
                    notes = f"{notes}\n{alt_emails}".strip() if notes else alt_emails

                contacts.append({
                    "name": name,
                    "phone": primary_phone,
                    "email": primary_email,
                    "organization": current_card["organization"].strip(),
                    "notes": notes,
                    "raw_vcard": "\n".join(current_card["raw_lines"])
                })
            in_vcard = False
            current_card = None
            continue

        if not in_vcard or current_card is None:
            continue

        current_card["raw_lines"].append(line)

        # Parse property key and value
        if ":" not in line:
            continue
        header, val = line.split(":", 1)
        val = val.strip()

        # Handle quoted-printable encoding
        if "ENCODING=QUOTED-PRINTABLE" in header.upper():
            try:
                val = quopri.decodestring(val.encode("utf-8")).decode("utf-8", errors="replace")
            except Exception:
                pass

        # Unescape escaped commas, semicolons, backslashes
        val = val.replace(r"\,", ",").replace(r"\;", ";").replace(r"\n", "\n").replace(r"\\", "\\")

        prop_name = header.split(";")[0].strip().upper()

        if prop_name == "FN":
            current_card["name"] = val
        elif prop_name == "N" and not current_card["name"]:
            # N:Family;Given;Middle;Prefix;Suffix
            parts = val.split(";")
            given = parts[1].strip() if len(parts) > 1 else ""
            family = parts[0].strip() if len(parts) > 0 else ""
            current_card["n_parts"] = [given, family]
        elif prop_name == "TEL":
            clean_tel = re.sub(r"[^\d+()\- .extEXT]", "", val).strip()
            if clean_tel:
                current_card["phones_list"].append(clean_tel)
        elif prop_name == "EMAIL":
            if "@" in val:
                current_card["emails_list"].append(val.strip())
        elif prop_name == "ORG":
            current_card["organization"] = val.replace(";", " - ").strip()
        elif prop_name in ("NOTE", "TITLE"):
            if prop_name == "TITLE" and not current_card["organization"]:
                current_card["organization"] = val
            else:
                existing_notes = current_card["notes"]
                current_card["notes"] = f"{existing_notes}\n{val}".strip() if existing_notes else val

    return contacts

def parse_csv_contacts(csv_text: str) -> List[Dict[str, str]]:
    """Parse CSV text with smart header matching into structured contacts."""
    reader = csv.reader(io.StringIO(csv_text))
    rows = list(reader)
    if not rows:
        return []

    header_row = [c.strip().lower() for c in rows[0]]
    
    def find_col_idx(aliases: List[str]) -> Optional[int]:
        for alias in aliases:
            for idx, col in enumerate(header_row):
                if alias in col:
                    return idx
        return None

    name_idx = find_col_idx(["name", "full name", "contact", "display name", "first name"])
    phone_idx = find_col_idx(["phone", "mobile", "cell", "tel", "number"])
    email_idx = find_col_idx(["email", "e-mail", "mail"])
    org_idx = find_col_idx(["organization", "company", "org", "work", "business"])
    notes_idx = find_col_idx(["note", "comment", "description", "memo"])

    # Check for split first/last name
    first_name_idx = find_col_idx(["first name", "given name", "first"])
    last_name_idx = find_col_idx(["last name", "family name", "last", "surname"])

    contacts: List[Dict[str, str]] = []
    for row in rows[1:]:
        if not row or not any(field.strip() for field in row):
            continue

        name = ""
        if name_idx is not None and name_idx < len(row):
            name = row[name_idx].strip()
        elif first_name_idx is not None and last_name_idx is not None:
            fn = row[first_name_idx].strip() if first_name_idx < len(row) else ""
            ln = row[last_name_idx].strip() if last_name_idx < len(row) else ""
            name = f"{fn} {ln}".strip()

        phone = row[phone_idx].strip() if phone_idx is not None and phone_idx < len(row) else ""
        email = row[email_idx].strip() if email_idx is not None and email_idx < len(row) else ""
        org = row[org_idx].strip() if org_idx is not None and org_idx < len(row) else ""
        notes = row[notes_idx].strip() if notes_idx is not None and notes_idx < len(row) else ""

        if not name:
            if phone:
                name = f"Contact ({phone})"
            elif email:
                name = email
            else:
                continue

        contacts.append({
            "name": name,
            "phone": phone,
            "email": email,
            "organization": org,
            "notes": notes,
            "raw_vcard": ""
        })

    return contacts

@router.get("")
def list_contacts(
    search: Optional[str] = Query(None),
    starred_only: bool = Query(False),
    limit: int = Query(500, ge=1, le=2000),
    offset: int = Query(0, ge=0),
    user: dict = Depends(get_current_user)
):
    """List contacts belonging to current user, with optional search and star filter."""
    user_id = user["id"]
    query = "SELECT id, name, phone, email, organization, notes, is_starred, created_at, updated_at FROM contacts WHERE owner_id = ?"
    params: List[Any] = [user_id]

    if starred_only:
        query += " AND is_starred = 1"

    if search and search.strip():
        term = f"%{search.strip()}%"
        query += " AND (name LIKE ? OR phone LIKE ? OR email LIKE ? OR organization LIKE ? OR notes LIKE ?)"
        params.extend([term, term, term, term, term])

    query += " ORDER BY is_starred DESC, name COLLATE NOCASE ASC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    with get_db() as conn:
        rows = conn.execute(query, params).fetchall()
        count_query = "SELECT COUNT(*) as cnt FROM contacts WHERE owner_id = ?"
        count_params: List[Any] = [user_id]
        if starred_only:
            count_query += " AND is_starred = 1"
        if search and search.strip():
            term = f"%{search.strip()}%"
            count_query += " AND (name LIKE ? OR phone LIKE ? OR email LIKE ? OR organization LIKE ? OR notes LIKE ?)"
            count_params.extend([term, term, term, term, term])
        total = conn.execute(count_query, count_params).fetchone()["cnt"]

    items = [dict(r) for r in rows]
    for item in items:
        item["is_starred"] = bool(item["is_starred"])

    return {"contacts": items, "total": total}

@router.post("", status_code=status.HTTP_201_CREATED)
def create_contact(req: ContactCreateRequest, user: dict = Depends(get_current_user)):
    """Create a single contact."""
    user_id = user["id"]
    name = req.name.strip()
    if not name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Contact name cannot be empty.")

    with get_db() as conn:
        cursor = conn.execute(
            """
            INSERT INTO contacts (owner_id, name, phone, email, organization, notes, raw_vcard, is_starred)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                name,
                req.phone.strip() if req.phone else "",
                req.email.strip() if req.email else "",
                req.organization.strip() if req.organization else "",
                req.notes.strip() if req.notes else "",
                req.raw_vcard or "",
                1 if req.is_starred else 0
            )
        )
        contact_id = cursor.lastrowid
        row = conn.execute("SELECT * FROM contacts WHERE id = ?", (contact_id,)).fetchone()

    log_audit_event("CONTACT_CREATED", user["username"], "", "", f"Created contact '{name}' (#{contact_id})")
    item = dict(row)
    item["is_starred"] = bool(item["is_starred"])
    return item

@router.post("/batch", status_code=status.HTTP_201_CREATED)
def create_contacts_batch(req: ContactBatchCreateRequest, user: dict = Depends(get_current_user)):
    """Batch upload contacts (e.g. from device contact picker or import)."""
    user_id = user["id"]
    if not req.contacts:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No contacts provided.")

    imported_count = 0
    with get_db() as conn:
        conn.execute("BEGIN;")
        try:
            for c in req.contacts:
                name = c.name.strip() if c.name else "Unnamed Contact"
                conn.execute(
                    """
                    INSERT INTO contacts (owner_id, name, phone, email, organization, notes, raw_vcard, is_starred)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        user_id,
                        name,
                        c.phone.strip() if c.phone else "",
                        c.email.strip() if c.email else "",
                        c.organization.strip() if c.organization else "",
                        c.notes.strip() if c.notes else "",
                        c.raw_vcard or "",
                        1 if c.is_starred else 0
                    )
                )
                imported_count += 1
            conn.execute("COMMIT;")
        except Exception:
            conn.execute("ROLLBACK;")
            raise

    log_audit_event("CONTACTS_BATCH_IMPORTED", user["username"], "", "", f"Imported {imported_count} contacts")
    return {"status": "ok", "imported": imported_count}

@router.get("/{contact_id}")
def get_contact(contact_id: int, user: dict = Depends(get_current_user)):
    """Get single contact by ID."""
    with get_db() as conn:
        row = conn.execute("SELECT * FROM contacts WHERE id = ? AND owner_id = ?", (contact_id, user["id"])).fetchone()
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found.")
    item = dict(row)
    item["is_starred"] = bool(item["is_starred"])
    return item

@router.patch("/{contact_id}")
def update_contact(contact_id: int, req: ContactUpdateRequest, user: dict = Depends(get_current_user)):
    """Update contact attributes."""
    user_id = user["id"]
    with get_db() as conn:
        existing = conn.execute("SELECT * FROM contacts WHERE id = ? AND owner_id = ?", (contact_id, user_id)).fetchone()
        if not existing:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found.")

        updates = []
        params = []
        if req.name is not None:
            clean_name = req.name.strip()
            if not clean_name:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Contact name cannot be empty.")
            updates.append("name = ?")
            params.append(clean_name)
        if req.phone is not None:
            updates.append("phone = ?")
            params.append(req.phone.strip())
        if req.email is not None:
            updates.append("email = ?")
            params.append(req.email.strip())
        if req.organization is not None:
            updates.append("organization = ?")
            params.append(req.organization.strip())
        if req.notes is not None:
            updates.append("notes = ?")
            params.append(req.notes.strip())
        if req.is_starred is not None:
            updates.append("is_starred = ?")
            params.append(1 if req.is_starred else 0)

        if updates:
            updates.append("updated_at = CURRENT_TIMESTAMP")
            params.extend([contact_id, user_id])
            conn.execute(f"UPDATE contacts SET {', '.join(updates)} WHERE id = ? AND owner_id = ?", params)

        updated_row = conn.execute("SELECT * FROM contacts WHERE id = ?", (contact_id,)).fetchone()

    item = dict(updated_row)
    item["is_starred"] = bool(item["is_starred"])
    return item

@router.post("/{contact_id}/star")
def toggle_star(contact_id: int, user: dict = Depends(get_current_user)):
    """Toggle starred status for a contact."""
    user_id = user["id"]
    with get_db() as conn:
        row = conn.execute("SELECT is_starred FROM contacts WHERE id = ? AND owner_id = ?", (contact_id, user_id)).fetchone()
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found.")
        new_starred = 0 if row["is_starred"] else 1
        conn.execute("UPDATE contacts SET is_starred = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (new_starred, contact_id))
    return {"status": "ok", "is_starred": bool(new_starred)}

@router.delete("/{contact_id}")
def delete_contact(contact_id: int, user: dict = Depends(get_current_user)):
    """Delete a contact."""
    user_id = user["id"]
    with get_db() as conn:
        cursor = conn.execute("DELETE FROM contacts WHERE id = ? AND owner_id = ?", (contact_id, user_id))
        if cursor.rowcount == 0:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found.")
    return {"status": "ok", "message": "Contact deleted"}

@router.post("/delete-batch")
def delete_contacts_batch(req: ContactBatchDeleteRequest, user: dict = Depends(get_current_user)):
    """Batch delete multiple contacts."""
    user_id = user["id"]
    if not req.contact_ids:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No contact IDs provided.")

    placeholders = ",".join("?" for _ in req.contact_ids)
    with get_db() as conn:
        cursor = conn.execute(
            f"DELETE FROM contacts WHERE owner_id = ? AND id IN ({placeholders})",
            [user_id] + req.contact_ids
        )
        deleted = cursor.rowcount

    log_audit_event("CONTACTS_DELETED", user["username"], "", "", f"Deleted {deleted} contacts")
    return {"status": "ok", "deleted": deleted}

@router.post("/import-file")
async def import_contacts_file(file: UploadFile = File(...), user: dict = Depends(get_current_user)):
    """Import contacts from uploaded .vcf / .vcard or .csv file."""
    user_id = user["id"]
    filename = (file.filename or "").lower()
    content_bytes = await file.read()
    try:
        text_content = content_bytes.decode("utf-8")
    except UnicodeDecodeError:
        text_content = content_bytes.decode("latin-1", errors="replace")

    parsed_contacts: List[Dict[str, str]] = []
    if filename.endswith(".vcf") or filename.endswith(".vcard") or "BEGIN:VCARD" in text_content.upper():
        parsed_contacts = parse_vcards(text_content)
    elif filename.endswith(".csv"):
        parsed_contacts = parse_csv_contacts(text_content)
    else:
        # Fallback: attempt vCard, if empty attempt CSV
        parsed_contacts = parse_vcards(text_content)
        if not parsed_contacts:
            parsed_contacts = parse_csv_contacts(text_content)

    if not parsed_contacts:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No valid contacts could be found in the uploaded file. Please upload a .vcf (vCard) or .csv file."
        )

    imported_count = 0
    with get_db() as conn:
        conn.execute("BEGIN;")
        try:
            for c in parsed_contacts:
                conn.execute(
                    """
                    INSERT INTO contacts (owner_id, name, phone, email, organization, notes, raw_vcard, is_starred)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 0)
                    """,
                    (
                        user_id,
                        c["name"],
                        c["phone"],
                        c["email"],
                        c["organization"],
                        c["notes"],
                        c.get("raw_vcard", "")
                    )
                )
                imported_count += 1
            conn.execute("COMMIT;")
        except Exception:
            conn.execute("ROLLBACK;")
            raise

    log_audit_event("CONTACTS_FILE_IMPORTED", user["username"], "", "", f"Imported {imported_count} contacts from {file.filename}")
    return {"status": "ok", "imported": imported_count, "filename": file.filename}

@router.get("/export/vcf")
def export_contacts_vcf(user: dict = Depends(get_current_user)):
    """Export all user contacts as a standard RFC 6350 vCard (.vcf) file."""
    user_id = user["id"]
    with get_db() as conn:
        rows = conn.execute(
            "SELECT name, phone, email, organization, notes, raw_vcard FROM contacts WHERE owner_id = ? ORDER BY name COLLATE NOCASE ASC",
            (user_id,)
        ).fetchall()

    vcard_output: List[str] = []
    for r in rows:
        # If raw_vcard exists and is well-formed, use it directly for round-trip fidelity
        raw = r["raw_vcard"] or ""
        if "BEGIN:VCARD" in raw.upper() and "END:VCARD" in raw.upper():
            vcard_output.append(raw.strip())
        else:
            name = r["name"] or "Unnamed Contact"
            lines = [
                "BEGIN:VCARD",
                "VERSION:3.0",
                f"FN:{name}"
            ]
            if r["phone"]:
                lines.append(f"TEL;TYPE=CELL:{r['phone']}")
            if r["email"]:
                lines.append(f"EMAIL;TYPE=INTERNET:{r['email']}")
            if r["organization"]:
                lines.append(f"ORG:{r['organization']}")
            if r["notes"]:
                escaped_notes = r["notes"].replace("\n", "\\n")
                lines.append(f"NOTE:{escaped_notes}")
            lines.append("END:VCARD")
            vcard_output.append("\r\n".join(lines))

    data = ("\r\n".join(vcard_output) + "\r\n").encode("utf-8")
    return Response(
        content=data,
        media_type="text/vcard; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="contacts_export.vcf"'}
    )

@router.get("/export/csv")
def export_contacts_csv(user: dict = Depends(get_current_user)):
    """Export all user contacts as a CSV file."""
    user_id = user["id"]
    with get_db() as conn:
        rows = conn.execute(
            "SELECT name, phone, email, organization, notes, is_starred, created_at FROM contacts WHERE owner_id = ? ORDER BY name COLLATE NOCASE ASC",
            (user_id,)
        ).fetchall()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Name", "Phone", "Email", "Organization", "Notes", "Starred", "Created At"])
    for r in rows:
        writer.writerow([
            r["name"],
            r["phone"],
            r["email"],
            r["organization"],
            r["notes"],
            "Yes" if r["is_starred"] else "No",
            r["created_at"]
        ])

    data = output.getvalue().encode("utf-8")
    return Response(
        content=data,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="contacts_export.csv"'}
    )
