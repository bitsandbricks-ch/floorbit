# Install on Kubernetes or k3s

[`deploy/kubernetes/floorbit.yaml`](https://github.com/bitsandbricks-ch/floorbit/blob/master/deploy/kubernetes/floorbit.yaml)
runs Floorbit with Redis on any Kubernetes cluster, k3s included. It has one Floorbit pod with a
persistent volume, a Redis pod, two Services and an Ingress for k3s's Traefik.

## Keep the volume

Floorbit keeps everything in `/app/state`: `data.json` (the floor plan, accounts and settings),
the audit log, past events, plugin state and check-ins. **Without a volume on that path, every new
pod starts empty.** That happens on every update, every restart and every move to another node. The
manifest mounts the claim `floorbit-state` there. Don't delete the claim when you update.

## Install

```sh
kubectl create namespace floorbit
kubectl -n floorbit create secret generic floorbit --from-literal=SECRET_KEY="$(openssl rand -hex 32)"
# edit floor.example.com (PUBLIC_URL and the Ingress host) in the file, then:
kubectl -n floorbit apply -f deploy/kubernetes/floorbit.yaml
kubectl -n floorbit rollout status deploy/floorbit
```

The first account and the rest of the setup are the same as with Docker Compose
([install.md](install.md#2-the-first-account-and-setup)). Settings go in the Deployment's `env`, or
under **Settings** in the app.

`SECRET_KEY` signs the sign-in cookies. Without it, Floorbit makes one and keeps it in `data.json`,
which works too as long as the volume stays. Keeping it in a Secret also keeps everyone signed in
across a restore.

## Updating

Pin a version in the `image` line (`ghcr.io/bitsandbricks-ch/floorbit:1.2.3`), change it and apply
the file again, or restart to pull `latest`:

```sh
kubectl -n floorbit rollout restart deploy/floorbit
```

The Deployment uses `strategy: Recreate`. The old pod stops and lets go of the volume before the new
one starts, so a `ReadWriteOnce` volume never has two pods. Expect a few seconds without Floorbit.

## Backups

**Settings > Backup and restore** downloads the floor plan and settings ([backup.md](backup.md)). To
copy everything out of the volume:

```sh
pod=$(kubectl -n floorbit get pod -l app=floorbit -o name | head -1)
kubectl -n floorbit cp "${pod#pod/}:/app/state" ./floorbit-backup-$(date +%F)
```

## More than one pod

One pod that restarts in seconds and keeps its volume is the dependable setup for a crew tool, and
it's the default. Several pods behind one Service work when all of these are true:

- **Postgres** for the documents and logs: `FLOORBIT_DATABASE_URL=postgresql://…` on every pod
  ([database.md](database.md)). SQLite and files stay with one pod.
- **Redis** shared by every pod (`REDIS_HOST`), and `FLOORBIT_CLUSTER=redis` on every pod.
- **A `ReadWriteMany` volume** on `/app/state` for what is still files there: hall background
  images, syslog and flow statistics. Without one, each pod has its own copy of those.
- `strategy: RollingUpdate` instead of `Recreate`, once the volume is `ReadWriteMany`.

With `FLOORBIT_CLUSTER=redis` the pods share three things through Redis:

- **Live updates.** A change made on one pod shows up in the browsers connected to the others.
- **Agent calls.** A [local agent](agent.md) holds its link to one pod. The other pods send its
  calls there and get the answers back, so it doesn't matter which pod a browser reaches.
- **One leader.** Every pod polls the switches and runs its checks, so every page is current on
  every pod. Only the pod holding the leader lease sends what those checks find: Discord alerts,
  webhooks, the event timeline, plugin hooks, replay frames and the nightly config backup. When it
  stops, another pod takes the lease within about 20 seconds. What a crew member does (an
  incident, a notice, a handover) is
  sent by the pod that took the request. If Redis can't be reached, every pod acts as the leader,
  because a duplicate alert is better than a missing one.

Each pod logs `[cluster] pod … joined (Redis)` at start, and the leader logs `… is now the leader`.
Sign-in cookies work on every pod as long as they all have the same `SECRET_KEY` (the Secret above).

## Syslog and NetFlow

Both take UDP from the event network. On a hosted cluster, let the
[local agent](agent.md) take them on the event network instead. On a cluster at the event, add a
`LoadBalancer` or `NodePort` Service for UDP 5514 (syslog) and 2055 (flows), as in
`docker-compose.yml`.
