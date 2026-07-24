"""`ComplianceMixin` on every class-based framework adapter — the AI-Act evidence comes off the SAME object
the agent writes memory to, in whichever framework the caller already uses.

The first test is a REGRESSION GUARD, not a formality. Pydantic collects annotations from plain mixin bases
too, so a `store: Any` declared on the mixin is promoted to a model FIELD on adapters that subclass a
pydantic model (LangChain `BaseRetriever`, LlamaIndex `BaseMemoryBlock`) — and it then SHADOWS an adapter
that exposes `store` as a `@property`, so `self.store` returns the property object and every compliance call
fails on a non-store. Measured before the mixin was rolled out; the fix is that the mixin declares no
annotations at all.
"""
import os, sys, tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from inspeximus import Inspeximus
from inspeximus.integrations.governance import ComplianceMixin


def _store():
    return Inspeximus(path=os.path.join(tempfile.mkdtemp(), "m.json"), receipts=True)


def test_mixin_never_shadows_a_store_property_on_a_pydantic_adapter():
    pydantic = pytest.importorskip("pydantic")

    class Block(pydantic.BaseModel, ComplianceMixin):
        k: int = 5

        @property
        def store(self):
            return self._real

    assert "store" not in Block.model_fields, \
        "ComplianceMixin must declare no annotations, or pydantic turns `store` into a field"

    b = Block()
    object.__setattr__(b, "_real", _store())
    assert isinstance(b.store, Inspeximus)
    assert b.compliance_check()["ok"] is True


def _assert_compliance_surface(adapter, store):
    """Every mixed-in adapter must yield the four evidence operations off its own object."""
    assert isinstance(adapter, ComplianceMixin)
    assert adapter.store is store

    report = adapter.compliance_report()
    assert report["kind"] and report["controls"]
    assert adapter.compliance_check()["ok"] is True
    assert adapter.retention(max_age_days=3650)["erased"] == 0          # dry-run by default
    assert type(adapter).verify_audit_bundle(adapter.audit_bundle())["ok"] is True


def test_langchain_retriever_and_chat_history():
    pytest.importorskip("langchain_core")
    from inspeximus.integrations.langchain import InspeximusRetriever, InspeximusChatMessageHistory
    s = _store()
    s.remember("billing uses oauth2", key="billing::auth", object="oauth2")
    _assert_compliance_surface(InspeximusRetriever(store=s), s)
    _assert_compliance_surface(InspeximusChatMessageHistory("sess-1", store=s), s)


def test_langgraph_store():
    pytest.importorskip("langgraph")
    from inspeximus.integrations.langgraph import InspeximusStore
    s = _store()
    _assert_compliance_surface(InspeximusStore(store=s), s)


def test_llamaindex_memory_block():
    pytest.importorskip("llama_index.core")
    from inspeximus.integrations.llamaindex import InspeximusMemoryBlock
    s = _store()
    _assert_compliance_surface(InspeximusMemoryBlock(store=s), s)


def test_autogen_memory():
    from inspeximus.integrations.autogen import InspeximusMemory      # imports no autogen package
    s = _store()
    _assert_compliance_surface(InspeximusMemory(store=s), s)


def test_openai_agents_session():
    from inspeximus.integrations.openai_agents import InspeximusSession   # matched structurally, no import
    s = _store()
    _assert_compliance_surface(InspeximusSession("sess-1", store=s), s)


def test_crewai_storage():
    pytest.importorskip("crewai")
    from inspeximus.integrations.crewai import InspeximusStorage
    s = _store()
    _assert_compliance_surface(InspeximusStorage(store=s), s)


def test_haystack_document_store():
    pytest.importorskip("haystack")
    from inspeximus.integrations.haystack import InspeximusDocumentStore
    s = _store()
    _assert_compliance_surface(InspeximusDocumentStore(store=s), s)


def test_google_adk_memory_service():
    pytest.importorskip("google.adk")
    from inspeximus.integrations.google_adk import InspeximusMemoryService
    s = _store()
    _assert_compliance_surface(InspeximusMemoryService(store=s), s)


def test_pydantic_ai_is_deliberately_not_covered():
    """`pydantic_ai` exposes a FUNCTION toolset, not a class, so there is no object to mix into — the
    caller reaches the evidence on the store they passed in. Pinned so the gap stays deliberate."""
    import inspeximus.integrations.pydantic_ai as mod
    assert not any(isinstance(v, type) and issubclass(v, ComplianceMixin)
                   for v in vars(mod).values())
    assert hasattr(mod, "inspeximus_toolset")
