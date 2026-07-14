import json
from datetime import datetime, timezone

from app.core.settings import settings
from app.models.job import Job, Progress
from app.services.job_service import JobService


def _make_job(job_id: str) -> Job:
    now = datetime.now(timezone.utc)
    return Job(
        id=job_id,
        filename="demo.mp4",
        processing_mode="screen",
        status="queued",
        created_at=now,
        updated_at=now,
    )


def test_subscribers_receive_job_updates(tmp_path) -> None:
    settings.storage_path = str(tmp_path)
    service = JobService()
    service._jobs["job-sse"] = _make_job("job-sse")

    subscriber = service.subscribe()
    with service._lock:
        job = service._jobs["job-sse"]
        job.status = "processing"
        job.progress = Progress(percent=42, message="Halfway there.")
        job.updated_at = datetime.now(timezone.utc)
        service._save_jobs()

    frame = subscriber.get(timeout=1.0)
    assert frame.startswith("data: ") and frame.endswith("\n\n")
    event = json.loads(frame.removeprefix("data: "))
    assert event["id"] == "job-sse"
    assert event["status"] == "processing"
    assert event["progress"]["percent"] == 42

    service.unsubscribe(subscriber)
    with service._lock:
        service._jobs["job-sse"].updated_at = datetime.now(timezone.utc)
        service._save_jobs()
    assert subscriber.empty()


def test_subscribers_receive_deletion_events(tmp_path) -> None:
    settings.storage_path = str(tmp_path)
    service = JobService()
    service._jobs["job-gone"] = _make_job("job-gone")
    service._save_jobs()

    subscriber = service.subscribe()
    assert service.delete_job("job-gone") is True

    frame = subscriber.get(timeout=1.0)
    assert frame.startswith("event: deleted\n")
    payload = json.loads(frame.split("data: ", 1)[1])
    assert payload["id"] == "job-gone"


def test_full_subscriber_queue_does_not_block_saves(tmp_path) -> None:
    settings.storage_path = str(tmp_path)
    service = JobService()
    service._jobs["job-full"] = _make_job("job-full")

    subscriber = service.subscribe()
    for _ in range(120):  # exceed the queue's maxsize
        with service._lock:
            service._jobs["job-full"].updated_at = datetime.now(timezone.utc)
            service._save_jobs()

    assert subscriber.qsize() <= 100
    service.unsubscribe(subscriber)
