# Mini Distributed Compute Platform

A lightweight, containerized job-execution platform that runs Linux workloads, exposes metrics, logs executions, and is designed to scale from a laptop to the cloud.

Think of it as "Slurm-lite for containers" — a minimal distributed compute platform that demonstrates core systems engineering principles.

## What This System Does

This platform provides:

- **Job Execution**: Execute arbitrary Linux commands in isolated containers
- **Job Orchestration**: A coordinator service dispatches jobs to runner instances
- **Observability**: Structured logging and Prometheus-style metrics
- **Scalability**: Designed to scale from a single machine to Kubernetes clusters

## Architecture

### High-Level Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         Client Layer                                     │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐                  │
│  │   curl/CLI   │  │  HTTP Client │  │  API Client  │                  │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘                  │
└─────────┼──────────────────┼──────────────────┼─────────────────────────┘
          │                  │                  │
          │  HTTP/REST       │                  │
          │  Port 8000       │                  │
          │                  │                  │
┌─────────▼──────────────────▼──────────────────▼─────────────────────────┐
│                    Coordinator Service                                  │
│                    (FastAPI / Python 3.11+)                             │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │                    API Endpoints                                │   │
│  │  • POST /jobs          - Submit new job                         │   │
│  │  • GET  /jobs/{id}     - Query job status                       │   │
│  │  • GET  /metrics       - Prometheus metrics                     │   │
│  │  • GET  /health        - Health check                           │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                                                                          │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │              Job Management Layer                                │   │
│  │  • Job Queue (in-memory dict)                                    │   │
│  │  • Job State Machine: pending → running → completed/failed      │   │
│  │  • Async job dispatch (asyncio.create_task)                     │   │
│  │  • Job tracking with UUIDs                                      │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                                                                          │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │                    Metrics & Observability                       │   │
│  │  • jobs_total, jobs_completed_total, jobs_failed_total          │   │
│  │  • job_runtime_seconds (histogram)                               │   │
│  │  • Structured logging (stdout)                                   │   │
│  └──────────────────────────────────────────────────────────────────┘   │
└─────────┬───────────────────────────────────────────────────────────────┘
          │
          │  HTTP POST /execute
          │  (httpx.AsyncClient)
          │  Port 8080
          │
┌─────────▼───────────────────────────────────────────────────────────────┐
│                    Runner Service                                        │
│                    (FastAPI / Python 3.11+)                             │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │                    API Endpoints                                │   │
│  │  • POST /execute      - Execute Linux command                    │   │
│  │  • GET  /metrics     - Execution metrics                         │   │
│  │  • GET  /health      - Health check                             │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                                                                          │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │              Execution Engine                                     │   │
│  │  • subprocess.Popen (shell=True)                                 │   │
│  │  • Timeout enforcement (subprocess.communicate)                  │   │
│  │  • Process isolation (container boundaries)                      │   │
│  │  • stdout/stderr capture                                         │   │
│  │  • Exit code tracking                                            │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                                                                          │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │                    Metrics & Observability                       │   │
│  │  • executions_total, executions_success_total                    │   │
│  │  • executions_failed_total                                       │   │
│  │  • Structured logging (stdout)                                    │   │
│  └──────────────────────────────────────────────────────────────────┘   │
└─────────┬───────────────────────────────────────────────────────────────┘
          │
          │  subprocess execution
          │
┌─────────▼───────────────────────────────────────────────────────────────┐
│                    Linux Process Layer                                   │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │              Isolated Process Execution                          │   │
│  │  • Command execution (shell=True)                                 │   │
│  │  • Resource limits (Docker cgroups)                              │   │
│  │  • Timeout handling                                              │   │
│  │  • Output capture (stdout/stderr)                                │   │
│  └──────────────────────────────────────────────────────────────────┘   │
└───────────────────────────────────────────────────────────────────────────┘
```

### Container Architecture
<img width="2122" height="1840" alt="image" src="https://github.com/user-attachments/assets/4b5e27a0-fcd4-42cc-97e3-514b00ec50ee" />



### Data Flow

```
┌─────────┐
│ Client  │
└────┬────┘
     │
     │ 1. POST /jobs {"command": "uname -a", "timeout": 30}
     │
