import pytest
from app.database import get_db

def test_contacts_crud(auth_client):
    # 1. Create contact
    res = auth_client.post("/api/contacts", json={
        "name": "Alice Johnson",
        "phone": "+1-555-0199",
        "email": "alice@example.com",
        "organization": "Acme Labs",
        "notes": "Met at DevCon"
    })
    assert res.status_code == 201
    contact = res.json()
    contact_id = contact["id"]
    assert contact["name"] == "Alice Johnson"
    assert contact["phone"] == "+1-555-0199"
    assert contact["is_starred"] is False

    # 2. Get contact
    res = auth_client.get(f"/api/contacts/{contact_id}")
    assert res.status_code == 200
    assert res.json()["email"] == "alice@example.com"

    # 3. Star contact
    res = auth_client.post(f"/api/contacts/{contact_id}/star")
    assert res.status_code == 200
    assert res.json()["is_starred"] is True

    # 4. List contacts with search and starred
    res = auth_client.get("/api/contacts?search=Alice")
    assert res.status_code == 200
    assert len(res.json()["contacts"]) >= 1

    res = auth_client.get("/api/contacts?starred_only=true")
    assert res.status_code == 200
    assert any(c["id"] == contact_id for c in res.json()["contacts"])

    # 5. Update contact
    res = auth_client.patch(f"/api/contacts/{contact_id}", json={
        "organization": "Acme Corp International"
    })
    assert res.status_code == 200
    assert res.json()["organization"] == "Acme Corp International"

    # 6. Delete contact
    res = auth_client.delete(f"/api/contacts/{contact_id}")
    assert res.status_code == 200

    res = auth_client.get(f"/api/contacts/{contact_id}")
    assert res.status_code == 404

def test_contacts_batch_create_and_delete(auth_client):
    res = auth_client.post("/api/contacts/batch", json={
        "contacts": [
            {"name": "Bob Builder", "phone": "111-222-3333"},
            {"name": "Charlie Brown", "phone": "444-555-6666"}
        ]
    })
    assert res.status_code == 201
    assert res.json()["imported"] == 2

    # Find created contacts
    res = auth_client.get("/api/contacts?search=Builder")
    assert res.status_code == 200
    bob_id = res.json()["contacts"][0]["id"]

    res = auth_client.get("/api/contacts?search=Brown")
    assert res.status_code == 200
    charlie_id = res.json()["contacts"][0]["id"]

    # Batch delete
    del_res = auth_client.post("/api/contacts/delete-batch", json={
        "contact_ids": [bob_id, charlie_id]
    })
    assert del_res.status_code == 200
    assert del_res.json()["deleted"] == 2

def test_vcard_import_export(auth_client):
    vcf_content = """BEGIN:VCARD
VERSION:3.0
FN:David Miller
TEL;TYPE=CELL:+15559876543
EMAIL;TYPE=INTERNET:david.miller@example.com
ORG:Nexus Technologies
NOTE:Lead Developer
END:VCARD
BEGIN:VCARD
VERSION:3.0
FN:Emma Watson
TEL;TYPE=WORK:+15551234567
EMAIL;TYPE=WORK:emma@example.org
ORG:Global Studios
END:VCARD
"""
    files = {"file": ("contacts.vcf", vcf_content.encode("utf-8"), "text/vcard")}
    import_res = auth_client.post("/api/contacts/import-file", files=files)
    assert import_res.status_code == 200
    assert import_res.json()["imported"] == 2

    # Verify search
    res = auth_client.get("/api/contacts?search=David")
    assert res.status_code == 200
    assert len(res.json()["contacts"]) >= 1

    # Export VCF
    export_vcf = auth_client.get("/api/contacts/export/vcf")
    assert export_vcf.status_code == 200
    assert "BEGIN:VCARD" in export_vcf.text
    assert "David Miller" in export_vcf.text

    # Export CSV
    export_csv = auth_client.get("/api/contacts/export/csv")
    assert export_csv.status_code == 200
    assert "David Miller" in export_csv.text
    assert "Nexus Technologies" in export_csv.text

def test_csv_import(auth_client):
    csv_content = """Name,Phone,Email,Organization,Notes
Franklin Jones,555-888-9999,frank@test.com,Apex Security,Security Lead
Grace Hopper,555-000-1111,grace@navy.mil,Computing Pioneer,Compiler Inventor
"""
    files = {"file": ("my_contacts.csv", csv_content.encode("utf-8"), "text/csv")}
    import_res = auth_client.post("/api/contacts/import-file", files=files)
    assert import_res.status_code == 200
    assert import_res.json()["imported"] == 2

    res = auth_client.get("/api/contacts?search=Grace")
    assert res.status_code == 200
    assert res.json()["contacts"][0]["organization"] == "Computing Pioneer"
