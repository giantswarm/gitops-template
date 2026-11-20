"""Checks of how store_refs finds the stores an object refers to; they need no cluster."""

from store_refs import store_kinds


def test_store_kinds_of_an_external_secret() -> None:
    external_secret = {
        "kind": "ExternalSecret",
        "spec": {
            "secretStoreRef": {"kind": "ClusterSecretStore", "name": "a"},
            "data": [
                {"secretKey": "b", "sourceRef": {"storeRef": {"name": "b"}}},
                {"secretKey": "c", "remoteRef": {"key": "c"}},
            ],
            "dataFrom": [
                {
                    "sourceRef": {
                        "storeRef": {"kind": "ClusterSecretStore", "name": "d"}
                    }
                },
                {"sourceRef": {"generatorRef": {"kind": "Password", "name": "e"}}},
            ],
        },
    }
    # a reference without a kind is to a SecretStore, ESO's default
    assert store_kinds(external_secret) == [
        "ClusterSecretStore",
        "SecretStore",
        "ClusterSecretStore",
    ]


def test_store_kinds_of_a_push_secret() -> None:
    push_secret = {
        "kind": "PushSecret",
        "spec": {
            "secretStoreRefs": [
                {"kind": "SecretStore", "name": "a"},
                {"kind": "ClusterSecretStore", "name": "b"},
            ]
        },
    }
    assert store_kinds(push_secret) == ["SecretStore", "ClusterSecretStore"]


def test_store_kinds_of_other_objects() -> None:
    assert store_kinds({"kind": "ConfigMap", "data": {}}) == []
