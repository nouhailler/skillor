import argparse, asyncio
from app.db import Base, SessionLocal, engine
from app.services.ingestion import run_import
from app.services.seed import seed_database

def main():
    parser=argparse.ArgumentParser(prog="skillor")
    sub=parser.add_subparsers(dest="command",required=True)
    sub.add_parser("seed")
    sync=sub.add_parser("sync"); sync.add_argument("source",choices=["esco","eurostat","france_travail"]); sync.add_argument("--query",default="data"); sync.add_argument("--limit",type=int,default=50); sync.add_argument("--max-relation-skills",type=int,default=None)
    args=parser.parse_args(); Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        if args.command=="seed": seed_database(db); print("Jeu initial chargé")
        else:
            job=asyncio.run(run_import(db,args.source,query=args.query,limit=args.limit,max_relation_skills=args.max_relation_skills)); print(f"{job.status}: {job.records_stored} lignes, job={job.id}")

if __name__=="__main__": main()
