"""
demo_gc_id_reuse.py
===================
Shows how Python's garbage collector can reuse memory addresses (id()),
causing bugs in caches that use id() as a key.

This is especially visible on Python 3.13+ where GC runs more frequently.

Run with:
    python demo_gc_id.py
    python3.11 demo_gc_id.py
    python3.13 demo_gc_id.py
"""

import gc
import platform
import sys
from collections import namedtuple


# ---------------------------------------------------------------------------
# Shared data structures (used across all demos)
# ---------------------------------------------------------------------------

FieldSchema = namedtuple("FieldSchema", ["name", "type", "offset", "width"])
CardSchema  = namedtuple("CardSchema",  ["fields", "name_to_index"])


# ---------------------------------------------------------------------------
# Part 1 – Basic id() reuse demo
# ---------------------------------------------------------------------------

def demo_id_reuse():
    """
    Creates two different schemas back-to-back.
    If Python reuses the first schema's memory address for the second,
    an id()-based cache will return the wrong value.
    """
    print("=" * 60)
    print("PART 1 – Basic id() reuse")
    print("=" * 60)

    id_cache = {}  # id(schema) → format string

    # Schema A: 2 int fields
    schema_a = CardSchema(
        fields=(FieldSchema("foo", int, 0, 10), FieldSchema("bar", int, 10, 10)),
        name_to_index={"foo": 0, "bar": 1},
    )
    id_cache[id(schema_a)] = "FormatSpec(2 int fields)"
    addr_a = id(schema_a)
    print(f"  Schema A  id={addr_a:#x}  →  cached: {id_cache[addr_a]}")

    # Free schema_a so its address can be reused
    del schema_a
    gc.collect()
    print(f"  Schema A freed, address {addr_a:#x} is now available")

    # Schema B: 8 float fields
    schema_b = CardSchema(
        fields=tuple(FieldSchema(c, float, i * 10, 10) for i, c in enumerate("abcdefgh")),
        name_to_index={c: i for i, c in enumerate("abcdefgh")},
    )
    addr_b = id(schema_b)
    print(f"  Schema B  id={addr_b:#x}")

    if addr_a == addr_b:
        stale = id_cache[addr_b]
        print(f"\n  [BUG] Address collision!")
        print(f"        Cache says: '{stale}'")
        print(f"        Reality: Schema B has 8 float fields → wrong result!")
    else:
        print(f"\n  [OK] No collision this run (addresses differ)")
        print(f"       Run again — collisions are non-deterministic")

    # Force collisions to prove the point
    print("\n  Forcing 50 back-to-back pairs to check reuse rate...")
    collisions = sum(_schemas_share_address() for _ in range(50))
    print(f"  Address reused: {collisions}/50 pairs")
    if collisions:
        print("  ⚠  Confirmed: Python reused freed addresses → cache bug is real")
    else:
        print("  ✓  No reuse this run (allocator timing varies)")
    print()


def _schemas_share_address() -> bool:
    """Returns True if two consecutive schemas land at the same address."""
    s1 = CardSchema(fields=(FieldSchema("x", int, 0, 10),), name_to_index={"x": 0})
    addr = id(s1)
    del s1
    gc.collect()
    s2 = CardSchema(fields=(FieldSchema("y", float, 0, 10),), name_to_index={"y": 0})
    return id(s2) == addr


# ---------------------------------------------------------------------------
# Part 2 – Stress test: measure how often stale cache hits occur
# ---------------------------------------------------------------------------

