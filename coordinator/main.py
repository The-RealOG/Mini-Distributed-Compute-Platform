"""
Coordinator Service

Dispatches jobs to runner instances and tracks their status.
"""

import asyncio
import logging
import os
import time
from datetime import datetime
from typing import Dict, Optional
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

# Configure structured logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = FastAPI(title="Mini Distributed Compute Platform - Coordinator")

# In-memory job store (in production, use Redis/PostgreSQL)
jobs: Dict[str, Dict] = {}

# Metrics
metrics = {
    "jobs_total": 0,
    "jobs_failed_total": 0,
    "jobs_completed_total": 0,
    "job_runtimes": [],  # List of runtime in seconds
}

# Get runner URL from environment or use default
RUNNER_URL = os.getenv("RUNNER_URL", "http://runner:8080")


class JobRequest(BaseModel):
    command: str = Field(..., description="Linux command to execute")
    timeout: int = Field(default=30, ge=1, le=300, description="Timeout in seconds")


class JobResponse(BaseModel):
    job_id: str
    status: str
    created_at: str


class JobStatus(BaseModel):
    job_id: str
    status: str
    exit_code: Optional[int] = None
    stdout: Optional[str] = None
    stderr: Optional[str] = None
    runtime_ms: Optional[int] = None
    created_at: str
    completed_at: Optional[str] = None


@app.post("/jobs", response_model=JobResponse)
async def submit_job(job_request: JobRequest):
    """Submit a new job for execution."""
    job_id = str(uuid4())
    
    job_data = {
        "job_id": job_id,
        "command": job_request.command,
        "timeout": job_request.timeout,
        "status": "pending",
        "created_at": datetime.utcnow().isoformat() + "Z",
        "completed_at": None,
        "exit_code": None,
        "stdout": None,
        "stderr": None,
        "runtime_ms": None
    }
    
    jobs[job_id] = job_data
    metrics["jobs_total"] += 1
    
    logger.info(f"Job {job_id} submitted: {job_request.command}")
    
    # Dispatch job asynchronously
    asyncio.create_task(execute_job(job_id, job_request))
    
    return JobResponse(
        job_id=job_id,
        status="pending",
        created_at=job_data["created_at"]
    )


async def execute_job(job_id: str, job_request: JobRequest):
    """Execute job by dispatching to runner."""
    import httpx
    
    start_time = time.time()
    jobs[job_id]["status"] = "running"
    
    try:
        async with httpx.AsyncClient(timeout=job_request.timeout + 5) as client:
            response = await client.post(
                f"{RUNNER_URL}/execute",
                json={"command": job_request.command, "timeout": job_request.timeout},
                timeout=job_request.timeout + 5
            )
            response.raise_for_status()
            result = response.json()
            
            runtime_ms = int((time.time() - start_time) * 1000)
            
            jobs[job_id].update({
                "status": "completed" if result["exit_code"] == 0 else "failed",
                "exit_code": result["exit_code"],
                "stdout": result.get("stdout", ""),
                "stderr": result.get("stderr", ""),
                "runtime_ms": runtime_ms,
                "completed_at": datetime.utcnow().isoformat() + "Z"
            })
            
            # Update metrics
            if result["exit_code"] != 0:
                metrics["jobs_failed_total"] += 1
            else:
                metrics["jobs_completed_total"] += 1
            
            runtime_seconds = runtime_ms / 1000.0
            metrics["job_runtimes"].append(runtime_seconds)
            # Keep only last 1000 runtimes for memory efficiency
            if len(metrics["job_runtimes"]) > 1000:
                metrics["job_runtimes"] = metrics["job_runtimes"][-1000:]
            
            logger.info(
                f"Job {job_id} completed with exit code {result['exit_code']} "
                f"in {runtime_ms}ms"
            )
            
    except httpx.TimeoutException:
        jobs[job_id].update({
            "status": "failed",
            "exit_code": -1,
            "stderr": "Job execution timeout",
            "runtime_ms": int((time.time() - start_time) * 1000),
            "completed_at": datetime.utcnow().isoformat() + "Z"
        })
        metrics["jobs_failed_total"] += 1
        logger.error(f"Job {job_id} timed out")
        
    except Exception as e:
        jobs[job_id].update({
            "status": "failed",
            "exit_code": -1,
            "stderr": str(e),
            "runtime_ms": int((time.time() - start_time) * 1000),
            "completed_at": datetime.utcnow().isoformat() + "Z"
        })
        metrics["jobs_failed_total"] += 1
        logger.error(f"Job {job_id} failed: {e}")


@app.get("/jobs/{job_id}", response_model=JobStatus)
async def get_job_status(job_id: str):
    """Get the status of a job."""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    
    job = jobs[job_id]
    return JobStatus(**job)


@app.get("/metrics", response_class=PlainTextResponse)
async def get_metrics():
    """Prometheus-style metrics endpoint."""
    # Calculate average runtime
    avg_runtime = 0.0
    if metrics["job_runtimes"]:
        avg_runtime = sum(metrics["job_runtimes"]) / len(metrics["job_runtimes"])
    
    # Generate Prometheus format metrics
    prom_metrics = f"""# HELP jobs_total Total number of jobs processed
# TYPE jobs_total counter
jobs_total {metrics['jobs_total']}

# HELP jobs_completed_total Total number of completed jobs
# TYPE jobs_completed_total counter
jobs_completed_total {metrics['jobs_completed_total']}

# HELP jobs_failed_total Total number of failed jobs
# TYPE jobs_failed_total counter
jobs_failed_total {metrics['jobs_failed_total']}

# HELP jobs_pending_total Total number of pending jobs
# TYPE jobs_pending_total gauge
jobs_pending_total {sum(1 for j in jobs.values() if j['status'] == 'pending')}

# HELP jobs_running_total Total number of running jobs
# TYPE jobs_running_total gauge
jobs_running_total {sum(1 for j in jobs.values() if j['status'] == 'running')}

# HELP job_runtime_seconds Average job runtime in seconds
# TYPE job_runtime_seconds gauge
job_runtime_seconds {avg_runtime:.3f}

# HELP job_runtime_seconds_total Sum of all job runtimes
# TYPE job_runtime_seconds_total counter
job_runtime_seconds_total {sum(metrics['job_runtimes']):.3f}
"""
    
    return prom_metrics


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "coordinator"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
