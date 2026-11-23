# Where upstream advice doesn't apply here

Each entry: what upstream documentation or common practice suggests, what to do in this repository, and why.

## Installing or bootstrapping Flux

- **Upstream:** `flux bootstrap`, a `flux-system` namespace, `gotk-components.yaml` and `gotk-sync.yaml` in the
  repository.
- **Here:** none of it. The repository starts from one `Kustomization`, `management-clusters/MC_NAME/MC_NAME.yaml`,
  with a `GitRepository` and its token created on the management cluster once.
- **Why:** Giant Swarm runs Flux, in `flux-giantswarm`, and upgrades it. A second Flux, or the first one's manifests
  in a customer's repository, would fight it.

## `--no-cross-namespace-refs`

- **Upstream:** recommended for multi-tenancy.
- **Here:** don't recommend it, and don't restructure sources to avoid cross-namespace references.
- **Why:** every organisation's objects read the one `GitRepository` in `default`. Tenancy is enforced another way:
  by the `automation` ServiceAccounts' rights and the admission policies.

## A `Kustomization` or `HelmRelease` without a ServiceAccount

- **Upstream:** examples have no `spec.serviceAccountName`, and Flux acts as itself.
- **Here:** always `serviceAccountName: automation`, or `kubeConfig` for a workload cluster.
- **Why:** the management cluster refuses the object otherwise. Pasting an upstream example unchanged is the usual
  cause of "refused at admission".

## Creating the namespace

- **Upstream:** a `Namespace` manifest next to the workload.
- **Here:** never on the management cluster. An organisation's namespace exists because its `Organization` does. For
  an app in a workload cluster, the `HelmRelease` sets `install.createNamespace: true`, as the examples do; a
  namespace that needs labels or other objects is an out-of-band object.
- **Why:** the repository can't create cluster-scoped objects on the management cluster. In the workload cluster the
  `HelmRelease` acts through the cluster's kubeconfig, where it can.

## `prune: false` as a safety measure

- **Upstream and habit:** turn pruning off so nothing is deleted by accident.
- **Here:** `spec.prune` stays `true`. Protect a specific object with the
  `kustomize.toolkit.fluxcd.io/prune: disabled` annotation.
- **Why:** with pruning off, deleting an app's files leaves the app running and unmanaged, and Git stops being the
  truth. The annotation protects the few objects that matter and keeps the rest honest.

## Charts from upstream registries

- **Upstream:** the project's own Helm repository or OCI registry.
- **Here:** Giant Swarm's charts from `gsoci.azurecr.io`, at versions Giant Swarm ships. Flux, Kyverno and External
  Secrets Operator are never installed by the repository at all.
- **Why:** Giant Swarm's charts carry the platform's defaults and are what it supports. A version newer than the
  management cluster runs may use an API the cluster doesn't serve.

## `HelmRepository` and `HelmChart`

- **Upstream:** common in older examples.
- **Here:** an `OCIRepository` per chart, and a `HelmRelease` with `chartRef`.
- **Why:** it's what the examples, Renovate's rules and the tests are built around.

## Two reconcilers on one object

- **Habit:** add a `HelmRelease` for something already installed another way, or keep both during a migration; list a
  file wherever it's needed; write a Secret from Git and from a secret manager to be safe.
- **Here:** one reconciler per object. One `Kustomization` builds each object, one `HelmRelease` installs each release,
  one route delivers each Secret, and nothing in Git applies what a Kyverno policy generates. Adopting an existing
  release with a `HelmRelease` is fine, once nothing else reconciles it.
- **Why:** a reconciler can't tell whether it really owns an object. Two of them, or one told twice, keep undoing each
  other, the object flaps and nothing reports an error, see `docs/explanation/one-owner.md`.

## One `Kustomization` for everything

- **Upstream:** a single `Kustomization` over a `clusters/` directory.
- **Here:** the chain described in the skill: management cluster, organisation, cluster, apps.
- **Why:** each link runs as a different account and fails on its own. One `Kustomization` would need
  `default/automation`'s reach over everything, and one bad file would stop every cluster.

## Health checks on `Available`

- **Habit:** wait for the Cluster API `Cluster` to be `Available` before installing apps.
- **Here:** wait for `ControlPlaneAvailable` and `RemoteConnectionProbe`.
- **Why:** `Available` counts every node pool, so one pool short of its minimum would block every change to the
  cluster's apps.

## Applying by hand

- **Habit:** `kubectl apply -f` to try a change, or `flux reconcile` with a local change.
- **Here:** change Git. Check with `tools/test-all-ff validate` and `tools/fake-flux`.
- **Why:** anything applied by hand is either reverted by Flux at its next run or, worse, isn't in Git and survives
  until it breaks something. Suspending and resuming, in `docs/how-to/troubleshooting.md`, is the supported way to
  hold Flux off while you investigate.

## Tidying duplication

- **Habit:** factor repeated YAML into a shared base, and delete examples that overlap.
- **Here:** share what clusters really share, through `bases/`. Leave the examples whole.
- **Why:** an example is copied as one piece by someone learning. A shared fragment makes each example shorter and
  none of them copyable.
