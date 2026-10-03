import argparse, asyncio
from app.db import Base, SessionLocal, engine
from app.services.ingestion import run_import
from app.services.occupation_mapping import sync_rome_esco_crosswalk
from app.services.seed import seed_database

def main():
    parser=argparse.ArgumentParser(prog="skillor")
    sub=parser.add_subparsers(dest="command",required=True)
    sub.add_parser("seed")
    sync=sub.add_parser("sync"); sync.add_argument("source",choices=["esco","eurostat","france_travail"]); sync.add_argument("--query",default="data"); sync.add_argument("--limit",type=int,default=50); sync.add_argument("--max-relation-skills",type=int,default=None); sync.add_argument("--dataset",choices=["market","offers"],default="market"); sync.add_argument("--territory",default="FR"); sync.add_argument("--rome-code",default=None); sync.add_argument("--endpoint",default="indicateurs")
    crosswalk=sub.add_parser("sync-rome-esco"); crosswalk.add_argument("--url",default=None)
    args=parser.parse_args(); Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        if args.command=="seed": seed_database(db); print("Jeu initial chargé")
        elif args.command=="sync-rome-esco":
            result=asyncio.run(sync_rome_esco_crosswalk(db,args.url)); print(f"Crosswalk ROME–ESCO: {result['stored']} correspondances actives, {result['skipped_missing_esco']} sans métier ESCO local")
        else:
            job=asyncio.run(run_import(db,args.source,query=args.query,limit=args.limit,max_relation_skills=args.max_relation_skills,dataset=args.dataset,territory=args.territory,rome_code=args.rome_code,endpoint=args.endpoint)); print(f"{job.status}: {job.records_stored} lignes, job={job.id}")

if __name__=="__main__": main()
