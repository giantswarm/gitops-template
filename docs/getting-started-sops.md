# Getting started with SOPS

This guide moved to [Getting started](./tutorials/basic/getting-started.md), which keeps the bootstrap secrets with
SOPS and the app's secret values with External Secrets Operator, and says how to use SOPS on its own. The sections
below keep old links working.

## Before you start

See [Before you start](./tutorials/basic/getting-started.md#before-you-start).

## 1. Connect the management cluster

See [1. Connect the management cluster](./tutorials/basic/getting-started.md#1-connect-the-management-cluster). For
`kubectl gs gitops add management-cluster --gen-master-key`, see
[Management cluster](./how-to/kubectl-gs.md#management-cluster).

## 2. Add an organization

See [2. Add an organisation](./tutorials/basic/getting-started.md#2-add-an-organisation).

## 3. Create a workload cluster

See [3. Create a workload cluster](./tutorials/basic/getting-started.md#3-create-a-workload-cluster).

## 4. Deploy an app

See [4. Deploy an app](./tutorials/basic/getting-started.md#4-deploy-an-app). To keep the app's secret values in the
repository instead, see [Encrypt an app's values](./how-to/sops.md#encrypt-an-apps-values).

## 5. Update the app

See [5. Update the app](./tutorials/basic/getting-started.md#5-update-the-app).

## 6. Delete the cluster (optional)

See [6. Delete the cluster (optional)](./tutorials/basic/getting-started.md#6-delete-the-cluster-optional), and
[Delete a workload cluster](./how-to/delete-cluster.md) for a cluster with its own SOPS key.

## Next steps

See [Next steps](./tutorials/basic/getting-started.md#next-steps). To give a cluster its own key, see
[Add a workload cluster key (GPG)](./how-to/sops.md#add-a-workload-cluster-key-gpg) or
[Add a workload cluster key (age)](./how-to/sops.md#add-a-workload-cluster-key-age). Which key decrypts which files
is in [SOPS keys](./reference/sops-keys.md).
