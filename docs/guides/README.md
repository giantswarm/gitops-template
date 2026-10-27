# Guides

These guides cover what comes after [Getting started](../getting-started.md). Each one solves a single task.

Clusters:

- [Add a CAPx Workload Cluster template](./cluster-templates.md) to create many clusters from one definition.
- [Add Workload Cluster environments](./environments.md) to run dev, staging and production clusters from shared
  templates.

Apps:

Apps in this repository are Flux `HelmRelease` + `OCIRepository` pairs. The `OCIRepository` points at the chart in an
OCI registry, and the `HelmRelease` installs it into the workload cluster. See
[bases/apps/hello-world](/bases/apps/hello-world/) for an example.

- [Add a new App to a Workload Cluster](./add-app.md)
- [Update an existing App](./update-app.md)
- [Enable automatic updates of an existing App](./automatic-updates.md)
- [Add a new App Template to the repository](./app-templates.md) to reuse an app's configuration across clusters.
- [Create and use App Sets](./app-sets.md) to deploy several apps together.

Repository:

- [Configuring extra validation and diff previews on GitHub](./ci-validation.md)
