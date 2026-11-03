# Appendices

- [Appendices](#appendices)
  - [Tools](#tools)
    - [Core utilities](#core-utilities)
    - [Working with YAML files](#working-with-yaml-files)
    - [Encryption and Kubernetes tooling](#encryption-and-kubernetes-tooling)
    - [Validating yaml files in the repository](#validating-yaml-files-in-the-repository)
  - [Secret store for testing](#secret-store-for-testing)

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

## Secret store for testing

[Getting started](./getting-started.md) reads secrets through a `ClusterSecretStore` that points at your secret
manager. If you only want to try the guide and have no store yet, create one with the
[fake provider](https://external-secrets.io/latest/provider/fake/) of External Secrets Operator. It keeps the values
in the store object itself, so it needs no secret manager and no extra credentials.

Note that the token ends up in plain text in the cluster. Use this only for testing, and delete the store when you're
done. Creating a `ClusterSecretStore` also needs permissions beyond the `default` and `org-*` namespaces.

First, create the store with the two values the guide reads. Put your GitHub token in place of `YOUR_GITHUB_TOKEN`:

```sh
cat <<'EOF' | kubectl apply -f -
apiVersion: external-secrets.io/v1
kind: ClusterSecretStore
metadata:
  name: gitops-test
spec:
  provider:
    fake:
      data:
        - key: gitops/github-token
          value: YOUR_GITHUB_TOKEN
        - key: gitops/hello-world-values
          value: |
            podAnnotations:
              example.com/source: secret-manager
EOF
```

Check that the store is `Ready`:

```sh
kubectl get clustersecretstore gitops-test
```

Then set `SECRET_STORE=gitops-test` in the guide and keep its default secret names, `gitops/github-token` and
`gitops/hello-world-values`.

When you're done testing, delete the store:

```sh
kubectl delete clustersecretstore gitops-test
```
