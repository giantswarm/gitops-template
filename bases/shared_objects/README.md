# shared_objects

`bases/shared_objects`

Objects every organisation gets its own copy of, such as a CA bundle that all clusters trust. Write the object once
here, and every organisation that lists this base gets it in its namespace and keeps it in step with this file.

Nothing applies this directory directly. The objects have no namespace: each organisation's
[`namespace/shared-objects/`](/management-clusters/MC_NAME/organizations/ORG_NAME/namespace/shared-objects/) lists this
base, and the organisation's namespace Kustomization applies the copy into that organisation's namespace,
`org-<name>`.

## What's here

- `shared-ca-bundle.yaml`: the example, a ConfigMap `shared-ca-bundle` with a placeholder certificate.
- `kustomization.yaml`: lists the shared objects.

## When you copy it

Replace the placeholder certificate with your own CAs, or delete the example and list your own objects in
`kustomization.yaml`. Don't give an object a namespace here: each organisation sets its own. A new organisation gets
the objects by listing this base in its `namespace/shared-objects/kustomization.yaml`.

## Read more

- [Share an object](/docs/how-to/share-objects.md#share-an-object)
- [Add another organisation](/docs/how-to/share-objects.md#add-another-organisation)
