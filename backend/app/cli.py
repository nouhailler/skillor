import argparse, asyncio
from app.db import Base, SessionLocal, engine
from app.services.ingestion import run_eurostat_catalog_import, run_import
from app.services.occupation_mapping import sync_rome_esco_crosswalk
from app.services.seed import seed_database
from app.services.search import rebuild_search_index
from app.services.trend_analytics import recompute_skill_trends

def main():
    parser=argparse.ArgumentParser(prog="skillor")
    sub=parser.add_subparsers(dest="command",required=True)
    sub.add_parser("seed")
    sub.add_parser("reindex-search")
    sub.add_parser("recompute-trends")
    sync=sub.add_parser("sync"); sync.add_argument("source",choices=["esco","eurostat","france_travail"]); sync.add_argument("--query",default="data"); sync.add_argument("--limit",type=int,default=50); sync.add_argument("--max-relation-skills",type=int,default=None); sync.add_argument("--dataset",default=None); sync.add_argument("--profile",default=None); sync.add_argument("--territory",default="FR"); sync.add_argument("--geography",default="FR"); sync.add_argument("--since",type=int,default=2021); sync.add_argument("--rome-code",default=None); sync.add_argument("--endpoint",default="indicateurs")
    eurostat=sub.add_parser("sync-eurostat"); eurostat.add_argument("--profiles",default="all"); eurostat.add_argument("--geography",default="FR"); eurostat.add_argument("--since",type=int,default=2021)
    crosswalk=sub.add_parser("sync-rome-esco"); crosswalk.add_argument("--url",default=None)
    args=parser.parse_args(); Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        if args.command=="seed": seed_database(db); print("Jeu initial chargé")
        elif args.command=="reindex-search": print(f"Index de recherche: {rebuild_search_index(db)} termes")
        elif args.command=="recompute-trends":
            result=recompute_skill_trends(db); print(f"TrendScore {result['method_version']}: {result['scores_written']} scores, {result['skills_scored']}/{result['skills_evaluated']} compétences")
        elif args.command=="sync-rome-esco":
            result=asyncio.run(sync_rome_esco_crosswalk(db,args.url)); print(f"Crosswalk ROME–ESCO: {result['stored']} correspondances actives, {result['skipped_missing_esco']} sans métier ESCO local")
        elif args.command=="sync-eurostat":
            jobs=asyncio.run(run_eurostat_catalog_import(db,args.profiles,args.geography,args.since)); print("Eurostat: "+", ".join(f"{job.parameters.get('profile')}={job.status}({job.records_stored})" for job in jobs))
        else:
            job=asyncio.run(run_import(db,args.source,query=args.query,limit=args.limit,max_relation_skills=args.max_relation_skills,dataset=args.dataset,profile=args.profile,territory=args.territory,geography=args.geography,since=args.since,rome_code=args.rome_code,endpoint=args.endpoint)); print(f"{job.status}: {job.records_stored} lignes, job={job.id}")

if __name__=="__main__": main()
