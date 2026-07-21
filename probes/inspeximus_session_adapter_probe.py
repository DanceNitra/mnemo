"""inspeximus_session_adapter_probe.py — InspeximusSession faithfully implements the OpenAI Agents `Session` protocol.

Verifies the adapter's contract WITHOUT the SDK installed (the protocol is matched structurally). Checks map
to the SDK's documented Session semantics + inspeximus's honest governance bonus.
"""
import sys, pathlib, asyncio, tempfile
# test the SHIPPED package layout (inspeximus_pypi/inspeximus/ is the real package with integrations/), so
# `from inspeximus.integrations...` resolves exactly as an installed user would import it.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "inspeximus_pypi"))
from inspeximus import Inspeximus, new_receipt_keypair
from inspeximus.integrations.openai_agents import InspeximusSession


def item(role, content):
    return {"role": role, "content": content}


async def run():
    ok = {}
    tmp = pathlib.Path(tempfile.mkdtemp())
    path = str(tmp / "sessions.json")

    s = InspeximusSession("user-42", path=path)

    # empty session
    ok["A empty get -> []"] = (await s.get_items()) == []
    ok["B pop empty -> None"] = (await s.pop_item()) is None

    # add + get preserves order + verbatim
    await s.add_items([item("user", "hi"), item("assistant", "hello")])
    await s.add_items([item("user", "what is 2+2?")])
    got = await s.get_items()
    ok["C order + verbatim"] = got == [item("user", "hi"), item("assistant", "hello"), item("user", "what is 2+2?")]

    # limit -> latest N, still oldest-first
    ok["D limit=2 -> latest two"] = (await s.get_items(limit=2)) == [item("assistant", "hello"), item("user", "what is 2+2?")]
    ok["E limit=0 -> []"] = (await s.get_items(limit=0)) == []

    # pop removes + returns most recent
    popped = await s.pop_item()
    ok["F pop -> most recent"] = popped == item("user", "what is 2+2?")
    ok["G pop shrank history"] = (await s.get_items()) == [item("user", "hi"), item("assistant", "hello")]

    # multi-session isolation on ONE shared store
    store = Inspeximus(path=str(tmp / "shared.json"))
    sa = InspeximusSession("A", store=store); sb = InspeximusSession("B", store=store)
    await sa.add_items([item("user", "a1")]); await sb.add_items([item("user", "b1"), item("user", "b2")])
    ok["H session isolation"] = ((await sa.get_items()) == [item("user", "a1")]
                                 and (await sb.get_items()) == [item("user", "b1"), item("user", "b2")])

    # persistence across a reopen (same path)
    s2 = InspeximusSession("user-42", path=path)
    ok["I persistence across reopen"] = (await s2.get_items()) == [item("user", "hi"), item("assistant", "hello")]

    # clear removes only this session
    await sa.clear_session()
    ok["J clear this session only"] = ((await sa.get_items()) == []
                                       and (await sb.get_items()) == [item("user", "b1"), item("user", "b2")])

    # governance bonus: erasure leaves an accounted-for, tamper-evident trail
    sk, pk = new_receipt_keypair()
    gstore = Inspeximus(path=str(tmp / "gov.json"), receipts=True, receipt_key=sk, receipt_pubkey=pk)
    gs = InspeximusSession("user-9", store=gstore)
    await gs.add_items([item("user", "delete me later"), item("assistant", "ok")])
    r = gs.forget_subject(request_id="dsar-1")
    verify_ok, _ = gstore.verify_writes(expected_pubkey=pk)
    ok["K erasure + accounted-for audit"] = (r["erased"] == 2 and verify_ok
                                             and (await gs.get_items()) == []
                                             and gstore.erasure_report()["tombstoned_total"] == 2)

    print("=" * 66)
    print("InspeximusSession — OpenAI Agents Session protocol (faithful + governance)")
    print("=" * 66)
    for k, v in ok.items():
        print(f"  [{'PASS' if v else 'FAIL'}] {k}")
    print("-" * 66)
    print("RECEIPT:", "VALID — all checks hold" if all(ok.values()) else "INVALID — do not ship")
    return 0 if all(ok.values()) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run()))
