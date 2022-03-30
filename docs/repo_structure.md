# Repository Structure

- [General Remarks](#general-remarks)
- [Rules for Naming Resources](#rules-for-naming-resources)
- [Rules for Optional Components](#rules-for-optional-components)
  - [`[OTHER_RESOURCES]`](#other_resources)
  - [`[kustomization.yaml]`](#kustomizationyaml)
  - [`[organizations]`](#organizations)
  - [`[workload-clusters]`](#workload-clusters)
- [Flux Kustomization CRs Involved](#flux-kustomization-crs-involved)

## General Remarks

The repository follows a certain structure that mimics the actual hierarchy of the installation
building blocks, i.e. organizations, workload clusters, apps, etc., and their relations to each other, see figure below.

```text
.sops.yaml
bases
├── clusters
└── nodepools
management-clusters
└── MC_NAME
    ├── .sops.keys
    ├── [kustomization.yaml]
    ├── [OTHER_RESOURCES]
    ├── MC_NAME.yaml
    └── [organizations]
        ├── [kustomization.yaml]
        └── ORG_NAME
            ├── [kustomization.yaml]
            ├── [OTHER_RESOURCES]
            ├── ORG_NAME.yaml
            └── [workload-clusters]
                ├── kustomization.yaml
                ├── WC_NAME.yaml
                └── WC_NAME                             managed from MC_NAME.yaml
-----------------------------------------------------------------------------------
                    ├── [kustomization.yaml]            WC_NAME.yaml responsibility
                    ├── apps
                    ├── cluster
                    └── [OTHER_RESOURCES]
```

Capital letters are placeholders for the actual names of user resources and MUST be changed upon configuration. In case
of any doubt, it is RECOMMENDED to follow the [Rules for Naming Resources](#rules-for-naming-resources) when doing so.

Nodes of the structure carrying an extension, e.g. `*.yaml` denote files, while the rest are considered directories,
e.g. `organizations`. A special case to this rule is the `OTHER_RESOURCES` placeholder that denotes both files and
directories, in order to emphasize that structure it MAY be extended by a user at different levels, with resources they
need. When doing so however, the user SHOULD try to stay compliant with the hierarchy and find the best match for the
resources to be introduced.

Components enclosed between square brackets `[]` are considered OPTIONAL, hence users MAY omit them, it is however
RECOMMENDED to stay compliant with the [Rules for Optional Components](#rules-for-optional-components) when doing so.
This is to offer flexibility and allow different environments and use-cases.

The horizontal line marks the delegation of responsibility for reconciliation. Resources above the line are managed by
the `MC_NAME.yaml` Kustomization CR, whereas resources below the line are managed by the `WC_NAME.yaml`, see the
[Flux Kustomization CRs Involved](#flux-kustomizations-crs-involved).

## Rules for Naming Resources

Naming recommendations are in the table below.

| Placeholder | Rule |
| :--: | :--: |
| `MC_NAME` | User is REQUIRED to use the Management Cluster codename for clarity |
| `ORG_NAME` | Organization name, it is RECOMMENDED to not use capital letters and omit the `org-` prefix |
| `WC_NAME` | User MAY may give it an arbitrary name, however it is RECOMMENDED to use the Workload Cluster id
for clarity |

## Rules for Optional Components

### `[OTHER_RESOURCES]`

Any resources supported by Kubernetes, not explicitly targeted by the structure described here. Upon configuration,
when the number of these additional resources is relatively high, it is RECOMMENDED to group them by their kinds aiming
for readability, see examples below.

```text
## RECOMMENDED ##
management-clusters
└── demomc
    ├── secrets
    |   ├── secret-1.enc.yaml
    |   └── secret-2.enc.yaml
    └── configmaps
        └── cm.yaml
```

```text
## NOT RECOMMENDED ##
management-clusters
└── demomc
    ├── secret-1.enc.yaml
    ├── secret-2.enc.yaml
    └── cm.yaml
```

The "relatively high" is however a subject to user preferences, hence user MAY use any hierarchy they see fit, as far
as it does not break the general structure presented here.

### `[kustomization.yaml]`

If the file is not present under a path supplied to Flux, it will then auto-generate it for a given directory and its
sub-directories, recursively continuing the process until either reaching the bottom of directory hierarchy or finding
a `kustomization.yaml`. Hence, the file **plays a crucial role in the GitOps process**, even if not explicitly created.
User MAY omit it if they do not relay on the
[kustomize feature](https://kubernetes.io/docs/tasks/manage-kubernetes-objects/kustomization/#kustomize-feature-list)
and when feeling confident about Flux auto discovering resources. Otherwise it is RECOMMENDED to create it and use it
to explicitly control resources to be reconciled (with `.bases` and `.resources` fields).

### `[organizations]`

It is RECOMMENDED to use it explicitly when there are other resources populated under the `MC_NAME` directory, see
`[OTHER_RESOURCES]`. This is to avoid ambiguity that could arise with an increasing number of resources, when different
kinds of those are mixed together in a single directory, this blurs their content and thus degrades readability.

```text
## RECOMMENDED ##
management-clusters
└── demomc
    ├── secrets
    |   ├── mc-secret-1.enc.yaml
    |   └── mc-secret-2.enc.yaml
    ├── configmaps
    |   ├── mc-cm-1.yaml
    |   └── mc-cm-2.yaml
    └── organizations
        └── demo-gitops
            └── demo-gitops.yaml
```

```text
## NOT RECOMMENDED ##
management-clusters
└── demomc
    ├── mc-secret-1.enc.yaml
    ├── mc-secret-2.enc.yaml
    ├── mc-cm-1.yaml
    ├── mc-cm-2.yaml
    └── demo-gitops
            └── demo-gitops.yaml
---
management-clusters
└── demomc
    ├── secrets
    |   ├── mc-secret-1.enc.yaml
    |   └── mc-secret-2.enc.yaml
    ├── configmaps
    |   ├── mc-cm-1.yaml
    |   └── mc-cm-2.yaml
    └── demo-gitops
            └── demo-gitops.yaml
```

With no `OTHER_RESOURCES` present, or when preferring a flatter structure, the user MAY decide to not use the
organizations' container explicitly, and store organizations by their names directly under the `MC_NAME`, see example below.

```text
management-clusters
└── demomc
    └── demo-gitops
        └── demo-gitops.yaml
```

### `[workload-clusters]`

It is RECOMMENDED to use it explicitly when there are other resources populated under the `ORG_NAME` directory, see
`[OTHER_RESOURCES]`, see examples below. The same reasoning as for the `[organizations]` apply here.

```text
## RECOMMENDED ##
management-clusters
└── demomc
    └── organizations
        └── demo-gitops
            ├── secrets
            |   ├── org-secret-1.enc.yaml
            |   └── org-secret-2.enc.yaml
            ├── configmaps
            |   ├── org-cm-1.yaml
            |   └── org-cm-2.yaml
            ├── demo-gitops.yaml
            └── workload-clusters
                ├── kustomization.yaml
                ├── demo0.yaml
                └── demo0
```

```text
## NOT RECOMMENDED ##
management-clusters
└── demomc
    └── organizations
        └── demo-gitops
            ├── org-secret-1.enc.yaml
            ├── org-secret-2.enc.yaml
            ├── org-cm-1.yaml
            ├── org-cm-2.yaml
            ├── demo-gitops.yaml
            ├── kustomization.yaml
            ├── demo0.yaml
            └── demo0
---
management-clusters
└── demomc
    └── organizations
        └── demo-gitops
            ├── secrets
            |   ├── org-secret-1.enc.yaml
            |   └── org-secret-2.enc.yaml
            ├── configmaps
            |   ├── org-cm-1.yaml
            |   └── org-cm-2.yaml
            ├── demo-gitops.yaml
            ├── kustomization.yaml
            ├── demo0.yaml
            └── demo0
```

With no `OTHER_RESOURCES` present, or when preferring a flatter structure, the user MAY decide to not use the
`workload-clusters` container explicitly, and store clusters by their names directly under the `ORG_NAME`, see example below.

```text
management-clusters
└── demomc
    └── organizations
        └── demo-gitops
            ├── demo-gitops.yaml
            ├── kustomization.yaml
            ├── demo0.yaml
            └── demo0
```

## Flux Kustomization CRs Involved

Current design assumes use of **two** types of Flux's Kustomization CRs: the `MC_NAME.yaml` and the `WC_NAME.yaml`, see the
shortened version of the structure below.

```text
management-clusters
└── MC_NAME
    ├── MC_NAME.yaml                        # First Kustomization CR
    └── organizations
        └── ORG_NAME
            └── workload-clusters
                ├── kustomization.yaml
                ├── WC_NAME.yaml            # Second Kustomization CR
                └── WC_NAME
                    ├── apps
                    └── cluster
```

The `MC_NAME.yaml` starts at the `MC_NAME/` directory and reconciles everything up to the `WC_NAME.yaml`, but not any
resource under the `WC_NAME/` directory. This is accomplished with the mandatory `kustomization.yaml` that includes, and
hence tells Flux to create, only the `WC_NAME.yaml` from the `workload-clusters` directory, see example below:

```text
resources:
- WC_NAME.yaml
```

The `WC_NAME.yaml` Kustomization CR, when created, points to the respective `WC_NAME/` directory and reconciles
everything there, including itself, and hence takes over the reconciliation from where the `MC_NAME.yaml` leaves it.

But why two Kustomization CRs? The need for the first one, namely the `MC_NAME.yaml`, is obvious as without it there is no
reconciliation at all. The `WC_NAME.yaml` has been introduced in order to use the
[variable substitution feature of Flux](https://fluxcd.io/docs/components/kustomize/kustomization/#variable-substitution)
for configuring widely repeatable fields, that could otherwise be hard to configure. These fields are workload cluster ID,
control plane ID, release, etc., virtually any field that must be repeated for different CRs, like `Cluster`,
`MachineDeployment`, `App`, etc., falls into this category. Let's consider available options together.

Providing values to these fields by means of patches feels cumbersome and error prone, and leaves a decent footprint.

Not using patches, and hence bases, means placing a complete definition of resources into the structure, but it results
in an even bigger footprint, and works against good practices, e.g. imagine user needs to update a field in all the CRs
of a certain kind and how annoying it could be without a base.

This clearly feels there is a certain group of fields that could use a little templating magic, which is sadly not supported
in the Kubernetes kustomize. One could ask why not introduce Helm Chart to do it? If we did, it would solve the problem,
but at the cost of introducing additional layers in between Kustomization and end resource, and related effort of doing it.

Hence, a simple variables substitution offered by Flux, feels the right answer.
