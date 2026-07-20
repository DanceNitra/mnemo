<!-- moved out of README.md to keep the landing page readable; content unchanged -->

## Framework integrations

mnemo drops into the major agent frameworks as their **native memory type**, so an agent gets value-ranked
recall plus **correction-integrity** (a corrected fact does not resurrect on a later read) without changing its
code. Each adapter lives under `mnemo.integrations.*` and is an opt-in extra — `import mnemo` stays
zero-dependency, and the framework is imported lazily only when you use its adapter.

| framework | mnemo class | install |
|---|---|---|
| [LangChain](#current-truth-retriever-for-langchain-mnemoretriever-1110) | `MnemoRetriever` | `pip install "agora-mnemo[langchain]"` |
| [OpenAI Agents SDK](#drop-in-memory-for-the-openai-agents-sdk-mnemosession-0620) | `MnemoSession` | `pip install "agora-mnemo[openai-agents]"` |
| [AutoGen](#current-truth-memory-for-autogen-mnemomemory-070) | `MnemoMemory` | `pip install "agora-mnemo[autogen]"` |
| [LangGraph / LangMem](#langgraph-store-with-queryable-history-mnemostore-071) | `MnemoStore` | `pip install "agora-mnemo[langgraph]"` · [runnable example](examples/07_langgraph_memory.py) |
| [LlamaIndex](#current-truth-long-term-memory-for-llamaindex-mnemomemoryblock-073) | `MnemoMemoryBlock` | `pip install "agora-mnemo[llamaindex]"` |
| [Google ADK](#persistent-memory-for-google-adk-mnemomemoryservice-074) | `MnemoMemoryService` | `pip install "agora-mnemo[google-adk]"` |
| [Pydantic AI](#memory-as-tools-for-pydantic-ai-mnemo_toolset-078) | `mnemo_toolset` | `pip install "agora-mnemo[pydantic-ai]"` |
| [CrewAI](#current-truth-storage-for-crewai-mnemostorage-1120) | `MnemoStorage` | `pip install "agora-mnemo[crewai]"` |

Details for each below.

### Current-truth retriever for LangChain: `MnemoRetriever` (1.11.0+)
`mnemo.integrations.langchain.MnemoRetriever` is a LangChain [`BaseRetriever`](https://python.langchain.com/docs/concepts/retrievers/)
— the same slot a vector-store retriever fills in a RAG chain — so you get value-ranked recall with
correction-integrity built in. `MnemoChatMessageHistory` (a `BaseChatMessageHistory`) persists a conversation
in the same store:

```python
from mnemo.integrations.langchain import MnemoRetriever
r = MnemoRetriever(path="mem.json", k=5)
r.add("the deploy channel is BLUE-9", key="deploy-channel")   # keyed write -> supersedable
r.add("the deploy channel is RED-2",  key="deploy-channel")   # supersedes BLUE-9
docs = r.invoke("what is the deploy channel?")                # returns RED-2, never BLUE-9
```

The differentiator vs a plain vector retriever: `invoke()` goes through mnemo's `recall()`, so a corrected
fact is never handed back into your chain/prompt (write facts with a supersession `key=` for that to engage;
plain text is stored append-only). Pass `embed=` for semantic recall, `extractor=` to auto-key free text.
Duck-typed on `langchain-core` (imported lazily); `import mnemo` stays zero-dependency.

### Drop-in memory for the OpenAI Agents SDK: `MnemoSession` (0.6.20+)
`mnemo.integrations.openai_agents.MnemoSession` is a persistent [`Session`](https://openai.github.io/openai-agents-python/sessions/)
backend — the same slot `SQLiteSession`/`RedisSession` fill — so agent conversations survive restarts:

```python
from agents import Agent, Runner
from mnemo.integrations.openai_agents import MnemoSession
session = MnemoSession("user-42", path="sessions.json")   # one store can hold many sessions
Runner.run_sync(agent, "hi", session=session)
```

It faithfully implements the protocol (`get_items`/`add_items`/`pop_item`/`clear_session`, verbatim items,
`limit`=latest-N, multi-session isolation) and needs **no dependency** — the SDK is matched structurally,
never imported. **Honest scope:** a `Session` is a verbatim turn log, so mnemo's supersession/echo_guard
(which key on *facts*) don't auto-clean replayed messages — for poison-resistant fact memory use mnemo's core
`remember(key=…)`/`recall()` alongside. What it adds *for free* over a plain SQLite session: **right-to-erasure**
of a user's turns with a signed, content-free deletion tombstone (`session.forget_subject()`), and
**tamper-evident** history (`store.verify_writes()` with receipts enabled). Receipt:
`mnemo/probes/mnemo_session_adapter_probe.py` (11/11). Adapters live under `mnemo.integrations` (opt-in extras).

### Current-truth memory for AutoGen: `MnemoMemory` (0.7.0+)
`mnemo.integrations.autogen.MnemoMemory` implements AutoGen's [`Memory`](https://microsoft.github.io/autogen/stable/user-guide/agentchat-user-guide/memory.html)
protocol (`add`/`query`/`update_context`/`clear`/`close`) — and here mnemo's value is not incidental. Unlike a
verbatim `Session`, AutoGen `Memory` retrieves facts and injects them before each turn, so **`recall()` hiding
superseded values means the agent is grounded on current-truth, not on a stale value a later correction
already retired**:

```python
from autogen_agentchat.agents import AssistantAgent
from mnemo.integrations.autogen import MnemoMemory
mem = MnemoMemory(path="mem.json")
agent = AssistantAgent("assistant", model_client=..., memory=[mem])
```

Pass a stable `key` (+ `object`) in a memory's `metadata` to drive deterministic supersession — a later
`key="user::timezone", object="PST"` retires an earlier `UTC`, and `update_context` then injects only `PST`.
Verified end-to-end against the real `autogen-core` (`mnemo/probes/mnemo_autogen_adapter_probe.py`, 7/7,
including "superseded value is not injected"). Zero-dependency core: AutoGen is imported lazily inside the
adapter, never by `import mnemo`.

### LangGraph store with queryable history: `MnemoStore` (0.7.1+)
`mnemo.integrations.langgraph.MnemoStore` is a LangGraph [`BaseStore`](https://langchain-ai.github.io/langgraph/reference/store/)
(faithful `put`/`get`/`search`/`delete`/`list_namespaces` + `batch`/`abatch`) — and since LangMem sits on any
BaseStore, one adapter reaches both. Same last-write-wins semantics as the built-in `InMemoryStore`, plus the
thing it throws away: **history**. A second `put` on a key overwrites the first in `InMemoryStore` and the old
value is gone; `MnemoStore` keeps it on mnemo's supersession ledger, so `store.history(namespace, key)` returns
every value the key has held — plus point-in-time reads, tamper-evident receipts, and `forget_subject` erasure.

```python
from mnemo.integrations.langgraph import MnemoStore
store = MnemoStore(path="lg.json")
store.put(("user","42"), "timezone", {"tz": "UTC"}); store.put(("user","42"), "timezone", {"tz": "PST"})
store.get(("user","42"), "timezone").value    # {"tz": "PST"}   (like InMemoryStore)
store.history(("user","42"), "timezone")       # [{"tz":"UTC"}, {"tz":"PST"}]   (mnemo-only)
```

Verified end-to-end against real `langgraph` (`mnemo/probes/mnemo_langgraph_adapter_probe.py`, 9/9, incl. the
"InMemoryStore has no history" contrast). Subclasses BaseStore, so importing this module imports LangGraph
(opt-in extra); `import mnemo` stays zero-dependency.

### Flag conflicts before you trust the write: `check_conflict()` (0.7.2+)
Practitioners keep landing on the same move: stop trusting the write path, check each new fact against what's
already stored, and flag conflicts *before* they commit. `check_conflict(text, key=…, object=…)` does that,
read-only and with no LLM: it returns the active memories the new fact would contradict — a value change on a
managed `key`, or a numeric/negation clash with a similar memory — so you can gate, review, or reject the write
before calling `remember()`.

```python
m.remember("the retry limit is 5 attempts")
m.check_conflict("the retry limit is 12 attempts")   # -> [{'kind': 'clash', ...}]  (numeric update)
m.check_conflict("the retry limit is 5 attempts")    # -> []  a duplicate is NOT a conflict
```

The signal is a value/negation clash, **not** cosine similarity — which is the whole point: a corrected value
is often *more* embedding-similar to the original than a rephrase (AUROC ~0.59 at telling them apart), so a
"too similar, must be a dup" gate silently swallows the contradiction. Pass `incompatible(a, b) -> bool` (e.g.
an LLM judge) to also catch a purely semantic contradiction with no numeric/negation marker. The mechanism is
textbook (a DB CHECK-constraint validate-on-write; TMS contradiction-on-assert, Doyle 1979) — here it's a
native, zero-dependency primitive. Also exposed as the `check_conflict` MCP tool. Receipt:
`mnemo/probes/check_conflict_probe.py` (8/8).

### Current-truth long-term memory for LlamaIndex: `MnemoMemoryBlock` (0.7.3+)
`mnemo.integrations.llamaindex.MnemoMemoryBlock` is a LlamaIndex long-term [`BaseMemoryBlock`](https://developers.llamaindex.ai/python/framework/module_guides/deploying/agents/memory/)
(async `_aget`/`_aput`), so it sits alongside the built-in Static/FactExtraction/Vector blocks on a `Memory`:

```python
from llama_index.core.memory import Memory
from mnemo.integrations.llamaindex import MnemoMemoryBlock
memory = Memory.from_defaults(session_id="s1", token_limit=40000,
                              memory_blocks=[MnemoMemoryBlock(name="mnemo", path="mem.json", k=5)])
```

Same differentiator as the AutoGen block: `_aget` retrieves through mnemo's `recall()`, which hides superseded
values, so once a fact is corrected (via a keyed write) the block never injects the stale value back into the
prompt. Verified end-to-end against real `llama-index-core`
(`mnemo/probes/mnemo_llamaindex_adapter_probe.py`, 4/4, incl. "corrected value not re-injected"). Subclasses
BaseMemoryBlock so importing it imports LlamaIndex (opt-in extra); `import mnemo` stays zero-dependency.

### Persistent memory for Google ADK: `MnemoMemoryService` (0.7.4+)
`mnemo.integrations.google_adk.MnemoMemoryService` is a drop-in Google ADK [`BaseMemoryService`](https://google.github.io/adk-docs/sessions/memory/)
(`add_session_to_memory` / `search_memory`), backed by a mnemo store so memory persists and retrieval is
value-ranked lexical+semantic instead of the built-in word-overlap:

```python
from google.adk.runners import Runner
from mnemo.integrations.google_adk import MnemoMemoryService
runner = Runner(agent=agent, app_name="app", session_service=...,
                memory_service=MnemoMemoryService(path="mem.json"))
```

Two honest extras over `InMemoryMemoryService`: `search_memory` goes through supersession-filtered `recall()`
(a corrected keyed fact is not returned), and `forget_subject_for(app_name, user_id, request_id=…)` gives
per-user right-to-erasure with a signed deletion tombstone. Verified end-to-end against real `google-adk`
2.4.0 (`mnemo/probes/mnemo_adk_adapter_probe.py`, 4/4, incl. per-user isolation, current-truth, and
accounted-for erasure). Opt-in extra; `import mnemo` stays zero-dependency.

### Memory-as-tools for Pydantic AI: `mnemo_toolset` (0.7.8+)
Pydantic AI ships no built-in persistent memory by design; the pattern (Hindsight's `hindsight-pydantic-ai`,
etc.) is to expose memory as agent tools. `mnemo.integrations.pydantic_ai.mnemo_toolset` returns a
[`FunctionToolset`](https://ai.pydantic.dev/toolsets/) the agent can call — `remember`, `recall`,
`check_conflict`, `forget`:

```python
from pydantic_ai import Agent
from mnemo.integrations.pydantic_ai import mnemo_toolset
agent = Agent("openai:gpt-4o-mini", toolsets=[mnemo_toolset(path="mem.json")])
```

The differentiators the built-in "give the model a scratchpad" pattern lacks: `recall` is
supersession-filtered (a corrected value stops surfacing, so the agent reads current-truth), and
`check_conflict` lets the agent test a fact for a contradiction with what is already stored BEFORE it commits
it. Pass `extractor=` so the tools auto-key free text (so both supersession and conflict-detection fire
without the model supplying a key). Verified end-to-end against real `pydantic-ai` 2.8.0 with `TestModel` (no
API key): the agent invokes all four tools, and current-truth / conflict / erasure all hold
(`mnemo/probes/mnemo_pydantic_ai_adapter_probe.py`). Importing this module imports Pydantic AI (opt-in
extra); `import mnemo` stays zero-dependency.

### Current-truth storage for CrewAI: `MnemoStorage` (1.12.0+)
CrewAI's memory (short-term, long-term, entity, external) delegates persistence to a `Storage` object with
`save(value, metadata)` / `search(query, limit, score_threshold)` / `reset()`. `mnemo.integrations.crewai.MnemoStorage`
is a drop-in Storage you hand to `ExternalMemory` (or any custom-storage slot), so a crew gets value-ranked
recall plus correction-integrity:

```python
from crewai import Crew
from crewai.memory.external.external_memory import ExternalMemory
from mnemo.integrations.crewai import MnemoStorage
crew = Crew(agents=[...], tasks=[...],
            external_memory=ExternalMemory(storage=MnemoStorage(path="crew_mem.json")))
```

The differentiator vs CrewAI's default RAG storage: `search()` retrieves through mnemo's `recall()`, which
hides **superseded** values — once a fact is corrected the stale value never returns into the crew's context.
For that to bite, carry a supersession key in the metadata (`storage.save(value, {"key": "user::tz"})`) or set
an `extractor=` so plain `save()` calls auto-key. Duck-typed: CrewAI is matched structurally and never
imported, so the zero-dependency core is untouched (`import mnemo` pulls nothing). Receipt:
`mnemo/probes/mnemo_crewai_adapter_probe.py` (6/6, incl. "corrected value not returned").

### Make the governance layer key itself over free text: the `extractor` hook (0.7.5+)
mnemo's supersession, `echo_guard`, `check_conflict`, and `forget_subject` all key on the `(key, object)` of a
fact. That's great when you write structured facts, but a conversation `Session` or a chat turn is free text
with no key, so supersession never fires on it. Plug an `extractor` once and every `remember()` derives the
key for you, so the whole governance layer composes over free text with no per-call keying:

```python
import re
m.extractor = lambda t: (m := re.match(r"(.+?) is (\w+)", t)) and (f"fact::{m[1].strip()}", m[2])
m.remember("server timezone is UTC")
m.remember("server timezone is PST")   # same derived key -> supersedes UTC, no manual key=
m.recall("server timezone")            # -> PST only
```

Your extractor can be a regex or an LLM you call and cache; it returns `(key, object)` or `None`. Explicit
`key=`/`object=` always win, and a broken extractor fails open (the write still lands as a plain append).
Honest limit: supersession is only as sound as your extractor, so a mis-derived key mis-supersedes (the same
risk as a wrong manual `key=`) — keep it deterministic and reviewable. This is a before-save hook (DB trigger
/ ORM before_save; textbook) packaged so the integrity primitives compose without threading keys everywhere.
Receipt: `mnemo/probes/extractor_hook_probe.py` (7/7).

The free-text framework adapters (OpenAI Agents `Session`, AutoGen `Memory`, LlamaIndex `BaseMemoryBlock`,
Google ADK `MemoryService`, Pydantic AI `mnemo_toolset`) accept `extractor=` and wire it into their store, so
plugging it once makes their current-truth recall fire automatically over conversation turns:

```python
mem = MnemoMemory(path="mem.json", extractor=my_extractor)   # AutoGen; same for the others
```

Verified against real `autogen-core` (`mnemo/probes/extractor_adapter_wireup_probe.py`): without the extractor
a corrected fact still leaks; with it, only the current value is recalled.

### Data minimization: `apply_retention(max_age_days)` (0.7.7+)
The age-bound companion to `capacity=` (size bound) and `forget_subject` (subject erasure), for the GDPR
storage-limitation principle: don't keep data longer than you need it. `apply_retention(days)` hard-deletes old
memories, but never the current value of a key and never a graduated `semantic`/`procedural` fact, those are
the live state, not stale accumulation. By default it drops old *superseded* values (minimizing retained PII,
which trades off `as_of()` history for those intervals, your call via `drop_superseded`) and old un-keyed
*episodic* turns. Run it directly, or on idle via `sleep(retention_days=90)`.

```python
m.apply_retention(max_age_days=90)     # or: m.sleep(retention_days=90)
```

Textbook (DB TTL / log retention), packaged as a native zero-dependency retention primitive. Receipt:
`mnemo/probes/retention_probe.py` (7/7, incl. "current keyed value and semantic facts are never expired").

### One-call write router with revert resolution: `route()` (0.7.9+)
"Go back to what we had before" names no value, so a value-keyed store has nothing to match and cosine has
nothing to grab — it is an unresolved pointer, not a similarity failure. `route(text)` ships the two-job split
for exactly this: a deterministic, ledger-aware intent tagger (assert / correct / revert / echo) in front, and
a fuzzy-version resolver behind it ("back / the way it was" → the predecessor via `revert()`; "the original /
what we started with" → the first version; a named old value → that version) — so a revert executes on the
version graph through the sanctioned reaffirm channel, and similarity never runs on a revert:

```python
m.route("the cache region is osaka", key="cache region", object="osaka")
m.route("correction: the cache region is now malmo", key="cache region", object="malmo")
m.route("go back to what we had for the cache region")   # no value named -> restores osaka from the ledger
```

Measured (`mnemo/probes/route_probe.py`, 148 rows): every *marked* class — corrections, value-obscuring
reverts, named reverts, original-restores, innocent temporal chatter — routes at 1.00 end-to-end under every
policy, with zero LLM (LLM taggers measured on the same rows add nothing: 1.00 on marked classes too). The
honest limit is measured rather than hidden: an UNMARKED restatement of a superseded value is ambiguous by
construction (a stale echo and a deliberate reaffirm can be byte-identical; LLMs land at ~coin-flip 0.35–0.55),
so `policy=` picks the failure mode — `safe` (default) never restores on an unmarked restatement
(echo-blocked 1.00 / legit-reaffirm-honored 0.00), `context` separates honest twins via the preceding turn
(1.00/1.00) but is forgeable (a forged change-aware context walks through it), `trusting` always restores
(0.00/1.00). The unforgeable separator is provenance — the explicit `revert()` channel or a revert marker —
not smarter classification. Also an MCP tool (`route`).

### Authorized revert channel: stop content from undoing a correction (0.7.10+)
A value-obscuring "go back to what we had" and a stale echo are byte-identical, so — as a sharp r/RAG thread
put it — the tie-break is an *authentication* problem, not an NLP one: it cannot come from the text, only from
an authority whose origin an attacker who can write text cannot author. Opt in and `route()`/`revert()` require
an out-of-band **capability** before they will restore a superseded value:

```python
from mnemo import Mnemo, new_receipt_keypair, sign_revert

# symmetric (zero extra deps): the harness holds a secret; the content path can't mint the capability
m = Mnemo(path="mem.json", revert_authority="a-harness-side-secret")
m.route("go back to what we had for the region", policy="trusting")   # -> action="authorization_required"
m.revert("region", capability=m.revert_capability("region"))          # principal path executes

# asymmetric (closes the residual: even a compromised on-box harness can't mint):
sk, pk = new_receipt_keypair()                 # private key stays OFF the box, store holds only pk
m = Mnemo(path="mem.json", revert_pubkey=pk)
cap = sign_revert(sk, m.revert_challenge("region"))   # only the off-box private key can produce this
m.revert("region", capability=cap)
```

With an authority set, a text-derived revert never executes — `route()` returns `authorization_required` and
the principal confirms out of band; `remember(reaffirm=True)` is gated the same way, so the raw primitive can't
bypass it. The capability binds to the key and the current record (`revert_challenge`), so a captured one can't
be replayed after the value moves or retargeted to another key. Textbook capability security (Dennis & Van Horn
1966) / confused-deputy fix (Hardy 1988), packaged onto the memory store's revert path. Honest boundary: this
closes the content→restore path (and, in asymmetric mode, the on-box-harness→restore path); it does not stop a
stolen private key or authenticate a human. Adversarial receipt: `mnemo/probes/authorized_revert_probe.py`
(11/11: content blocked, harness-can't-mint, replay/retarget/forgery refused, principal path works).

