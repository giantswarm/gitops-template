# Tools

## Fake Flux Build

You can use this bash tool under a repository based on this template to run automatic `kustomization.yaml` generation.

### Requirements

- [kubectl](https://kubernetes.io/docs/tasks/tools/) 
- [yq](https://github.com/mikefarah/yq)

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

## Test All FFB

You can use this bash tool under a repository based on this template to get verify the syntax of your manifests.

### Requirements

- [kubectl](https://kubernetes.io/docs/tasks/tools/) 
- [yq](https://github.com/mikefarah/yq)


