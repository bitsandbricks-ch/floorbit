### Added

- A Kubernetes and k3s example (`deploy/kubernetes/floorbit.yaml`, docs/kubernetes.md). It has one pod with a persistent volume on `/app/state`, so updates and restarts no longer start Floorbit empty, plus Redis and a Traefik Ingress.
