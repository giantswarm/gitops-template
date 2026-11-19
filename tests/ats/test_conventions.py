from conventions import merged


def test_merged_merges_maps_and_keeps_the_original() -> None:
    obj: dict = {"metadata": {"labels": {"a": "1"}, "name": "x"}, "spec": {"b": 1}}
    fix = {"metadata": {"labels": {"c": "2"}}, "spec": {"b": 2}}

    assert merged(obj, fix) == {
        "metadata": {"labels": {"a": "1", "c": "2"}, "name": "x"},
        "spec": {"b": 2},
    }
    assert obj["metadata"]["labels"] == {"a": "1"}


def test_merged_adds_missing_maps() -> None:
    assert merged({"spec": {}}, {"metadata": {"annotations": {"a": "1"}}}) == {
        "spec": {},
        "metadata": {"annotations": {"a": "1"}},
    }
