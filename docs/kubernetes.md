# Install on Kubernetes or k3s

[`deploy/kubernetes/floorbit.yaml`](https://github.com/bitsandbricks-ch/floorbit/blob/master/deploy/kubernetes/floorbit.yaml)
runs Floorbit with Valkey on any Kubernetes cluster, k3s included. It has one Floorbit pod with a
persistent volume, a Valkey pod (the cache), three Services and an Ingress for k3s's Traefik.

The Floorbit pod has two containers: Floorbit and its [local agent](agent.md). Floorbit reaches the
event network (switches, LibreNMS, NetBox, game servers) only through the agent, the same way as a
hosted Floorbit does. Floorbit writes the agent's key into a memory volume only the two share and
enrols it as "Local agent" at each start, so there is no key to copy. The cluster has to reach the
event network for this; otherwise run the agent in the hall instead and remove the `agent` container.

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

The manifest sets `CHECKIN_TRUST_PROXY=true`. Only the Ingress reaches the pod, so Floorbit takes
the visitor's address from Traefik's `X-Forwarded-For` header and not Traefik's own address. Without it,
five wrong passwords from anyone would lock that username for everyone. If Traefik itself only sees
node addresses (k3s's built-in load balancer can hide the client), set
`externalTrafficPolicy: Local` on Traefik's Service.

## HTTPS

The Ingress serves `floor.example.com` over HTTPS only: plain HTTP gets a redirect (the Traefik
Middleware `floorbit-https`). Local agents send their key and a signature with every request, and
crew sign in, so nothing should go over plain HTTP. The certificate is the Secret `floorbit-tls`:

- **cert-manager:** uncomment the `cert-manager.io/cluster-issuer` annotation and name your
  ClusterIssuer; cert-manager fills the Secret and renews it.
- **Your own certificate:** `kubectl -n floorbit create secret tls floorbit-tls --cert=fullchain.pem --key=key.pem`.
- **Neither yet:** Traefik answers with its default self-signed certificate. The line is still
  encrypted, but browsers warn and an agent refuses it unless it trusts that certificate.

Installing into a namespace other than `floorbit`? The middleware annotation names it
(`<namespace>-floorbit-https@kubernetescrd`): change it too.

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

The cache moved from Redis to Valkey: the file now has `floorbit-valkey` instead of `floorbit-redis`.
After applying it, remove the old one, which held only a cache:

```sh
kubectl -n floorbit delete deployment,service floorbit-redis
```

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
  ([database.md](database.md)). SQLite, the default, stays with one pod.
- **Valkey or Redis** shared by every pod (`REDIS_HOST`), and `FLOORBIT_CLUSTER=valkey` (or `redis`, the same) on every pod.
- **A `ReadWriteMany` volume** on `/app/state` for what is still files there: hall background
  images, syslog and flow statistics. Without one, each pod has its own copy of those.
- `strategy: RollingUpdate` instead of `Recreate`, once the volume is `ReadWriteMany`.

With `FLOORBIT_CLUSTER` set the pods share three things through Valkey:

- **Live updates.** A change made on one pod shows up in the browsers connected to the others.
  While Redis is away, other pods' changes don't reach these browsers; when it is back, each pod
  tells its open pages to fetch everything again. A page whose own stream dropped (Wi-Fi, a
  restart) does the same when it reconnects.
- **Agent calls.** A [local agent](agent.md) holds its link to one pod. The other pods send its
  calls there and get the answers back, so it doesn't matter which pod a browser reaches. Calls
  and answers cross Redis sealed with the vault key every pod shares (a switch call carries its
  login), so the pods need the same `FLOORBIT_SECRET_KEY_FILE`.
- **One leader.** The pod holding the leader lease runs the background checks: switch status, the
  port watch and traffic, the health wall, services, security, power, game servers, DNS, which
  machine is on which port, the uplinks between switches and the check-in refresh. It shares what
  they found through Valkey (`floorbit/shared_state.py`); the other pods' pages read that, a second
  or two old at most (the traffic history up to half a minute, from the database). A "check now"
  on another pod, a typed-in power reading and what a local agent sends go to the leader. A pod
  that takes the lease carries on from that picture, so a switch that was down stays down instead
  of starting from a fresh baseline. Only the leader sends what the checks find: Discord alerts,
  webhooks, the event timeline, plugin hooks, replay frames and the nightly config backup. When it
  stops, another pod takes the lease within about 20 seconds. What a crew member does (an
  incident, a notice, a handover) is
  sent by the pod that took the request. If Valkey can't be reached, every pod acts as the leader,
  because a duplicate alert is better than a missing one.

The [switch terminal](terminal.md) keeps its SSH connection in the pod that opened it. A request for
it that lands on another pod is passed to that pod through Valkey (sealed, like agent calls), so no
sticky sessions are needed. When that pod stops, its terminals close.

Each pod logs `[cluster] pod … joined (Redis)` at start, and the leader logs `… is now the leader`.
Sign-in cookies work on every pod as long as they all have the same `SECRET_KEY` (the Secret above).

## Syslog and NetFlow

Both take UDP from the event network, and the agent container takes them. The `floorbit-agent`
Service (type `LoadBalancer`; k3s's ServiceLB opens it on the nodes) publishes udp/514 (syslog) and
udp/2055 (flows): point the devices at a node's address. On a hosted cluster, the agent in the hall
takes them instead.
