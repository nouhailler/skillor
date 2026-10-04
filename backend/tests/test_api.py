from app.main import app

def test_openapi_exposes_mvp_routes():
    paths=app.openapi()["paths"]
    assert "/api/v1/health" in paths
    assert "/api/v1/dashboard" in paths
    assert "/api/v1/search" in paths
    assert "/api/v1/search/suggestions" in paths
    assert "/api/v1/search/filters" in paths
    assert "/api/v1/catalog/occupations" in paths
    assert "/api/v1/catalog/skills" in paths
    assert "/api/v1/market/series" in paths
    assert "/api/v1/market/geographies" in paths
    assert "/api/v1/occupations/{occupation_id}" in paths
    assert "/api/v1/imports/{source}" in paths
    assert "/api/v1/sources/france_travail/coverage" in paths
    assert "/api/v1/eurostat/datasets" in paths
    assert "/api/v1/eurostat/indicators" in paths
    assert "/api/v1/imports/eurostat/catalog" in paths
