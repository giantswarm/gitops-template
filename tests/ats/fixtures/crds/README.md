# CRDs for the test's workload cluster

The kind test creates these `CustomResourceDefinition`s in the vCluster that stands in for the
`out-of-band-no-flux` workload cluster (see
[CI checks](../../../../docs/reference/ci-checks.md#the-out-of-band-no-flux-workload-cluster)).
A Giant Swarm workload cluster gets them from its default apps. The apps of the example create objects of these
kinds, and their charts don't install the CRDs themselves. The test installs only the CRDs, no controllers.

They're kept in the repository, so the test doesn't download them on every run and they change only when someone
updates them here. Each file is one CRD, copied unchanged from the upstream file below, except the Kyverno one.

| File | Needed by | Source |
| --- | --- | --- |
| `ciliumnetworkpolicies.cilium.io.yaml` | gateway-api-crds, envoy-gateway | [Cilium v1.18.4](https://raw.githubusercontent.com/cilium/cilium/v1.18.4/pkg/k8s/apis/cilium.io/client/crds/v2/ciliumnetworkpolicies.yaml) |
| `podmonitors.monitoring.coreos.com.yaml` | envoy-gateway | [prometheus-operator v0.86.2](https://raw.githubusercontent.com/prometheus-operator/prometheus-operator/v0.86.2/example/prometheus-operator-crd/monitoring.coreos.com_podmonitors.yaml) |
| `servicemonitors.monitoring.coreos.com.yaml` | gateway-api-state-metrics | [prometheus-operator v0.86.2](https://raw.githubusercontent.com/prometheus-operator/prometheus-operator/v0.86.2/example/prometheus-operator-crd/monitoring.coreos.com_servicemonitors.yaml) |
| `podlogs.monitoring.grafana.com.yaml` | envoy-gateway | [Grafana Alloy v1.11.3](https://raw.githubusercontent.com/grafana/alloy/v1.11.3/operations/helm/charts/alloy/charts/crds/crds/monitoring.grafana.com_podlogs.yaml) |
| `certificates.cert-manager.io.yaml`, `issuers.cert-manager.io.yaml` | gateway-api-config | the two CRDs of that name in [cert-manager v1.19.1](https://github.com/cert-manager/cert-manager/releases/download/v1.19.1/cert-manager.crds.yaml) |
| `clusterpolicies.kyverno.io.yaml` | gateway-api-config | [Kyverno v1.15.2](https://raw.githubusercontent.com/kyverno/kyverno/v1.15.2/config/crds/kyverno/kyverno.io_clusterpolicies.yaml), reduced, see below |
| `dnsendpoints.externaldns.k8s.io.yaml` | gateway-api-config | [external-dns v0.19.0](https://raw.githubusercontent.com/kubernetes-sigs/external-dns/v0.19.0/config/crd/standard/dnsendpoints.externaldns.k8s.io.yaml) |

The Kyverno CRD is 1.4 MB upstream, more than the 500 kB the `check-added-large-files` pre-commit hook allows. The
file here keeps only version `v1`, the one the charts use and the storage version, and drops the `description` text
of its schema. It validates the same objects. To update it, run this on the upstream file:

```python
import sys

import yaml


def strip(node):
    if isinstance(node, dict):
        return {
            k: strip(v)
            for k, v in node.items()
            if not (k == "description" and isinstance(v, str))
        }
    if isinstance(node, list):
        return [strip(v) for v in node]
    return node


crd = yaml.safe_load(open(sys.argv[1]))
crd["spec"]["versions"] = [strip(v) for v in crd["spec"]["versions"] if v["name"] == "v1"]
print("---")
print(yaml.safe_dump(crd, sort_keys=False), end="")
```

When you update a CRD, update its row in the table. When an app needs another kind, add its CRD here; the test
installs every `.yaml` file in this directory.
