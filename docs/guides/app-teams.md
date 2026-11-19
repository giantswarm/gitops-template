# Give an application team its own repository

This repository belongs to the platform team: it holds the clusters and the apps Giant Swarm ships. Application teams
usually want to deliver their own workloads from their own repository, without a pull request to the platform
repository for every change, and without being able to touch anything but their own workloads. This guide sets that
up for one team on one workload cluster.

## How it works

The team gets a namespace in the workload cluster, and Flux applies the team's repository into that namespace, and
nowhere else:

1. The platform team creates a ServiceAccount named after the team in the organization namespace on the management
   cluster. It has no rights there. In the workload cluster, the platform team creates the team's namespace, and a
   `RoleBinding` there that gives the ServiceAccount the `admin` role in that namespace.
1. On the management cluster, in the organization namespace, the platform team adds a `GitRepository` for the
   team's repository and a Flux `Kustomization` that applies it. The `Kustomization` reaches the workload cluster
   through its kubeconfig Secret, and has `serviceAccountName` set to the team's ServiceAccount. Flux then
   impersonates `system:serviceaccount:org-<organization>:<team>` in the workload cluster, which can write the team's
   namespace only. `targetNamespace` puts everything from the team's repository into that namespace.
1. The team pushes plain Kubernetes manifests, or a `kustomization.yaml`, to its repository. Flux applies them at
   the next `interval`, and deletes what the team deletes, as the `Kustomization` has `prune: true`.

