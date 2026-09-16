import asyncio
import json
import logging
import signal
import time
from datetime import timedelta

from sqlalchemy import select, update

from app.config import get_settings
from app.db import Session, engine
from app.models import WebhookLog, now
from app.outbound import DeliveryError, build_payload, complete, deliver
from app.security import decrypt
from app.templates import context_for, render

logger = logging.getLogger("station.worker")
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)


async def claim_job() -> str | None:
    async with Session.begin() as db:
        # FOR UPDATE SKIP LOCKED allows multiple worker containers safely.
        job = await db.scalar(
            select(WebhookLog)
            .where(WebhookLog.status == "pending")
            .order_by(WebhookLog.received_at)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if job is None:
            return None
        job.status = "processing"
        job.started_at = now()
        job.attempts += 1
        return job.id


async def process_job(job_id: str) -> None:
    started = time.monotonic()
    async with Session() as db:
        job = await db.get(WebhookLog, job_id)
        if job is None or job.status != "processing":
            return
        try:
            async with asyncio.timeout(150):
                config = json.loads(decrypt(job.config_snapshot))
                context = context_for(config, job.input_payload, job.event)
                source = render(config["source_template"], context)
                job.llm_output = (
                    await complete(config, source, job.trace_id)
                    if config["llm_enabled"]
                    else source
                )
                context["llm_output"] = job.llm_output
                job.output_payload = build_payload(
                    config["target_type"],
                    render(config["target_template"], context),
                    config.get("target_mentions"),
                )
                # Persist output before external side effect, even if the worker dies mid-send.
                await db.commit()
                job.target_response = await deliver(config, job.output_payload, job.trace_id)
                job.output_at = now()
                job.status = "succeeded"
                job.error = None
        except Exception as exc:
            job.status = "failed"
            job.error = (
                str(exc) if isinstance(exc, DeliveryError) else f"处理失败：{type(exc).__name__}"
            )
        job.finished_at = now()
        job.cost_ms = int((time.monotonic() - started) * 1000)
        await db.commit()
        logger.info(
            "delivery trace_id=%s log_id=%s status=%s cost_ms=%s",
            job.trace_id,
            job.id,
            job.status,
            job.cost_ms,
        )


async def recover_stale_jobs() -> None:
    cutoff = now() - timedelta(seconds=get_settings().worker_lease_seconds)
    async with Session.begin() as db:
        await db.execute(
            update(WebhookLog)
            .where(WebhookLog.status == "processing", WebhookLog.started_at < cutoff)
            .values(
                status="failed",
                finished_at=now(),
                error="worker 中断或超时，投递结果未知；确认目标后手动重试",
            )
        )


async def run() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    stopping = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stopping.set)

    async def pause(seconds: float):
        try:
            await asyncio.wait_for(stopping.wait(), timeout=seconds)
        except TimeoutError:
            pass

    try:
        while not stopping.is_set():
            try:
                await recover_stale_jobs()
                job_id = await claim_job()
                if job_id:
                    await process_job(job_id)
                else:
                    await pause(get_settings().worker_poll_seconds)
            except Exception as exc:
                logger.error("worker_iteration_failed error_type=%s", type(exc).__name__)
                await pause(5)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(run())
