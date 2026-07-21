# -*- coding: utf-8 -*-
"""`inspeximus install` — it edits config files it did not write, so the tests are about restraint.

The bar is not "does it produce a config". It is: does it refuse when it should, leave everything
else alone, and decline to claim success it has not earned.
"""
import json
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from inspeximus import install as I   # noqa: E402


def test_every_host_declares_whether_it_was_actually_exercised():
    for name, spec in I.HOSTS.items():
        assert isinstance(spec["verified"], bool), name
        assert spec["docs"].startswith("http"), name


def test_unknown_host_is_an_error_not_a_guess():
    p = I.plan("emacs")
    assert p["error"] and "unknown host" in p["error"]


def test_unverified_host_says_so_instead_of_implying_success(tmp_path, monkeypatch):
    monkeypatch.setattr(I, "_home", lambda: tmp_path)
    p = I.plan("cursor")
    assert p["verified"] is False
    assert "UNVERIFIED" in I.render(p)


def test_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.setattr(I, "_home", lambda: tmp_path)
    first = I.plan("claude")
    assert first["action"] == "create"
    ok, _ = I.apply(first)
    assert ok
    second = I.plan("claude")
    assert second["action"] == "unchanged"
    ok, msg = I.apply(second)
    assert ok and "unchanged" in msg
    data = json.loads((tmp_path / ".claude.json").read_text(encoding="utf-8"))
    assert list(data["mcpServers"]) == ["inspeximus"]      # one entry, not two


def test_never_clobbers_someone_elses_config(tmp_path, monkeypatch):
    monkeypatch.setattr(I, "_home", lambda: tmp_path)
    cfg = tmp_path / ".claude.json"
    cfg.write_text(json.dumps({
        "numStartups": 41,
        "projects": {"/x": {"allowedTools": ["a"]}},
        "mcpServers": {"someone-else": {"command": "their-server"}},
    }), encoding="utf-8")
    I.apply(I.plan("claude"))
    data = json.loads(cfg.read_text(encoding="utf-8"))
    assert data["numStartups"] == 41
    assert data["projects"]["/x"]["allowedTools"] == ["a"]
    assert data["mcpServers"]["someone-else"] == {"command": "their-server"}
    assert "inspeximus" in data["mcpServers"]


def test_refuses_a_malformed_config_rather_than_replacing_it(tmp_path, monkeypatch):
    monkeypatch.setattr(I, "_home", lambda: tmp_path)
    cfg = tmp_path / ".claude.json"
    cfg.write_text("{ this is not json", encoding="utf-8")
    p = I.plan("claude")
    assert p["error"] and "not valid JSON" in p["error"]
    ok, _ = I.apply(p)
    assert not ok
    assert cfg.read_text(encoding="utf-8") == "{ this is not json"    # untouched


def test_backs_up_before_overwriting(tmp_path, monkeypatch):
    monkeypatch.setattr(I, "_home", lambda: tmp_path)
    cfg = tmp_path / ".claude.json"
    cfg.write_text(json.dumps({"keep": 1}), encoding="utf-8")
    I.apply(I.plan("claude"))
    assert json.loads((tmp_path / ".claude.json.bak").read_text(encoding="utf-8")) == {"keep": 1}


def test_toml_escapes_windows_paths_and_still_parses(tmp_path):
    r"""A Windows path interpolated raw into TOML contains \U, which TOML reads as a unicode escape."""
    tomllib = pytest.importorskip("tomllib")
    block = {"command": r"C:\Users\Someone\.local\bin\uvx.EXE",
             "args": ["--from", "inspeximus[mcp]", "inspeximus-mcp"],
             "env": {"INSPEXIMUS_PATH": r"C:\Users\Someone\mem.json"}}
    parsed = tomllib.loads(I._toml_block("inspeximus", block))
    entry = parsed["mcp_servers"]["inspeximus"]
    assert entry["command"] == block["command"]
    assert entry["args"] == block["args"]
    assert entry["env"]["INSPEXIMUS_PATH"] == block["env"]["INSPEXIMUS_PATH"]


def test_codex_writes_only_fields_its_schema_accepts():
    """Codex's config is deny_unknown_fields: one extra key is a parse error, not a warning."""
    spec = I.HOSTS["codex"]
    emitted = spec["fields"](I.default_server_block("/tmp/mem.json"))
    assert set(emitted) <= {"command", "args", "env"}


def test_windsurf_has_no_project_scope(tmp_path, monkeypatch):
    monkeypatch.setattr(I, "_home", lambda: tmp_path)
    p = I.plan("windsurf", scope="project")
    assert p["error"] and "no 'project' scope" in p["error"]


def test_cline_honours_its_path_overrides(tmp_path, monkeypatch):
    monkeypatch.setenv("CLINE_MCP_SETTINGS_PATH", str(tmp_path / "custom.json"))
    assert I._cline_paths(None)["user"] == tmp_path / "custom.json"
    monkeypatch.delenv("CLINE_MCP_SETTINGS_PATH")
    monkeypatch.setenv("CLINE_DATA_DIR", str(tmp_path / "d"))
    assert I._cline_paths(None)["user"] == tmp_path / "d" / "settings" / "cline_mcp_settings.json"


def test_dry_run_writes_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(I, "_home", lambda: tmp_path)
    p = I.plan("claude")
    assert "dry run" in I.render(p, dry_run=True)
    assert not (tmp_path / ".claude.json").exists()


def test_rerunning_without_store_does_not_strip_what_the_first_run_wrote(tmp_path, monkeypatch):
    """The second run must not silently drop env, nor any key the user added by hand."""
    monkeypatch.setattr(I, "_home", lambda: tmp_path)
    I.apply(I.plan("claude", store_path="/somewhere/mem.json"))
    cfg = tmp_path / ".claude.json"
    data = json.loads(cfg.read_text(encoding="utf-8"))
    data["mcpServers"]["inspeximus"]["timeout"] = 45000          # user's own edit
    cfg.write_text(json.dumps(data), encoding="utf-8")

    p = I.plan("claude")                                          # no --store this time
    I.apply(p)
    entry = json.loads(cfg.read_text(encoding="utf-8"))["mcpServers"]["inspeximus"]
    assert entry["env"] == {"INSPEXIMUS_PATH": "/somewhere/mem.json"}
    assert entry["timeout"] == 45000
