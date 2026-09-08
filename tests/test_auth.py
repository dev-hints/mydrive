import pytest

def test_setup_and_login_flow(client):
    # Check status
    res = client.get("/api/auth/setup-status")
    assert res.status_code == 200

    # Test bad password
    bad_login = client.post("/api/auth/login", json={
        "username": "admin",
        "password": "WrongPassword!"
    })
    assert bad_login.status_code == 401

def test_rate_limiting_lockout(client):
    # Attempt 6 wrong logins in a row to trigger lockout
    ip_headers = {"x-forwarded-for": "192.168.1.100"}
    for _ in range(5):
        client.post("/api/auth/login", json={
            "username": "victim",
            "password": "WrongPassword!"
        }, headers=ip_headers)

    # 6th attempt must be 429 Too Many Requests
    locked_res = client.post("/api/auth/login", json={
        "username": "victim",
        "password": "WrongPassword!"
    }, headers=ip_headers)
    assert locked_res.status_code == 429
    assert "Too many failed attempts" in locked_res.json()["detail"]

def test_password_change_and_session(auth_client):
    me = auth_client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["user"]["username"] == "admin"

    # Change password
    change_res = auth_client.post("/api/auth/change-password", json={
        "old_password": "StrongPassword123!",
        "new_password": "NewStrongPassword456!"
    })
    assert change_res.status_code == 200

    # Revert back so other fixtures don't break
    revert_res = auth_client.post("/api/auth/change-password", json={
        "old_password": "NewStrongPassword456!",
        "new_password": "StrongPassword123!"
    })
    assert revert_res.status_code == 200
