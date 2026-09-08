import pytest
import io
import hashlib

def test_chunked_upload_assembly(auth_client):
    chunk_1 = b"Chunk 1: First part of the big file.\n"
    chunk_2 = b"Chunk 2: Second part of the big file.\n"
    chunk_3 = b"Chunk 3: Third and final part.\n"
    full_data = chunk_1 + chunk_2 + chunk_3
    full_sha256 = hashlib.sha256(full_data).hexdigest()

    # 1. Init
    init_res = auth_client.post("/api/upload/init", json={
        "filename": "big_dataset.bin",
        "target_dir": "",
        "total_size": len(full_data),
        "total_chunks": 3
    })
    assert init_res.status_code == 200
    upload_id = init_res.json()["upload_id"]

    # 2. Upload chunks in arbitrary order (chunk 1, then 0, then 2)
    c1_res = auth_client.post("/api/upload/chunk", data={"upload_id": upload_id, "chunk_index": 1}, files={"chunk_file": ("c1", io.BytesIO(chunk_2))})
    assert c1_res.status_code == 200

    c0_res = auth_client.post("/api/upload/chunk", data={"upload_id": upload_id, "chunk_index": 0}, files={"chunk_file": ("c0", io.BytesIO(chunk_1))})
    assert c0_res.status_code == 200

    # Check status
    status_res = auth_client.get(f"/api/upload/status/{upload_id}")
    assert status_res.status_code == 200
    assert status_res.json()["received_chunks"] == [0, 1]
    assert status_res.json()["is_complete"] is False

    c2_res = auth_client.post("/api/upload/chunk", data={"upload_id": upload_id, "chunk_index": 2}, files={"chunk_file": ("c2", io.BytesIO(chunk_3))})
    assert c2_res.status_code == 200

    # 3. Finish & Assemble
    finish_res = auth_client.post("/api/upload/finish", json={
        "upload_id": upload_id,
        "expected_sha256": full_sha256
    })
    assert finish_res.status_code == 200
    file_info = finish_res.json()["file"]
    assert file_info["size"] == len(full_data)

    # 4. Verify downloaded file matches exactly
    dl_res = auth_client.get(f"/api/files/download?path={file_info['relative_path']}")
    assert dl_res.status_code == 200
    assert dl_res.content == full_data
