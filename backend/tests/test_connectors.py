from app.connectors.esco import EscoConnector
from app.connectors.eurostat import EurostatConnector

def test_esco_normalization_supports_hal():
    payload={"language":"fr","results":{"occupation":{"_embedded":{"results":[{"title":"Data scientist","uri":"http://data.europa.eu/esco/occupation/1"}]}},"skill":{"_embedded":{"results":[{"preferredLabel":{"fr":"Python"},"uri":"http://data.europa.eu/esco/skill/1"}]}}}}
    rows=EscoConnector().normalize(payload)
    assert [(r["entity_type"],r["canonical_name"]) for r in rows] == [("occupation","Data scientist"),("skill","Python")]

def test_eurostat_json_stat_normalization():
    payload={"id":["unit","geo","time"],"size":[1,1,2],"dimension":{"unit":{"category":{"index":{"PC_ACT":0}}},"geo":{"category":{"index":{"FR":0}}},"time":{"category":{"index":{"2024":0,"2025":1}}}},"value":{"0":7.4,"1":7.2},"_skillor_dataset":"une_rt_a"}
    rows=EurostatConnector().normalize(payload)
    assert rows[0]["metric"] == "unemployment_rate"
    assert [x["value"] for x in rows] == [7.4,7.2]
    assert rows[1]["period"] == "2025"
