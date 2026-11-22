# organizations

`management-clusters/MC_NAME/organizations`

One directory per organisation on this management cluster, named after it. An organisation is a tenant: it gets its
own namespace, `org-<name>`, and its workload clusters live there.

The management cluster's Flux `Kustomization`, in `../MC_NAME.yaml`, applies each organisation's directory, through the
`kustomization.yaml` in it.

## What's here

- [`ORG_NAME/`](ORG_NAME/): the example organisation.

## When you copy it

Copy `ORG_NAME/` once per organisation, and rename it. Each organisation's directory is self-contained, so adding one
doesn't touch the others.

## Read more

- [2. Add an organisation](/docs/tutorials/basic/getting-started.md#2-add-an-organisation)
