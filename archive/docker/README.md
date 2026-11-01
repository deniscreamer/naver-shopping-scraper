# archive/docker: retired Docker setup

Not maintained. The supported platform is macOS (see [server/README.md](../../server/README.md#macos)).
These are the upstream files the server shipped with, kept for the day a Linux deployment is needed again.

| File | What it was |
|---|---|
| `Dockerfile` | Image on `chetan1111/botasaurus:chrome-151` (ships Google Chrome and Xvfb), `pip install -r requirements.txt`, `CMD python run.py` in `/app`. Build context must be `server/`. |
| `.dockerignore` | Must sit at the root of the build context (`server/`) to apply. |
| `docker-compose.yaml` | One service on port 8000 with `shm_size: 1gb`; `build: ./server` assumes it sits at the repo root. |

Why the server still works in a container without code changes: on Linux without `DISPLAY` the driver starts a
shared Xvfb (`patchright_driver._ensure_display`), and inside a container the Chrome channel is forced to `chrome`
(`patchright_driver._in_container`), so the image's Google Chrome runs headed on the virtual display.

## Restore

```bash
git mv archive/docker/Dockerfile archive/docker/.dockerignore server/
git mv archive/docker/docker-compose.yaml .
docker compose up --build        # or: docker build -t naver-shopping server
```

Then re-add Docker to `server/README.md`, record a decision entry in `server/docs/DEVELOPMENT_RULES.md`, and run the
live smoke (`scripts/smoke_endpoints.py`) against the container: the files were last verified with the upstream
layout, not since the move to `server/`.
