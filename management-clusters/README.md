# management-clusters

`management-clusters`

One directory per management cluster, named after it. Everything Flux applies to a management cluster, and through it
to that cluster's organisations and workload clusters, starts in that cluster's directory.

Each management cluster's own Flux Kustomization, in its directory's `MC_NAME.yaml`, applies that directory and nothing
else. So a management cluster never picks up another's files, and the `MC_NAME` placeholder directory here is applied
by no real cluster: it's the example you copy.

## What's here

- [`MC_NAME/`](MC_NAME/): the example management cluster, with one organisation and its workload clusters.

## When you copy it

Copy `MC_NAME/` to a directory named after your management cluster, and change the names marked `TODO` in it. Keep
`management-clusters/` itself: the `spec.path` of every Flux Kustomization starts with it.

## Read more

- [1. Connect the management cluster](/docs/tutorials/basic/getting-started.md#1-connect-the-management-cluster)
- [Layout](/docs/reference/repo-structure.md#layout)