┌────▼──────────────────────────────────────────────────────────────┐
│ Coordinator                                                       │
│  • Generate UUID (job_id)                                        │
│  • Store job in memory: {job_id, status: "pending", ...}         │
│  • Increment jobs_total metric                                    │
│  • Return JobResponse {job_id, status: "pending"}                │
│                                                                   │
│  • Async dispatch: asyncio.create_task(execute_job(...))         │
│    └─> Update status: "pending" → "running"                       │
└────┬──────────────────────────────────────────────────────────────┘
     │
     │ 2. POST http://runner:8080/execute
     │    {"command": "uname -a", "timeout": 30}
     │
┌────▼──────────────────────────────────────────────────────────────┐
│ Runner                                                            │
│  • Validate request                                               │
│  • Execute: subprocess.Popen(command, shell=True)                │
│  • Monitor with timeout (subprocess.communicate)                  │
│  • Capture stdout/stderr                                          │
│  • Track exit_code                                                │
│  • Update metrics (executions_total, etc.)                        │
│  • Return ExecuteResponse {exit_code, stdout, stderr, runtime_ms}│
└────┬──────────────────────────────────────────────────────────────┘
     │
     │ 3. HTTP Response {exit_code: 0, stdout: "...", ...}
     │
┌────▼──────────────────────────────────────────────────────────────┐
│ Coordinator                                                       │
│  • Update job status: "running" → "completed"/"failed"          │
│  • Store results: {exit_code, stdout, stderr, runtime_ms}        │
│  • Update metrics:                                                │
│    - jobs_completed_total or jobs_failed_total                   │
│    - job_runtimes.append(runtime_ms)                             │
│  • Log completion                                                 │
└────────────────────────────────────────────────────────────────────┘
     │
     │ 4. GET /jobs/{job_id}
     │
┌────▼────┐
│ Client  │ ← Returns full job status with results
└─────────┘
```

### Component Responsibilities

#### Coordinator Service
- **API Gateway**: Exposes REST API for job submission and status queries
- **Job Orchestration**: Manages job lifecycle (pending → running → completed/failed)
- **Service Discovery**: Discovers runner instances via `RUNNER_URL` environment variable
- **State Management**: Maintains in-memory job store
- **Metrics Aggregation**: Collects and exposes Prometheus-style metrics
- **Error Handling**: Manages timeouts, network failures, and runner unavailability

#### Runner Service
- **Command Execution**: Executes Linux commands in isolated subprocesses
- **Process Management**: Handles timeouts, process termination, and resource limits
- **Output Capture**: Captures stdout/stderr streams
- **Metrics Collection**: Tracks execution metrics (success/failure rates, runtimes)
- **Health Reporting**: Exposes health check endpoint for orchestration

#### Infrastructure Layer
- **Containerization**: Docker containers provide isolation and resource limits
- **Networking**: Docker bridge network enables service-to-service communication
- **Resource Management**: CPU and memory limits enforced via Docker cgroups
- **Health Monitoring**: Health checks enable automatic recovery and load balancing

### Components

1. **Coordinator Service**: FastAPI-based service that accepts job requests, dispatches them to runners, and tracks job status
2. **Runner Service**: Executes Linux commands using subprocess, captures output, and reports results back
3. **Docker Infrastructure**: Both services run in containers with proper isolation and resource limits

## Why This Exists

This project demonstrates:

- **Systems Engineering**: Process management, inter-service communication, resource isolation
- **Platform Engineering**: Containerization, orchestration, observability
- **Linux Familiarity**: Direct interaction with OS primitives, subprocess execution
- **Cloud Readiness**: Designed with Kubernetes deployment in mind

## To Execute this program

### Prerequisites

- Docker and Docker Compose
- Python 3.11+ (for local development)

### Running the Platform

```bash
# Start all services
docker-compose up --build

# In another terminal, submit a job
curl -X POST http://localhost:8000/jobs \
  -H "Content-Type: application/json" \
  -d '{"command": "echo hello world"}'

