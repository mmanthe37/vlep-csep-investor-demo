import os
from celery import Celery

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery(
    "vlep_worker",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=["vlep.tasks"]
)

celery_app.conf.task_routes = {
    "vlep.tasks.io_*": {"queue": "io_bound"},
    "vlep.tasks.nlp_*": {"queue": "gpu_heavy"},
    "vlep.tasks.csep_*": {"queue": "gpu_heavy"},
    "*": {"queue": "default"},
}

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    worker_prefetch_multiplier=1, # Better for long-running NLP tasks
    task_acks_late=True # Only ack after successful completion
)

@celery_app.task(name="vlep.tasks.io_fetch_fhir")
def io_fetch_fhir(patient_id: str):
    return {"status": "success", "patient_id": patient_id}

@celery_app.task(name="vlep.tasks.nlp_phenotyping")
def nlp_phenotyping(text: str):
    return {"status": "success", "phenotype": "extracted"}
