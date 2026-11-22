---
name: giantswarm-gitops
description: How GitOps works on a Giant Swarm management cluster, for work in this template or a fork of it. Use it before adding or changing a workload cluster, an organisation, an app, a Flux Kustomization, HelmRelease or ResourceSet, a SOPS or External Secrets Operator secret, or anything under bases/ or management-clusters/, and before reviewing such a change or diagnosing something that isn't Ready. It covers what the platform lets the repository do, where upstream Flux advice doesn't apply, why the layout is as it is, and how to check a change without a cluster.
license: Apache-2.0
---

# GitOps on a Giant Swarm management cluster

This repository is applied by a Flux that Giant Swarm runs, on a cluster the repository's author doesn't administer.
Most of what you know about Flux comes from upstream documentation, which assumes you own the cluster. Here you
don't, and several upstream habits produce files the management cluster refuses, or that do harm once applied.

`AGENTS.md` has the rules in short. This skill gives the reasons, so you can judge a case the rules don't name. Paths
are from the repository root.

## Before you change anything

1. Find out whose repository this is. The template (`giantswarm/gitops-template`) holds examples with placeholder
   names such as `MC_NAME` and `WC_NAME`. A fork holds a customer's real clusters, and a merge there changes
   production. Keys and secrets in a fork are real.
2. Read the `README.md` of the directory you're about to change, and `docs/reference/repo-structure.md` for the rule
   you're about to rely on.
3. If the task needs something the platform doesn't allow (see below), stop and say so. Don't write a workaround into
   the repository.

## Who may do what, and why

Giant Swarm and the customer share one Flux, in `flux-giantswarm`. Giant Swarm's rbac-operator decides what the
repository may do, and two admission policies enforce it. `docs/reference/repo-structure.md`, section "What you can
do, and what Giant Swarm does", is the full statement. In short:

- **Namespaced objects only, in `default` and the organisations' `org-*` namespaces.** The customer isn't a cluster
  admin, so a `Namespace`, `ClusterRole`, `ClusterRoleBinding`, `ClusterPolicy` or CRD in the repository fails when
  Flux applies it. The two cluster-scoped kinds the platform grants on purpose are `Organization` and, on CAPA,
  `AWSClusterRoleIdentity`.
- **Every `Kustomization`, `HelmRelease` and `ResourceSet` names `serviceAccountName: automation`**, or `kubeConfig`
  when it applies to a workload cluster. Flux then acts with that account's rights and no more. One without either is
  refused at admission: that's what stops a file in Git from borrowing Flux's own rights.
- **`default/automation` reaches every organisation; `org-<name>/automation` reaches only its own.** So the
  repository keeps the first account's work small. `management-clusters/MC_NAME/MC_NAME.yaml` applies only
  `Organization`s and objects in `default`, and everything of an organisation's is applied from its own namespace, as
  its own account. A mistake in one organisation's files then can't reach another's. Don't move an organisation's
  objects into `default` to make something work.
- **Sources are in the object's own namespace or in `default`.** Cross-namespace references to `default` are how the
  one `GitRepository` serves every organisation. They're intended.
- **The platform's own apps aren't the repository's.** Flux, Flux Operator, Kyverno, External Secrets Operator and
  anything in `flux-giantswarm`, `giantswarm` or `kyverno` are installed, upgraded and configured by Giant Swarm. So
  is granting an `automation` account more rights. When a task needs one of these, the answer is "ask Giant Swarm",
  written in the pull request, not a manifest.
- **Some objects the examples read are created by the management cluster**, such as the `${cluster_name}-kubeconfig`
  Secret and the `${cluster_name}-cluster-values` ConfigMap. Don't add them to the repository.

## Where upstream advice doesn't apply

Read `references/upstream-differences.md` when you're about to copy something from Flux, kustomize, Helm or
Kubernetes documentation, or when a review comment says "upstream does it differently". It lists each habit, what to
do here and why.

## How the layout works, and why

`docs/explanation/how-it-works.md` tells this in full. What you need to hold in your head:

- **A chain of `Kustomization`s, each applying the next.** The management cluster's applies the organisations and
  each organisation's `namespace.yaml`; that applies the organisation's `namespace/` directory into `org-<name>`,
  which lists `workload-clusters/`; each cluster's `Kustomization` applies the cluster's directory. Each link has its
  own rights and its own failures, so a mistake stops as little as possible.
- **A file Flux should apply has to be listed.** Every directory has a `kustomization.yaml`, and a file that isn't in
  it does nothing. A new cluster's `Kustomization`s go into `workload-clusters/kustomization.yaml`. "It isn't being
  applied" is nearly always this.
- **Three directories per cluster.** `cluster/` holds the cluster itself: a chart, installed on the management
  cluster, that creates it with Cluster API. `apps/` holds the apps: `HelmRelease`s that stay on the management
  cluster and install into the workload cluster through its kubeconfig. `out-of-band/` holds what must be applied
  inside the workload cluster directly, and is left out of the cluster's `kustomization.yaml` on purpose.
