"""Checking the assertions against the objects in a cluster."""

import logging
import time

import pykube
from pykube.objects import APIObject, NamespacedAPIObject

from checks.comparison import assert_objects, object_name

FLUX_MANAGED_OBJECTS_READY_TIMEOUT_SEC = 15

logger = logging.getLogger(__name__)


class AssertionFileError(Exception):
    """An assertion file declares an object without the fields that identify it."""

    def __init__(self, file: str, missing: str) -> None:
        super().__init__(
            f"Expected object declared in the '{file}' has to have {missing}."
        )


class KindNotServedError(Exception):
    """The API server doesn't serve the kind an assertion declares."""

    def __init__(self, kind: str, group_version: str | None) -> None:
        super().__init__(
            f"The API server doesn't serve kind '{kind}' in '{group_version}'."
        )


class ObjectTimeoutError(Exception):
    """The object an assertion declares doesn't appear in the cluster."""

    def __init__(self, obj_name: str, kind: str) -> None:
        super().__init__(
            f"Timeout of {FLUX_MANAGED_OBJECTS_READY_TIMEOUT_SEC} sec reached while waiting "
            f"for object '{obj_name}' of kind '{kind}'"
        )


def resource_name(resource_list: dict, kind: str) -> str:
    """The plural resource name of `kind`, from the API server's discovery document of its
    group and version (`/api/v1` or `/apis/<group>/<version>`)."""
    for resource in resource_list.get("resources") or []:
        # subresources, such as `deployments/status`, have the kind of their parent
        if resource.get("kind") == kind and "/" not in resource["name"]:
            return resource["name"]
    raise KindNotServedError(kind, resource_list.get("groupVersion"))


def _validate(ass: dict, file: str) -> None:
    error = None
    if "metadata" not in ass or "kind" not in ass:
        error = AssertionFileError(file, "the 'metadata' and 'kind' properties")
    elif "name" not in ass["metadata"]:
        error = AssertionFileError(file, "'name' property in the 'metadata' section")
    if error is not None:
        logger.error(str(error))
        raise error


def _cluster_obj(api: pykube.HTTPClient, ass: dict) -> APIObject:
    if "namespace" in ass["metadata"]:
        cluster_obj: APIObject = NamespacedAPIObject(api, ass)
        cluster_obj.obj["metadata"]["namespace"] = ass["metadata"]["namespace"]
    else:
        cluster_obj = APIObject(api, ass)
    cluster_obj.kind = ass["kind"]
    cluster_obj.version = ass["apiVersion"]
    cluster_obj.endpoint = resource_name(
        api.resource_list(ass["apiVersion"]), ass["kind"]
    )
    return cluster_obj


def check_assertions(api: pykube.HTTPClient, assertions: dict[str, list[dict]]) -> int:
    """Check every assertion against the cluster `api` talks to; return how many there were."""
    checked = 0
    for file, assert_list in assertions.items():
        # I'm out names for "assertion" :P
        for ass in assert_list:
            _validate(ass, file)
            cluster_obj = _cluster_obj(api, ass)
            reload_obj_from_cluster(cluster_obj)
            assert_objects(ass, cluster_obj, file)
            checked += 1
    return checked


def reload_obj_from_cluster(cluster_obj: APIObject) -> None:
    for _ in range(FLUX_MANAGED_OBJECTS_READY_TIMEOUT_SEC):
        try:
            cluster_obj.reload()
        except pykube.http.HTTPError as err:
            # we might need to wait a bit for flux to create all the managed objects
            if err.code != 404:
                raise
            time.sleep(1)
        else:
            return
    raise ObjectTimeoutError(object_name(cluster_obj.obj["metadata"]), cluster_obj.kind)
