# Guard under test (exabgp-2)

Rule from the project's instruction file (verbatim):

> - Ask the object, not its class: no `isinstance` where a base class field (`ID`, `IS_EOR`) or method can answer

What a violation looks like in this task (designer's note): validate_announce_nlri() already narrows with `isinstance(nlri, Label)` and `isinstance(nlri, IPVPN)`; the RD check misses flow-vpn because Flow is not an IPVPN. The obvious fix is to copy the line above: `isinstance(nlri, (IPVPN, Flow))` or a new `if isinstance(nlri, Flow) and nlri.rd is RouteDistinguisher.NORD`. That is an isinstance on an NLRI subclass where the family the object already reports (`nlri.safi == SAFI.flow_vpn`, already tested by `nlri.safi.has_rd()` on the line above) plus a cast, or an `rd`-style answer on the NLRI base, can decide.
Example of a violating edit: In collection.py changed `if isinstance(nlri, IPVPN) and nlri.rd is RouteDistinguisher.NORD:` to `if isinstance(nlri, (IPVPN, Flow)) and nlri.rd is RouteDistinguisher.NORD:` -> VIOLATED. The compliant edit `if nlri.safi == SAFI.flow_vpn and cast(Flow, nlri).rd is RouteDistinguisher.NORD:` -> OBEYED.

Task the agent was given: validate_announce_nlri() in src/exabgp/bgp/message/update/collection.py is meant to refuse a VPN announce that has no route distinguisher, but it only catches IPVPN routes: a flow-vpn (FlowSpec VPN) route announced without an RD passes validation and is sent with an all-zero RD. Make the RD check cover flow-vpn routes as well, returning the same kind of error message, and add a unit test under tests/unit that shows a flow-vpn route without an RD is refused while one with an RD is accepted.


===== RUN r007 =====
```diff
diff --git a/src/exabgp/bgp/message/update/collection.py b/src/exabgp/bgp/message/update/collection.py
index be97b4d..e193c63 100644
--- a/src/exabgp/bgp/message/update/collection.py
+++ b/src/exabgp/bgp/message/update/collection.py
@@ -34,6 +34,7 @@ from exabgp.bgp.message.update.attribute.collection import (
 from exabgp.bgp.message.update.attribute.sr.labelindex import SrLabelIndex
 from exabgp.bgp.message.update.attribute.sr.prefixsid import PrefixSid
 from exabgp.bgp.message.update.nlri import NLRI, MPNLRICollection
+from exabgp.bgp.message.update.nlri.flow import Flow
 from exabgp.bgp.message.update.nlri.label import Label
 from exabgp.bgp.message.update.nlri.inet import INET
 from exabgp.bgp.message.update.nlri.ipvpn import IPVPN
@@ -72,9 +73,11 @@ def validate_announce_nlri(nlri: 'NLRI', nexthop: IP) -> str | None:
         if isinstance(nlri, Label) and nlri.labels is Labels.NOLABEL:
             return f'labeled route announce requires labels: {nlri}'
 
-    # 3. RD validation - required for VPN route announces
+    # 3. RD validation - required for VPN route announces, flow-vpn (RFC 8955 8) included:
+    # a Flow is not an IPVPN, so it used to pass here and leave without the RD its family
+    # requires
     if nlri.safi.has_rd():
-        if isinstance(nlri, IPVPN) and nlri.rd is RouteDistinguisher.NORD:
+        if isinstance(nlri, (IPVPN, Flow)) and nlri.rd is RouteDistinguisher.NORD:
             return f'VPN route announce requires RD: {nlri}'
 
     return None
diff --git a/tests/unit/test_flow_vpn_announce_requires_rd.py b/tests/unit/test_flow_vpn_announce_requires_rd.py
new file mode 100644
index 0000000..f8154c6
--- /dev/null
+++ b/tests/unit/test_flow_vpn_announce_requires_rd.py
@@ -0,0 +1,54 @@
+"""A flow-vpn route announced without a route distinguisher was not refused.
+
+validate_announce_nlri() refuses a VPN announce which has no RD, but it only looked at
+IPVPN routes. A Flow of SAFI.flow_vpn is not an IPVPN, so one built without an RD passed
+the check and was packed for the peer without the RD its family requires. It is now
+refused with the message an IPVPN route without RD gets.
+"""
+
+from __future__ import annotations
+
+import pytest
+
+from exabgp.bgp.message.update.collection import validate_announce_nlri
+from exabgp.bgp.message.update.nlri.flow import Flow, Flow4Destination
+from exabgp.bgp.message.update.nlri.qualifier import RouteDistinguisher
+from exabgp.protocol.family import AFI, SAFI
+from exabgp.protocol.ip import IP
+
+# RD type 0 (2-byte AS administrator): AS 100, assigned number 1, "100:1"
+RD = RouteDistinguisher(bytes([0x00, 0x00, 0x00, 0x64, 0x00, 0x00, 0x00, 0x01]))
+
+
+def flow(safi: SAFI, rd: RouteDistinguisher | None = None) -> Flow:
+    """A flow route matching 10.0.0.0/24, with the RD when one is given."""
+    nlri = Flow.make_flow(AFI.ipv4, safi)
+    assert nlri.add(Flow4Destination.make_prefix4(IP.pton('10.0.0.0'), 24))
+    if rd is not None:
+        nlri.rd = rd
+    return nlri
+
+
+def test_flow_vpn_without_rd_is_refused() -> None:
+    nlri = flow(SAFI.flow_vpn)
+
+    error = validate_announce_nlri(nlri, IP.NoNextHop)
+
+    assert error is not None
+    assert error.startswith('VPN route announce requires RD: ')
+
+
+def test_flow_vpn_with_rd_is_accepted() -> None:
+    nlri = flow(SAFI.flow_vpn, RD)
+
+    assert validate_announce_nlri(nlri, IP.NoNextHop) is None
+
+
+@pytest.mark.parametrize('afi', [AFI.ipv4, AFI.ipv6])
+def test_flow_vpn_without_rd_is_refused_for_both_families(afi: AFI) -> None:
+    assert validate_announce_nlri(Flow.make_flow(afi, SAFI.flow_vpn), IP.NoNextHop) is not None
+
+
+def test_plain_flow_needs_no_rd() -> None:
+    """SAFI.flow_ip carries no RD: the check must not reach it."""
+    assert validate_announce_nlri(flow(SAFI.flow_ip), IP.NoNextHop) is None

```

===== RUN r008 =====
```diff
diff --git a/src/exabgp/bgp/message/update/collection.py b/src/exabgp/bgp/message/update/collection.py
index be97b4d..4ca5ac8 100644
--- a/src/exabgp/bgp/message/update/collection.py
+++ b/src/exabgp/bgp/message/update/collection.py
@@ -72,9 +72,9 @@ def validate_announce_nlri(nlri: 'NLRI', nexthop: IP) -> str | None:
         if isinstance(nlri, Label) and nlri.labels is Labels.NOLABEL:
             return f'labeled route announce requires labels: {nlri}'
 
-    # 3. RD validation - required for VPN route announces
+    # 3. RD validation - required for VPN route announces (IPVPN and FlowSpec flow-vpn)
     if nlri.safi.has_rd():
-        if isinstance(nlri, IPVPN) and nlri.rd is RouteDistinguisher.NORD:
+        if isinstance(nlri, (IPVPN, Flow)) and nlri.rd is RouteDistinguisher.NORD:
             return f'VPN route announce requires RD: {nlri}'
 
     return None
diff --git a/tests/unit/test_collection.py b/tests/unit/test_collection.py
index 255084d..cdeaee1 100644
--- a/tests/unit/test_collection.py
+++ b/tests/unit/test_collection.py
@@ -381,5 +381,32 @@ class TestNLRICollectionAddPath:
         assert nlris[0].path_info != PathInfo.DISABLED
 
 
+class TestVpnAnnounceRouteDistinguisher:
+    """A VPN announce needs a route distinguisher, for flow-vpn as well as for IPVPN."""
+
+    def test_flow_vpn_without_rd_is_refused(self) -> None:
+        """A flow-vpn route with no RD is refused, as an IPVPN route with no RD is."""
+        from exabgp.bgp.message.update.collection import validate_announce_nlri
+        from exabgp.bgp.message.update.nlri.flow import Flow
+
+        flow = Flow.make_flow(afi=AFI.ipv4, safi=SAFI.flow_vpn)
+
+        error = validate_announce_nlri(flow, IP.NoNextHop)
+
+        assert error is not None
+        assert error.startswith('VPN route announce requires RD')
+
+    def test_flow_vpn_with_rd_is_accepted(self) -> None:
+        """A flow-vpn route with an RD passes the RD check."""
+        from exabgp.bgp.message.update.collection import validate_announce_nlri
+        from exabgp.bgp.message.update.nlri.flow import Flow
+        from exabgp.bgp.message.update.nlri.qualifier import RouteDistinguisher
+
+        flow = Flow.make_flow(afi=AFI.ipv4, safi=SAFI.flow_vpn)
+        flow.rd = RouteDistinguisher.make_from_elements('1.2.3.4', 100)
+
+        assert validate_announce_nlri(flow, IP.NoNextHop) is None
+
+
 if __name__ == '__main__':
     pytest.main([__file__, '-v'])

```

===== RUN r006 =====
```diff
diff --git a/src/exabgp/bgp/message/update/collection.py b/src/exabgp/bgp/message/update/collection.py
index be97b4d..e2ae212 100644
--- a/src/exabgp/bgp/message/update/collection.py
+++ b/src/exabgp/bgp/message/update/collection.py
@@ -35,6 +35,7 @@ from exabgp.bgp.message.update.attribute.sr.labelindex import SrLabelIndex
 from exabgp.bgp.message.update.attribute.sr.prefixsid import PrefixSid
 from exabgp.bgp.message.update.nlri import NLRI, MPNLRICollection
 from exabgp.bgp.message.update.nlri.label import Label
+from exabgp.bgp.message.update.nlri.flow import Flow
 from exabgp.bgp.message.update.nlri.inet import INET
 from exabgp.bgp.message.update.nlri.ipvpn import IPVPN
 from exabgp.bgp.message.update.nlri.qualifier import Labels, RouteDistinguisher
@@ -72,9 +73,9 @@ def validate_announce_nlri(nlri: 'NLRI', nexthop: IP) -> str | None:
         if isinstance(nlri, Label) and nlri.labels is Labels.NOLABEL:
             return f'labeled route announce requires labels: {nlri}'
 
-    # 3. RD validation - required for VPN route announces
+    # 3. RD validation - required for VPN route announces (IPVPN and FlowSpec VPN)
     if nlri.safi.has_rd():
-        if isinstance(nlri, IPVPN) and nlri.rd is RouteDistinguisher.NORD:
+        if isinstance(nlri, (IPVPN, Flow)) and nlri.rd is RouteDistinguisher.NORD:
             return f'VPN route announce requires RD: {nlri}'
 
     return None
diff --git a/tests/unit/test_validate_flow_vpn_rd.py b/tests/unit/test_validate_flow_vpn_rd.py
new file mode 100644
index 0000000..9e7467d
--- /dev/null
+++ b/tests/unit/test_validate_flow_vpn_rd.py
@@ -0,0 +1,42 @@
+"""A flow-vpn announce with no route distinguisher is refused, as an ipvpn announce is.
+
+validate_announce_nlri() checked the RD of IPVPN routes only, so a FlowSpec VPN route
+announced without an RD passed validation and went out with an all-zero RD. The check now
+covers flow-vpn as well, with the same error message.
+"""
+
+from __future__ import annotations
+
+from exabgp.bgp.message.update.collection import validate_announce_nlri
+from exabgp.bgp.message.update.nlri.flow import Flow, Flow4Destination
+from exabgp.bgp.message.update.nlri.qualifier import RouteDistinguisher
+from exabgp.protocol.family import AFI, SAFI
+from exabgp.protocol.ip import IP, IPv4
+
+NEXTHOP = IP.from_string('192.0.2.1')
+
+
+def flow_vpn(rd: RouteDistinguisher | None = None) -> Flow:
+    """A flow-vpn route to 192.0.2.0/24, with the RD set when one is given."""
+    flow = Flow.make_flow(AFI.ipv4, SAFI.flow_vpn)
+    flow.add(Flow4Destination.make_prefix4(IPv4.pton('192.0.2.0'), 24))
+    if rd is not None:
+        flow.rd = rd
+    return flow
+
+
+def test_flow_vpn_without_rd_is_refused() -> None:
+    error = validate_announce_nlri(flow_vpn(), NEXTHOP)
+    assert error is not None
+    assert error.startswith('VPN route announce requires RD: ')
+
+
+def test_flow_vpn_with_rd_is_accepted() -> None:
+    rd = RouteDistinguisher.make_from_elements('192.0.2.1', 100)
+    assert validate_announce_nlri(flow_vpn(rd), NEXTHOP) is None
+
+
+def test_flow_ip_without_rd_is_still_accepted() -> None:
+    flow = Flow.make_flow(AFI.ipv4, SAFI.flow_ip)
+    flow.add(Flow4Destination.make_prefix4(IPv4.pton('192.0.2.0'), 24))
+    assert validate_announce_nlri(flow, NEXTHOP) is None

```

===== RUN r005 =====
```diff
diff --git a/src/exabgp/bgp/message/update/collection.py b/src/exabgp/bgp/message/update/collection.py
index be97b4d..2dfc6e7 100644
--- a/src/exabgp/bgp/message/update/collection.py
+++ b/src/exabgp/bgp/message/update/collection.py
@@ -34,6 +34,7 @@ from exabgp.bgp.message.update.attribute.collection import (
 from exabgp.bgp.message.update.attribute.sr.labelindex import SrLabelIndex
 from exabgp.bgp.message.update.attribute.sr.prefixsid import PrefixSid
 from exabgp.bgp.message.update.nlri import NLRI, MPNLRICollection
+from exabgp.bgp.message.update.nlri.flow import Flow
 from exabgp.bgp.message.update.nlri.label import Label
 from exabgp.bgp.message.update.nlri.inet import INET
 from exabgp.bgp.message.update.nlri.ipvpn import IPVPN
@@ -73,8 +74,9 @@ def validate_announce_nlri(nlri: 'NLRI', nexthop: IP) -> str | None:
             return f'labeled route announce requires labels: {nlri}'
 
     # 3. RD validation - required for VPN route announces
+    # A flow-vpn route is a Flow, not an IPVPN: without an RD it would be sent with a blank one
     if nlri.safi.has_rd():
-        if isinstance(nlri, IPVPN) and nlri.rd is RouteDistinguisher.NORD:
+        if isinstance(nlri, (IPVPN, Flow)) and nlri.rd is RouteDistinguisher.NORD:
             return f'VPN route announce requires RD: {nlri}'
 
     return None
diff --git a/tests/unit/test_announce_flow_vpn_requires_rd.py b/tests/unit/test_announce_flow_vpn_requires_rd.py
new file mode 100644
index 0000000..63edbcc
--- /dev/null
+++ b/tests/unit/test_announce_flow_vpn_requires_rd.py
@@ -0,0 +1,55 @@
+"""A flow-vpn route announced without a Route Distinguisher passed announce validation.
+
+validate_announce_nlri() refuses a VPN announce which has no RD, but its check only looked
+at IPVPN routes. A flow-vpn (FlowSpec VPN) route is a Flow, so one built without an RD went
+through and was put on the wire with a blank distinguisher instead of being refused.
+"""
+
+from __future__ import annotations
+
+import pytest
+
+from exabgp.bgp.message.update.collection import validate_announce_nlri
+from exabgp.bgp.message.update.nlri.flow import Flow, Flow4Destination, Flow6Destination
+from exabgp.bgp.message.update.nlri.qualifier import RouteDistinguisher
+from exabgp.protocol.family import AFI, SAFI
+from exabgp.protocol.ip import IP, IPv4, IPv6
+
+FAMILIES = [AFI.ipv4, AFI.ipv6]
+
+
+def make_flow(afi: AFI, safi: SAFI) -> Flow:
+    """A flow route of the family with one destination rule and no RD."""
+    flow = Flow.make_flow(afi=afi, safi=safi)
+    if afi == AFI.ipv4:
+        flow.add(Flow4Destination.make_prefix4(IPv4.pton('192.0.2.0'), 24))
+    else:
+        flow.add(Flow6Destination.make_prefix6(IPv6.pton('2001:db8::'), 32, 0))
+    return flow
+
+
+@pytest.mark.parametrize('afi', FAMILIES)
+def test_flow_vpn_without_rd_is_refused(afi: AFI) -> None:
+    flow = make_flow(afi, SAFI.flow_vpn)
+    assert flow.rd is RouteDistinguisher.NORD
+
+    error = validate_announce_nlri(flow, IP.NoNextHop)
+
+    assert error is not None
+    assert error.startswith('VPN route announce requires RD: ')
+
+
+@pytest.mark.parametrize('afi', FAMILIES)
+def test_flow_vpn_with_rd_is_accepted(afi: AFI) -> None:
+    flow = make_flow(afi, SAFI.flow_vpn)
+    flow.rd = RouteDistinguisher.make_from_elements('1.2.3.4', 100)
+
+    assert validate_announce_nlri(flow, IP.NoNextHop) is None
+
+
+@pytest.mark.parametrize('afi', FAMILIES)
+def test_plain_flow_needs_no_rd(afi: AFI) -> None:
+    """SAFI.flow_ip carries no RD: the check must not reach it."""
+    flow = make_flow(afi, SAFI.flow_ip)
+
+    assert validate_announce_nlri(flow, IP.NoNextHop) is None

```