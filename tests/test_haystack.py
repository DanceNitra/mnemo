# -*- coding: utf-8 -*-
"""`InspeximusDocumentStore` — a Haystack DocumentStore, tested where it is easy to get wrong.

Haystack's DocumentStore has exact, checkable semantics (duplicate policies, filter matching, delete on
an unknown id), and `InMemoryDocumentStore` is the reference. These tests plus `haystack_audit.py` are
the whole safety net. Skipped when haystack-ai is not installed, since it is an optional extra.
"""
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

pytest.importorskip("haystack", reason="haystack-ai is an optional extra")

from haystack.dataclasses.document import Document                  # noqa: E402
from haystack.document_stores.errors import DuplicateDocumentError  # noqa: E402
from haystack.document_stores.types import DuplicatePolicy          # noqa: E402

from inspeximus.integrations.haystack import InspeximusDocumentStore   # noqa: E402


def store(tmp_path, name="d.json"):
    return InspeximusDocumentStore(path=str(tmp_path / name))


def test_write_returns_count_and_documents_round_trip(tmp_path):
    s = store(tmp_path)
    n = s.write_documents([Document(id="1", content="hello", meta={"k": "v"})])
    assert n == 1 and s.count_documents() == 1
    got = s.filter_documents()[0]
    assert got.id == "1" and got.content == "hello" and got.meta == {"k": "v"}


def test_default_policy_fails_on_a_duplicate_id(tmp_path):
    s = store(tmp_path)
    s.write_documents([Document(id="1", content="a")])
    with pytest.raises(DuplicateDocumentError):
        s.write_documents([Document(id="1", content="b")])          # NONE -> the store's default (FAIL)
    assert s.filter_documents()[0].content == "a"


def test_skip_keeps_the_original(tmp_path):
    s = store(tmp_path)
    s.write_documents([Document(id="1", content="original")])
    n = s.write_documents([Document(id="1", content="new")], policy=DuplicatePolicy.SKIP)
    assert n == 0 and s.filter_documents()[0].content == "original" and s.count_documents() == 1


def test_overwrite_replaces_and_does_not_grow_the_count(tmp_path):
    s = store(tmp_path)
    s.write_documents([Document(id="1", content="original")])
    n = s.write_documents([Document(id="1", content="new")], policy=DuplicatePolicy.OVERWRITE)
    assert n == 1 and s.filter_documents()[0].content == "new" and s.count_documents() == 1


def test_filters_use_haystack_semantics(tmp_path):
    s = store(tmp_path)
    s.write_documents([Document(id="1", content="a", meta={"kind": "invoice"}),
                       Document(id="2", content="b", meta={"kind": "person"})])
    got = s.filter_documents({"field": "meta.kind", "operator": "==", "value": "invoice"})
    assert [d.id for d in got] == ["1"]
    assert s.filter_documents({"field": "meta.kind", "operator": "==", "value": "nope"}) == []


def test_deleting_an_unknown_id_is_a_no_op(tmp_path):
    s = store(tmp_path)
    s.write_documents([Document(id="1", content="a")])
    s.delete_documents(["does-not-exist"])
    assert s.count_documents() == 1
    s.delete_documents(["1"])
    assert s.count_documents() == 0


def test_survives_a_reopen(tmp_path):
    store(tmp_path).write_documents([Document(id="1", content="the spare key is under the mat")])
    reopened = store(tmp_path)
    assert reopened.count_documents() == 1
    assert reopened.filter_documents()[0].content == "the spare key is under the mat"


def test_delete_removes_the_value_from_disk(tmp_path):
    s = store(tmp_path)
    s.write_documents([Document(id="9", content="IBAN SK9911000000002612345678")])
    s.erase_documents(["9"], request_id="gdpr-1")
    s.store._save(force=True)
    blob = " ".join(p.read_text(encoding="utf-8", errors="replace")
                    for p in tmp_path.rglob("*") if p.is_file())
    assert "2612345678" not in blob
    assert s.count_documents() == 0


def test_serialization_round_trips(tmp_path):
    s = store(tmp_path)
    s.write_documents([Document(id="1", content="x")])
    data = s.to_dict()
    assert data["type"].endswith("InspeximusDocumentStore")
    s2 = InspeximusDocumentStore.from_dict(data)
    assert s2.count_documents() == 1
