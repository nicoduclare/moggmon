# Podman Notes

Podman is optional for Mogger Mon development. The normal local path is:

```bash
pnpm install
pnpm start:dev
```

If you prefer a containerized shell, build the local image and mount the repo:

```bash
podman build -t mogger-mon -f Dockerfile .
podman run --rm -p 8000:8000 -v "$(pwd):/app:Z" --userns=keep-id -u "$(id -u):$(id -g)" localhost/mogger-mon pnpm start:dev
```

The checked-in env presets default to local-first guest play. Do not point public presets at third-party production APIs.