- **Out-of-band has two deliveries.** The management cluster pushes it, with a `Kustomization` that has `kubeConfig`
  (the template names it `<cluster>-direct.yaml`), or Flux running in the workload cluster pulls it. Both are valid.
  Which one a cluster uses is the cluster owner's decision.
- **The apps wait for the cluster.** A cluster with an apps `Kustomization` gates it on the cluster's control plane
  being available and reachable, not on every node pool, so one short node pool doesn't hold back every change.
- **`bases/` is shared.** A change there changes every cluster that uses the base, the stack or the component. Say
  which clusters a change to `bases/` reaches.
- **Variables come from the cluster's `Kustomization`.** `${cluster_name}`, `${organization}`, `${release}` and the
  rest are set in `spec.postBuild.substitute`. A variable that comes out empty is missing there.
- **An organisation owns many clusters.** It's a unit such as a department. Apps for all of an organisation's
  clusters at once go in its `multicluster/` directory, as a `ResourceSet`.

## Deleting is the dangerous direction

`Kustomization`s here have `prune: true`: take a file out of Git and Flux deletes what it created. That's wanted for
an app and ruinous for a cluster. So:

- Objects whose deletion would take a cluster or an organisation with them carry
  `kustomize.toolkit.fluxcd.io/prune: disabled`, and clusters also carry `giantswarm.io/prevent-deletion`.
  `docs/explanation/deletion-protection.md` lists them. Never remove either to make a change go through.
- Renaming a `Kustomization`, or moving its file to where another `Kustomization` applies it, is a deletion followed
  by a creation, and the old one's finalizer deletes what it applied. Treat every rename and move of a Flux object as
  a deletion, and check what it would prune.
- Deleting a cluster is a procedure with an order, in `docs/how-to/delete-cluster.md`. Follow it; don't delete the
  directory.
- When you propose a change that removes or moves anything, say what Flux will delete as a result.

## The examples are deliberate

Each `CAPITAL_LETTER.yaml` under `workload-clusters/`, with its directory, shows one thing a customer does. Examples
that look alike differ in the one thing they demonstrate: `WC_NAME_OUT_OF_BAND_FLUX_APP` and
`WC_NAME_OUT_OF_BAND_NO_FLUX_APP` carry the same apps and differ only in how `out-of-band/` arrives. Duplication
between examples is the point, because a customer copies one whole.

So don't merge, deduplicate, move or delete examples, and don't "fix" one to match another, without asking what it
demonstrates. Every example has to get `Ready` in CI: an example that needs something CI doesn't have gets the
prerequisite installed, never an exclusion.

The template guides and doesn't restrict. Don't add a policy that refuses something a customer may create in their
own namespaces, however sensible the rule looks.

## Secrets

SOPS, External Secrets Operator, or both: all three are valid, and `docs/explanation/secrets.md` says which secret
suits which. Don't remove one in favour of the other.

- **Nothing in plain text, not even for a moment.** Pipe a Secret into `sops` so it's encrypted on its way into the
  file, as `docs/how-to/sops.md` shows. Never write the plain file first and encrypt it after.
- **Don't edit an encrypted file by hand.** Any change outside `sops`, including to its metadata, breaks its MAC.
  That's why a SOPS Secret names its real namespace from the start.
- **A decrypted value stays on the machine.** Decrypt only to change a value, as `docs/how-to/sops.md` describes,
  and never put one in a commit, a pull request, a comment or a log.
- **A `SecretStore` is not a Secret.** Anyone who can read the management cluster can read what it holds, so a test
  store holds dummy values only.
- **A fork's CI runs with the real master key.** There's no test mode. Don't propose a "test key".

## Check your work without a cluster

Nothing here needs a cluster to check, and nothing should be applied to one by hand to see whether it works.

- `pre-commit run --files <changed files>`: lint, the README check and the SOPS check.
- `tools/test-all-ff validate`: builds every Flux `Kustomization` as Flux would, and validates the result against the
  schemas. Run it after any change to a manifest or a tool. It takes a few minutes.
- `tools/fake-flux build <kustomization>`: shows exactly what one `Kustomization` would apply, to compare before and
  after a change.
- CI's kind test applies the whole repository to a throwaway cluster. A pull request that changes only documentation
  or comments skips it; `docs/reference/ci-checks.md` says what runs when.

A hook or a test that fails is telling you something. Fix the cause; don't skip the hook or exclude the object.

## When something isn't `Ready`

`docs/how-to/troubleshooting.md` goes from symptom to cause. Read the failing object's own message first, then walk
up the chain: a cluster's `Kustomization` that says `DependencyNotReady` is waiting for the one above it, and the
fault is there.

## How to report

- State what a change will make Flux create, change and delete, and on which clusters.
- Separate what you verified (and how) from what only a cluster would show.
- Name anything that is Giant Swarm's to do.
- If a rule here stops the task, say which and stop. Don't route around it.