The cluster's apps `Kustomization` applies the team's `GitRepository` and `Kustomization`, as the organization's
`automation` ServiceAccount, so they can only live in the organization's namespace, see
[Tenancy](../how-it-works.md#tenancy).

| The platform team owns, in this repository | The application team owns, in its repository |
| --- | --- |
| The workload cluster and its apps | Its workloads: `Deployment`s, `Service`s, `ConfigMap`s and the like |
| The team's ServiceAccount on the management cluster, in the organization's `teams` directory | |
| The team's namespace and `RoleBinding` in the workload cluster, in the cluster's `out-of-band` directory | The directory Flux applies, and its `kustomization.yaml` if it has one |
| The team's `GitRepository` and `Kustomization` on the management cluster, in the cluster's `teams` directory: which repository, which branch or tag, which directory | What goes into that directory, on that branch or tag |

What the team can't do: create objects outside its namespace, or cluster-wide objects such as a
`CustomResourceDefinition`, a `ClusterRole` or another `Namespace`. Kubernetes refuses them, and the team's
`Kustomization` reports the error. If the team needs one, the platform team adds it to the cluster's files.

## Example

The `out-of-band-no-flux` example cluster has the team `hello-team`, and the kind test in
[CI validation](./ci-validation.md) reconciles it into the test's workload cluster:

- [organizations/ORG_NAME/teams/hello-team.yaml](/management-clusters/MC_NAME/organizations/ORG_NAME/teams/hello-team.yaml):
  the team's ServiceAccount, which the management cluster's Kustomization applies.
- [out-of-band/teams/hello-team.yaml](/management-clusters/MC_NAME/organizations/ORG_NAME/workload-clusters/WC_NAME_OUT_OF_BAND_NO_FLUX_APP/out-of-band/teams/hello-team.yaml):
  the team's namespace and `RoleBinding`, which the cluster's `-direct` Kustomization applies to the workload
  cluster.
- [teams/hello-team](/management-clusters/MC_NAME/organizations/ORG_NAME/workload-clusters/WC_NAME_OUT_OF_BAND_NO_FLUX_APP/teams/hello-team/):
  the team's `GitRepository` and `Kustomization`.

The team's repository in the example is [podinfo](https://github.com/stefanprodan/podinfo), Flux's demo app, whose
`kustomize` directory holds a `Deployment`, a `Service` and a `HorizontalPodAutoscaler`. It stands in for a
repository your team owns.

## Add a team

The cluster needs a `-direct` Kustomization, which applies its `out-of-band` directory to the workload cluster, see
[Add a new Workload Cluster repository structure](../add_wc_structure.md#directory-tree).

1. Export the names:

    ```sh
    export MC_NAME=CODENAME
    export ORG_NAME=ORGANIZATION
    export WC_NAME=CLUSTER_NAME
    export TEAM_NAME=TEAM
    export TEAM_REPOSITORY=https://github.com/YOUR_ORGANIZATION/TEAM_REPOSITORY
    export WC_DIR=management-clusters/${MC_NAME}/organizations/${ORG_NAME}/workload-clusters/${WC_NAME}
    ```

1. Create the team's ServiceAccount in the organization namespace, once per organization, whichever clusters the
   team delivers to. Flux checks that it exists before it deletes what the team's `Kustomization` applied, so it
   belongs to the organization rather than to a cluster, and outlives the team's `Kustomization`s:

    ```sh
    mkdir -p management-clusters/${MC_NAME}/organizations/${ORG_NAME}/teams
    cat <<EOF > management-clusters/${MC_NAME}/organizations/${ORG_NAME}/teams/${TEAM_NAME}.yaml
    apiVersion: v1
    kind: ServiceAccount
    metadata:
      name: ${TEAM_NAME}
      namespace: org-${ORG_NAME}
    EOF
    ```

    The management cluster's `Kustomization` applies it, as the organization directory has no `kustomization.yaml`.

1. Create the team's namespace and `RoleBinding` in the workload cluster:

    ```sh
    mkdir -p ${WC_DIR}/out-of-band/teams
    cat <<EOF > ${WC_DIR}/out-of-band/teams/${TEAM_NAME}.yaml
    apiVersion: v1
    kind: Namespace
    metadata:
      name: ${TEAM_NAME}
    ---
    apiVersion: rbac.authorization.k8s.io/v1
    kind: RoleBinding
    metadata:
      name: ${TEAM_NAME}
      namespace: ${TEAM_NAME}
    roleRef:
      apiGroup: rbac.authorization.k8s.io
      kind: ClusterRole
      name: admin
    subjects:
      - kind: ServiceAccount
        name: ${TEAM_NAME}
        namespace: org-${ORG_NAME}
    EOF
    ```

    The ServiceAccount doesn't have to exist in the workload cluster: the `RoleBinding` names the user Flux
    impersonates.

1. Create the team's `GitRepository` and `Kustomization`. Set `ref` to the branch or tag the team delivers from, and
   `path` to the directory in its repository:

    ```sh
    mkdir -p ${WC_DIR}/teams/${TEAM_NAME}
    cat <<EOF > ${WC_DIR}/teams/${TEAM_NAME}/git-repository.yaml
    apiVersion: source.toolkit.fluxcd.io/v1
    kind: GitRepository
    metadata:
      name: \${cluster_name}-${TEAM_NAME}
      namespace: org-\${organization}
    spec:
      interval: 10m
      ref:
        branch: main
      url: ${TEAM_REPOSITORY}
    EOF
    cat <<EOF > ${WC_DIR}/teams/${TEAM_NAME}/flux-kustomization.yaml
    apiVersion: kustomize.toolkit.fluxcd.io/v1
    kind: Kustomization
    metadata:
      name: \${cluster_name}-${TEAM_NAME}
      namespace: org-\${organization}
    spec:
      dependsOn:
        - name: ${MC_NAME}-clusters-${WC_NAME}-direct
      interval: 10m
      kubeConfig:
        secretRef:
          name: \${cluster_name}-kubeconfig
      path: ./deploy
      prune: true
      retryInterval: 1m
      serviceAccountName: ${TEAM_NAME}
      sourceRef:
        kind: GitRepository
        name: \${cluster_name}-${TEAM_NAME}
      targetNamespace: ${TEAM_NAME}
      timeout: 2m
    EOF
    cat <<EOF > ${WC_DIR}/teams/${TEAM_NAME}/kustomization.yaml
    apiVersion: kustomize.config.k8s.io/v1beta1
    kind: Kustomization
    resources:
      - git-repository.yaml
      - flux-kustomization.yaml
    EOF
    ```

    `dependsOn` names the cluster's `-direct` Kustomization, so Flux applies the team's repository once the namespace
    and `RoleBinding` exist. The cluster's apps `Kustomization` fills in `${cluster_name}` and `${organization}`.

    For a private repository, add a Secret with read access to it in `org-${ORG_NAME}` and name it in the
    `GitRepository`'s `spec.secretRef`, the same way as the platform repository's in
    [Getting started](../getting-started.md).

1. List the team in the cluster's `teams` directory, and the directory in the cluster's `kustomization.yaml`:

    ```sh
    [ -f ${WC_DIR}/teams/kustomization.yaml ] || printf 'apiVersion: kustomize.config.k8s.io/v1beta1\nkind: Kustomization\nresources: []\n' > ${WC_DIR}/teams/kustomization.yaml
    yq -i '.resources += ["'"${TEAM_NAME}"'/"]' ${WC_DIR}/teams/kustomization.yaml
    yq -i '.resources += ["teams/"] | .resources |= unique' ${WC_DIR}/kustomization.yaml
    ```

1. Commit and push.

**Check:** the team's `Kustomization` is `Ready`:

```sh
flux get kustomizations -n org-${ORG_NAME} ${WC_NAME}-${TEAM_NAME}
```

In the workload cluster, the team's workloads run in its namespace:

```sh
kubectl get all -n ${TEAM_NAME}
```

To remove the team from the cluster, delete its directory in the cluster's `teams`, its entry in
`teams/kustomization.yaml` and its file in `out-of-band/teams`, and push. Flux deletes the team's `Kustomization`,
which deletes the team's workloads from the workload cluster, then the namespace. Delete the team's ServiceAccount
only once no cluster of the organization has the team any more.
