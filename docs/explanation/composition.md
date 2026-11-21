# Composition

A repository with one cluster needs no structure to speak of. With twenty clusters across three stages and two
regions, every choice about where a value lives decides how much you copy, and what a change reaches. This page
explains the choices this template makes: environments as directories, and the three ways it shares configuration,
bases, Components and stacks.

## Directories, branches or repositories

There are three common ways to keep environments such as dev, staging and production apart:

- a directory per environment, all on the `main` branch of one repository;
- a branch per environment, in the same repository;
- a repository per environment, with one more repository for what they share.

Each has pros and cons. This template uses directories. One branch of one repository is the source of truth for every
environment, so sharing a template is a relative path, and comparing or promoting configuration across environments is
a diff of two directories in one commit. The cost is that access control is coarser: who can merge to `main` can change
every environment, which [CODEOWNERS](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-code-owners)
softens but doesn't remove. Templates have no versions of their own either: a change to a base reaches every cluster
that uses it at once, unless a stage pins what it needs.

Branches look tidy until you merge between them: every promotion is a merge, and the differences you meant to keep
fight the ones you meant to promote. Separate repositories give you clean access control, at the price of a
`GitRepository` per environment and changes that span several pull requests.

The [stages and regions tutorial](../tutorials/intermediate/stages-and-regions.md) shows the directory approach with
three stages and two regions.

## Bases, Components and stacks

The template shares configuration three ways. They're all plain kustomize; what differs is what they do to the objects
around them.

A **base** is a directory a cluster lists under `resources:`. It adds objects, and it builds on its own, so it can be
the `path` of a Flux `Kustomization`. The cluster bases in `bases/clusters` and the App Templates in `bases/apps` are
bases: a cluster lists the base and only adds what's different, such as its own values.

A **stack** is a base of several apps deployed together, such as `bases/stacks/hello-web`. It lists other bases, App
Templates or stacks, and holds what ties them together: the order they install in, the values that have to agree, and
the chart versions known to work together. A cluster lists the stack once, rather than each app with its own patches.
See [Deploy several apps together](../tutorials/intermediate/stacks.md).

A **[kustomize Component](https://kubectl.docs.kubernetes.io/guides/config_management/components/)** is a directory a
cluster lists under `components:`. Unlike a base, it can patch objects it didn't create, and it can't build on its own.
The [regions](../tutorials/intermediate/stages-and-regions.md#regions) are Components because they append a ConfigMap
to the cluster's `valuesFrom`, and the [stages](../tutorials/intermediate/stages-and-regions.md#stages) because they pin
the versions of the cluster and its apps.

So: make a stack a base, under `resources:`, as hello-web is. Use a Component only when the piece has to patch objects
outside itself. For some Components the order in `components:` matters, such as the regions, whose entries land in
`valuesFrom` in that order; for others, such as the stages, it doesn't. [Values](../reference/values.md) has the
rules.

## Limits of kustomize

kustomize is not a templating engine. It can replace values, but it can't set one value in several places, so values
that have to agree are written in each app's file, as hello-web does with the `hello` subdomain. Two apps can only
share values by listing the same ConfigMap or Secret in `valuesFrom`, and then both charts have to understand every key
in it the same way.

Flux adds one thing kustomize lacks, variables: a `Kustomization`'s `spec.postBuild.substitute` fills in
`${cluster_name}` and the like after kustomize has built the directory. That's what lets one base serve every cluster.
It's string replacement, though, not logic: there are no conditions and no loops.

When that isn't enough, two other ways fit better:

- an umbrella Helm chart, which installs the apps as
  [sub-charts](https://helm.sh/docs/chart_template_guide/subcharts_and_globals/) and can pass one value to all of them;
- a Flux Operator `ResourceSet` in the organisation's `multicluster/apps`, which renders the apps for several clusters
  from one set of inputs, see [Roll an app out to many clusters](../tutorials/advanced/multicluster-apps.md).
