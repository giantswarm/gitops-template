"""Comparing an assertion with the object in the cluster."""

import logging

import pytest
from deepdiff import DeepDiff
from deepdiff.helper import NotPresent
from deepdiff.model import DiffLevel
from pykube.objects import APIObject

logger = logging.getLogger(__name__)


def object_name(meta: dict) -> str:
    """`namespace/name` of a namespaced object, `name` of any other."""
    return (
        meta["namespace"] + "/" + meta["name"] if "namespace" in meta else meta["name"]
    )


def normalize_whitespace(value: object) -> object:
    """Return `value` with trailing whitespace removed from every line of every string in it.

    Multi-line strings, such as the `values` of a ConfigMap, are compared as text. Whether an
    assertion file writes them as `|` or `|-`, or a line ends in a stray space, says nothing
    about the values, so those differences are dropped before the comparison. Every other
    difference in the text, including indentation, still fails it.
    """
    if isinstance(value, str):
        return "\n".join(line.rstrip() for line in value.splitlines())
    if isinstance(value, dict):
        return {k: normalize_whitespace(v) for k, v in value.items()}
    if isinstance(value, list):
        return [normalize_whitespace(v) for v in value]
    return value


def _order_matters_not(level: DiffLevel) -> bool:
    return "valuesFrom" not in level.path()


def _fail_different(cluster_obj: APIObject, file: str, diff: DeepDiff) -> None:
    msg = (
        f"Object '{object_name(cluster_obj.obj['metadata'])}' of kind "
        f"'{cluster_obj.obj['kind']}' is different than expectation in file '{file}'."
    )
    logger.error(msg)
    logger.error(diff)
    pytest.fail(msg)


def assert_objects(ass: dict, cluster_obj: APIObject, file: str) -> None:
    for key in cluster_obj.obj:
        if key not in ass:
            continue
        diff = DeepDiff(
            normalize_whitespace(ass[key]),
            normalize_whitespace(cluster_obj.obj[key]),
            # List order doesn't matter, except for `valuesFrom`: Helm merges
            # values in that order, so a reordered list changes the result.
            ignore_order=False,
            ignore_order_func=_order_matters_not,
            threshold_to_diff_deeper=0,
        )
        # we have no difference between the expectation and the real object
        if len(diff) == 0:
            continue
        # The only difference that we allow for is when the real object has some attributes
        #  that the expectation doesn't have. This means that if a diff of a kind different
        #  from 'dictionary_item_added' is detected, it's an error.
        if len(diff) > 1 or "dictionary_item_added" not in diff.tree:
            _fail_different(cluster_obj, file, diff)
        # Even if we only have 'dictionary_item_added', it has to show that added stuff is
        #  only on the real object side. In other words, we check that all the attributes
        #  given in the expectation are present in the real object.
        missing = [
            d.path()
            for d in diff.tree["dictionary_item_added"]
            if not isinstance(d.t1, NotPresent)
        ]
        if missing:
            msg = f"The object in the cluster doesn't have {missing}."
            raise AssertionError(msg)
