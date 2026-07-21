# inspeximus examples

Runnable, copy-paste examples. Each is self-contained and needs only `pip install inspeximus`.

| file | shows |
|---|---|
| [`01_basics.py`](01_basics.py) | remember, recall, first-class **correction** (keyed supersession), and `history()` audit trail |
| [`02_correction_and_erasure.py`](02_correction_and_erasure.py) | `echo_guard` (a restated stale value doesn't resurrect), `forget()`, and audited `forget_subject()` erasure |
| [`03_semantic_recall.py`](03_semantic_recall.py) | plug **any** `embed=` function for semantic recall; runs as-is with a dependency-free stand-in |
| [`04_encryption.py`](04_encryption.py) | AES-256-GCM **encryption-at-rest** + **crypto-shredding** erasure (needs `cryptography`) |

```bash
pip install inspeximus
python 01_basics.py
```

Everything here is zero-dependency and needs no LLM or API key. For semantic recall at production quality,
`pip install sentence-transformers` and pass its encoder as `embed=` (see `03_semantic_recall.py`).
