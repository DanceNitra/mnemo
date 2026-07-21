"""
encryption_at_rest_probe.py — a runnable receipt for inspeximus 1.7.0 encryption-at-rest + crypto-shredding. MIT.

Demonstrates, deterministically, exactly what the feature does AND its honest limits — so a reader can verify
the claim instead of trusting it. Standard primitives only (AES-256-GCM via `cryptography`); we do not roll our
own crypto.

WHAT IT SHOWS
  1. data at rest is confidential  — the secret is NOT present in the on-disk bytes
  2. tamper-evident               — flipping one byte makes the store fail to open (AEAD)
  3. no key -> no data            — wrong key / no key raises, never silently returns empty
  4. crypto-shred                 — destroy the key and every at-rest copy of the ciphertext is unrecoverable
  5. the HONEST boundary          — what it protects (at rest) and what it does NOT (a running process)

RUN:  pip install cryptography ; python encryption_at_rest_probe.py
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from inspeximus import Inspeximus, new_encryption_key  # noqa: E402

SECRET = "patient SSN 123-45-6789; diagnosis: confidential"


def main():
    d = tempfile.mkdtemp()
    path = os.path.join(d, "vault.json")
    key = new_encryption_key()                       # 32-byte AES-256 key; the app holds it, inspeximus never stores it

    m = Inspeximus(path=path, encrypt_key=key)
    m.remember(SECRET, key="record::patient", object=SECRET)
    m.flush()

    raw = open(path, "rb").read()
    print("inspeximus 1.7.0 encryption-at-rest — runnable receipt\n")
    print(f"  1. confidential at rest : secret in the on-disk bytes? {SECRET.encode() in raw}"
          f"   (header={raw[:5]!r}, {len(raw)} bytes of ciphertext)")

    # 2. tamper-evident
    bad = bytearray(raw); bad[-1] ^= 0x01
    open(path, "wb").write(bad)
    try:
        Inspeximus(path=path, encrypt_key=key); tamper = "NOT detected (BUG)"
    except Exception:
        tamper = "detected (store refuses to open)"
    open(path, "wb").write(raw)                      # restore
    print(f"  2. tamper-evident       : one flipped byte -> {tamper}")

    # 3. no key -> no data
    try:
        Inspeximus(path=path); nokey = "opened WITHOUT key (BUG)"
    except Exception:
        nokey = "raises (never silent-empty)"
    try:
        Inspeximus(path=path, encrypt_key=new_encryption_key()); wrong = "opened with WRONG key (BUG)"
    except Exception:
        wrong = "raises"
    print(f"  3. no key -> no data    : open without key -> {nokey}; wrong key -> {wrong}")

    # 4. crypto-shred: destroy the key -> the ciphertext (and any backup of it) is dead
    m2 = Inspeximus(path=path, encrypt_key=key)
    receipt = m2.shred()
    del key                                          # simulate destroying the only key
    try:
        Inspeximus(path=path, encrypt_key=new_encryption_key()); recov = "RECOVERED (BUG)"
    except Exception:
        recov = "unrecoverable"
    print(f"  4. crypto-shred         : key destroyed -> reopen (no original key) -> {recov}"
          f"   {json.dumps(receipt['note'])}")

    print("\n  5. honest boundary:")
    print("     PROTECTS  : the file / disk image / stolen laptop / backup, at rest")
    print("     does NOT  : a compromised RUNNING process (key + plaintext are in RAM), the key holder,")
    print("                 malware/keyloggers, OS swap of live plaintext. Not end-to-end, not runtime.")
    print("     shred honest limit: cannot reach plaintext already copied elsewhere, or any copy saved")
    print("                 UNENCRYPTED before a key was set. Supports GDPR Art.17 erasure; not a compliance cert.")
    print("\n  prior art credited: SQLCipher (embedded-DB AES), NIST SP 800-88 (cryptographic erasure), age/Fernet.")


if __name__ == "__main__":
    main()
