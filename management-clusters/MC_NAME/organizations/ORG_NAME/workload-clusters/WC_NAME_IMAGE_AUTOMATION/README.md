# WC_NAME_IMAGE_AUTOMATION

`management-clusters/MC_NAME/organizations/ORG_NAME/workload-clusters/WC_NAME_IMAGE_AUTOMATION`

A workload that isn't a chart: a plain `Deployment`, applied to the workload cluster with kustomize alone, no Helm and no
`helm-controller`, whose image Flux image automation keeps current. The management cluster watches the image's
registry, writes each newer tag its policy allows into the `Deployment`'s file, and pushes the commit to the branch
`flux/image-updates`. The workflow
[`image-updates-pull-request.yaml`](/.github/workflows/image-updates-pull-request.yaml) opens a pull request from it, and
Flux applies the new tag once you merge it. Compare the apps that follow a version range, such as
[`hello-world-automatic-updates`](../WC_NAME_OUT_OF_BAND_NO_FLUX_APP/apps/hello-world-automatic-updates/), where Flux
installs a new chart version without a commit.

Two Flux `Kustomization`s, next to this directory in `workload-clusters/`, apply it:

- `WC_NAME_IMAGE_AUTOMATION.yaml` applies this directory into `org-<name>`, whose `kustomization.yaml` lists `cluster/`
  and `image-automation/`. It has no apps `Kustomization` and no health check on the cluster: the image automation runs
  on the management cluster and doesn't need the workload cluster up. A health check would hold one of
  kustomize-controller's four workers on the management cluster until the cluster is up.
- `WC_NAME_IMAGE_AUTOMATION-direct.yaml` applies `out-of-band/` into the workload cluster itself, through the cluster's
  kubeconfig.

Neither decrypts anything: the one secret, the deploy key, comes from External Secrets Operator.

## What's here

- `kustomization.yaml`: lists `cluster/` and `image-automation/`, and leaves out `out-of-band/`, which belongs to the
  workload cluster.
- `cluster/`: the cluster, from the CAPA base and the `eu_central` region, with its own values in
  `cluster_userconfig.yaml` and `patch_cluster_userconfig.yaml`.
- [`image-automation/`](image-automation/): the image automation and its deploy key, on the management cluster.
- `out-of-band/`: what the `-direct` `Kustomization` applies to the workload cluster. It has no `kustomization.yaml`, so
  Flux takes every YAML file below it.
- `out-of-band/helloworld/`: the `Deployment`, with the setter comment that tells the image automation which line to
  change.

## When you copy it

Copy the directory and its two `Kustomization`s, rename them after your cluster, and set `cluster_name` in both,
`release` in `WC_NAME_IMAGE_AUTOMATION.yaml`, and the `-direct` `Kustomization`'s kubeconfig Secret. Then:

- in `image-automation/`, set your fork's SSH URL and the branch your management cluster reads in
  `git-repository.yaml`, your image in `image-repository.yaml`, your range in `image-policy.yaml`, and
  `update.path` in `image-update-automation.yaml` to your cluster's `out-of-band/`;
- in `out-of-band/helloworld/deployment.yaml`, change the setter comment to name your organisation's namespace and your
  policy, `<namespace>:<cluster>-helloworld`;
- create a deploy key with write access on your fork, keep its private half in your secret manager, and point the
  `ExternalSecret` at your store, as [Image automation](/docs/how-to/image-automation.md) shows;
- turn on GitHub's "Allow GitHub Actions to create and approve pull requests", so the workflow can open its pull
  request.

On a management cluster, image-automation-controller needs egress to `github.com` on port 22 to push over SSH. That's
Giant Swarm's to allow, not something the repository configures.

List the cluster's `Kustomization`s in `workload-clusters/kustomization.yaml` and in the organisation's commit status
`Alert`, as [`workload-clusters/README.md`](../README.md#when-you-copy-it) says.

## Read more

- [Image automation](/docs/how-to/image-automation.md)
- [Add the -direct `Kustomization`](/docs/tutorials/advanced/out-of-band.md#add-the--direct-kustomization)
- [Image automation in the kind test](/docs/reference/ci-checks.md#image-automation)
