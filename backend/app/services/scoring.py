from dataclasses import dataclass, asdict

@dataclass(frozen=True)
class TrendComponents:
    growth: float
    acceleration: float
    volume: float
    geographic_spread: float
    source_confidence: float

def trend_score(c: TrendComponents) -> dict:
    values = asdict(c)
    bounded = {key: max(0.0, min(100.0, float(value))) for key, value in values.items()}
    score = 0.35 * bounded["growth"] + 0.25 * bounded["acceleration"] + 0.20 * bounded["volume"] + 0.10 * bounded["geographic_spread"] + 0.10 * bounded["source_confidence"]
    return {"score": round(score, 2), "components": bounded, "method_version": "1.0", "is_official": False}

def confidence_score(source_quality: float, recency: float, coverage: float, consistency: float, agreement: float) -> dict:
    score = .30*source_quality + .25*recency + .20*coverage + .15*consistency + .10*agreement
    return {"score": round(max(0, min(100, score)), 2), "method_version": "1.0", "is_official": False}
