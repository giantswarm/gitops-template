# Appendices

- [Appendices](#appendices)
  - [Tools](#tools)
    - [Core utilities](#core-utilities)
    - [Working with YAML files](#working-with-yaml-files)
    - [Encryption and Kubernetes tooling](#encryption-and-kubernetes-tooling)
    - [Validating yaml files in the repository](#validating-yaml-files-in-the-repository)

## Tools

This section contains the list of tools used throughout the code examples in this repository.

### Core utilities

For core utilities like `base64`, `sed`, `tr`, etc. GNU compatible versions are assumed in the code examples.

### Working with YAML files

For `yq` the [github.com/mikefarah/yq](https://github.com/mikefarah/yq/) version is assumed in the code examples.

### Encryption and Kubernetes tooling

- `gpg` of [GnuPG](https://gnupg.org/) to create and manage the encryption keys
- `sops` of [github.com/getsops/sops](https://github.com/getsops/sops) to encrypt Secrets
- `kubectl` to create manifests and apply the initial configuration to the Management Cluster
- `kubectl gs` of [github.com/giantswarm/kubectl-gs](https://github.com/giantswarm/kubectl-gs) to template
  Giant Swarm resources
- `flux` of [github.com/fluxcd/flux2](https://github.com/fluxcd/flux2) to render and inspect Flux `Kustomizations`

### Validating yaml files in the repository

You need the following tools installed to use [test-all-ff](/tools/test-all-ff) script.

- `yamllint` of [github.com/adrienverge/yamllint](https://github.com/adrienverge/yamllint)
- `kubeconform` of [github.com/yannh/kubeconform](https://github.com/yannh/kubeconform)
