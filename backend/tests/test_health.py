def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_root_reports_health_path(client):
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["health"] == "/health"


def test_openapi_available(client):
    response = client.get("/openapi.json")
    assert response.status_code == 200
    assert "/health" in response.json()["paths"]
