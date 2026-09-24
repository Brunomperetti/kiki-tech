from sqlalchemy import select
from sqlalchemy.orm import Session
from ..database.models import CatalogSnapshot, ImportJobRecord, ReconciliationRun
class CatalogRepository:
    def __init__(self, db: Session): self.db=db
    def save_snapshot(self, source: str, payload: list[dict]):
        item=self.db.scalar(select(CatalogSnapshot).where(CatalogSnapshot.source==source))
        if item: item.payload=payload
        else: self.db.add(CatalogSnapshot(source=source,payload=payload))
        self.db.commit()
    def snapshot(self, source: str) -> list[dict]:
        item=self.db.scalar(select(CatalogSnapshot).where(CatalogSnapshot.source==source)); return item.payload if item else []
    def add_job(self, job: ImportJobRecord): self.db.add(job); self.db.commit(); self.db.refresh(job); return job
    def jobs(self): return list(self.db.scalars(select(ImportJobRecord).order_by(ImportJobRecord.id.desc())))
    def latest_jobs_by_source(self):
        jobs=self.jobs(); seen=set(); result=[]
        for job in jobs:
            if job.source not in seen: result.append(job); seen.add(job.source)
        return result
    def add_run(self, run: ReconciliationRun): self.db.add(run); self.db.commit(); self.db.refresh(run); return run
    def latest_run(self): return self.db.scalar(select(ReconciliationRun).order_by(ReconciliationRun.id.desc()).limit(1))
