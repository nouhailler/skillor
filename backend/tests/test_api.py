from app.main import app

def test_openapi_exposes_mvp_routes():
    paths=app.openapi()["paths"]
    assert "/api/v1/health" in paths
    assert "/api/v1/dashboard" in paths
    assert "/api/v1/search" in paths
    assert "/api/v1/occupations/{occupation_id}" in paths
    assert "/api/v1/imports/{source}" in paths
