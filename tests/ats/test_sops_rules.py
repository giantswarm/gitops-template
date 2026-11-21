"""The `.sops.yaml` rule that encrypts the workload clusters' SOPS keys in an organisation's
namespace/secrets with the management cluster's master key comes before any other rule for that
directory, such as the organisation key's rule docs/how-to/sops.md appends. Needs no cluster.
"""

import re
from pathlib import Path

import yaml

REPO_DIR = Path(__file__).resolve().parents[2]
ORG_SECRETS = "management-clusters/MC_NAME/organizations/ORG_NAME/namespace/secrets"
# the rule docs/how-to/sops.md appends for an organisation's own key
ORGANIZATION_KEY_RULE = {
    "encrypted_regex": "^(data|stringData)$",
    "path_regex": f"{ORG_SECRETS}/.*\\.enc\\.yaml",
    "pgp": "ORGANIZATION KEY",
}
KEY_FILE = re.compile(r".*\.(gpg|age)key\.enc\.yaml$")


def first_rule(rules: list[dict], path: str) -> dict | None:
    """The rule sops encrypts `path` with: the first whose `path_regex` matches it."""
    return next((r for r in rules if re.search(r["path_regex"], path)), None)


def test_first_rule() -> None:
    rules = [{"path_regex": "a/.*"}, {"path_regex": "a/b"}]
    assert first_rule(rules, "a/b") == rules[0]
    assert first_rule(rules, "c") is None


def _rules() -> list[dict]:
    with (REPO_DIR / ".sops.yaml").open() as f:
        return yaml.safe_load(f)["creation_rules"]


def _keys() -> list[str]:
    with (REPO_DIR / ORG_SECRETS / "kustomization.yaml").open() as f:
        resources = yaml.safe_load(f)["resources"]
    return [f"{ORG_SECRETS}/{r}" for r in resources if KEY_FILE.match(r)]


def test_cluster_keys_are_encrypted_with_the_master_key() -> None:
    rules = _rules()
    master = first_rule(
        rules, "management-clusters/MC_NAME/secrets/MC_NAME.gpgkey.enc.yaml"
    )
    assert master is not None
    keys = _keys()
    assert keys, f"no SOPS key in {ORG_SECRETS}"
    for rules_in_use in (rules, [*rules, ORGANIZATION_KEY_RULE]):
        assert {k: (first_rule(rules_in_use, k) or {}).get("pgp") for k in keys} == {
            k: master["pgp"] for k in keys
        }


def test_the_organisation_key_encrypts_the_organisation_secrets() -> None:
    # the master key's rule leaves the organisation's other Secrets to the organisation's key
    rules = [*_rules(), ORGANIZATION_KEY_RULE]
    assert first_rule(rules, f"{ORG_SECRETS}/secret.enc.yaml") == ORGANIZATION_KEY_RULE
