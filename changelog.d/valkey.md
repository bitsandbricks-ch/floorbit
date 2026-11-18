### Changed

- The cache runs on Valkey, the open-source fork of Redis, in Docker Compose, the Kubernetes example
  and CI. Valkey speaks the same protocol, so the `REDIS_*` settings stay as they are and a Redis
  you already run keeps working. `FLOORBIT_CLUSTER` accepts `valkey` as well as `redis`. After
  updating, run `docker compose up -d --remove-orphans` once (or delete `floorbit-redis` on
  Kubernetes); see docs/install.md and docs/kubernetes.md.
- A Redis snapshot (`dump.rdb`) that had been committed by mistake is gone from the repository.
