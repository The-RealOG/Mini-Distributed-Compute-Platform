"""
Job Runner Service

Executes Linux commands in isolated processes and returns results.
"""

import logging
import subprocess
import sys
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

# Configure structured logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = FastAPI(title="Mini Distributed Compute Platform - Runner")

# Metrics
metrics = {
    "executions_total": 0,
    "executions_failed_total": 0,
    "executions_success_total": 0,
}


class ExecuteRequest(BaseModel):
    command: str = Field(..., description="Linux command to execute")
    timeout: int = Field(default=30, ge=1, le=300, description="Timeout in seconds")


class ExecuteResponse(BaseModel):
    exit_code: int
    stdout: str
    stderr: str
    runtime_ms: int


def execute_command(command: str, timeout: int) -> ExecuteResponse:
    """
    Execute a Linux command using subprocess.
    
    Args:
        command: The command to execute
        timeout: Maximum execution time in seconds
        
    Returns:
        ExecuteResponse with exit code, stdout, stderr, and runtime
    """
    import time
    
    start_time = time.time()
    
    try:
        # Execute command with timeout
        # Use shell=True for command parsing, but with proper timeout handling
        process = subprocess.Popen(
            command,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1
        )
        
        try:
            stdout, stderr = process.communicate(timeout=timeout)
            exit_code = process.returncode
        except subprocess.TimeoutExpired:
            process.kill()
            stdout, stderr = process.communicate()
            exit_code = -1
            stderr = f"Command timed out after {timeout} seconds\n{stderr}"
        
        runtime_ms = int((time.time() - start_time) * 1000)
        
        # Update metrics
        metrics["executions_total"] += 1
        if exit_code == 0:
            metrics["executions_success_total"] += 1
        else:
            metrics["executions_failed_total"] += 1
        
        logger.info(
            f"Command executed: {command[:50]}... "
            f"Exit code: {exit_code}, Runtime: {runtime_ms}ms"
        )
        
        return ExecuteResponse(
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            runtime_ms=runtime_ms
        )
        
    except Exception as e:
        runtime_ms = int((time.time() - start_time) * 1000)
        metrics["executions_total"] += 1
        metrics["executions_failed_total"] += 1
        
        logger.error(f"Error executing command '{command}': {e}")
        
        return ExecuteResponse(
            exit_code=-1,
            stdout="",
            stderr=f"Execution error: {str(e)}",
            runtime_ms=runtime_ms
        )


@app.post("/execute", response_model=ExecuteResponse)
async def execute(request: ExecuteRequest):
    """
    Execute a Linux command.
    
    This endpoint accepts a command and executes it using subprocess.
    Commands are executed with a timeout to prevent runaway processes.
    """
    # Basic input validation
    if not request.command or not request.command.strip():
        raise HTTPException(status_code=400, detail="Command cannot be empty")
    
    # Log the execution request
    logger.info(f"Received execution request: {request.command[:100]}")
    
    # Execute the command
    result = execute_command(request.command, request.timeout)
    
    return result


@app.get("/metrics", response_class=PlainTextResponse)
async def get_metrics():
    """Prometheus-style metrics endpoint."""
    prom_metrics = f"""# HELP executions_total Total number of command executions
# TYPE executions_total counter
executions_total {metrics['executions_total']}

# HELP executions_success_total Total number of successful executions
# TYPE executions_success_total counter
executions_success_total {metrics['executions_success_total']}

# HELP executions_failed_total Total number of failed executions
# TYPE executions_failed_total counter
executions_failed_total {metrics['executions_failed_total']}
"""
    
    return prom_metrics


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "runner"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
