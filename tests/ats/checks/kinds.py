"""The Flux kinds the checks read, and the kinds a HelmRelease refers to."""

import pykube
from pykube.objects import APIObject
from pytest_helm_charts.flux.git_repository import GitRepositoryCR
from pytest_helm_charts.flux.helm_release import HelmReleaseCR
from pytest_helm_charts.flux.helm_repository import HelmRepositoryCR
from pytest_helm_charts.flux.utils import NamespacedFluxCR


class OCIRepositoryCR(NamespacedFluxCR):
    version = "source.toolkit.fluxcd.io/v1"
    endpoint = "ocirepositories"
    kind = "OCIRepository"


class HelmChartCR(NamespacedFluxCR):
    version = "source.toolkit.fluxcd.io/v1"
    endpoint = "helmcharts"
    kind = "HelmChart"


class BucketCR(NamespacedFluxCR):
    version = "source.toolkit.fluxcd.io/v1"
    endpoint = "buckets"
    kind = "Bucket"


# The kinds a HelmRelease takes its chart from: `chartRef` names an OCIRepository or a
#  HelmChart, `chart.spec.sourceRef` one of the others.
CHART_SOURCE_KINDS: dict[str, type[APIObject]] = {
    "OCIRepository": OCIRepositoryCR,
    "HelmChart": HelmChartCR,
    "HelmRepository": HelmRepositoryCR,
    "GitRepository": GitRepositoryCR,
    "Bucket": BucketCR,
}
REFERENCED_KINDS: dict[str, type[APIObject]] = {
    **CHART_SOURCE_KINDS,
    "ConfigMap": pykube.ConfigMap,
    "Secret": pykube.Secret,
    "HelmRelease": HelmReleaseCR,
}
# S1: the Flux sources that have to get ready, every source kind
SOURCE_KINDS: list[type[APIObject]] = list(CHART_SOURCE_KINDS.values())
