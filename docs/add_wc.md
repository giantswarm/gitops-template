# Add a new Workload Cluster

Adding a new Workload Cluster requires a few major steps in the configuration process. You need to
understand and follow all of them to produce a valid configuration. These steps are documented in following docs:

1. [Preparing a cluster definition template](./add_wc_template.md) you want to use for your cluster (if it
   doesn't already exist).
1. [Preparing GitOps repository structure, encryption secrets and dedicated Flux Kustomization](./add_wc_structure.md).
1. [Providing actual instance of a cluster, a definition of infrastructure required to run it](./add_wc_instance.md).
1. [Configuring Apps to be deployed in the new cluster](./apps/README.md).
