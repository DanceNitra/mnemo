"""`from mnemo.mem0 import Memory` — the mem0-compatible drop-in. See mnemo.mem0_compat for the implementation."""
from .mem0_compat import Memory, _derive_key_object, _text_of  # noqa: F401

__all__ = ["Memory"]
