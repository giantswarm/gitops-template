# shared-objects

`management-clusters/MC_NAME/organizations/ORG_NAME/namespace/shared-objects`

This organisation's copy of the objects every organisation shares. The `kustomization.yaml` here lists
[`bases/shared_objects`](/bases/shared_objects/), so a change to the base reaches every organisation that lists it.

The organisation's namespace Kustomization, in `../../namespace.yaml`, applies this directory into `org-<name>`, which
gives the shared objects this organisation's namespace.

## What's here

- `kustomization.yaml`: lists the base, and nothing else.

## When you copy it

Copy it with the organisation, unchanged. Something only this organisation needs doesn't go into the base: add it to
the organisation's `namespace/` instead.

## Read more

- [Share an object](/docs/how-to/share-objects.md#share-an-object)
