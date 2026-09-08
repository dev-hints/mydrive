import pytest
import io
import urllib.parse

def test_unicode_and_special_character_filenames(auth_client):
    filenames = [
        "नमस्ते_भारत.txt",                        # Hindi
        "我的中文文档_2026.txt",                    # Chinese
        "ملف_خاص_جديد.txt",                      # Arabic
        "বাংলা_ফাইল.txt",                         # Bengali
        "🚀🎉_Special_Emoji_File.txt",           # Emoji
        "My Report (Final) & Summary #1.txt"    # Spaces, brackets, ampersands
    ]

    for fname in filenames:
        content = f"Content for {fname}".encode("utf-8")
        file_payload = {"file": (fname, io.BytesIO(content), "text/plain")}

        # 1. Upload
        up_res = auth_client.post("/api/files/upload", files=file_payload, data={"target_dir": ""})
        assert up_res.status_code == 200, f"Upload failed for {fname}"
        file_meta = up_res.json()["file"]
        assert file_meta["name"] == fname

        # 2. List and verify filename presence
        list_res = auth_client.get("/api/files?path=")
        assert list_res.status_code == 200
        names = [item["name"] for item in list_res.json()["items"]]
        assert fname in names, f"Filename {fname} not found in directory listing"

        # 3. Download and verify content & Content-Disposition header
        dl_res = auth_client.get(f"/api/files/download?path={urllib.parse.quote(file_meta['relative_path'])}")
        assert dl_res.status_code == 200
        assert dl_res.content == content
        cd = dl_res.headers.get("Content-Disposition", "")
        assert "filename*=" in cd, f"Missing RFC 5987 UTF-8 Content-Disposition for {fname}"
