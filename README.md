<div align="center">

<img src="https://raw.githubusercontent.com/DanceNitra/mnemo/main/assets_readme/hero_banner.png" alt="mnemo — a glowing digital memory layer resting on a robust machined-steel base" width="800">

# agora-mnemo

*Mnemosyne — the self-correcting memory layer for AI agents.*

*Correct a fact once and it stays corrected: mnemo serves the new value and refuses to let the old one creep
back — deterministically, with no LLM on the write path. Extracted from an autonomous research OS that has run
it daily over 10,000 notes.*

`pip install agora-mnemo` → `import mnemo` · [PyPI](https://pypi.org/project/agora-mnemo/) · [Hugging Face](https://huggingface.co/Danchi17/mnemo) · [DOI](https://doi.org/10.5281/zenodo.21128549) · [Homepage](https://dancenitra.github.io/mnemo/) · MIT · v1.24.1

[![Star on GitHub](https://img.shields.io/github/stars/DanceNitra/mnemo?style=social)](https://github.com/DanceNitra/mnemo)

*If mnemo's saved you some time, a ⭐ would mean a lot — it's how other people find it. Thank you!*

<img src="assets_readme/correction_demo.svg" alt="A fact is corrected; later the old value is restated, yet recall still serves the correction — the restatement lands retired via echo_guard" width="720">

Built by **[Rastislav Drahoš](https://github.com/DanceNitra)** — extracted from [Agora](https://github.com/DanceNitra/agora), an autonomous research OS that runs it daily.

</div>

---

## Every claim below is checked by a script you can run

```bash
python claims_audit.py          # downloads the published wheel from PyPI and audits THAT
```

It fetches the released artifact, prints its sha256, and runs each claim on it — never on the working
tree. The write-path claim is enforced rather than asserted: sockets are disabled for the duration, so a
write that reached for a model would fail the check instead of passing it quietly. Claims about *other*
systems are listed separately and marked untestable here; verifying those means running those systems,
so they are never counted as passing.

```
auditing : agora_mnemo-1.24.1-py3-none-any.whl
13 passed · 0 FAILED · 0 skipped · 5 not testable here
```

This exists because the exercise pays for itself: the first time we ran a README sentence against the
published wheel, it failed. Erasure did delete the record and scrub the bytes, but plain `forget()` left
no receipt, so the store's own `verify_writes()` reported the deletion as out-of-band — flagging a
legitimate API call as tampering. Fixed in 1.24.0, with a regression probe, and the audit now covers it.

## Why mnemo — the one thing no other agent memory does

Every mainstream agent-memory library puts an **LLM on the write path**: it calls a model to extract, summarize,
or build a graph *every time you store something*. mem0 runs LLM fact-extraction on `add()` by default; Zep/Graphiti
runs LLM entity/edge extraction on every `add_episode()`. That one choice is why their stored state is
**non-deterministic**, costs a model call per write, and can silently drop a fact.

**mnemo has no LLM on the write path.** Storing a fact is a deterministic, zero-cost operation — and *that* is
what makes three things possible the mainstream libraries don't offer:

> **What that costs, measured on someone else's benchmark.** On the [MemOps](https://github.com/MemTensor/MemOps)
> long-context scenarios (24 scenarios, ~50 sessions each), ingesting one scenario through mem0's default
> pipeline took **600–730 s of LLM extraction**; mnemo's write path made **zero model calls**. Read the rest
> before quoting that: on the same run, answer accuracy was **statistically indistinguishable** — mnemo 0.593,
> a naive keep-all store 0.592, mem0 0.544, with every bootstrap CI crossing zero. So the honest claim is *same
> answers, no write-time model cost*, not *better answers*. About 2% of mem0's extraction calls failed to parse
> and those memories are missing from its store, which handicaps it slightly. MemOps is published by MemTensor,
> who also make a competing system. Harness, pre-registration and the full result:
> [agora/agora_output/lab/memops](https://github.com/DanceNitra/agora/tree/main/agora_output/lab/memops).

- **Corrections that stick.** Write a new value for a key and it *supersedes* the old one; `echo_guard` blocks a
  later restatement of the retired value from resurfacing. No config, no model call. Honest scope: the guard
  engages on **keyed or extractor-derived** assertions (the shipped extractors derive the key from raw text);
  a free-text write that nothing keys is stored as an independent record and ranks on its own.
- **Revert on command.** `m.revert(key)` rolls a corrected fact back to its predecessor. Of the leading systems
  we checked — mem0, Zep/Graphiti, Letta, Cognee, Memobase, MemoryScope, LangMem, txtai — **none exposes a
  revert-to-predecessor command** (mem0's `history()` is a read-only log; Graphiti invalidates but never
  un-invalidates; Letta has no undo).
- **Deletes the value, not just the pointer.** `forget_subject` removes the value from mnemo's records (subject
  + its `derived_from` lineage) and leaves a **content-free**, tamper-evident signed receipt — so what remains is
  a proof-of-deletion, not the data. Since **1.24.0 every deletion path leaves that receipt**, including plain
  `forget(ids=…, where=…)`; before that only `forget_subject` and `forget_pii` did, so a record removed with
  `forget()` was erased correctly but unaccounted-for, and `verify_writes()` reported it as an out-of-band
  deletion — the store flagging its own legitimate API call as tampering. Pass `request_id=` / `basis=` to
  `forget()` to bind the reason into the receipt's committed hash. Most agent-memory libraries instead *retain the deleted value* by design:
  mem0 keeps it in its SQLite history table (a full `reset()` purges it); Graphiti stamps the old edge
  `invalid_at` and keeps it. For **secure erasure at rest** (against raw-disk/backup forensics — which a plaintext
  store of ANY library, mnemo included, does not give you) use an encrypted store + `shred()` (NIST SP 800-88
  crypto-erasure: destroy the key and every at-rest copy dies).

| | LLM on write | corrections stick | revert to predecessor | deleted value retained? |
|---|---|---|---|---|
| **mnemo** | **no — deterministic** | ✅ supersession + echo_guard | ✅ `revert(key)` | ✅ no — value scrubbed, content-free receipt (+ `shred()` for at-rest) |
| mem0 | yes (by default) | LLM decides ADD/UPDATE | ✗ history is read-only | ✗ kept in the history table by design |
| Zep / Graphiti | yes | temporal invalidation | ✗ no un-invalidate | ✗ invalidated edge retained |
| Letta / MemGPT | yes | LLM rewrites the block | ✗ no undo | ✗ |

*(Every competitor cell was checked against that project's current source/docs — see [the integrity
benchmark](mnemo/probes/INTEGRITY_BENCHMARK.md), which also names each system that shares an individual property.
Cryptographic deletion receipts do exist in purpose-built provenance systems like Engram and Heartwood; the claim
here is scoped to mainstream agent-memory libraries.)*

The mechanism underneath — **no LLM on the write path** — is the part a competitor can't copy without abandoning
its extraction design. That is the moat.

## And it doesn't cost you recall

Integrity would be hollow if mnemo retrieved worse. It doesn't. On the standard **LOCOMO** benchmark (full set,
n=1536), with the built-in tuned recipe (a semantic embedder + hybrid recall + a soft speaker prefilter),
mnemo's **retrieval-recall@25 is 0.78** (a supporting turn is retrieved) / **0.65** (all supporting turns) —
top-tier, and measured the honest way: **LLM-free and reproducible**, with no LLM judge to inflate it. Run it:
`python mnemo/probes/retrieval_recall_locomo.py`.

*(We deliberately don't headline an LLM-judged end-to-end QA score. Those are judge-dependent and not comparable
across harnesses — mem0 reports 66.9% and Zep 71.2% under their own judges — so a cross-system "we win" claim
would need running them through this harness, which we haven't done. What we publish is our own reproducible
number.)*

**Every number in this README traces to a runnable probe in [`mnemo/probes/`](mnemo/probes/). Nothing is
asserted that you can't reproduce.**

## Quickstart (2 minutes)

```bash
pip install agora-mnemo          # zero required dependencies
```

```python
from mnemo import Mnemo

m = Mnemo("memory.json")                      # persists to JSON; drop the path for pure in-memory
m.remember("The API rate limit is 1000 req/min", key="api::rate_limit")
m.recall("what is the rate limit")            # -> ["The API rate limit is 1000 req/min"]

# Correction is first-class: writing the same key supersedes the old value — no config, no LLM call.
m.remember("The API rate limit is 5000 req/min", key="api::rate_limit")
m.recall("rate limit")                        # -> ["...5000 req/min"]  (only the current value)
m.revert("api::rate_limit")                   # roll back to the predecessor, on command
m.history("api::rate_limit")                  # full audit trail, oldest to newest
```

New in **1.11.0**: ready-made write-path extractors (`regex_extractor`, deterministic; `make_llm_extractor`,
opt-in) that can derive a key from text without an explicit one, and a first-class **LangChain**
integration (`from mnemo.integrations.langchain import MnemoRetriever` — a retriever that never hands a
superseded fact back to your chain). `pip install "agora-mnemo[langchain]"`.

**Honest scope of `regex_extractor` (measured 2026-07-20, corrected from an earlier overclaim).** It keys
clean declarative statements — "My ZIP code is 94107", "Alice's email is …", "The API rate limit is 500 rps".
It does **not** reliably key natural conversational prose: measured on an external dialogue corpus (the
MemOps dataset, arXiv 2607.12893) it derived a key for 5.2% of sentences (1,037 of 19,851 across six transcripts), and — the part that matters —
it does not hold a *stable* key across a real correction chain, because "my official title … **was** Junior
Data Analyst" and "**so my current title is** Data Analyst" yield different keys that never meet. On raw
chat transcripts, supersession therefore mostly does not fire and mnemo behaves as a verbatim store.
**If you control the write, pass `key=` explicitly** — that is the path where corrections-stick, `revert`
and the erasure guarantees actually hold. (This README previously said the extractors exist "so supersession
engages over free text"; that was too strong. See CHANGELOG 1.23.1, which also fixes a real data-loss bug
found in the same measurement.)

## Give your agent this memory in 60 seconds (MCP)

Using **Claude Code**? One command registers mnemo as your agent's memory ([uv](https://docs.astral.sh/uv/) fetches it, nothing else to install):

```bash
claude mcp add mnemo -e MNEMO_PATH=~/.mnemo_memory.json -- uvx --from "agora-mnemo[mcp]" mnemo-mcp
```

**Claude Desktop / Cursor / any MCP client** — add to your MCP config (`claude_desktop_config.json`, `.cursor/mcp.json`, …):

```json
{
  "mcpServers": {
    "mnemo": {
      "command": "uvx",
      "args": ["--from", "agora-mnemo[mcp]", "mnemo-mcp"],
      "env": { "MNEMO_PATH": "~/.mnemo_memory.json" }
    }
  }
}
```

Your agent now has `remember` / `recall` / `history` — and corrections that stick: when a fact is superseded,
recall serves the current value, a restated stale value can't resurrect it (`echo_guard`), and `revert` /
`route` undo a correction on an unmarked "go back". `recall` returns compact records by default (drops internal
fields; `get(id)` / `neighbors(id)` for detail on demand). Eighteen tools total; [details below](#use-it-as-an-mcp-server-any-claude--cursor--agent-client).

**Jump to:** [Correction (measured)](#correction-is-a-first-class-operation-measured-across-systems) ·
[Governance & erasure](#governance-erasure--audit) · [Org-wide erasure receipt](#org-wide-erasure-receipt-one-signed-manifest-across-every-store-you-register) · [Install](#install) ·
[MCP server](#use-it-as-an-mcp-server-any-claude--cursor--agent-client) ·
[Shell CLI](#use-it-from-the-shell-the-mnemo-cli-1124) ·
[Framework integrations](#framework-integrations) ·
[The four operations](#the-four-operations) · [Five rules](#five-rules-it-wont-break-each-one-cost-us-to-learn) ·
[Provenance & receipts](#provenance--why-these-rules-with-receipts) · [Threat model](#threat-model--layered-defense-adversarial-memory-integrity)

## Use

The full API reference — every method, argument and return shape, with runnable examples —
lives in **[docs/API.md](docs/API.md)**. The four operations you actually need are further down this
page; everything else is there when you need it.
## Framework integrations

Adapters for LangGraph, CrewAI, LangChain, LlamaIndex, AutoGen and the rest,
with copy-paste snippets: **[docs/INTEGRATIONS.md](docs/INTEGRATIONS.md)**.
## Use it as an MCP server (any Claude / Cursor / agent client)

`mnemo` ships an [MCP](https://modelcontextprotocol.io) stdio server so any MCP-compatible agent can
use it as long-term memory — `remember` (with a per-type decay prior), value-ranked `recall`,
`consolidate`, `consolidate_clusters`, `contradictions`, `value_by_cohort`, `forget` (verified erasure).
Correction is first-class over MCP too: `revert` / `route` undo a correction on an unmarked "go back", and the
read-path review layer `observe` / `reopened` / `resolve_reopened` (1.9.2–1.9.5) reopens a settled record for
steward review on a *corroborated* contradiction (a lone restatement stays an echo, never an auto-change).
The MCP `remember` exposes `key` (deterministic supersession) plus `object` / `reaffirm`, and the server
runs with **`echo_guard` ON by default** (0.6.11) so a corrected fact stays corrected even if the old value
is re-stated later — the failure mode a plain keyed/add-based store shows on RAMR's ECHO-RESISTANCE
(keyed-without-guard 0.00, a real add-based system 0.57, guard 1.00). Set `MNEMO_ECHO_GUARD=0` to disable.
Install and run the server straight from PyPI (the `[mcp]` extra pulls the MCP SDK; the core library stays
dependency-free):

```bash
pip install "agora-mnemo[mcp]"     # the library + the MCP server SDK
mnemo-mcp                          # speaks MCP over stdio
```

Register it with any MCP client — Claude Code (`.mcp.json`), Claude Desktop
(`claude_desktop_config.json`), Cursor, Windsurf, Codex, Gemini. Zero-setup with `uvx` (installs on first run):

```json
{
  "mcpServers": {
    "mnemo": {
      "command": "uvx",
      "args": ["--from", "agora-mnemo[mcp]", "mnemo-mcp"],
      "env": { "MNEMO_PATH": "./mnemo_memory.json" }
    }
  }
}
```

Or, after `pip install "agora-mnemo[mcp]"`, with the console script directly:

```json
{
  "mcpServers": {
    "mnemo": {
      "command": "mnemo-mcp",
      "env": { "MNEMO_PATH": "./mnemo_memory.json" }
    }
  }
}
```

For **semantic** recall, point it at any OpenAI-compatible embeddings endpoint via
`MNEMO_EMBED_URL` / `MNEMO_EMBED_MODEL` / `MNEMO_EMBED_KEY`; with none set it uses the lexical
fallback. The agent then calls `recall(query)` before reasoning and `remember(fact)` as it learns —
its memory is value-ranked and append-only, not a recency buffer. If `MNEMO_EMBED_MODEL` contains
`nomic` (nomic-embed-text is asymmetric — see its model card; like E5's `passage:`/`query:`), mnemo auto-applies its
required task prefixes — `search_document: ` for stored text, `search_query: ` for the query (opt out with
`MNEMO_NOMIC_PREFIX=0`). Omitting them was simply using the model wrong; with prefixes on, our own
reinforcement-controlled re-measure lands recall_any@1 at 0.397 on one LoCoMo config (n=1536, deterministic
retrieval-recall — an upper bound, not end-to-end QA; a self-comparison, not a cross-system claim; the earlier
0.19→0.29 delta was contaminated by a since-fixed recall-reinforcement confound — see the 1.15.0 CHANGELOG correction). In the library, pass a separate `Mnemo(embed=…, embed_query=…)` for any
asymmetric embedder. If you use `persist_vectors=True`, also pass `Mnemo(embed_id="…")` (a recipe fingerprint): when
it changes, mnemo re-embeds the persisted vectors once so a new-space query can't silently mis-match old vectors.

**Compact recall + progressive disclosure (1.14.0).** Over MCP, `recall` returns a compact projection — `{id,
text, score, value, tags}` — dropping internal bookkeeping fields the model doesn't reason over, and `k` is
hard-capped (`MNEMO_MAX_K`, default 50), so a recall drops cheaply into the prompt. **Full text is kept by
default**; snippet truncation is **opt-in** (`snippet_chars>0`) — off by default on purpose, since truncating a
hit could cut off a corrected value past the boundary and defeat the echo-guard. Pull detail on demand: `get(id)`
returns one full record, `neighbors(id, k)` a bounded local expansion (excludes self). `recall(full=True)` returns
complete records. `token_report(query, k)` is a **deterministic, no-LLM** (~chars/4) payload-size estimate
comparing the compact projection to the full records for the **same k hits** — an apples-to-apples sizing aid, not
a whole-store comparison and not a measured token saving. None of this is novel — it's standard MCP/RAG
context-economy practice (progressive disclosure / small-to-big retrieval); mnemo never emitted embedding vectors.

## The four operations

| op | what it does |
|---|---|
| `remember(text, tags, value, mtype, key)` | **append-only** raw capture, absolute UTC time, never edited; `mtype` ∈ {episodic, semantic, procedural} sets the **decay prior** (events fade fast, durable facts slow, rules barely). Optional `key` = a **deterministic (subject, relation) supersession key**: a new value retires every active record with the same key — *no similarity threshold, no LLM* — so recall never serves the stale value (bi-temporal: a back-filled earlier value can't overwrite the current one) |
| `recall(query, k, where=…)` | **value-ranked** retrieval: relevance × value, **decayed by the memory's per-type half-life** (access resets the clock), so important durable memories beat both merely-similar and stale ones. Optional `where` = a **metadata pre-filter** (the cheap *filter-before-you-rank* lever): field → scalar / list / operator (`$gte $lte $gt $lt $in $nin $ne $contains`), matched top-level then `meta`, ALL fields AND-ed — e.g. a hard time-range `where={"valid_from":{"$gte":t0,"$lte":t1}}` or a closed-set entity `where={"speaker":{"$in":[…]}}`. Measured to beat retriever choice on LoCoMo (`probes/locomo_metadata_prefilter.py`); it's a HARD filter, so on lossy/predicted extraction keep it loose (a wrong filter hard-deletes the answer). Reinforcement is **relevance-weighted** (a bullseye hit reinforces value more than one that squeaked into top-k, so a weak-but-frequent false positive can't go immortal); a repeatedly-recalled episodic memory **graduates** to semantic **only when corroborated** — by an earned outcome, or by **≥2 distinct *canonical* sources** (entity-resolved before counting, so sybil variants of one origin — `Wikipedia` / `wikipedia.org` / a full URL — collapse to one and can't mint durability); and a memory whose source was later contradicted is **provenance-demoted** + flagged `stale_derived` |
| `consolidate(keep)` | the **dream pass**: flag universal-matcher *hubs*, link near-duplicates, apply the **state-toggle guard** (a polarity clash supersedes, doesn't merge), supersede the low-value surplus — only *adds* a derived layer |
| `consolidate_clusters(threshold)` | **cluster-triggered** consolidation: consolidate a semantic cluster only once it's grown past `threshold` — sparse topics keep their raw episodes, dense ones don't grow unbounded |
| `contradictions()` | flag mutually-incompatible **related** memories (similarity-gated) for human review |
| `forget(ids, where)` | the one op that **truly deletes** (the rest is append-only): hard-removes the matched records *and* scrubs their ids from every survivor's links + toggle pointers + the vec/token caches, so a forgotten memory can't resurface via recall, a consolidation link, or the dream pass. For erasure / right-to-be-forgotten, poison removal, or a hard correction — measured 15/15 on a verified-forgetting severe-test |

## Five rules it won't break (each one cost us to learn)

1. **Raw capture is immutable.** Consolidation adds links and markers; it never overwrites the
   source. This is what stops the slow accuracy drift of LLM-rewritten memory.
2. **Absolute timestamps at write time.** Relative/derived times rot the moment they're consolidated.
3. **Value-ranked, type-aware decay.** Retention is `value × a per-type half-life`, not recency or
   access-frequency alone. A *uniform* access-reset clock keeps merely-*popular* memories while a
   load-bearing-but-cold fact — queried once a month, prevents a destructive action — starves; we
   measured exactly that failure. The fix is that the half-life is set by **kind**, not by read
   count: episodic events fade in days, semantic facts in months, procedural rules barely at all. A
   cold-but-critical fact survives by being **typed** semantic/procedural (long half-life × its high
   value), not by frequent reads; access only resets the clock *within* a type's window.
4. **Value is reported at the cohort level** (tag / time-block), never per-memory.
5. **Contradictions are flagged, never auto-resolved.** Silent rewrites destroy trust in the whole
   memory.

## Provenance — why these rules, with receipts

<details>
<summary>Why these rules — the measured receipts behind mnemo's design. Click to expand.</summary>

`mnemo`'s design isn't taste; it's what Agora's lab *measured*:

- **Semantic recall beats keyword recall, and the gap widens with scale** — as the store grows to
  a corpus of several thousand notes, lexical `recall@5` decays from **0.94** (small store) to **0.25**,
  while semantic **holds at ~0.65** — ≈**2.6×** at full scale (Agora Lab `b4c260`); on paraphrase
  queries semantic `recall@5` is **0.86 vs 0.20** lexical (`3501f1`). The embedder is the real lever
  at scale; the lexical overlap match is the zero-dependency *floor* that still runs anywhere on a
  small store. (Honest footnote: pruning
  universal-matcher *hub* notes lifts **lexical** recall ~20% only when a store is link-spammed, and
  does **not** move semantic recall — it's a lexical/hybrid optimisation, not a headline.)
- **Value-ranked consolidation** — under a keep-budget, ranking *what to keep* by value beats
  FIFO/random, and the advantage **scales super-linearly as the budget shrinks** (≈1.8× at half
  budget → ≈4× at one-eighth), surviving heavy estimation noise.
- **Retention must blend value with recency, not decay on access alone** — we simulated a
  half-life-with-access-reset policy (a *popularity* signal) against a value-aware blend under a
  shrinking budget, with value made deliberately anti-correlated with access-frequency for a
  load-bearing-but-cold subset. At a 30% keep-budget the access-decay policy retained only **2.8%**
  of the high-value/low-frequency memories and **20%** of total value, vs **100%** and **64%** for
  the blend — about **3× more value kept** (the gap persists, ≈2.2× retained value, even at a 7%
  budget). Pure access-frequency decay starves the rarely-queried-but-critical memories; forgetting
  must consume an explicit value channel *separate from* access recency. (Agora Lab `19d802`.)
- **Supersession needs a deterministic key, not embedding similarity** — replicating an external
  result (MemStrata / Yadav, arXiv 2606.26511) on our own local `nomic` stack: a cosine-similarity
  classifier separating a *contradicted* fact from a *rephrased duplicate* scores **AUROC ~0.61**
  (near chance) — a contradiction is often *more* embedding-similar to the original than a true
  rephrase is. A similarity-based store therefore serves the **stale value ~42% of the time**; the
  deterministic `(subject, relation, object)` supersession key (`remember(..., key=...)`) drives that
  to **0%** (Agora Lab `exp_supersession_replication`, severe-test 8/8). This is *why* supersession is
  a key, not a threshold.
- **No single recall mechanism survives all operating points — only the layered store does** —
  head-to-head on a synthetic *evolving + contaminated* stream (stable / superseded / poisoned facts,
  local `nomic`): a naive **cosine top-1** store scores **42%** (fine on stable, but blind to
  supersession — **0/8** on updated facts — and fooled by repeated lies); a **recency** store **67%**
  (fixes supersession but serves the *freshest lie* — **0/8** on poison); `mnemo` — deterministic
  supersession key **+** corroboration gate **+** value-ranking — is **100%**, robust across all three.
  Each single mechanism wins one regime and loses another (the *memory operating-point trap*), which is
  why the durable layer needs all three together (probe `mnemo/probes/operating_point_memory.py`).
- **Cohort-level value** — per-memory outcome attribution is **statistically underpowered at n-of-1**
  (the best proxy reached only ~0.36 power at realistic sample sizes); the cohort is where the
  signal lives. Hence rule 4.
- **Contradiction detection** runs in production over the 10,000-note vault; the lesson that it must
  *flag, not auto-edit* (rule 5) is why silent rewrites are forbidden.

(Methods + numbers live in the Agora track record: <https://dancenitra.github.io/agora/>.)

</details>

## Threat model & layered defense (adversarial memory integrity)

<details>
<summary>The full adversarial threat model + layered defenses. Click to expand.</summary>

An untrusted-ingestion memory store cannot decide whether a written claim is *true*. mnemo doesn't try to;
it makes the attacker **pay**, and the honest map of what each layer buys — worked to bedrock across a public
practitioner thread with adversarial review — is below. Every claim here has a runnable receipt in
[`mnemo/probes/`](probes/); this is textbook mechanism with a receipt, **not** a new theory.

**A defense the attacker can also write is a suggestion, not a defense.** Content-declared provenance is
theater: `Source: X` and `corroborated by N` are strings a writer controls, so default (distinct source
*strings*) corroboration falls to a sybil that mints two labels (~0.9 attack-success across 10 models —
[`memory_defense_layer_probe`](probes/memory_defense_layer_probe.py)). Only channels the writer does **not**
control hold — distinct *verified keys* (`strict_corroboration`, Ed25519 `attest`) **whose issuance is itself
costly/rate-limited** (a free-to-mint key is just another string a sybil spends), an *earned* Beta(good,bad)
outcome credit a session can't self-grant, and *system write-history*.
That is Biba integrity (1977) / Cheng-Friedman (2005): no symmetric reputation is sybilproof; the escape is
an exogenous, un-writable anchor.

**The layers, and the exact residual each leaves:**
- **Provenance — did the call happen?** Bind standing to a *runtime* signature over the real `(tool, result)`,
  not the session's log ([`execution_receipt_gate`](probes/execution_receipt_gate_probe.py)). Closes fabricated
  logs **iff the executor is a trust domain separate from the session**; in-process tools → the key is
  session-readable → theater.
- **Veracity — is a real call's output true?** No write-time oracle (a novel fact has no priors; attestation =
  authorship, not truth). Standing is *earned at use time* from an observed outcome
  ([`veracity_outcome_grounding`](probes/veracity_outcome_grounding_probe.py)) — only helps where harm is observable.
- **The irreversible tail.** A provenance-scaled `spend_irreversible` budget makes a low-provenance memory bind an
  honest action's irreversible spend against itself ([`soft_influence_taint`](probes/soft_influence_taint_probe.py));
  a reversibility checkpoint bounds a one-shot defector. Bounds, doesn't close (Sybil relocates it per identity).
- **The sub-threshold coordinated campaign.** A temporal change-detector is evaded for free at bias `h→0`, but
  `B≈N·h` forces a growing correlated low-provenance population a **cross-sectional** detector catches
  ([`two_detector_trap`](probes/two_detector_trap_probe.py)); and randomized retrieval raises a *targeted*
  attacker's coverage from O(1) to ~Θ(fN) with no anchor
  ([`moving_target_retrieval`](probes/moving_target_retrieval_probe.py)).

**The bedrock.** Checked from ~8 directions (detection, reputation, elicitation-without-ground-truth à la Bayesian
Truth Serum, robust aggregation, moving-target), every layer we examined reduces to one of two exogenous anchors —
a bounded corruption *count* (Byzantine; sybils break it) or a shared attacker-independent *prior* (peer-prediction;
a coalition coordinating its reports breaks it). *(A synthesis over those cases, not a proof.)* You cannot separate
a large coordinated coalition from genuine consensus from internal signals alone (Cheng-Friedman +
Lamport-Shostak-Pease 1982; and no internal truth-oracle, by analogy to Tarski's undefinability). What that
leaves is not "give up" but a shape: **localize the one exogenous check at the rare high-consequence irreversible
step** (a human, a separately-provenanced feed — a channel the poison can't reach), and **don't let evidence-free
consensus drive an irreversible action** (weight it ~0; on an observable target, require an independent evidentiary
provenance, which is super-linear to forge, not N reputations). The residual is the integrity of that one minimal
anchor — a standard, bounded problem, not the intractable verify-all-memory one.

Prior art credited throughout: Biba 1977 · Douceur 2002 · Cheng-Friedman 2005 · Friedman-Resnick 2001 ·
Lamport-Shostak-Pease 1982 · Lorden 1971 / Moustakides 1986 (CUSUM delay floor) ·
Tarski (undefinability of truth, used by analogy) · Doyle 1979 (truth-maintenance) · Garcia-Molina & Salem 1987 (Sagas) ·
Prelec 2004 (Bayesian Truth Serum) · Blanchard 2017 / Yin 2018 (Byzantine-robust aggregation) ·
PoisonedRAG (Zou 2024) · MINJA (Dong, arXiv:2503.03704) · AgentPoison (Chen, arXiv:2407.12784) ·
the shilling / Sybil-detection line (Mobasher-Burke 2007, Mehta-Nejdl 2009, SybilRank/Cao 2012, Viswanath 2010).

</details>

## The `second_brain` thinking layer

An optional layer on top of the store — dialectic, contradiction
surfacing, question generation: **[docs/SECOND_BRAIN.md](docs/SECOND_BRAIN.md)**.
## Status

`v0.2` — the core, honest and runnable, **now with two MCP servers** (`mnemo_mcp` for memory,
`second_brain_mcp` for the thinking layer over your notes) **and a deterministic supersession key**
(`remember(..., key=...)`) that closes the embedding *supersession blind spot*. Roadmap: pluggable
vector stores, a hosted tier. Open-core; the core stays free.

MIT-licensed · part of [Agora](https://github.com/DanceNitra/agora).

## Self-maintaining (maintain.py)
The #1 second-brain frustration is **maintenance**, not capture. `maintain.py` runs the chore people
stop doing — over a folder of Markdown notes it finds **dead `[[wikilinks]]`, orphan notes, stale
notes, near-duplicate clusters**, and a **vault health score** (`self_legibility` = % of notes in the
link graph's giant component — knowledge debt is a *percolation* collapse, so it warns *before* the
cliff). Crucially it turns findings into **actions**: for each orphan it **suggests which existing
note to link it to** (re-connecting it to the graph), and flags **archive candidates** (old +
isolated). It resolves links by filename *or* frontmatter alias, and dates notes by frontmatter
(not git-reset mtime) — both learned from dogfooding it on a real ~7,700-note vault (it rescued ~300
falsely-flagged orphans). Advisory + safe: it returns a plan and an action list; it never edits,
moves, or deletes a note. And it can **apply** the fix when you ask: `apply_suggestions` appends a
marked `## Related (auto-suggested)` block of `[[links]]` to each orphan — additive only, idempotent
(re-running replaces its own block), **dry-run by default**. `python maintain.py` runs a verified
round-trip on a synthetic vault (diagnose → suggest → apply); `maintenance_report` and `apply_links`
in `second_brain_mcp.py` expose it to any MCP agent.

<!-- MCP registry ownership proof -->
mcp-name: io.github.DanceNitra/mnemo
