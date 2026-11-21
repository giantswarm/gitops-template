# namespace

`management-clusters/MC_NAME/organizations/ORG_NAME/namespace`

Everything the organisation keeps in its own namespace, `org-<name>`: the workload clusters' SOPS keys, their Flux
Kustomizations, the secret stores and the commit status objects.

The organisation's namespace Kustomization, in `../namespace.yaml`, applies this directory into `org-<name>` with
`targetNamespace`. It has a Kustomization of its own, rather than riding along with the management cluster's, because
the namespace doesn't exist until organization-operator has created it for the `Organization`. This one fails until
then and succeeds on its next retry, and nothing else has to wait. The files here name no namespace, and write
`${organization}` where they need the organisation's name.

## What's here

- `kustomization.yaml`: lists the three directories here, and two next to what they belong with:
  `../workload-clusters` and `../multicluster/secret-stores`.
- [`secrets/`](secrets/): the workload clusters' SOPS keys.
- [`notifications/`](notifications/): commit statuses for the Kustomizations in this namespace.
- [`shared-objects/`](shared-objects/): this organisation's copy of `bases/shared_objects`.

## When you copy it

Copy it with the organisation. `kustomization.yaml` needs no change: the names come from the organisation's directory.
The subdirectories do: put your own clusters' keys in `secrets/`, and change the two `TODO`s in `notifications/`, the
`Provider`'s repository and the `Alert`'s list of Kustomizations. Don't give a file a namespace other than the
organisation's. Something that has to be in `default` belongs in the organisation's directory instead, and something
cluster-scoped doesn't belong to an organisation.

## Read more

- [2. Add an organisation](/docs/tutorials/basic/getting-started.md#2-add-an-organisation)
- [Flux Kustomizations](/docs/reference/repo-structure.md#flux-kustomizations)
