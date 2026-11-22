# Configure CI in a fork

Your fork comes with GitHub workflows that check every pull request before Flux ever sees it. Most of them work as
they are. This page covers the parts you set yourself: which upstream workflows you follow, what the kind test needs in
your fork, its settings and its one secret, and when the workflows run. [CI checks](../reference/ci-checks.md) says
what each job checks.

## The workflows

`validate.yaml`, `yaml-diff.yaml` and `validate-file-names.yaml` call shared workflows from
[giantswarm/github-workflows](https://github.com/giantswarm/github-workflows) at a commit SHA, followed by a `# main`
comment, so a change there doesn't change your CI until you take it. With Renovate and the `renovate.json5` this
repository ships, Renovate opens a pull request that moves the SHA to the newest commit on `main` and merges it once
your checks pass. Without Renovate, move the SHA yourself when you want a fix from upstream.

[validate.yaml](../../.github/workflows/validate.yaml) is the one with settings. It passes them to the shared workflow
as inputs, each with a comment that says why it has the value it has:

| Input | Value in this repository |
| --- | --- |
| `python_version` | the Python of `tests/ats/Pipfile` |
| `kubeconform_ver` | the `kubeconform` of `tools/test-all-ff` |
| `kind_ver` | the kind release whose default node image runs the Kubernetes minor version of the management clusters |
| `gitops_flux_app_version` | the `flux-app` chart on the management clusters |
| `gitops_ignored_objects` | empty |
| `gitops_init_namespaces` | `default` |

Renovate keeps the versions up to date through the `# renovate:` comment above each. `kind_ver` follows the
management clusters, not kind's releases: an `allowedVersions` bound in `renovate.json5` keeps it, and the other pins
that stand for what the management clusters run, at the versions they run. When the management clusters move, raise
the bound there.

## The kind test in your fork

The kind test isn't only the template's: it runs on whatever your fork has under `management-clusters/`. It finds the
root Flux `Kustomization` of each management cluster, the `GitRepository` it reads and the Secret it decrypts with in your
files, so a management cluster built with the [basic tutorial](../tutorials/basic/getting-started.md), with a
`GitRepository` name of your own, needs no change to the test. Three things are yours to do:

1. **Set the master key.** Put your management cluster's private master key in the repository secret
   `GITOPS_MASTER_GPG_KEY` (see [Configuration](#configuration) below), and read
   [What the key in CI means](#what-the-key-in-ci-means) first. If your management cluster's `Kustomization` has no
   `decryption`, as with External Secrets Operator only, there's nothing to set.
1. **Delete the template's examples.** `management-clusters/MC_NAME` holds example SOPS secrets, there to show what an
   encrypted Secret looks like. They're encrypted for the template's master key, which your fork doesn't have, so the
   test can't decrypt them: delete the directory, and the template's rules for `MC_NAME` in `.sops.yaml`. If you'd
   rather keep the examples to read, leave them, and list your own management clusters in `managementClusters` in
   [tests/ats/kind-test.yaml](../../tests/ats/kind-test.yaml) instead, so the test applies only yours.
1. **Write bindings for your own clusters, when you want more than `Ready`.** Out of the box, the test checks that
   everything your management clusters apply gets `Ready`, at the platform's versions, rights and admission rules. The
   checks of the template's examples are skipped once the examples are gone, each saying why. To check more of your
   own, add to `kind-test.yaml` and `tests/ats/assertions`, as
   [Write bindings for your own clusters](../tutorials/advanced/testing.md#write-bindings-for-your-own-clusters)
   describes.

What the test proves, and what it stands in for, such as your secret manager and cluster creation, is in
[What the test proves, and what it can't](../reference/ci-checks.md#what-the-test-proves-and-what-it-cant).

### What the key in CI means

The kind test checks that production will work, so it decrypts with production's key: there's no test key that would
prove your secrets decrypt. That has a cost, and it's worth saying plainly:

- Every run decrypts your management cluster's secrets on a GitHub-hosted runner, into a kind cluster that lives as
  long as the job.
- Anyone who can change a workflow, which is anyone with write access to the repository, can read the secret. Treat
  write access to the repository as access to the key, and so to every secret it decrypts.
- GitHub gives a pull request from a fork of your repository no secrets, so an outsider's pull request can't read it;
  the test skips its cluster checks there instead.
- Flux in the kind cluster uses what it decrypts, as it would in production. Your own `Alert`s and `Provider`s post
  real commit statuses or chat messages, for the pull request's head commit, with the tokens they decrypt; the test
  suspends only the template's example `Alert`s. Anything else the repository decrypts that reaches outside the kind
  cluster, such as a kubeconfig encrypted with SOPS for a `Kustomization` or `HelmRelease` to deploy to a cluster,
  gets used: Flux applies to that cluster from the pull request's branch.

If that's more than you want to give CI, don't set the secret, and don't run the kind test: stop calling the shared
workflow from `validate.yaml`, as
[Choose `tests/ats`, Chainsaw or both](../tutorials/advanced/testing.md#choose-testsats-chainsaw-or-both) describes.

## Configuration

The kind test reads these settings, which `validate.yaml` sets through the inputs above and a repository secret:

- `GITOPS_FLUX_APP_VERSION`: the version of [flux-app](https://github.com/giantswarm/flux-app/releases)
  provided by Giant Swarm.
- `GITOPS_INIT_NAMESPACES`: a comma-separated list of the namespaces that exist before Flux applies the repository.
  The test creates the ones that don't exist, and an `automation` ServiceAccount in each, with the rights it has on a
  management cluster (see
  [The rights of the `automation` ServiceAccounts](../reference/ci-checks.md#the-rights-of-the-automation-serviceaccounts)).
  [validate.yaml](../../.github/workflows/validate.yaml) sets it to `default` with the `gitops_init_namespaces` input
  of the shared workflow, whose default also names `org-org-name`. The test fails for an `org-*` namespace in the
  list: as on a new management cluster, the organisation's namespace exists only once Flux has applied its
  `Organization` (see
  [The organization-operator stand-in](../reference/ci-checks.md#the-organization-operator-stand-in)).
- `GITOPS_IGNORED_OBJECTS`: a comma-separated list of (namespaced) `HelmRelease`s and sources that the test doesn't
  look at, such as `org-org-name/my-helmrelease`. It doesn't apply to `Kustomization`s, which all have to get
  `Ready`. [validate.yaml](../../.github/workflows/validate.yaml) sets it with the `gitops_ignored_objects` input of
  the shared workflow, empty in this repository. Keep it empty: an example the test can reconcile has to get `Ready`,
  so install what it needs in the test instead.
- `GITOPS_MASTER_GPG_KEY`: a repository secret holding your private master GPG key, armoured (with its
  `-----BEGIN...` and `-----END...` lines) and then base64-encoded. The test puts it in the Secret each management
  cluster's root `Kustomization` names in `spec.decryption.secretRef`, such as `sops-gpg-master`. With several
  management clusters that decrypt, export all their keys at once, into one armoured block. When no root decrypts, the
  key isn't needed. When a root does, an empty key fails the test, in your fork's own runs too, with one exception: a
  pull request from a fork gets no secrets from GitHub, so there the test skips every test that needs the cluster and
  says so in a warning on the run. The checks that need no cluster still run.
- `GITHUB_TOKEN`: the run's own token, which the shared workflow passes to the test. The test's `GitRepository`s read
  the repository with it, so the test works in a private repository too. You set nothing.
- [tests/ats/kind-test.yaml](../../tests/ats/kind-test.yaml): which management clusters the test applies, and the
  bindings of the example checks (see [Configure the kind test](../reference/ci-checks.md#configure-the-kind-test)).

To set the secret from the master key in your keyring, for example with the GitHub CLI:

```sh
gpg --export-secret-keys --armor "${KEY_FP}" | base64 -w0 | gh secret set GITOPS_MASTER_GPG_KEY
```

Only the master key decrypts what the kind test applies: the workload clusters' keys are in the repository, encrypted
with it. Read [What the key in CI means](#what-the-key-in-ci-means) before you set it.

## When the workflows run

`validate.yaml` runs on every pull request, whatever branch it targets, and on every push to `main`. The push run
checks `main` as it is after a merge, which no pull request run has tested when two pull requests merge one after the
other. If your fork's default branch has another name, or you want post-merge runs on more branches, list them under
`on.push.branches`.

The kind test runs the test code of the pull request merged with its base, but its Flux reads the pull request's own
branch. Update a branch that's behind before you read a kind test failure as yours (see
[What the test finds in the repository](../reference/ci-checks.md#what-the-test-finds-in-the-repository)).

A pull request that changes nothing the tests read, such as documentation alone, gets a lighter run (see
[Which pull requests run the kind test](#which-pull-requests-run-the-kind-test)). Every push to `main` runs everything.

A pull request from a fork gets a read-only token and none of the repository's secrets. `yaml-diff.yaml` and
`validate.yaml` skip their comments there, which they can't post, leave a notice on the run saying why, and put the
diff and the validation log in the job summary. The kind test skips the tests that need the cluster there (see
[`GITOPS_MASTER_GPG_KEY`](#configuration)).

The kind test takes a while, so `validate.yaml` runs only once at a time per pull request. When you push a new commit
to a pull request, the run for the previous commit is cancelled. Pushes to a branch, such as a merge to `main`, don't
cancel the run in progress: it finishes, and GitHub keeps only the newest of the push runs waiting behind it.

## Which pull requests run the kind test

A comment in a manifest and a Renovate setting both used to cost the whole chain: about four minutes of `validate`
and twelve of the kind test, to prove nothing had changed. `validate.yaml` now asks first. Its `changes` job runs
[tests/ats/ci_scope.py](../../tests/ats/ci_scope.py), which compares the pull request's head with its merge base and
gives each changed file one of three answers:

- **No test reads it.** The file matches a pattern in `IGNORABLE` at the top of the module and none in
  `NOT_IGNORABLE`: Markdown, `docs/`, `renovate.json5`, `tests/chainsaw/`, the workflows other than `validate.yaml`
  and `validate-light.yaml`, `.gitignore`, `CODEOWNERS` and `LICENSE`. That includes the READMEs of the examples:
  `check-directory-readmes` still checks them in the light run. A `*.yaml` that names a Flux API counts, wherever it
  is, as `tools/test-all-ff` reads every such file outside `tests/`.
- **Same YAML.** A YAML file changed only in its comments, whitespace, quoting or the order of its keys. The order of
  documents and of list items counts, and so does a value spelled differently, such as `yes` for `true`.
- **Anything else counts:** a real change, however small, a file added, removed or renamed, YAML that doesn't parse.

If no file counts, `validate.yaml` calls [validate-light.yaml](../../.github/workflows/validate-light.yaml) in place
of the shared workflow. It runs the same `pre-commit` hooks, so Markdown is still linted and READMEs still checked,
and reports `validate / validate` and `validate / test_on_kind` as skipped. GitHub counts a skipped check as passed,
so a branch that requires these checks doesn't wait for them. The job summary of `changes` lists every file with its
answer, so you can see why a pull request got the run it did.

The decision fails open. If GitHub lists fewer files than the pull request changes, if the module hits an error, or if
the job can't get as far as asking, the full run happens. A change to the content of a manifest always runs the kind
test, however small: it's the only proof that the example still works.

To add your own files to the light run, such as a directory of notes, add a pattern to `IGNORABLE` in
`tests/ats/ci_scope.py`. The patterns are `fnmatch` patterns, where `*` matches `/` too, so `notes/*` covers
everything below `notes/`. Only add what neither test reads: the module can't tell if you're wrong, and a pull
request that matches skips the kind test.
