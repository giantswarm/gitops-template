# Testing

By now your repository holds clusters in several stages, apps from templates and stacks, out-of-band objects, teams and
`ResourceSet`s, all wired together by names that have to match. A typo in one of them doesn't fail on your machine. It
fails on the management cluster, after the merge, which is the worst place to find it.

This repository tests itself in two ways, and you can use either or both in your fork:

- **the kind test**, `tests/ats`: on every pull request, CI bootstraps a throwaway kind cluster the way a new
  management cluster is bootstrapped, lets Flux apply the repository from your branch, and checks that everything gets
  `Ready`. It catches mistakes before the merge, and it works on your management clusters, not only on the template's
  examples.
- **Chainsaw**, `tests/chainsaw`: tests in YAML that you run against a real management cluster that Flux reconciles
  from your repository. They check what's running, after the merge.

Neither creates anything on your management cluster: the kind test runs in a throwaway cluster, and Chainsaw only
reads what Flux applied.

- [What the kind test does](#what-the-kind-test-does)
- [Write bindings for your own clusters](#write-bindings-for-your-own-clusters)
- [Run the kind test locally](#run-the-kind-test-locally)
- [Test with Chainsaw](#test-with-chainsaw)
- [Run Chainsaw from your machine](#run-chainsaw-from-your-machine)
- [Run Chainsaw in GitHub Actions](#run-chainsaw-in-github-actions)
- [Choose `tests/ats`, Chainsaw or both](#choose-testsats-chainsaw-or-both)

## What the kind test does

The `validate` workflow, in [validate.yaml](/.github/workflows/validate.yaml), runs the kind test for every pull request
that changes more than Markdown. It:

1. creates a kind cluster, and installs what a Giant Swarm management cluster brings: Flux from flux-app, the CRDs of
   Cluster API and of Giant Swarm, External Secrets Operator, Kyverno and Flux Operator, at the versions the management
   clusters run;
1. applies the two Kyverno policies a management cluster uses to refuse Flux objects that break its rules, so the
   test refuses them too;
1. stands in for organization-operator, which creates an organisation's namespace once Flux has applied its
   `Organization`, and for the workload clusters, with a stand-in `Cluster` for every cluster a `Kustomization` waits
   for, since kind can't create real ones;
1. points the `GitRepository` your management cluster's `Kustomization` reads at your branch, puts your master key in
   the Secret it decrypts with, applies each management cluster's `Kustomization`, and waits until every Flux
   `Kustomization`, source and `HelmRelease` it can run is `Ready`;
1. compares the objects with the assertions in `tests/ats/assertions`, and runs the example checks, such as the
   upgrade windows of the `ResourceSet`s and pruning, where the examples are.

None of the first four steps knows a name of yours or of the template's: the test reads them from your files. The
fifth is the template's own, bound to its examples in [tests/ats/kind-test.yaml](/tests/ats/kind-test.yaml). Once
you've deleted the examples, as [Configure CI](../../how-to/configure-ci.md#the-kind-test-in-your-fork) tells you to,
those checks are skipped, each with a line that says which example it missed. A skipped check isn't a failure; it's a
check with nothing to look at.

Every example is something you build from, so every example the test can reconcile has to get `Ready`: the test
installs what an example needs rather than skipping it. Creating clusters is the one exception, as there's no cloud
account to create them in, and your secret manager is another, as the kind cluster can't reach it.
[The kind test](../../reference/ci-checks.md#the-kind-test) has every check in detail, and
[what it can't prove](../../reference/ci-checks.md#what-the-test-proves-and-what-it-cant).

## Write bindings for your own clusters

Out of the box, the test tells you that what you wrote applies and gets `Ready`. That's most of what goes wrong, but
not all of it: a cluster can be `Ready` with the wrong node pools, and an app `Ready` with the wrong values. To check
those, you tell the test what right looks like, in two places.

**Assertions.** A file under `tests/ats/assertions/exists` lists objects that have to exist, with the fields that have to
match; the test checks every field you write and ignores the rest, though a list has to match whole. The app of the
basic tutorial, installed where you meant it to be, is a good start:

```yaml
apiVersion: helm.toolkit.fluxcd.io/v2
kind: HelmRelease
metadata:
  name: prod1-hello-world
  namespace: org-acme
spec:
  releaseName: hello-world
  targetNamespace: hello-world
```

Every file there is checked, unless the binding of an example that isn't there names it. The template's own files are
named by their examples' bindings, so they go quietly with the examples; delete them anyway when you delete the
examples, as they're no use to you.

**`kind-test.yaml`.** The data the test can't find in your files:

- `nodePools`: the node pools each workload cluster should end up with, by namespace. Once a namespace is listed,
  every cluster in it has to be, so a new cluster without an entry fails the test, which is the point.
- `clusterBaseApps`: the apps a cluster's `Kustomization` installs before the cluster is `Available`, such as a
  Gateway API stack, by the `Cluster`'s `namespace/name`. The test checks they're installed while the cluster's other
  apps wait.
- `secretStore`: a stand-in for your secret manager, with test values for the keys your `ExternalSecret`s read. It
  only helps where your repository doesn't create a store of the same name itself; a real store in the repository
  replaces it, and its `ExternalSecret`s can't sync in kind.
- `managementClusters`: which of your management clusters the test applies, when not all of them.

For a cluster `prod1` in the organisation `acme`, with its own pool and the Gateway API bundle installed with the
cluster:

```yaml
nodePools:
  org-acme:
    prod1: [nodepool0]
clusterBaseApps:
  org-acme/prod1:
    - prod1-gateway-api-bundle
```

The rest of `kind-test.yaml`, under `examples`, binds the template's examples. You can leave it: with the examples
gone, it does nothing but explain the skips. Or delete what you don't use.

The checks of the examples, such as pruning or the upgrade windows, are written for the template's example objects.
They're worth reading when you build something similar, and copying when you want the same check on yours, but they
won't check your objects by renaming a binding.

## Run the kind test locally

CI is the usual place for the kind test, but a local run is quicker when you're chasing a failure. You need:

- Docker, running natively on the host, as on the GitHub runner. The test reaches the vCluster, the workload cluster
  it runs inside the kind cluster, at the kind node's IP address, on a node port, so it has to be able to route to
  kind's Docker network. Where Docker runs in a VM, such as Docker Desktop or a Podman machine, or where the test runs
  in a container outside that network, the vCluster's setup times out;
- [kind](https://kind.sigs.k8s.io/), the version `kind_ver` in `validate.yaml` names, `kubectl` and `helm` in your
  `$PATH`;
- Python 3.12 and [pipenv](https://pipenv.pypa.io/);
- your branch pushed to a repository the kind cluster can read: a public one, or a private one with a token that can
  read it in `GITHUB_TOKEN`, and the private part of your master GPG key, as in CI, unless nothing you apply decrypts.

1. Create a kind cluster and save its kubeconfig:

    ```sh
    kind create cluster --name gitops-test
    kind get kubeconfig --name gitops-test > "${TMPDIR:-/tmp}/gitops-test.kubeconfig"
    ```

1. Set what the test reads. The flux-app version is the one `validate.yaml` passes to CI, and the master key is your
   private master key, armoured and base64-encoded, as in the `GITOPS_MASTER_GPG_KEY` secret:

    ```sh
    export KUBECONFIG="${TMPDIR:-/tmp}/gitops-test.kubeconfig"
    export GITOPS_REPO_URL
    export GITOPS_REPO_BRANCH=$(git branch --show-current)
    export GITOPS_FLUX_APP_VERSION=$(yq '.jobs.validate.with.gitops_flux_app_version' .github/workflows/validate.yaml)
    export GITOPS_INIT_NAMESPACES=default
    export GITOPS_IGNORED_OBJECTS=""
    export GITOPS_MASTER_GPG_KEY=$(gpg --export-secret-keys --armor MASTER_KEY_FINGERPRINT | base64 -w0)
    ```

    `GITOPS_INIT_NAMESPACES` and `GITOPS_IGNORED_OBJECTS` are what `validate.yaml` sets for CI; see
    [Configuration](../../how-to/configure-ci.md#configuration) for what they do.

1. Install the test's Python packages and run it:

    ```sh
    cd tests/ats
    pipenv install --deploy
    pipenv run pytest .
    cd ../..
    ```

    The last line takes you back to the root of your clone, where the rest of this page runs.

    To run some tests only, pass pytest's `-k` with part of their names, but bear in mind that the last one,
    `test_prune`, deletes what the others check, and fails if they didn't run first.

1. Delete the cluster when you're done, and stop pointing `kubectl` at its kubeconfig:

    ```sh
    kind delete cluster --name gitops-test
    unset KUBECONFIG
    ```

## Test with Chainsaw

[tests/chainsaw](/tests/chainsaw) holds tests written in YAML for [Chainsaw](https://kyverno.github.io/chainsaw/),
which you run against a management cluster that Flux reconciles from your repository. Chainsaw is separate from
`tests/ats` and runs as a step of its own. This repository doesn't run it in its CI.

Each test is a `chainsaw-test.yaml`, with steps that wait for an object to match what the step expects, such as its
`Ready` condition. The tests only read objects. Every command here passes `--namespace default`: by default, Chainsaw
creates a `chainsaw-*` namespace for each test, which a management cluster doesn't let you do, and with the flag it
uses the existing `default` namespace and neither creates nor deletes one.

| Test | What it checks |
| --- | --- |
| `readiness-ordering` | Along the `out-of-band-no-flux` cluster's chain, each object is linked to the one before it and is `Ready`: the `Cluster`'s control plane is available and reachable, the cluster's `Kustomization` health-checks it and waits for its control plane, the apps `Kustomization` depends on that one, and the `hello-world-standalone` `HelmRelease` depends on `gateway-api-crds`. The test checks the links and the state the objects end in, not the order they got `Ready` in. A failure names the first object of the chain that isn't `Ready` or isn't linked. |
| `kyverno-generate` | The [secret-stores](../../how-to/workload-cluster-secrets.md#give-every-cluster-a-store-with-kyverno) `Policy` is `Ready`, and has given the `out-of-band-no-flux` cluster its `ExternalSecret` and its `SecretStore`, both `Ready` and labelled with the policy that made them. |
| `external-secrets` | The example's `ExternalSecret`, which gives an app secret values as in the [basic tutorial](../basic/getting-started.md#4-deploy-an-app), has synced, the Secret it writes has the `reconcile.fluxcd.io/watch` label and the values, and the `HelmRelease` that reads the values from that key is `Ready`. |

The steps name no objects themselves: they read the names from a values file.
[tests/chainsaw/values.yaml](/tests/chainsaw/values.yaml) names the template's examples: the organisation's namespace,
the `out-of-band-no-flux` cluster with its `Kustomization`s and two of its `HelmRelease`s, the `ExternalSecret` with
the key of the values in its Secret and the `HelmRelease` that reads that Secret, and the Kyverno policy of the
secret stores. Copy it and set the names of your own objects. Run only the tests whose examples you use.

To add a test, create a directory in `tests/chainsaw` with a `chainsaw-test.yaml`, and put the names it needs in the
values file.

## Run Chainsaw from your machine

1. Install [Chainsaw](https://kyverno.github.io/chainsaw/latest/quick-start/install/), the version that
   `CHAINSAW_VERSION` in [chainsaw.yaml](/.github/workflows/chainsaw.yaml) pins.
1. Copy the values file and set your objects' names in it:

    ```sh
    cp tests/chainsaw/values.yaml my-values.yaml
    ```

1. With your kubeconfig's context on the management cluster, run:

    ```sh
    chainsaw test tests/chainsaw --values my-values.yaml --namespace default
    ```

    Add `--include-test-regex 'chainsaw/(readiness-ordering|external-secrets)'` to run some of the tests only.
    Chainsaw runs each test as a subtest of one named `chainsaw`, so the expression has to match `chainsaw/<test>`.
    Without the prefix it matches no test, and Chainsaw passes without running any, which is a cheerful way to test
    nothing at all.

Your user needs to read the objects the tests check, and the `default` namespace.

## Run Chainsaw in GitHub Actions

[chainsaw.yaml](/.github/workflows/chainsaw.yaml) is an example workflow that installs Chainsaw and runs the tests
against a management cluster. It has only a manual trigger, so it doesn't run on pull requests or pushes, and this
repository doesn't set the secret it needs. To use it:

1. Create a repository secret `CHAINSAW_KUBECONFIG` with a kubeconfig for the management cluster. Use a credential
   that works without a browser, such as a service account token, with the rights above.
1. Run the `chainsaw` workflow from the Actions tab, with the path of your values file as its `values` input. To run it
   on a schedule or after a merge, add a `schedule` or `push` trigger.

The workflow downloads the Chainsaw release that `CHAINSAW_VERSION` pins and checks it against `CHAINSAW_SHA256`.
Renovate moves the version but not the checksum: set the checksum of the new release's `chainsaw_linux_amd64.tar.gz`,
from its `checksums.txt`, in the same pull request. Nothing in CI runs the workflow, so no check would catch a stale
checksum: `renovate.json5` never merges a Chainsaw update automatically, so that the pull request waits for you to set
it.

## Choose `tests/ats`, Chainsaw or both

- `tests/ats` only: the template's default. `validate.yaml` runs it on a kind cluster for every pull request that
  changes more than Markdown. Delete `tests/chainsaw` and `.github/workflows/chainsaw.yaml`.
- Chainsaw only: keep `tests/chainsaw` and enable the workflow. The shared workflow that `validate.yaml` calls always
  runs `tests/ats` in its kind test and has no input to turn it off. To test with Chainsaw alone, stop calling it from
  `validate.yaml`, and run the checks you want to keep in a workflow of your own.
- Both: keep everything. `tests/ats` checks pull requests on a kind cluster, and Chainsaw checks your management
  cluster when you run it.
