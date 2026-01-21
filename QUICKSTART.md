# How to run the program

## Why Builds Might Be Slow

The first time you build Docker images, Docker needs to:
1. Download the base Python image (roughly 50MB)
2. Download and install Python packages
3. Create the container layers

**First build**: Approximately 2 - 5 minutes (depending on internet speed)
**Subsequent builds**: Approximately 10 - 30 seconds (cached layers)


### Build and Run

```bash
cd mini-platform

# Build images (first time: 2-5 min, subsequent: ~30 sec)
docker-compose build

# Start services (takes ~10 seconds)
docker-compose up -d

# Check logs
docker-compose logs -f

# Test it
curl -X POST http://localhost:8000/jobs \
  -H "Content-Type: application/json" \
  -d '{"command": "echo hello world"}'
```

## Troubleshooting

**If your build is stuck?**
- Check your internet connection (downloading base images)
- Check Docker has enough resources: Docker Desktop → Settings → Resources

**Services won't start?**
- Check that ports 8000 and 8080 aren't already in use
- Check logs: `docker-compose logs`

**Want to see what's taking time?**
```bash
# Build with verbose output
docker-compose build --progress=plain
```
