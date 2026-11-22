# Check a change before you push

CI checks every pull request, see [CI checks](../reference/ci-checks.md). It's quicker to catch a mistake on your
machine: a typo in a patch costs you a minute here, and a round trip through CI there. Each check below is optional
and runs from the root of your clone.

## Run pre-commit

The repository has a [`pre-commit` config](/.pre-commit-config.yaml) that checks the YAML and Markdown formatting, and
that every Flux `Kustomization`'s path exists and builds, see
[check-kustomization-paths](../reference/ci-checks.md#check-kustomization-paths). Another hook,
[check-directory-readmes](/tools/README.md#check-directory-readmes), fails when a directory you add under `bases/` or
`management-clusters/` has no README: write one that says what the directory is for. A third,
[check-sops-encrypted](/tools/README.md#check-sops-encrypted), fails when a `*.enc.yaml` file you've staged isn't
encrypted with SOPS, before its secret reaches Git's history. CI runs the same hooks. To use them,
[install](https://pre-commit.com/#install) `pre-commit`, then set up the hooks once in your clone:

```sh
pre-commit install --install-hooks
```

From then on, the hooks check the files of every commit. To run the checks without committing:

```sh
pre-commit run -a
```

To check only the files you changed:

```sh
pre-commit run --files FILE...
```

To commit without running them, use `git commit --no-verify`. CI runs them anyway.

## Render what Flux applies

A cluster can merge many layers: a base, components, patches and the variables of its `Kustomization`. To see what
comes out, build the directory as Flux does.

kustomize alone shows the result before Flux fills in the variables. Build a directory, not a file in it on its own,
which leaves out the directory's `kustomization.yaml`. For example, to see what the management cluster's
`Kustomization` applies from an organisation:

```sh
kubectl kustomize management-clusters/MC_NAME/organizations/ORG_NAME
```

Building the organisation's `namespace` on its own leaves `${organization}` as it is: `namespace.yaml` fills it in.

[`tools/fake-flux`](/tools/README.md#fake-flux) builds a Flux `Kustomization` as Flux applies it, variables and all,
in the namespace its parent puts it in. List the `Kustomization`s it finds, then build one by its number or name:

```sh
tools/fake-flux list
tools/fake-flux build mc-name-clusters-capi-wc-name
```

To see one object, pass a `yq` query. For example, the merged `valuesFrom` of a cluster's `HelmRelease`:

```sh
tools/fake-flux build mc-name-clusters-capi-wc-name '. | select(.kind == "HelmRelease") | .spec.valuesFrom'
```

[Values](../reference/values.md) explains the order of the layers you'll see there. The
[tools README](/tools/README.md#fake-flux-usage) lists the other arguments.

## Validate with test-all-ff

[`tools/test-all-ff validate`](/tools/README.md#test-all-ff) runs what the `validate` job of CI runs: it builds every
Flux `Kustomization` of the repository with `fake-flux`, checks the result with `yamllint` and `kubeconform`, and
renders the chart of every `HelmRelease` with its values:

```sh
tools/test-all-ff validate
```

It needs these tools in your `$PATH`:

- `yamllint` of [github.com/adrienverge/yamllint](https://github.com/adrienverge/yamllint)
- `kubeconform` of [github.com/yannh/kubeconform](https://github.com/yannh/kubeconform); CI uses 0.8.0
- `curl`, `sha256sum` and `tar`, to fetch the Flux CRD schemas. See [tools](/tools/README.md#test-all-ff) for the
  schema sources and versions.
- `helm` of [helm.sh](https://helm.sh/docs/intro/install/), to render the chart of every `HelmRelease` with its values
- `flux`, `kubectl` and `yq`, see [Tools](../reference/tools.md#tools)

`tools/test-all-ff template` prints everything the repository applies, which is what the `get-diff` job of CI compares.
