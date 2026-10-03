from app.connectors.esco import EscoConnector
from app.connectors.eurostat import EurostatConnector
from app.connectors.france_travail import FranceTravailConnector
from app.eurostat_catalog import eurostat_catalog
from app.services.occupation_mapping import parse_rome_esco_crosswalk

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

def test_eurostat_catalog_covers_six_indicator_families():
    catalog=eurostat_catalog()
    assert set(catalog) == {"unemployment","employment","wages","education","sectors","regional_unemployment"}
    assert {spec["family"] for spec in catalog.values()} == {"unemployment","employment","wages","education","sectors","regional"}
    assert catalog["wages"]["filters"]["indic_se"] == "MEAN_E_EUR"
    assert catalog["wages"]["output_unit"] == "EUR/month"

def test_eurostat_regional_normalization_keeps_french_nuts_and_labels():
    payload={"id":["unit","geo","time"],"size":[1,2,1],"dimension":{
        "unit":{"category":{"index":{"PC":0},"label":{"PC":"Percentage"}}},
        "geo":{"category":{"index":{"FR10":0,"DE11":1},"label":{"FR10":"Île-de-France","DE11":"Stuttgart"}}},
        "time":{"category":{"index":{"2025":0},"label":{"2025":"2025"}}}},
        "value":{"0":7.1,"1":4.2},"status":{"0":"p"},"_skillor_dataset":"lfst_r_lfu3rt",
        "_skillor_profile":"regional_unemployment","_skillor_metric":"regional_unemployment_rate",
        "_skillor_family":"regional","_skillor_geography_level":"nuts2","_skillor_geography_prefix":"FR"}
    rows=EurostatConnector().normalize(payload)
    assert len(rows) == 1
    assert rows[0]["geography_code"] == "FR10"
    assert rows[0]["geography_name"] == "Île-de-France"
    assert rows[0]["status"] == "p"
    assert rows[0]["dimension_labels"]["unit"] == "Percentage"

def test_france_travail_market_rows_keep_occupation_and_territory_context():
    payload={"resultats":[{"indicateur":"Difficulté recrutement","valeur":"67,5","unite":"percent",
        "periode":"2026-Q1","territoire":{"code":"75","libelle":"Paris"},
        "metier":{"codeRome":"M1805","libelle":"Études et développement informatique"},
        "secteur":{"code":"62","libelle":"Programmation informatique"}}]}
    rows=FranceTravailConnector().normalize(payload)
    assert rows[0]["metric"] == "recruitment_difficulty"
    assert rows[0]["occupation_external_code"] == "M1805"
    assert rows[0]["geography_name"] == "Paris"
    assert rows[0]["dimensions"]["sector_code"] == "62"

def test_france_travail_offers_are_aggregated_by_job_territory_sector_and_skill():
    offer={"romeCode":"M1805","romeLibelle":"Études et développement informatique",
        "appellationlibelle":"Développeur / Développeuse web","dateCreation":"2026-09-12T10:00:00Z",
        "lieuTravail":{"commune":"75101","libelle":"Paris 1er"},"secteurActivite":"62",
        "secteurActiviteLibelle":"Programmation informatique","competences":[{"code":"120025","libelle":"Python"}],
        "salaire":{"minimum":35000,"maximum":45000,"unite":"EUR/year"}}
    payload={"_skillor_kind":"offers","resultats":[offer,offer]}
    rows=FranceTravailConnector().normalize(payload)
    by_metric={row["metric"]:row for row in rows}
    assert by_metric["job_offers"]["value"] == 2
    assert by_metric["skill_offer_mentions"]["value"] == 2
    assert by_metric["salary_min"]["value"] == 35000
    assert by_metric["salary_max"]["value"] == 45000

def test_france_travail_parses_salary_label_without_including_month_count():
    payload={"_skillor_kind":"offers","resultats":[{"romeCode":"M1805","dateCreation":"2026-09-12",
        "salaire":{"libelle":"Mensuel de 2 500,50 Euros à 3 000 Euros sur 12 mois"}}]}
    by_metric={row["metric"]:row for row in FranceTravailConnector().normalize(payload)}
    assert by_metric["salary_min"]["value"] == 2500.5
    assert by_metric["salary_max"]["value"] == 3000
    assert by_metric["salary_min"]["unit"] == "EUR/month"

def test_official_rome_esco_crosswalk_parser_skips_metadata_header():
    csv_text="""Mapping project name,ESCO - ROME\nClassification 1 Version,1.1\n\nclassification 1 ID,classification 1 prefered label,classification 2 ID,classification 2 prefered label,mapping relation\nhttp://data.europa.eu/esco/occupation/abc,développeur,12345,Développeur / Développeuse web,skos:exactMatch\n"""
    rows=parse_rome_esco_crosswalk(csv_text)
    assert rows == [{"esco_uri":"http://data.europa.eu/esco/occupation/abc","esco_label":"développeur",
        "external_code":"12345","external_label":"Développeur / Développeuse web",
        "mapping_relation":"skos:exactMatch","confidence_score":1.0}]
