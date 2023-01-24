# Tools

## Fake Flux Build

You can use this bash tool under a repository based on this template to run automatic `kustomization.yaml` generation.

### Requirements

- [kubectl](https://kubernetes.io/docs/tasks/tools/)
- [yq](https://github.com/mikefarah/yq)
- [fake-flux-build](https://github.com/giantswarm/gitops-template/blob/main/tools/fake-flux-build)

### Examples

- Build rfjh2 workload cluster Cluster CRs.

```bash
fake-flux-build build gorilla giantswarm-production rfjh2 cluster
```

- Build c68pn workload cluster all App CRs.

```bash
fake-flux-build build gollum giantswarm c68pn apps
```

- Build c68pn workload cluster docs App CRs.

```bash
fake-flux-build build gollum giantswarm c68pn apps/docs
```

- Build flux01 workload cluster Cluster and App CRs

```bash
fake-flux-build build gamma multi-project flux01 /
```

#### Using `fake-flux-build` to show a single resource set

You can use a combination of `fake-flux-build` and `yq` to show specific resources under a given path which can be
useful for troubleshooting issues with that resources deployment.

This is achieved by using `yq` selectors to match the reource(s) in question

```bash
fake-flux-build build gorilla giantswarm-production rfjh2 / | yq 'select(.kind == "App" and .metadata.name == "ailefroide*")'
```

## Test All FFB

You can use this bash tool under a repository based on this template to get verify the syntax of your manifests.
