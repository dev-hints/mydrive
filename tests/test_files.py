import pytest
import io

def test_folder_crud(auth_client):
    # Create folder
    res = auth_client.post("/api/files/folder", json={
        "parent_path": "",
        "folder_name": "TestFolder"
    })
    assert res.status_code == 200
    assert res.json()["relative_path"] == "TestFolder"

    # List folder
    list_res = auth_client.get("/api/files?path=")
    assert list_res.status_code == 200
    names = [i["name"] for i in list_res.json()["items"]]
    assert "TestFolder" in names

    # Rename folder
    rename_res = auth_client.patch("/api/files/rename", json={
        "path": "TestFolder",
        "new_name": "RenamedFolder"
    })
    assert rename_res.status_code == 200
    assert rename_res.json()["relative_path"] == "RenamedFolder"

    # Trash folder
    trash_res = auth_client.delete("/api/files?path=RenamedFolder")
    assert trash_res.status_code == 200

def test_file_upload_and_download(auth_client):
    content = b"Hello, MyDrive on Android Termux and Debian PRoot!"
    file_payload = {"file": ("test_hello.txt", io.BytesIO(content), "text/plain")}

    upload_res = auth_client.post("/api/files/upload", files=file_payload, data={"target_dir": ""})
    assert upload_res.status_code == 200
    rel_path = upload_res.json()["file"]["relative_path"]
    assert rel_path == "test_hello.txt"

    # Download normal
    dl_res = auth_client.get(f"/api/files/download?path={rel_path}")
    assert dl_res.status_code == 200
    assert dl_res.content == content

    # Download Range (bytes 0-10)
    range_res = auth_client.get(f"/api/files/download?path={rel_path}", headers={"Range": "bytes=0-10"})
    assert range_res.status_code == 206
    assert range_res.content == content[0:11]
    assert range_res.headers.get("Content-Range") == f"bytes 0-10/{len(content)}"

def test_trash_and_restore(auth_client):
    content = b"File to be trashed and restored"
    upload_res = auth_client.post("/api/files/upload", files={"file": ("to_trash.txt", io.BytesIO(content), "text/plain")})
    assert upload_res.status_code == 200

    # Delete (move to trash)
    del_res = auth_client.delete("/api/files?path=to_trash.txt")
    assert del_res.status_code == 200

    # List trash
    trash_list = auth_client.get("/api/files/trash")
    assert trash_list.status_code == 200
    trash_items = trash_list.json()["items"]
    trashed_item = next((item for item in trash_items if item["name"] == "to_trash.txt"), None)
    assert trashed_item is not None

    # Restore from trash
    restore_res = auth_client.post(f"/api/files/trash/restore/{trashed_item['id']}")
    assert restore_res.status_code == 200

    # Verify restored file exists
    dl_res = auth_client.get("/api/files/download?path=to_trash.txt")
    assert dl_res.status_code == 200
    assert dl_res.content == content

