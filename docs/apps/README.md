# Managing Apps installed in clusters with GitOps

> **Note**
> The apps in this repository are now `HelmRelease` + `OCIRepository` pairs, but the pages below still walk through
> the App CR workflow and `kubectl gs template app`. They are being rewritten as part of
> [giantswarm/roadmap#4380](https://github.com/giantswarm/roadmap/issues/4380). For the shape the example manifests
> actually have today, read [bases/apps/hello-world](/bases/apps/hello-world/).

Below is an index of docs about how to manage applications deployed to clusters:

   1. [Add a new App Template to the repository](add_app_template.md)
   1. [Creating and using App Sets (apps deployed together as a single step)](app_sets.md)
   1. [Add a new App to a Workload Cluster](add_appcr.md)
   1. [Update an existing App](update_appcr.md)
   1. [Enable automatic updates of an existing App](automatic_updates_appcr.md)
