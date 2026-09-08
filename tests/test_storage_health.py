import pytest

def test_health_endpoint(client):
    res = client.get("/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert data["database"] == "ok"
    assert data["storage"] == "ok"
    assert "uptime_seconds" in data

def test_storage_stats(auth_client):
    res = auth_client.get("/api/storage")
    assert res.status_code == 200
    stats = res.json()
    assert "total_disk" in stats
    assert "used_disk" in stats
    assert "free_disk" in stats
    assert "file_count" in stats
    assert "folder_count" in stats
    assert stats["total_disk"] > 0

def test_audit_logs(auth_client):
    res = auth_client.get("/api/audit")
    assert res.status_code == 200
    data = res.json()
    assert "logs" in data
    assert "total" in data
    assert len(data["logs"]) > 0
