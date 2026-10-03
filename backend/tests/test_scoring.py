from app.services.scoring import TrendComponents, confidence_score, trend_score

def test_trend_score_is_explainable_and_internal():
    result=trend_score(TrendComponents(100,80,60,40,90))
    assert result["score"] == 80.0
    assert result["method_version"] == "1.0"
    assert result["is_official"] is False
    assert set(result["components"]) == {"growth","acceleration","volume","geographic_spread","source_confidence"}

def test_scores_are_bounded():
    result=trend_score(TrendComponents(200,-10,50,50,50))
    assert 0 <= result["score"] <= 100
    assert confidence_score(200,200,200,200,200)["score"] == 100
