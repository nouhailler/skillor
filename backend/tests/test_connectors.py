from app.connectors.esco import EscoConnector
from app.connectors.eurostat import EurostatConnector

def test_esco_normalization_supports_hal():
    payload={"language":"fr","results":{"occupation":{"_embedded":{"results":[{"title":"Data scientist","uri":"http://data.europa.eu/esco/occupation/1"}]}},"skill":{"_embedded":{"results":[{"preferredLabel":{"fr":"Python"},"uri":"http://data.europa.eu/esco/skill/1"}]}}}}
    result=EscoConnector().normalize(payload)
    assert [(r["entity_type"],r["canonical_name"]) for r in result["entities"]] == [("occupation","Data scientist"),("skill","Python")]

def test_esco_normalizes_multilingual_graph_and_isco():
    occupation_uri="http://data.europa.eu/esco/occupation/occ-1"
    essential_uri="http://data.europa.eu/esco/skill/skill-1"
    optional_uri="http://data.europa.eu/esco/skill/skill-2"
    detail={"uri":occupation_uri,"title":"scientifique des données","preferredLabel":{"fr":"scientifique des données","en":"data scientist"},"alternativeLabel":{"fr":["data scientist"]},"description":{"fr":{"literal":"Analyse des données."}},"_links":{"broaderIscoGroup":[{"uri":"http://data.europa.eu/esco/isco/C2511","code":"2511"}],"hasEssentialSkill":[{"uri":essential_uri,"title":"statistiques","skillType":"http://data.europa.eu/esco/skill-type/knowledge"}],"hasOptionalSkill":[{"uri":optional_uri,"title":"Python","skillType":"http://data.europa.eu/esco/skill-type/skill"}]}}
    skill_detail={"uri":essential_uri,"title":"statistiques","preferredLabel":{"fr":"statistiques","en":"statistics"},"alternativeLabel":{"fr":["méthodes statistiques"]},"description":{"fr":{"literal":"Science des données chiffrées."}},"skillType":"http://data.europa.eu/esco/skill-type/knowledge"}
    payload={"language":"fr","results":{"occupation":{"_embedded":{"results":[{"title":"scientifique des données","uri":occupation_uri}]}},"skill":{"_embedded":{"results":[]}}},"occupation_details":{occupation_uri:detail},"skill_details":{essential_uri:skill_detail}}
    result=EscoConnector().normalize(payload)
    occupation=next(row for row in result["entities"] if row["entity_type"]=="occupation")
    knowledge=next(row for row in result["entities"] if row["esco_uri"]==essential_uri)
    assert occupation["isco_code"] == "2511"
    assert occupation["multilingual_labels"]["en"] == "data scientist"
    assert occupation["aliases"]["fr"] == ["data scientist"]
    assert knowledge["skill_type"] == "knowledge"
    assert {(r["skill_uri"],r["relationship_type"],r["weight"]) for r in result["relations"]} == {(essential_uri,"essential",1.0),(optional_uri,"optional",0.6)}

def test_eurostat_json_stat_normalization():
    payload={"id":["unit","geo","time"],"size":[1,1,2],"dimension":{"unit":{"category":{"index":{"PC_ACT":0}}},"geo":{"category":{"index":{"FR":0}}},"time":{"category":{"index":{"2024":0,"2025":1}}}},"value":{"0":7.4,"1":7.2},"_skillor_dataset":"une_rt_a"}
    rows=EurostatConnector().normalize(payload)
    assert rows[0]["metric"] == "unemployment_rate"
    assert [x["value"] for x in rows] == [7.4,7.2]
    assert rows[1]["period"] == "2025"
