# Managing Apps installed in clusters with GitOps

Apps in this repository are Flux `HelmRelease` + `OCIRepository` pairs: the `OCIRepository` points at the chart in an
OCI registry, the `HelmRelease` installs it into the workload cluster. See
[bases/apps/hello-world](/bases/apps/hello-world/) for an example. Only the cluster itself is still an App CR, see
[Add a new Workload Cluster](../add_wc.md).

Below is an index of docs about how to manage applications deployed to clusters:

   1. [Add a new App Template to the repository](add_app_template.md)
   1. [Creating and using App Sets (apps deployed together as a single step)](app_sets.md)
   1. [Add a new App to a Workload Cluster](add_appcr.md)
   1. [Update an existing App](update_appcr.md)
   1. [Enable automatic updates of an existing App](automatic_updates_appcr.md)
