# Admission policies

The two Kyverno `ClusterPolicy`s that every Giant Swarm management cluster enforces on Flux objects, copied
from [giantswarm/management-cluster-bases](https://github.com/giantswarm/management-cluster-bases) at commit
`54ec7bdb049a14d343999107abe7174cb65fd9f2`, re-indented for yamllint, which changes no value:

| File | Source |
| --- | --- |
| `flux-multi-tenancy.yaml` | `bases/flux-app-v2/common/resource-kyverno-policies.yaml` |
| `flux-operator-multi-tenancy.yaml` | `bases/flux-operator/clusterpolicy.yaml` |

[admission_policies.py](../../admission_policies.py) applies them in the kind test once Kyverno runs, before Flux applies
the repository, so an object the management cluster would refuse at admission fails the test. When
management-cluster-bases changes them, copy them again and update the commit here, in the first line of each file and in
`SOURCE_COMMIT`.
