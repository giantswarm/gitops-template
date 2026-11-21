# Teams

This repository belongs to the platform team: it holds the clusters, and the apps that every cluster needs. Application
teams usually want to deliver their own workloads from their own repository, without a pull request to the platform
repository for every change, and without being able to touch anything but their own workloads. Think of it as giving a
team its own allotment: the platform team marks out the plot and the gate, and what grows inside is the team's
business.

This tutorial sets that up for one team on the cluster from the [basic tutorial](../basic/getting-started.md). It
builds on [Out-of-band resources](./out-of-band.md): the team's namespace is an out-of-band object, applied straight to
the workload cluster.

- [Two modes](#two-modes)
- [Add a team with Flux on the management cluster](#add-a-team-with-flux-on-the-management-cluster)
- [Add a team with Flux in the workload cluster](#add-a-team-with-flux-in-the-workload-cluster)
- [Remove a team](#remove-a-team)
- [Next steps](#next-steps)

Run the commands from the root of your clone, with the variables the basic tutorial exported still set: those from
[Before you start](../basic/getting-started.md#before-you-start), and the ones its steps add, such as `WC_CONTEXT`.

## Two modes

The team gets a namespace in the workload cluster, and Flux applies the team's repository into that namespace, and
nowhere else. Which Flux does it depends on where Flux runs:

1. **Flux on the management cluster.** The team's `GitRepository` and `Kustomization` live on the management cluster,
   in the organisation's namespace, and the `Kustomization` reaches the workload cluster through its kubeconfig. In the
   workload cluster, the platform team gives the organisation's `automation` ServiceAccount the `admin` role in the
   team's namespace, with a `RoleBinding`. The `Kustomization` has `serviceAccountName: automation`, so Flux
   impersonates `system:serviceaccount:org-<name>:automation` in the workload cluster, which can write only the
   namespaces that have such a `RoleBinding`. The workload cluster runs no Flux.
1. **Flux in the workload cluster.** The workload cluster runs Flux, as in
   [Run Flux in the workload cluster](./out-of-band.md#run-flux-in-the-workload-cluster). The platform team puts the
   team's namespace, a ServiceAccount named after the team, a `RoleBinding` that makes it `admin` there, and the team's
   `GitRepository` and `Kustomization` into the cluster's `out-of-band` directory. The cluster's `-direct`
   `Kustomization` delivers them, and Flux in the workload cluster reconciles them, as the team's ServiceAccount.

Pick Flux on the management cluster when the workload cluster doesn't run Flux: there's nothing to install or upgrade
in it, and the platform team sees every team's `Kustomization` on the management cluster. Pick Flux in the workload
cluster when it runs Flux anyway, when the team should see its `Kustomization` and its errors in the cluster it deploys
to, when delivery should go on while the management cluster is unavailable, or when the teams on a cluster must be kept
apart from each other. With Flux on the management cluster, every team on the same workload cluster has the same
identity there, the organisation's `automation` ServiceAccount, which is `admin` in every team's namespace, so one
team's repository can write into another team's namespace. With Flux in the workload cluster, each team has a
ServiceAccount of its own.

Who owns what:

| The platform team owns, in this repository | The application team owns, in its repository |
| --- | --- |
| The workload cluster and its apps | Its workloads: `Deployment`s, `Service`s, `ConfigMap`s and the like |
| The team's namespace and `RoleBinding` in the workload cluster, in the cluster's `out-of-band` directory | The directory Flux applies, and its `kustomization.yaml` if it has one |
| The team's `GitRepository` and `Kustomization`: on the management cluster, in the cluster's `teams` directory, or in the workload cluster, in the cluster's `out-of-band` directory. Which repository, which branch or tag, which directory | What goes into that directory, on that branch or tag |

What the team can't do: create objects outside its namespace, or cluster-wide objects such as a
`CustomResourceDefinition`, a `ClusterRole` or another `Namespace`. Kubernetes refuses them, and the team's
`Kustomization` reports the error. If the team needs one, the platform team adds it to the cluster's files.

Nor can it create Flux objects in a workload cluster that runs Giant Swarm's flux-app: its `flux-edit` role doesn't add
Flux's kinds to the `admin` role. Upstream Flux's does, so in a workload cluster that runs upstream Flux the team could
create a `Kustomization` or a `HelmRelease` of its own. Without `serviceAccountName`, Flux would apply it as
kustomize-controller or helm-controller, with the rights of a cluster admin. There, start both kustomize-controller and
helm-controller with `--default-service-account`, so that Flux applies such an object as that ServiceAccount of the
object's namespace instead.

The fork has a team in each mode on the `out-of-band-no-flux` example cluster, and the kind test reconciles them:
`hello-team`, with Flux on the management cluster, in
[out-of-band/teams/hello-team.yaml](/management-clusters/MC_NAME/organizations/ORG_NAME/workload-clusters/WC_NAME_OUT_OF_BAND_NO_FLUX_APP/out-of-band/teams/hello-team.yaml)
and [teams/hello-team](/management-clusters/MC_NAME/organizations/ORG_NAME/workload-clusters/WC_NAME_OUT_OF_BAND_NO_FLUX_APP/teams/hello-team/),
and `hello-team-wc`, with Flux in the workload cluster, in
[out-of-band/teams/hello-team-wc.yaml](/management-clusters/MC_NAME/organizations/ORG_NAME/workload-clusters/WC_NAME_OUT_OF_BAND_NO_FLUX_APP/out-of-band/teams/hello-team-wc.yaml).
The test's workload cluster runs no Flux, so for `hello-team-wc` it checks that the objects get there, not that they
reconcile. Both use [podinfo](https://github.com/stefanprodan/podinfo), Flux's demo app, as the team's repository: its
`kustomize` directory holds a `Deployment`, a `Service` and a `HorizontalPodAutoscaler`.

Export the team's name, its repository, the branch Flux delivers from and the directory in it. With podinfo, as below,
you can try either mode before a real team turns up:

```sh
export TEAM_NAME=hello-team
export TEAM_REPOSITORY=https://github.com/stefanprodan/podinfo
export TEAM_BRANCH=master
export TEAM_PATH=./kustomize
```

## Add a team with Flux on the management cluster

The cluster needs its `-direct` `Kustomization`, which applies its `out-of-band` directory to the workload cluster, see
[Add the -direct Kustomization](./out-of-band.md#add-the--direct-kustomization).

1. Create the team's namespace in the workload cluster, and the `RoleBinding` that gives the organisation's
   `automation` ServiceAccount the `admin` role there:

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
        name: automation
        namespace: org-\${organization}
    EOF
    ```

    `automation` doesn't have to exist in the workload cluster: the `RoleBinding` names the user Flux impersonates. If
    the cluster's `out-of-band` directory has a `kustomization.yaml`, list the file there:

    ```sh
    [ -f ${WC_DIR}/out-of-band/kustomization.yaml ] && yq -i '.resources += ["teams/'"${TEAM_NAME}"'.yaml"] | .resources |= unique' ${WC_DIR}/out-of-band/kustomization.yaml
    ```

1. Create the team's `GitRepository` and `Kustomization`, in the cluster's `teams` directory. The cluster's apps
   `Kustomization` applies them into the organisation's namespace, where the cluster's kubeconfig Secret is, and fills
   in `${cluster_name}` and `${organization}`:

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
        branch: ${TEAM_BRANCH}
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
      path: ${TEAM_PATH}
      prune: true
      retryInterval: 1m
      serviceAccountName: automation
      sourceRef:
        kind: GitRepository
        name: \${cluster_name}-${TEAM_NAME}
      targetNamespace: ${TEAM_NAME}
      timeout: 2m
    EOF
    cat <<'EOF' > ${WC_DIR}/teams/${TEAM_NAME}/kustomization.yaml
    apiVersion: kustomize.config.k8s.io/v1beta1
    kind: Kustomization
    resources:
      - git-repository.yaml
      - flux-kustomization.yaml
    EOF
    ```

    `dependsOn` names the cluster's `-direct` `Kustomization`, in the same namespace, so Flux applies the team's
    repository once the namespace and the `RoleBinding` exist. `targetNamespace` puts everything from the team's
    repository into the team's namespace.

    For a private repository, add a Secret with read access to it in `org-${ORG_NAME}`, and name it in the
    `GitRepository`'s `spec.secretRef`. Encrypt it with SOPS or write it with an `ExternalSecret`, as you do the
    platform repository's.

1. List the team in the cluster's `teams` directory, and the directory in the cluster's `kustomization.yaml`:

    ```sh
    [ -f ${WC_DIR}/teams/kustomization.yaml ] || printf 'apiVersion: kustomize.config.k8s.io/v1beta1\nkind: Kustomization\nresources: []\n' > ${WC_DIR}/teams/kustomization.yaml
    yq -i '.resources += ["'"${TEAM_NAME}"'/"] | .resources |= unique' ${WC_DIR}/teams/kustomization.yaml
    yq -i '.resources += ["teams/"] | .resources |= unique' ${WC_DIR}/kustomization.yaml
    ```

1. Commit and push:

    ```sh
    git add ${WC_DIR} && git commit -m "Add team ${TEAM_NAME} to ${WC_NAME}" && git push
    ```

**Check:** the team's `Kustomization` is `Ready`, and the team's workloads run in its namespace in the workload
cluster:

```sh
flux get kustomizations ${WC_NAME}-${TEAM_NAME} -n org-${ORG_NAME}
kubectl --context ${WC_CONTEXT} get all -n ${TEAM_NAME}
```

From now on, the team pushes plain manifests, or a `kustomization.yaml`, to its repository, and Flux applies them at
the next `interval`. It deletes what the team deletes, as the `Kustomization` has `prune: true`.

## Add a team with Flux in the workload cluster

The cluster needs its `-direct` `Kustomization`, which pushes the team's objects, and Flux, which reconciles them.
Install flux-app with the first two steps of
[Run Flux in the workload cluster](./out-of-band.md#run-flux-in-the-workload-cluster), with
`FLUX_WC_DIR=${WC_DIR}`, and leave out the third: the `-direct` `Kustomization` already applies `out-of-band` to this
cluster, and Flux in the workload cluster mustn't apply it as well. Flux brings its CRDs with it, which the `-direct`
`Kustomization` needs before it can apply a `GitRepository` or a `Kustomization`.

1. If you added a team with Flux on the management cluster above, give this one another name, so that the two don't
   share a namespace:

    ```sh
    export TEAM_NAME=hello-team-wc
    ```

1. Create the team's namespace, ServiceAccount, `RoleBinding`, `GitRepository` and `Kustomization`, in one file:

    ```sh
    mkdir -p ${WC_DIR}/out-of-band/teams
    cat <<EOF > ${WC_DIR}/out-of-band/teams/${TEAM_NAME}.yaml
    apiVersion: v1
    kind: Namespace
    metadata:
      name: ${TEAM_NAME}
    ---
    apiVersion: v1
    kind: ServiceAccount
    metadata:
      name: ${TEAM_NAME}
      namespace: ${TEAM_NAME}
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
        namespace: ${TEAM_NAME}
    ---
    apiVersion: source.toolkit.fluxcd.io/v1
    kind: GitRepository
    metadata:
      name: ${TEAM_NAME}
      namespace: ${TEAM_NAME}
    spec:
      interval: 10m
      ref:
        branch: ${TEAM_BRANCH}
      url: ${TEAM_REPOSITORY}
    ---
    apiVersion: kustomize.toolkit.fluxcd.io/v1
    kind: Kustomization
    metadata:
      name: ${TEAM_NAME}
      namespace: ${TEAM_NAME}
    spec:
      interval: 10m
      path: ${TEAM_PATH}
      prune: true
      retryInterval: 1m
      serviceAccountName: ${TEAM_NAME}
      sourceRef:
        kind: GitRepository
        name: ${TEAM_NAME}
      targetNamespace: ${TEAM_NAME}
      timeout: 2m
    EOF
    ```

    Flux in the workload cluster impersonates the team's ServiceAccount, which can write the team's namespace only. If
    the cluster's `out-of-band` directory has a `kustomization.yaml`, list the file there:

    ```sh
    [ -f ${WC_DIR}/out-of-band/kustomization.yaml ] && yq -i '.resources += ["teams/'"${TEAM_NAME}"'.yaml"] | .resources |= unique' ${WC_DIR}/out-of-band/kustomization.yaml
    ```

    A private repository needs a Secret with read access to it in the team's namespace, named in the
    `GitRepository`'s `spec.secretRef`. Deliver it the same way, in `out-of-band`, encrypted with SOPS, and give the
    `-direct` `Kustomization` the `decryption` that the cluster's other `Kustomization`s have, see
    [Decrypt a cluster's files](../../how-to/sops.md#decrypt-a-clusters-files).

1. Commit and push:

    ```sh
    git add ${WC_DIR} && git commit -m "Add team ${TEAM_NAME} to ${WC_NAME}" && git push
    ```

**Check:** in the workload cluster, the team's `Kustomization` is `Ready`, and its workloads run in its namespace:

```sh
flux --context ${WC_CONTEXT} get kustomizations ${TEAM_NAME} -n ${TEAM_NAME}
kubectl --context ${WC_CONTEXT} get all -n ${TEAM_NAME}
```

## Remove a team

How you remove a team depends on its mode, and the order matters with Flux on the management cluster. Set
`TEAM_NAME` to the team you're removing first: `hello-team` for the one with Flux on the management cluster above,
`hello-team-wc` for the one with Flux in the workload cluster.

**Flux on the management cluster** takes two pushes, in this order:

1. Set the team's name:

    ```sh
    export TEAM_NAME=hello-team
    ```

1. Delete the team's directory in the cluster's `teams`, and its entry in `teams/kustomization.yaml`, and push. Flux
   deletes the team's `Kustomization`, which deletes the team's workloads from the workload cluster. Wait until the
   `Kustomization` is gone:

    ```sh
    kubectl wait --for=delete kustomization/${WC_NAME}-${TEAM_NAME} -n org-${ORG_NAME} --timeout=10m
    ```

1. Delete the team's file in `out-of-band/teams`, and its entry in `out-of-band/kustomization.yaml` if there is one,
   and push. The `-direct` `Kustomization` deletes the team's namespace and `RoleBinding`.

Don't do both in one push. To delete the team's workloads, Flux impersonates the organisation's `automation`
ServiceAccount in the workload cluster. Without the `RoleBinding` in the team's namespace, the workload cluster refuses
it, and the team's `Kustomization` stays `Terminating` until the `RoleBinding` is back.

Remove a cluster's teams this way before you [delete the cluster](../../how-to/delete-cluster.md). Deleting the
cluster's files deletes the team's `Kustomization` and `RoleBinding` in the same push. Once the cluster is gone, so is
its kubeconfig Secret, Flux can't reach the cluster any more, and the team's `Kustomization` stays `Terminating` for
good.

**Flux in the workload cluster** takes one push: delete the team's file in `out-of-band/teams`, and its entry in
`out-of-band/kustomization.yaml` if there is one, and push. The `-direct` `Kustomization` deletes the team's objects
from the workload cluster, and the team's workloads go with its namespace. The team's ServiceAccount is in the workload
cluster and goes in the same push, and once it's gone, Flux there lets the team's `Kustomization` go without deleting
its workloads itself, which the namespace's deletion does.

## Next steps

- [Testing](./testing.md): how the kind test reconciles the example teams.
- [Out-of-band resources](./out-of-band.md): the `-direct` `Kustomization` the teams rely on.
