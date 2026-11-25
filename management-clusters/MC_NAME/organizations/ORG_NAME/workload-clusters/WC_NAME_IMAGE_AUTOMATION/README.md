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

Three Flux `Kustomization`s, next to this directory in `workload-clusters/`, apply it:

- `WC_NAME_IMAGE_AUTOMATION.yaml` applies `cluster/` into `org-<name>`, and is `Ready` once Cluster API reports the
  cluster's control plane available and reachable.
- `WC_NAME_IMAGE_AUTOMATION-apps.yaml` then applies this directory into `org-<name>`, whose `kustomization.yaml` lists
  `apps/`.
- `WC_NAME_IMAGE_AUTOMATION-direct.yaml` applies `out-of-band/` into the workload cluster itself, through the cluster's
  kubeconfig.

None of them decrypts anything: the one secret, the deploy key, comes from External Secrets Operator.

## What's here

- `kustomization.yaml`: lists `apps/`, so neither `cluster/` nor `out-of-band/` is applied twice or to the wrong cluster.
- `cluster/`: the cluster, from the CAPA base and the `eu_central` region, with its own values in
  `cluster_userconfig.yaml` and `patch_cluster_userconfig.yaml`.
- `apps/`: what runs on the management cluster for the cluster. Its `kustomization.yaml` lists it and labels it with the
  cluster.
- [`apps/image-automation/`](apps/image-automation/): the image automation and its deploy key.
- `out-of-band/`: what the `-direct` `Kustomization` applies to the workload cluster. It has no `kustomization.yaml`, so
  Flux takes every YAML file below it.
- `out-of-band/helloworld/`: the `Deployment`, with the setter comment that tells the image automation which line to
  change.

## When you copy it

Copy the directory and its three `Kustomization`s, rename them after your cluster, and set `cluster_name` in all three,
`release` and the health check's cluster name in `WC_NAME_IMAGE_AUTOMATION.yaml`, and the `-direct` `Kustomization`'s
kubeconfig Secret. Then:

- in `apps/image-automation/`, set your fork's SSH URL and the branch your management cluster reads in
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