# Check job status
curl http://localhost:8000/jobs/{job_id} #a job id should be generated after you've submitted a curl request

# View metrics
curl http://localhost:8000/metrics
```

### Local Development

```bash
# Coordinator
cd coordinator
pip install -r requirements.txt
uvicorn main:app --reload --port 8000

# Runner (in another terminal)
cd runner
pip install -r requirements.txt
python main.py
```

## API Reference

### Submit a Job

```bash
POST /jobs
Content-Type: application/json

{
  "command": "uname -a",
  "timeout": 30
}
```

Response:
```json
{
  "job_id": "abc123",
  "status": "pending",
  "created_at": "2024-01-01T00:00:00Z"
}
```

### Get Job Status

```bash
GET /jobs/{job_id}
```

Response:
```json
{
  "job_id": "abc123",
  "status": "completed",
  "exit_code": 0,
  "stdout": "Linux hostname 5.4.0...",
  "stderr": "",
  "runtime_ms": 45
}
```

### Metrics Endpoint

```bash
GET /metrics
```

Returns Prometheus-style metrics:
```
# HELP jobs_total Total number of jobs processed
# TYPE jobs_total counter
jobs_total 42

# HELP jobs_failed_total Total number of failed jobs
# TYPE jobs_failed_total counter
jobs_failed_total 2

# HELP job_runtime_seconds Average job runtime in seconds
# TYPE job_runtime_seconds histogram
job_runtime_seconds_bucket{le="0.1"} 10
job_runtime_seconds_bucket{le="1.0"} 35
```

## Scaling to Kubernetes / Cloud

### Current Design (Local)

- Docker Compose orchestrates services
- Direct HTTP communication between coordinator and runners
- In-memory job tracking

### Production Deployment (Kubernetes)

1. **Service Discovery**: Use Kubernetes Services for runner discovery
2. **Job Queue**: Replace in-memory queue with Redis/RabbitMQ
3. **State Management**: Use PostgreSQL for job persistence
4. **Autoscaling**: Kubernetes HPA based on queue depth
5. **Security**: Network policies, pod security policies, RBAC
6. **Monitoring**: Prometheus + Grafana for metrics visualization
7. **Logging**: Centralized logging with ELK stack or Loki

### Cloud Provider Considerations

**AWS**:
- ECS/EKS for orchestration
- SQS for job queue
- CloudWatch for metrics/logs
- IAM roles for service authentication

**Azure**:
- AKS for orchestration
- Service Bus for job queue
- Azure Monitor for metrics/logs
- Managed Identity for authentication

## Cross-Functional Considerations

### Security

- **Sandboxing**: Jobs run in isolated containers with resource limits
- **Input Validation**: Command sanitization and timeout enforcement
- **Network Isolation**: Containers run on isolated networks
- **Future**: Implement user namespaces, seccomp profiles, AppArmor policies

### Infrastructure

- **Autoscaling**: Design supports horizontal scaling of runners
- **Resource Management**: CPU/memory limits per container
- **High Availability**: Coordinator can be replicated behind load balancer
- **Future**: Implement health checks, graceful shutdown, circuit breakers

### Product

- **Job Priority**: Current FIFO queue, extensible to priority queues
- **Fairness**: Round-robin dispatch to runners
- **SLA Tracking**: Metrics expose job completion times
- **Future**: Implement job priorities, quotas, rate limiting

## Development

### Project Structure

```
mini-platform/
├── coordinator/          # Coordinator service
│   ├── main.py          # FastAPI application
│   ├── Dockerfile       # Container definition
│   └── requirements.txt # Python dependencies
├── runner/              # Runner service
│   ├── main.py         # Job execution logic
│   ├── Dockerfile      # Container definition
│   └── requirements.txt # Python dependencies
├── docker-compose.yml   # Local orchestration
├── .github/
│   └── workflows/
│       └── ci.yml      # CI/CD pipeline
└── README.md           # This file
```

### Testing

```bash
# Run tests
docker-compose up -d
pytest tests/

# Manual testing
curl -X POST http://localhost:8000/jobs \
  -H "Content-Type: application/json" \
  -d '{"command": "cat /proc/cpuinfo"}'
```
