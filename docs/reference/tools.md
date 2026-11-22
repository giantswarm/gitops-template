# Tools and versions

The commands in these docs use the tools below. You don't need all of them: the table says which part of the docs
needs each one.

The snippets are written for `bash` and tested in it. They also work in `zsh`, the default shell on macOS: they keep
comments off the command lines, because an interactive `zsh` doesn't treat `#` as a comment unless
`setopt interactivecomments` is set. The few lines that are only a comment, such as `# edit values.tmp.yaml`, mark
where you do something by hand, and `zsh` answers them with `command not found: #`, which you can ignore. In any
other shell, start `bash` first.

## Tools

| Tool | Used for | Needed by |
| --- | --- | --- |
| `git` | your fork of the repository | everything |
| GNU core utilities, such as `base64`, `sed` and `tr` | the shell snippets, which use GNU options such as `sed -i`. On macOS, install the GNU versions (for example `brew install coreutils gnu-sed`) and put them first in your `PATH` | everything |
| [`yq`](https://github.com/mikefarah/yq/), the Go version by Mike Farah | changing YAML files from the command line. The Python `yq` takes other arguments | everything |
| `kubectl` | applying the first objects to the management cluster, and creating manifests with `--dry-run=client` | everything |
| [`kubectl gs`](https://github.com/giantswarm/kubectl-gs), X.Y.Z or newer | logging in, and the shortcuts that write files for you, see [kubectl-gs version](#kubectl-gs-version) | everything |
| [`flux`](https://github.com/fluxcd/flux2), the same minor version as the management cluster's Flux, 2.7 today | inspecting and reconciling Flux objects, and rendering what Flux applies | everything |
| `gpg` of [GnuPG](https://gnupg.org/) | creating and handling GPG keys | [SOPS](../how-to/sops.md) |
| [`sops`](https://github.com/getsops/sops), 3.10.0 or newer | encrypting and decrypting Secrets in the repository. The docs pipe a Secret into `sops --encrypt --filename-override PATH /dev/stdin`, so it never sits in the repository in plain text. 3.9.0 added `--filename-override`; 3.10.0 is the first that matches a relative path against `.sops.yaml` from any directory, as the steps that run in an app's directory need | [SOPS](../how-to/sops.md) |
| `age-keygen` of [age](https://github.com/FiloSottile/age) | creating an age key | [Add a workload cluster key (age)](../how-to/sops.md#add-a-workload-cluster-key-age) |
| `jq` and a password manager's CLI, such as 1Password's `op` | keeping a private key in a password manager | [Keep a private key in a password manager](../how-to/sops.md#keep-a-private-key-in-a-password-manager), optional |
| `flux-operator`, Flux Operator's CLI | forcing a `ResourceSetInputProvider` outside its window | [Hold upgrades for a window](../tutorials/advanced/scheduled-upgrades.md), optional: `kubectl annotate` does the same |
| [`pre-commit`](https://pre-commit.com/) | checking a change before you commit it | [Run pre-commit](../how-to/check-changes.md#run-pre-commit), optional |
| [`yamllint`](https://github.com/adrienverge/yamllint) | linting YAML | [Validate with test-all-ff](../how-to/check-changes.md#validate-with-test-all-ff) |
| [`kubeconform`](https://github.com/yannh/kubeconform); CI uses 0.8.0 | checking objects against their schemas | [Validate with test-all-ff](../how-to/check-changes.md#validate-with-test-all-ff) |
| `curl`, `sha256sum` and `tar` | fetching the Flux CRD schemas, see [tools](/tools/README.md#test-all-ff) for the sources and versions | [Validate with test-all-ff](../how-to/check-changes.md#validate-with-test-all-ff) |
| [`helm`](https://helm.sh/docs/intro/install/) | rendering the chart of every `HelmRelease` with its values | [Validate with test-all-ff](../how-to/check-changes.md#validate-with-test-all-ff) |
| [`kustomize`](https://kubectl.docs.kubernetes.io/installation/kustomize/binaries/) | building directories as Flux does; `kubectl kustomize` stands in for it in most places | [Render what Flux applies](../how-to/check-changes.md#render-what-flux-applies) |
| Docker, [kind](https://kind.sigs.k8s.io/), Python 3.12 with [pipenv](https://pipenv.pypa.io/), and [Chainsaw](https://kyverno.github.io/chainsaw/) | running the tests yourself, see [Testing the repository](../tutorials/advanced/testing.md) for the versions | [Testing the repository](../tutorials/advanced/testing.md), optional |

## kubectl-gs version

The `kubectl gs gitops` commands in these docs need kubectl-gs X.Y.Z or newer, the first release that writes the
layout of structure version 3, which this repository uses, and protects what it writes from deletion, see
[What kubectl-gs writes](../explanation/deletion-protection.md#what-kubectl-gs-writes). Check yours with
`kubectl gs --version`, and update it with `kubectl gs selfupdate`. Older releases write version 2, with a `mapi`
directory, and an older binary prints the help text for a command it doesn't know instead of an error, so the command
seems to do nothing. [Let kubectl-gs write the files](../how-to/kubectl-gs.md) says what each command writes.

| Command or flag | Added in | Note |
| --- | --- | --- |
| `kubectl gs --version` | 0.6.1 | |
| `kubectl gs login` | 0.5.3 | |
| `kubectl gs login --workload-cluster`, with `--organization` | 1.44.0 | |
| `kubectl gs get clusters`, with `-n` | 0.6.0 | |
| `kubectl gs template organization`, with `--name` | 1.39.0 | Writes the `Organization` without the deletion protection |
| `kubectl gs template cluster` printing a Flux `OCIRepository` and `HelmRelease`, with `--provider`, `--name`, `--organization` and `--release` | 5.13.0 | The flags are older. These docs use it with `--provider capa` and a release |
| `kubectl gs template cluster --prevent-deletion` | 2.57.0 | Defaults to `true` from 7.0.0, which also puts the label on the `OCIRepository` and `HelmRelease` |
| `kubectl gs gitops init` | 2.20.0 | |
| `kubectl gs gitops add management-cluster`, with `--name`, `--repository-name` and `--gen-master-key` | 2.20.0 | Before 6.0.0 it records the management cluster at structure version 1. From X.Y.Z it writes `prune: true`, the protected `secrets/kustomization.yaml` and the `.sops.yaml` rule for the workload clusters' keys |
| `kubectl gs gitops add management-cluster --skip-encryption` | 5.12.0 | |
| `kubectl gs gitops add organization`, with `--name` and `--management-cluster` | 2.20.0 | Before 6.0.0 it records the organisation at structure version 1. From X.Y.Z it writes the protected `Organization`, `namespace.yaml` and the organisation's `kustomization.yaml`, and `--repository-name` is optional; before, the `Organization` alone, without the protection |
| `kubectl gs gitops add workload-cluster`, with `--name`, `--organization`, `--management-cluster`, `--repository-name`, `--base` and `--cluster-user-config` | 2.20.0 | Before 6.0.0 it generates the cluster as an App CR, in repository structure version 1. From 6.0.0 it generates structure version 2, with the `mapi` directory. From X.Y.Z it generates structure version 3, the layout of this repository, and refuses an organisation whose clusters' `Kustomization`s haven't moved into its namespace, see [Workload cluster](../how-to/kubectl-gs.md#workload-cluster) |
| `kubectl gs gitops add workload-cluster --skip-mapi` | 2.20.0 | Removed in X.Y.Z, which never writes `mapi` |
| `kubectl gs gitops add workload-cluster --release` | 4.0.0 | Replaced `--cluster-release`. Sets the cluster app version and the `release` since 5.12.0 |
| `kubectl gs gitops add base`, with `--provider` | 2.30.0 | Before 6.0.0 it generates an App CR, in repository structure version 1. Writes into `bases/clusters/PROVIDER` from X.Y.Z, into `bases/clusters/PROVIDER/template` before |
| `kubectl gs gitops add base --prevent-deletion` | 7.0.0 | Defaults to `true`. From X.Y.Z it also writes the `kustomize.toolkit.fluxcd.io/prune: disabled` annotation |
| `kubectl gs gitops add app` | 2.20.0 | Deprecated since 5.2.0, without a replacement. Before X.Y.Z, it needs `--skip-mapi` on this repository's layout |
| `kubectl gs gitops add automatic-update`, with `--management-cluster`, `--organization`, `--workload-cluster` and `--app` | 2.20.0 | Before 6.0.0 it generates Flux image automation instead of a version range on the app's `OCIRepository`. Before X.Y.Z, it needs `--skip-mapi` on this repository's layout |
| `kubectl gs gitops add automatic-update --version-range` | 6.0.0 | |
| `kubectl gs gitops add encryption`, with `--generate`, `--management-cluster`, `--organization`, `--workload-cluster` and `--target` | 2.20.0 | From X.Y.Z it writes a workload cluster's key into the organisation's `namespace/secrets`, see [Encryption](../how-to/kubectl-gs.md#encryption); before, into `MC_NAME/secrets`, where structure version 3 can't use it |
| `--dry-run` on the `kubectl gs gitops` commands | 2.20.0 | |
| `kubectl gs gitops check`, with `--adopt` | 5.8.0 | Before 6.0.0 it only knows structure version 1, before X.Y.Z version 2 |
| `kubectl gs gitops upgrade` | 5.13.0 | Before 6.0.0 it only knows structure version 1, so there is nothing to upgrade to. The migration to structure version 3 needs X.Y.Z, see [Check and upgrade the structure version](../how-to/upgrade-fork.md#check-and-upgrade-the-structure-version) |
| `kubectl gs deploy chart`, with `--chart-name`, `--version`, `--organization`, `--target-cluster`, `--target-namespace`, `--values-from` and `--dry-run` | 5.1.0 | `--values-from` with a key and `optional`, as in `ConfigMap/NAME:values`, needs 5.12.0 |
| `kubectl gs selfupdate` | 1.47.0 | |