def test_photos_videos_documents_sections(auth_client):
    # 1. Create nested folders
    auth_client.post("/api/files/folder", json={"parent_path": "", "folder_name": "Albums"})
    auth_client.post("/api/files/folder", json={"parent_path": "Albums", "folder_name": "Vacation"})
    auth_client.post("/api/files/folder", json={"parent_path": "", "folder_name": "Docs"})

    # 2. Upload photos in root and subfolder
    auth_client.post("/api/files/upload", files={"file": ("root_pic.jpg", io.BytesIO(b"root-img-data"), "image/jpeg")}, data={"target_dir": ""})
    auth_client.post("/api/files/upload", files={"file": ("beach.png", io.BytesIO(b"beach-img-data"), "image/png")}, data={"target_dir": "Albums/Vacation"})

    # 3. Upload videos in root and subfolder
    auth_client.post("/api/files/upload", files={"file": ("movie.mp4", io.BytesIO(b"video-data-1"), "video/mp4")}, data={"target_dir": ""})
    auth_client.post("/api/files/upload", files={"file": ("clip.webm", io.BytesIO(b"video-data-2"), "video/webm")}, data={"target_dir": "Albums/Vacation"})

    # 4. Upload documents in root and subfolder
    auth_client.post("/api/files/upload", files={"file": ("report.pdf", io.BytesIO(b"pdf-data"), "application/pdf")}, data={"target_dir": ""})
    auth_client.post("/api/files/upload", files={"file": ("notes.docx", io.BytesIO(b"docx-data"), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")}, data={"target_dir": "Docs"})

    # 5. Test GET /api/files/photos
    photos_res = auth_client.get("/api/files/photos")
    assert photos_res.status_code == 200
    photo_names = [i["name"] for i in photos_res.json()["items"]]
    assert "root_pic.jpg" in photo_names
    assert "beach.png" in photo_names
    assert "movie.mp4" not in photo_names
    assert "report.pdf" not in photo_names
    # Check relative paths show files are in anywhere in the folder
    beach_item = next(i for i in photos_res.json()["items"] if i["name"] == "beach.png")
    assert beach_item["relative_path"] == "Albums/Vacation/beach.png"

    # 6. Test GET /api/files/videos
    videos_res = auth_client.get("/api/files/videos")
    assert videos_res.status_code == 200
    video_names = [i["name"] for i in videos_res.json()["items"]]
    assert "movie.mp4" in video_names
    assert "clip.webm" in video_names
    assert "beach.png" not in video_names
    clip_item = next(i for i in videos_res.json()["items"] if i["name"] == "clip.webm")
    assert clip_item["relative_path"] == "Albums/Vacation/clip.webm"

    # 7. Test GET /api/files/documents
    docs_res = auth_client.get("/api/files/documents")
    assert docs_res.status_code == 200
    doc_names = [i["name"] for i in docs_res.json()["items"]]
    assert "report.pdf" in doc_names
    assert "notes.docx" in doc_names
    assert "root_pic.jpg" not in doc_names
    notes_item = next(i for i in docs_res.json()["items"] if i["name"] == "notes.docx")
    assert notes_item["relative_path"] == "Docs/notes.docx"

    # 8. Test /api/files/category/{category} generic endpoint
    cat_photos = auth_client.get("/api/files/category/photos")
    assert cat_photos.status_code == 200
    assert len(cat_photos.json()["items"]) == len(photos_res.json()["items"])

    invalid_cat = auth_client.get("/api/files/category/unknown_category")
    assert invalid_cat.status_code == 400

    # 9. Test trash exclusion: trashing beach.png removes it from photos section
    del_res = auth_client.delete("/api/files?path=Albums/Vacation/beach.png")
    assert del_res.status_code == 200
    photos_after_trash = auth_client.get("/api/files/photos")
    photo_names_after = [i["name"] for i in photos_after_trash.json()["items"]]
    assert "beach.png" not in photo_names_after
    assert "root_pic.jpg" in photo_names_after

def test_direct_disk_files_sync_in_categories(auth_client):
    from app.storage import storage_manager
    user_root = storage_manager.get_user_storage_root(owner_id=1)
    
    # Create subfolder on disk directly
    sub_dir = user_root / "RawPhotos" / "Sub"
    sub_dir.mkdir(parents=True, exist_ok=True)

    # Place image file directly on disk
    photo_file = sub_dir / "camera_capture.jpg"
    photo_file.write_bytes(b"\xff\xd8\xff\xe0" + b"sample-jpeg-bytes")

    # Place video file directly on disk
    video_file = sub_dir / "clip_direct.mp4"
    video_file.write_bytes(b"sample-mp4-bytes")

    # Place document file directly on disk
    doc_file = sub_dir / "paper.pdf"
    doc_file.write_bytes(b"%PDF-1.4 sample pdf")

    # Query /api/files/photos
    res_photos = auth_client.get("/api/files/photos")
    assert res_photos.status_code == 200
    names = [i["name"] for i in res_photos.json()["items"]]
    assert "camera_capture.jpg" in names

    # Query /api/files/videos
    res_videos = auth_client.get("/api/files/videos")
    assert res_videos.status_code == 200
    names_vid = [i["name"] for i in res_videos.json()["items"]]
    assert "clip_direct.mp4" in names_vid

    # Query /api/files/documents
    res_docs = auth_client.get("/api/files/documents")
    assert res_docs.status_code == 200
    names_doc = [i["name"] for i in res_docs.json()["items"]]
    assert "paper.pdf" in names_doc
