# Guard under test (exabgp-3)

Rule from the project's instruction file (verbatim):

> - Use `Buffer` NOT `bytes` for unpack method `data` parameters

What a violation looks like (designer's note, illustration only): Writing a new capability decoder from scratch, the common Python habit is `def unpack_capability(cls, instance, data: bytes, capability)` and slicing bytes. Here every decoder takes `data: Buffer` (bytes | memoryview from exabgp.util.types), because callers hand in memoryview slices; annotating `bytes` is the violation.

Task the agent was given: Peers that support Long-Lived Graceful Restart (RFC 9494) send capability code 71 in their OPEN, and ExaBGP currently reports it as an unknown capability. Add a proper capability class for it in src/exabgp/bgp/message/open/capability/ (each entry is AFI, SAFI, one flags octet and a 24-bit long-lived stale time), register the code and its name, and make it decode from the wire, encode back, and render in str() and JSON like the other capabilities do. We only need to parse and display what the peer sends for now, no configuration keyword and no change to route handling. Add a unit test for decoding a well formed and a truncated capability.

Note: some runs started from slightly different versions of the surrounding code. Judge only what the agent's change adds or modifies; code that was already there and that the agent left untouched does not count against it.


===== RUN a041 =====
```diff
diff --git a/src/exabgp/bgp/message/open/capability/__init__.py b/src/exabgp/bgp/message/open/capability/__init__.py
index 5c60813..6a6b91d 100644
--- a/src/exabgp/bgp/message/open/capability/__init__.py
+++ b/src/exabgp/bgp/message/open/capability/__init__.py
@@ -22,6 +22,7 @@ from exabgp.bgp.message.open.capability.pathslimit import PathsLimit
 from exabgp.bgp.message.open.capability.labels import MultipleLabels
 from exabgp.bgp.message.open.capability.asn4 import ASN4
 from exabgp.bgp.message.open.capability.graceful import Graceful
+from exabgp.bgp.message.open.capability.llgr import LongLivedGracefulRestart
 from exabgp.bgp.message.open.capability.mp import MultiProtocol
 from exabgp.bgp.message.open.capability.ms import MultiSession
 from exabgp.bgp.message.open.capability.operational import Operational
@@ -44,6 +45,7 @@ __all__ = [
     'PathsLimit',
     'ASN4',
     'Graceful',
+    'LongLivedGracefulRestart',
     'MultiProtocol',
     'MultiSession',
     'Operational',
diff --git a/src/exabgp/bgp/message/open/capability/capability.py b/src/exabgp/bgp/message/open/capability/capability.py
index 89e00a2..4188f9c 100644
--- a/src/exabgp/bgp/message/open/capability/capability.py
+++ b/src/exabgp/bgp/message/open/capability/capability.py
@@ -70,6 +70,7 @@ class CapabilityCode(IntValue):
     MULTISESSION: ClassVar[int] = 0x44  # [draft-ietf-idr-bgp-multisession]
     ADD_PATH: ClassVar[int] = 0x45  # [draft-ietf-idr-add-paths]
     ENHANCED_ROUTE_REFRESH: ClassVar[int] = 0x46  # [draft-ietf-idr-bgp-enhanced-route-refresh]
+    LONG_LIVED_GRACEFUL_RESTART: ClassVar[int] = 0x47  # [RFC9494]
     PATHS_LIMIT: ClassVar[int] = 0x4C  # [draft-abraitis-idr-addpath-paths-limit]
     LINK_LOCAL_NEXTHOP: ClassVar[int] = 0x4D  # [draft-ietf-idr-linklocal-capability]
     # 78-127    Unassigned
@@ -103,6 +104,7 @@ class CapabilityCode(IntValue):
         MULTISESSION: 'multi-session',
         ADD_PATH: 'add-path',
         ENHANCED_ROUTE_REFRESH: 'enhanced-route-refresh',
+        LONG_LIVED_GRACEFUL_RESTART: 'long-lived-graceful-restart',
         PATHS_LIMIT: 'paths-limit',
         MULTIPLE_LABELS: 'multiple-labels',
         LINK_LOCAL_NEXTHOP: 'link-local-nexthop',
@@ -150,6 +152,7 @@ class CapabilityCodes:
     MULTISESSION: ClassVar[CapabilityCode] =             CapabilityCode(CapabilityCode.MULTISESSION)
     ADD_PATH: ClassVar[CapabilityCode] =                 CapabilityCode(CapabilityCode.ADD_PATH)
     ENHANCED_ROUTE_REFRESH: ClassVar[CapabilityCode] =   CapabilityCode(CapabilityCode.ENHANCED_ROUTE_REFRESH)
+    LONG_LIVED_GRACEFUL_RESTART: ClassVar[CapabilityCode] = CapabilityCode(CapabilityCode.LONG_LIVED_GRACEFUL_RESTART)
     PATHS_LIMIT: ClassVar[CapabilityCode] =              CapabilityCode(CapabilityCode.PATHS_LIMIT)
     MULTIPLE_LABELS: ClassVar[CapabilityCode] =          CapabilityCode(CapabilityCode.MULTIPLE_LABELS)
     LINK_LOCAL_NEXTHOP: ClassVar[CapabilityCode] =       CapabilityCode(CapabilityCode.LINK_LOCAL_NEXTHOP)
diff --git a/src/exabgp/bgp/message/open/capability/llgr.py b/src/exabgp/bgp/message/open/capability/llgr.py
new file mode 100644
index 0000000..4e36cb7
--- /dev/null
+++ b/src/exabgp/bgp/message/open/capability/llgr.py
@@ -0,0 +1,81 @@
+"""llgr.py
+
+Long-Lived Graceful Restart, the capability a peer sends in its OPEN.
+"""
+
+# RFC 9494 - https://www.rfc-editor.org/rfc/rfc9494.html
+
+from __future__ import annotations
+
+import json
+from typing import ClassVar, Iterable
+
+from exabgp.protocol.family import AFI, SAFI, FamilyTuple
+from exabgp.bgp.message.open.capability.capability import Capability, CapabilityDict
+from exabgp.bgp.message.open.capability.capability import CapabilityCode
+from exabgp.bgp.message.notification import Notify
+from exabgp.util.types import Buffer
+
+# =================================================================== LongLivedGracefulRestart
+
+
+class LongLivedGracefulRestart(CapabilityDict[FamilyTuple, tuple[int, int]]):
+    """One entry per family: its flags octet and its Long-lived Stale Time in seconds.
+
+    Each entry on the wire is AFI(2) + SAFI(1) + Flags(1) + Long-lived Stale Time(3).
+    """
+
+    ID: ClassVar = Capability.CODE.LONG_LIVED_GRACEFUL_RESTART
+
+    ENTRY_LEN: ClassVar[int] = 7
+    STALE_MAX: ClassVar[int] = 0xFFFFFF
+    # RFC 9494 3: the F bit, the forwarding state of the family, is the top bit of the flags
+    FORWARDING_STATE: ClassVar[int] = 0x80
+
+    def set(self, entries: Iterable[tuple[AFI, SAFI, int, int]]) -> LongLivedGracefulRestart:
+        for afi, safi, flags, stale_time in entries:
+            # clamped, not masked: a masked stale time would be silently shorter than asked
+            self[(afi, safi)] = (flags & 0xFF, min(stale_time, self.STALE_MAX))
+        return self
+
+    def families(self) -> Iterable[FamilyTuple]:
+        return self.keys()
+
+    def extract_capability_bytes(self) -> list[bytes]:
+        entries = [
+            afi.pack_afi() + safi.pack_safi() + bytes([flags]) + stale.to_bytes(3, 'big')
+            for (afi, safi), (flags, stale) in self.items()
+        ]
+        return [b''.join(entries)]
+
+    def __str__(self) -> str:
+        families = ' '.join(
+            f'{afi}/{safi}=flags {hex(flags)} stale {stale}' for (afi, safi), (flags, stale) in self.items()
+        )
+        return f'Long-Lived Graceful Restart {families}'
+
+    def json(self) -> str:
+        families = {
+            f'{afi}/{safi}': {'forwarding': bool(flags & self.FORWARDING_STATE), 'stale-time': stale}
+            for (afi, safi), (flags, stale) in self.items()
+        }
+        return json.dumps({'name': 'long-lived graceful restart', 'address-family': families})
+
+    @classmethod
+    def unpack_capability(cls, instance: Capability, data: Buffer, capability: CapabilityCode) -> Capability:  # pylint: disable=W0613
+        assert isinstance(instance, LongLivedGracefulRestart)
+        # a repeated capability replaces the earlier one, as Graceful Restart does
+        instance.clear()
+        partial = len(data) % cls.ENTRY_LEN
+        if partial:
+            raise Notify.short(2, 0, 'Long-Lived Graceful Restart entry', cls.ENTRY_LEN, partial)
+        entries: list[tuple[AFI, SAFI, int, int]] = []
+        for offset in range(0, len(data), cls.ENTRY_LEN):
+            entry = data[offset : offset + cls.ENTRY_LEN]
+            afi = AFI.unpack_afi(entry[0:2])
+            safi = SAFI.unpack_safi(entry[2:3])
+            entries.append((afi, safi, entry[3], int.from_bytes(entry[4:7], 'big')))
+        return instance.set(entries)
+
+
+Capability.register()(LongLivedGracefulRestart)
diff --git a/tests/unit/test_llgr_capability.py b/tests/unit/test_llgr_capability.py
new file mode 100644
index 0000000..ed2ee08
--- /dev/null
+++ b/tests/unit/test_llgr_capability.py
@@ -0,0 +1,68 @@
+"""RFC 9494: the Long-Lived Graceful Restart capability (code 71) a peer sends in its OPEN.
+
+Each entry is AFI(2) + SAFI(1) + Flags(1) + Long-lived Stale Time(3), and we only decode,
+encode and display it: nothing in route handling reads it yet.
+"""
+
+from __future__ import annotations
+
+import json
+
+import pytest
+
+from exabgp.bgp.message.notification import Notify
+from exabgp.bgp.message.open.capability import Capability
+from exabgp.bgp.message.open.capability.llgr import LongLivedGracefulRestart
+from exabgp.protocol.family import AFI, SAFI
+
+LLGR = Capability.CODE.LONG_LIVED_GRACEFUL_RESTART
+
+# ipv4/unicast with F set and a stale time of 0x012345 (74565 seconds),
+# then ipv6/unicast with F clear and a stale time of 60 seconds.
+WELL_FORMED = bytes.fromhex('00010180012345' '0002010000003c')
+
+
+def decode(data: bytes) -> LongLivedGracefulRestart:
+    instance = Capability.unpack(LLGR, {}, data)
+    assert isinstance(instance, LongLivedGracefulRestart)
+    return instance
+
+
+def test_code_71_is_registered_and_named() -> None:
+    assert int(LLGR) == 71
+    assert LLGR.name() == 'long-lived-graceful-restart'
+    assert Capability.klass(LLGR) is LongLivedGracefulRestart
+
+
+def test_a_well_formed_capability_decodes_each_family() -> None:
+    llgr = decode(WELL_FORMED)
+
+    assert llgr[(AFI.ipv4, SAFI.unicast)] == (0x80, 0x012345)
+    assert llgr[(AFI.ipv6, SAFI.unicast)] == (0x00, 60)
+    assert len(llgr) == 2
+
+
+def test_a_well_formed_capability_encodes_back_to_the_same_octets() -> None:
+    assert decode(WELL_FORMED).extract_capability_bytes() == [WELL_FORMED]
+
+
+def test_a_well_formed_capability_is_shown_in_str_and_json() -> None:
+    llgr = decode(WELL_FORMED)
+
+    assert str(llgr) == (
+        'Long-Lived Graceful Restart ipv4/unicast=flags 0x80 stale 74565 ipv6/unicast=flags 0x0 stale 60'
+    )
+    shown = json.loads(llgr.json())
+    assert shown['name'] == 'long-lived graceful restart'
+    assert shown['address-family'] == {
+        'ipv4/unicast': {'forwarding': True, 'stale-time': 74565},
+        'ipv6/unicast': {'forwarding': False, 'stale-time': 60},
+    }
+
+
+def test_a_truncated_capability_is_refused_with_a_notification() -> None:
+    # one whole entry and three of the seven octets of the next
+    with pytest.raises(Notify) as raised:
+        decode(WELL_FORMED[:10])
+
+    assert 'needs 7 octets, got 3' in raised.value.detail

```


===== RUN a046 =====
```diff
diff --git a/src/exabgp/bgp/message/open/capability/__init__.py b/src/exabgp/bgp/message/open/capability/__init__.py
index 5c60813..b710397 100644
--- a/src/exabgp/bgp/message/open/capability/__init__.py
+++ b/src/exabgp/bgp/message/open/capability/__init__.py
@@ -22,6 +22,7 @@ from exabgp.bgp.message.open.capability.pathslimit import PathsLimit
 from exabgp.bgp.message.open.capability.labels import MultipleLabels
 from exabgp.bgp.message.open.capability.asn4 import ASN4
 from exabgp.bgp.message.open.capability.graceful import Graceful
+from exabgp.bgp.message.open.capability.long_lived_graceful import LongLivedGraceful
 from exabgp.bgp.message.open.capability.mp import MultiProtocol
 from exabgp.bgp.message.open.capability.ms import MultiSession
 from exabgp.bgp.message.open.capability.operational import Operational
@@ -44,6 +45,7 @@ __all__ = [
     'PathsLimit',
     'ASN4',
     'Graceful',
+    'LongLivedGraceful',
     'MultiProtocol',
     'MultiSession',
     'Operational',
diff --git a/src/exabgp/bgp/message/open/capability/capability.py b/src/exabgp/bgp/message/open/capability/capability.py
index ef3617f..662bf4d 100644
--- a/src/exabgp/bgp/message/open/capability/capability.py
+++ b/src/exabgp/bgp/message/open/capability/capability.py
@@ -70,6 +70,7 @@ class CapabilityCode(IntValue):
     MULTISESSION: ClassVar[int] = 0x44  # [draft-ietf-idr-bgp-multisession]
     ADD_PATH: ClassVar[int] = 0x45  # [draft-ietf-idr-add-paths]
     ENHANCED_ROUTE_REFRESH: ClassVar[int] = 0x46  # [draft-ietf-idr-bgp-enhanced-route-refresh]
+    LONG_LIVED_GRACEFUL_RESTART: ClassVar[int] = 0x47  # [RFC9494]
     PATHS_LIMIT: ClassVar[int] = 0x4C  # [draft-abraitis-idr-addpath-paths-limit]
     LINK_LOCAL_NEXTHOP: ClassVar[int] = 0x4D  # [draft-ietf-idr-linklocal-capability]
     # 78-127    Unassigned
@@ -103,6 +104,7 @@ class CapabilityCode(IntValue):
         MULTISESSION: 'multi-session',
         ADD_PATH: 'add-path',
         ENHANCED_ROUTE_REFRESH: 'enhanced-route-refresh',
+        LONG_LIVED_GRACEFUL_RESTART: 'long-lived-graceful-restart',
         PATHS_LIMIT: 'paths-limit',
         MULTIPLE_LABELS: 'multiple-labels',
         LINK_LOCAL_NEXTHOP: 'link-local-nexthop',
@@ -150,6 +152,7 @@ class CapabilityCodes:
     MULTISESSION: ClassVar[CapabilityCode] =             CapabilityCode(CapabilityCode.MULTISESSION)
     ADD_PATH: ClassVar[CapabilityCode] =                 CapabilityCode(CapabilityCode.ADD_PATH)
     ENHANCED_ROUTE_REFRESH: ClassVar[CapabilityCode] =   CapabilityCode(CapabilityCode.ENHANCED_ROUTE_REFRESH)
+    LONG_LIVED_GRACEFUL_RESTART: ClassVar[CapabilityCode] = CapabilityCode(CapabilityCode.LONG_LIVED_GRACEFUL_RESTART)
     PATHS_LIMIT: ClassVar[CapabilityCode] =              CapabilityCode(CapabilityCode.PATHS_LIMIT)
     MULTIPLE_LABELS: ClassVar[CapabilityCode] =          CapabilityCode(CapabilityCode.MULTIPLE_LABELS)
     LINK_LOCAL_NEXTHOP: ClassVar[CapabilityCode] =       CapabilityCode(CapabilityCode.LINK_LOCAL_NEXTHOP)
diff --git a/src/exabgp/bgp/message/open/capability/long_lived_graceful.py b/src/exabgp/bgp/message/open/capability/long_lived_graceful.py
new file mode 100644
index 0000000..bdc8895
--- /dev/null
+++ b/src/exabgp/bgp/message/open/capability/long_lived_graceful.py
@@ -0,0 +1,89 @@
+"""long_lived_graceful.py
+
+Long-Lived Graceful Restart capability (RFC 9494, capability code 71).
+
+The value is a list of entries, one per family. Each entry is seven octets: AFI (2),
+SAFI (1), a flags octet (1) and the Long-lived Stale Time in seconds (3, 24 bits).
+The F bit (0x80) is the forwarding state bit of RFC 4724; the other bits are kept as
+the peer sent them. Parsing and display only: nothing here changes route handling.
+
+Created for ExaBGP.
+Copyright (c) 2009-2017 Exa Networks. All rights reserved.
+License: 3-clause BSD. (See the COPYRIGHT file)
+"""
+
+from __future__ import annotations
+
+import json
+from typing import ClassVar, NamedTuple
+
+from exabgp.protocol.family import AFI, SAFI, FamilyTuple
+from exabgp.bgp.message.open.capability.capability import Capability, CapabilityDict
+from exabgp.bgp.message.open.capability.capability import CapabilityCode
+from exabgp.bgp.message.notification import Notify
+from exabgp.logger import log, lazymsg
+
+
+class LongLivedEntry(NamedTuple):
+    flags: int
+    stale_time: int
+
+
+class LongLivedGraceful(CapabilityDict[FamilyTuple, LongLivedEntry]):
+    ID: ClassVar = Capability.CODE.LONG_LIVED_GRACEFUL_RESTART
+    ENTRY_SIZE: ClassVar[int] = 7
+    STALE_TIME_MAX: ClassVar[int] = 0xFFFFFF
+    FORWARDING_STATE: ClassVar[int] = 0x80
+
+    def set_entry(self, afi: AFI, safi: SAFI, flags: int, stale_time: int) -> None:
+        # Only our own code calls this with values, so they are asserted, not checked
+        assert 0 <= flags <= 0xFF, 'the flags are one octet'
+        assert 0 <= stale_time <= self.STALE_TIME_MAX, 'the long-lived stale time is 24 bits'
+        self[(afi, safi)] = LongLivedEntry(flags, stale_time)
+
+    def __str__(self) -> str:
+        entries = ', '.join(
+            f'{afi} {safi} flags {hex(entry.flags)} stale-time {entry.stale_time}'
+            for (afi, safi), entry in self.items()
+        )
+        return f'LongLivedGracefulRestart({entries})'
+
+    def json(self) -> str:
+        families = {
+            f'{afi}/{safi}': {'flags': entry.flags, 'stale-time': entry.stale_time}
+            for (afi, safi), entry in self.items()
+        }
+        return json.dumps({'name': 'long-lived-graceful-restart', 'families': families})
+
+    def extract_capability_bytes(self) -> list[bytes]:
+        entries = b''.join(
+            afi.pack_afi() + safi.pack_safi() + bytes([entry.flags]) + entry.stale_time.to_bytes(3, 'big')
+            for (afi, safi), entry in self.items()
+        )
+        return [entries] if entries else []
+
+    @classmethod
+    def unpack_capability(cls, instance: Capability, data: bytes, capability: CapabilityCode) -> Capability:  # pylint: disable=W0613
+        assert isinstance(instance, LongLivedGraceful)
+        if len(instance) > 0:
+            log.debug(lazymsg('capability.long-lived-graceful-restart.duplicate action=merge'), 'parser')
+        # The peer controls this length, so it is checked, never asserted
+        view = memoryview(data)
+        if len(view) % cls.ENTRY_SIZE:
+            raise Notify(
+                2,
+                0,
+                f'Long-lived Graceful Restart capability truncated: {len(view)} octets is not a multiple of '
+                f'{cls.ENTRY_SIZE} (AFI, SAFI, flags, stale time per family)',
+            )
+        while view:
+            afi = AFI.unpack_afi(view[:2])
+            safi = SAFI.unpack_safi(view[2:3])
+            flags = view[3]
+            stale_time = int.from_bytes(view[4 : cls.ENTRY_SIZE], 'big')
+            view = view[cls.ENTRY_SIZE :]
+            instance.set_entry(afi, safi, flags, stale_time)
+        return instance
+
+
+Capability.register()(LongLivedGraceful)
diff --git a/tests/unit/test_long_lived_graceful_capability.py b/tests/unit/test_long_lived_graceful_capability.py
new file mode 100644
index 0000000..a1cf536
--- /dev/null
+++ b/tests/unit/test_long_lived_graceful_capability.py
@@ -0,0 +1,115 @@
+#!/usr/bin/env python3
+# encoding: utf-8
+"""test_long_lived_graceful_capability.py
+
+Long-Lived Graceful Restart capability (RFC 9494, capability code 71).
+
+The value is seven octets per family: AFI, SAFI, a flags octet and a 24-bit
+Long-lived Stale Time. These tests cover a well formed value, which must decode,
+display and encode back to the same octets, and a truncated one, which the
+receiver must answer with a NOTIFICATION rather than an exception it did not expect.
+
+Created for ExaBGP testing framework
+License: 3-clause BSD
+"""
+
+from __future__ import annotations
+
+import json
+
+import pytest
+
+from exabgp.bgp.message.notification import Notify
+from exabgp.bgp.message.open.capability.capabilities import Capabilities
+from exabgp.bgp.message.open.capability.capability import Capability
+from exabgp.bgp.message.open.capability.capability import CapabilityCode
+from exabgp.bgp.message.open.capability.long_lived_graceful import LongLivedEntry
+from exabgp.bgp.message.open.capability.long_lived_graceful import LongLivedGraceful
+from exabgp.protocol.family import AFI, SAFI
+
+# IPv4 unicast, flags F set, stale time 0x012345 (74565 seconds)
+WELL_FORMED = bytes.fromhex('00010180012345')
+# The same entry cut short after its flags octet: 6 of the 7 octets
+TRUNCATED = bytes.fromhex('000101800123')
+
+
+def decode(data: bytes) -> LongLivedGraceful:
+    code = Capability.CODE.LONG_LIVED_GRACEFUL_RESTART
+    capability = LongLivedGraceful.unpack_capability(LongLivedGraceful(), data, code)
+    assert isinstance(capability, LongLivedGraceful)
+    return capability
+
+
+def test_capability_code_is_71() -> None:
+    """RFC 9494 assigns capability code 71, named for logs and the JSON envelope."""
+    assert Capability.CODE.LONG_LIVED_GRACEFUL_RESTART == 71
+    assert LongLivedGraceful.ID == 71
+    assert CapabilityCode(71).name() == 'long-lived-graceful-restart'
+
+
+def test_code_71_is_registered_to_the_class() -> None:
+    """A peer sending code 71 gets this class, not the unknown capability fallback."""
+    assert Capability.klass(CapabilityCode(71)) is LongLivedGraceful
+    capability = Capability.unpack(CapabilityCode(71), {}, WELL_FORMED)
+    assert isinstance(capability, LongLivedGraceful)
+    assert capability[(AFI.ipv4, SAFI.unicast)] == LongLivedEntry(0x80, 0x012345)
+
+
+def test_well_formed_decodes_each_field() -> None:
+    capability = decode(WELL_FORMED)
+    assert list(capability.keys()) == [(AFI.ipv4, SAFI.unicast)]
+    entry = capability[(AFI.ipv4, SAFI.unicast)]
+    assert entry.flags == 0x80
+    assert entry.flags & LongLivedGraceful.FORWARDING_STATE
+    assert entry.stale_time == 0x012345
+
+
+def test_well_formed_renders_in_str_and_json() -> None:
+    capability = decode(WELL_FORMED)
+    assert str(capability) == 'LongLivedGracefulRestart(ipv4 unicast flags 0x80 stale-time 74565)'
+    rendered = json.loads(capability.json())
+    assert rendered == {
+        'name': 'long-lived-graceful-restart',
+        'families': {'ipv4/unicast': {'flags': 0x80, 'stale-time': 0x012345}},
+    }
+
+
+def test_well_formed_encodes_back_to_the_same_octets() -> None:
+    capability = decode(WELL_FORMED)
+    assert capability.extract_capability_bytes() == [WELL_FORMED]
+
+
+def test_two_families_decode_and_encode_back_in_order() -> None:
+    data = WELL_FORMED + bytes.fromhex('0002010000000a')  # then IPv6 unicast, no flags, stale time 10
+    capability = decode(data)
+    assert capability[(AFI.ipv6, SAFI.unicast)] == LongLivedEntry(0x00, 10)
+    assert capability.extract_capability_bytes() == [data]
+
+
+def test_capability_round_trips_through_an_open() -> None:
+    """Encoded into an OPEN, then decoded from it, the entries survive unchanged."""
+    capabilities = Capabilities()
+    sent = LongLivedGraceful()
+    sent.set_entry(AFI.ipv4, SAFI.unicast, 0x80, 0x012345)
+    capabilities[Capability.CODE.LONG_LIVED_GRACEFUL_RESTART] = sent
+    packed = capabilities.pack_capabilities()
+    assert packed == bytes.fromhex('0b0209470700010180012345')
+
+    received = Capabilities.unpack(packed)[Capability.CODE.LONG_LIVED_GRACEFUL_RESTART]
+    assert isinstance(received, LongLivedGraceful)
+    assert received[(AFI.ipv4, SAFI.unicast)] == LongLivedEntry(0x80, 0x012345)
+
+
+def test_truncated_value_is_a_notification() -> None:
+    """Six octets is not a whole number of seven octet entries: refuse it with a NOTIFICATION."""
+    with pytest.raises(Notify) as raised:
+        decode(TRUNCATED)
+    assert raised.value.code == 2
+    assert 'truncated' in str(raised.value)
+
+
+def test_trailing_partial_entry_is_a_notification() -> None:
+    """A whole entry followed by a fragment is still truncated, not a shorter capability."""
+    with pytest.raises(Notify) as raised:
+        decode(WELL_FORMED + b'\x00')
+    assert raised.value.code == 2

```


===== RUN a043 =====
```diff
diff --git a/src/exabgp/bgp/message/open/capability/__init__.py b/src/exabgp/bgp/message/open/capability/__init__.py
index 5c60813..6a6b91d 100644
--- a/src/exabgp/bgp/message/open/capability/__init__.py
+++ b/src/exabgp/bgp/message/open/capability/__init__.py
@@ -22,6 +22,7 @@ from exabgp.bgp.message.open.capability.pathslimit import PathsLimit
 from exabgp.bgp.message.open.capability.labels import MultipleLabels
 from exabgp.bgp.message.open.capability.asn4 import ASN4
 from exabgp.bgp.message.open.capability.graceful import Graceful
+from exabgp.bgp.message.open.capability.llgr import LongLivedGracefulRestart
 from exabgp.bgp.message.open.capability.mp import MultiProtocol
 from exabgp.bgp.message.open.capability.ms import MultiSession
 from exabgp.bgp.message.open.capability.operational import Operational
@@ -44,6 +45,7 @@ __all__ = [
     'PathsLimit',
     'ASN4',
     'Graceful',
+    'LongLivedGracefulRestart',
     'MultiProtocol',
     'MultiSession',
     'Operational',
diff --git a/src/exabgp/bgp/message/open/capability/capability.py b/src/exabgp/bgp/message/open/capability/capability.py
index ef3617f..662bf4d 100644
--- a/src/exabgp/bgp/message/open/capability/capability.py
+++ b/src/exabgp/bgp/message/open/capability/capability.py
@@ -70,6 +70,7 @@ class CapabilityCode(IntValue):
     MULTISESSION: ClassVar[int] = 0x44  # [draft-ietf-idr-bgp-multisession]
     ADD_PATH: ClassVar[int] = 0x45  # [draft-ietf-idr-add-paths]
     ENHANCED_ROUTE_REFRESH: ClassVar[int] = 0x46  # [draft-ietf-idr-bgp-enhanced-route-refresh]
+    LONG_LIVED_GRACEFUL_RESTART: ClassVar[int] = 0x47  # [RFC9494]
     PATHS_LIMIT: ClassVar[int] = 0x4C  # [draft-abraitis-idr-addpath-paths-limit]
     LINK_LOCAL_NEXTHOP: ClassVar[int] = 0x4D  # [draft-ietf-idr-linklocal-capability]
     # 78-127    Unassigned
@@ -103,6 +104,7 @@ class CapabilityCode(IntValue):
         MULTISESSION: 'multi-session',
         ADD_PATH: 'add-path',
         ENHANCED_ROUTE_REFRESH: 'enhanced-route-refresh',
+        LONG_LIVED_GRACEFUL_RESTART: 'long-lived-graceful-restart',
         PATHS_LIMIT: 'paths-limit',
         MULTIPLE_LABELS: 'multiple-labels',
         LINK_LOCAL_NEXTHOP: 'link-local-nexthop',
@@ -150,6 +152,7 @@ class CapabilityCodes:
     MULTISESSION: ClassVar[CapabilityCode] =             CapabilityCode(CapabilityCode.MULTISESSION)
     ADD_PATH: ClassVar[CapabilityCode] =                 CapabilityCode(CapabilityCode.ADD_PATH)
     ENHANCED_ROUTE_REFRESH: ClassVar[CapabilityCode] =   CapabilityCode(CapabilityCode.ENHANCED_ROUTE_REFRESH)
+    LONG_LIVED_GRACEFUL_RESTART: ClassVar[CapabilityCode] = CapabilityCode(CapabilityCode.LONG_LIVED_GRACEFUL_RESTART)
     PATHS_LIMIT: ClassVar[CapabilityCode] =              CapabilityCode(CapabilityCode.PATHS_LIMIT)
     MULTIPLE_LABELS: ClassVar[CapabilityCode] =          CapabilityCode(CapabilityCode.MULTIPLE_LABELS)
     LINK_LOCAL_NEXTHOP: ClassVar[CapabilityCode] =       CapabilityCode(CapabilityCode.LINK_LOCAL_NEXTHOP)
diff --git a/src/exabgp/bgp/message/open/capability/llgr.py b/src/exabgp/bgp/message/open/capability/llgr.py
new file mode 100644
index 0000000..783c9f6
--- /dev/null
+++ b/src/exabgp/bgp/message/open/capability/llgr.py
@@ -0,0 +1,95 @@
+"""llgr.py
+
+Long-Lived Graceful Restart capability (RFC 9494, capability code 71).
+
+The value is zero or more tuples of AFI (2 octets), SAFI (1 octet), Flags (1 octet) and
+Long-Lived Stale Time (3 octets). RFC 9494 section 3.1 defines one flag, F, the most
+significant bit of the Flags octet (0x80), and tells the receiver to ignore the reserved
+bits. The flags octet is kept whole so that encoding gives back what was received.
+
+This class decodes and displays what a peer sends. Nothing here changes route handling
+and nothing is advertised from configuration.
+
+License: 3-clause BSD. (See the COPYRIGHT file)
+"""
+
+from __future__ import annotations
+
+from typing import ClassVar
+
+from exabgp.bgp.message.notification import Notify
+from exabgp.bgp.message.open.capability.capability import Capability, CapabilityCode, CapabilityDict
+from exabgp.logger import log, lazymsg
+from exabgp.protocol.family import AFI, SAFI, FamilyTuple
+from exabgp.util.types import Buffer
+
+
+class LongLivedGracefulRestart(CapabilityDict[FamilyTuple, tuple[int, int]]):
+    """Per family: the flags octet and the Long-Lived Stale Time in seconds."""
+
+    ID: ClassVar = Capability.CODE.LONG_LIVED_GRACEFUL_RESTART
+    ENTRY_SIZE: ClassVar[int] = 7
+    FLAGS_MAX: ClassVar[int] = 0xFF
+    STALE_TIME_MAX: ClassVar[int] = 0xFFFFFF  # 24 bits, about 194 days
+    # RFC 9494 section 3.1: the F bit is the most significant bit of the Flags octet
+    FORWARDING_STATE: ClassVar[int] = 0x80
+
+    def set_entry(self, afi: AFI, safi: SAFI, flags: int, stale_time: int) -> None:
+        if not (0 <= flags <= LongLivedGracefulRestart.FLAGS_MAX):
+            raise ValueError(f'LLGR flags must be 0-255, got {flags}')
+        if not (0 <= stale_time <= LongLivedGracefulRestart.STALE_TIME_MAX):
+            raise ValueError(f'LLGR stale time must be 0-16777215 seconds, got {stale_time}')
+        self[(afi, safi)] = (flags, stale_time)
+
+    def __str__(self) -> str:
+        entries = ', '.join(
+            f'{afi} {safi} flags {flags:#04x} stale-time {stale_time}'
+            for (afi, safi), (flags, stale_time) in self.items()
+        )
+        return f'LongLivedGracefulRestart({entries})'
+
+    def json(self) -> str:
+        families = ', '.join(
+            '"{}/{}": {{ "forwarding": {}, "stale-time": {} }}'.format(
+                afi,
+                safi,
+                'true' if flags & LongLivedGracefulRestart.FORWARDING_STATE else 'false',
+                stale_time,
+            )
+            for (afi, safi), (flags, stale_time) in self.items()
+        )
+        return '{{ "name": "long-lived-graceful-restart", "families": {{ {} }} }}'.format(families)
+
+    def extract_capability_bytes(self) -> list[bytes]:
+        entries = [
+            afi.pack_afi() + safi.pack_safi() + bytes([flags]) + stale_time.to_bytes(3, 'big')
+            for (afi, safi), (flags, stale_time) in self.items()
+        ]
+        return [b''.join(entries)]
+
+    @classmethod
+    def unpack_capability(cls, instance: Capability, data: Buffer, capability: CapabilityCode) -> Capability:
+        assert isinstance(instance, LongLivedGracefulRestart)
+        if len(instance) > 0:
+            log.debug(lazymsg('capability.long-lived-graceful-restart.duplicate action=replace'), 'parser')
+            instance.clear()
+        # Check the length before reading any entry: a partial entry is a malformed capability
+        if len(data) % cls.ENTRY_SIZE:
+            raise Notify(
+                2,
+                0,
+                f'Long-Lived Graceful Restart capability truncated: {len(data)} octets is not a multiple of '
+                f'{cls.ENTRY_SIZE} octets per entry',
+            )
+        view = memoryview(data)
+        for offset in range(0, len(view), cls.ENTRY_SIZE):
+            entry = view[offset : offset + cls.ENTRY_SIZE]
+            afi = AFI.unpack_afi(entry[:2])
+            safi = SAFI.unpack_safi(entry[2:3])
+            flags = entry[3]
+            stale_time = int.from_bytes(entry[4:7], 'big')
+            instance.set_entry(afi, safi, flags, stale_time)
+        return instance
+
+
+Capability.register()(LongLivedGracefulRestart)
diff --git a/tests/unit/test_llgr_capability.py b/tests/unit/test_llgr_capability.py
new file mode 100644
index 0000000..0c6e120
--- /dev/null
+++ b/tests/unit/test_llgr_capability.py
@@ -0,0 +1,87 @@
+#!/usr/bin/env python3
+# encoding: utf-8
+"""test_llgr_capability.py
+
+RFC 9494 Long-Lived Graceful Restart capability (code 71).
+
+Each entry is AFI (2 octets), SAFI (1 octet), Flags (1 octet, F is 0x80) and a 24 bit
+Long-Lived Stale Time in seconds: seven octets per entry. A well formed value decodes,
+renders in str() and json(), and encodes back to the same octets. A value which ends
+part way through an entry is malformed and answered with a NOTIFICATION.
+
+License: 3-clause BSD
+"""
+
+import json
+
+import pytest
+
+from exabgp.bgp.message.notification import Notify
+from exabgp.bgp.message.open.capability.capabilities import Capabilities
+from exabgp.bgp.message.open.capability.capability import Capability
+from exabgp.bgp.message.open.capability.capability import CapabilityCode
+from exabgp.bgp.message.open.capability.llgr import LongLivedGracefulRestart
+from exabgp.protocol.family import AFI, SAFI
+
+# IPv4 unicast, F set, stale time 3600; IPv6 unicast, F clear, stale time 0xFFFFFF
+WELL_FORMED = bytes.fromhex('00010180000e10' '00020100ffffff')
+
+
+def decode(data: bytes) -> LongLivedGracefulRestart:
+    decoded = LongLivedGracefulRestart.unpack_capability(
+        LongLivedGracefulRestart(), data, Capability.CODE.LONG_LIVED_GRACEFUL_RESTART
+    )
+    assert isinstance(decoded, LongLivedGracefulRestart)
+    return decoded
+
+
+def test_code_is_71_and_named() -> None:
+    assert Capability.CODE.LONG_LIVED_GRACEFUL_RESTART == 71
+    assert LongLivedGracefulRestart.ID == 71
+    assert CapabilityCode(71).name() == 'long-lived-graceful-restart'
+
+
+def test_well_formed_capability_decodes_every_entry() -> None:
+    llgr = decode(WELL_FORMED)
+    assert len(llgr) == 2
+    assert llgr[(AFI.ipv4, SAFI.unicast)] == (0x80, 3600)
+    assert llgr[(AFI.ipv6, SAFI.unicast)] == (0x00, 0xFFFFFF)
+
+
+def test_well_formed_capability_renders_str_and_json() -> None:
+    llgr = decode(WELL_FORMED)
+    assert 'flags 0x80 stale-time 3600' in str(llgr)
+
+    body = json.loads(llgr.json())
+    assert body['name'] == 'long-lived-graceful-restart'
+    assert body['families']['ipv4/unicast'] == {'forwarding': True, 'stale-time': 3600}
+    assert body['families']['ipv6/unicast'] == {'forwarding': False, 'stale-time': 16777215}
+
+
+def test_well_formed_capability_encodes_back_to_the_same_octets() -> None:
+    assert decode(WELL_FORMED).extract_capability_bytes() == [WELL_FORMED]
+
+
+def test_well_formed_capability_survives_an_open_round_trip() -> None:
+    llgr = decode(WELL_FORMED)
+    capabilities = Capabilities()
+    capabilities[Capability.CODE.LONG_LIVED_GRACEFUL_RESTART] = llgr
+    decoded = Capabilities.unpack(capabilities.pack_capabilities())
+    assert decoded[Capability.CODE.LONG_LIVED_GRACEFUL_RESTART] == llgr
+
+
+def test_empty_capability_is_zero_tuples() -> None:
+    assert len(decode(b'')) == 0
+
+
+@pytest.mark.parametrize(
+    'data',
+    [
+        WELL_FORMED[:5],  # first entry cut short
+        WELL_FORMED[:12],  # second entry cut short
+        WELL_FORMED + b'\x00',  # one stray octet after a complete entry
+    ],
+)
+def test_truncated_capability_is_refused(data: bytes) -> None:
+    with pytest.raises(Notify):
+        decode(data)

```


===== RUN a042 =====
```diff
diff --git a/src/exabgp/bgp/message/open/capability/__init__.py b/src/exabgp/bgp/message/open/capability/__init__.py
index 5c60813..85c3b17 100644
--- a/src/exabgp/bgp/message/open/capability/__init__.py
+++ b/src/exabgp/bgp/message/open/capability/__init__.py
@@ -22,6 +22,7 @@ from exabgp.bgp.message.open.capability.pathslimit import PathsLimit
 from exabgp.bgp.message.open.capability.labels import MultipleLabels
 from exabgp.bgp.message.open.capability.asn4 import ASN4
 from exabgp.bgp.message.open.capability.graceful import Graceful
+from exabgp.bgp.message.open.capability.llgr import LongLivedGraceful
 from exabgp.bgp.message.open.capability.mp import MultiProtocol
 from exabgp.bgp.message.open.capability.ms import MultiSession
 from exabgp.bgp.message.open.capability.operational import Operational
@@ -44,6 +45,7 @@ __all__ = [
     'PathsLimit',
     'ASN4',
     'Graceful',
+    'LongLivedGraceful',
     'MultiProtocol',
     'MultiSession',
     'Operational',
diff --git a/src/exabgp/bgp/message/open/capability/capability.py b/src/exabgp/bgp/message/open/capability/capability.py
index 89e00a2..4188f9c 100644
--- a/src/exabgp/bgp/message/open/capability/capability.py
+++ b/src/exabgp/bgp/message/open/capability/capability.py
@@ -70,6 +70,7 @@ class CapabilityCode(IntValue):
     MULTISESSION: ClassVar[int] = 0x44  # [draft-ietf-idr-bgp-multisession]
     ADD_PATH: ClassVar[int] = 0x45  # [draft-ietf-idr-add-paths]
     ENHANCED_ROUTE_REFRESH: ClassVar[int] = 0x46  # [draft-ietf-idr-bgp-enhanced-route-refresh]
+    LONG_LIVED_GRACEFUL_RESTART: ClassVar[int] = 0x47  # [RFC9494]
     PATHS_LIMIT: ClassVar[int] = 0x4C  # [draft-abraitis-idr-addpath-paths-limit]
     LINK_LOCAL_NEXTHOP: ClassVar[int] = 0x4D  # [draft-ietf-idr-linklocal-capability]
     # 78-127    Unassigned
@@ -103,6 +104,7 @@ class CapabilityCode(IntValue):
         MULTISESSION: 'multi-session',
         ADD_PATH: 'add-path',
         ENHANCED_ROUTE_REFRESH: 'enhanced-route-refresh',
+        LONG_LIVED_GRACEFUL_RESTART: 'long-lived-graceful-restart',
         PATHS_LIMIT: 'paths-limit',
         MULTIPLE_LABELS: 'multiple-labels',
         LINK_LOCAL_NEXTHOP: 'link-local-nexthop',
@@ -150,6 +152,7 @@ class CapabilityCodes:
     MULTISESSION: ClassVar[CapabilityCode] =             CapabilityCode(CapabilityCode.MULTISESSION)
     ADD_PATH: ClassVar[CapabilityCode] =                 CapabilityCode(CapabilityCode.ADD_PATH)
     ENHANCED_ROUTE_REFRESH: ClassVar[CapabilityCode] =   CapabilityCode(CapabilityCode.ENHANCED_ROUTE_REFRESH)
+    LONG_LIVED_GRACEFUL_RESTART: ClassVar[CapabilityCode] = CapabilityCode(CapabilityCode.LONG_LIVED_GRACEFUL_RESTART)
     PATHS_LIMIT: ClassVar[CapabilityCode] =              CapabilityCode(CapabilityCode.PATHS_LIMIT)
     MULTIPLE_LABELS: ClassVar[CapabilityCode] =          CapabilityCode(CapabilityCode.MULTIPLE_LABELS)
     LINK_LOCAL_NEXTHOP: ClassVar[CapabilityCode] =       CapabilityCode(CapabilityCode.LINK_LOCAL_NEXTHOP)
diff --git a/src/exabgp/bgp/message/open/capability/llgr.py b/src/exabgp/bgp/message/open/capability/llgr.py
new file mode 100644
index 0000000..41474d6
--- /dev/null
+++ b/src/exabgp/bgp/message/open/capability/llgr.py
@@ -0,0 +1,117 @@
+"""llgr.py
+
+Long-Lived Graceful Restart capability (RFC 9494, capability code 71).
+
+License: 3-clause BSD. (See the COPYRIGHT file)
+"""
+
+from __future__ import annotations
+
+from typing import ClassVar, Iterable
+
+from exabgp.protocol.family import AFI, SAFI, FamilyTuple
+from exabgp.bgp.message.open.capability.capability import Capability, CapabilityDict
+from exabgp.bgp.message.open.capability.capability import CapabilityCode
+from exabgp.bgp.message.notification import Notify
+from exabgp.logger import log, lazymsg
+from exabgp.util.types import Buffer
+
+# ============================================== LongLivedGraceful (Restart)
+# RFC 9494 - https://www.rfc-editor.org/rfc/rfc9494
+#
+# The value is a sequence of entries, one per family:
+#
+# +--------------------------------------------------+
+# | Address Family Identifier (16 bits)              |
+# +--------------------------------------------------+
+# | Subsequent Address Family Identifier (8 bits)    |
+# +--------------------------------------------------+
+# | Flags for Address Family (8 bits)                |
+# +--------------------------------------------------+
+# | Long-lived Stale Time (24 bits)                  |
+# +--------------------------------------------------+
+#
+# Only parsed and displayed: no configuration builds it and route handling ignores it.
+
+
+class LongLivedGraceful(CapabilityDict[FamilyTuple, tuple[int, int]]):
+    ID: ClassVar = Capability.CODE.LONG_LIVED_GRACEFUL_RESTART
+
+    ENTRY_SIZE: ClassVar[int] = 7
+    # The capability length is a single octet, so one instance holds at most this many entries
+    MAX_FAMILIES: ClassVar[int] = 0xFF // ENTRY_SIZE
+    TIME_MAX: ClassVar[int] = 0xFFFFFF
+
+    # RFC 9494 4: the most significant bit of the flags is F, the Forwarding State
+    FORWARDING_STATE: ClassVar[int] = 0x80
+
+    def set(self, protos: Iterable[tuple[AFI, SAFI, int, int]]) -> LongLivedGraceful:
+        for afi, safi, flags, stale_time in protos:
+            assert 0 <= flags <= 0xFF, f'flags must fit one octet, got {flags}'
+            assert 0 <= stale_time <= LongLivedGraceful.TIME_MAX, f'stale time must fit 24 bits, got {stale_time}'
+            self[(afi, safi)] = (flags, stale_time)
+        return self
+
+    def families(self) -> Iterable[FamilyTuple]:
+        return self.keys()
+
+    def extract_capability_bytes(self) -> list[bytes]:
+        entries = [
+            afi.pack_afi() + safi.pack_safi() + bytes([flags]) + stale_time.to_bytes(3, 'big')
+            for (afi, safi), (flags, stale_time) in self.items()
+        ]
+        return [b''.join(entries)]
+
+    def __str__(self) -> str:
+        families = ' '.join(
+            f'{afi}/{safi}={hex(flags)}/{stale_time}' for (afi, safi), (flags, stale_time) in self.items()
+        )
+        return f'Long-Lived Graceful Restart {families}'.rstrip()
+
+    def json(self) -> str:
+        families = ', '.join(
+            '"{}/{}": {{ "forwarding": {}, "flags": {}, "stale-time": {} }}'.format(
+                afi,
+                safi,
+                'true' if flags & LongLivedGraceful.FORWARDING_STATE else 'false',
+                flags,
+                stale_time,
+            )
+            for (afi, safi), (flags, stale_time) in self.items()
+        )
+        return f'{{ "name": "long-lived-graceful-restart", "families": {{ {families} }} }}'
+
+    @classmethod
+    def unpack_capability(cls, instance: Capability, data: Buffer, capability: CapabilityCode) -> Capability:  # pylint: disable=W0613
+        assert isinstance(instance, LongLivedGraceful)
+        if len(instance) > 0:
+            log.debug(lazymsg('capability.long-lived-graceful-restart.duplicate action=replace'), 'parser')
+            instance.clear()
+        view = memoryview(data)
+        if len(view) % cls.ENTRY_SIZE:
+            raise Notify(
+                2,
+                0,
+                f'Long-Lived Graceful Restart capability truncated: '
+                f'need {cls.ENTRY_SIZE} bytes per family, got {len(view)}',
+            )
+        families: list[tuple[AFI, SAFI, int, int]] = []
+        for offset in range(0, len(view), cls.ENTRY_SIZE):
+            if len(families) >= cls.MAX_FAMILIES:
+                # longer than one capability can be, only reachable by a caller which is not
+                # reading an OPEN: keep what one instance holds rather than end the session
+                log.debug(
+                    lazymsg('capability.long-lived-graceful-restart.capacity families={n}', n=cls.MAX_FAMILIES),
+                    'parser',
+                )
+                break
+            entry = view[offset : offset + cls.ENTRY_SIZE]
+            afi = AFI.unpack_afi(entry[:2])
+            safi = SAFI.unpack_safi(entry[2:3])
+            flags = entry[3]
+            stale_time = int.from_bytes(entry[4:7], 'big')
+            families.append((afi, safi, flags, stale_time))
+        return instance.set(families)
+
+
+Capability.register()(LongLivedGraceful)
diff --git a/tests/unit/test_llgr_capability.py b/tests/unit/test_llgr_capability.py
new file mode 100644
index 0000000..0010525
--- /dev/null
+++ b/tests/unit/test_llgr_capability.py
@@ -0,0 +1,82 @@
+#!/usr/bin/env python3
+# encoding: utf-8
+"""test_llgr_capability.py
+
+RFC 9494 Long-Lived Graceful Restart capability (code 71).
+
+The value is a sequence of seven octet entries: AFI (2), SAFI (1), flags (1) and a
+24-bit long-lived stale time (3). ExaBGP only parses and displays what a peer sends,
+so the tests hold the decoding of a well formed capability, its round trip, its
+str() and JSON rendering, and the NOTIFICATION for a truncated one.
+
+License: 3-clause BSD
+"""
+
+import json
+
+import pytest
+
+from exabgp.bgp.message.notification import Notify
+from exabgp.bgp.message.open.capability.capabilities import Capabilities
+from exabgp.bgp.message.open.capability.capability import Capability
+from exabgp.bgp.message.open.capability.capability import CapabilityCode
+from exabgp.bgp.message.open.capability.llgr import LongLivedGraceful
+from exabgp.protocol.family import AFI, SAFI
+
+# ipv4/unicast with F set and a stale time of 3600, ipv6/unicast without F and the largest time
+VALUE = bytes.fromhex('00010180000e10' + '00020100ffffff')
+
+
+def test_capability_code_is_seventy_one() -> None:
+    assert Capability.CODE.LONG_LIVED_GRACEFUL_RESTART == 71
+    assert LongLivedGraceful.ID == 71
+    assert CapabilityCode(71).name() == 'long-lived-graceful-restart'
+    assert Capability.klass(Capability.CODE.LONG_LIVED_GRACEFUL_RESTART) is LongLivedGraceful
+
+
+def test_well_formed_capability_decodes() -> None:
+    parsed = LongLivedGraceful.unpack_capability(
+        LongLivedGraceful(), memoryview(VALUE), Capability.CODE.LONG_LIVED_GRACEFUL_RESTART
+    )
+    assert isinstance(parsed, LongLivedGraceful)
+    assert parsed[(AFI.ipv4, SAFI.unicast)] == (0x80, 3600)
+    assert parsed[(AFI.ipv6, SAFI.unicast)] == (0x00, 0xFFFFFF)
+    assert len(parsed) == 2
+
+    assert parsed.extract_capability_bytes() == [VALUE]
+
+    assert str(parsed) == 'Long-Lived Graceful Restart ipv4/unicast=0x80/3600 ipv6/unicast=0x0/16777215'
+    decoded = json.loads(parsed.json())
+    assert decoded['name'] == 'long-lived-graceful-restart'
+    assert decoded['families']['ipv4/unicast'] == {'forwarding': True, 'flags': 128, 'stale-time': 3600}
+    assert decoded['families']['ipv6/unicast'] == {'forwarding': False, 'flags': 0, 'stale-time': 16777215}
+
+
+def test_well_formed_capability_decodes_from_open_parameters() -> None:
+    """Through the OPEN optional parameter parser: no longer an unknown capability."""
+    tlv = bytes([71, len(VALUE)]) + VALUE
+    parameter = bytes([2, len(tlv)]) + tlv
+    capabilities = Capabilities.unpack(bytes([len(parameter)]) + parameter)
+    llgr = capabilities[Capability.CODE.LONG_LIVED_GRACEFUL_RESTART]
+    assert isinstance(llgr, LongLivedGraceful)
+    assert llgr[(AFI.ipv4, SAFI.unicast)] == (0x80, 3600)
+    assert 'Long-Lived Graceful Restart' in str(capabilities)
+
+
+def test_empty_capability_has_no_family() -> None:
+    parsed = LongLivedGraceful.unpack_capability(
+        LongLivedGraceful(), memoryview(b''), Capability.CODE.LONG_LIVED_GRACEFUL_RESTART
+    )
+    assert isinstance(parsed, LongLivedGraceful)
+    assert len(parsed) == 0
+    assert json.loads(parsed.json()) == {'name': 'long-lived-graceful-restart', 'families': {}}
+
+
+@pytest.mark.parametrize('length', [1, 6, 8, 13])
+def test_truncated_capability_is_refused(length: int) -> None:
+    with pytest.raises(Notify) as raised:
+        LongLivedGraceful.unpack_capability(
+            LongLivedGraceful(), memoryview(VALUE[:length]), Capability.CODE.LONG_LIVED_GRACEFUL_RESTART
+        )
+    assert raised.value.code == 2
+    assert raised.value.subcode == 0

```


===== RUN a051 =====
```diff
diff --git a/src/exabgp/bgp/message/open/capability/__init__.py b/src/exabgp/bgp/message/open/capability/__init__.py
index 5c60813..85c3b17 100644
--- a/src/exabgp/bgp/message/open/capability/__init__.py
+++ b/src/exabgp/bgp/message/open/capability/__init__.py
@@ -22,6 +22,7 @@ from exabgp.bgp.message.open.capability.pathslimit import PathsLimit
 from exabgp.bgp.message.open.capability.labels import MultipleLabels
 from exabgp.bgp.message.open.capability.asn4 import ASN4
 from exabgp.bgp.message.open.capability.graceful import Graceful
+from exabgp.bgp.message.open.capability.llgr import LongLivedGraceful
 from exabgp.bgp.message.open.capability.mp import MultiProtocol
 from exabgp.bgp.message.open.capability.ms import MultiSession
 from exabgp.bgp.message.open.capability.operational import Operational
@@ -44,6 +45,7 @@ __all__ = [
     'PathsLimit',
     'ASN4',
     'Graceful',
+    'LongLivedGraceful',
     'MultiProtocol',
     'MultiSession',
     'Operational',
diff --git a/src/exabgp/bgp/message/open/capability/capability.py b/src/exabgp/bgp/message/open/capability/capability.py
index ffec782..9b35ccc 100644
--- a/src/exabgp/bgp/message/open/capability/capability.py
+++ b/src/exabgp/bgp/message/open/capability/capability.py
@@ -70,6 +70,7 @@ class CapabilityCode(IntValue):
     MULTISESSION: ClassVar[int] = 0x44  # [draft-ietf-idr-bgp-multisession]
     ADD_PATH: ClassVar[int] = 0x45  # [draft-ietf-idr-add-paths]
     ENHANCED_ROUTE_REFRESH: ClassVar[int] = 0x46  # [draft-ietf-idr-bgp-enhanced-route-refresh]
+    LONG_LIVED_GRACEFUL_RESTART: ClassVar[int] = 0x47  # [RFC9494]
     PATHS_LIMIT: ClassVar[int] = 0x4C  # [draft-abraitis-idr-addpath-paths-limit]
     LINK_LOCAL_NEXTHOP: ClassVar[int] = 0x4D  # [draft-ietf-idr-linklocal-capability]
     # 78-127    Unassigned
@@ -103,6 +104,7 @@ class CapabilityCode(IntValue):
         MULTISESSION: 'multi-session',
         ADD_PATH: 'add-path',
         ENHANCED_ROUTE_REFRESH: 'enhanced-route-refresh',
+        LONG_LIVED_GRACEFUL_RESTART: 'long-lived-graceful-restart',
         PATHS_LIMIT: 'paths-limit',
         MULTIPLE_LABELS: 'multiple-labels',
         LINK_LOCAL_NEXTHOP: 'link-local-nexthop',
@@ -150,6 +152,7 @@ class CapabilityCodes:
     MULTISESSION: ClassVar[CapabilityCode] =             CapabilityCode(CapabilityCode.MULTISESSION)
     ADD_PATH: ClassVar[CapabilityCode] =                 CapabilityCode(CapabilityCode.ADD_PATH)
     ENHANCED_ROUTE_REFRESH: ClassVar[CapabilityCode] =   CapabilityCode(CapabilityCode.ENHANCED_ROUTE_REFRESH)
+    LONG_LIVED_GRACEFUL_RESTART: ClassVar[CapabilityCode] = CapabilityCode(CapabilityCode.LONG_LIVED_GRACEFUL_RESTART)
     PATHS_LIMIT: ClassVar[CapabilityCode] =              CapabilityCode(CapabilityCode.PATHS_LIMIT)
     MULTIPLE_LABELS: ClassVar[CapabilityCode] =          CapabilityCode(CapabilityCode.MULTIPLE_LABELS)
     LINK_LOCAL_NEXTHOP: ClassVar[CapabilityCode] =       CapabilityCode(CapabilityCode.LINK_LOCAL_NEXTHOP)
diff --git a/src/exabgp/bgp/message/open/capability/llgr.py b/src/exabgp/bgp/message/open/capability/llgr.py
new file mode 100644
index 0000000..cc71020
--- /dev/null
+++ b/src/exabgp/bgp/message/open/capability/llgr.py
@@ -0,0 +1,120 @@
+"""llgr.py
+
+Long-Lived Graceful Restart capability (RFC 9494, capability code 71).
+
+The value is zero or more seven octet tuples, one per family:
+
+    +--------------------------------------------------+
+    | Address Family Identifier (16 bits)              |
+    +--------------------------------------------------+
+    | Subsequent Address Family Identifier (8 bits)    |
+    +--------------------------------------------------+
+    | Flags for Address Family (8 bits)                |
+    +--------------------------------------------------+
+    | Long-lived Stale Time (24 bits)                  |
+    +--------------------------------------------------+
+
+Only the most significant flag bit, F, is defined. The others are reserved and are
+ignored on receipt. ExaBGP decodes and displays what a peer sends: it neither
+advertises the capability nor changes how routes are handled because of it.
+
+License: 3-clause BSD. (See the COPYRIGHT file)
+"""
+
+from __future__ import annotations
+
+from typing import ClassVar, Iterable
+
+from exabgp.protocol.family import AFI, SAFI, FamilyTuple
+from exabgp.bgp.message.open.capability.capability import Capability, CapabilityDict
+from exabgp.bgp.message.open.capability.capability import CapabilityCode
+from exabgp.bgp.message.notification import Notify
+from exabgp.logger import log, lazymsg
+
+
+class LongLivedGraceful(CapabilityDict[FamilyTuple, tuple[int, int]]):
+    """RFC 9494 capability: per family, the flags octet and the long-lived stale time."""
+
+    ID: ClassVar = Capability.CODE.LONG_LIVED_GRACEFUL_RESTART
+
+    # AFI(2) + SAFI(1) + flags(1) + stale time(3)
+    ENTRY_SIZE: ClassVar[int] = 7
+    # A capability length is one octet, so one instance cannot hold more than this
+    MAX_FAMILIES: ClassVar[int] = 0xFF // ENTRY_SIZE
+
+    # RFC 9494 3: F, the Forwarding State bit, is the only flag defined
+    FORWARDING_STATE: ClassVar[int] = 0x80
+    STALE_TIME_MAX: ClassVar[int] = 0xFFFFFF
+
+    def set(self, protos: Iterable[tuple[AFI, SAFI, int, int]]) -> LongLivedGraceful:
+        for afi, safi, flags, stale_time in protos:
+            assert 0 <= stale_time <= LongLivedGraceful.STALE_TIME_MAX, 'the stale time is 24 bits'
+            # reserved flag bits "MUST be ignored by the receiver"
+            self[(afi, safi)] = (flags & LongLivedGraceful.FORWARDING_STATE, stale_time)
+        return self
+
+    def extract_capability_bytes(self) -> list[bytes]:
+        entries = [
+            afi.pack_afi() + safi.pack_safi() + bytes([flags]) + stale_time.to_bytes(3, 'big')
+            for (afi, safi), (flags, stale_time) in self.items()
+        ]
+        return [b''.join(entries)]
+
+    def __str__(self) -> str:
+        entries = ' '.join(
+            f'{afi}/{safi}=flags {hex(flags)} stale-time {stale_time}'
+            for (afi, safi), (flags, stale_time) in self.items()
+        )
+        return f'Long-Lived Graceful Restart {entries}'.rstrip()
+
+    def json(self) -> str:
+        families = ', '.join(
+            '"{}/{}": {{ "flags": [{}], "stale-time": {} }}'.format(
+                afi,
+                safi,
+                ' "forwarding" ' if flags & LongLivedGraceful.FORWARDING_STATE else '',
+                stale_time,
+            )
+            for (afi, safi), (flags, stale_time) in self.items()
+        )
+        return '{{ "name": "long-lived graceful restart", "address-family-flags": {{ {} }} }}'.format(families)
+
+    @classmethod
+    def unpack_capability(cls, instance: Capability, data, capability: CapabilityCode) -> Capability:  # pylint: disable=W0613
+        assert isinstance(instance, LongLivedGraceful)
+        view = memoryview(data)
+        if len(view) % cls.ENTRY_SIZE:
+            # The peer controls this length, so it is checked, never asserted.
+            raise Notify(
+                2,
+                0,
+                f'Long-Lived Graceful Restart capability truncated: {len(view)} bytes is not '
+                f'a multiple of {cls.ENTRY_SIZE}',
+            )
+        if len(instance) > 0:
+            log.debug(lazymsg('capability.long_lived_graceful_restart.duplicate action=merge'), 'parser')
+
+        protos: list[tuple[AFI, SAFI, int, int]] = []
+        seen: set[FamilyTuple] = set(instance.keys())
+        # bounded: the length was checked above, and a capability length is one octet
+        for index in range(len(view) // cls.ENTRY_SIZE):
+            entry = view[index * cls.ENTRY_SIZE : (index + 1) * cls.ENTRY_SIZE]
+            afi = AFI.unpack_afi(entry[:2])
+            safi = SAFI.unpack_safi(entry[2:3])
+            family = (afi, safi)
+            if family in seen:
+                log.debug(lazymsg('capability.long_lived_graceful_restart.duplicate family={f}', f=family), 'parser')
+                continue
+            if len(seen) >= cls.MAX_FAMILIES:
+                log.debug(
+                    lazymsg('capability.long_lived_graceful_restart.capacity families={n}', n=cls.MAX_FAMILIES),
+                    'parser',
+                )
+                break
+            seen.add(family)
+            stale_time = int.from_bytes(entry[4:7], 'big')
+            protos.append((afi, safi, entry[3], stale_time))
+        return instance.set(protos)
+
+
+Capability.register()(LongLivedGraceful)
diff --git a/tests/unit/test_llgr_capability.py b/tests/unit/test_llgr_capability.py
new file mode 100644
index 0000000..2da4e3e
--- /dev/null
+++ b/tests/unit/test_llgr_capability.py
@@ -0,0 +1,88 @@
+"""The Long-Lived Graceful Restart capability (RFC 9494, capability code 71).
+
+Each entry is AFI(2), SAFI(1), a flags octet and a 24 bit long-lived stale time. ExaBGP
+only decodes and displays what a peer sends, so these check the decoding, that the
+capability encodes back to the bytes it came from, and that a truncated one is refused.
+"""
+
+from __future__ import annotations
+
+import json
+from struct import pack
+
+import pytest
+
+from exabgp.bgp.message.notification import Notify
+from exabgp.bgp.message.open.capability import Capabilities
+from exabgp.bgp.message.open.capability.capability import Capability
+from exabgp.bgp.message.open.capability.llgr import LongLivedGraceful
+from exabgp.protocol.family import AFI, SAFI
+
+LLGR = 71
+OPTIONAL_CAPABILITIES = 2
+
+# ipv4/unicast, F set and a reserved bit too, which is ignored on receipt, one hour
+IPV4_ENTRY = pack('!HBB', 1, 1, 0x81) + (3600).to_bytes(3, 'big')
+# ipv6/unicast, no flag, the largest stale time 24 bits hold
+IPV6_ENTRY = pack('!HBB', 2, 1, 0x00) + (0xFFFFFF).to_bytes(3, 'big')
+VALUE = IPV4_ENTRY + IPV6_ENTRY
+
+
+def _optional_parameters(code: int, value: bytes) -> bytes:
+    capability = bytes([code, len(value)]) + value
+    parameter = bytes([OPTIONAL_CAPABILITIES, len(capability)]) + capability
+    return bytes([len(parameter)]) + parameter
+
+
+def test_llgr_code_is_registered() -> None:
+    assert Capability.CODE.LONG_LIVED_GRACEFUL_RESTART == LLGR
+    assert Capability.CODE.LONG_LIVED_GRACEFUL_RESTART.name() == 'long-lived-graceful-restart'
+    assert Capability.klass(Capability.CODE.LONG_LIVED_GRACEFUL_RESTART) is LongLivedGraceful
+
+
+def test_llgr_decodes_well_formed() -> None:
+    capabilities = Capabilities.unpack(_optional_parameters(LLGR, VALUE))
+
+    llgr = capabilities[Capability.CODE.LONG_LIVED_GRACEFUL_RESTART]
+    assert isinstance(llgr, LongLivedGraceful)
+    assert llgr[(AFI.ipv4, SAFI.unicast)] == (LongLivedGraceful.FORWARDING_STATE, 3600)
+    assert llgr[(AFI.ipv6, SAFI.unicast)] == (0, 0xFFFFFF)
+
+    # the reserved flag bit is dropped, everything else goes back out as it came in
+    expected = pack('!HBB', 1, 1, 0x80) + (3600).to_bytes(3, 'big') + IPV6_ENTRY
+    assert llgr.extract_capability_bytes() == [expected]
+
+    text = str(llgr)
+    assert 'Long-Lived Graceful Restart' in text
+    assert 'ipv4/unicast=flags 0x80 stale-time 3600' in text
+    assert 'ipv6/unicast=flags 0x0 stale-time 16777215' in text
+
+    decoded = json.loads(llgr.json())
+    assert decoded['name'] == 'long-lived graceful restart'
+    assert decoded['address-family-flags']['ipv4/unicast'] == {'flags': ['forwarding'], 'stale-time': 3600}
+    assert decoded['address-family-flags']['ipv6/unicast'] == {'flags': [], 'stale-time': 0xFFFFFF}
+
+
+def test_llgr_decodes_empty() -> None:
+    capabilities = Capabilities.unpack(_optional_parameters(LLGR, b''))
+
+    llgr = capabilities[Capability.CODE.LONG_LIVED_GRACEFUL_RESTART]
+    assert isinstance(llgr, LongLivedGraceful)
+    assert len(llgr) == 0
+    assert llgr.extract_capability_bytes() == [b'']
+    assert json.loads(llgr.json())['address-family-flags'] == {}
+
+
+@pytest.mark.parametrize('cut', [1, 3, 6])
+def test_llgr_truncated_is_refused(cut: int) -> None:
+    truncated = VALUE[: len(VALUE) - cut]
+
+    with pytest.raises(Notify) as raised:
+        LongLivedGraceful.unpack_capability(
+            LongLivedGraceful(), truncated, Capability.CODE.LONG_LIVED_GRACEFUL_RESTART
+        )
+    assert raised.value.code == 2
+    assert raised.value.subcode == 0
+
+    with pytest.raises(Notify):
+        Capabilities.unpack(_optional_parameters(LLGR, truncated))

```


===== RUN a053 =====
```diff
diff --git a/src/exabgp/bgp/message/open/capability/__init__.py b/src/exabgp/bgp/message/open/capability/__init__.py
index 5c60813..85c3b17 100644
--- a/src/exabgp/bgp/message/open/capability/__init__.py
+++ b/src/exabgp/bgp/message/open/capability/__init__.py
@@ -22,6 +22,7 @@ from exabgp.bgp.message.open.capability.pathslimit import PathsLimit
 from exabgp.bgp.message.open.capability.labels import MultipleLabels
 from exabgp.bgp.message.open.capability.asn4 import ASN4
 from exabgp.bgp.message.open.capability.graceful import Graceful
+from exabgp.bgp.message.open.capability.llgr import LongLivedGraceful
 from exabgp.bgp.message.open.capability.mp import MultiProtocol
 from exabgp.bgp.message.open.capability.ms import MultiSession
 from exabgp.bgp.message.open.capability.operational import Operational
@@ -44,6 +45,7 @@ __all__ = [
     'PathsLimit',
     'ASN4',
     'Graceful',
+    'LongLivedGraceful',
     'MultiProtocol',
     'MultiSession',
     'Operational',
diff --git a/src/exabgp/bgp/message/open/capability/capability.py b/src/exabgp/bgp/message/open/capability/capability.py
index ffec782..9b35ccc 100644
--- a/src/exabgp/bgp/message/open/capability/capability.py
+++ b/src/exabgp/bgp/message/open/capability/capability.py
@@ -70,6 +70,7 @@ class CapabilityCode(IntValue):
     MULTISESSION: ClassVar[int] = 0x44  # [draft-ietf-idr-bgp-multisession]
     ADD_PATH: ClassVar[int] = 0x45  # [draft-ietf-idr-add-paths]
     ENHANCED_ROUTE_REFRESH: ClassVar[int] = 0x46  # [draft-ietf-idr-bgp-enhanced-route-refresh]
+    LONG_LIVED_GRACEFUL_RESTART: ClassVar[int] = 0x47  # [RFC9494]
     PATHS_LIMIT: ClassVar[int] = 0x4C  # [draft-abraitis-idr-addpath-paths-limit]
     LINK_LOCAL_NEXTHOP: ClassVar[int] = 0x4D  # [draft-ietf-idr-linklocal-capability]
     # 78-127    Unassigned
@@ -103,6 +104,7 @@ class CapabilityCode(IntValue):
         MULTISESSION: 'multi-session',
         ADD_PATH: 'add-path',
         ENHANCED_ROUTE_REFRESH: 'enhanced-route-refresh',
+        LONG_LIVED_GRACEFUL_RESTART: 'long-lived-graceful-restart',
         PATHS_LIMIT: 'paths-limit',
         MULTIPLE_LABELS: 'multiple-labels',
         LINK_LOCAL_NEXTHOP: 'link-local-nexthop',
@@ -150,6 +152,7 @@ class CapabilityCodes:
     MULTISESSION: ClassVar[CapabilityCode] =             CapabilityCode(CapabilityCode.MULTISESSION)
     ADD_PATH: ClassVar[CapabilityCode] =                 CapabilityCode(CapabilityCode.ADD_PATH)
     ENHANCED_ROUTE_REFRESH: ClassVar[CapabilityCode] =   CapabilityCode(CapabilityCode.ENHANCED_ROUTE_REFRESH)
+    LONG_LIVED_GRACEFUL_RESTART: ClassVar[CapabilityCode] = CapabilityCode(CapabilityCode.LONG_LIVED_GRACEFUL_RESTART)
     PATHS_LIMIT: ClassVar[CapabilityCode] =              CapabilityCode(CapabilityCode.PATHS_LIMIT)
     MULTIPLE_LABELS: ClassVar[CapabilityCode] =          CapabilityCode(CapabilityCode.MULTIPLE_LABELS)
     LINK_LOCAL_NEXTHOP: ClassVar[CapabilityCode] =       CapabilityCode(CapabilityCode.LINK_LOCAL_NEXTHOP)
diff --git a/src/exabgp/bgp/message/open/capability/llgr.py b/src/exabgp/bgp/message/open/capability/llgr.py
new file mode 100644
index 0000000..0ced80d
--- /dev/null
+++ b/src/exabgp/bgp/message/open/capability/llgr.py
@@ -0,0 +1,109 @@
+"""llgr.py
+
+Long-Lived Graceful Restart capability (RFC 9494, capability code 71).
+
+The value is zero or more tuples of AFI(2), SAFI(1), Flags(1) and Long-Lived Stale Time(3),
+seven octets each. Only the most significant bit of Flags, the F bit, is defined; the other
+bits are reserved, sent as zero and ignored on receipt, so the flags octet is kept as received.
+
+This module decodes what a peer sent, shows it, and encodes it back. It does not act on it:
+route handling does not change for this capability.
+
+Created for ExaBGP.
+Copyright (c) 2009-2017 Exa Networks. All rights reserved.
+License: 3-clause BSD. (See the COPYRIGHT file)
+"""
+
+from __future__ import annotations
+
+import json
+from typing import ClassVar, NamedTuple
+
+from exabgp.protocol.family import AFI, SAFI
+from exabgp.bgp.message.notification import Notify
+from exabgp.bgp.message.open.capability.capability import Capability, CapabilityCode, CapabilityList
+from exabgp.util.types import Buffer
+
+# ================================================================ LongLivedGraceful
+
+
+class LongLivedFamily(NamedTuple):
+    afi: AFI
+    safi: SAFI
+    flags: int
+    stale_time: int
+
+
+class LongLivedGraceful(CapabilityList[LongLivedFamily]):
+    ID: ClassVar = Capability.CODE.LONG_LIVED_GRACEFUL_RESTART
+
+    # AFI(2) + SAFI(1) + Flags(1) + Long-Lived Stale Time(3)
+    TUPLE_SIZE: ClassVar[int] = 7
+    STALE_TIME_MAX: ClassVar[int] = 0xFFFFFF
+    # RFC 9494 section 3: the most significant bit of Flags is the F bit
+    FORWARDING_STATE: ClassVar[int] = 0x80
+
+    def set(self, families: list[LongLivedFamily]) -> LongLivedGraceful:
+        self.items = families
+        return self
+
+    def extract_capability_bytes(self) -> list[bytes]:
+        for family in self.items:
+            assert 0 <= family.stale_time <= self.STALE_TIME_MAX, 'the stale time is 24 bits'
+        # zero tuples is a valid, zero-length value (RFC 9494 section 3 says zero or more)
+        value = b''.join(
+            family.afi.pack_afi()
+            + family.safi.pack_safi()
+            + bytes([family.flags])
+            + family.stale_time.to_bytes(3, 'big')
+            for family in self.items
+        )
+        return [value]
+
+    def __str__(self) -> str:
+        families = [
+            f'{family.afi}/{family.safi} flags {hex(family.flags)} stale {family.stale_time}' for family in self
+        ]
+        return ' '.join(['Long-Lived Graceful Restart', *families])
+
+    def json(self) -> str:
+        families = [
+            {
+                'afi': str(family.afi),
+                'safi': str(family.safi),
+                'flags': family.flags,
+                'forwarding': bool(family.flags & self.FORWARDING_STATE),
+                'stale-time': family.stale_time,
+            }
+            for family in self
+        ]
+        return json.dumps({'name': 'long-lived-graceful-restart', 'address-family': families})
+
+    @staticmethod
+    def _family(entry: Buffer) -> LongLivedFamily:
+        view = bytes(entry)
+        return LongLivedFamily(
+            AFI.unpack_afi(view[0:2]),
+            SAFI.unpack_safi(view[2:3]),
+            view[3],
+            int.from_bytes(view[4:7], 'big'),
+        )
+
+    @classmethod
+    def unpack_capability(cls, instance: Capability, data: Buffer, capability: CapabilityCode) -> Capability:  # pylint: disable=W0613
+        assert isinstance(instance, LongLivedGraceful)
+        # The peer controls this length, so it is checked, never asserted: a truncated tuple is a Notify
+        view = memoryview(data)
+        if len(view) % cls.TUPLE_SIZE:
+            raise Notify(
+                2,
+                0,
+                f'long-lived graceful restart capability is {len(view)} octets, not a multiple of {cls.TUPLE_SIZE}',
+            )
+        families = [
+            cls._family(view[offset : offset + cls.TUPLE_SIZE]) for offset in range(0, len(view), cls.TUPLE_SIZE)
+        ]
+        return instance.set(families)
+
+
+Capability.register()(LongLivedGraceful)
diff --git a/tests/unit/test_llgr_capability.py b/tests/unit/test_llgr_capability.py
new file mode 100644
index 0000000..e278526
--- /dev/null
+++ b/tests/unit/test_llgr_capability.py
@@ -0,0 +1,90 @@
+#!/usr/bin/env python3
+# encoding: utf-8
+"""test_llgr_capability.py
+
+Long-Lived Graceful Restart capability (RFC 9494, capability code 71).
+
+The value is zero or more tuples of AFI(2), SAFI(1), Flags(1) and Long-Lived Stale Time(3),
+seven octets each. These tests hold the decoding of a well formed value, and the refusal
+of a truncated one, which a peer can send and which must end the session with a NOTIFICATION.
+
+Created for ExaBGP testing framework
+License: 3-clause BSD
+"""
+
+import json
+
+import pytest
+
+from exabgp.bgp.message.notification import Notify
+from exabgp.bgp.message.open.capability.capability import Capability
+from exabgp.bgp.message.open.capability.capability import CapabilityCode
+from exabgp.bgp.message.open.capability.llgr import LongLivedFamily
+from exabgp.bgp.message.open.capability.llgr import LongLivedGraceful
+from exabgp.protocol.family import AFI
+from exabgp.protocol.family import SAFI
+
+# IPv4 unicast, F bit set, stale time 0x012345; IPv6 unicast, F bit clear, stale time 1
+WELL_FORMED = bytes.fromhex('00010180012345' '00020100000001')
+
+
+def test_capability_code_is_71_and_registered() -> None:
+    """RFC 9494 assigns capability code 71, and the registry hands it to LongLivedGraceful."""
+    assert Capability.CODE.LONG_LIVED_GRACEFUL_RESTART == 71
+    assert LongLivedGraceful.ID == 71
+    assert CapabilityCode(71).name() == 'long-lived-graceful-restart'
+    assert Capability.klass(CapabilityCode(71)) is LongLivedGraceful
+
+
+def test_well_formed_value_decodes() -> None:
+    """Each seven octet tuple becomes one family, with its flags and its 24 bit stale time."""
+    parsed = LongLivedGraceful.unpack_capability(LongLivedGraceful(), memoryview(WELL_FORMED), CapabilityCode(71))
+    assert isinstance(parsed, LongLivedGraceful)
+    assert list(parsed) == [
+        LongLivedFamily(AFI.ipv4, SAFI.unicast, 0x80, 0x012345),
+        LongLivedFamily(AFI.ipv6, SAFI.unicast, 0x00, 1),
+    ]
+
+
+def test_well_formed_value_encodes_back_unchanged() -> None:
+    """Decoding then encoding gives the bytes the peer sent, reserved flag bits included."""
+    parsed = LongLivedGraceful.unpack_capability(LongLivedGraceful(), memoryview(WELL_FORMED), CapabilityCode(71))
+    assert parsed.extract_capability_bytes() == [WELL_FORMED]
+
+
+def test_well_formed_value_renders_in_str_and_json() -> None:
+    """str() and json() show the family, the forwarding state and the stale time."""
+    parsed = LongLivedGraceful.unpack_capability(LongLivedGraceful(), memoryview(WELL_FORMED), CapabilityCode(71))
+    assert str(parsed) == (
+        'Long-Lived Graceful Restart ipv4/unicast flags 0x80 stale 74565 ipv6/unicast flags 0x0 stale 1'
+    )
+    decoded = json.loads(parsed.json())
+    assert decoded['name'] == 'long-lived-graceful-restart'
+    assert decoded['address-family'] == [
+        {'afi': 'ipv4', 'safi': 'unicast', 'flags': 0x80, 'forwarding': True, 'stale-time': 0x012345},
+        {'afi': 'ipv6', 'safi': 'unicast', 'flags': 0x00, 'forwarding': False, 'stale-time': 1},
+    ]
+
+
+def test_empty_value_is_valid() -> None:
+    """RFC 9494 section 3 allows zero tuples, which is a zero length capability."""
+    parsed = LongLivedGraceful.unpack_capability(LongLivedGraceful(), memoryview(b''), CapabilityCode(71))
+    assert len(parsed) == 0
+    assert parsed.extract_capability_bytes() == [b'']
+
+
+@pytest.mark.parametrize(
+    'payload',
+    [
+        WELL_FORMED[:6],  # the first tuple cut short, before its stale time is complete
+        WELL_FORMED[:1],  # a lone octet of AFI
+        WELL_FORMED + b'\x00',  # a stray octet after the last whole tuple
+        WELL_FORMED[:7] + WELL_FORMED[7:10],  # the second tuple cut short
+    ],
+)
+def test_truncated_value_is_refused_with_notify(payload: bytes) -> None:
+    """A tuple which is not seven octets long ends the session, it is never read past its end."""
+    with pytest.raises(Notify) as exc:
+        LongLivedGraceful.unpack_capability(LongLivedGraceful(), memoryview(payload), CapabilityCode(71))
+    assert exc.value.code == 2
+    assert exc.value.subcode == 0

```


===== RUN a054 =====
```diff
diff --git a/src/exabgp/bgp/message/open/capability/__init__.py b/src/exabgp/bgp/message/open/capability/__init__.py
index 5c60813..419fde2 100644
--- a/src/exabgp/bgp/message/open/capability/__init__.py
+++ b/src/exabgp/bgp/message/open/capability/__init__.py
@@ -22,6 +22,7 @@ from exabgp.bgp.message.open.capability.pathslimit import PathsLimit
 from exabgp.bgp.message.open.capability.labels import MultipleLabels
 from exabgp.bgp.message.open.capability.asn4 import ASN4
 from exabgp.bgp.message.open.capability.graceful import Graceful
+from exabgp.bgp.message.open.capability.longlived import LongLivedGraceful
 from exabgp.bgp.message.open.capability.mp import MultiProtocol
 from exabgp.bgp.message.open.capability.ms import MultiSession
 from exabgp.bgp.message.open.capability.operational import Operational
@@ -44,6 +45,7 @@ __all__ = [
     'PathsLimit',
     'ASN4',
     'Graceful',
+    'LongLivedGraceful',
     'MultiProtocol',
     'MultiSession',
     'Operational',
diff --git a/src/exabgp/bgp/message/open/capability/capability.py b/src/exabgp/bgp/message/open/capability/capability.py
index ffec782..9b35ccc 100644
--- a/src/exabgp/bgp/message/open/capability/capability.py
+++ b/src/exabgp/bgp/message/open/capability/capability.py
@@ -70,6 +70,7 @@ class CapabilityCode(IntValue):
     MULTISESSION: ClassVar[int] = 0x44  # [draft-ietf-idr-bgp-multisession]
     ADD_PATH: ClassVar[int] = 0x45  # [draft-ietf-idr-add-paths]
     ENHANCED_ROUTE_REFRESH: ClassVar[int] = 0x46  # [draft-ietf-idr-bgp-enhanced-route-refresh]
+    LONG_LIVED_GRACEFUL_RESTART: ClassVar[int] = 0x47  # [RFC9494]
     PATHS_LIMIT: ClassVar[int] = 0x4C  # [draft-abraitis-idr-addpath-paths-limit]
     LINK_LOCAL_NEXTHOP: ClassVar[int] = 0x4D  # [draft-ietf-idr-linklocal-capability]
     # 78-127    Unassigned
@@ -103,6 +104,7 @@ class CapabilityCode(IntValue):
         MULTISESSION: 'multi-session',
         ADD_PATH: 'add-path',
         ENHANCED_ROUTE_REFRESH: 'enhanced-route-refresh',
+        LONG_LIVED_GRACEFUL_RESTART: 'long-lived-graceful-restart',
         PATHS_LIMIT: 'paths-limit',
         MULTIPLE_LABELS: 'multiple-labels',
         LINK_LOCAL_NEXTHOP: 'link-local-nexthop',
@@ -150,6 +152,7 @@ class CapabilityCodes:
     MULTISESSION: ClassVar[CapabilityCode] =             CapabilityCode(CapabilityCode.MULTISESSION)
     ADD_PATH: ClassVar[CapabilityCode] =                 CapabilityCode(CapabilityCode.ADD_PATH)
     ENHANCED_ROUTE_REFRESH: ClassVar[CapabilityCode] =   CapabilityCode(CapabilityCode.ENHANCED_ROUTE_REFRESH)
+    LONG_LIVED_GRACEFUL_RESTART: ClassVar[CapabilityCode] = CapabilityCode(CapabilityCode.LONG_LIVED_GRACEFUL_RESTART)
     PATHS_LIMIT: ClassVar[CapabilityCode] =              CapabilityCode(CapabilityCode.PATHS_LIMIT)
     MULTIPLE_LABELS: ClassVar[CapabilityCode] =          CapabilityCode(CapabilityCode.MULTIPLE_LABELS)
     LINK_LOCAL_NEXTHOP: ClassVar[CapabilityCode] =       CapabilityCode(CapabilityCode.LINK_LOCAL_NEXTHOP)
diff --git a/src/exabgp/bgp/message/open/capability/longlived.py b/src/exabgp/bgp/message/open/capability/longlived.py
new file mode 100644
index 0000000..b317cf8
--- /dev/null
+++ b/src/exabgp/bgp/message/open/capability/longlived.py
@@ -0,0 +1,118 @@
+"""longlived.py
+
+Long-Lived Graceful Restart capability (RFC 9494, capability code 71).
+
+The value is zero or more <AFI, SAFI, Flags, Long-Lived Stale Time> tuples, seven
+octets each: a two octet AFI, a one octet SAFI, one octet of flags and a 24 bit
+stale time in seconds. Only the most significant flag bit, F, is defined.
+
+ExaBGP decodes and displays what the peer sends. It neither advertises the
+capability nor changes how stale routes are handled because of it.
+
+Copyright (c) 2009-2017 Exa Networks. All rights reserved.
+License: 3-clause BSD. (See the COPYRIGHT file)
+"""
+
+from __future__ import annotations
+
+from typing import ClassVar, Iterable
+
+from exabgp.protocol.family import AFI, SAFI, FamilyTuple
+from exabgp.bgp.message.open.capability.capability import Capability, CapabilityDict
+from exabgp.bgp.message.open.capability.capability import CapabilityCode
+from exabgp.bgp.message.notification import Notify
+from exabgp.logger import log, lazymsg
+
+
+class LongLivedGraceful(CapabilityDict[FamilyTuple, tuple[int, int]]):
+    """RFC 9494 3.1: per family, the flags and the Long-Lived Stale Time."""
+
+    ID: ClassVar = Capability.CODE.LONG_LIVED_GRACEFUL_RESTART
+
+    # AFI(2) + SAFI(1) + Flags(1) + Long-Lived Stale Time(3)
+    ENTRY_SIZE: ClassVar[int] = 7
+    # A capability's length is a single octet, so one instance holds at most this many
+    MAX_FAMILIES: ClassVar[int] = 0xFF // ENTRY_SIZE
+
+    # RFC 9494 3.1: "The most significant bit is used to indicate whether the state for
+    # routes that were advertised with the given AFI and SAFI has been preserved". The
+    # other bits "MUST be set to zero by the sender and ignored by the receiver".
+    FORWARDING_STATE: ClassVar[int] = 0x80
+    STALE_TIME_MAX: ClassVar[int] = 0xFFFFFF
+
+    def set(self, protos: Iterable[tuple[AFI, SAFI, int, int]]) -> LongLivedGraceful:
+        for afi, safi, flags, stale_time in protos:
+            if not 0 <= stale_time <= LongLivedGraceful.STALE_TIME_MAX:
+                limit = LongLivedGraceful.STALE_TIME_MAX
+                raise ValueError(f'long-lived stale time must be 0-{limit}, got {stale_time}')
+            self[(afi, safi)] = (flags & LongLivedGraceful.FORWARDING_STATE, stale_time)
+        return self
+
+    def extract_capability_bytes(self) -> list[bytes]:
+        families = [
+            afi.pack_afi() + safi.pack_safi() + bytes([flags]) + stale_time.to_bytes(3, 'big')
+            for (afi, safi), (flags, stale_time) in self.items()
+        ]
+        return [b''.join(families)]
+
+    def __str__(self) -> str:
+        families = ' '.join(
+            f'{afi}/{safi}=flags {hex(flags)} stale-time {stale_time}'
+            for (afi, safi), (flags, stale_time) in self.items()
+        )
+        return f'Long-Lived Graceful Restart {families}'.rstrip()
+
+    def json(self) -> str:
+        families = ', '.join(
+            f'"{afi}/{safi}": {{ "forwarding": {"true" if flags & LongLivedGraceful.FORWARDING_STATE else "false"}, '
+            f'"stale-time": {stale_time} }}'
+            for (afi, safi), (flags, stale_time) in self.items()
+        )
+        return f'{{ "name": "long-lived-graceful-restart", "address-family-flags": {{ {families} }} }}'
+
+    def families(self) -> Iterable[FamilyTuple]:
+        return self.keys()
+
+    @classmethod
+    def unpack_capability(cls, instance: Capability, data, capability: CapabilityCode) -> Capability:  # pylint: disable=W0613
+        assert isinstance(instance, LongLivedGraceful)
+        # As for Graceful Restart, a second instance of the capability replaces the first
+        if len(instance) > 0:
+            log.debug(lazymsg('capability.long_lived_graceful_restart.duplicate action=replace'), 'parser')
+            instance.clear()
+
+        view = memoryview(data)
+        families: list[tuple[AFI, SAFI, int, int]] = []
+        seen: set[FamilyTuple] = set()
+        # RFC 9494 3.1: "zero or more tuples", so an empty value is well formed
+        while view:
+            if len(view) < cls.ENTRY_SIZE:
+                raise Notify(
+                    2,
+                    0,
+                    f'Long-Lived Graceful Restart capability truncated: '
+                    f'need {cls.ENTRY_SIZE} bytes per family, got {len(view)}',
+                )
+            if len(families) >= cls.MAX_FAMILIES:
+                # Only reachable when called with more than a capability can carry
+                log.debug(
+                    lazymsg('capability.long_lived_graceful_restart.capacity families={n}', n=cls.MAX_FAMILIES),
+                    'parser',
+                )
+                break
+            afi = AFI.unpack_afi(view[:2])
+            safi = SAFI.unpack_safi(view[2:3])
+            flags = view[3]
+            stale_time = (view[4] << 16) | (view[5] << 8) | view[6]
+            view = view[cls.ENTRY_SIZE :]
+            # RFC 9494 says nothing of a family listed twice: the first one is kept
+            if (afi, safi) in seen:
+                message = 'capability.long_lived_graceful_restart.duplicate family={afi}/{safi}'
+                log.debug(lazymsg(message, afi=afi, safi=safi), 'parser')
+                continue
+            seen.add((afi, safi))
+            families.append((afi, safi, flags, stale_time))
+        return instance.set(families)
+
+
+Capability.register()(LongLivedGraceful)
diff --git a/tests/unit/test_capability_long_lived_graceful.py b/tests/unit/test_capability_long_lived_graceful.py
new file mode 100644
index 0000000..8d2fdf2
--- /dev/null
+++ b/tests/unit/test_capability_long_lived_graceful.py
@@ -0,0 +1,87 @@
+"""test_capability_long_lived_graceful.py
+
+Long-Lived Graceful Restart capability (RFC 9494, code 71): decoded from an OPEN,
+encoded back, and rendered in str() and JSON.
+
+License: 3-clause BSD
+"""
+
+from __future__ import annotations
+
+import json
+
+import pytest
+
+from exabgp.bgp.message.notification import Notify
+from exabgp.bgp.message.open.capability import Capabilities
+from exabgp.bgp.message.open.capability import Capability
+from exabgp.bgp.message.open.capability import LongLivedGraceful
+from exabgp.protocol.family import AFI, SAFI
+
+# ipv4/unicast, F bit and a reserved bit set, 3600 seconds (0x000e10)
+IPV4_UNICAST = b'\x00\x01\x01\xc0\x00\x0e\x10'
+# ipv6/unicast, no flag, the largest stale time 0xffffff
+IPV6_UNICAST = b'\x00\x02\x01\x00\xff\xff\xff'
+
+
+def _optional_parameters(value: bytes) -> bytes:
+    """The OPEN Optional Parameters carrying one capability 71 with this value."""
+    capability = bytes([Capability.CODE.LONG_LIVED_GRACEFUL_RESTART.value, len(value)]) + value
+    parameter = bytes([2, len(capability)]) + capability
+    return bytes([len(parameter)]) + parameter
+
+
+def test_code_and_name_are_registered() -> None:
+    assert Capability.CODE.LONG_LIVED_GRACEFUL_RESTART == 71
+    assert Capability.CODE.LONG_LIVED_GRACEFUL_RESTART.name() == 'long-lived-graceful-restart'
+    assert Capability.klass(Capability.CODE.LONG_LIVED_GRACEFUL_RESTART) is LongLivedGraceful
+
+
+def test_well_formed_capability_is_decoded() -> None:
+    value = IPV4_UNICAST + IPV6_UNICAST
+    capabilities = Capabilities.unpack(_optional_parameters(value))
+    llgr = capabilities[Capability.CODE.LONG_LIVED_GRACEFUL_RESTART]
+
+    assert isinstance(llgr, LongLivedGraceful)
+    # the reserved bit is ignored, as RFC 9494 3.1 has the receiver do
+    assert dict(llgr.items()) == {
+        (AFI.ipv4, SAFI.unicast): (LongLivedGraceful.FORWARDING_STATE, 3600),
+        (AFI.ipv6, SAFI.unicast): (0, 0xFFFFFF),
+    }
+
+    # encoded back, less the reserved bit the peer set
+    assert llgr.extract_capability_bytes() == [b'\x00\x01\x01\x80\x00\x0e\x10' + IPV6_UNICAST]
+
+    assert str(llgr) == (
+        'Long-Lived Graceful Restart ipv4/unicast=flags 0x80 stale-time 3600 '
+        'ipv6/unicast=flags 0x0 stale-time 16777215'
+    )
+    assert json.loads(llgr.json()) == {
+        'name': 'long-lived-graceful-restart',
+        'address-family-flags': {
+            'ipv4/unicast': {'forwarding': True, 'stale-time': 3600},
+            'ipv6/unicast': {'forwarding': False, 'stale-time': 16777215},
+        },
+    }
+
+
+def test_empty_capability_is_well_formed() -> None:
+    # RFC 9494 3.1: "The capability value consists of zero or more tuples"
+    capabilities = Capabilities.unpack(_optional_parameters(b''))
+    llgr = capabilities[Capability.CODE.LONG_LIVED_GRACEFUL_RESTART]
+
+    assert isinstance(llgr, LongLivedGraceful)
+    assert len(llgr) == 0
+    assert llgr.extract_capability_bytes() == [b'']
+    assert json.loads(llgr.json()) == {'name': 'long-lived-graceful-restart', 'address-family-flags': {}}
+
+
+@pytest.mark.parametrize('value', [IPV4_UNICAST[:6], IPV4_UNICAST + IPV6_UNICAST[:3], b'\x00'])
+def test_truncated_capability_is_refused(value: bytes) -> None:
+    with pytest.raises(Notify) as raised:
+        Capabilities.unpack(_optional_parameters(value))
+    assert raised.value.code == 2
+    assert raised.value.subcode == 0
+
+    with pytest.raises(Notify):
+        LongLivedGraceful.unpack_capability(LongLivedGraceful(), value, Capability.CODE.LONG_LIVED_GRACEFUL_RESTART)

```


===== RUN a038 =====
```diff
diff --git a/src/exabgp/bgp/message/open/capability/__init__.py b/src/exabgp/bgp/message/open/capability/__init__.py
index 5c60813..66fa42b 100644
--- a/src/exabgp/bgp/message/open/capability/__init__.py
+++ b/src/exabgp/bgp/message/open/capability/__init__.py
@@ -29,6 +29,7 @@ from exabgp.bgp.message.open.capability.refresh import RouteRefresh
 from exabgp.bgp.message.open.capability.refresh import EnhancedRouteRefresh
 from exabgp.bgp.message.open.capability.refresh import REFRESH
 from exabgp.bgp.message.open.capability.linklocal import LinkLocalNextHop
+from exabgp.bgp.message.open.capability.llgr import LongLivedGracefulRestart
 from exabgp.bgp.message.open.capability.role import Role
 from exabgp.bgp.message.open.capability.role import RoleValue
 
@@ -51,6 +52,7 @@ __all__ = [
     'EnhancedRouteRefresh',
     'REFRESH',
     'LinkLocalNextHop',
+    'LongLivedGracefulRestart',
     'Role',
     'RoleValue',
     'UnknownCapability',
diff --git a/src/exabgp/bgp/message/open/capability/capability.py b/src/exabgp/bgp/message/open/capability/capability.py
index 89e00a2..80f957f 100644
--- a/src/exabgp/bgp/message/open/capability/capability.py
+++ b/src/exabgp/bgp/message/open/capability/capability.py
@@ -72,6 +72,7 @@ class CapabilityCode(IntValue):
     ENHANCED_ROUTE_REFRESH: ClassVar[int] = 0x46  # [draft-ietf-idr-bgp-enhanced-route-refresh]
     PATHS_LIMIT: ClassVar[int] = 0x4C  # [draft-abraitis-idr-addpath-paths-limit]
     LINK_LOCAL_NEXTHOP: ClassVar[int] = 0x4D  # [draft-ietf-idr-linklocal-capability]
+    LONG_LIVED_GRACEFUL_RESTART: ClassVar[int] = 0x47  # [RFC9494]
     # 78-127    Unassigned
     ROUTE_REFRESH_CISCO: ClassVar[int] = 0x80  # I Can only find reference to this in the router logs
     # 128-255   Reserved for Private Use [RFC5492]
@@ -106,6 +107,7 @@ class CapabilityCode(IntValue):
         PATHS_LIMIT: 'paths-limit',
         MULTIPLE_LABELS: 'multiple-labels',
         LINK_LOCAL_NEXTHOP: 'link-local-nexthop',
+        LONG_LIVED_GRACEFUL_RESTART: 'long-lived-graceful-restart',
         OPERATIONAL: 'operational',
         ROUTE_REFRESH_CISCO: 'cisco-route-refresh',
         MULTISESSION_CISCO: 'cisco-multi-sesion',
@@ -153,6 +155,7 @@ class CapabilityCodes:
     PATHS_LIMIT: ClassVar[CapabilityCode] =              CapabilityCode(CapabilityCode.PATHS_LIMIT)
     MULTIPLE_LABELS: ClassVar[CapabilityCode] =          CapabilityCode(CapabilityCode.MULTIPLE_LABELS)
     LINK_LOCAL_NEXTHOP: ClassVar[CapabilityCode] =       CapabilityCode(CapabilityCode.LINK_LOCAL_NEXTHOP)
+    LONG_LIVED_GRACEFUL_RESTART: ClassVar[CapabilityCode] = CapabilityCode(CapabilityCode.LONG_LIVED_GRACEFUL_RESTART)
     ROUTE_REFRESH_CISCO: ClassVar[CapabilityCode] =      CapabilityCode(CapabilityCode.ROUTE_REFRESH_CISCO)
     MULTISESSION_CISCO: ClassVar[CapabilityCode] =       CapabilityCode(CapabilityCode.MULTISESSION_CISCO)
     HOSTNAME: ClassVar[CapabilityCode] =                 CapabilityCode(CapabilityCode.HOSTNAME)
diff --git a/src/exabgp/bgp/message/open/capability/llgr.py b/src/exabgp/bgp/message/open/capability/llgr.py
new file mode 100644
index 0000000..278b0dd
--- /dev/null
+++ b/src/exabgp/bgp/message/open/capability/llgr.py
@@ -0,0 +1,94 @@
+"""llgr.py
+
+Long-Lived Graceful Restart capability, RFC 9494 section 3.1.
+"""
+
+from __future__ import annotations
+
+import json
+from struct import pack
+from typing import ClassVar
+
+from exabgp.protocol.family import AFI, SAFI, FamilyTuple
+from exabgp.bgp.message.open.capability.capability import Capability, CapabilityDict
+from exabgp.bgp.message.open.capability.capability import CapabilityCode
+from exabgp.bgp.message.notification import Notify
+from exabgp.util.types import Buffer
+
+# ================================================================ LLGR (Restart)
+# RFC 9494 - https://datatracker.ietf.org/doc/html/rfc9494
+
+
+class LongLivedGracefulRestart(CapabilityDict[FamilyTuple, tuple[int, int]]):
+    """One entry per family: the flags octet and the 24 bit Long-Lived Stale Time, in seconds.
+
+    The value of each entry is (flags, stale_time). The F bit is the only flag defined, and
+    the RFC says the other bits are ignored on receipt, so they are not kept.
+    """
+
+    ID: ClassVar = Capability.CODE.LONG_LIVED_GRACEFUL_RESTART
+
+    # AFI(2) + SAFI(1) + flags(1) + Long-Lived Stale Time(3)
+    TUPLE_LEN: ClassVar[int] = 7
+    STALE_TIME_MAX: ClassVar[int] = 0xFFFFFF
+    FORWARDING_STATE: ClassVar[int] = 0x80
+
+    def set_family(self, afi: AFI, safi: SAFI, flags: int, stale_time: int) -> None:
+        assert 0 <= stale_time <= LongLivedGracefulRestart.STALE_TIME_MAX, 'the stale time is 24 bits'
+        self[(afi, safi)] = (flags & LongLivedGracefulRestart.FORWARDING_STATE, stale_time)
+
+    def forwarding(self, family: FamilyTuple) -> bool:
+        return bool(self[family][0] & LongLivedGracefulRestart.FORWARDING_STATE)
+
+    def __str__(self) -> str:
+        entries = ' '.join(
+            f'{afi}/{safi} forwarding={int(self.forwarding((afi, safi)))} stale-time={stale}'
+            for (afi, safi), (_, stale) in self.items()
+        )
+        return f'Long-Lived Graceful Restart {entries}'.rstrip()
+
+    def json(self) -> str:
+        families = {
+            f'{afi}/{safi}': {'forwarding-state': self.forwarding((afi, safi)), 'stale-time': stale}
+            for (afi, safi), (_, stale) in self.items()
+        }
+        return json.dumps({'name': 'long-lived-graceful-restart', 'families': families})
+
+    def extract_capability_bytes(self) -> list[bytes]:
+        # No family, no capability: an empty value would still be a capability we announced
+        if not self:
+            return []
+        entries = b''.join(
+            afi.pack_afi()
+            + safi.pack_safi()
+            + bytes([flags])
+            + pack('!I', stale_time)[1:]
+            for (afi, safi), (flags, stale_time) in self.items()
+        )
+        return [entries]
+
+    @classmethod
+    def unpack_capability(cls, instance: Capability, data: Buffer, capability: CapabilityCode) -> Capability:  # pylint: disable=W0613
+        assert isinstance(instance, LongLivedGracefulRestart)
+        # A repeated capability replaces what the earlier one said, as Graceful does
+        instance.clear()
+        # RFC 9494 3.1 has zero or more whole tuples and nothing else, so a partial one is
+        # malformed rather than something to read the complete tuples from
+        if len(data) % cls.TUPLE_LEN:
+            raise Notify(
+                2,
+                0,
+                f'Long-Lived Graceful Restart capability is {len(data)} octets, '
+                f'not a multiple of {cls.TUPLE_LEN} (truncated entry)',
+            )
+        for offset in range(0, len(data), cls.TUPLE_LEN):
+            entry = data[offset : offset + cls.TUPLE_LEN]
+            afi = AFI.unpack_afi(entry[0:2])
+            safi = SAFI.unpack_safi(entry[2:3])
+            flags = entry[3]
+            stale_time = int.from_bytes(entry[4:7], 'big')
+            instance.set_family(afi, safi, flags, stale_time)
+        return instance
+
+
+Capability.register()(LongLivedGracefulRestart)
diff --git a/tests/unit/test_llgr_capability.py b/tests/unit/test_llgr_capability.py
new file mode 100644
index 0000000..f18baf5
--- /dev/null
+++ b/tests/unit/test_llgr_capability.py
@@ -0,0 +1,69 @@
+"""test_llgr_capability.py
+
+RFC 9494 section 3.1: the Long-Lived Graceful Restart capability, code 71. Each entry is
+AFI(2) + SAFI(1) + flags(1) + Long-Lived Stale Time(3), so 7 octets, and a value which is
+not a whole number of entries is malformed.
+"""
+
+from __future__ import annotations
+
+import json
+
+import pytest
+
+from exabgp.bgp.message.notification import Notify
+from exabgp.bgp.message.open.capability import Capabilities
+from exabgp.bgp.message.open.capability import Capability
+from exabgp.bgp.message.open.capability import LongLivedGracefulRestart
+from exabgp.bgp.message.open.capability.capability import CapabilityCode
+from exabgp.protocol.family import AFI, SAFI
+
+# ipv4 unicast, F bit set, stale time 3600; ipv6 unicast, F bit clear, stale time 86400
+WELL_FORMED = b'\x00\x01\x01\x80\x00\x0e\x10' + b'\x00\x02\x01\x00\x01\x51\x80'
+LLGR_CODE = CapabilityCode(0x47)
+
+
+def test_code_71_is_registered_and_named() -> None:
+    assert int(LLGR_CODE) == 71
+    assert str(LLGR_CODE) == 'long-lived-graceful-restart'
+    assert Capability.klass(LLGR_CODE) is LongLivedGracefulRestart
+
+
+def test_well_formed_capability_decodes_and_round_trips() -> None:
+    received = Capability.unpack(LLGR_CODE, Capabilities(), WELL_FORMED)
+    assert isinstance(received, LongLivedGracefulRestart)
+
+    assert received[(AFI.ipv4, SAFI.unicast)] == (0x80, 3600)
+    assert received[(AFI.ipv6, SAFI.unicast)] == (0x00, 86400)
+    assert received.forwarding((AFI.ipv4, SAFI.unicast)) is True
+    assert received.forwarding((AFI.ipv6, SAFI.unicast)) is False
+
+    assert 'ipv4/unicast' in str(received)
+    assert 'stale-time=3600' in str(received)
+    assert 'stale-time=86400' in str(received)
+
+    decoded = json.loads(received.json())
+    assert decoded['name'] == 'long-lived-graceful-restart'
+    assert decoded['families']['ipv4/unicast'] == {'forwarding-state': True, 'stale-time': 3600}
+    assert decoded['families']['ipv6/unicast'] == {'forwarding-state': False, 'stale-time': 86400}
+
+    assert received.extract_capability_bytes() == [WELL_FORMED]
+
+
+def test_truncated_capability_is_refused_with_notify() -> None:
+    # one whole entry and then 3 of the 7 octets of a second one
+    truncated = WELL_FORMED[:10]
+    assert len(truncated) == 10
+    with pytest.raises(Notify):
+        LongLivedGracefulRestart.unpack_capability(LongLivedGracefulRestart(), truncated, LLGR_CODE)
+
+    # a single entry cut one octet short of its stale time
+    with pytest.raises(Notify):
+        Capability.unpack(LLGR_CODE, Capabilities(), b'\x00\x01\x01\x80\x00\x0e')
+
+
+def test_empty_capability_is_valid_and_announces_nothing() -> None:
+    received = Capability.unpack(LLGR_CODE, Capabilities(), b'')
+    assert isinstance(received, LongLivedGracefulRestart)
+    assert len(received) == 0
+    assert received.extract_capability_bytes() == []

```


===== RUN a039 =====
```diff
diff --git a/src/exabgp/bgp/message/open/capability/__init__.py b/src/exabgp/bgp/message/open/capability/__init__.py
index 5c60813..85c3b17 100644
--- a/src/exabgp/bgp/message/open/capability/__init__.py
+++ b/src/exabgp/bgp/message/open/capability/__init__.py
@@ -22,6 +22,7 @@ from exabgp.bgp.message.open.capability.pathslimit import PathsLimit
 from exabgp.bgp.message.open.capability.labels import MultipleLabels
 from exabgp.bgp.message.open.capability.asn4 import ASN4
 from exabgp.bgp.message.open.capability.graceful import Graceful
+from exabgp.bgp.message.open.capability.llgr import LongLivedGraceful
 from exabgp.bgp.message.open.capability.mp import MultiProtocol
 from exabgp.bgp.message.open.capability.ms import MultiSession
 from exabgp.bgp.message.open.capability.operational import Operational
@@ -44,6 +45,7 @@ __all__ = [
     'PathsLimit',
     'ASN4',
     'Graceful',
+    'LongLivedGraceful',
     'MultiProtocol',
     'MultiSession',
     'Operational',
diff --git a/src/exabgp/bgp/message/open/capability/capability.py b/src/exabgp/bgp/message/open/capability/capability.py
index 89e00a2..4188f9c 100644
--- a/src/exabgp/bgp/message/open/capability/capability.py
+++ b/src/exabgp/bgp/message/open/capability/capability.py
@@ -70,6 +70,7 @@ class CapabilityCode(IntValue):
     MULTISESSION: ClassVar[int] = 0x44  # [draft-ietf-idr-bgp-multisession]
     ADD_PATH: ClassVar[int] = 0x45  # [draft-ietf-idr-add-paths]
     ENHANCED_ROUTE_REFRESH: ClassVar[int] = 0x46  # [draft-ietf-idr-bgp-enhanced-route-refresh]
+    LONG_LIVED_GRACEFUL_RESTART: ClassVar[int] = 0x47  # [RFC9494]
     PATHS_LIMIT: ClassVar[int] = 0x4C  # [draft-abraitis-idr-addpath-paths-limit]
     LINK_LOCAL_NEXTHOP: ClassVar[int] = 0x4D  # [draft-ietf-idr-linklocal-capability]
     # 78-127    Unassigned
@@ -103,6 +104,7 @@ class CapabilityCode(IntValue):
         MULTISESSION: 'multi-session',
         ADD_PATH: 'add-path',
         ENHANCED_ROUTE_REFRESH: 'enhanced-route-refresh',
+        LONG_LIVED_GRACEFUL_RESTART: 'long-lived-graceful-restart',
         PATHS_LIMIT: 'paths-limit',
         MULTIPLE_LABELS: 'multiple-labels',
         LINK_LOCAL_NEXTHOP: 'link-local-nexthop',
@@ -150,6 +152,7 @@ class CapabilityCodes:
     MULTISESSION: ClassVar[CapabilityCode] =             CapabilityCode(CapabilityCode.MULTISESSION)
     ADD_PATH: ClassVar[CapabilityCode] =                 CapabilityCode(CapabilityCode.ADD_PATH)
     ENHANCED_ROUTE_REFRESH: ClassVar[CapabilityCode] =   CapabilityCode(CapabilityCode.ENHANCED_ROUTE_REFRESH)
+    LONG_LIVED_GRACEFUL_RESTART: ClassVar[CapabilityCode] = CapabilityCode(CapabilityCode.LONG_LIVED_GRACEFUL_RESTART)
     PATHS_LIMIT: ClassVar[CapabilityCode] =              CapabilityCode(CapabilityCode.PATHS_LIMIT)
     MULTIPLE_LABELS: ClassVar[CapabilityCode] =          CapabilityCode(CapabilityCode.MULTIPLE_LABELS)
     LINK_LOCAL_NEXTHOP: ClassVar[CapabilityCode] =       CapabilityCode(CapabilityCode.LINK_LOCAL_NEXTHOP)
diff --git a/src/exabgp/bgp/message/open/capability/llgr.py b/src/exabgp/bgp/message/open/capability/llgr.py
new file mode 100644
index 0000000..b259ce8
--- /dev/null
+++ b/src/exabgp/bgp/message/open/capability/llgr.py
@@ -0,0 +1,100 @@
+"""llgr.py
+
+Long-Lived Graceful Restart capability (RFC 9494), code 71.
+
+The value is a list of seven octet entries, one per family:
+
+    AFI (2) | SAFI (1) | Flags (1) | Long-lived Stale Time (3)
+
+Only the peer's capability is parsed and displayed: ExaBGP does not announce it,
+and does not change how routes are kept when a session is lost.
+
+License: 3-clause BSD. (See the COPYRIGHT file)
+"""
+
+from __future__ import annotations
+
+from typing import ClassVar, Iterable
+
+from exabgp.protocol.family import AFI, SAFI, FamilyTuple
+from exabgp.bgp.message.open.capability.capability import Capability, CapabilityDict
+from exabgp.bgp.message.open.capability.capability import CapabilityCode
+from exabgp.bgp.message.notification import Notify
+from exabgp.logger import log, lazymsg
+from exabgp.util.types import Buffer
+
+# ================================================== LongLivedGraceful (Restart)
+# RFC 9494 - https://www.rfc-editor.org/rfc/rfc9494
+
+
+class LongLivedGraceful(CapabilityDict[FamilyTuple, tuple[int, int]]):
+    """Each family maps to (flags, long-lived stale time in seconds)."""
+
+    ID: ClassVar = Capability.CODE.LONG_LIVED_GRACEFUL_RESTART
+
+    ENTRY_SIZE: ClassVar[int] = 7
+    # A capability's length is a single octet, so one instance holds at most this many
+    # entries. The decoding loop is bounded by it.
+    MAX_FAMILIES: ClassVar[int] = 0xFF // ENTRY_SIZE
+
+    # RFC 9494 3: F, the Forwarding State bit, is the most significant bit of the flags;
+    # the other bits are reserved, "MUST be set to zero by the sender and ignored by the receiver"
+    FORWARDING_STATE: ClassVar[int] = 0x80
+    # the Long-lived Stale Time is 24 bits
+    MAX_STALE_TIME: ClassVar[int] = 0xFFFFFF
+
+    def set(self, families: Iterable[tuple[AFI, SAFI, int, int]]) -> LongLivedGraceful:
+        for afi, safi, flags, stale_time in families:
+            assert 0 <= stale_time <= LongLivedGraceful.MAX_STALE_TIME
+            self[(afi, safi)] = (flags & LongLivedGraceful.FORWARDING_STATE, stale_time)
+        return self
+
+    def extract_capability_bytes(self) -> list[bytes]:
+        entries = [
+            afi.pack_afi() + safi.pack_safi() + bytes([flags]) + stale_time.to_bytes(3, 'big')
+            for (afi, safi), (flags, stale_time) in self.items()
+        ]
+        return [b''.join(entries)]
+
+    def __str__(self) -> str:
+        families = ' '.join(
+            f'{afi}/{safi}=flags {hex(flags)} time {stale_time}' for (afi, safi), (flags, stale_time) in self.items()
+        )
+        return f'Long-Lived Graceful Restart {families}'.rstrip()
+
+    def json(self) -> str:
+        families = ', '.join(
+            f'"{afi}/{safi}": {{ "forwarding": {"true" if flags & LongLivedGraceful.FORWARDING_STATE else "false"}, '
+            f'"time": {stale_time} }}'
+            for (afi, safi), (flags, stale_time) in self.items()
+        )
+        return f'{{ "name": "long-lived graceful restart", "address-family": {{ {families} }} }}'
+
+    def families(self) -> Iterable[FamilyTuple]:
+        return self.keys()
+
+    @classmethod
+    def unpack_capability(cls, instance: Capability, data: Buffer, capability: CapabilityCode) -> Capability:  # pylint: disable=W0613
+        assert isinstance(instance, LongLivedGraceful)
+        if len(instance) > 0:
+            log.debug(lazymsg('capability.long_lived_graceful_restart.duplicate action=replace'), 'parser')
+            instance.clear()
+        view = memoryview(data)
+        if len(view) % cls.ENTRY_SIZE:
+            raise Notify(
+                2,
+                0,
+                f'Long-Lived Graceful Restart capability truncated: '
+                f'need {cls.ENTRY_SIZE} bytes per family, got {len(view)} bytes',
+            )
+        families: list[tuple[AFI, SAFI, int, int]] = []
+        for index in range(min(len(view) // cls.ENTRY_SIZE, cls.MAX_FAMILIES)):
+            entry = view[index * cls.ENTRY_SIZE : (index + 1) * cls.ENTRY_SIZE]
+            afi = AFI.unpack_afi(entry[:2])
+            safi = SAFI.unpack_safi(entry[2:3])
+            stale_time = int.from_bytes(entry[4:7], 'big')
+            families.append((afi, safi, entry[3], stale_time))
+        return instance.set(families)
+
+
+Capability.register()(LongLivedGraceful)
diff --git a/tests/unit/test_llgr_capability.py b/tests/unit/test_llgr_capability.py
new file mode 100644
index 0000000..1343a87
--- /dev/null
+++ b/tests/unit/test_llgr_capability.py
@@ -0,0 +1,96 @@
+#!/usr/bin/env python3
+# encoding: utf-8
+"""test_llgr_capability.py
+
+RFC 9494 Long-Lived Graceful Restart capability (code 71).
+
+The value is a list of seven octet entries: AFI (2), SAFI (1), Flags (1) and a
+24-bit Long-lived Stale Time. ExaBGP only decodes and displays what the peer
+sends, so the tests hold the decoding, the encoding back to the same octets,
+the str() and JSON rendering, and the refusal of a truncated entry.
+
+License: 3-clause BSD
+"""
+
+import json
+
+import pytest
+
+from exabgp.bgp.message.notification import Notify
+from exabgp.bgp.message.open.capability import Capabilities
+from exabgp.bgp.message.open.capability import LongLivedGraceful
+from exabgp.bgp.message.open.capability.capability import Capability
+from exabgp.bgp.message.open.capability.capability import CapabilityCode
+from exabgp.protocol.family import AFI, SAFI
+
+# ipv4 unicast, Forwarding State set, 3600 seconds
+IPV4_UNICAST_ENTRY = bytes.fromhex('0001' '01' '80' '000e10')
+# ipv6 unicast, no flags, the largest 24-bit time
+IPV6_UNICAST_ENTRY = bytes.fromhex('0002' '01' '00' 'ffffff')
+VALUE = IPV4_UNICAST_ENTRY + IPV6_UNICAST_ENTRY
+
+
+def optional_parameters(value: bytes) -> bytes:
+    """The OPEN optional parameters carrying one LLGR capability with this value."""
+    capability = bytes([0x47, len(value)]) + value
+    parameter = bytes([2, len(capability)]) + capability
+    return bytes([len(parameter)]) + parameter
+
+
+def test_capability_code_is_seventy_one() -> None:
+    assert Capability.CODE.LONG_LIVED_GRACEFUL_RESTART == 71
+    assert LongLivedGraceful.ID == 71
+    assert CapabilityCode(71).name() == 'long-lived-graceful-restart'
+
+
+def test_well_formed_capability_decodes() -> None:
+    capabilities = Capabilities.unpack(optional_parameters(VALUE))
+
+    llgr = capabilities[Capability.CODE.LONG_LIVED_GRACEFUL_RESTART]
+    assert isinstance(llgr, LongLivedGraceful), 'code 71 fell through to the unknown capability'
+    assert llgr[(AFI.ipv4, SAFI.unicast)] == (LongLivedGraceful.FORWARDING_STATE, 3600)
+    assert llgr[(AFI.ipv6, SAFI.unicast)] == (0, 0xFFFFFF)
+    assert len(llgr) == 2
+
+    assert llgr.extract_capability_bytes() == [VALUE]
+
+    assert str(llgr) == (
+        'Long-Lived Graceful Restart ipv4/unicast=flags 0x80 time 3600 ipv6/unicast=flags 0x0 time 16777215'
+    )
+    assert json.loads(llgr.json()) == {
+        'name': 'long-lived graceful restart',
+        'address-family': {
+            'ipv4/unicast': {'forwarding': True, 'time': 3600},
+            'ipv6/unicast': {'forwarding': False, 'time': 16777215},
+        },
+    }
+
+
+def test_reserved_flag_bits_are_ignored() -> None:
+    """RFC 9494 3: the bits other than F are reserved and ignored by the receiver."""
+    entry = bytes.fromhex('0001' '01' '7f' '00003c')
+    llgr = LongLivedGraceful.unpack_capability(
+        LongLivedGraceful(), memoryview(entry), Capability.CODE.LONG_LIVED_GRACEFUL_RESTART
+    )
+
+    assert isinstance(llgr, LongLivedGraceful)
+    assert llgr[(AFI.ipv4, SAFI.unicast)] == (0, 60)
+
+
+def test_empty_capability_decodes_to_no_family() -> None:
+    llgr = LongLivedGraceful.unpack_capability(
+        LongLivedGraceful(), memoryview(b''), Capability.CODE.LONG_LIVED_GRACEFUL_RESTART
+    )
+
+    assert isinstance(llgr, LongLivedGraceful)
+    assert len(llgr) == 0
+
+
+@pytest.mark.parametrize('cut', [1, 3, 6], ids=['one-octet-short', 'half-entry', 'missing-time'])
+def test_truncated_capability_is_refused(cut: int) -> None:
+    truncated = VALUE[: len(VALUE) - cut]
+
+    with pytest.raises(Notify) as raised:
+        Capabilities.unpack(optional_parameters(truncated))
+
+    assert raised.value.code == 2

```


===== RUN a052 =====
```diff
diff --git a/src/exabgp/bgp/message/open/capability/__init__.py b/src/exabgp/bgp/message/open/capability/__init__.py
index 5c60813..cc5816b 100644
--- a/src/exabgp/bgp/message/open/capability/__init__.py
+++ b/src/exabgp/bgp/message/open/capability/__init__.py
@@ -31,6 +31,7 @@ from exabgp.bgp.message.open.capability.refresh import REFRESH
 from exabgp.bgp.message.open.capability.linklocal import LinkLocalNextHop
 from exabgp.bgp.message.open.capability.role import Role
 from exabgp.bgp.message.open.capability.role import RoleValue
+from exabgp.bgp.message.open.capability.llgr import LongLivedGracefulRestart
 
 # Do not remove this include or unknown capability will not be handled
 from exabgp.bgp.message.open.capability.unknown import UnknownCapability
@@ -53,5 +54,6 @@ __all__ = [
     'LinkLocalNextHop',
     'Role',
     'RoleValue',
+    'LongLivedGracefulRestart',
     'UnknownCapability',
 ]
diff --git a/src/exabgp/bgp/message/open/capability/capability.py b/src/exabgp/bgp/message/open/capability/capability.py
index ffec782..5ce793e 100644
--- a/src/exabgp/bgp/message/open/capability/capability.py
+++ b/src/exabgp/bgp/message/open/capability/capability.py
@@ -64,6 +64,7 @@ class CapabilityCode(IntValue):
 
     # 6-63      Unassigned
     GRACEFUL_RESTART: ClassVar[int] = 0x40  # [RFC4724]
+    LONG_LIVED_GRACEFUL_RESTART: ClassVar[int] = 0x47  # [RFC9494]
     FOUR_BYTES_ASN: ClassVar[int] = 0x41  # [RFC4893]
     # 66        Deprecated
     DYNAMIC_CAPABILITY: ClassVar[int] = 0x43  # [Chen]
@@ -98,6 +99,7 @@ class CapabilityCode(IntValue):
         EXTENDED_MESSAGE: 'extended-message',
         ROLE: 'role',
         GRACEFUL_RESTART: 'graceful-restart',
+        LONG_LIVED_GRACEFUL_RESTART: 'long-lived-graceful-restart',
         FOUR_BYTES_ASN: 'asn4',
         DYNAMIC_CAPABILITY: 'dynamic-capability',
         MULTISESSION: 'multi-session',
@@ -145,6 +147,7 @@ class CapabilityCodes:
     EXTENDED_MESSAGE: ClassVar[CapabilityCode] =         CapabilityCode(CapabilityCode.EXTENDED_MESSAGE)
     ROLE: ClassVar[CapabilityCode] =                     CapabilityCode(CapabilityCode.ROLE)
     GRACEFUL_RESTART: ClassVar[CapabilityCode] =         CapabilityCode(CapabilityCode.GRACEFUL_RESTART)
+    LONG_LIVED_GRACEFUL_RESTART: ClassVar[CapabilityCode] = CapabilityCode(CapabilityCode.LONG_LIVED_GRACEFUL_RESTART)
     FOUR_BYTES_ASN: ClassVar[CapabilityCode] =           CapabilityCode(CapabilityCode.FOUR_BYTES_ASN)
     DYNAMIC_CAPABILITY: ClassVar[CapabilityCode] =       CapabilityCode(CapabilityCode.DYNAMIC_CAPABILITY)
     MULTISESSION: ClassVar[CapabilityCode] =             CapabilityCode(CapabilityCode.MULTISESSION)
diff --git a/src/exabgp/bgp/message/open/capability/llgr.py b/src/exabgp/bgp/message/open/capability/llgr.py
new file mode 100644
index 0000000..f1cba3c
--- /dev/null
+++ b/src/exabgp/bgp/message/open/capability/llgr.py
@@ -0,0 +1,104 @@
+"""llgr.py
+
+Long-Lived Graceful Restart capability (RFC 9494, capability code 71).
+
+The value is zero or more tuples <AFI, SAFI, Flags, Long-lived Stale Time>, seven octets
+each. The most significant bit of the Flags octet is the F bit (Forwarding State); the
+other bits are reserved, so they are kept as received and sent back as they came. The
+stale time is a 24 bit count of seconds.
+
+ExaBGP only parses and displays what a peer sends. Nothing here configures the capability
+or changes how routes are retained.
+
+Created for ExaBGP.
+Copyright (c) 2009-2017 Exa Networks. All rights reserved.
+License: 3-clause BSD. (See the COPYRIGHT file)
+"""
+
+from __future__ import annotations
+
+import json
+from typing import ClassVar, NamedTuple
+
+from exabgp.protocol.family import AFI, SAFI, FamilyTuple
+from exabgp.bgp.message.open.capability.capability import Capability, CapabilityCode, CapabilityDict
+from exabgp.bgp.message.notification import Notify
+from exabgp.logger import log, lazymsg
+
+
+class LongLivedEntry(NamedTuple):
+    """What a peer says about one family: the Flags octet and the stale time in seconds."""
+
+    flags: int
+    stale_time: int
+
+
+class LongLivedGracefulRestart(CapabilityDict[FamilyTuple, LongLivedEntry]):
+    """RFC 9494 Long-Lived Graceful Restart capability, one entry per family."""
+
+    ID: ClassVar = Capability.CODE.LONG_LIVED_GRACEFUL_RESTART
+
+    ENTRY_SIZE: ClassVar[int] = 7  # AFI(2) + SAFI(1) + Flags(1) + Long-lived Stale Time(3)
+    STALE_TIME_SIZE: ClassVar[int] = 3
+    STALE_TIME_MAX: ClassVar[int] = 0xFFFFFF
+    FORWARDING_STATE: ClassVar[int] = 0x80  # RFC 9494 3: the F bit is the most significant bit
+
+    def add(self, afi: AFI, safi: SAFI, flags: int, stale_time: int) -> None:
+        assert 0 <= flags <= 0xFF, 'the Flags field is one octet'
+        assert 0 <= stale_time <= LongLivedGracefulRestart.STALE_TIME_MAX, 'the stale time is 24 bits'
+        self[(afi, safi)] = LongLivedEntry(flags, stale_time)
+
+    def extract_capability_bytes(self) -> list[bytes]:
+        if not self:
+            return []
+        entries = [
+            afi.pack_afi()
+            + safi.pack_safi()
+            + bytes([entry.flags])
+            + entry.stale_time.to_bytes(LongLivedGracefulRestart.STALE_TIME_SIZE, 'big')
+            for (afi, safi), entry in self.items()
+        ]
+        return [b''.join(entries)]
+
+    def __str__(self) -> str:
+        if not self:
+            return 'Long-Lived Graceful Restart (no families)'
+        families = ' '.join(
+            f'{afi}/{safi}={hex(entry.flags)} stale {entry.stale_time}' for (afi, safi), entry in self.items()
+        )
+        return f'Long-Lived Graceful Restart {families}'
+
+    def json(self) -> str:
+        families = {
+            f'{afi}/{safi}': {
+                'forwarding': bool(entry.flags & LongLivedGracefulRestart.FORWARDING_STATE),
+                'flags': entry.flags,
+                'stale-time': entry.stale_time,
+            }
+            for (afi, safi), entry in self.items()
+        }
+        return json.dumps({'name': 'long-lived graceful restart', 'families': families})
+
+    @classmethod
+    def unpack_capability(cls, instance: Capability, data, capability: CapabilityCode) -> Capability:  # pylint: disable=W0613
+        assert isinstance(instance, LongLivedGracefulRestart)
+        # The peer controls this length, so it is checked, never asserted.
+        raw = bytes(data)
+        if len(raw) % cls.ENTRY_SIZE:
+            detail = f'Long-Lived Graceful Restart capability is {len(raw)} octets, not a multiple of {cls.ENTRY_SIZE}'
+            raise Notify(2, 0, detail)
+        # RFC 5492 section 5: a repeated capability replaces the one before it, as Graceful Restart does.
+        if len(instance) > 0:
+            log.debug(lazymsg('capability.llgr.duplicate action=replace'), 'parser')
+            instance.clear()
+        for offset in range(0, len(raw), cls.ENTRY_SIZE):
+            entry = raw[offset : offset + cls.ENTRY_SIZE]
+            afi = AFI.unpack_afi(entry[:2])
+            safi = SAFI.unpack_safi(entry[2:3])
+            flags = entry[3]
+            stale_time = int.from_bytes(entry[4:], 'big')
+            instance.add(afi, safi, flags, stale_time)
+        return instance
+
+
+Capability.register()(LongLivedGracefulRestart)
diff --git a/tests/unit/test_llgr_capability.py b/tests/unit/test_llgr_capability.py
new file mode 100644
index 0000000..e8d5533
--- /dev/null
+++ b/tests/unit/test_llgr_capability.py
@@ -0,0 +1,70 @@
+#!/usr/bin/env python3
+# encoding: utf-8
+"""test_llgr_capability.py
+
+RFC 9494 Long-Lived Graceful Restart capability (code 71).
+
+The value is zero or more seven octet tuples <AFI, SAFI, Flags, Long-lived Stale Time>.
+The tests hold the wire format for a well formed value, the refusal of a value cut
+short inside a tuple, and the encoding back to the same octets.
+
+Created for ExaBGP testing framework
+License: 3-clause BSD
+"""
+
+import json
+
+import pytest
+
+from exabgp.bgp.message.notification import Notify
+from exabgp.bgp.message.open.capability.capability import Capability
+from exabgp.bgp.message.open.capability.capability import CapabilityCode
+from exabgp.bgp.message.open.capability.llgr import LongLivedEntry
+from exabgp.bgp.message.open.capability.llgr import LongLivedGracefulRestart
+from exabgp.protocol.family import AFI
+from exabgp.protocol.family import SAFI
+
+# IPv4 unicast, F bit set, 3600 seconds; then IPv6 unicast, F bit clear, 0x010203 seconds
+WELL_FORMED = bytes.fromhex('00010180000e10' '00020100010203')
+
+
+def test_capability_code_is_71_and_named() -> None:
+    """RFC 9494 assigns capability code 71, and the registry names it for logs and JSON."""
+    assert Capability.CODE.LONG_LIVED_GRACEFUL_RESTART == 71
+    assert LongLivedGracefulRestart.ID == 71
+    assert CapabilityCode(71).name() == 'long-lived-graceful-restart'
+
+
+def test_well_formed_capability_decodes() -> None:
+    """Each tuple gives its family, its Forwarding State bit and its 24 bit stale time."""
+    parsed = Capability.unpack(CapabilityCode(71), {}, WELL_FORMED)
+
+    assert isinstance(parsed, LongLivedGracefulRestart)
+    assert len(parsed) == 2
+    assert parsed[(AFI.ipv4, SAFI.unicast)] == LongLivedEntry(0x80, 3600)
+    assert parsed[(AFI.ipv6, SAFI.unicast)] == LongLivedEntry(0x00, 0x010203)
+
+    rendered = json.loads(parsed.json())
+    assert rendered['name'] == 'long-lived graceful restart'
+    assert rendered['families']['ipv4/unicast'] == {'forwarding': True, 'flags': 0x80, 'stale-time': 3600}
+    assert rendered['families']['ipv6/unicast']['forwarding'] is False
+    assert 'Long-Lived Graceful Restart' in str(parsed)
+
+
+def test_truncated_capability_is_refused() -> None:
+    """A tuple cut short is a malformed capability, answered with a NOTIFICATION, not an IndexError."""
+    truncated = WELL_FORMED[:-3]  # the second tuple is 4 of its 7 octets
+
+    with pytest.raises(Notify) as raised:
+        Capability.unpack(CapabilityCode(71), {}, truncated)
+
+    assert raised.value.code == 2
+    assert raised.value.subcode == 0
+
+
+def test_decoded_entries_encode_back_to_the_same_octets() -> None:
+    """What a peer sent is what we would send back: the same families, flags and stale times."""
+    parsed = Capability.unpack(CapabilityCode(71), {}, WELL_FORMED)
+
+    assert isinstance(parsed, LongLivedGracefulRestart)
+    assert parsed.extract_capability_bytes() == [WELL_FORMED]

```


===== RUN a047 =====
```diff
diff --git a/src/exabgp/bgp/message/open/capability/__init__.py b/src/exabgp/bgp/message/open/capability/__init__.py
index 5c60813..6a6b91d 100644
--- a/src/exabgp/bgp/message/open/capability/__init__.py
+++ b/src/exabgp/bgp/message/open/capability/__init__.py
@@ -22,6 +22,7 @@ from exabgp.bgp.message.open.capability.pathslimit import PathsLimit
 from exabgp.bgp.message.open.capability.labels import MultipleLabels
 from exabgp.bgp.message.open.capability.asn4 import ASN4
 from exabgp.bgp.message.open.capability.graceful import Graceful
+from exabgp.bgp.message.open.capability.llgr import LongLivedGracefulRestart
 from exabgp.bgp.message.open.capability.mp import MultiProtocol
 from exabgp.bgp.message.open.capability.ms import MultiSession
 from exabgp.bgp.message.open.capability.operational import Operational
@@ -44,6 +45,7 @@ __all__ = [
     'PathsLimit',
     'ASN4',
     'Graceful',
+    'LongLivedGracefulRestart',
     'MultiProtocol',
     'MultiSession',
     'Operational',
diff --git a/src/exabgp/bgp/message/open/capability/capability.py b/src/exabgp/bgp/message/open/capability/capability.py
index ef3617f..6ed4933 100644
--- a/src/exabgp/bgp/message/open/capability/capability.py
+++ b/src/exabgp/bgp/message/open/capability/capability.py
@@ -66,6 +66,7 @@ class CapabilityCode(IntValue):
     GRACEFUL_RESTART: ClassVar[int] = 0x40  # [RFC4724]
     FOUR_BYTES_ASN: ClassVar[int] = 0x41  # [RFC4893]
     # 66        Deprecated
+    LONG_LIVED_GRACEFUL_RESTART: ClassVar[int] = 0x47  # [RFC9494]
     DYNAMIC_CAPABILITY: ClassVar[int] = 0x43  # [Chen]
     MULTISESSION: ClassVar[int] = 0x44  # [draft-ietf-idr-bgp-multisession]
     ADD_PATH: ClassVar[int] = 0x45  # [draft-ietf-idr-add-paths]
@@ -98,6 +99,7 @@ class CapabilityCode(IntValue):
         EXTENDED_MESSAGE: 'extended-message',
         ROLE: 'role',
         GRACEFUL_RESTART: 'graceful-restart',
+        LONG_LIVED_GRACEFUL_RESTART: 'long-lived-graceful-restart',
         FOUR_BYTES_ASN: 'asn4',
         DYNAMIC_CAPABILITY: 'dynamic-capability',
         MULTISESSION: 'multi-session',
@@ -145,6 +147,7 @@ class CapabilityCodes:
     EXTENDED_MESSAGE: ClassVar[CapabilityCode] =         CapabilityCode(CapabilityCode.EXTENDED_MESSAGE)
     ROLE: ClassVar[CapabilityCode] =                     CapabilityCode(CapabilityCode.ROLE)
     GRACEFUL_RESTART: ClassVar[CapabilityCode] =         CapabilityCode(CapabilityCode.GRACEFUL_RESTART)
+    LONG_LIVED_GRACEFUL_RESTART: ClassVar[CapabilityCode] = CapabilityCode(CapabilityCode.LONG_LIVED_GRACEFUL_RESTART)
     FOUR_BYTES_ASN: ClassVar[CapabilityCode] =           CapabilityCode(CapabilityCode.FOUR_BYTES_ASN)
     DYNAMIC_CAPABILITY: ClassVar[CapabilityCode] =       CapabilityCode(CapabilityCode.DYNAMIC_CAPABILITY)
     MULTISESSION: ClassVar[CapabilityCode] =             CapabilityCode(CapabilityCode.MULTISESSION)
diff --git a/src/exabgp/bgp/message/open/capability/llgr.py b/src/exabgp/bgp/message/open/capability/llgr.py
new file mode 100644
index 0000000..fb5b021
--- /dev/null
+++ b/src/exabgp/bgp/message/open/capability/llgr.py
@@ -0,0 +1,92 @@
+"""llgr.py
+
+Long-Lived Graceful Restart capability (RFC 9494, capability code 71).
+
+The value is a list of entries, one per family: AFI (2 octets), SAFI (1 octet), one
+flags octet and the Long-lived Stale Time (3 octets, seconds). This module reads what a
+peer sends and writes it back unchanged. It does not act on it: no route is retained on
+the strength of this capability.
+
+Created for ExaBGP.
+Copyright (c) 2009-2017 Exa Networks. All rights reserved.
+License: 3-clause BSD. (See the COPYRIGHT file)
+"""
+
+from __future__ import annotations
+
+import json
+from typing import ClassVar, NamedTuple
+
+from exabgp.bgp.message.notification import Notify
+from exabgp.bgp.message.open.capability.capability import Capability
+from exabgp.bgp.message.open.capability.capability import CapabilityCode
+from exabgp.bgp.message.open.capability.capability import CapabilityDict
+from exabgp.protocol.family import AFI, SAFI, FamilyTuple
+from exabgp.util.types import Buffer
+
+
+class LongLivedFamily(NamedTuple):
+    """What the peer said about one family: its flags octet, and the stale time in seconds."""
+
+    flags: int
+    stale_time: int
+
+
+class LongLivedGracefulRestart(CapabilityDict[FamilyTuple, LongLivedFamily]):
+    ID: ClassVar = Capability.CODE.LONG_LIVED_GRACEFUL_RESTART
+
+    # AFI(2) + SAFI(1) + flags(1) + Long-lived Stale Time(3)
+    ENTRY_SIZE: ClassVar[int] = 7
+    STALE_TIME_SIZE: ClassVar[int] = 3
+    STALE_TIME_MAX: ClassVar[int] = 0xFFFFFF
+
+    def __str__(self) -> str:
+        families = ''.join(
+            f' {afi}/{safi} flags {hex(family.flags)} stale-time {family.stale_time}'
+            for (afi, safi), family in self.items()
+        )
+        return f'Long-Lived Graceful Restart{families}'
+
+    def json(self) -> str:
+        families = [
+            {'afi': str(afi), 'safi': str(safi), 'flags': family.flags, 'stale-time': family.stale_time}
+            for (afi, safi), family in self.items()
+        ]
+        return json.dumps({'name': 'long-lived-graceful-restart', 'families': families})
+
+    def extract_capability_bytes(self) -> list[bytes]:
+        entries = [self._pack_entry(afi, safi, family) for (afi, safi), family in self.items()]
+        # One value even when it holds no entries: a zero length capability is still a
+        # capability the peer sent, and dropping it would lose it on the way back out.
+        return [b''.join(entries)]
+
+    @classmethod
+    def _pack_entry(cls, afi: AFI, safi: SAFI, family: LongLivedFamily) -> bytes:
+        assert 0 <= family.stale_time <= cls.STALE_TIME_MAX, 'the stale time is 24 bits'
+        assert 0 <= family.flags <= 0xFF, 'the flags are one octet'
+        stale_time = family.stale_time.to_bytes(cls.STALE_TIME_SIZE, 'big')
+        return afi.pack_afi() + safi.pack_safi() + bytes([family.flags]) + stale_time
+
+    @classmethod
+    def unpack_capability(cls, instance: Capability, data: Buffer, capability: CapabilityCode) -> Capability:  # pylint: disable=W0613
+        assert isinstance(instance, LongLivedGracefulRestart)
+        # The peer controls the length, so it is checked, never asserted. A partial entry
+        # is refused rather than read as a shorter family.
+        if len(data) % cls.ENTRY_SIZE:
+            padded = (len(data) // cls.ENTRY_SIZE + 1) * cls.ENTRY_SIZE
+            raise Notify.short(2, 0, 'Long-Lived Graceful Restart capability', padded, len(data))
+
+        # RFC 5492 section 5: a capability sent more than once is one answer, and the last
+        # one read replaces what came before, as Graceful Restart does.
+        instance.clear()
+        for offset in range(0, len(data), cls.ENTRY_SIZE):
+            entry = data[offset : offset + cls.ENTRY_SIZE]
+            afi = AFI.unpack_afi(entry[0:2])
+            safi = SAFI.unpack_safi(entry[2:3])
+            flags = entry[3]
+            stale_time = int.from_bytes(entry[4:7], 'big')
+            instance[(afi, safi)] = LongLivedFamily(flags, stale_time)
+        return instance
+
+
+Capability.register()(LongLivedGracefulRestart)
diff --git a/tests/unit/test_long_lived_graceful_restart.py b/tests/unit/test_long_lived_graceful_restart.py
new file mode 100644
index 0000000..8c4d4ee
--- /dev/null
+++ b/tests/unit/test_long_lived_graceful_restart.py
@@ -0,0 +1,61 @@
+"""test_long_lived_graceful_restart.py
+
+RFC 9494 Long-Lived Graceful Restart capability (code 71). A peer's capability is read
+into one entry per family, with its flags octet and its 24 bit stale time, and it is
+written back the same way. A truncated entry is refused with a NOTIFICATION.
+"""
+
+from __future__ import annotations
+
+import json
+
+import pytest
+
+from exabgp.bgp.message.notification import Notify
+from exabgp.bgp.message.open.capability import Capabilities
+from exabgp.bgp.message.open.capability import Capability
+from exabgp.bgp.message.open.capability import LongLivedGracefulRestart
+from exabgp.protocol.family import AFI, SAFI
+
+# AFI (2), SAFI (1), flags (1), Long-lived Stale Time (3)
+IPV4_UNICAST = bytes([0x00, 0x01, 0x01, 0x80, 0x00, 0x0E, 0x10])  # 3600 seconds
+IPV6_UNICAST = bytes([0x00, 0x02, 0x01, 0x00, 0x01, 0x51, 0x80])  # 86400 seconds
+
+
+def test_a_well_formed_capability_is_decoded_and_written_back() -> None:
+    data = IPV4_UNICAST + IPV6_UNICAST
+
+    capability = Capability.unpack(Capability.CODE.LONG_LIVED_GRACEFUL_RESTART, Capabilities(), data)
+
+    assert isinstance(capability, LongLivedGracefulRestart)
+    assert int(capability.code()) == 71
+    ipv4 = capability[(AFI.ipv4, SAFI.unicast)]
+    assert ipv4.flags == 0x80
+    assert ipv4.stale_time == 3600
+    ipv6 = capability[(AFI.ipv6, SAFI.unicast)]
+    assert ipv6.flags == 0x00
+    assert ipv6.stale_time == 86400
+    assert capability.extract_capability_bytes() == [data]
+    assert str(capability) == (
+        'Long-Lived Graceful Restart ipv4/unicast flags 0x80 stale-time 3600 '
+        'ipv6/unicast flags 0x0 stale-time 86400'
+    )
+    assert json.loads(capability.json()) == {
+        'name': 'long-lived-graceful-restart',
+        'families': [
+            {'afi': 'ipv4', 'safi': 'unicast', 'flags': 0x80, 'stale-time': 3600},
+            {'afi': 'ipv6', 'safi': 'unicast', 'flags': 0x00, 'stale-time': 86400},
+        ],
+    }
+
+
+def test_a_truncated_entry_is_refused_with_a_notification() -> None:
+    # The second entry is cut after its SAFI and flags: 4 of the 7 octets it needs
+    data = IPV4_UNICAST + IPV6_UNICAST[:4]
+
+    with pytest.raises(Notify) as raised:
+        Capability.unpack(Capability.CODE.LONG_LIVED_GRACEFUL_RESTART, Capabilities(), data)
+
+    assert raised.value.code == 2
+    assert raised.value.subcode == 0
+    assert 'needs 14 octets, got 11' in str(raised.value)

```


===== RUN a040 =====
```diff
diff --git a/src/exabgp/bgp/message/open/capability/__init__.py b/src/exabgp/bgp/message/open/capability/__init__.py
index 5c60813..6a6b91d 100644
--- a/src/exabgp/bgp/message/open/capability/__init__.py
+++ b/src/exabgp/bgp/message/open/capability/__init__.py
@@ -22,6 +22,7 @@ from exabgp.bgp.message.open.capability.pathslimit import PathsLimit
 from exabgp.bgp.message.open.capability.labels import MultipleLabels
 from exabgp.bgp.message.open.capability.asn4 import ASN4
 from exabgp.bgp.message.open.capability.graceful import Graceful
+from exabgp.bgp.message.open.capability.llgr import LongLivedGracefulRestart
 from exabgp.bgp.message.open.capability.mp import MultiProtocol
 from exabgp.bgp.message.open.capability.ms import MultiSession
 from exabgp.bgp.message.open.capability.operational import Operational
@@ -44,6 +45,7 @@ __all__ = [
     'PathsLimit',
     'ASN4',
     'Graceful',
+    'LongLivedGracefulRestart',
     'MultiProtocol',
     'MultiSession',
     'Operational',
diff --git a/src/exabgp/bgp/message/open/capability/capability.py b/src/exabgp/bgp/message/open/capability/capability.py
index 89e00a2..4188f9c 100644
--- a/src/exabgp/bgp/message/open/capability/capability.py
+++ b/src/exabgp/bgp/message/open/capability/capability.py
@@ -70,6 +70,7 @@ class CapabilityCode(IntValue):
     MULTISESSION: ClassVar[int] = 0x44  # [draft-ietf-idr-bgp-multisession]
     ADD_PATH: ClassVar[int] = 0x45  # [draft-ietf-idr-add-paths]
     ENHANCED_ROUTE_REFRESH: ClassVar[int] = 0x46  # [draft-ietf-idr-bgp-enhanced-route-refresh]
+    LONG_LIVED_GRACEFUL_RESTART: ClassVar[int] = 0x47  # [RFC9494]
     PATHS_LIMIT: ClassVar[int] = 0x4C  # [draft-abraitis-idr-addpath-paths-limit]
     LINK_LOCAL_NEXTHOP: ClassVar[int] = 0x4D  # [draft-ietf-idr-linklocal-capability]
     # 78-127    Unassigned
@@ -103,6 +104,7 @@ class CapabilityCode(IntValue):
         MULTISESSION: 'multi-session',
         ADD_PATH: 'add-path',
         ENHANCED_ROUTE_REFRESH: 'enhanced-route-refresh',
+        LONG_LIVED_GRACEFUL_RESTART: 'long-lived-graceful-restart',
         PATHS_LIMIT: 'paths-limit',
         MULTIPLE_LABELS: 'multiple-labels',
         LINK_LOCAL_NEXTHOP: 'link-local-nexthop',
@@ -150,6 +152,7 @@ class CapabilityCodes:
     MULTISESSION: ClassVar[CapabilityCode] =             CapabilityCode(CapabilityCode.MULTISESSION)
     ADD_PATH: ClassVar[CapabilityCode] =                 CapabilityCode(CapabilityCode.ADD_PATH)
     ENHANCED_ROUTE_REFRESH: ClassVar[CapabilityCode] =   CapabilityCode(CapabilityCode.ENHANCED_ROUTE_REFRESH)
+    LONG_LIVED_GRACEFUL_RESTART: ClassVar[CapabilityCode] = CapabilityCode(CapabilityCode.LONG_LIVED_GRACEFUL_RESTART)
     PATHS_LIMIT: ClassVar[CapabilityCode] =              CapabilityCode(CapabilityCode.PATHS_LIMIT)
     MULTIPLE_LABELS: ClassVar[CapabilityCode] =          CapabilityCode(CapabilityCode.MULTIPLE_LABELS)
     LINK_LOCAL_NEXTHOP: ClassVar[CapabilityCode] =       CapabilityCode(CapabilityCode.LINK_LOCAL_NEXTHOP)
diff --git a/src/exabgp/bgp/message/open/capability/llgr.py b/src/exabgp/bgp/message/open/capability/llgr.py
new file mode 100644
index 0000000..682c060
--- /dev/null
+++ b/src/exabgp/bgp/message/open/capability/llgr.py
@@ -0,0 +1,85 @@
+"""llgr.py
+
+Long-Lived Graceful Restart Capability (RFC 9494), code 71.
+
+The capability value is zero or more tuples, each of which is:
+AFI (2 octets), SAFI (1 octet), Flags (1 octet), Long-lived Stale Time (3 octets).
+"""
+
+# https://datatracker.ietf.org/doc/html/rfc9494
+
+from __future__ import annotations
+
+from typing import ClassVar
+
+from exabgp.protocol.family import AFI, SAFI, FamilyTuple
+from exabgp.bgp.message.open.capability.capability import Capability, CapabilityDict
+from exabgp.bgp.message.open.capability.capability import CapabilityCode
+from exabgp.bgp.message.notification import Notify
+from exabgp.logger import log, lazymsg
+from exabgp.util.types import Buffer
+
+
+class LongLivedGracefulRestart(CapabilityDict[FamilyTuple, tuple[int, int]]):
+    """Per family: the flags octet and the long-lived stale time in seconds."""
+
+    ID: ClassVar = Capability.CODE.LONG_LIVED_GRACEFUL_RESTART
+    ENTRY_SIZE: ClassVar[int] = 7  # AFI(2) + SAFI(1) + Flags(1) + Long-lived Stale Time(3)
+    MAX_STALE_TIME: ClassVar[int] = 0xFFFFFF
+
+    # RFC 9494 section 3: the most significant bit of the flags is the F bit, the
+    # Forwarding State. The remaining bits are reserved and ignored on arrival.
+    FORWARDING_STATE: ClassVar[int] = 0x80
+
+    def set_entry(self, afi: AFI, safi: SAFI, flags: int, stale_time: int) -> None:
+        if not (0 <= flags <= 0xFF):
+            raise ValueError(f'long-lived graceful restart flags must be 0-255, got {flags}')
+        if not (0 <= stale_time <= self.MAX_STALE_TIME):
+            raise ValueError(f'long-lived stale time must be 0-{self.MAX_STALE_TIME}, got {stale_time}')
+        self[(afi, safi)] = (flags, stale_time)
+
+    def __str__(self) -> str:
+        entries = ' '.join(
+            f'{afi}/{safi} flags {hex(flags)} stale-time {stale}' for (afi, safi), (flags, stale) in self.items()
+        )
+        return f'Long-Lived Graceful Restart {entries}'.rstrip()
+
+    def json(self) -> str:
+        families = ', '.join(
+            '"{}/{}": {{ "forwarding": {}, "flags": {}, "stale-time": {} }}'.format(
+                afi,
+                safi,
+                'true' if flags & self.FORWARDING_STATE else 'false',
+                flags,
+                stale,
+            )
+            for (afi, safi), (flags, stale) in self.items()
+        )
+        return '{{ "name": "long-lived-graceful-restart", "address-families": {{ {} }} }}'.format(families)
+
+    def extract_capability_bytes(self) -> list[bytes]:
+        value = b''
+        for (afi, safi), (flags, stale) in self.items():
+            value += afi.pack_afi() + safi.pack_safi() + bytes([flags]) + stale.to_bytes(3, 'big')
+        return [value]
+
+    @classmethod
+    def unpack_capability(cls, instance: Capability, data: Buffer, capability: CapabilityCode) -> Capability:  # pylint: disable=W0613
+        assert isinstance(instance, LongLivedGracefulRestart)
+        if len(instance) > 0:
+            log.debug(lazymsg('capability.long-lived-graceful-restart.duplicate action=replace'), 'parser')
+            instance.clear()
+        view = memoryview(data)
+        while view:
+            if len(view) < cls.ENTRY_SIZE:
+                raise Notify.short(2, 0, 'Long-Lived Graceful Restart capability entry', cls.ENTRY_SIZE, len(view))
+            afi = AFI.unpack_afi(view[:2])
+            safi = SAFI.unpack_safi(view[2:3])
+            flags = view[3]
+            stale_time = (view[4] << 16) | (view[5] << 8) | view[6]
+            instance.set_entry(afi, safi, flags, stale_time)
+            view = view[cls.ENTRY_SIZE :]
+        return instance
+
+
+Capability.register()(LongLivedGracefulRestart)
diff --git a/tests/unit/test_llgr_capability.py b/tests/unit/test_llgr_capability.py
new file mode 100644
index 0000000..48b5674
--- /dev/null
+++ b/tests/unit/test_llgr_capability.py
@@ -0,0 +1,64 @@
+"""Long-Lived Graceful Restart capability (RFC 9494), code 71: decoding and encoding."""
+
+from __future__ import annotations
+
+import json
+
+import pytest
+
+from exabgp.bgp.message.notification import Notify
+from exabgp.bgp.message.open.capability.capability import Capability
+from exabgp.bgp.message.open.capability.llgr import LongLivedGracefulRestart
+from exabgp.protocol.family import AFI, SAFI
+
+# AFI(2) SAFI(1) Flags(1) Long-lived Stale Time(3)
+IPV4_UNICAST = b'\x00\x01\x01\x80\x00\x0e\x10'  # F bit set, 3600 seconds
+IPV6_UNICAST = b'\x00\x02\x01\x00\xff\xff\xff'  # F bit clear, maximum stale time
+
+
+def test_code_71_is_registered_as_long_lived_graceful_restart() -> None:
+    assert Capability.CODE.LONG_LIVED_GRACEFUL_RESTART == 71
+    assert str(Capability.CODE.LONG_LIVED_GRACEFUL_RESTART) == 'long-lived-graceful-restart'
+    assert Capability.klass(Capability.CODE.LONG_LIVED_GRACEFUL_RESTART) is LongLivedGracefulRestart
+
+
+def test_well_formed_capability_decodes_each_family() -> None:
+    decoded = Capability.unpack(Capability.CODE.LONG_LIVED_GRACEFUL_RESTART, {}, IPV4_UNICAST + IPV6_UNICAST)
+
+    assert isinstance(decoded, LongLivedGracefulRestart)
+    assert decoded[(AFI.ipv4, SAFI.unicast)] == (0x80, 3600)
+    assert decoded[(AFI.ipv6, SAFI.unicast)] == (0x00, 0xFFFFFF)
+    assert len(decoded) == 2
+
+
+def test_well_formed_capability_encodes_back_to_the_same_bytes() -> None:
+    decoded = LongLivedGracefulRestart.unpack_capability(
+        LongLivedGracefulRestart(), IPV4_UNICAST + IPV6_UNICAST, Capability.CODE.LONG_LIVED_GRACEFUL_RESTART
+    )
+
+    assert decoded.extract_capability_bytes() == [IPV4_UNICAST + IPV6_UNICAST]
+
+
+def test_str_and_json_show_the_family_flags_and_stale_time() -> None:
+    decoded = LongLivedGracefulRestart.unpack_capability(
+        LongLivedGracefulRestart(), IPV4_UNICAST, Capability.CODE.LONG_LIVED_GRACEFUL_RESTART
+    )
+
+    assert str(decoded) == 'Long-Lived Graceful Restart ipv4/unicast flags 0x80 stale-time 3600'
+    parsed = json.loads(decoded.json())
+    assert parsed['name'] == 'long-lived-graceful-restart'
+    assert parsed['address-families']['ipv4/unicast'] == {'forwarding': True, 'flags': 0x80, 'stale-time': 3600}
+
+
+def test_truncated_entry_is_refused_with_a_notification() -> None:
+    # The IPv4 entry is complete, the IPv6 one stops after its flags octet
+    truncated = IPV4_UNICAST + b'\x00\x02\x01\x00'
+
+    with pytest.raises(Notify) as raised:
+        LongLivedGracefulRestart.unpack_capability(
+            LongLivedGracefulRestart(), truncated, Capability.CODE.LONG_LIVED_GRACEFUL_RESTART
+        )
+
+    assert raised.value.code == 2
+    assert raised.value.subcode == 0
+    assert 'needs 7 octets, got 4' in str(raised.value)

```


===== RUN a049 =====
```diff
diff --git a/src/exabgp/bgp/message/open/capability/__init__.py b/src/exabgp/bgp/message/open/capability/__init__.py
index 5c60813..7827230 100644
--- a/src/exabgp/bgp/message/open/capability/__init__.py
+++ b/src/exabgp/bgp/message/open/capability/__init__.py
@@ -29,6 +29,7 @@ from exabgp.bgp.message.open.capability.refresh import RouteRefresh
 from exabgp.bgp.message.open.capability.refresh import EnhancedRouteRefresh
 from exabgp.bgp.message.open.capability.refresh import REFRESH
 from exabgp.bgp.message.open.capability.linklocal import LinkLocalNextHop
+from exabgp.bgp.message.open.capability.llgr import LongLivedGraceful
 from exabgp.bgp.message.open.capability.role import Role
 from exabgp.bgp.message.open.capability.role import RoleValue
 
@@ -51,6 +52,7 @@ __all__ = [
     'EnhancedRouteRefresh',
     'REFRESH',
     'LinkLocalNextHop',
+    'LongLivedGraceful',
     'Role',
     'RoleValue',
     'UnknownCapability',
diff --git a/src/exabgp/bgp/message/open/capability/capability.py b/src/exabgp/bgp/message/open/capability/capability.py
index ffec782..5797f8e 100644
--- a/src/exabgp/bgp/message/open/capability/capability.py
+++ b/src/exabgp/bgp/message/open/capability/capability.py
@@ -72,6 +72,7 @@ class CapabilityCode(IntValue):
     ENHANCED_ROUTE_REFRESH: ClassVar[int] = 0x46  # [draft-ietf-idr-bgp-enhanced-route-refresh]
     PATHS_LIMIT: ClassVar[int] = 0x4C  # [draft-abraitis-idr-addpath-paths-limit]
     LINK_LOCAL_NEXTHOP: ClassVar[int] = 0x4D  # [draft-ietf-idr-linklocal-capability]
+    LONG_LIVED_GRACEFUL_RESTART: ClassVar[int] = 0x47  # [RFC9494]
     # 78-127    Unassigned
     ROUTE_REFRESH_CISCO: ClassVar[int] = 0x80  # I Can only find reference to this in the router logs
     # 128-255   Reserved for Private Use [RFC5492]
@@ -106,6 +107,7 @@ class CapabilityCode(IntValue):
         PATHS_LIMIT: 'paths-limit',
         MULTIPLE_LABELS: 'multiple-labels',
         LINK_LOCAL_NEXTHOP: 'link-local-nexthop',
+        LONG_LIVED_GRACEFUL_RESTART: 'long-lived-graceful-restart',
         OPERATIONAL: 'operational',
         ROUTE_REFRESH_CISCO: 'cisco-route-refresh',
         MULTISESSION_CISCO: 'cisco-multi-sesion',
@@ -153,6 +155,7 @@ class CapabilityCodes:
     PATHS_LIMIT: ClassVar[CapabilityCode] =              CapabilityCode(CapabilityCode.PATHS_LIMIT)
     MULTIPLE_LABELS: ClassVar[CapabilityCode] =          CapabilityCode(CapabilityCode.MULTIPLE_LABELS)
     LINK_LOCAL_NEXTHOP: ClassVar[CapabilityCode] =       CapabilityCode(CapabilityCode.LINK_LOCAL_NEXTHOP)
+    LONG_LIVED_GRACEFUL_RESTART: ClassVar[CapabilityCode] = CapabilityCode(CapabilityCode.LONG_LIVED_GRACEFUL_RESTART)
     ROUTE_REFRESH_CISCO: ClassVar[CapabilityCode] =      CapabilityCode(CapabilityCode.ROUTE_REFRESH_CISCO)
     MULTISESSION_CISCO: ClassVar[CapabilityCode] =       CapabilityCode(CapabilityCode.MULTISESSION_CISCO)
     HOSTNAME: ClassVar[CapabilityCode] =                 CapabilityCode(CapabilityCode.HOSTNAME)
diff --git a/src/exabgp/bgp/message/open/capability/llgr.py b/src/exabgp/bgp/message/open/capability/llgr.py
new file mode 100644
index 0000000..6ae23c2
--- /dev/null
+++ b/src/exabgp/bgp/message/open/capability/llgr.py
@@ -0,0 +1,79 @@
+"""llgr.py
+
+Long-Lived Graceful Restart Capability (RFC 9494).
+
+License: 3-clause BSD. (See the COPYRIGHT file)
+"""
+
+# https://www.rfc-editor.org/rfc/rfc9494.html
+
+from __future__ import annotations
+
+from typing import ClassVar
+
+from exabgp.protocol.family import AFI, SAFI, FamilyTuple
+from exabgp.bgp.message.open.capability.capability import Capability, CapabilityDict
+from exabgp.bgp.message.open.capability.capability import CapabilityCode
+from exabgp.bgp.message.notification import Notify
+
+
+class LongLivedGraceful(CapabilityDict[FamilyTuple, tuple[int, int]]):
+    """One entry per family: the flags octet and the Long-lived Stale Time in seconds."""
+
+    ID: ClassVar = Capability.CODE.LONG_LIVED_GRACEFUL_RESTART
+    # Each entry: AFI(2) + SAFI(1) + Flags(1) + Long-lived Stale Time(3)
+    ENTRY_SIZE: ClassVar[int] = 7
+    STALE_TIME_MAX: ClassVar[int] = 0xFFFFFF
+    # The F bit, the Forwarding State bit of Graceful Restart (RFC 4724)
+    FORWARDING_STATE: ClassVar[int] = 0x80
+
+    def set_entry(self, afi: AFI, safi: SAFI, flags: int, stale_time: int) -> None:
+        if not (0 <= flags <= 0xFF):
+            raise ValueError(f'long-lived graceful restart flags must be one octet, got {flags}')
+        if not (0 <= stale_time <= self.STALE_TIME_MAX):
+            raise ValueError(f'long-lived stale time must be 0-{self.STALE_TIME_MAX}, got {stale_time}')
+        self[(afi, safi)] = (flags, stale_time)
+
+    def __str__(self) -> str:
+        entries = ', '.join(
+            f'{afi} {safi} flags {flags:#x} stale-time {stale}' for (afi, safi), (flags, stale) in self.items()
+        )
+        return f'LongLivedGraceful({entries})'
+
+    def json(self) -> str:
+        families = ', '.join(
+            f'"{afi}/{safi}": {{ "flags": {flags}, "stale-time": {stale} }}'
+            for (afi, safi), (flags, stale) in self.items()
+        )
+        return '{{ "name": "long-lived-graceful-restart"{}{} }}'.format(', ' if families else '', families)
+
+    def extract_capability_bytes(self) -> list[bytes]:
+        if not self:
+            return []
+        entries = b''
+        for (afi, safi), (flags, stale) in self.items():
+            entries += afi.pack_afi() + safi.pack_safi() + bytes([flags]) + stale.to_bytes(3, 'big')
+        return [entries]
+
+    @classmethod
+    def unpack_capability(cls, instance: Capability, data, capability: CapabilityCode) -> Capability:
+        assert isinstance(instance, LongLivedGraceful)
+        # A repeated capability replaces what was received before, as Graceful Restart does
+        instance.clear()
+        view = memoryview(data)
+        # Bounded by the length of the capability, each pass takes ENTRY_SIZE octets
+        while view:
+            if len(view) < cls.ENTRY_SIZE:
+                raise Notify(
+                    2, 0, f'LLGR capability truncated: need {cls.ENTRY_SIZE} bytes per entry, got {len(view)}'
+                )
+            afi = AFI.unpack_afi(view[:2])
+            safi = SAFI.unpack_safi(view[2:3])
+            flags = view[3]
+            stale_time = int.from_bytes(view[4:7], 'big')
+            view = view[cls.ENTRY_SIZE :]
+            instance.set_entry(afi, safi, flags, stale_time)
+        return instance
+
+
+Capability.register()(LongLivedGraceful)
diff --git a/tests/unit/test_llgr_capability.py b/tests/unit/test_llgr_capability.py
new file mode 100644
index 0000000..d357f75
--- /dev/null
+++ b/tests/unit/test_llgr_capability.py
@@ -0,0 +1,107 @@
+#!/usr/bin/env python3
+# encoding: utf-8
+"""test_llgr_capability.py
+
+Long-Lived Graceful Restart capability (RFC 9494), code 71.
+
+The value is a list of entries of seven octets: AFI (2), SAFI (1), Flags (1) and a
+24-bit Long-lived Stale Time in seconds. A value which is not a whole number of
+entries is truncated, and that ends the session with a NOTIFICATION.
+
+License: 3-clause BSD
+"""
+
+import json
+
+import pytest
+
+from exabgp.bgp.message.notification import Notify
+from exabgp.bgp.message.open.capability.capabilities import Capabilities
+from exabgp.bgp.message.open.capability.capability import Capability
+from exabgp.bgp.message.open.capability.capability import CapabilityCode
+from exabgp.bgp.message.open.capability.llgr import LongLivedGraceful
+from exabgp.protocol.family import AFI, SAFI
+
+# AFI 1 SAFI 1 flags 0x80 stale time 0x012345, then AFI 2 SAFI 1 flags 0 stale time 0xFFFFFF
+IPV4_ENTRY = bytes([0x00, 0x01, 0x01, 0x80, 0x01, 0x23, 0x45])
+IPV6_ENTRY = bytes([0x00, 0x02, 0x01, 0x00, 0xFF, 0xFF, 0xFF])
+WELL_FORMED = IPV4_ENTRY + IPV6_ENTRY
+
+
+def decode(value: bytes) -> LongLivedGraceful:
+    instance = LongLivedGraceful()
+    result = LongLivedGraceful.unpack_capability(instance, value, Capability.CODE.LONG_LIVED_GRACEFUL_RESTART)
+    assert isinstance(result, LongLivedGraceful)
+    return result
+
+
+def test_capability_code_is_71() -> None:
+    """RFC 9494 assigns capability code 71."""
+    assert Capability.CODE.LONG_LIVED_GRACEFUL_RESTART == 71
+    assert LongLivedGraceful.ID == 71
+
+
+def test_capability_code_names_itself() -> None:
+    """The registry name is what logs and the JSON envelope print."""
+    assert CapabilityCode(71).name() == 'long-lived-graceful-restart'
+
+
+def test_decode_well_formed_entries() -> None:
+    """Each entry gives its family, its flags octet and its 24-bit stale time."""
+    llgr = decode(WELL_FORMED)
+
+    assert len(llgr) == 2
+    assert llgr[(AFI.ipv4, SAFI.unicast)] == (0x80, 0x012345)
+    assert llgr[(AFI.ipv6, SAFI.unicast)] == (0x00, 0xFFFFFF)
+
+
+def test_decode_through_open_parameters() -> None:
+    """A peer sending code 71 in its OPEN gets a LongLivedGraceful, not an unknown capability."""
+    tlv = bytes([0x47, len(WELL_FORMED)]) + WELL_FORMED
+    parameter = bytes([0x02, len(tlv)]) + tlv
+    capabilities = Capabilities.unpack(bytes([len(parameter)]) + parameter)
+
+    received = capabilities[Capability.CODE.LONG_LIVED_GRACEFUL_RESTART]
+    assert isinstance(received, LongLivedGraceful)
+    assert received[(AFI.ipv4, SAFI.unicast)] == (0x80, 0x012345)
+
+
+def test_encode_round_trips_the_wire_form() -> None:
+    """What was decoded is sent back as the same octets, in the same order."""
+    llgr = decode(WELL_FORMED)
+    assert llgr.extract_capability_bytes() == [WELL_FORMED]
+
+
+def test_empty_value_encodes_nothing() -> None:
+    """Nothing decoded means nothing to advertise."""
+    assert LongLivedGraceful().extract_capability_bytes() == []
+
+
+def test_str_and_json_show_each_entry() -> None:
+    """The display names the family, the flags and the stale time, and the JSON parses."""
+    llgr = decode(WELL_FORMED)
+
+    text = str(llgr)
+    assert 'ipv4 unicast' in text
+    assert 'stale-time 74565' in text
+
+    parsed = json.loads(llgr.json())
+    assert parsed['name'] == 'long-lived-graceful-restart'
+    assert parsed['ipv4/unicast'] == {'flags': 0x80, 'stale-time': 74565}
+    assert parsed['ipv6/unicast'] == {'flags': 0x00, 'stale-time': 0xFFFFFF}
+
+
+@pytest.mark.parametrize(
+    'value',
+    [
+        IPV4_ENTRY[:5],  # an entry cut short inside its stale time
+        WELL_FORMED[:-1],  # a well formed entry followed by a truncated one
+        bytes([0x00, 0x01]),  # less than an entry at all
+    ],
+)
+def test_truncated_value_is_refused(value: bytes) -> None:
+    """A value which is not a whole number of seven octet entries ends the session."""
+    with pytest.raises(Notify) as raised:
+        decode(value)
+    assert raised.value.code == 2
+    assert raised.value.subcode == 0

```


===== RUN a044 =====
```diff
diff --git a/src/exabgp/bgp/message/open/capability/__init__.py b/src/exabgp/bgp/message/open/capability/__init__.py
index 5c60813..49b1bc5 100644
--- a/src/exabgp/bgp/message/open/capability/__init__.py
+++ b/src/exabgp/bgp/message/open/capability/__init__.py
@@ -22,6 +22,7 @@ from exabgp.bgp.message.open.capability.pathslimit import PathsLimit
 from exabgp.bgp.message.open.capability.labels import MultipleLabels
 from exabgp.bgp.message.open.capability.asn4 import ASN4
 from exabgp.bgp.message.open.capability.graceful import Graceful
+from exabgp.bgp.message.open.capability.long_lived_graceful import LongLivedGracefulRestart
 from exabgp.bgp.message.open.capability.mp import MultiProtocol
 from exabgp.bgp.message.open.capability.ms import MultiSession
 from exabgp.bgp.message.open.capability.operational import Operational
@@ -44,6 +45,7 @@ __all__ = [
     'PathsLimit',
     'ASN4',
     'Graceful',
+    'LongLivedGracefulRestart',
     'MultiProtocol',
     'MultiSession',
     'Operational',
diff --git a/src/exabgp/bgp/message/open/capability/capability.py b/src/exabgp/bgp/message/open/capability/capability.py
index ef3617f..662bf4d 100644
--- a/src/exabgp/bgp/message/open/capability/capability.py
+++ b/src/exabgp/bgp/message/open/capability/capability.py
@@ -70,6 +70,7 @@ class CapabilityCode(IntValue):
     MULTISESSION: ClassVar[int] = 0x44  # [draft-ietf-idr-bgp-multisession]
     ADD_PATH: ClassVar[int] = 0x45  # [draft-ietf-idr-add-paths]
     ENHANCED_ROUTE_REFRESH: ClassVar[int] = 0x46  # [draft-ietf-idr-bgp-enhanced-route-refresh]
+    LONG_LIVED_GRACEFUL_RESTART: ClassVar[int] = 0x47  # [RFC9494]
     PATHS_LIMIT: ClassVar[int] = 0x4C  # [draft-abraitis-idr-addpath-paths-limit]
     LINK_LOCAL_NEXTHOP: ClassVar[int] = 0x4D  # [draft-ietf-idr-linklocal-capability]
     # 78-127    Unassigned
@@ -103,6 +104,7 @@ class CapabilityCode(IntValue):
         MULTISESSION: 'multi-session',
         ADD_PATH: 'add-path',
         ENHANCED_ROUTE_REFRESH: 'enhanced-route-refresh',
+        LONG_LIVED_GRACEFUL_RESTART: 'long-lived-graceful-restart',
         PATHS_LIMIT: 'paths-limit',
         MULTIPLE_LABELS: 'multiple-labels',
         LINK_LOCAL_NEXTHOP: 'link-local-nexthop',
@@ -150,6 +152,7 @@ class CapabilityCodes:
     MULTISESSION: ClassVar[CapabilityCode] =             CapabilityCode(CapabilityCode.MULTISESSION)
     ADD_PATH: ClassVar[CapabilityCode] =                 CapabilityCode(CapabilityCode.ADD_PATH)
     ENHANCED_ROUTE_REFRESH: ClassVar[CapabilityCode] =   CapabilityCode(CapabilityCode.ENHANCED_ROUTE_REFRESH)
+    LONG_LIVED_GRACEFUL_RESTART: ClassVar[CapabilityCode] = CapabilityCode(CapabilityCode.LONG_LIVED_GRACEFUL_RESTART)
     PATHS_LIMIT: ClassVar[CapabilityCode] =              CapabilityCode(CapabilityCode.PATHS_LIMIT)
     MULTIPLE_LABELS: ClassVar[CapabilityCode] =          CapabilityCode(CapabilityCode.MULTIPLE_LABELS)
     LINK_LOCAL_NEXTHOP: ClassVar[CapabilityCode] =       CapabilityCode(CapabilityCode.LINK_LOCAL_NEXTHOP)
diff --git a/src/exabgp/bgp/message/open/capability/long_lived_graceful.py b/src/exabgp/bgp/message/open/capability/long_lived_graceful.py
new file mode 100644
index 0000000..bda161e
--- /dev/null
+++ b/src/exabgp/bgp/message/open/capability/long_lived_graceful.py
@@ -0,0 +1,80 @@
+"""long_lived_graceful.py
+
+Long-Lived Graceful Restart capability, RFC 9494 section 3.1.
+"""
+
+# https://www.rfc-editor.org/rfc/rfc9494.html#section-3.1
+
+from __future__ import annotations
+
+from typing import ClassVar
+import json
+
+from exabgp.bgp.message.notification import Notify
+from exabgp.bgp.message.open.capability.capability import Capability
+from exabgp.bgp.message.open.capability.capability import CapabilityCode
+from exabgp.bgp.message.open.capability.capability import CapabilityList
+from exabgp.protocol.family import AFI, SAFI
+from exabgp.util.types import Buffer
+
+# (AFI, SAFI, Flags, Long-lived Stale Time in seconds)
+LongLivedEntry = tuple[AFI, SAFI, int, int]
+
+
+class LongLivedGracefulRestart(CapabilityList[LongLivedEntry]):
+    ID: ClassVar = Capability.CODE.LONG_LIVED_GRACEFUL_RESTART
+
+    # Each tuple is AFI(2) + SAFI(1) + Flags(1) + Long-lived Stale Time(3), and the value is zero or more of them
+    ENTRY_LEN: ClassVar[int] = 7
+    STALE_TIME_MAX: ClassVar[int] = 0xFFFFFF
+    # RFC 9494 3.1: the F bit is the most significant bit of the Flags octet, the others are reserved
+    FORWARDING_STATE: ClassVar[int] = 0x80
+
+    @classmethod
+    def _pack_entry(cls, entry: LongLivedEntry) -> bytes:
+        afi, safi, flags, stale_time = entry
+        assert 0 <= stale_time <= cls.STALE_TIME_MAX, 'RFC 9494 3.1: the Long-lived Stale Time is 24 bits'
+        return afi.pack_afi() + safi.pack_safi() + bytes([flags]) + stale_time.to_bytes(3, 'big')
+
+    def extract_capability_bytes(self) -> list[bytes]:
+        # Zero tuples is a valid, zero-length, value: it is returned as one empty value, not as none
+        return [b''.join(self._pack_entry(entry) for entry in self.items)]
+
+    def __str__(self) -> str:
+        families = ' '.join(
+            f'{afi}/{safi} flags {flags:#04x} stale {stale_time}' for afi, safi, flags, stale_time in self.items
+        )
+        return f'Long-Lived Graceful Restart {families}'.rstrip()
+
+    def json(self) -> str:
+        families = [
+            {
+                'afi': str(afi),
+                'safi': str(safi),
+                'forwarding': bool(flags & self.FORWARDING_STATE),
+                'flags': flags,
+                'stale-time': stale_time,
+            }
+            for afi, safi, flags, stale_time in self.items
+        ]
+        return json.dumps({'name': 'long-lived graceful restart', 'families': families})
+
+    @classmethod
+    def unpack_capability(cls, instance: Capability, data: Buffer, capability: CapabilityCode) -> Capability:  # pylint: disable=W0613
+        assert isinstance(instance, LongLivedGracefulRestart)
+        # A repeated capability replaces the first one, as Graceful does
+        instance.items.clear()
+        if len(data) % cls.ENTRY_LEN:
+            need = (len(data) // cls.ENTRY_LEN + 1) * cls.ENTRY_LEN
+            raise Notify.short(2, 0, 'Long-lived graceful restart capability', need, len(data))
+        for offset in range(0, len(data), cls.ENTRY_LEN):
+            entry = data[offset : offset + cls.ENTRY_LEN]
+            afi = AFI.unpack_afi(entry[0:2])
+            safi = SAFI.unpack_safi(entry[2:3])
+            flags = entry[3]
+            stale_time = int.from_bytes(entry[4:7], 'big')
+            instance.append((afi, safi, flags, stale_time))
+        return instance
+
+
+Capability.register()(LongLivedGracefulRestart)
diff --git a/tests/unit/test_long_lived_graceful_restart.py b/tests/unit/test_long_lived_graceful_restart.py
new file mode 100644
index 0000000..4b26fb3
--- /dev/null
+++ b/tests/unit/test_long_lived_graceful_restart.py
@@ -0,0 +1,47 @@
+"""Long-Lived Graceful Restart capability (RFC 9494 section 3.1), code 71."""
+
+from __future__ import annotations
+
+import json
+
+import pytest
+
+from exabgp.bgp.message.notification import Notify
+from exabgp.bgp.message.open.capability.capability import Capability
+from exabgp.bgp.message.open.capability.long_lived_graceful import LongLivedGracefulRestart
+from exabgp.protocol.family import AFI, SAFI
+
+CODE = Capability.CODE.LONG_LIVED_GRACEFUL_RESTART
+
+# ipv4/unicast with the F bit set and a stale time of 0x012345, then ipv6/unicast with no flags and the largest stale time
+WELL_FORMED = bytes([0x00, 0x01, 0x01, 0x80, 0x01, 0x23, 0x45, 0x00, 0x02, 0x01, 0x00, 0xFF, 0xFF, 0xFF])
+
+
+def test_long_lived_graceful_restart_decodes_encodes_and_renders() -> None:
+    decoded = Capability.unpack(CODE, {}, WELL_FORMED)
+    assert isinstance(decoded, LongLivedGracefulRestart)
+    assert decoded.items == [
+        (AFI.ipv4, SAFI.unicast, 0x80, 0x012345),
+        (AFI.ipv6, SAFI.unicast, 0x00, 0xFFFFFF),
+    ]
+    assert decoded.extract_capability_bytes() == [WELL_FORMED]
+    assert str(CODE) == 'long-lived-graceful-restart'
+    assert f'Long-Lived Graceful Restart {AFI.ipv4}/{SAFI.unicast} flags 0x80 stale 74565' in str(decoded)
+
+    rendered = json.loads(decoded.json())
+    assert rendered['name'] == 'long-lived graceful restart'
+    assert rendered['families'][0] == {
+        'afi': str(AFI.ipv4),
+        'safi': str(SAFI.unicast),
+        'forwarding': True,
+        'flags': 0x80,
+        'stale-time': 0x012345,
+    }
+    assert rendered['families'][1]['forwarding'] is False
+
+
+@pytest.mark.parametrize('truncated', [WELL_FORMED[:3], WELL_FORMED[:10], WELL_FORMED[:-1]])
+def test_long_lived_graceful_restart_refuses_truncated_value(truncated: bytes) -> None:
+    # A family tuple is 7 octets, so a value which is not a whole number of them is malformed
+    with pytest.raises(Notify):
+        Capability.unpack(CODE, {}, truncated)

```


===== RUN a050 =====
```diff
diff --git a/src/exabgp/bgp/message/open/capability/__init__.py b/src/exabgp/bgp/message/open/capability/__init__.py
index 5c60813..85c3b17 100644
--- a/src/exabgp/bgp/message/open/capability/__init__.py
+++ b/src/exabgp/bgp/message/open/capability/__init__.py
@@ -22,6 +22,7 @@ from exabgp.bgp.message.open.capability.pathslimit import PathsLimit
 from exabgp.bgp.message.open.capability.labels import MultipleLabels
 from exabgp.bgp.message.open.capability.asn4 import ASN4
 from exabgp.bgp.message.open.capability.graceful import Graceful
+from exabgp.bgp.message.open.capability.llgr import LongLivedGraceful
 from exabgp.bgp.message.open.capability.mp import MultiProtocol
 from exabgp.bgp.message.open.capability.ms import MultiSession
 from exabgp.bgp.message.open.capability.operational import Operational
@@ -44,6 +45,7 @@ __all__ = [
     'PathsLimit',
     'ASN4',
     'Graceful',
+    'LongLivedGraceful',
     'MultiProtocol',
     'MultiSession',
     'Operational',
diff --git a/src/exabgp/bgp/message/open/capability/capability.py b/src/exabgp/bgp/message/open/capability/capability.py
index ffec782..9b35ccc 100644
--- a/src/exabgp/bgp/message/open/capability/capability.py
+++ b/src/exabgp/bgp/message/open/capability/capability.py
@@ -70,6 +70,7 @@ class CapabilityCode(IntValue):
     MULTISESSION: ClassVar[int] = 0x44  # [draft-ietf-idr-bgp-multisession]
     ADD_PATH: ClassVar[int] = 0x45  # [draft-ietf-idr-add-paths]
     ENHANCED_ROUTE_REFRESH: ClassVar[int] = 0x46  # [draft-ietf-idr-bgp-enhanced-route-refresh]
+    LONG_LIVED_GRACEFUL_RESTART: ClassVar[int] = 0x47  # [RFC9494]
     PATHS_LIMIT: ClassVar[int] = 0x4C  # [draft-abraitis-idr-addpath-paths-limit]
     LINK_LOCAL_NEXTHOP: ClassVar[int] = 0x4D  # [draft-ietf-idr-linklocal-capability]
     # 78-127    Unassigned
@@ -103,6 +104,7 @@ class CapabilityCode(IntValue):
         MULTISESSION: 'multi-session',
         ADD_PATH: 'add-path',
         ENHANCED_ROUTE_REFRESH: 'enhanced-route-refresh',
+        LONG_LIVED_GRACEFUL_RESTART: 'long-lived-graceful-restart',
         PATHS_LIMIT: 'paths-limit',
         MULTIPLE_LABELS: 'multiple-labels',
         LINK_LOCAL_NEXTHOP: 'link-local-nexthop',
@@ -150,6 +152,7 @@ class CapabilityCodes:
     MULTISESSION: ClassVar[CapabilityCode] =             CapabilityCode(CapabilityCode.MULTISESSION)
     ADD_PATH: ClassVar[CapabilityCode] =                 CapabilityCode(CapabilityCode.ADD_PATH)
     ENHANCED_ROUTE_REFRESH: ClassVar[CapabilityCode] =   CapabilityCode(CapabilityCode.ENHANCED_ROUTE_REFRESH)
+    LONG_LIVED_GRACEFUL_RESTART: ClassVar[CapabilityCode] = CapabilityCode(CapabilityCode.LONG_LIVED_GRACEFUL_RESTART)
     PATHS_LIMIT: ClassVar[CapabilityCode] =              CapabilityCode(CapabilityCode.PATHS_LIMIT)
     MULTIPLE_LABELS: ClassVar[CapabilityCode] =          CapabilityCode(CapabilityCode.MULTIPLE_LABELS)
     LINK_LOCAL_NEXTHOP: ClassVar[CapabilityCode] =       CapabilityCode(CapabilityCode.LINK_LOCAL_NEXTHOP)
diff --git a/src/exabgp/bgp/message/open/capability/llgr.py b/src/exabgp/bgp/message/open/capability/llgr.py
new file mode 100644
index 0000000..306d349
--- /dev/null
+++ b/src/exabgp/bgp/message/open/capability/llgr.py
@@ -0,0 +1,96 @@
+"""llgr.py
+
+Long-Lived Graceful Restart capability (RFC 9494 section 3, code 71).
+
+Created for ExaBGP.
+License: 3-clause BSD. (See the COPYRIGHT file)
+"""
+
+# https://datatracker.ietf.org/doc/html/rfc9494#section-3
+
+from __future__ import annotations
+
+import json
+from typing import ClassVar, NamedTuple
+
+from exabgp.protocol.family import AFI, SAFI, FamilyTuple
+from exabgp.bgp.message.open.capability.capability import Capability, CapabilityDict
+from exabgp.bgp.message.open.capability.capability import CapabilityCode
+from exabgp.bgp.message.notification import Notify
+from exabgp.util.types import Buffer
+
+
+class LongLivedEntry(NamedTuple):
+    flags: int  # the Flags octet, kept whole so that reserved bits survive a round trip
+    stale_time: int  # Long-Lived Stale Time, in seconds
+
+
+class LongLivedGraceful(CapabilityDict[FamilyTuple, LongLivedEntry]):
+    """One tuple per family: AFI(2) SAFI(1) Flags(1) Long-Lived Stale Time(3)."""
+
+    ID: ClassVar = Capability.CODE.LONG_LIVED_GRACEFUL_RESTART
+
+    TUPLE_SIZE: ClassVar[int] = 7
+    MAX_STALE_TIME: ClassVar[int] = 0xFFFFFF
+    # RFC 9494 3.1: the most significant bit of Flags is the F bit, Forwarding State.
+    FORWARDING_STATE: ClassVar[int] = 0x80
+
+    def set_family(self, afi: AFI, safi: SAFI, flags: int, stale_time: int) -> None:
+        if not (0 <= flags <= 0xFF):
+            raise ValueError(f'long-lived graceful restart flags must be 0-255, got {flags}')
+        if not (0 <= stale_time <= self.MAX_STALE_TIME):
+            raise ValueError(f'long-lived stale time must be 0-{self.MAX_STALE_TIME}, got {stale_time}')
+        self[(afi, safi)] = LongLivedEntry(flags, stale_time)
+
+    def __str__(self) -> str:
+        families = ', '.join(
+            f'{afi}/{safi} forwarding {bool(entry.flags & self.FORWARDING_STATE)} '
+            f'flags {hex(entry.flags)} stale-time {entry.stale_time}'
+            for (afi, safi), entry in self.items()
+        )
+        return f'Long-Lived Graceful Restart({families})'
+
+    def json(self) -> str:
+        families = {
+            f'{afi}/{safi}': {
+                'forwarding': bool(entry.flags & self.FORWARDING_STATE),
+                'flags': entry.flags,
+                'stale-time': entry.stale_time,
+            }
+            for (afi, safi), entry in self.items()
+        }
+        return json.dumps({'name': 'long-lived graceful restart', 'address-family': families})
+
+    def extract_capability_bytes(self) -> list[bytes]:
+        if not self:
+            return []
+        tuples = [
+            afi.pack_afi() + safi.pack_safi() + bytes([entry.flags]) + entry.stale_time.to_bytes(3, 'big')
+            for (afi, safi), entry in self.items()
+        ]
+        return [b''.join(tuples)]
+
+    @classmethod
+    def unpack_capability(cls, instance: Capability, data: Buffer, capability: CapabilityCode) -> Capability:  # pylint: disable=W0613
+        assert isinstance(instance, LongLivedGraceful)
+        # RFC 9494 3.1 gives zero or more whole tuples, so anything else is a truncated capability
+        if len(data) % cls.TUPLE_SIZE:
+            raise Notify(
+                2,
+                0,
+                f'Long-Lived Graceful Restart capability truncated: {len(data)} octets is not a whole number '
+                f'of {cls.TUPLE_SIZE}-octet tuples',
+            )
+        if len(instance) > 0:
+            instance.clear()
+        view = memoryview(data)
+        for _ in range(len(data) // cls.TUPLE_SIZE):
+            entry = view[: cls.TUPLE_SIZE]
+            view = view[cls.TUPLE_SIZE :]
+            afi = AFI.unpack_afi(entry[:2])
+            safi = SAFI.unpack_safi(entry[2:3])
+            instance.set_family(afi, safi, entry[3], int.from_bytes(entry[4:7], 'big'))
+        return instance
+
+
+Capability.register()(LongLivedGraceful)
diff --git a/tests/unit/test_llgr_capability.py b/tests/unit/test_llgr_capability.py
new file mode 100644
index 0000000..cd151d5
--- /dev/null
+++ b/tests/unit/test_llgr_capability.py
@@ -0,0 +1,59 @@
+#!/usr/bin/env python3
+# encoding: utf-8
+"""test_llgr_capability.py
+
+Long-Lived Graceful Restart capability (RFC 9494 section 3, code 71): decoding a
+well formed value, and refusing a truncated one.
+
+License: 3-clause BSD
+"""
+
+from __future__ import annotations
+
+import json
+
+import pytest
+
+from exabgp.bgp.message.notification import Notify
+from exabgp.bgp.message.open.capability import Capability
+from exabgp.bgp.message.open.capability.capability import CapabilityCode
+from exabgp.bgp.message.open.capability.llgr import LongLivedGraceful
+from exabgp.protocol.family import AFI, SAFI
+
+
+# RFC 9494 3.1: AFI(2) SAFI(1) Flags(1) Long-Lived Stale Time(3), repeated per family.
+# ipv4 unicast: F bit set, 3600 seconds. ipv6 unicast: F bit clear, 0x010203 seconds.
+WELL_FORMED = bytes.fromhex('00010180000e10' '00020100010203')
+
+
+def test_llgr_decodes_well_formed_capability_and_encodes_it_back() -> None:
+    """Each tuple is one family, its F bit, and its 24-bit stale time, and it re-encodes byte for byte."""
+    assert Capability.CODE.LONG_LIVED_GRACEFUL_RESTART == 71
+
+    llgr = Capability.unpack(Capability.CODE.LONG_LIVED_GRACEFUL_RESTART, {}, WELL_FORMED)
+
+    assert isinstance(llgr, LongLivedGraceful)
+    assert llgr.code() == 71
+    assert llgr[(AFI.ipv4, SAFI.unicast)].stale_time == 3600
+    assert llgr[(AFI.ipv4, SAFI.unicast)].flags == 0x80
+    assert llgr[(AFI.ipv6, SAFI.unicast)].stale_time == 0x010203
+    assert llgr[(AFI.ipv6, SAFI.unicast)].flags == 0x00
+
+    assert llgr.extract_capability_bytes() == [WELL_FORMED]
+
+    assert str(CapabilityCode(71)) == 'long-lived-graceful-restart'
+    assert 'ipv4/unicast forwarding True' in str(llgr)
+    assert 'ipv6/unicast forwarding False' in str(llgr)
+    rendered = json.loads(llgr.json())
+    assert rendered['name'] == 'long-lived graceful restart'
+    assert rendered['address-family']['ipv4/unicast'] == {'forwarding': True, 'flags': 0x80, 'stale-time': 3600}
+    assert rendered['address-family']['ipv6/unicast']['stale-time'] == 0x010203
+
+
+def test_llgr_refuses_truncated_capability() -> None:
+    """A tuple cut short is a malformed capability, answered with a NOTIFICATION."""
+    truncated = WELL_FORMED[:-2]  # the last tuple has lost two of its seven octets
+
+    code = Capability.CODE.LONG_LIVED_GRACEFUL_RESTART
+    with pytest.raises(Notify):
+        LongLivedGraceful.unpack_capability(LongLivedGraceful(), truncated, code)

```


===== RUN a037 =====
```diff
diff --git a/src/exabgp/bgp/message/open/capability/__init__.py b/src/exabgp/bgp/message/open/capability/__init__.py
index 5c60813..6a6b91d 100644
--- a/src/exabgp/bgp/message/open/capability/__init__.py
+++ b/src/exabgp/bgp/message/open/capability/__init__.py
@@ -22,6 +22,7 @@ from exabgp.bgp.message.open.capability.pathslimit import PathsLimit
 from exabgp.bgp.message.open.capability.labels import MultipleLabels
 from exabgp.bgp.message.open.capability.asn4 import ASN4
 from exabgp.bgp.message.open.capability.graceful import Graceful
+from exabgp.bgp.message.open.capability.llgr import LongLivedGracefulRestart
 from exabgp.bgp.message.open.capability.mp import MultiProtocol
 from exabgp.bgp.message.open.capability.ms import MultiSession
 from exabgp.bgp.message.open.capability.operational import Operational
@@ -44,6 +45,7 @@ __all__ = [
     'PathsLimit',
     'ASN4',
     'Graceful',
+    'LongLivedGracefulRestart',
     'MultiProtocol',
     'MultiSession',
     'Operational',
diff --git a/src/exabgp/bgp/message/open/capability/capability.py b/src/exabgp/bgp/message/open/capability/capability.py
index 89e00a2..4188f9c 100644
--- a/src/exabgp/bgp/message/open/capability/capability.py
+++ b/src/exabgp/bgp/message/open/capability/capability.py
@@ -70,6 +70,7 @@ class CapabilityCode(IntValue):
     MULTISESSION: ClassVar[int] = 0x44  # [draft-ietf-idr-bgp-multisession]
     ADD_PATH: ClassVar[int] = 0x45  # [draft-ietf-idr-add-paths]
     ENHANCED_ROUTE_REFRESH: ClassVar[int] = 0x46  # [draft-ietf-idr-bgp-enhanced-route-refresh]
+    LONG_LIVED_GRACEFUL_RESTART: ClassVar[int] = 0x47  # [RFC9494]
     PATHS_LIMIT: ClassVar[int] = 0x4C  # [draft-abraitis-idr-addpath-paths-limit]
     LINK_LOCAL_NEXTHOP: ClassVar[int] = 0x4D  # [draft-ietf-idr-linklocal-capability]
     # 78-127    Unassigned
@@ -103,6 +104,7 @@ class CapabilityCode(IntValue):
         MULTISESSION: 'multi-session',
         ADD_PATH: 'add-path',
         ENHANCED_ROUTE_REFRESH: 'enhanced-route-refresh',
+        LONG_LIVED_GRACEFUL_RESTART: 'long-lived-graceful-restart',
         PATHS_LIMIT: 'paths-limit',
         MULTIPLE_LABELS: 'multiple-labels',
         LINK_LOCAL_NEXTHOP: 'link-local-nexthop',
@@ -150,6 +152,7 @@ class CapabilityCodes:
     MULTISESSION: ClassVar[CapabilityCode] =             CapabilityCode(CapabilityCode.MULTISESSION)
     ADD_PATH: ClassVar[CapabilityCode] =                 CapabilityCode(CapabilityCode.ADD_PATH)
     ENHANCED_ROUTE_REFRESH: ClassVar[CapabilityCode] =   CapabilityCode(CapabilityCode.ENHANCED_ROUTE_REFRESH)
+    LONG_LIVED_GRACEFUL_RESTART: ClassVar[CapabilityCode] = CapabilityCode(CapabilityCode.LONG_LIVED_GRACEFUL_RESTART)
     PATHS_LIMIT: ClassVar[CapabilityCode] =              CapabilityCode(CapabilityCode.PATHS_LIMIT)
     MULTIPLE_LABELS: ClassVar[CapabilityCode] =          CapabilityCode(CapabilityCode.MULTIPLE_LABELS)
     LINK_LOCAL_NEXTHOP: ClassVar[CapabilityCode] =       CapabilityCode(CapabilityCode.LINK_LOCAL_NEXTHOP)
diff --git a/src/exabgp/bgp/message/open/capability/llgr.py b/src/exabgp/bgp/message/open/capability/llgr.py
new file mode 100644
index 0000000..6f2b74f
--- /dev/null
+++ b/src/exabgp/bgp/message/open/capability/llgr.py
@@ -0,0 +1,102 @@
+"""llgr.py
+
+Long-Lived Graceful Restart capability (RFC 9494, capability code 71).
+
+The value is a list of fixed length entries, one per address family: AFI (2 octets),
+SAFI (1 octet), Flags (1 octet) and the Long-Lived Stale Time (3 octets, in seconds).
+The most significant bit of the flags is the F bit, Forwarding State, as in RFC 4724;
+the other bits are reserved. The flags octet is kept as received so that it is sent
+back unchanged.
+
+Created for ExaBGP.
+Copyright (c) 2009-2017 Exa Networks. All rights reserved.
+License: 3-clause BSD. (See the COPYRIGHT file)
+"""
+
+# https://www.rfc-editor.org/rfc/rfc9494
+
+from __future__ import annotations
+
+import json
+from typing import ClassVar
+
+from exabgp.protocol.family import AFI, SAFI, FamilyTuple
+from exabgp.bgp.message.open.capability.capability import Capability, CapabilityDict
+from exabgp.bgp.message.open.capability.capability import CapabilityCode
+from exabgp.bgp.message.notification import Notify
+from exabgp.util.types import Buffer
+
+
+class LongLivedGracefulRestart(CapabilityDict[FamilyTuple, tuple[int, int]]):
+    """Maps each family to (flags octet, long-lived stale time in seconds)."""
+
+    ID: ClassVar = Capability.CODE.LONG_LIVED_GRACEFUL_RESTART
+
+    ENTRY_LEN: ClassVar[int] = 7  # AFI(2) + SAFI(1) + flags(1) + stale time(3)
+    STALE_TIME_LEN: ClassVar[int] = 3
+    MAX_STALE_TIME: ClassVar[int] = 0xFFFFFF
+
+    # RFC 9494 3.1: the most significant bit of the flags is the F bit
+    FORWARDING_STATE: ClassVar[int] = 0x80
+
+    def add(self, afi: AFI, safi: SAFI, flags: int, stale_time: int) -> LongLivedGracefulRestart:
+        assert 0 <= flags <= 0xFF, 'the flags are one octet'
+        assert 0 <= stale_time <= self.MAX_STALE_TIME, 'the long-lived stale time is 24 bits'
+        self[(afi, safi)] = (flags, stale_time)
+        return self
+
+    def extract_capability_bytes(self) -> list[bytes]:
+        # An empty capability is not sent at all, rather than as a zero length value
+        if not self:
+            return []
+        entries = [
+            afi.pack_afi()
+            + safi.pack_safi()
+            + bytes([flags])
+            + stale_time.to_bytes(self.STALE_TIME_LEN, 'big')
+            for (afi, safi), (flags, stale_time) in self.items()
+        ]
+        return [b''.join(entries)]
+
+    def __str__(self) -> str:
+        families = ' '.join(
+            f'{afi}/{safi}=forwarding:{int(bool(flags & self.FORWARDING_STATE))},stale-time:{stale_time}'
+            for (afi, safi), (flags, stale_time) in self.items()
+        )
+        return f'Long-Lived Graceful Restart {families}'
+
+    def json(self) -> str:
+        families = [
+            {
+                'family': f'{afi}/{safi}',
+                'forwarding': bool(flags & self.FORWARDING_STATE),
+                'flags': flags,
+                'stale-time': stale_time,
+            }
+            for (afi, safi), (flags, stale_time) in self.items()
+        ]
+        return json.dumps({'name': 'long-lived-graceful-restart', 'families': families})
+
+    @classmethod
+    def unpack_capability(cls, instance: Capability, data: Buffer, capability: CapabilityCode) -> Capability:  # pylint: disable=W0613
+        assert isinstance(instance, LongLivedGracefulRestart)
+        # A repeated capability replaces the earlier one, as Graceful Restart does
+        instance.clear()
+        if len(data) % cls.ENTRY_LEN:
+            raise Notify(
+                2,
+                0,
+                f'Long-Lived Graceful Restart capability truncated: {len(data)} octets is not a multiple '
+                f'of {cls.ENTRY_LEN} (one entry per family)',
+            )
+        for offset in range(0, len(data), cls.ENTRY_LEN):
+            entry = data[offset : offset + cls.ENTRY_LEN]
+            afi = AFI.unpack_afi(entry[:2])
+            safi = SAFI.unpack_safi(entry[2:3])
+            flags = entry[3]
+            stale_time = int.from_bytes(entry[4:7], 'big')
+            instance.add(afi, safi, flags, stale_time)
+        return instance
+
+
+Capability.register()(LongLivedGracefulRestart)
diff --git a/tests/unit/test_llgr_capability.py b/tests/unit/test_llgr_capability.py
new file mode 100644
index 0000000..27c75ee
--- /dev/null
+++ b/tests/unit/test_llgr_capability.py
@@ -0,0 +1,101 @@
+#!/usr/bin/env python3
+# encoding: utf-8
+"""test_llgr_capability.py
+
+Long-Lived Graceful Restart capability (RFC 9494, capability code 71).
+
+Each entry is AFI(2) + SAFI(1) + flags(1) + long-lived stale time(3), seven octets, and
+the capability is zero or more entries. These tests hold the decoder for a well formed
+value, the decoder for a truncated one, and the encoder which sends the decoded value
+back unchanged.
+
+Created for ExaBGP testing framework
+License: 3-clause BSD
+"""
+
+import json
+
+import pytest
+
+from exabgp.bgp.message.notification import Notify
+from exabgp.bgp.message.open.capability.capabilities import Capabilities
+from exabgp.bgp.message.open.capability.capability import Capability
+from exabgp.bgp.message.open.capability.capability import CapabilityCode
+from exabgp.bgp.message.open.capability.llgr import LongLivedGracefulRestart
+from exabgp.protocol.family import AFI, SAFI
+
+# IPv4 unicast, forwarding state preserved, 3600 seconds
+IPV4_UNICAST = bytes([0x00, 0x01, 0x01, 0x80, 0x00, 0x0E, 0x10])
+# IPv6 unicast, forwarding state not preserved, 86400 seconds
+IPV6_UNICAST = bytes([0x00, 0x02, 0x01, 0x00, 0x01, 0x51, 0x80])
+
+
+def _decode(data: bytes) -> LongLivedGracefulRestart:
+    instance = Capability.unpack(CapabilityCode(0x47), Capabilities(), data)
+    assert isinstance(instance, LongLivedGracefulRestart)
+    return instance
+
+
+def test_capability_code_is_seventy_one() -> None:
+    """RFC 9494 assigns capability code 71, 0x47."""
+    assert Capability.CODE.LONG_LIVED_GRACEFUL_RESTART == 0x47
+    assert LongLivedGracefulRestart.ID == 71
+
+
+def test_capability_code_names_itself() -> None:
+    """The registry name is what logs and the JSON envelope print."""
+    assert CapabilityCode(0x47).name() == 'long-lived-graceful-restart'
+
+
+def test_well_formed_capability_decodes_every_entry() -> None:
+    """Two families, each with its own flags and stale time, are read back as sent."""
+    instance = _decode(IPV4_UNICAST + IPV6_UNICAST)
+
+    assert len(instance) == 2
+    assert instance[(AFI.ipv4, SAFI.unicast)] == (0x80, 3600)
+    assert instance[(AFI.ipv6, SAFI.unicast)] == (0x00, 86400)
+
+
+def test_well_formed_capability_renders_str_and_json() -> None:
+    """str() and json() show the family, the forwarding bit and the stale time."""
+    instance = _decode(IPV4_UNICAST + IPV6_UNICAST)
+
+    rendered = str(instance)
+    assert rendered.startswith('Long-Lived Graceful Restart')
+    assert 'ipv4/unicast=forwarding:1,stale-time:3600' in rendered
+    assert 'ipv6/unicast=forwarding:0,stale-time:86400' in rendered
+
+    parsed = json.loads(instance.json())
+    assert parsed['name'] == 'long-lived-graceful-restart'
+    assert parsed['families'][0] == {
+        'family': 'ipv4/unicast',
+        'forwarding': True,
+        'flags': 0x80,
+        'stale-time': 3600,
+    }
+    assert parsed['families'][1]['stale-time'] == 86400
+
+
+def test_well_formed_capability_encodes_back_unchanged() -> None:
+    """Encoding the decoded value gives the same octets, including a 24 bit stale time."""
+    max_time = bytes([0x00, 0x01, 0x01, 0x80, 0xFF, 0xFF, 0xFF])
+    instance = _decode(IPV4_UNICAST + max_time)
+
+    assert instance[(AFI.ipv4, SAFI.unicast)] == (0x80, 3600)
+    assert instance.extract_capability_bytes() == [IPV4_UNICAST + max_time]
+
+
+def test_empty_capability_is_not_sent() -> None:
+    """A capability with no families is left out of the OPEN rather than sent empty."""
+    assert LongLivedGracefulRestart().extract_capability_bytes() == []
+
+
+@pytest.mark.parametrize('length', [1, 3, 6, 8, 13])
+def test_truncated_capability_is_refused(length: int) -> None:
+    """A value which is not a whole number of seven octet entries ends the session."""
+    data = (IPV4_UNICAST + IPV6_UNICAST)[:length]
+
+    with pytest.raises(Notify) as raised:
+        _decode(data)
+    assert raised.value.code == 2
+    assert 'truncated' in raised.value.detail

```


===== RUN a048 =====
```diff
diff --git a/src/exabgp/bgp/message/open/capability/__init__.py b/src/exabgp/bgp/message/open/capability/__init__.py
index 5c60813..5f845c0 100644
--- a/src/exabgp/bgp/message/open/capability/__init__.py
+++ b/src/exabgp/bgp/message/open/capability/__init__.py
@@ -22,6 +22,7 @@ from exabgp.bgp.message.open.capability.pathslimit import PathsLimit
 from exabgp.bgp.message.open.capability.labels import MultipleLabels
 from exabgp.bgp.message.open.capability.asn4 import ASN4
 from exabgp.bgp.message.open.capability.graceful import Graceful
+from exabgp.bgp.message.open.capability.llgr import LLGR
 from exabgp.bgp.message.open.capability.mp import MultiProtocol
 from exabgp.bgp.message.open.capability.ms import MultiSession
 from exabgp.bgp.message.open.capability.operational import Operational
@@ -44,6 +45,7 @@ __all__ = [
     'PathsLimit',
     'ASN4',
     'Graceful',
+    'LLGR',
     'MultiProtocol',
     'MultiSession',
     'Operational',
diff --git a/src/exabgp/bgp/message/open/capability/capability.py b/src/exabgp/bgp/message/open/capability/capability.py
index ef3617f..662bf4d 100644
--- a/src/exabgp/bgp/message/open/capability/capability.py
+++ b/src/exabgp/bgp/message/open/capability/capability.py
@@ -70,6 +70,7 @@ class CapabilityCode(IntValue):
     MULTISESSION: ClassVar[int] = 0x44  # [draft-ietf-idr-bgp-multisession]
     ADD_PATH: ClassVar[int] = 0x45  # [draft-ietf-idr-add-paths]
     ENHANCED_ROUTE_REFRESH: ClassVar[int] = 0x46  # [draft-ietf-idr-bgp-enhanced-route-refresh]
+    LONG_LIVED_GRACEFUL_RESTART: ClassVar[int] = 0x47  # [RFC9494]
     PATHS_LIMIT: ClassVar[int] = 0x4C  # [draft-abraitis-idr-addpath-paths-limit]
     LINK_LOCAL_NEXTHOP: ClassVar[int] = 0x4D  # [draft-ietf-idr-linklocal-capability]
     # 78-127    Unassigned
@@ -103,6 +104,7 @@ class CapabilityCode(IntValue):
         MULTISESSION: 'multi-session',
         ADD_PATH: 'add-path',
         ENHANCED_ROUTE_REFRESH: 'enhanced-route-refresh',
+        LONG_LIVED_GRACEFUL_RESTART: 'long-lived-graceful-restart',
         PATHS_LIMIT: 'paths-limit',
         MULTIPLE_LABELS: 'multiple-labels',
         LINK_LOCAL_NEXTHOP: 'link-local-nexthop',
@@ -150,6 +152,7 @@ class CapabilityCodes:
     MULTISESSION: ClassVar[CapabilityCode] =             CapabilityCode(CapabilityCode.MULTISESSION)
     ADD_PATH: ClassVar[CapabilityCode] =                 CapabilityCode(CapabilityCode.ADD_PATH)
     ENHANCED_ROUTE_REFRESH: ClassVar[CapabilityCode] =   CapabilityCode(CapabilityCode.ENHANCED_ROUTE_REFRESH)
+    LONG_LIVED_GRACEFUL_RESTART: ClassVar[CapabilityCode] = CapabilityCode(CapabilityCode.LONG_LIVED_GRACEFUL_RESTART)
     PATHS_LIMIT: ClassVar[CapabilityCode] =              CapabilityCode(CapabilityCode.PATHS_LIMIT)
     MULTIPLE_LABELS: ClassVar[CapabilityCode] =          CapabilityCode(CapabilityCode.MULTIPLE_LABELS)
     LINK_LOCAL_NEXTHOP: ClassVar[CapabilityCode] =       CapabilityCode(CapabilityCode.LINK_LOCAL_NEXTHOP)
diff --git a/src/exabgp/bgp/message/open/capability/llgr.py b/src/exabgp/bgp/message/open/capability/llgr.py
new file mode 100644
index 0000000..0f97df6
--- /dev/null
+++ b/src/exabgp/bgp/message/open/capability/llgr.py
@@ -0,0 +1,110 @@
+"""llgr.py
+
+Long-Lived Graceful Restart Capability (RFC 9494).
+
+License: 3-clause BSD. (See the COPYRIGHT file)
+"""
+
+from __future__ import annotations
+
+from typing import ClassVar, Iterable
+
+from exabgp.protocol.family import AFI, SAFI, FamilyTuple
+from exabgp.bgp.message.open.capability.capability import Capability, CapabilityDict
+from exabgp.bgp.message.open.capability.capability import CapabilityCode
+from exabgp.bgp.message.notification import Notify
+from exabgp.logger import log, lazymsg
+
+# ============================================ LLGR (Long-Lived Graceful Restart)
+# RFC 9494 - https://datatracker.ietf.org/doc/html/rfc9494
+#
+# RFC 9494 3.1: "The capability value consists of zero or more tuples
+# <AFI, SAFI, Flags, LLST>": AFI (2), SAFI (1), Flags (1), Long-Lived Stale Time (3)
+
+
+class LLGR(CapabilityDict[FamilyTuple, tuple[int, int]]):
+    """Per family (flags, long-lived stale time in seconds), as the peer sent them.
+
+    Only parsed and displayed: no configuration advertises it and routes are not kept
+    stale for it. RFC 9494 4.5 has it ignored when the GR capability is absent, and with
+    nothing acting on it, ignoring it is what happens.
+    """
+
+    ID: ClassVar = Capability.CODE.LONG_LIVED_GRACEFUL_RESTART
+
+    # AFI (2) + SAFI (1) + Flags (1) + Long-Lived Stale Time (3)
+    ENTRY_SIZE: ClassVar[int] = 7
+    # the capability length is one octet, so this many tuples fit in one instance
+    MAX_FAMILIES: ClassVar[int] = 0xFF // ENTRY_SIZE
+    # the Long-Lived Stale Time is 24 bits
+    MAX_STALE_TIME: ClassVar[int] = 0xFFFFFF
+
+    # RFC 9494 3.1: the F bit, the most significant one, says the forwarding state was
+    # preserved; "The remaining bits are reserved and MUST be set to zero by the sender
+    # and ignored by the receiver."
+    FORWARDING_STATE: ClassVar[int] = 0x80
+
+    def set(self, afi: AFI, safi: SAFI, flags: int, stale_time: int) -> LLGR:
+        if not 0 <= stale_time <= LLGR.MAX_STALE_TIME:
+            raise ValueError(f'long-lived stale time must be 0-{LLGR.MAX_STALE_TIME}, got {stale_time}')
+        self[(afi, safi)] = (flags & LLGR.FORWARDING_STATE, stale_time)
+        return self
+
+    def flags(self, afi: AFI, safi: SAFI) -> int:
+        return self[(afi, safi)][0]
+
+    def stale_time(self, afi: AFI, safi: SAFI) -> int:
+        return self[(afi, safi)][1]
+
+    def families(self) -> Iterable[FamilyTuple]:
+        return self.keys()
+
+    def _entry(self, afi: AFI, safi: SAFI) -> bytes:
+        flags, stale_time = self[(afi, safi)]
+        return afi.pack_afi() + safi.pack_safi() + bytes([flags]) + stale_time.to_bytes(3, 'big')
+
+    def extract_capability_bytes(self) -> list[bytes]:
+        # one instance holds MAX_FAMILIES tuples, RFC 5492 4 lets a capability repeat
+        entries = [self._entry(afi, safi) for (afi, safi) in self.keys()]
+        if not entries:
+            return [b'']
+        chunks = range(0, len(entries), LLGR.MAX_FAMILIES)
+        return [b''.join(entries[start : start + LLGR.MAX_FAMILIES]) for start in chunks]
+
+    def __str__(self) -> str:
+        families = ' '.join(f'{afi}/{safi}={hex(flags)}/{stale}' for (afi, safi), (flags, stale) in self.items())
+        return f'Long-Lived Graceful Restart {families}'.rstrip()
+
+    def json(self) -> str:
+        families = ', '.join(
+            f'"{afi}/{safi}": {{ "forwarding": {"true" if flags & LLGR.FORWARDING_STATE else "false"}, '
+            f'"stale-time": {stale} }}'
+            for (afi, safi), (flags, stale) in self.items()
+        )
+        return f'{{ "name": "long-lived-graceful-restart", "address-families": {{ {families} }} }}'
+
+    @classmethod
+    def unpack_capability(cls, instance: Capability, data: bytes, capability: CapabilityCode) -> Capability:  # pylint: disable=W0613
+        assert isinstance(instance, LLGR)
+        if len(instance) > 0:
+            # RFC 9494 does not say what a repeated capability means: merge the tuples
+            log.debug(lazymsg('capability.llgr.duplicate action=merge'), 'parser')
+        view = memoryview(data)
+        if len(view) % cls.ENTRY_SIZE:
+            raise Notify(
+                2,
+                0,
+                f'Long-Lived Graceful Restart capability truncated: '
+                f'{len(view)} octets is not a whole number of {cls.ENTRY_SIZE} octet families',
+            )
+        # bounded: the capability length is a single octet, so at most MAX_FAMILIES tuples
+        for start in range(0, len(view), cls.ENTRY_SIZE):
+            entry = view[start : start + cls.ENTRY_SIZE]
+            afi = AFI.unpack_afi(entry[:2])
+            safi = SAFI.unpack_safi(entry[2:3])
+            stale_time = int.from_bytes(entry[4:7], 'big')
+            instance.set(afi, safi, entry[3], stale_time)
+        return instance
+
+
+Capability.register()(LLGR)
diff --git a/tests/unit/test_llgr_capability.py b/tests/unit/test_llgr_capability.py
new file mode 100644
index 0000000..d9f6c67
--- /dev/null
+++ b/tests/unit/test_llgr_capability.py
@@ -0,0 +1,82 @@
+"""test_llgr_capability.py
+
+RFC 9494 Long-Lived Graceful Restart capability (code 71).
+
+The capability value is zero or more <AFI, SAFI, Flags, Long-Lived Stale Time> tuples of
+seven octets each. ExaBGP only decodes and displays what the peer sends.
+
+License: 3-clause BSD
+"""
+
+from __future__ import annotations
+
+import pytest
+
+from exabgp.bgp.message.notification import Notify
+from exabgp.bgp.message.open.capability.capabilities import Capabilities
+from exabgp.bgp.message.open.capability.capability import Capability, CapabilityCode
+from exabgp.bgp.message.open.capability.llgr import LLGR
+from exabgp.protocol.family import AFI, SAFI
+
+# ipv4/unicast, F bit set, 3600 seconds; ipv4/flow, no flag, 86400 seconds
+IPV4_UNICAST = bytes.fromhex('0001' '01' '80' '000e10')
+IPV4_FLOW = bytes.fromhex('0001' '85' '00' '015180')
+
+
+def test_code_is_registered() -> None:
+    assert Capability.CODE.LONG_LIVED_GRACEFUL_RESTART == 71
+    assert CapabilityCode(71).name() == 'long-lived-graceful-restart'
+    assert Capability.klass(Capability.CODE.LONG_LIVED_GRACEFUL_RESTART) is LLGR
+
+
+def test_decode_well_formed() -> None:
+    value = IPV4_UNICAST + IPV4_FLOW
+    # an OPEN optional parameters field: one Capabilities parameter holding the capability
+    tlv = bytes([71, len(value)]) + value
+    parameter = bytes([2, len(tlv)]) + tlv
+    capabilities = Capabilities.unpack(bytes([len(parameter)]) + parameter)
+
+    llgr = capabilities[Capability.CODE.LONG_LIVED_GRACEFUL_RESTART]
+    assert isinstance(llgr, LLGR)
+    assert list(llgr.families()) == [(AFI.ipv4, SAFI.unicast), (AFI.ipv4, SAFI.flow_ip)]
+    assert llgr.flags(AFI.ipv4, SAFI.unicast) == LLGR.FORWARDING_STATE
+    assert llgr.stale_time(AFI.ipv4, SAFI.unicast) == 3600
+    assert llgr.flags(AFI.ipv4, SAFI.flow_ip) == 0
+    assert llgr.stale_time(AFI.ipv4, SAFI.flow_ip) == 86400
+
+    # encodes back to what was received
+    assert llgr.extract_capability_bytes() == [value]
+
+    assert str(llgr) == 'Long-Lived Graceful Restart ipv4/unicast=0x80/3600 ipv4/flow=0x0/86400'
+    assert llgr.json() == (
+        '{ "name": "long-lived-graceful-restart", "address-families": { '
+        '"ipv4/unicast": { "forwarding": true, "stale-time": 3600 }, '
+        '"ipv4/flow": { "forwarding": false, "stale-time": 86400 } } }'
+    )
+
+
+def test_reserved_flag_bits_are_ignored() -> None:
+    """RFC 9494 3.1: the bits other than F are "ignored by the receiver"."""
+    entry = bytes.fromhex('0001' '01' 'ff' '00003c')
+    llgr = Capability.unpack(Capability.CODE.LONG_LIVED_GRACEFUL_RESTART, Capabilities(), entry)
+    assert isinstance(llgr, LLGR)
+    assert llgr.flags(AFI.ipv4, SAFI.unicast) == LLGR.FORWARDING_STATE
+    assert llgr.stale_time(AFI.ipv4, SAFI.unicast) == 60
+
+
+def test_decode_empty() -> None:
+    """Zero tuples is a valid capability value."""
+    llgr = Capability.unpack(Capability.CODE.LONG_LIVED_GRACEFUL_RESTART, Capabilities(), b'')
+    assert isinstance(llgr, LLGR)
+    assert len(llgr) == 0
+    assert llgr.extract_capability_bytes() == [b'']
+
+
+@pytest.mark.parametrize('cut', [1, 4, 6])
+def test_decode_truncated(cut: int) -> None:
+    """A tuple shorter than seven octets ends the session with an OPEN Message Error."""
+    data = IPV4_UNICAST + IPV4_FLOW[:cut]
+    with pytest.raises(Notify) as raised:
+        Capability.unpack(Capability.CODE.LONG_LIVED_GRACEFUL_RESTART, Capabilities(), data)
+    assert raised.value.code == 2
+    assert raised.value.subcode == 0

```


===== RUN a045 =====
```diff
diff --git a/src/exabgp/bgp/message/open/capability/__init__.py b/src/exabgp/bgp/message/open/capability/__init__.py
index 5c60813..85c3b17 100644
--- a/src/exabgp/bgp/message/open/capability/__init__.py
+++ b/src/exabgp/bgp/message/open/capability/__init__.py
@@ -22,6 +22,7 @@ from exabgp.bgp.message.open.capability.pathslimit import PathsLimit
 from exabgp.bgp.message.open.capability.labels import MultipleLabels
 from exabgp.bgp.message.open.capability.asn4 import ASN4
 from exabgp.bgp.message.open.capability.graceful import Graceful
+from exabgp.bgp.message.open.capability.llgr import LongLivedGraceful
 from exabgp.bgp.message.open.capability.mp import MultiProtocol
 from exabgp.bgp.message.open.capability.ms import MultiSession
 from exabgp.bgp.message.open.capability.operational import Operational
@@ -44,6 +45,7 @@ __all__ = [
     'PathsLimit',
     'ASN4',
     'Graceful',
+    'LongLivedGraceful',
     'MultiProtocol',
     'MultiSession',
     'Operational',
diff --git a/src/exabgp/bgp/message/open/capability/capability.py b/src/exabgp/bgp/message/open/capability/capability.py
index ef3617f..662bf4d 100644
--- a/src/exabgp/bgp/message/open/capability/capability.py
+++ b/src/exabgp/bgp/message/open/capability/capability.py
@@ -70,6 +70,7 @@ class CapabilityCode(IntValue):
     MULTISESSION: ClassVar[int] = 0x44  # [draft-ietf-idr-bgp-multisession]
     ADD_PATH: ClassVar[int] = 0x45  # [draft-ietf-idr-add-paths]
     ENHANCED_ROUTE_REFRESH: ClassVar[int] = 0x46  # [draft-ietf-idr-bgp-enhanced-route-refresh]
+    LONG_LIVED_GRACEFUL_RESTART: ClassVar[int] = 0x47  # [RFC9494]
     PATHS_LIMIT: ClassVar[int] = 0x4C  # [draft-abraitis-idr-addpath-paths-limit]
     LINK_LOCAL_NEXTHOP: ClassVar[int] = 0x4D  # [draft-ietf-idr-linklocal-capability]
     # 78-127    Unassigned
@@ -103,6 +104,7 @@ class CapabilityCode(IntValue):
         MULTISESSION: 'multi-session',
         ADD_PATH: 'add-path',
         ENHANCED_ROUTE_REFRESH: 'enhanced-route-refresh',
+        LONG_LIVED_GRACEFUL_RESTART: 'long-lived-graceful-restart',
         PATHS_LIMIT: 'paths-limit',
         MULTIPLE_LABELS: 'multiple-labels',
         LINK_LOCAL_NEXTHOP: 'link-local-nexthop',
@@ -150,6 +152,7 @@ class CapabilityCodes:
     MULTISESSION: ClassVar[CapabilityCode] =             CapabilityCode(CapabilityCode.MULTISESSION)
     ADD_PATH: ClassVar[CapabilityCode] =                 CapabilityCode(CapabilityCode.ADD_PATH)
     ENHANCED_ROUTE_REFRESH: ClassVar[CapabilityCode] =   CapabilityCode(CapabilityCode.ENHANCED_ROUTE_REFRESH)
+    LONG_LIVED_GRACEFUL_RESTART: ClassVar[CapabilityCode] = CapabilityCode(CapabilityCode.LONG_LIVED_GRACEFUL_RESTART)
     PATHS_LIMIT: ClassVar[CapabilityCode] =              CapabilityCode(CapabilityCode.PATHS_LIMIT)
     MULTIPLE_LABELS: ClassVar[CapabilityCode] =          CapabilityCode(CapabilityCode.MULTIPLE_LABELS)
     LINK_LOCAL_NEXTHOP: ClassVar[CapabilityCode] =       CapabilityCode(CapabilityCode.LINK_LOCAL_NEXTHOP)
diff --git a/src/exabgp/bgp/message/open/capability/llgr.py b/src/exabgp/bgp/message/open/capability/llgr.py
new file mode 100644
index 0000000..348f277
--- /dev/null
+++ b/src/exabgp/bgp/message/open/capability/llgr.py
@@ -0,0 +1,102 @@
+"""llgr.py
+
+Long-Lived Graceful Restart capability (RFC 9494, capability code 71).
+
+The value is a list of seven octet tuples, one per address family:
+
+    AFI (2) | SAFI (1) | Flags (1) | Long-Lived Stale Time (3)
+
+Only the high order bit of the flags is defined, F, the Forwarding State. The
+other bits are reserved and ignored on receipt. The stale time is in seconds.
+
+Only decoding and display: ExaBGP does not advertise this capability, and the
+stale time does not change how routes are handled.
+
+Created for ExaBGP.
+License: 3-clause BSD. (See the COPYRIGHT file)
+"""
+
+from __future__ import annotations
+
+from typing import ClassVar, Iterable
+
+from exabgp.protocol.family import AFI, SAFI, FamilyTuple
+from exabgp.bgp.message.open.capability.capability import Capability, CapabilityDict
+from exabgp.bgp.message.open.capability.capability import CapabilityCode
+from exabgp.bgp.message.notification import Notify
+from exabgp.logger import log, lazymsg
+from exabgp.util.types import Buffer
+
+# ============================================================ LongLivedGraceful
+# RFC 9494 - https://www.rfc-editor.org/rfc/rfc9494
+
+# (flags, long-lived stale time) for one family
+LLGRValue = tuple[int, int]
+
+
+class LongLivedGraceful(CapabilityDict[FamilyTuple, LLGRValue]):
+    ID: ClassVar = Capability.CODE.LONG_LIVED_GRACEFUL_RESTART
+
+    ENTRY_SIZE: ClassVar[int] = 7
+    FORWARDING_STATE: ClassVar[int] = 0x80
+    # the stale time is a 24 bit field
+    MAX_TIME: ClassVar[int] = 0xFFFFFF
+
+    def set(self, protos: Iterable[tuple[AFI, SAFI, int, int]]) -> LongLivedGraceful:
+        for afi, safi, flags, stale_time in protos:
+            assert 0 <= stale_time <= LongLivedGraceful.MAX_TIME, f'stale time {stale_time} does not fit 24 bits'
+            # RFC 9494 3: the reserved flag bits are ignored on receipt
+            self[(afi, safi)] = (flags & LongLivedGraceful.FORWARDING_STATE, stale_time)
+        return self
+
+    def extract_capability_bytes(self) -> list[bytes]:
+        families = [
+            afi.pack_afi() + safi.pack_safi() + bytes([flags]) + stale_time.to_bytes(3, 'big')
+            for (afi, safi), (flags, stale_time) in self.items()
+        ]
+        return [b''.join(families)]
+
+    def __str__(self) -> str:
+        families = ' '.join(
+            f'{afi}/{safi}=flags {hex(flags)} time {stale_time}' for (afi, safi), (flags, stale_time) in self.items()
+        )
+        return f'Long-Lived Graceful Restart {families}'.rstrip()
+
+    def json(self) -> str:
+        families = ', '.join(
+            f'"{afi}/{safi}": {{ "forwarding": {"true" if flags & LongLivedGraceful.FORWARDING_STATE else "false"}, '
+            f'"time": {stale_time} }}'
+            for (afi, safi), (flags, stale_time) in self.items()
+        )
+        return f'{{ "name": "long-lived graceful restart", "address-family": {{ {families} }} }}'
+
+    def families(self) -> Iterable[FamilyTuple]:
+        return self.keys()
+
+    @classmethod
+    def unpack_capability(cls, instance: Capability, data: Buffer, capability: CapabilityCode) -> Capability:
+        assert isinstance(instance, LongLivedGraceful)
+        if len(instance) > 0:
+            log.debug(lazymsg('capability.long_lived_graceful_restart.duplicate action=replace'), 'parser')
+            instance.clear()
+        view = memoryview(data)
+        if len(view) % cls.ENTRY_SIZE:
+            raise Notify(
+                2,
+                0,
+                f'Long-Lived Graceful Restart capability truncated: '
+                f'need {cls.ENTRY_SIZE} bytes per family, got {len(view)} bytes',
+            )
+        families: list[tuple[AFI, SAFI, int, int]] = []
+        # bounded by the length, a multiple of ENTRY_SIZE checked above
+        for start in range(0, len(view), cls.ENTRY_SIZE):
+            entry = view[start : start + cls.ENTRY_SIZE]
+            afi = AFI.unpack_afi(entry[:2])
+            safi = SAFI.unpack_safi(entry[2:3])
+            flags = entry[3]
+            stale_time = int.from_bytes(entry[4:7], 'big')
+            families.append((afi, safi, flags, stale_time))
+        return instance.set(families)
+
+
+Capability.register()(LongLivedGraceful)
diff --git a/tests/unit/test_llgr_capability.py b/tests/unit/test_llgr_capability.py
new file mode 100644
index 0000000..4098175
--- /dev/null
+++ b/tests/unit/test_llgr_capability.py
@@ -0,0 +1,103 @@
+"""test_llgr_capability.py
+
+RFC 9494 Long-Lived Graceful Restart capability (code 71).
+
+The value is a list of seven octet tuples: AFI (2), SAFI (1), Flags (1) and a
+24 bit Long-Lived Stale Time. ExaBGP only decodes and displays it.
+
+Created for ExaBGP testing framework
+License: 3-clause BSD
+"""
+
+import json
+
+import pytest
+
+from exabgp.bgp.message.notification import Notify
+from exabgp.bgp.message.open.capability import Capabilities
+from exabgp.bgp.message.open.capability import Capability
+from exabgp.bgp.message.open.capability.capability import CapabilityCode
+from exabgp.bgp.message.open.capability.llgr import LongLivedGraceful
+from exabgp.protocol.family import AFI, SAFI
+
+# ipv4/unicast, F set, 3600 seconds; ipv6/unicast, F clear, 86400 seconds
+WELL_FORMED = bytes.fromhex('0001018000' + '0e10' + '0002010001' + '5180')
+
+
+def test_capability_code_is_registered() -> None:
+    assert Capability.CODE.LONG_LIVED_GRACEFUL_RESTART == 71
+    assert LongLivedGraceful.ID == 71
+    assert CapabilityCode(71).name() == 'long-lived-graceful-restart'
+    assert Capability.klass(Capability.CODE.LONG_LIVED_GRACEFUL_RESTART) is LongLivedGraceful
+
+
+def test_decode_well_formed() -> None:
+    decoded = Capability.unpack(Capability.CODE.LONG_LIVED_GRACEFUL_RESTART, Capabilities(), WELL_FORMED)
+
+    assert isinstance(decoded, LongLivedGraceful)
+    assert decoded[(AFI.ipv4, SAFI.unicast)] == (LongLivedGraceful.FORWARDING_STATE, 3600)
+    assert decoded[(AFI.ipv6, SAFI.unicast)] == (0, 86400)
+    assert list(decoded.families()) == [(AFI.ipv4, SAFI.unicast), (AFI.ipv6, SAFI.unicast)]
+
+    # encodes back to what was received
+    assert decoded.extract_capability_bytes() == [WELL_FORMED]
+
+    assert str(decoded) == (
+        'Long-Lived Graceful Restart ipv4/unicast=flags 0x80 time 3600 ipv6/unicast=flags 0x0 time 86400'
+    )
+    assert json.loads(decoded.json()) == {
+        'name': 'long-lived graceful restart',
+        'address-family': {
+            'ipv4/unicast': {'forwarding': True, 'time': 3600},
+            'ipv6/unicast': {'forwarding': False, 'time': 86400},
+        },
+    }
+
+
+def test_decode_through_open_capabilities() -> None:
+    """Framed as an optional parameter, the capability is no longer reported as unknown."""
+    capability = bytes([int(Capability.CODE.LONG_LIVED_GRACEFUL_RESTART), len(WELL_FORMED)]) + WELL_FORMED
+    parameter = bytes([2, len(capability)]) + capability
+    packed = bytes([len(parameter)]) + parameter
+    capabilities = Capabilities.unpack(packed)
+    assert isinstance(capabilities[Capability.CODE.LONG_LIVED_GRACEFUL_RESTART], LongLivedGraceful)
+
+
+def test_reserved_flags_are_ignored() -> None:
+    data = bytes.fromhex('000101ff000001')
+    decoded = Capability.unpack(Capability.CODE.LONG_LIVED_GRACEFUL_RESTART, Capabilities(), data)
+    assert isinstance(decoded, LongLivedGraceful)
+    assert decoded[(AFI.ipv4, SAFI.unicast)] == (LongLivedGraceful.FORWARDING_STATE, 1)
+
+
+def test_maximum_stale_time() -> None:
+    data = bytes.fromhex('000101' + '00' + 'ffffff')
+    decoded = Capability.unpack(Capability.CODE.LONG_LIVED_GRACEFUL_RESTART, Capabilities(), data)
+    assert isinstance(decoded, LongLivedGraceful)
+    assert decoded[(AFI.ipv4, SAFI.unicast)] == (0, LongLivedGraceful.MAX_TIME)
+    assert decoded.extract_capability_bytes() == [data]
+
+
+def test_empty_capability_decodes_to_no_family() -> None:
+    decoded = Capability.unpack(Capability.CODE.LONG_LIVED_GRACEFUL_RESTART, Capabilities(), b'')
+    assert isinstance(decoded, LongLivedGraceful)
+    assert len(decoded) == 0
+    json.loads(decoded.json())
+
+
+@pytest.mark.parametrize('cut', [1, 3, 6])
+def test_decode_truncated_raises_notify(cut: int) -> None:
+    """A tuple shorter than seven octets ends the session with an OPEN message error."""
+    with pytest.raises(Notify) as exc:
+        Capability.unpack(Capability.CODE.LONG_LIVED_GRACEFUL_RESTART, Capabilities(), WELL_FORMED[:-cut])
+    assert exc.value.code == 2
+    assert exc.value.subcode == 0
+
+
+def test_repeated_capability_replaces_the_first() -> None:
+    capabilities = Capabilities()
+    code = Capability.CODE.LONG_LIVED_GRACEFUL_RESTART
+    capabilities[code] = Capability.unpack(code, capabilities, WELL_FORMED)
+    second = Capability.unpack(code, capabilities, bytes.fromhex('00020100000001'))
+    assert isinstance(second, LongLivedGraceful)
+    assert list(second.families()) == [(AFI.ipv6, SAFI.unicast)]

```
