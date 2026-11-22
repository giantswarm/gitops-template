# Tools and versions

The commands in these docs use the tools below. You don't need all of them: the table says which part of the docs
needs each one.

## Tools

| Tool | Used for | Needed by |
| --- | --- | --- |
| `git` | your fork of the repository | everything |
| GNU core utilities, such as `base64`, `sed` and `tr` | the shell snippets, which use GNU options such as `sed -i`. On macOS, install the GNU versions (for example `brew install coreutils gnu-sed`) and put them first in your `PATH` | everything |
| [`yq`](https://github.com/mikefarah/yq/), the Go version by Mike Farah | changing YAML files from the command line. The Python `yq` takes other arguments | everything |
| `kubectl` | applying the first objects to the management cluster, and creating manifests with `--dry-run=client` | everything |
| [`kubectl gs`](https://github.com/giantswarm/kubectl-gs), 6.0.0 or newer | logging in, and the shortcuts that write files for you, see [kubectl-gs version](#kubectl-gs-version) | everything |
| [`flux`](https://github.com/fluxcd/flux2) | inspecting and reconciling Flux objects, and rendering what Flux applies | everything |
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

## kubectl-gs version

The `kubectl gs` commands in these docs need kubectl-gs 6.0.0 or newer. 7.0.0 and newer protect a cluster from
deletion by default, see [What kubectl-gs writes](../explanation/deletion-protection.md#what-kubectl-gs-writes). Check
yours with `kubectl gs --version`, and update it with `kubectl gs selfupdate`. Older versions lack some of the commands
and flags, and an older binary prints the help text for a command it doesn't know instead of an error, so the command
seems to do nothing.

No release writes the layout of structure version 3, which this repository uses: every `gitops` command writes
version 2. [Let kubectl-gs write the files](../how-to/kubectl-gs.md) says what to change in what they write.

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
| `kubectl gs gitops add management-cluster`, with `--name`, `--repository-name` and `--gen-master-key` | 2.20.0 | Before 6.0.0 it records the management cluster at structure version 1 |
| `kubectl gs gitops add management-cluster --skip-encryption` | 5.12.0 | |
| `kubectl gs gitops add organization`, with `--name` and `--management-cluster` | 2.20.0 | Before 6.0.0 it records the organisation at structure version 1. Writes the `Organization` without the deletion protection |
| `kubectl gs gitops add workload-cluster`, with `--name`, `--organization`, `--management-cluster`, `--repository-name`, `--base` and `--cluster-user-config` | 2.20.0 | Before 6.0.0 it generates the cluster as an App CR, in repository structure version 1. From 6.0.0 it generates structure version 2, with the `mapi` directory. This repository uses structure version 3, without `mapi`, see [Workload cluster](../how-to/kubectl-gs.md#workload-cluster) |
| `kubectl gs gitops add workload-cluster --skip-mapi` | 2.20.0 | |
| `kubectl gs gitops add workload-cluster --release` | 4.0.0 | Replaced `--cluster-release`. Sets the cluster app version and the `release` since 5.12.0 |
| `kubectl gs gitops add base`, with `--provider` | 2.30.0 | Before 6.0.0 it generates an App CR, in repository structure version 1. Writes into `bases/clusters/PROVIDER/template` |
| `kubectl gs gitops add base --prevent-deletion` | 7.0.0 | Defaults to `true` |
| `kubectl gs gitops add app` | 2.20.0 | Deprecated since 5.2.0, without a replacement. Use `--skip-mapi` on this repository's layout |
| `kubectl gs gitops add automatic-update`, with `--management-cluster`, `--organization`, `--workload-cluster`, `--app` and `--skip-mapi` | 2.20.0 | Before 6.0.0 it generates Flux image automation instead of a version range on the app's `OCIRepository`. Use `--skip-mapi` on this repository's layout |
| `kubectl gs gitops add automatic-update --version-range` | 6.0.0 | |
| `kubectl gs gitops add encryption`, with `--generate`, `--management-cluster`, `--organization`, `--workload-cluster` and `--target` | 2.20.0 | Writes a workload cluster's key where structure version 3 can't use it, see [Keep secrets in the repository](../how-to/sops.md) |
| `--dry-run` on the `kubectl gs gitops` commands | 2.20.0 | |
| `kubectl gs gitops check`, with `--adopt` | 5.8.0 | Before 6.0.0 it only knows structure version 1. No release knows structure version 3 yet |
| `kubectl gs gitops upgrade` | 5.13.0 | Before 6.0.0 it only knows structure version 1, so there is nothing to upgrade to. No release has the migration to structure version 3 yet |
| `kubectl gs deploy chart`, with `--chart-name`, `--version`, `--organization`, `--target-cluster`, `--target-namespace`, `--values-from` and `--dry-run` | 5.1.0 | `--values-from` with a key and `optional`, as in `ConfigMap/NAME:values`, needs 5.12.0 |
| `kubectl gs selfupdate` | 1.47.0 | |
