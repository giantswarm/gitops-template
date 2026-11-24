# When something isn't Ready

Every step in these docs ends on a **Check** that describes what success looks like. This page is for when you don't
see it. It's sorted by what you see, not by which controller is complaining. Find the symptom, and its section says
what it means in this repository, why it happens, what you can do about it, and when it's Giant Swarm's to fix.

Most of it comes down to one habit. Flux nearly always tells you what's wrong, in the `Ready` condition of the object
that failed. The trick is finding that object, because one failure makes everything after it wait.

- [Read a failure](#read-a-failure)
- [Find what applied an object](#find-what-applied-an-object)
- [Everything says DependencyNotReady](#everything-says-dependencynotready)
- [The source can't be fetched](#the-source-cant-be-fetched)
- [A build fails](#a-build-fails)
- [A variable comes out empty](#a-variable-comes-out-empty)
- [Forbidden, or refused at admission](#forbidden-or-refused-at-admission)
- [A cluster's `Kustomization` waits on its health check](#a-clusters-kustomization-waits-on-its-health-check)
- [A new cluster's apps started before its nodes joined](#a-new-clusters-apps-started-before-its-nodes-joined)
- [A `HelmRelease` can't find its values](#a-helmrelease-cant-find-its-values)
- [A `HelmRelease` has run out of retries](#a-helmrelease-has-run-out-of-retries)
- [A cluster's upgrade failed](#a-clusters-upgrade-failed)
- [A cluster's first install failed](#a-clusters-first-install-failed)
- [SOPS can't decrypt](#sops-cant-decrypt)
- [A `SecretStore` or `ExternalSecret` isn't `Ready`](#a-secretstore-or-externalsecret-isnt-ready)
- [Something keeps changing back](#something-keeps-changing-back)
- [Suspend and resume](#suspend-and-resume)
- [Something is stuck Terminating](#something-is-stuck-terminating)
- [An app is `Ready` but doesn't answer](#an-app-is-ready-but-doesnt-answer)

The messages quoted here are those of Flux 2.7 and External Secrets Operator 2.14, the versions on Giant Swarm
management clusters today. `NS`, `NAME` and the like stand for the real names in your messages.

## Read a failure

Start with everything that isn't `Ready`, across the namespaces you use:

```sh
flux get kustomizations -A --status-selector ready=false
flux get helmreleases -A --status-selector ready=false
flux get sources all -A --status-selector ready=false
```

The `MESSAGE` column is the message of the object's `Ready` condition, which is usually the whole story. For one
object, its conditions and its recent events say more:

```sh
kubectl describe kustomization NAME -n NS
flux events --for Kustomization/NAME -n NS
```

The same works for `HelmRelease/NAME`, `GitRepository/NAME`, `OCIRepository/NAME` and the rest. `flux tree
kustomization NAME -n NS` lists what a Flux `Kustomization` applies. To go the other way, from an object to what
applied it, see [Find what applied an object](#find-what-applied-an-object).

When that isn't enough, read the controllers' logs. You and Giant Swarm share one Flux, in the `flux-giantswarm`
namespace. You can read its logs, though you can't change anything there (see
[What you can do, and what Giant Swarm does](../reference/repo-structure.md#what-you-can-do-and-what-giant-swarm-does)).
`flux logs` looks in `flux-system` unless you tell it otherwise:

```sh
flux logs --flux-namespace flux-giantswarm --kind Kustomization --name NAME --namespace NS
kubectl logs -n flux-giantswarm deployment/helm-controller --since 1h
```

The controllers are `source-controller`, `kustomize-controller`, `helm-controller` and `notification-controller`.

Once you've fixed the cause in Git and pushed, you don't have to wait for the next interval. Ask Flux to fetch the
repository and apply it now:

```sh
flux reconcile kustomization NAME -n NS --with-source
```

## Find what applied an object

Something on a cluster didn't change when you expected it to, and you don't know which Flux object to look at. Start
from the object. `flux trace` goes from an object to the Flux `Kustomization` or `HelmRelease` that applied it, and on
to the source and the revision it came from:

```sh
flux trace helmrelease NAME -n NS
flux trace -n NS deployment/NAME externalsecret/OTHER_NAME
```

The answer names the `Kustomization`, its namespace and `Path`, the `Revision` it last applied with the message of its
`Ready` condition, and then the `GitRepository` or `OCIRepository` with its own revision. Read it in this order:

- **The revision is older than your commit.** Flux hasn't applied your change yet, or can't. The `Message` says which,
  and the `Kustomization` it names is the one to [read](#read-a-failure).
- **The revision is your commit, and the object still hasn't changed.** Your change isn't in what that `Kustomization`
  builds. The file isn't under its `Path`, isn't listed in a `kustomization.yaml`, or a patch or a variable further
  along overrides it. [Render what Flux applies](./check-changes.md#render-what-flux-applies) shows you what it builds.
- **It names a `Kustomization` you didn't expect.** Then that's where the object's file has to change.

A `Kustomization` is an object too, so you can trace it in turn, and walk up the chain as far as the management
cluster's own:

```sh
flux trace kustomization NAME -n NS
```

`flux trace` works from labels. kustomize-controller puts `kustomize.toolkit.fluxcd.io/name` and
`kustomize.toolkit.fluxcd.io/namespace` on everything it applies, and helm-controller puts
`helm.toolkit.fluxcd.io/name` and `helm.toolkit.fluxcd.io/namespace` on everything a chart installs. An object without
them is followed up through its owners, so tracing a Pod finds its Deployment's `HelmRelease`, and tracing a Secret
that External Secrets Operator wrote finds its `ExternalSecret`'s `Kustomization`. Then it looks the Flux object up in
the cluster you're logged in to, and that's where it stops being able to help in three cases:

- **An app's objects in a workload cluster.** The `HelmRelease` that installed them, or the `-direct` `Kustomization`
  that pushed them, lives on the management cluster, so `flux trace` in the workload cluster finds the labels and then
  can't find the object they name. Read the labels there yourself, and trace the object they name on the management
  cluster:

    ```sh
    kubectl get deployment NAME -n NS -o jsonpath='{.metadata.labels}'  # in the workload cluster
    flux trace helmrelease HELMRELEASE_NAME -n HELMRELEASE_NAMESPACE     # on the management cluster
    ```

    Where the workload cluster runs its own Flux and that Flux applied the object, as with out-of-band objects it
    pulls, `flux trace` works in the workload cluster as it is.
- **An object a `ResourceSet` rendered.** Flux Operator labels it `resourceset.fluxcd.controlplane.io/name` and
  `resourceset.fluxcd.controlplane.io/namespace`, which `flux trace` doesn't know, so it reports
  `object not managed by Flux`. Read the two labels, then trace the `ResourceSet` they name, which a `Kustomization`
  applied:

    ```sh
    kubectl get helmrelease NAME -n NS -o jsonpath='{.metadata.labels}'
    flux trace resourceset RESOURCESET_NAME -n RESOURCESET_NAMESPACE
    ```

- **An object Flux didn't apply.** `object not managed by Flux`, and no label of the kinds above, means something else
  made it: an operator, Kyverno (`generate.kyverno.io/policy-name` names the policy, and the policy is what you
  trace), or someone with `kubectl`. A change in Git won't reach an object nothing in Git creates.

## Everything says DependencyNotReady

**What you see.** Many `Kustomization`s are `False` with reason `DependencyNotReady` and a message such as
`dependency 'default/MC_NAME-organization-ORG_NAME' is not ready`, or `dependency '...' revision is not up to date`.

**What it means.** Nothing is wrong with them. The `Kustomization`s here form a chain, each with the one before it in
`dependsOn`: the management cluster's `MC_NAME.yaml`, then each organisation's `namespace.yaml`, then each cluster's
`Kustomization`, then its apps `Kustomization`. They all read the same `GitRepository`, so each waits until the one
before it is `Ready` at the same commit (see [Flux `Kustomization`s](../reference/repo-structure.md#flux-kustomizations)).
One failure near the top makes everything below it wait, and say so, every 30 seconds.

**What you can do.** Follow the chain up. Open the dependency the message names; if it says `DependencyNotReady` too,
open its dependency, until you reach the one that fails for a reason of its own. Fix that, and the rest follow on
their own within a minute or so. While `MC_NAME.yaml` fails, no organisation applies anything new; while one
organisation's `namespace.yaml` fails, only that organisation's clusters wait.

A `HelmRelease` can wait in the same way, on another `HelmRelease` in its `dependsOn`. One that waits on a release the
cluster doesn't have, such as `gateway-api-crds` on a cluster without Envoy Gateway, waits for good, without an error.

## The source can't be fetched

**What you see.** The `GitRepository` is `False` with reason `GitOperationFailed` and a message that starts
`failed to checkout and determine revision: unable to clone 'URL'`, followed by the cause: that authentication is
required or failed, that the host can't be found, or `couldn't find remote ref "refs/heads/BRANCH"`. Or an
`OCIRepository` is `False`, with `OCIPullFailed` and `failed to determine artifact digest` for a tag that doesn't exist,
or with `no match found for semver: RANGE` for a range no tag satisfies. Everything that reads the source waits.

**What it means and what you can do.**

- *Authentication.* The token in the Secret that `spec.secretRef` names, such as `github-https-credentials` in
  `default`, has expired, been revoked, or can't read the repository. Create a new token and write the Secret again,
  as in [step 1](../tutorials/basic/getting-started.md#1-connect-the-management-cluster) of the basic tutorial. A token
  doesn't go into Git, so this is the one fix that isn't a push.
- *A missing branch or tag.* Check `spec.ref` against what's really there. For an `OCIRepository`, list the chart's
  tags in the registry, and remember that a `semver` range without `-0` ignores pre-releases.
- *The host can't be reached.* Check the URL. If it's right but the management cluster can't reach your Git host (one
  inside your own network, for example), ask Giant Swarm: the management cluster's network is theirs.

## A build fails

**What you see.** A `Kustomization` is `False` with reason `BuildFailed` and `kustomize build failed:` followed by
kustomize's error: a file that doesn't exist, a patch whose target isn't there, a resource listed twice.

**What it means.** The directory doesn't build, so Flux applies none of it, and keeps what it applied last. Nothing is
deleted while the build fails.

**What you can do.** Fix the files and push. The same mistake fails CI and `tools/fake-flux` on your machine, so
[Check a change before you push](./check-changes.md) catches most of these before they reach the cluster. A common
one on this layout is a commit that lists a file in a `kustomization.yaml` without adding the file itself.

## A variable comes out empty

**What you see.** Something applied with an empty value where a `${variable}` should be: a name ending in `-`, an
`OCIRepository` with no tag, or an apply that fails because a name is invalid.

**What it means.** Flux fills in `${variable}`s from the `Kustomization`'s `spec.postBuild`. On the management
cluster, a variable that isn't set becomes an empty string, without an error. CI is stricter, and fails on it.

**What you can do.** Set the variable in the `Kustomization`'s `postBuild.substitute` (see
[Variables](../reference/repo-structure.md#variables)). A `${variable}` that should reach the cluster as it is needs
escaping as `$${variable}`.

## Forbidden, or refused at admission

**What you see.** A `Kustomization` is `False` with a message such as `Kind/NS/NAME dry-run failed (Forbidden): ...
User "system:serviceaccount:org-ORG_NAME:automation" cannot create resource ...`. Or a push applies nothing new, and
the `Kustomization` that applies the file is `False` with a message from an admission webhook that names a Kyverno
policy, such as `flux-multi-tenancy`.

**What it means.** Flux applies the files as the `automation` ServiceAccount of the `Kustomization`'s namespace. The
management cluster limits what that account may do and which Flux objects it accepts (see
[What you can do, and what Giant Swarm does](../reference/repo-structure.md#what-you-can-do-and-what-giant-swarm-does)).
"Forbidden" means the account may not write that object there: a cluster directory, applied as the organisation's
account, holds an object in `default`, in another namespace, or a cluster-scoped one. A Kyverno refusal means a Flux
object breaks one of the rules, usually a `Kustomization` or `HelmRelease` without `serviceAccountName`, copied from
upstream Flux documentation.

**What you can do.** Move an object that belongs in `default` into what `MC_NAME.yaml` applies. Add
`serviceAccountName: automation` to a Flux object that lacks it, and keep its sources in its own namespace or in
`default`. A cluster-scoped object other than an `Organization` is Giant Swarm's to create, if they agree to.

## A cluster's `Kustomization` waits on its health check

**What you see.** A cluster's `Kustomization`, `WC_NAME.yaml`, is `Unknown` with reason `Progressing` and
`Reconciliation in progress` for a long time, and its apps `Kustomization` says `DependencyNotReady`. After 30 minutes
it turns `False` with reason `HealthCheckFailed` and a message that names the Cluster API `Cluster`.

**What it means.** The cluster's `Kustomization` only gets `Ready` once the `Cluster`'s `ControlPlaneAvailable` and
`RemoteConnectionProbe` conditions are `True`: its control plane is up, and the management cluster can reach it,
which is all the apps need to install. Its `timeout` of 30 minutes covers a new cluster coming up (see
[Flux `Kustomization`s](../reference/repo-structure.md#flux-kustomizations)). For a new cluster, waiting is normal. For
a running one, it means the control plane is down or out of reach. The worker nodes don't count: a node pool that's
short of nodes doesn't hold the `Kustomization` back.

A new commit doesn't cut the wait short. A fix you push to the cluster's files is only applied once the current wait
has run out, and then the next wait starts.

**What you can do.** Look at the cluster itself, which you can read:

```sh
kubectl get clusters -n org-ORG_NAME
kubectl describe cluster CLUSTER_NAME -n org-ORG_NAME
kubectl get machinedeployments,machinepools -n org-ORG_NAME
```

A condition that's `False` usually says why. If it's something in your values, fix it and push, and wait for the
current check to time out. If it's the infrastructure, such as a cloud quota or an outage, or the control plane has
been down for a long time with nothing in your files to explain it, it's Giant Swarm's: open a support ticket with the
cluster's name.

## A new cluster's apps started before its nodes joined

**What you see.** On a new cluster, the apps `Kustomization` is `Ready`, but the apps' pods wait `Pending`, and a
`HelmRelease` may fail with a timeout, uninstall, and try again.

**What it means.** The apps wait for the control plane, not for the worker nodes, so on a new cluster they can start
before any node has joined. A `HelmRelease` then runs out its 10-minute `timeout`. The app bases retry a failed install
up to 10 times, uninstalling it in between, so it settles by itself once the nodes join. It's the price of not holding
back every later change to the apps while one node pool is short.

**What you can do.** Usually nothing but wait. If the nodes don't come, look at the node pools as in the section
above, and if a `HelmRelease` has used up its retries by then, see
[A `HelmRelease` has run out of retries](#a-helmrelease-has-run-out-of-retries).

## A `HelmRelease` can't find its values

**What you see.** A `HelmRelease` is `False` with reason `ValuesError` and a message such as
`could not resolve ConfigMap chart values reference 'NS/NAME' with key 'values': configmaps "NAME" not found`.

**What it means.** Every entry in `spec.valuesFrom` that isn't `optional: true` has to exist. The usual ones here:

- `cluster-app-installation-values`, the first entry of every cluster's `HelmRelease`, which Giant Swarm provides in
  every organisation's namespace (see
  [Values from the management cluster](/bases/clusters/capa/readme.md#values-from-the-management-cluster)). If it's
  missing, every cluster in that organisation fails this way, and it's Giant Swarm's to fix.
- `CLUSTER_NAME-cluster-values`, the first entry of every app, which cluster-apps-operator creates once the cluster
  exists. An app on a cluster that isn't up yet waits for it. An apps `Kustomization` waits for the cluster, so you'll
  mostly see it on apps that don't, such as [multicluster apps](../tutorials/advanced/multicluster-apps.md).
- A `-user-values` ConfigMap or `-user-secrets` Secret of your own, whose name doesn't match the `HelmRelease`'s
  entry, or which the directory's `kustomization.yaml` doesn't list.

An app whose cluster's kubeconfig Secret doesn't exist yet says `could not get KubeConfig secret` instead, with reason
`RESTClientError`, and recovers by itself once the cluster is up.

**What you can do.** Fix the name or list the file, and push. The `HelmRelease` retries by itself, so a missing object
that turns up later needs nothing from you.

## A `HelmRelease` has run out of retries

**What you see.** A `HelmRelease` is `False` with reason `InstallFailed` or `UpgradeFailed` and Helm's error, and it
has a `Stalled` condition with reason `RetriesExceeded` and a message such as `Failed to install after 11 attempt(s)`.
It doesn't change any more, whatever you wait for.

**What it means.** Helm tried, failed, and Flux remediated as the `HelmRelease`'s `install.remediation` or
`upgrade.remediation` says, as many times as `retries` allows. After that it stops for good, until something changes
its spec or you tell it to try again. Helm's error says why: a values schema the chart rejects, a resource that
already exists, a hook or a workload that didn't get ready within `timeout`.

**What you can do.** Fix the cause. If the fix is a change to the `HelmRelease`'s spec, such as a new version or a
different `timeout`, pushing it is enough: a changed spec starts the count again. If the fix is somewhere else, such as
a values ConfigMap, a Secret or something in the workload cluster, tell Flux to start again:

```sh
flux reconcile helmrelease NAME -n NS --reset
```

`--reset` clears the failure count, so the `HelmRelease` gets its retries back. `--force` instead makes one install or
upgrade attempt even though the retries are spent.

## A cluster's upgrade failed

**What you see.** A cluster's `HelmRelease` is `False` with `UpgradeFailed` and Helm's error, and it doesn't try again.

**What it means.** The cluster base turns upgrade remediation off on purpose, with `upgrade.remediation.retries: 0`.
Flux remediates a failed upgrade by rolling the chart back, and for a cluster that's the Giant Swarm release it had:
the nodes that already rolled would roll a second time, with nobody watching. So a failed upgrade stays failed, for you
to look at.

**What you can do.** Read Helm's error in the `Ready` condition, and look at the cluster as in
[A cluster's `Kustomization` waits on its health check](#a-clusters-kustomization-waits-on-its-health-check). Fix the
cause in Git, or go back to the release the cluster had by reverting the commit, push, and once Flux has applied it,
start again:

```sh
flux reconcile helmrelease CLUSTER_NAME -n org-ORG_NAME --reset
```

## A cluster's first install failed

**What you see.** A new cluster's `HelmRelease` is `Stalled` with `RetriesExceeded` and `Failed to install after 1
attempt(s)`, and the cluster's `Kustomization` waits on its health check.

**What it means.** The cluster base turns install remediation off on purpose: `install.remediation` has no `retries`
and `remediateLastFailure: false`. Flux remediates a failed install by uninstalling it, and uninstalling a cluster
chart deletes whatever part of the cluster already exists. So a failed install stays failed and stays put, for you to
look at (see [The protected objects](../explanation/deletion-protection.md#the-protected-objects)). The release also
carries the `giantswarm.io/prevent-deletion` label, so you can't delete the `HelmRelease` to start afresh: the
management cluster refuses.

**What you can do.** Read Helm's error in the `Ready` condition, and the cluster's own state as in
[A cluster's `Kustomization` waits on its health check](#a-clusters-kustomization-waits-on-its-health-check). Common
causes are a cluster name longer than 20 characters, a release that doesn't exist, missing values from the
management cluster, and a values file the chart's schema rejects. Fix it in Git, push, and once Flux has applied the
fix, start again:

```sh
flux reconcile helmrelease CLUSTER_NAME -n org-ORG_NAME --reset
```

If you'd rather start from nothing, that means deleting the cluster, deliberately, as
[Delete a workload cluster](./delete-cluster.md) describes. If the install fails for reasons outside your files, such
as the cloud account or the release itself, it's Giant Swarm's.

## SOPS can't decrypt

**What you see**, on the `Kustomization` that applies the file:

- `Secret/NS/NAME is SOPS encrypted, configuring decryption is required for this secret to be reconciled`: the
  `Kustomization` has no `spec.decryption`.
- Reason `BuildFailed` and `secrets "NAME" not found`: the key Secret that `spec.decryption.secretRef` names isn't in
  the `Kustomization`'s namespace.
- Reason `BuildFailed` and `decryption failed for ...`, with `Failed to get the data key required to decrypt the SOPS
  file`: none of the keys in that Secret can decrypt the file. It was encrypted for another key.

**What it means and what you can do.**

- *No decryption.* Add `spec.decryption`, as [Decrypt a cluster's files](./sops.md#decrypt-a-clusters-files) shows.
- *No key Secret.* A cluster's key goes in its organisation's `namespace/secrets`, in the organisation's namespace,
  with its `Kustomization`s. The master key is `sops-gpg-master` in `default`. Check the Secret's name, and that its
  directory's `kustomization.yaml` lists it (see [SOPS keys](../reference/sops-keys.md)).
- *The wrong key.* The first rule in `.sops.yaml` whose `path_regex` matches a file picks its key when you encrypt
  it. A file encrypted before you added its cluster's rule, or under a rule that matches too much, has the wrong key.
  `sops` names the key in the file's `sops:` section. Encrypt it again with the right one (see
  [Change encrypted values](./sops.md#change-encrypted-values)).

A file someone changed by hand, without `sops`, has a broken MAC. Flux doesn't check the MAC, so it carries on
decrypting, and the cluster shows nothing wrong. `sops` does check it, so you find out the next time you edit or
rotate the file: it refuses with a MAC mismatch. Write the file again from scratch with its values, encrypted, rather
than patching it.

## A `SecretStore` or `ExternalSecret` isn't `Ready`

**What you see.** A `SecretStore` is `False` with reason `InvalidProviderConfig` and `unable to validate store` or
`unable to create client`. Or an `ExternalSecret` is `False` with reason `SecretSyncedError` and
`could not get secret data from provider`.

**What it means.** The store is how External Secrets Operator logs in to your secret manager; the `ExternalSecret`
reads through it. The `ExternalSecret`'s message is the same whatever went wrong, so look at its store first: a store
that isn't `Ready` fails every `ExternalSecret` that uses it. A store fails on its credentials, or on settings such as
a region or a vault URL. A ready store with a failing `ExternalSecret` usually means the key or property it asks for
doesn't exist, or the store's credentials may not read it.

**What you can do.** Read the events, which carry more detail than the conditions:

```sh
kubectl describe secretstore STORE_NAME -n NS
kubectl describe externalsecret NAME -n NS
```

Fix the store's credentials or the `ExternalSecret`'s `remoteRef`, in your secret manager or in Git. An
`ExternalSecret` fetches again every `refreshInterval`; to fetch at once, change any annotation on it:

```sh
kubectl annotate externalsecret NAME -n NS force-sync=$(date +%s) --overwrite
```

External Secrets Operator itself, and the cluster-wide stores, are Giant Swarm's (see
[Secrets](../explanation/secrets.md)).

## Something keeps changing back

Everything is `Ready`, and yet a value keeps changing back: a Secret holds one value, then another, a release's
revision climbs with no change in Git, the `kustomize.toolkit.fluxcd.io/name` label switches between two
`Kustomization`s, or an object disappears while its file is still in Git and comes back a few minutes later.

> [!Caution]
> Two reconcilers are writing the same object, or one is writing it twice, and nothing reports it as an error. See
> [One owner per object](../explanation/one-owner.md).

Find both writers: [find what applied the object](#find-what-applied-an-object), then list everything that has
written to it:

```sh
kubectl get KIND NAME -n NS --show-managed-fields -o yaml
```

Then take the object away from all but one of them, in Git. A Secret that both an `ExternalSecret` and a
SOPS-encrypted file write is the commonest case here, see
[One Secret, one route](../explanation/secrets.md#one-secret-one-route).

When both writers are Flux `Kustomization`s, CI finds them before you merge: `test_no_object_has_two_kustomizations`
fails and names the object and both `Kustomization`s (see [Objects in two builds](../reference/ci-checks.md#objects-in-two-builds)).
It needs no cluster, so run it on your branch to check a fix:

```sh
cd tests/ats
pipenv install --deploy
KUBECONFIG=/dev/null pipenv run pytest test_one_owner.py
```

## Suspend and resume

Sometimes you want Flux to stop for a while: to try a change by hand, or to keep it from undoing one while you work.
Suspend the object, and resume it when you're done:

```sh
flux suspend kustomization NAME -n NS
flux resume kustomization NAME -n NS
```

A suspended `Kustomization` stops applying and keeps the status it had: it stays `Ready`, at the revision it applied
last. Everything that depends on it stops too. Its dependants read the same `GitRepository`, so as soon as you push a
new commit they wait for it to apply that commit. Until you resume it, they report
`dependency '...' revision is not up to date`. Suspend `MC_NAME.yaml` and every organisation and cluster stops
following Git, though they all look fine.

`flux resume` applies the latest commit at once, and waits until the object is `Ready` again. A suspended
`HelmRelease` behaves the same way, with one more catch: if it's deleted while suspended, Flux doesn't uninstall its
chart. Suspending is a change on the cluster, not in Git, so nothing reminds you to resume. Write it down somewhere
your team will see it.

## Something is stuck Terminating

**What you see.** An object has a `deletionTimestamp` and doesn't go away. Its finalizers say who it's waiting for:

```sh
kubectl get KIND NAME -n NS -o jsonpath='{.metadata.finalizers}'
```

**What it means.** A finalizer is a controller's promise to clean up before the object goes. The object stays until
that controller has done its work and removed the finalizer. When the controller can't do its work, the object waits
for good.

The case this repository can lead you into is a `-direct` `Kustomization`, which applies `out-of-band` to a workload
cluster through the cluster's kubeconfig Secret. Deleting it means deleting what it applied, in the workload cluster.
If the cluster went first, its kubeconfig Secret went with it. Flux can't reach the cluster to clean up, and the
`Kustomization` stays `Terminating`, retrying, for good. [Delete a workload cluster](./delete-cluster.md) removes it
before the cluster for exactly this reason.

**What you can do.** For the `-direct` `Kustomization`, tell Flux to let it go without cleaning up. A suspended
`Kustomization` that's being deleted leaves its objects alone and removes its finalizer:

```sh
kubectl patch kustomization NAME -n org-ORG_NAME --type merge -p '{"spec":{"suspend":true}}'
```

The objects it applied went with the cluster anyway. Don't remove a finalizer by hand when the controller can still
do its job: whatever it would have cleaned up stays behind, and nothing tracks it any more.

In a workload cluster, an object stuck `Terminating` is usually waiting for its own controller, such as a `Namespace`
waiting for its contents or a `GatewayClass` waiting for its `Gateway`s (see
[envoy-gateway](/bases/stacks/envoy-gateway/README.md)). Those are yours to look at, as the cluster's admin. An object
on the management cluster waiting for a finalizer of Giant Swarm's controllers, such as a cluster's resources while
Cluster API deletes it, is Giant Swarm's to look at if it doesn't move.

## An app is `Ready` but doesn't answer

**What you see.** Every `HelmRelease` is `Ready`, but the app's address doesn't resolve, times out, or comes with a
certificate the browser doesn't trust.

**What it means.** An app served through Envoy Gateway needs four things that `Ready` doesn't check: the
`giantswarm-default` Gateway has an address, a DNS record points the app's hostname at it, the Gateway's certificate
covers the hostname, and the app's `HTTPRoute` is attached to the Gateway. A different controller on the workload
cluster sees to each one, and none of them reports back to Flux. The record and the certificate take five to ten
minutes after the Gateway gets its address, so give them that first.

**What you can do.** Check them in order, on the workload cluster:

1. The Gateway has an address:

    ```sh
    kubectl get gateway giantswarm-default -n envoy-gateway-system
    ```

    An empty `ADDRESS`, with `PROGRAMMED` `False`, means the Gateway's Service has no load balancer, and nothing after
    it can work. On AWS, the Gateway gets its address from the AWS Load Balancer Controller, which isn't part of a
    Giant Swarm release. Install Giant Swarm's `aws-lb-controller-bundle` on the workload cluster as
    [its README](https://github.com/giantswarm/aws-lb-controller-bundle#installing) describes, or ask Giant Swarm to.
    On Azure and Cloud Director the release provides the load balancer. On vSphere it does too, from the addresses in
    the cluster's `global.connectivity.network.loadBalancers`: with none left, or none set, the Gateway gets no
    address. See [The Gateway's address](./other-providers.md#the-gateways-address).

1. The hostname has a DNS record. The Gateway only creates records, and certificate entries, for the subdomains in
   `gateways.default.listeners.https.subdomains` of the `gateway-api-config` values. The records it asks external-dns
   for are in its `DNSEndpoint`:

    ```sh
    kubectl get dnsendpoint gateway-giantswarm-default-https -n envoy-gateway-system -o jsonpath='{.spec.endpoints[*].dnsName}'
    ```

    A hostname that isn't listed there gets no record: add its subdomain to the values.

1. The certificate is `Ready`:

    ```sh
    kubectl get certificate -n envoy-gateway-system
    ```

    If it stays `False`, `kubectl describe` it. The Gateway's issuer solves Let's Encrypt's challenge through the
    Gateway, which needs cert-manager's Gateway API support:
    `global.apps.certManager.values.cert-manager.config.enableGatewayAPI: true` in the cluster's values, and a restart
    of cert-manager once the Gateway API CRDs are in, as
    [the basic tutorial](../tutorials/basic/getting-started.md#4-deploy-an-app) does.

1. The route is attached. Each entry under the route's `status.parents` should have `Accepted` and `ResolvedRefs`
   `True`:

    ```sh
    kubectl get httproute NAME -n NS -o jsonpath='{range .status.parents[*].conditions[*]}{.type}={.status} ({.reason}){"\n"}{end}'
    ```

    Giant Swarm's [route requirements](https://docs.giantswarm.io/tutorials/connectivity/gateway-api/route-requirements/)
    say what each reason means.

The Gateway, its values and the cluster's values are yours. If cert-manager or external-dns themselves don't run, or
the bundle doesn't install, that's Giant Swarm's.
