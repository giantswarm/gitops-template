# Configure CI in a fork

Your fork comes with GitHub workflows that check every pull request before Flux ever sees it. Most of them work as
they are. This page covers the parts you set yourself: which upstream workflows you follow, the settings and the secret
of the kind test, and when the workflows run. For what each job checks, see [CI checks](../reference/ci-checks.md).

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

## Configuration

The kind test reads these settings, which `validate.yaml` sets through the inputs above and a repository secret:

- `GITOPS_FLUX_APP_VERSION`: the version of [flux-app](https://github.com/giantswarm/flux-app/releases)
  provided by Giant Swarm.
- `GITOPS_INIT_NAMESPACES`: a comma-separated list of the namespaces that exist before Flux applies the repository.
  The test creates the ones that don't exist, and an `automation` ServiceAccount in each, with the rights it has on a
  management cluster: see
  [The rights of the `automation` ServiceAccounts](../reference/ci-checks.md#the-rights-of-the-automation-serviceaccounts).
  [validate.yaml](../../.github/workflows/validate.yaml) sets it to `default` with the `gitops_init_namespaces` input
  of the shared workflow, whose default also names `org-org-name`. The test fails for an `org-*` namespace in the
  list: as on a new management cluster, the organisation's namespace exists only once Flux has applied its
  `Organization`, see
  [The organization-operator stand-in](../reference/ci-checks.md#the-organization-operator-stand-in).
- `GITOPS_IGNORED_OBJECTS`: a comma-separated list of (namespaced) `HelmRelease`s and sources that the test doesn't
  look at (example: "org-org-name/my-helmrelease"). It doesn't apply to `Kustomization`s, which all have to get
  `Ready`. [validate.yaml](../../.github/workflows/validate.yaml) sets it with the `gitops_ignored_objects` input of
  the shared workflow, empty in this repository. Keep it empty: an example the test can reconcile has to get `Ready`,
  so install what it needs in the test instead.
- `GITOPS_MASTER_GPG_KEY`: this variable needs to be a secret (unless you know what you're doing) and needs to contain
  a base64 encoded private master GPG key (armor-encoded, including `-----BEGIN...`
  and `-----END...` header and footer) for your `sops` configuration. Set it as a repository secret on GitHub: the
  job picks up this secret by default. An empty key fails the test, also in a fork's own runs, with one exception: on
  a pull request from a fork, which GitHub gives no secrets, the test skips every test that needs the cluster and
  says so in a warning on the run; the checks that need no cluster still run.

To set the secret from the master key in your keyring, for example with the GitHub CLI:

```sh
gpg --export-secret-keys --armor "${KEY_FP}" | base64 -w0 | gh secret set GITOPS_MASTER_GPG_KEY
```

Only the master key decrypts what the kind test applies: the workload clusters' keys are in the repository, encrypted
with it. Anyone who can change your workflows can read the secret, so treat write access to the repository as access
to the key.

## When the workflows run

`validate.yaml` runs on every pull request, whatever branch it targets, and on every push to `main`. The push run
checks `main` as it is after a merge, which no pull request run has tested when two pull requests merge one after the
other. If your fork's default branch has another name, or you want post-merge runs on more branches, list them under
`on.push.branches`.

A pull request that changes nothing the tests read, such as documentation alone, gets a lighter run, see
[Which pull requests run the kind test](#which-pull-requests-run-the-kind-test). Every push to `main` runs everything.

A pull request from a fork gets a read-only token and none of the repository's secrets. `yaml-diff.yaml` and
`validate.yaml` skip their comments there, which they can't post, leave a notice on the run saying why, and put the
diff and the validation log in the job summary. The kind test skips the tests that need
the cluster there; see [`GITOPS_MASTER_GPG_KEY`](#configuration).

The kind test takes a while, so `validate.yaml` runs once per pull request at a time. When you push a new commit to
a pull request, the run for the previous commit is cancelled. Pushes to a branch, such as a merge to `main`, don't
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
