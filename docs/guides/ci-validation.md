# Configuring extra validation and diff previews on GitHub

With this repository, we're also including a GitHub workflow, that can make your work with this
repo easier. It is available in the [validate.yaml](../../.github/workflows/validate.yaml) file.

`validate.yaml`, `yaml-diff.yaml` and `validate-file-names.yaml` call shared workflows from
[giantswarm/github-workflows](https://github.com/giantswarm/github-workflows) at a commit SHA, followed by a `# main`
comment, so a change there doesn't change your CI until you take it. With Renovate and the `renovate.json5` this
repository ships, Renovate opens a pull request that moves the SHA to the newest commit on `main` and merges it once
your checks pass. Without Renovate, move the SHA yourself when you want a fix from upstream.

The workflow offers the following jobs:

- `check_pre_commit`: it runs all the `pre-commit` validation checks,
- `validate`: templates all your `Kustomizations` available in `workload_clusters` and passes the output
  through a YAML and Kubernetes objects linters to make sure that your code is valid YAML and produces final
  manifests understandable to Kubernetes. It also renders the chart of every `HelmRelease` with its merged values
  (see [validate-helm-values](../../tools/README.md#validate-helm-values)), so values the chart's schema rejects fail
  the job. It attaches a validation report as a comment to your PR.
- `get_diff`: it templates your changed manifests and compares them to a templated version without your changes,
  then it generates and saves a diff between the two and attaches it to your PR
- `test on kind`: deploys a full `flux` installation to a test `kind` cluster, then deploys your `Kustomizations`
  there to verify if they are deployed fine. It checks if all the `Kustomizations` are reconciled as expected
  and additionally if all the statements present in `tests/ats/assertions` are also available in objects in the
  cluster.

You can check a demo PR where this is used in [PR 44](https://github.com/giantswarm/gitops-template/pull/44).

## When the workflow runs

`validate.yaml` runs on every pull request, whatever branch it targets, and on every push to `main`. The push run
checks `main` as it is after a merge, which no pull request run has tested when two pull requests merge one after the
other. If your fork's default branch has another name, or you want post-merge runs on more branches, list them under
`on.push.branches`.

## `test-on-kind` validation step - additional information

This validation step offers some broader possibilities for validation, but also requires extra configuration.

### Validation option

By default, this test checks if all the `Kustomization` and `OCIRepository` objects except the ones defined in
`GITOPS_IGNORED_OBJECTS` environment variable are successfully reconciled in the cluster.

`HelmRelease`s that deploy to a workload cluster through its kubeconfig, or create a cluster from a `release-<provider>`
chart, can't get ready in the test cluster. For every `HelmRelease` the test checks what Flux needs from the management
cluster instead:

- the chart source exists and gets ready within 180 s: the `OCIRepository` or `HelmChart` in `chartRef`, or the
  `HelmRepository`, `GitRepository` or `Bucket` in `chart.spec.sourceRef`. An OCI `HelmRepository` has no status, so it
  only has to exist,
- every `HelmRelease` in `dependsOn` exists,
- every `valuesFrom` ConfigMap or Secret that isn't `optional` exists and has its `valuesKey`. Without a `targetPath`,
  the key has to hold a YAML mapping, which Flux merges into the values. With a `targetPath`, it holds a single value,
  such as a password, so any text will do. The `<cluster>-cluster-values` ConfigMap of the `HelmRelease`'s workload
  cluster doesn't have to exist, as the management cluster creates it; if it exists, it's checked like the others. The
  test takes `<cluster>` from the kubeconfig Secret when it's named `<cluster>-kubeconfig`, as Cluster API names it, and
  otherwise from the `giantswarm.io/cluster` or `cluster.x-k8s.io/cluster-name` label of the `HelmRelease`.

Any other `HelmRelease` has to become ready, unless one of these checks found a problem with it or it depends, directly
or not, on a `HelmRelease` that can't get ready. A `release-<provider>` chart (`release-aws`, `release-azure`,
`release-vsphere` or `release-cloud-director`) is recognised by its name, from `chart.spec.chart`, the `OCIRepository`
URL or the `HelmChart`.

The Kustomization check waits for the `Kustomization`s the test applies to show up, then lists them again after each
wait to pick up the ones Flux created meanwhile. It fails if no `Kustomization` shows up, and passes with a warning if
all of them are in `GITOPS_IGNORED_OBJECTS`. Once they're all ready, each one's `status.inventory` lists the objects it
applied. The `OCIRepository` and `HelmRelease` checks check every object of their kind in the cluster, except the ignored
ones, and fail if an object listed in an inventory doesn't exist. So a repository without `HelmRelease`s or
`OCIRepository`s passes them, while one whose objects went missing doesn't. Every check looks at all its objects once
more at the end, giving each one that isn't ready, such as one in the middle of a periodic reconciliation, time to get
ready, so one that was ready early and failed later is reported. An object Flux deleted meanwhile, such as a
`Kustomization` its parent pruned, is left out.

Additionally, every file present in `tests/ats/assertions/exists` is loaded and verified. Each of these files
has to contain one or more YAML description of objects of Kubernetes objects you expect to be present in the cluster
after your Kustomizations are deployed. Each object has to have `kind:`, `metadata.name` and `metadata.namespace`
(if it's a namespace-scoped object) defined. The rest of object definition is arbitrary, but every property specified
in the assertions file must be also present (and have exactly the same value) as the property of the object present
in cluster. Strings are compared as text, so a ConfigMap's `values` has to match line by line. Only trailing whitespace
is ignored: whether the assertion writes a block as `|` or `|-`, or a line ends in a space, doesn't matter.

### Configuration

This build step requires additional configuration using the following environment variables:

- `GITOPS_FLUX_APP_VERSION`: the version of [flux-app](https://github.com/giantswarm/flux-app/releases)
  version provided by Giant Swarm
- `GITOPS_INIT_NAMESPACES`: namespaces used for testing need to be initialized (RBAC permissions) before
  they can be used; as such this variable needs to hold a comma separated list of namespaces, where you want
  to deploy `Kustomization` objects during the test (example: `default,org-org-name`)
- `GITOPS_IGNORED_OBJECTS`: a comma-separated list of (namespaced) Flux objects that are expected to have a failed
  state during the test (example - a Kustomization that targets an external cluster:
  "org-org-name/mc-name-clusters-mapi-out-of-band-no-flux-direct"). [validate.yaml](../../.github/workflows/validate.yaml)
  sets it with the `gitops_ignored_objects` input of the shared workflow. Update it there when you rename or add a
  `Kustomization` that can't become ready in the test cluster.
- `GITOPS_MASTER_GPG_KEY`: this variable needs to be a secret (unless you know what you're doing) and needs to contain
  a base64 encoded private master GPG key (armor-encoded, including `-----BEGIN...`
  and `-----END...` header and footer) for your `sops` configuration. It is recommended
  to set it as a repository secret on github (tho job is configured to pick up this secret by default).

## Superseded runs

The kind test takes a while, so `validate.yaml` runs once per pull request at a time. When you push a new commit to
a pull request, the run for the previous commit is cancelled. Pushes to a branch, such as a merge to `main`, don't
cancel the run in progress: it finishes, and GitHub keeps only the newest of the push runs waiting behind it.
