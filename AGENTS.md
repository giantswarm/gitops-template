<!-- BEGIN devctl-managed: edits in this block are overwritten -->
<!-- markdownlint-disable-file MD041 -->

## Giant Swarm conventions

devctl maintains this block from [its template][devctl-agents-block] and
overwrites changes to it. Instructions for this repository go in the section
below. Where they differ from this block, they take precedence.

[devctl-agents-block]: https://github.com/giantswarm/devctl/blob/main/pkg/gen/input/llm/internal/file/agents_block.md.template

- Never put customer names or other customer information in code, commit
  messages, issues or pull requests. Most Giant Swarm repositories are public,
  and private ones are kept ready to become public.
- Giant Swarm's style guides are in <https://github.com/giantswarm/fmt>, one
  directory per topic (go, helm, kubernetes, prometheus, …). Read the relevant
  guide before you write or review that kind of code.
- Use conventional commits for commit messages and pull request titles.
- If `.github/workflows/zz_generated.auto_release.yaml` exists, GitHub Releases
  are written from pull request titles: do not edit CHANGELOG.md. Otherwise,
  add your change to CHANGELOG.md as described in
  <https://github.com/giantswarm/fmt/blob/main/releases/changelog.md>.
- If `.pre-commit-config.yaml` exists, run
  `pre-commit run --files <changed files>` before committing; not every clone
  has the hooks installed.
- Do not add linters, formatters or other tooling unless asked; use what the
  repository already has.
- Put documentation in `docs/` rather than growing README.md, which gives an
  overview and links into `docs/`. When a change affects documented behaviour,
  update the documentation in the same pull request.
- If the skills of the `giantswarm/claude-code` plugin marketplace are not
  available to you and the user works at Giant Swarm, tell them once that
  they can install the `gs-base` and `gs-dev`
  plugins from it.

<!-- END devctl-managed -->

## This repository

This is a template. A customer copies it, replaces the examples with their own management cluster, organisations and
clusters, and the copy becomes the repository their production clusters are applied from. Whether you're working on the
template or in a copy of it, the rules below hold. They differ from what upstream Flux documentation assumes, so
don't fall back on that.

The [`giantswarm-gitops` skill](.agents/skills/giantswarm-gitops/SKILL.md) gives the reasons behind these rules and
the cases where upstream advice doesn't apply. Load it before you change a manifest. If your agent doesn't find skills
in `.agents/skills` or `.claude/skills` by itself, read that file.

### Read first

