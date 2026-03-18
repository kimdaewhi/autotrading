from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_create_access_token():
    resp = client.post("/auth/token")
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data


def test_get_balance_with_token():
    token_resp = client.post("/auth/token")
    access_token = token_resp.json()["access_token"]

    resp = client.get(
        "/account/balance",
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert resp.status_code == 200


def test_get_access_token_and_balance():
    # 1. Access Token 발급
    response = client.post("/auth/token")
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    access_token = data["access_token"]

    # 2. 발급받은 Access Token으로 계좌 잔고 조회
    headers = {"Authorization": f"Bearer {access_token}"}
    balance_response = client.get("/account/balance", headers=headers)
    assert balance_response.status_code == 200
    
    balance_data = balance_response.json()
    assert balance_data["rt_cd"] == "0"
    assert "output1" in balance_data
    assert "output2" in balance_data
    assert isinstance(balance_data["output2"], list)
    assert len(balance_data["output2"]) > 0
    assert "dnca_tot_amt" in balance_data["output2"][0]