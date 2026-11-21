# Stages and regions

One cluster is a pet project. Most teams soon want a dev cluster to try things on, a staging cluster that looks like
production, and production itself, perhaps in more than one region. They should look alike in most ways and differ in
a few on purpose: dev runs the newest versions, prod the proven ones, and each region has its own location and node
pools.

This tutorial builds that: four clusters, `hello-app-dev-1` and `hello-app-staging-1` in `eu-central`, and two prod
clusters, one in `eu-central` and one in `us-west`, all from the [CAPA cluster base](/bases/clusters/capa), all running
the [hello-web](./stacks.md) stack. What differs between them lives in small pieces under `bases/environments`:

- a **region** says where a cluster runs, and can add a node pool in the region's zones;
- a **stage** says which versions its clusters run: the Giant Swarm release and the app versions.

Both are [kustomize Components](https://kubectl.docs.kubernetes.io/guides/config_management/components/): unlike a
base, a Component can patch objects that it doesn't create, here the cluster's `HelmRelease` and the `OCIRepository`s of
the cluster and its apps. A cluster lists its region and its stage under `components:`, and that's all it takes to
put it in a place and a stage. Why environments are directories rather than branches or repositories is in
[Directories, branches or repositories](../../explanation/composition.md#directories-branches-or-repositories).

- [Regions](#regions)
- [Stages](#stages)
- [Add clusters to the stages](#add-clusters-to-the-stages)
- [Promote a change from dev to prod](#promote-a-change-from-dev-to-prod)
- [Next steps](#next-steps)

The fork already has all of this: the Components in [bases/environments](/bases/environments), and the four clusters
as `HELLO_APP_*` in the example organisation. The steps write the same files, without their comments, so you can
follow them over the top of the Components, and create the clusters in your own organisation. Run the commands from
the root of your clone, with the variables from the basic tutorial's
[Before you start](../basic/getting-started.md#before-you-start) still set.

## Regions

Every cluster has to say which region it runs in. Without `global.providerSpecific.region`, the `release-aws` chart
takes the region of the management cluster's nodes, so a cluster would quietly be created next to its management
cluster. `tools/validate-helm-values` fails for a cluster without a region, so CI catches it before Flux does.

A region creates the `${cluster_name}-region-config` ConfigMap with the region, and appends it to the cluster's
`HelmRelease` `valuesFrom`, after the base's values.

1. Create the `eu-central` region. The quoted `'EOF'` keeps the variables in the files:

    ```sh
    mkdir -p bases/environments/regions/eu_central/node_pool
    cat <<'EOF' > bases/environments/regions/eu_central/region_config.yaml
    global:
      providerSpecific:
        region: eu-central-1
    EOF
    cat <<'EOF' > bases/environments/regions/eu_central/kustomization.yaml
    apiVersion: kustomize.config.k8s.io/v1alpha1
    kind: Component
    configMapGenerator:
      - files:
          - values=region_config.yaml
        name: ${cluster_name}-region-config
        namespace: org-${organization}
    generatorOptions:
      disableNameSuffixHash: true
      labels:
        reconcile.fluxcd.io/watch: Enabled
    patches:
      - patch: |-
          - op: add
            path: /spec/valuesFrom/-
            value:
              kind: ConfigMap
              name: ${cluster_name}-region-config
              valuesKey: values
        target:
          group: helm.toolkit.fluxcd.io
          kind: HelmRelease
          name: \${cluster_name}
    EOF
    ```

    The patch appends with `/spec/valuesFrom/-` rather than inserting at a fixed position such as
    `/spec/valuesFrom/1`. A fixed position is only right while the base has a given number of entries before it: the
    day the base gains one, the region's values silently land before or after the wrong layer. Appending takes the
    order from the `components:` list instead.

1. Give the region an extra node pool that spans its zones, in a second Component of its own. Only the clusters that
   need the capacity add it:

    ```sh
    cat <<'EOF' > bases/environments/regions/eu_central/node_pool/node_pool.yaml
    global:
      nodePools:
        large:
          availabilityZones:
            - eu-central-1a
            - eu-central-1b
            - eu-central-1c
          instanceType: m6a.2xlarge
          maxSize: 10
          minSize: 1
    EOF
    cat <<'EOF' > bases/environments/regions/eu_central/node_pool/kustomization.yaml
    apiVersion: kustomize.config.k8s.io/v1alpha1
    kind: Component
    configMapGenerator:
      - files:
          - values=node_pool.yaml
        name: ${cluster_name}-region-node-pool-config
        namespace: org-${organization}
    generatorOptions:
      disableNameSuffixHash: true
      labels:
        reconcile.fluxcd.io/watch: Enabled
    patches:
      - patch: |-
          - op: add
            path: /spec/valuesFrom/-
            value:
              kind: ConfigMap
              name: ${cluster_name}-region-node-pool-config
              valuesKey: values
        target:
          group: helm.toolkit.fluxcd.io
          kind: HelmRelease
          name: \${cluster_name}
    EOF
    ```

1. Create `us-west` from it. The two `kustomization.yaml` files are the same; only the values differ: the region is
   `us-west-2`, the pool's zones are `us-west-2a` to `us-west-2c`, and the pool uses the larger `m6a.4xlarge`:

    ```sh
    mkdir -p bases/environments/regions/us_west/node_pool
    cp bases/environments/regions/eu_central/kustomization.yaml bases/environments/regions/us_west/
    cp bases/environments/regions/eu_central/node_pool/kustomization.yaml bases/environments/regions/us_west/node_pool/
    cat <<'EOF' > bases/environments/regions/us_west/region_config.yaml
    global:
      providerSpecific:
        region: us-west-2
    EOF
    cat <<'EOF' > bases/environments/regions/us_west/node_pool/node_pool.yaml
    global:
      nodePools:
        large:
          availabilityZones:
            - us-west-2a
            - us-west-2b
            - us-west-2c
          instanceType: m6a.4xlarge
          maxSize: 10
          minSize: 1
    EOF
    ```

The pool is called `large`, so it doesn't share a key with a cluster's own `nodepool0`: a prod cluster gets both, its
own and the region's.

## Stages

A stage holds the versions its clusters run, and nothing else. It patches the tag of the cluster's `OCIRepository`,
which is the Giant Swarm release, and the `OCIRepository`s of the apps whose versions it controls. A patch for an app
that a cluster doesn't have changes nothing, so any CAPA cluster can use any stage. Its patches add nothing to
`valuesFrom`, so where it sits in the `components:` list doesn't matter.

Each stage pins its own release, so a new release reaches dev first, and staging and prod only when you promote it.
Pick releases from v34.0.0 on, which have a `release-aws` chart, and hello-world versions from its
[releases](https://github.com/giantswarm/hello-world-app/releases). The fork's stages hold the versions Renovate last
moved them to, so you can read them there:

```sh
kubectl get releases.release.giantswarm.io
grep -A1 'renovate:' bases/environments/stages/*/kustomization.yaml
```

Export them. Dev runs the newest release, staging one behind it, prod one behind staging:

```sh
export DEV_RELEASE=DEV_RELEASE                      # for example the newest release, without the `aws-` prefix
export STAGING_RELEASE=STAGING_RELEASE
export PROD_RELEASE=PROD_RELEASE
export STAGING_HELLO_WORLD=STAGING_HELLO_WORLD      # a hello-world chart version
export PROD_HELLO_WORLD=PROD_HELLO_WORLD
```

In the commands below, the shell fills in the versions, and `\\\${cluster_name}` writes `\${cluster_name}` into the
file: the target name escaped for kustomize, which reads it as a regular expression.

1. Dev doesn't pin hello-world at all: it follows hello-world's development builds, so every build from `3.0.0` on
   reaches dev as soon as it's published, with no pull request. Dev builds are pre-releases tagged
   `X.Y.Z-r<branch-CRC32>t<timestamp>h<sha>`. The `-0` on the range makes pre-releases eligible at all, and
   `semverFilter` keeps only the dev builds. Flux picks the highest matching tag, and for builds of the same version
   semver orders by the branch hash before the timestamp, so if several branches publish dev builds, put the CRC32 of
   the branch to follow into the filter instead of `[0-9a-f]{8}`:

    ```sh
    mkdir -p bases/environments/stages/dev bases/environments/stages/staging bases/environments/stages/prod
    cat <<EOF > bases/environments/stages/dev/kustomization.yaml
    apiVersion: kustomize.config.k8s.io/v1alpha1
    kind: Component
    patches:
      - patch: |-
          - op: replace
            path: /spec/ref
            value:
              semver: '>=3.0.0-0'
              semverFilter: '-r[0-9a-f]{8}t[0-9]{14}h[0-9a-f]{7}'
        target:
          kind: OCIRepository
          name: \\\${cluster_name}-hello-world
      - patch: |-
          - op: replace
            path: /spec/ref/tag
            # renovate: datasource=docker depName=gsoci.azurecr.io/charts/giantswarm/release-aws versioning=docker
            value: "${DEV_RELEASE}"
        target:
          kind: OCIRepository
          name: \\\${cluster_name}
    EOF
    ```

    The `# renovate:` comment lets Renovate find the release, which it can't see in a kustomize patch otherwise. Don't
    set `global.release.version` in any cluster values: the `release-aws` chart sets it from its own version.

1. Staging pins hello-world and the release, so it runs a version only once you've promoted it from dev. Its
   hello-world patch overrides the version the hello-web stack pins:

    ```sh
    cat <<EOF > bases/environments/stages/staging/kustomization.yaml
    apiVersion: kustomize.config.k8s.io/v1alpha1
    kind: Component
    patches:
      - patch: |-
          - op: replace
            path: /spec/ref/tag
            # renovate: datasource=docker depName=gsoci.azurecr.io/charts/giantswarm/hello-world versioning=docker
            value: "${STAGING_HELLO_WORLD}"
        target:
          kind: OCIRepository
          name: \\\${cluster_name}-hello-world
      - patch: |-
          - op: replace
            path: /spec/ref/tag
            # renovate: datasource=docker depName=gsoci.azurecr.io/charts/giantswarm/release-aws versioning=docker
            value: "${STAGING_RELEASE}"
        target:
          kind: OCIRepository
          name: \\\${cluster_name}
    EOF
    ```

1. Prod is staging with prod's versions:

    ```sh
    sed -e "s/\"${STAGING_HELLO_WORLD}\"/\"${PROD_HELLO_WORLD}\"/" -e "s/\"${STAGING_RELEASE}\"/\"${PROD_RELEASE}\"/" \
      bases/environments/stages/staging/kustomization.yaml > bases/environments/stages/prod/kustomization.yaml
    ```

A stage holds versions only. The prod clusters' bigger nodes are their own values, below.

A cluster whose release comes from a `ResourceSet`, as in [Scheduled upgrades](../advanced/scheduled-upgrades.md),
ignores the stage's release pin: it has no `OCIRepository` of the base's for the patch to change, and the `ResourceSet`
picks the release.

## Add clusters to the stages

Each cluster is built like any other CAPA cluster: the cluster base, the hello-web stack as a base app in
`cluster/apps`, its own values in `cluster_userconfig.yaml`, and its region and stage under `components:`. The
components append to the cluster's `HelmRelease` `valuesFrom` in the order they're listed, and the cluster's own patch
runs after them, so Flux merges the layers in this order:

1. `cluster-app-installation-values`, the management cluster's values;
1. `${cluster_name}-config`, the base's;
1. `${cluster_name}-region-config`, the region;
1. `${cluster_name}-region-node-pool-config`, the region's extra node pool, for the clusters that add it;
1. `${cluster_name}-cluster-userconfig`, the cluster's own.

1. Create the dev cluster's directory. Its `kustomization.yaml` lists only `cluster/`, so the cluster's `Kustomization`
   never applies an `out-of-band` directory next to it to the management cluster:

    ```sh
    export STAGES_DIR=${ORG_DIR}/workload-clusters
    mkdir -p ${STAGES_DIR}/HELLO_APP_DEV_CLUSTER_1/cluster/apps

    cat <<'EOF' > ${STAGES_DIR}/HELLO_APP_DEV_CLUSTER_1/kustomization.yaml
    apiVersion: kustomize.config.k8s.io/v1beta1
    kind: Kustomization
    resources:
      - cluster/
    EOF

    cat <<'EOF' > ${STAGES_DIR}/HELLO_APP_DEV_CLUSTER_1/cluster/kustomization.yaml
    apiVersion: kustomize.config.k8s.io/v1beta1
    buildMetadata: [originAnnotations]
    components:
      - ../../../../../../../bases/environments/regions/eu_central
      - ../../../../../../../bases/environments/stages/dev
    kind: Kustomization
    labels:
      - pairs:
          giantswarm.io/managed-by: flux
    patches:
      - path: patch_cluster_userconfig.yaml
        target:
          group: helm.toolkit.fluxcd.io
          kind: HelmRelease
          name: \${cluster_name}
    resources:
      - ../../../../../../../bases/clusters/capa
      - cluster_userconfig.yaml
      - apps/
    EOF

    cat <<'EOF' > ${STAGES_DIR}/HELLO_APP_DEV_CLUSTER_1/cluster/cluster_userconfig.yaml
    apiVersion: v1
    data:
      values: ""
    kind: ConfigMap
    metadata:
      labels:
        reconcile.fluxcd.io/watch: Enabled
      name: ${cluster_name}-cluster-userconfig
      namespace: org-${organization}
    EOF

    cat <<'EOF' > ${STAGES_DIR}/HELLO_APP_DEV_CLUSTER_1/cluster/patch_cluster_userconfig.yaml
    - op: add
      path: /spec/valuesFrom/-
      value:
        kind: ConfigMap
        name: ${cluster_name}-cluster-userconfig
        valuesKey: values
    EOF

    cat <<'EOF' > ${STAGES_DIR}/HELLO_APP_DEV_CLUSTER_1/cluster/apps/kustomization.yaml
    apiVersion: kustomize.config.k8s.io/v1beta1
    buildMetadata: [originAnnotations]
    kind: Kustomization
    resources:
      - ../../../../../../../../bases/stacks/hello-web
    EOF
    ```

    Dev has no values of its own yet, so its `cluster_userconfig.yaml` is empty and it gets the chart's default node
    pools.

1. Staging is dev with the staging stage:

    ```sh
    cp -r ${STAGES_DIR}/HELLO_APP_DEV_CLUSTER_1 ${STAGES_DIR}/HELLO_APP_STAGING_CLUSTER_1
    yq -i '.components |= map(sub("stages/dev$"; "stages/staging"))' \
      ${STAGES_DIR}/HELLO_APP_STAGING_CLUSTER_1/cluster/kustomization.yaml
    ```

1. The prod clusters list the prod stage, add their region's node pool after the region, and give themselves bigger
   nodes, and more of them:

    ```sh
    cp -r ${STAGES_DIR}/HELLO_APP_DEV_CLUSTER_1 ${STAGES_DIR}/HELLO_APP_PROD_CLUSTER_EU_CENTRAL
    yq -i '.components = [
      "../../../../../../../bases/environments/regions/eu_central",
      "../../../../../../../bases/environments/regions/eu_central/node_pool",
      "../../../../../../../bases/environments/stages/prod"
    ]' ${STAGES_DIR}/HELLO_APP_PROD_CLUSTER_EU_CENTRAL/cluster/kustomization.yaml

    cat <<'EOF' > ${STAGES_DIR}/HELLO_APP_PROD_CLUSTER_EU_CENTRAL/cluster/cluster_userconfig.yaml
    apiVersion: v1
    data:
      values: |
        global:
          nodePools:
            nodepool0:
              instanceType: m6a.8xlarge
              maxSize: 50
              minSize: 10
    kind: ConfigMap
    metadata:
      labels:
        reconcile.fluxcd.io/watch: Enabled
      name: ${cluster_name}-cluster-userconfig
      namespace: org-${organization}
    EOF

    cp -r ${STAGES_DIR}/HELLO_APP_PROD_CLUSTER_EU_CENTRAL ${STAGES_DIR}/HELLO_APP_PROD_CLUSTER_US_WEST
    yq -i '.components |= map(sub("eu_central"; "us_west"))' \
      ${STAGES_DIR}/HELLO_APP_PROD_CLUSTER_US_WEST/cluster/kustomization.yaml
    ```

1. Create the dev cluster's `Kustomization`, next to its directory. The organisation's namespace `Kustomization`
   applies it into `org-${ORG_NAME}`, and fills in `${organization}`, which the `\$` keeps in the file. It sets no
   `release`: the stage replaces the base's `${release}` tag before Flux would fill it in:

    ```sh
    cat <<EOF > ${STAGES_DIR}/HELLO_APP_DEV_CLUSTER_1.yaml
    apiVersion: kustomize.toolkit.fluxcd.io/v1
    kind: Kustomization
    metadata:
      name: ${MC_NAME}-clusters-hello-app-dev-1
    spec:
      dependsOn:
        - name: ${MC_NAME}-organization-${ORG_NAME}
          namespace: default
      interval: 10m
      path: "./${STAGES_DIR}/HELLO_APP_DEV_CLUSTER_1"
      postBuild:
        substitute:
          cluster_description: "description"
          cluster_name: "hello-app-dev-1"
          organization: "\${organization}"
      prune: true
      retryInterval: 1m
      serviceAccountName: automation
      sourceRef:
        kind: GitRepository
        name: ${GITOPS_REPO}
        namespace: default
      timeout: 2m
    EOF
    ```

1. The other three `Kustomization`s differ only in the directory and the cluster's name:

    ```sh
    for c in STAGING_CLUSTER_1:staging-1 PROD_CLUSTER_EU_CENTRAL:prod-euc PROD_CLUSTER_US_WEST:prod-usw; do
      sed -e "s/HELLO_APP_DEV_CLUSTER_1/HELLO_APP_${c%%:*}/" -e "s/hello-app-dev-1/hello-app-${c#*:}/" \
        ${STAGES_DIR}/HELLO_APP_DEV_CLUSTER_1.yaml > ${STAGES_DIR}/HELLO_APP_${c%%:*}.yaml
    done
    ```

1. List the four in the organisation's clusters, then commit and push:

    ```sh
    for c in DEV_CLUSTER_1 STAGING_CLUSTER_1 PROD_CLUSTER_EU_CENTRAL PROD_CLUSTER_US_WEST; do
      yq -i '.resources += ["HELLO_APP_'"${c}"'.yaml"] | .resources |= unique' ${STAGES_DIR}/kustomization.yaml
    done
    git add bases/environments ${STAGES_DIR}
    git commit -m "Add hello-app clusters in dev, staging and prod" && git push
    ```

**Check:** four clusters come up, each with the release of its stage:

```sh
kubectl get ocirepositories -n org-${ORG_NAME} | grep hello-app
```

With `prune: true`, Flux deletes what you delete from a cluster's files, but never the cluster itself: its
`HelmRelease` and `OCIRepository`, from the CAPA base, have the `kustomize.toolkit.fluxcd.io/prune: disabled`
annotation and the `giantswarm.io/prevent-deletion` label. To delete a cluster, see
[Delete a cluster](../../how-to/delete-cluster.md).

With this many layers, it helps to see what Flux will apply before you push. `tools/fake-flux` renders a cluster the
way Flux does, see [Render what Flux applies](../../how-to/check-changes.md#render-what-flux-applies).

## Promote a change from dev to prod

Every stage runs its own versions, and a version moves from one stage to the next in a pull request:

| Stage | hello-world | Release |
| --- | --- | --- |
| dev | the newest dev build, from a `semver` range | the newest |
| staging | pinned | one behind dev |
| prod | pinned | one behind staging |

[Renovate](/renovate.json5) finds the pins by their `# renovate:` comments, and opens a pull request per stage for
each new version of hello-world and of the release:

- **dev**: hello-world follows its range, so Flux deploys a new dev build without a pull request. A new release comes
  in the pull request without a stage prefix, which also updates the bases and the `WC_NAME*` example clusters.
- **staging**: a pull request on a `renovate/staging-*` branch changes the staging stage and the kind test's
  assertions for the staging clusters.
- **prod**: a pull request on a `renovate/prod-*` branch does the same for the prod stage.

The staging and prod pull requests, and every pull request that changes a release, are never merged automatically: a
release update replaces the cluster's nodes. Merging them in order is the promotion:

1. Dev gets the change first. Flux deploys each dev build of hello-world as it's published; for a release, merge the
   dev pull request.
1. Once the change works in dev, and for hello-world is published as a stable version, merge the staging pull request.
1. Once it works in staging, merge the prod pull request.

Without Renovate, promote the same way: change the version in the next stage's `kustomization.yaml` and merge it. To
promote a version other than the newest, change the version in Renovate's pull request before you merge it.

## Next steps

- [Automatic updates](./automatic-updates.md): version ranges, as dev uses for hello-world.
- [Scheduled upgrades](../advanced/scheduled-upgrades.md): hold prod's upgrades until an upgrade window.
- [Bases, Components and stacks](../../explanation/composition.md#bases-components-and-stacks): why stages and regions
  are Components.