def demo_stale_cache_hits(iterations: int = 100):
    """
    Simulates a module-level cache (like PyDyna's card.py) across many
    iterations. Each iteration uses a different schema shape. If the address
    of the new schema matches a freed one, the cache returns wrong data.
    """
    print("=" * 60)
    print(f"PART 2 – Stale cache hit rate over {iterations} iterations")
    print("=" * 60)

    # Mirrors a module-level cache that is never cleared between tests
    cache = {}  # (id, format_name) → expected FormatSpec string

    schema_templates = [
        ("int-2",   [FieldSchema("foo", int,   0, 10), FieldSchema("bar", int, 10, 10)]),
        ("float-8", [FieldSchema(c, float, i * 10, 10) for i, c in enumerate("abcdefgh")]),
        ("str-4",   [FieldSchema(c, str,   i * 10, 10) for i, c in enumerate("pqrs")]),
    ]

    stale_hits = 0
    first_stale = None

    for i in range(iterations):
        label, fields = schema_templates[i % len(schema_templates)]
        schema = tuple(fields)
        expected = f"FormatSpec({label})"
        key = (id(schema), "default")

        cached = cache.get(key)

        if cached is not None and cached != expected:
            # Cache hit, but it's for a *different* schema — the bug
            stale_hits += 1
            if first_stale is None:
                first_stale = (i, cached, expected, key[0])
        else:
            cache[key] = expected

        del schema
        gc.collect()  # Python 3.13+ does this automatically between tests

    rate = stale_hits / iterations * 100
    print(f"  Stale hits (bug): {stale_hits}/{iterations}  ({rate:.1f}%)")

    if first_stale:
        idx, got, expected, addr = first_stale
        print(f"  First stale hit at iteration {idx}:")
        print(f"    address 0x{addr:x}  →  cache had '{got}',  expected '{expected}'")
        print("  ⚠  id() collision confirmed")
    else:
        print("  ✓  No collisions this run")
        print("     They are still possible — try running again or on Python 3.13+")
    print()


# ---------------------------------------------------------------------------
# Part 3 – The fix: use content as the cache key
# ---------------------------------------------------------------------------

def demo_content_key_fix():
    """
    Instead of id(schema) (a memory address), use a tuple of the schema's
    actual field values. Different schemas always get different keys.
    """
    print("=" * 60)
    print("PART 3 – Fix: content-based cache key")
    print("=" * 60)

    cache = {}  # content_key → FormatSpec string

    def schema_key(fields):
        """Build a stable key from field contents, not memory address."""
        return tuple((f["name"], f["type"], f["offset"], f["width"]) for f in fields)

    # Schema A: 2 int fields
    fields_a = [
        {"name": "foo", "type": int, "offset": 0,  "width": 10},
        {"name": "bar", "type": int, "offset": 10, "width": 10},
    ]
    key_a = schema_key(fields_a)
    cache[key_a] = "FormatSpec(2 int fields)"
    print(f"  Schema A key: {key_a}")
    print(f"  Cached:       {cache[key_a]}")

    gc.collect()

    # Schema B: 8 float fields
    fields_b = [{"name": c, "type": float, "offset": i * 10, "width": 10}
                for i, c in enumerate("abcdefgh")]
    key_b = schema_key(fields_b)

    result = cache.get(key_b)
    if result:
        print(f"  [BUG] Stale hit: {result}")
    else:
        print(f"  Schema B key: {key_b[:2]}… ({len(fields_b)} fields)")
        print("  [OK] No collision — different content → different key")
    print()


# ---------------------------------------------------------------------------
# Part 4 – Python / GC version info
# ---------------------------------------------------------------------------

def show_gc_info():
    """Prints Python version and relevant GC settings."""
    print("=" * 60)
    print("PART 4 – GC info for this Python")
    print("=" * 60)
    print(f"  Python   : {sys.version}")
    print(f"  Platform : {platform.system()} {platform.machine()}")
    print(f"  GC enabled     : {gc.isenabled()}")
    print(f"  GC thresholds  : {gc.get_threshold()}")

    if hasattr(gc, "get_freeze_count"):
        print(f"  Freeze count   : {gc.get_freeze_count()}")

    version = sys.version_info
    if version >= (3, 13):
        print("  ⚠  Python 3.13+: incremental GC runs between every function call")
        print("     id()-based caches will produce stale hits")
    elif version >= (3, 12):
        print("  ⚠  Python 3.12: incremental GC introduced (opt-in)")
    else:
        print("  ✓  Python <3.12: stop-the-world GC — collisions are rare in practice")
    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    show_gc_info()
    demo_id_reuse()
    demo_stale_cache_hits()
    demo_content_key_fix()

    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print("  BUG : id(obj) as a cache key is unsafe.")
    print("        Python reuses freed memory addresses, so id() can refer")
    print("        to a completely different object after GC runs.")
    print("        Python 3.13+ makes this much more likely (incremental GC).")
    print()
    print("  FIX : Use a content-based tuple as the cache key instead:")
    print("        (name, type, offset, width, ...) — describes what the")
    print("        schema IS, not where it lives in memory.")
