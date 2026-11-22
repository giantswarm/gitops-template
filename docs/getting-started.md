# Getting started

This page moved to [Getting started](./tutorials/basic/getting-started.md), which keeps the bootstrap secrets with
SOPS and the app's secret values with External Secrets Operator, and says how to use either one on its own. The
sections below keep old links working.

## Before you start

See [Before you start](./tutorials/basic/getting-started.md#before-you-start).

## 1. Connect the management cluster

See [1. Connect the management cluster](./tutorials/basic/getting-started.md#1-connect-the-management-cluster). To
read the repository token from your secret manager with an `ExternalSecret`, see
[Keep the repository token in your secret manager](./how-to/external-secrets.md#keep-the-repository-token-in-your-secret-manager).
For `kubectl gs gitops add management-cluster`, see [Management cluster](./how-to/kubectl-gs.md#management-cluster).

## 2. Add an organization

See [2. Add an organisation](./tutorials/basic/getting-started.md#2-add-an-organisation). For
`kubectl gs gitops add organization`, see [Organisation](./how-to/kubectl-gs.md#organisation).

## 3. Create a workload cluster

See [3. Create a workload cluster](./tutorials/basic/getting-started.md#3-create-a-workload-cluster). For
`kubectl gs gitops add workload-cluster` and what to change after it, see
[Workload cluster](./how-to/kubectl-gs.md#workload-cluster).

## 4. Deploy an app

See [4. Deploy an app](./tutorials/basic/getting-started.md#4-deploy-an-app). For `kubectl gs deploy chart`, see
[App](./how-to/kubectl-gs.md#app).

## 5. Update the app

See [5. Update the app](./tutorials/basic/getting-started.md#5-update-the-app).

## 6. Delete the cluster (optional)

See [6. Delete the cluster (optional)](./tutorials/basic/getting-started.md#6-delete-the-cluster-optional) for the
cluster the tutorial creates, and [Delete a workload cluster](./how-to/delete-cluster.md) for any cluster, with its
keys, out-of-band resources and application teams. What kubectl-gs protects is in
[What kubectl-gs writes](./explanation/deletion-protection.md#what-kubectl-gs-writes).

## Next steps

See [Next steps](./tutorials/basic/getting-started.md#next-steps).