- [Repository structure](docs/reference/repo-structure.md): the layout, the Flux `Kustomization`s, the variables, and
  [what you can do and what Giant Swarm does](docs/reference/repo-structure.md#what-you-can-do-and-what-giant-swarm-does).
- The `README.md` of the directory you're about to change. Every example directory has one, and it says what the
  directory shows and what to change when you copy it.
- [The documentation home](docs/README.md) for everything else. The tutorials teach; the reference pages and how-to
  guides are where the exact rules and commands are.

### What the platform allows

Flux runs once per management cluster, in `flux-giantswarm`, and Giant Swarm operates it. There is no `flux-system`.
The repository's author is not a cluster admin:

- Write only namespaced objects, and only in `default` and the organisations' `org-*` namespaces.
- The only cluster-scoped kinds are `Organization` and, on CAPA, `AWSClusterRoleIdentity`. No `Namespace`,
  `ClusterRole`, `ClusterRoleBinding`, `ClusterPolicy` or CRD.
- Every `Kustomization`, `HelmRelease` and `ResourceSet` on the management cluster names
  `serviceAccountName: automation`, or `kubeConfig` when it applies to a workload cluster. Without one, the management
  cluster refuses it.
- A source is in the object's own namespace or in `default`.
- Installing or configuring Flux, Flux Operator, Kyverno, External Secrets Operator or anything in a namespace other
  than `default` and `org-*` is Giant Swarm's to do. When a change needs that, say so; don't write it into the
  repository.
- Some objects the examples read aren't in the repository because the management cluster creates them, see
  [Objects the management cluster provides](docs/reference/repo-structure.md#objects-the-management-cluster-provides).
  Don't add them.

### What not to carry over from upstream

- Don't bootstrap or install Flux, and don't add `flux-system`, `gotk-components.yaml` or `gotk-sync.yaml`.
- Don't recommend `--no-cross-namespace-refs`. Objects here refer to sources in `default` on purpose.
- Don't set `spec.prune: false` to protect something. `Kustomization`s keep `prune: true`, and the objects whose
  deletion would do harm carry the `kustomize.toolkit.fluxcd.io/prune: disabled` annotation, see
  [Deletion protection](docs/explanation/deletion-protection.md).
- Don't take charts from upstream registries. Apps and clusters come from Giant Swarm's charts on
  `gsoci.azurecr.io`, at versions Giant Swarm ships.
- Don't let two things reconcile one chart, such as an `App` and a `HelmRelease` for the same release.
- Clusters are Cluster API clusters, `cluster.x-k8s.io/v1beta2`. There are no other kinds of cluster here.

### What the layout means

- `management-clusters/MC_NAME/MC_NAME.yaml` is the one `Kustomization` the management cluster starts from. It
  applies only `Organization`s and objects in `default`.
- An organisation is a unit that owns many clusters, such as a department. Its `namespace.yaml` applies everything
  of the organisation's into `org-<name>`, as that namespace's own `automation` account, so one organisation's files
  can't reach another's.
- A workload cluster is a directory and the `Kustomization`s beside it. `cluster/` and `apps/` are applied to the
  management cluster, where Flux installs the apps into the workload cluster through its kubeconfig. `out-of-band/`
  goes straight into the workload cluster, pushed by the management cluster or pulled by Flux in the workload
  cluster.
- `bases/` holds what clusters share. A change there changes every cluster that uses it.
- A file Flux should apply has to be listed in a `kustomization.yaml`. A new cluster also goes into the
  organisation's `workload-clusters/kustomization.yaml`.

### The examples are deliberate

Each `CAPITAL_LETTER.yaml` under `workload-clusters/`, with its directory, shows a different thing a customer does,
and the [workload-clusters README](management-clusters/MC_NAME/organizations/ORG_NAME/workload-clusters/README.md)
says which. Two examples that look alike differ in the one thing they demonstrate:
`WC_NAME_OUT_OF_BAND_FLUX_APP` and `WC_NAME_OUT_OF_BAND_NO_FLUX_APP` carry the same apps and differ in how
`out-of-band/` reaches the workload cluster. Don't merge, move, deduplicate or delete examples to tidy them, and
don't change what one demonstrates without asking.

The template guides and never restricts: don't add policies that refuse what a customer may create in their own
namespaces.

### Secrets

SOPS and External Secrets Operator are both supported, alone or together. Don't remove either.

- Never write a secret in plain text into the repository, not even for a moment. Encrypt on the way into the file,
  as [SOPS](docs/how-to/sops.md) shows. `tools/check-sops-encrypted` runs in `pre-commit` and refuses a `*.enc.yaml`
  that isn't encrypted.
- Don't edit an encrypted file's content by hand: any change outside `sops` breaks its MAC.
- A `SecretStore` is not a Secret. Anyone who can read the management cluster can read what a test store holds.
- In a customer's copy the keys are real, and CI runs with the real master key. There is no test mode.

### Check your work

- `pre-commit run --files <changed files>`, see [Run pre-commit](docs/how-to/check-changes.md#run-pre-commit).
- `tools/test-all-ff validate` after any change to a manifest or a tool. It needs no cluster, see
  [Validate with test-all-ff](docs/how-to/check-changes.md#validate-with-test-all-ff).
- Neither needs a cluster. The first place the repository runs is CI's kind test, see
  [CI checks](docs/reference/ci-checks.md); after the merge, Flux applies it.
- A directory you add under the examples needs a `README.md`, and a change to behaviour the documentation describes
  updates the documentation in the same pull request.

### When you work on the template itself

[CONTRIBUTING.md](CONTRIBUTING.md) applies. Every example has to get `Ready` in CI, and everything a reader sees, the
docs, the READMEs and the comments in the examples, follows [Voice](docs/contributing/voice.md). The layout's
[structure version](docs/reference/repo-structure.md#structure-version) has to stay in step with `kubectl gs gitops`,
which is another team's tool: report what it needs, don't assume a change there.
