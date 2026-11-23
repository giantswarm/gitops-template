# Stacks

At the end of [App Templates](./app-templates.md), your cluster runs hello-world from its template and Envoy Gateway
from its stack, side by side, and the cluster's own files hold what ties them together. hello-world's directory has
the `dependsOn` on the Gateway API CRDs and the hostname, Envoy Gateway's has the matching `hello` subdomain, and the
chart versions are wherever each base pins them. Every cluster that wants the two carries the same ties in its own
files, and has to get all of them right.

A stack keeps them in one place. It's several `HelmRelease`s that are deployed together and may depend on each other,
written as a kustomize base in `bases/stacks`. Its `resources:` lists the `HelmRelease`s and `OCIRepository`s of its
charts, or App Templates and other stacks, which can each still be used on their own, and the stack adds what ties
them together. A cluster lists the stack like an App Template, and gets all of its apps.

By the end of this tutorial, your cluster gets both from the hello-web stack, in one directory instead of two, and
hello-world still answers at the same address. It creates no cluster and installs nothing new: Flux updates the four
releases in place.

- [When a stack helps](#when-a-stack-helps)
- [Create a stack](#create-a-stack)
- [Use it in a cluster](#use-it-in-a-cluster)
- [Move an app into or out of a stack](#move-an-app-into-or-out-of-a-stack)
- [Next steps](#next-steps)

The fork ships two stacks:

- [envoy-gateway](/bases/stacks/envoy-gateway/) installs Envoy Gateway as three charts, in order: `gateway-api-crds`,
  the Gateway API CRDs; `envoy-gateway`, the controller, which `dependsOn` the CRDs; and `gateway-api-config`, the
  `giantswarm-default` `GatewayClass` and `Gateway`, which `dependsOn` the controller. Each chart has a directory of its
  own, with a `helm-release.yaml` and an `oci-repository.yaml`, so every file holds a single resource, as the files
  `kubectl gs gitops` writes do, and a command like `yq -i '.spec.ref.tag = "NEW_VERSION"' oci-repository.yaml` changes
  only the chart you mean.
- [hello-web](/bases/stacks/hello-web/) is a stack built from a stack and an app: hello-world, served over HTTPS
  through the envoy-gateway stack. It's the one this tutorial builds and installs.

On AWS, the Gateway gets its address from the AWS Load Balancer Controller, which isn't part of a Giant Swarm release.
Install Giant Swarm's `aws-lb-controller-bundle` on the workload cluster as
[its README](https://github.com/giantswarm/aws-lb-controller-bundle#installing) describes, or ask Giant Swarm to. The
cluster from the basic tutorial has it already. The Gateway also needs cert-manager's Gateway API support, which step
4 of the basic tutorial switches on.

Run the commands from the root of your clone, with the variables the basic tutorial exported still set: those from
[Before you start](../basic/getting-started.md#before-you-start), and the ones its steps add, such as `WC_CONTEXT`.

## When a stack helps

Put apps into a stack when they're deployed together and some of these apply:

- **Order.** One app needs another to be installed first. The stack adds the `dependsOn` once, instead of every
  cluster adding it, see [Order it after another release](./app-templates.md#order-it-after-another-release).
- **Values that have to agree.** One app's values have to match another's. In hello-web, the Gateway's
  `listeners.https.subdomains` lists `hello`, and hello-world's `route.hostnames` is `hello.{{ .Values.baseDomain }}`
  on the Gateway in `route.parentRefs`. Both files sit in the same directory, so a change to one is seen next to the
  other in review.
- **Versions known to work together.** The stack pins the chart version of each app in its `kustomization.yaml`, so
  the versions that were tested together are in one place. Each pin has a `# renovate:` comment, and Renovate opens a
  pull request per chart, so check an update against the other pins before you merge it.
- **One line per cluster.** Adding `hello-web` to a cluster's apps adds the whole stack, and removing it removes the
  whole stack.

If the apps are independent, don't make a stack: list each App Template in the cluster.

## Create a stack

hello-web is already in your fork. These steps write the same files, without their comments, so you can follow them
over the top of it.

```text
bases/stacks/hello-web
├── kustomization.yaml       the envoy-gateway stack and the hello-world App Template, and the patches that tie them
├── gateway_api_config.yaml  the Gateway, with the `hello` subdomain
└── hello_world.yaml         hello-world, with the hostname `hello.<base domain>` on that Gateway
```

1. Create the stack's directory:

    ```sh
    mkdir -p bases/stacks/hello-web
    ```

1. Put the values each app gets into a file of its own. Each file replaces the whole `-values` ConfigMap of the base
   that installs the app, so it has to hold every default the app needs: start from that base's default config and
   change what the stack needs. The `-user-values` ConfigMaps and `-user-secrets` Secrets stay free for a cluster's own
   values. First the Gateway, which replaces the envoy-gateway stack's `default_config_gateway_api_config.yaml`:

    ```sh
    cat <<'EOF' > bases/stacks/hello-web/gateway_api_config.yaml
    gateways:
      default:
        name: giantswarm-default
        listeners:
          https:
            subdomains:
              - hello
    EOF
    ```

    Then hello-world, which replaces the template's `default_config.yaml`. Its `parentRefs` names the Gateway above,
    and its hostname uses the `hello` subdomain the Gateway lists:

    ```sh
    cat <<'EOF' > bases/stacks/hello-web/hello_world.yaml
    autoscaling:
      minReplicas: 2
    ingress:
      enabled: false
    route:
      enabled: true
      kind: HTTPRoute
      parentRefs:
        - name: giantswarm-default
          namespace: envoy-gateway-system
      hostnames:
        - "hello.{{ .Values.baseDomain }}"
    EOF
    ```

1. Write the `kustomization.yaml`. It lists the envoy-gateway stack and the hello-world template, replaces their two
   `-values` ConfigMaps with the files above, makes hello-world wait for the Gateway API CRDs, and pins the version of
   each chart:

    ```sh
    cat <<'EOF' > bases/stacks/hello-web/kustomization.yaml
    apiVersion: kustomize.config.k8s.io/v1beta1
    buildMetadata: [originAnnotations]
    configMapGenerator:
      - behavior: replace
        files:
          - values=gateway_api_config.yaml
        name: ${cluster_name}-gateway-api-config-values
      - behavior: replace
        files:
          - values=hello_world.yaml
        name: ${cluster_name}-hello-world-values
    generatorOptions:
      disableNameSuffixHash: true
      labels:
        reconcile.fluxcd.io/watch: Enabled
    kind: Kustomization
    namespace: org-${organization}
    patches:
      - patch: |-
          - op: add
            path: /spec/dependsOn
            value:
              - name: ${cluster_name}-gateway-api-crds
        target:
          kind: HelmRelease
          name: \${cluster_name}-hello-world
      - patch: |-
          - op: replace
            path: /spec/ref/tag
            # renovate: datasource=docker depName=gsoci.azurecr.io/charts/giantswarm/gateway-api-crds versioning=docker
            value: "1.9.1"
        target:
          kind: OCIRepository
          name: \${cluster_name}-gateway-api-crds
      - patch: |-
          - op: replace
            path: /spec/ref/tag
            # renovate: datasource=docker depName=gsoci.azurecr.io/charts/giantswarm/envoy-gateway versioning=docker
            value: "1.10.5"
        target:
          kind: OCIRepository
          name: \${cluster_name}-envoy-gateway
      - patch: |-
          - op: replace
            path: /spec/ref/tag
            # renovate: datasource=docker depName=gsoci.azurecr.io/charts/giantswarm/gateway-api-config versioning=docker
            value: "1.13.1"
        target:
          kind: OCIRepository
          name: \${cluster_name}-gateway-api-config
      - patch: |-
          - op: replace
            path: /spec/ref/tag
            # renovate: datasource=docker depName=gsoci.azurecr.io/charts/giantswarm/hello-world versioning=docker
            value: "3.2.4"
        target:
          kind: OCIRepository
          name: \${cluster_name}-hello-world
    resources:
      - ../envoy-gateway
      - ../../apps/hello-world
    EOF
    ```

    The versions are the ones the fork pinned when this was written. Renovate keeps the fork's copy up to date.

    A few details carry the weight here:

    - The `name` of each generated ConfigMap has to be the name the listed base uses, or `behavior: replace` finds
      nothing to replace, and kustomize says so.
    - `namespace` is the organisation's namespace, as the `HelmRelease`s look up their values, their `OCIRepository`
      and the kubeconfig Secret there.
    - The `$` of a target name is escaped, as kustomize reads the name as a regular expression.

1. The fork's copy has comments on each part, and pins that Renovate may have moved since. Once you've compared the
   two, put the fork's back:

    ```sh
    git checkout -- bases/stacks/hello-web
    ```

## Use it in a cluster

A cluster uses a stack as it uses an App Template: a directory in the cluster's `apps`, whose `kustomization.yaml`
lists the stack under `resources:`. Your cluster's hello-world directory does nearly that already, so move it onto the
stack, and take out the envoy-gateway directory, which the stack replaces. Every object keeps its name, such as
`${WC_NAME}-hello-world` and `${WC_NAME}-gateway-api-crds`, so Flux upgrades the four releases in place.

1. Rename the app's directory after the stack, and point it at the stack instead of the template:

    ```sh
    git mv ${WC_DIR}/apps/hello-world ${WC_DIR}/apps/hello-web
    export APP_DIR=${WC_DIR}/apps/hello-web
    yq -i '.resources |= map(sub("bases/apps/hello-world$"; "bases/stacks/hello-web"))' ${APP_DIR}/kustomization.yaml
    yq -i '.resources |= map(sub("^hello-world$"; "hello-web"))' ${WC_DIR}/apps/kustomization.yaml
    ```

1. The stack now holds what the cluster's files did. It makes hello-world wait for the Gateway API CRDs, so take out
   the cluster's `dependsOn` patch. Its values set the route and the hostname, so take those out of
   `override_config.yaml` too:

    ```sh
    yq -i 'del(.patches[] | select(.patch | test("dependsOn")))' ${APP_DIR}/kustomization.yaml
    yq -i 'del(.ingress) | del(.route)' ${APP_DIR}/override_config.yaml
    ```

1. The stack brings Envoy Gateway, with the `hello` subdomain in its Gateway values, so remove the cluster's own
   envoy-gateway directory:

    ```sh
    git rm -rq ${WC_DIR}/apps/envoy-gateway
    yq -i 'del(.resources[] | select(. == "envoy-gateway"))' ${WC_DIR}/apps/kustomization.yaml
    ```

    The rest of `override_config.yaml` is still the `${cluster_name}-hello-world-user-values` ConfigMap, and still
    wins over the stack's values. There is no `${cluster_name}-hello-web` `HelmRelease`: a cluster's own values go to
    each app by the app's name, as `${cluster_name}-<app>-user-values`. A version patch from App Templates still works
    too, as the cluster's patches come after the stack's.

1. Commit and push:

    ```sh
    git add ${WC_DIR}/apps
    git commit -m "Deploy the hello-web stack to ${WC_NAME}" && git push
    ```

**Check:** the same four releases are `Ready`: the three of Envoy Gateway, then hello-world, which waits for the
Gateway API CRDs:

```sh
flux get helmreleases -n org-${ORG_NAME} | grep ${WC_NAME}-
```

If it doesn't get there, see [When something isn't Ready](../../how-to/troubleshooting.md).

hello-world's `HTTPRoute` is attached to the Gateway:

```sh
kubectl --context ${WC_CONTEXT} get httproute -n hello-world
```

And hello-world answers at the same address as before. The Gateway, its DNS record and its certificate didn't
change, only which files describe them:

```sh
curl -s ${HELLO_URL} | head
```

Your cluster installs the stack as a secondary app, from `${WC_DIR}/apps`, once the cluster is up. A cluster can also
install a stack with the cluster, as a base app, by listing it in `${WC_DIR}/cluster/apps/kustomization.yaml`, as the
`HELLO_APP_*` clusters in [Stages and regions](./stages-and-regions.md) do. A stack's apps are always applied by the
same Flux `Kustomization`. When only some of them have to be base apps, list their bases separately instead: the
out-of-band example clusters install the envoy-gateway stack in
`management-clusters/MC_NAME/organizations/ORG_NAME/workload-clusters/WC_NAME_OUT_OF_BAND_NO_FLUX_APP/cluster/apps`,
and hello-world from its template in
`management-clusters/MC_NAME/organizations/ORG_NAME/workload-clusters/WC_NAME_OUT_OF_BAND_NO_FLUX_APP/apps`.

## Move an app into or out of a stack

A stack and an app made from one of the bases it lists produce objects with the same names, such as
`${cluster_name}-hello-world`. A cluster can only have one of them, which is also what makes moving painless: change
both in the same commit, as you did above, and the objects keep their names, so Flux updates them in place instead of
reinstalling the app.

Moving an app out of a stack is the same in reverse: in one commit, list the app's template in the cluster's apps and
take the stack out. Take a stack out of a cluster altogether and Flux uninstalls all of its apps together. For the
envoy-gateway stack, see [Order it after another release](./app-templates.md#order-it-after-another-release) for the
`GatewayClass` that can be left behind.

kustomize has limits as a way to build stacks: it can replace values, but it can't set one value in several places,
which is why hello-web writes the `hello` subdomain twice. [Limits of kustomize](../../explanation/composition.md#limits-of-kustomize)
covers what to use when that gets in the way, and [Bases, Components and stacks](../../explanation/composition.md#bases-components-and-stacks)
why a stack is a base and not a Component.

## Next steps

- [Cluster bases](./cluster-bases.md): share a cluster's defaults the way a stack shares apps.
- [Stages and regions](./stages-and-regions.md): install hello-web on a cluster per stage, each with its own versions.
- [Automatic updates](./automatic-updates.md): what to bear in mind before you put a version range on a stack's app.
