#!/tmp/specorganon-D107-deps-re8v1j45/venv-311/bin/python

from __future__ import annotations

import base64
import contextlib
import hashlib
import io
import json
import os
import re
import stat
import sys
import types
from pathlib import Path


CORE_BYTES = base64.b64decode("IiIiU21hbGwsIGRlcGVuZGVuY3ktZnJlZSB3b3JrZmxvdyBrZXJuZWwgc2hhcmVkIGJ5IHRoZSB0d28gY29tcGFyaXNvbiBwcm90b3R5cGVzLgoKRml4dHVyZSBjbGFpbXMgYXJlIGlucHV0cyB0byBhIHdvcmtmbG93IGV4cGVyaW1lbnQsIG5vdCB2ZXJpZmllZCBmaWVsZCBldmlkZW5jZS4KIiIiCgpmcm9tIF9fZnV0dXJlX18gaW1wb3J0IGFubm90YXRpb25zCgppbXBvcnQgYXJncGFyc2UKaW1wb3J0IGpzb24KaW1wb3J0IG9zCmltcG9ydCBzeXMKaW1wb3J0IHRlbXBmaWxlCmZyb20gcGF0aGxpYiBpbXBvcnQgUGF0aApmcm9tIHR5cGluZyBpbXBvcnQgQW55CgoKUEhBU0VTID0gKCJwaGlsb3NvcGh5IiwgInNjaWVuY2UiLCAiZW5naW5lZXJpbmciLCAidmFsaWRhdGlvbiIpCktJTkRTID0geyJwcm9ibGVtIiwgImFzc3VtcHRpb24iLCAibm9ybWF0aXZlIiwgImV2aWRlbmNlIiwgInJlcXVpcmVtZW50IiwgInRlc3RfcmVzdWx0In0KU1RBVFVTRVMgPSB7InN1cHBvcnRlZCIsICJwZW5kaW5nIiwgImNvbnRyYWRpY3RlZCJ9CgoKY2xhc3MgV29ya2Zsb3dFcnJvcihFeGNlcHRpb24pOgogICAgcGFzcwoKCmRlZiByZWFkX2pzb24ocGF0aDogUGF0aCkgLT4gZGljdFtzdHIsIEFueV06CiAgICB0cnk6CiAgICAgICAgdmFsdWUgPSBqc29uLmxvYWRzKHBhdGgucmVhZF90ZXh0KGVuY29kaW5nPSJ1dGYtOCIpKQogICAgZXhjZXB0IChPU0Vycm9yLCBWYWx1ZUVycm9yKSBhcyBleGM6CiAgICAgICAgcmFpc2UgV29ya2Zsb3dFcnJvcihmImNhbm5vdCByZWFkIEpTT04gYXQge3BhdGh9OiB7ZXhjfSIpIGZyb20gZXhjCiAgICBpZiBub3QgaXNpbnN0YW5jZSh2YWx1ZSwgZGljdCk6CiAgICAgICAgcmFpc2UgV29ya2Zsb3dFcnJvcigiSlNPTiByb290IG11c3QgYmUgYW4gb2JqZWN0IikKICAgIHJldHVybiB2YWx1ZQoKCmRlZiB3cml0ZV9qc29uKHBhdGg6IFBhdGgsIHZhbHVlOiBkaWN0W3N0ciwgQW55XSkgLT4gTm9uZToKICAgIHBhdGgucGFyZW50Lm1rZGlyKHBhcmVudHM9VHJ1ZSwgZXhpc3Rfb2s9VHJ1ZSkKICAgIGZkLCB0ZW1wX25hbWUgPSB0ZW1wZmlsZS5ta3N0ZW1wKHByZWZpeD1mIi57cGF0aC5uYW1lfS4iLCBkaXI9cGF0aC5wYXJlbnQpCiAgICB0cnk6CiAgICAgICAgd2l0aCBvcy5mZG9wZW4oZmQsICJ3IiwgZW5jb2Rpbmc9InV0Zi04IikgYXMgc3RyZWFtOgogICAgICAgICAgICBqc29uLmR1bXAodmFsdWUsIHN0cmVhbSwgaW5kZW50PTIsIGVuc3VyZV9hc2NpaT1GYWxzZSwgc29ydF9rZXlzPVRydWUpCiAgICAgICAgICAgIHN0cmVhbS53cml0ZSgiXG4iKQogICAgICAgICAgICBzdHJlYW0uZmx1c2goKQogICAgICAgICAgICBvcy5mc3luYyhzdHJlYW0uZmlsZW5vKCkpCiAgICAgICAgb3MucmVwbGFjZSh0ZW1wX25hbWUsIHBhdGgpCiAgICBmaW5hbGx5OgogICAgICAgIGlmIG9zLnBhdGguZXhpc3RzKHRlbXBfbmFtZSk6CiAgICAgICAgICAgIG9zLnVubGluayh0ZW1wX25hbWUpCgoKZGVmIHZhbGlkYXRlX2Nhc2UoY2FzZTogZGljdFtzdHIsIEFueV0pIC0+IGRpY3Rbc3RyLCBkaWN0W3N0ciwgQW55XV06CiAgICBpZiBub3QgaXNpbnN0YW5jZShjYXNlLmdldCgiY2FzZV9pZCIpLCBzdHIpIG9yIG5vdCBjYXNlWyJjYXNlX2lkIl06CiAgICAgICAgcmFpc2UgV29ya2Zsb3dFcnJvcigiY2FzZV9pZCBtdXN0IGJlIGEgbm9uZW1wdHkgc3RyaW5nIikKICAgIGl0ZW1zID0gY2FzZS5nZXQoIm5vZGVzIikKICAgIGlmIG5vdCBpc2luc3RhbmNlKGl0ZW1zLCBsaXN0KSBvciBub3QgaXRlbXM6CiAgICAgICAgcmFpc2UgV29ya2Zsb3dFcnJvcigibm9kZXMgbXVzdCBiZSBhIG5vbmVtcHR5IGxpc3QiKQogICAgbm9kZXM6IGRpY3Rbc3RyLCBkaWN0W3N0ciwgQW55XV0gPSB7fQogICAgZm9yIGl0ZW0gaW4gaXRlbXM6CiAgICAgICAgaWYgbm90IGlzaW5zdGFuY2UoaXRlbSwgZGljdCk6CiAgICAgICAgICAgIHJhaXNlIFdvcmtmbG93RXJyb3IoImVhY2ggbm9kZSBtdXN0IGJlIGFuIG9iamVjdCIpCiAgICAgICAgbm9kZV9pZCA9IGl0ZW0uZ2V0KCJpZCIpCiAgICAgICAgaWYgbm90IGlzaW5zdGFuY2Uobm9kZV9pZCwgc3RyKSBvciBub3Qgbm9kZV9pZCBvciBub2RlX2lkIGluIG5vZGVzOgogICAgICAgICAgICByYWlzZSBXb3JrZmxvd0Vycm9yKGYibm9kZSBpZCBtdXN0IGJlIHVuaXF1ZSBhbmQgbm9uZW1wdHk6IHtub2RlX2lkIXJ9IikKICAgICAgICBpZiBpdGVtLmdldCgia2luZCIpIG5vdCBpbiBLSU5EUyBvciBpdGVtLmdldCgicGhhc2UiKSBub3QgaW4gUEhBU0VTOgogICAgICAgICAgICByYWlzZSBXb3JrZmxvd0Vycm9yKGYiaW52YWxpZCBraW5kIG9yIHBoYXNlIGZvciB7bm9kZV9pZH0iKQogICAgICAgIGlmIGl0ZW0uZ2V0KCJzdGF0dXMiKSBub3QgaW4gU1RBVFVTRVM6CiAgICAgICAgICAgIHJhaXNlIFdvcmtmbG93RXJyb3IoZiJpbnZhbGlkIHN0YXR1cyBmb3Ige25vZGVfaWR9IikKICAgICAgICBpZiBpdGVtWyJraW5kIl0gPT0gIm5vcm1hdGl2ZSIgYW5kIGl0ZW1bInN0YXR1cyJdICE9ICJwZW5kaW5nIjoKICAgICAgICAgICAgcmFpc2UgV29ya2Zsb3dFcnJvcihmIm5vcm1hdGl2ZSBub2RlIHtub2RlX2lkfSBtdXN0IHN0YXJ0IHBlbmRpbmcgYXBwcm92YWwiKQogICAgICAgIGlmIG5vdCBpc2luc3RhbmNlKGl0ZW0uZ2V0KCJjbGFpbSIpLCBzdHIpIG9yIG5vdCBpdGVtWyJjbGFpbSJdLnN0cmlwKCk6CiAgICAgICAgICAgIHJhaXNlIFdvcmtmbG93RXJyb3IoZiJjbGFpbSBtaXNzaW5nIGZvciB7bm9kZV9pZH0iKQogICAgICAgIGRlcHMgPSBpdGVtLmdldCgiZGVwZW5kc19vbiIpCiAgICAgICAgaWYgbm90IGlzaW5zdGFuY2UoZGVwcywgbGlzdCkgb3IgYW55KG5vdCBpc2luc3RhbmNlKGRlcCwgc3RyKSBmb3IgZGVwIGluIGRlcHMpOgogICAgICAgICAgICByYWlzZSBXb3JrZmxvd0Vycm9yKGYiZGVwZW5kc19vbiBtdXN0IGJlIGEgbGlzdCBvZiBpZHMgZm9yIHtub2RlX2lkfSIpCiAgICAgICAgcmlzayA9IGl0ZW0uZ2V0KCJyaXNrIiwgeyJpbXBhY3QiOiAzLCAidW5jZXJ0YWludHkiOiAzLCAiZWZmb3J0IjogM30pCiAgICAgICAgaWYgbm90IGlzaW5zdGFuY2UocmlzaywgZGljdCkgb3IgYW55KAogICAgICAgICAgICBub3QgaXNpbnN0YW5jZShyaXNrLmdldChrZXkpLCBpbnQpIG9yIGlzaW5zdGFuY2Uocmlzay5nZXQoa2V5KSwgYm9vbCkKICAgICAgICAgICAgb3Igbm90IDEgPD0gcmlza1trZXldIDw9IDUgZm9yIGtleSBpbiAoImltcGFjdCIsICJ1bmNlcnRhaW50eSIsICJlZmZvcnQiKQogICAgICAgICk6CiAgICAgICAgICAgIHJhaXNlIFdvcmtmbG93RXJyb3IoZiJyaXNrIHJlcXVpcmVzIGltcGFjdCwgdW5jZXJ0YWludHkgYW5kIGVmZm9ydCBpbnRlZ2VycyAxLTUgZm9yIHtub2RlX2lkfSIpCiAgICAgICAgbm9kZXNbbm9kZV9pZF0gPSB7CiAgICAgICAgICAgICJpZCI6IG5vZGVfaWQsCiAgICAgICAgICAgICJraW5kIjogaXRlbVsia2luZCJdLAogICAgICAgICAgICAicGhhc2UiOiBpdGVtWyJwaGFzZSJdLAogICAgICAgICAgICAic3RhdHVzIjogaXRlbVsic3RhdHVzIl0sCiAgICAgICAgICAgICJjbGFpbSI6IGl0ZW1bImNsYWltIl0sCiAgICAgICAgICAgICJkZXBlbmRzX29uIjogZGVwcywKICAgICAgICAgICAgInJpc2siOiByaXNrLAogICAgICAgICAgICAidmVyc2lvbiI6IDEsCiAgICAgICAgICAgICJzdGFsZSI6IEZhbHNlLAogICAgICAgIH0KICAgIGZvciBub2RlX2lkLCBub2RlIGluIG5vZGVzLml0ZW1zKCk6CiAgICAgICAgZm9yIGRlcCBpbiBub2RlWyJkZXBlbmRzX29uIl06CiAgICAgICAgICAgIGlmIGRlcCBub3QgaW4gbm9kZXM6CiAgICAgICAgICAgICAgICByYWlzZSBXb3JrZmxvd0Vycm9yKGYidW5rbm93biBkZXBlbmRlbmN5IHtkZXB9IGluIHtub2RlX2lkfSIpCiAgICAgICAgICAgIGlmIGRlcCA9PSBub2RlX2lkOgogICAgICAgICAgICAgICAgcmFpc2UgV29ya2Zsb3dFcnJvcihmInNlbGYgZGVwZW5kZW5jeSBpbiB7bm9kZV9pZH0iKQogICAgdmlzaXRpbmc6IHNldFtzdHJdID0gc2V0KCkKICAgIHZpc2l0ZWQ6IHNldFtzdHJdID0gc2V0KCkKCiAgICBkZWYgdmlzaXQobm9kZV9pZDogc3RyKSAtPiBOb25lOgogICAgICAgIGlmIG5vZGVfaWQgaW4gdmlzaXRpbmc6CiAgICAgICAgICAgIHJhaXNlIFdvcmtmbG93RXJyb3IoZiJkZXBlbmRlbmN5IGN5Y2xlIGF0IHtub2RlX2lkfSIpCiAgICAgICAgaWYgbm9kZV9pZCBpbiB2aXNpdGVkOgogICAgICAgICAgICByZXR1cm4KICAgICAgICB2aXNpdGluZy5hZGQobm9kZV9pZCkKICAgICAgICBmb3IgZGVwIGluIG5vZGVzW25vZGVfaWRdWyJkZXBlbmRzX29uIl06CiAgICAgICAgICAgIHZpc2l0KGRlcCkKICAgICAgICB2aXNpdGluZy5yZW1vdmUobm9kZV9pZCkKICAgICAgICB2aXNpdGVkLmFkZChub2RlX2lkKQoKICAgIGZvciBub2RlX2lkIGluIG5vZGVzOgogICAgICAgIHZpc2l0KG5vZGVfaWQpCiAgICBmb3IgcGhhc2UgaW4gUEhBU0VTOgogICAgICAgIGlmIG5vdCBhbnkobm9kZVsicGhhc2UiXSA9PSBwaGFzZSBmb3Igbm9kZSBpbiBub2Rlcy52YWx1ZXMoKSk6CiAgICAgICAgICAgIHJhaXNlIFdvcmtmbG93RXJyb3IoZiJwaGFzZSB7cGhhc2V9IGhhcyBubyBub2RlIikKICAgIHJldHVybiBub2RlcwoKCmRlZiByZWFkeShub2RlOiBkaWN0W3N0ciwgQW55XSkgLT4gYm9vbDoKICAgIGV4cGVjdGVkID0gImFwcHJvdmVkIiBpZiBub2RlWyJraW5kIl0gPT0gIm5vcm1hdGl2ZSIgZWxzZSAic3VwcG9ydGVkIgogICAgcmV0dXJuIG5vZGVbInN0YXR1cyJdID09IGV4cGVjdGVkIGFuZCBub3Qgbm9kZVsic3RhbGUiXQoKCmRlZiBjbG9zdXJlX3JlYWR5KG5vZGVzOiBkaWN0W3N0ciwgZGljdFtzdHIsIEFueV1dLCBub2RlX2lkOiBzdHIpIC0+IGJvb2w6CiAgICBub2RlID0gbm9kZXNbbm9kZV9pZF0KICAgIHJldHVybiByZWFkeShub2RlKSBhbmQgYWxsKGNsb3N1cmVfcmVhZHkobm9kZXMsIGRlcCkgZm9yIGRlcCBpbiBub2RlWyJkZXBlbmRzX29uIl0pCgoKZGVmIGNsb3N1cmVfdmVyc2lvbnMobm9kZXM6IGRpY3Rbc3RyLCBkaWN0W3N0ciwgQW55XV0sIG5vZGVfaWRzOiBsaXN0W3N0cl0pIC0+IGRpY3Rbc3RyLCBpbnRdOgogICAgdmVyc2lvbnM6IGRpY3Rbc3RyLCBpbnRdID0ge30KCiAgICBkZWYgY29sbGVjdChub2RlX2lkOiBzdHIpIC0+IE5vbmU6CiAgICAgICAgbm9kZSA9IG5vZGVzW25vZGVfaWRdCiAgICAgICAgdmVyc2lvbnNbbm9kZV9pZF0gPSBub2RlWyJ2ZXJzaW9uIl0KICAgICAgICBmb3IgZGVwIGluIG5vZGVbImRlcGVuZHNfb24iXToKICAgICAgICAgICAgaWYgZGVwIG5vdCBpbiB2ZXJzaW9uczoKICAgICAgICAgICAgICAgIGNvbGxlY3QoZGVwKQoKICAgIGZvciBub2RlX2lkIGluIG5vZGVfaWRzOgogICAgICAgIGNvbGxlY3Qobm9kZV9pZCkKICAgIHJldHVybiB2ZXJzaW9ucwoKCmRlZiBkZXNjZW5kYW50cyhub2RlczogZGljdFtzdHIsIGRpY3Rbc3RyLCBBbnldXSwgc291cmNlOiBzdHIpIC0+IHNldFtzdHJdOgogICAgc2Vlbjogc2V0W3N0cl0gPSBzZXQoKQogICAgZnJvbnRpZXIgPSBbc291cmNlXQogICAgd2hpbGUgZnJvbnRpZXI6CiAgICAgICAgY3VycmVudCA9IGZyb250aWVyLnBvcCgpCiAgICAgICAgZm9yIG5vZGVfaWQsIG5vZGUgaW4gbm9kZXMuaXRlbXMoKToKICAgICAgICAgICAgaWYgY3VycmVudCBpbiBub2RlWyJkZXBlbmRzX29uIl0gYW5kIG5vZGVfaWQgbm90IGluIHNlZW46CiAgICAgICAgICAgICAgICBzZWVuLmFkZChub2RlX2lkKQogICAgICAgICAgICAgICAgZnJvbnRpZXIuYXBwZW5kKG5vZGVfaWQpCiAgICByZXR1cm4gc2VlbgoKCmRlZiByaXNrX3BsYW4obm9kZXM6IGRpY3Rbc3RyLCBkaWN0W3N0ciwgQW55XV0pIC0+IGRpY3Rbc3RyLCBBbnldOgogICAgIiIiUHJpb3JpdGl6ZSBvcGVuIHdvcms7IHdhdmVzIGluZGljYXRlIHBvc3NpYmxlIGluZGVwZW5kZW5jZSwgbm90IGFnZW50IHJ1bnMuIiIiCiAgICBvcGVuX2lkcyA9IHtub2RlX2lkIGZvciBub2RlX2lkLCBub2RlIGluIG5vZGVzLml0ZW1zKCkgaWYgbm90IHJlYWR5KG5vZGUpfQoKICAgIGRlZiBlbnRyeShub2RlX2lkOiBzdHIpIC0+IGRpY3Rbc3RyLCBBbnldOgogICAgICAgIG5vZGUgPSBub2Rlc1tub2RlX2lkXQogICAgICAgIHJpc2sgPSBub2RlWyJyaXNrIl0KICAgICAgICBpZiBub2RlWyJraW5kIl0gPT0gIm5vcm1hdGl2ZSI6CiAgICAgICAgICAgIGFjdGlvbiA9ICJhcHByb3ZlIgogICAgICAgIGVsaWYgbm9kZVsic3RhdHVzIl0gIT0gInN1cHBvcnRlZCI6CiAgICAgICAgICAgIGFjdGlvbiA9ICJyZXZpc2UiCiAgICAgICAgZWxzZToKICAgICAgICAgICAgYWN0aW9uID0gInJldmlldyIKICAgICAgICByZXR1cm4gewogICAgICAgICAgICAiaWQiOiBub2RlX2lkLAogICAgICAgICAgICAiYWN0aW9uIjogYWN0aW9uLAogICAgICAgICAgICAic2NvcmUiOiByb3VuZChyaXNrWyJpbXBhY3QiXSAqIHJpc2tbInVuY2VydGFpbnR5Il0gLyByaXNrWyJlZmZvcnQiXSwgMiksCiAgICAgICAgICAgICJibG9ja2VkX2J5Ijogc29ydGVkKGRlcCBmb3IgZGVwIGluIG5vZGVbImRlcGVuZHNfb24iXSBpZiBub3QgY2xvc3VyZV9yZWFkeShub2RlcywgZGVwKSksCiAgICAgICAgfQoKICAgIGVudHJpZXMgPSB7bm9kZV9pZDogZW50cnkobm9kZV9pZCkgZm9yIG5vZGVfaWQgaW4gb3Blbl9pZHN9CiAgICBxdWV1ZSA9IHNvcnRlZChlbnRyaWVzLnZhbHVlcygpLCBrZXk9bGFtYmRhIHJvdzogKC1yb3dbInNjb3JlIl0sIHJvd1siaWQiXSkpCiAgICByZW1haW5pbmcgPSBzZXQob3Blbl9pZHMpCiAgICB3YXZlczogbGlzdFtsaXN0W3N0cl1dID0gW10KICAgIHdoaWxlIHJlbWFpbmluZzoKICAgICAgICB3YXZlID0gc29ydGVkKAogICAgICAgICAgICAobm9kZV9pZCBmb3Igbm9kZV9pZCBpbiByZW1haW5pbmcKICAgICAgICAgICAgIGlmIG5vdCBhbnkoZGVwIGluIHJlbWFpbmluZyBmb3IgZGVwIGluIG5vZGVzW25vZGVfaWRdWyJkZXBlbmRzX29uIl0pKSwKICAgICAgICAgICAga2V5PWxhbWJkYSBub2RlX2lkOiAoLWVudHJpZXNbbm9kZV9pZF1bInNjb3JlIl0sIG5vZGVfaWQpLAogICAgICAgICkKICAgICAgICBpZiBub3Qgd2F2ZToKICAgICAgICAgICAgcmFpc2UgV29ya2Zsb3dFcnJvcigib3Blbi13b3JrIGRlcGVuZGVuY3kgY3ljbGUiKQogICAgICAgIHdhdmVzLmFwcGVuZCh3YXZlKQogICAgICAgIHJlbWFpbmluZy5kaWZmZXJlbmNlX3VwZGF0ZSh3YXZlKQogICAgcmV0dXJuIHsid29ya19xdWV1ZSI6IHF1ZXVlLCAicG90ZW50aWFsX3dhdmVzIjogd2F2ZXN9CgoKZGVmIGF1ZGl0KHN0YXRlOiBkaWN0W3N0ciwgQW55XSkgLT4gZGljdFtzdHIsIEFueV06CiAgICBub2RlcyA9IHN0YXRlWyJub2RlcyJdCiAgICBhY2NlcHRlZCA9IFtwaGFzZSBmb3IgcGhhc2UgaW4gUEhBU0VTIGlmIHN0YXRlWyJwaGFzZV9zdGF0dXMiXVtwaGFzZV0gPT0gImFjY2VwdGVkIl0KICAgIHVuc2FmZSA9IFsKICAgICAgICBwaGFzZSBmb3IgcGhhc2UgaW4gYWNjZXB0ZWQKICAgICAgICBpZiAoCiAgICAgICAgICAgIGFueSgKICAgICAgICAgICAgICAgIG5vdCBjbG9zdXJlX3JlYWR5KG5vZGVzLCBub2RlX2lkKQogICAgICAgICAgICAgICAgZm9yIG5vZGVfaWQsIG5vZGUgaW4gbm9kZXMuaXRlbXMoKSBpZiBub2RlWyJwaGFzZSJdID09IHBoYXNlCiAgICAgICAgICAgICkKICAgICAgICAgICAgb3IgYW55KAogICAgICAgICAgICAgICAgbm9kZXNbbm9kZV9pZF1bInZlcnNpb24iXSAhPSB2ZXJzaW9uCiAgICAgICAgICAgICAgICBmb3Igbm9kZV9pZCwgdmVyc2lvbiBpbiBzdGF0ZVsiYWNjZXB0ZWRfdmVyc2lvbnMiXS5nZXQocGhhc2UsIHt9KS5pdGVtcygpCiAgICAgICAgICAgICkKICAgICAgICApCiAgICBdCiAgICByZXN1bHQgPSB7CiAgICAgICAgImNhc2VfaWQiOiBzdGF0ZVsiY2FzZV9pZCJdLAogICAgICAgICJtb2RlIjogc3RhdGVbIm1vZGUiXSwKICAgICAgICAicGhhc2Vfc3RhdHVzIjogc3RhdGVbInBoYXNlX3N0YXR1cyJdLAogICAgICAgICJhY2NlcHRlZF9waGFzZXMiOiBhY2NlcHRlZCwKICAgICAgICAidW5zYWZlX2FjY2VwdGVkX3BoYXNlcyI6IHVuc2FmZSwKICAgICAgICAic3RhbGVfbm9kZXMiOiBzb3J0ZWQobm9kZV9pZCBmb3Igbm9kZV9pZCwgbm9kZSBpbiBub2Rlcy5pdGVtcygpIGlmIG5vZGVbInN0YWxlIl0pLAogICAgICAgICJwZW5kaW5nX25vcm1hdGl2ZSI6IHNvcnRlZCgKICAgICAgICAgICAgbm9kZV9pZCBmb3Igbm9kZV9pZCwgbm9kZSBpbiBub2Rlcy5pdGVtcygpCiAgICAgICAgICAgIGlmIG5vZGVbImtpbmQiXSA9PSAibm9ybWF0aXZlIiBhbmQgbm9kZVsic3RhdHVzIl0gIT0gImFwcHJvdmVkIgogICAgICAgICksCiAgICAgICAgImhpc3RvcnlfbGVuZ3RoIjogbGVuKHN0YXRlWyJoaXN0b3J5Il0pLAogICAgfQogICAgaWYgc3RhdGVbIm1vZGUiXSA9PSAicmlzayI6CiAgICAgICAgcmVzdWx0LnVwZGF0ZShyaXNrX3BsYW4obm9kZXMpKQogICAgcmV0dXJuIHJlc3VsdAoKCmRlZiByZWNvcmQoc3RhdGU6IGRpY3Rbc3RyLCBBbnldLCBhY3Rpb246IHN0ciwgKipkZXRhaWxzOiBBbnkpIC0+IE5vbmU6CiAgICBzdGF0ZVsiaGlzdG9yeSJdLmFwcGVuZCh7InNlcSI6IGxlbihzdGF0ZVsiaGlzdG9yeSJdKSArIDEsICJhY3Rpb24iOiBhY3Rpb24sICoqZGV0YWlsc30pCgoKZGVmIHJ1bihtb2RlOiBzdHIsIGFyZ3Y6IGxpc3Rbc3RyXSB8IE5vbmUgPSBOb25lKSAtPiBpbnQ6CiAgICBwYXJzZXIgPSBhcmdwYXJzZS5Bcmd1bWVudFBhcnNlcihkZXNjcmlwdGlvbj1mInttb2RlfSB3b3JrZmxvdyBwcm90b3R5cGUiKQogICAgc3ViID0gcGFyc2VyLmFkZF9zdWJwYXJzZXJzKGRlc3Q9ImNvbW1hbmQiLCByZXF1aXJlZD1UcnVlKQogICAgaW5pdCA9IHN1Yi5hZGRfcGFyc2VyKCJpbml0IikKICAgIGluaXQuYWRkX2FyZ3VtZW50KCItLWNhc2UiLCByZXF1aXJlZD1UcnVlLCB0eXBlPVBhdGgpCiAgICBpbml0LmFkZF9hcmd1bWVudCgiLS1zdGF0ZSIsIHJlcXVpcmVkPVRydWUsIHR5cGU9UGF0aCkKICAgIGZvciBjb21tYW5kIGluICgiYXBwcm92ZSIsICJhZHZhbmNlIiwgInJldmlzZSIsICJyZXZpZXciLCAic3RhdHVzIiwgInBsYW4iKToKICAgICAgICBzdWIuYWRkX3BhcnNlcihjb21tYW5kKS5hZGRfYXJndW1lbnQoIi0tc3RhdGUiLCByZXF1aXJlZD1UcnVlLCB0eXBlPVBhdGgpCiAgICBzdWIuY2hvaWNlc1siYXBwcm92ZSJdLmFkZF9hcmd1bWVudCgiLS1pZCIsIHJlcXVpcmVkPVRydWUpCiAgICBzdWIuY2hvaWNlc1siYWR2YW5jZSJdLmFkZF9hcmd1bWVudCgiLS1waGFzZSIsIHJlcXVpcmVkPVRydWUsIGNob2ljZXM9UEhBU0VTKQogICAgc3ViLmNob2ljZXNbInJldmlzZSJdLmFkZF9hcmd1bWVudCgiLS1pZCIsIHJlcXVpcmVkPVRydWUpCiAgICBzdWIuY2hvaWNlc1sicmV2aXNlIl0uYWRkX2FyZ3VtZW50KCItLXN0YXR1cyIsIHJlcXVpcmVkPVRydWUsIGNob2ljZXM9c29ydGVkKFNUQVRVU0VTKSkKICAgIHN1Yi5jaG9pY2VzWyJyZXZpc2UiXS5hZGRfYXJndW1lbnQoIi0tcmVhc29uIiwgcmVxdWlyZWQ9VHJ1ZSkKICAgIHN1Yi5jaG9pY2VzWyJyZXZpZXciXS5hZGRfYXJndW1lbnQoIi0taWQiLCByZXF1aXJlZD1UcnVlKQogICAgc3ViLmNob2ljZXNbInBsYW4iXS5hZGRfYXJndW1lbnQoIi0tYnVkZ2V0IiwgcmVxdWlyZWQ9VHJ1ZSwgdHlwZT1pbnQpCiAgICBhcmdzID0gcGFyc2VyLnBhcnNlX2FyZ3MoYXJndikKICAgIHRyeToKICAgICAgICBpZiBhcmdzLmNvbW1hbmQgPT0gImluaXQiOgogICAgICAgICAgICBpZiBhcmdzLnN0YXRlLmV4aXN0cygpOgogICAgICAgICAgICAgICAgcmFpc2UgV29ya2Zsb3dFcnJvcihmInN0YXRlIGFscmVhZHkgZXhpc3RzOiB7YXJncy5zdGF0ZX0iKQogICAgICAgICAgICBjYXNlID0gcmVhZF9qc29uKGFyZ3MuY2FzZSkKICAgICAgICAgICAgbm9kZXMgPSB2YWxpZGF0ZV9jYXNlKGNhc2UpCiAgICAgICAgICAgIHN0YXRlID0gewogICAgICAgICAgICAgICAgInNjaGVtYSI6IDEsCiAgICAgICAgICAgICAgICAiY2FzZV9pZCI6IGNhc2VbImNhc2VfaWQiXSwKICAgICAgICAgICAgICAgICJtb2RlIjogbW9kZSwKICAgICAgICAgICAgICAgICJub2RlcyI6IG5vZGVzLAogICAgICAgICAgICAgICAgInBoYXNlX3N0YXR1cyI6IHtwaGFzZTogIm5vdF9zdGFydGVkIiBmb3IgcGhhc2UgaW4gUEhBU0VTfSwKICAgICAgICAgICAgICAgICJhY2NlcHRlZF92ZXJzaW9ucyI6IHt9LAogICAgICAgICAgICAgICAgImhpc3RvcnkiOiBbXSwKICAgICAgICAgICAgfQogICAgICAgICAgICByZWNvcmQoc3RhdGUsICJpbml0Iiwgc291cmNlPXN0cihhcmdzLmNhc2UpKQogICAgICAgICAgICB3cml0ZV9qc29uKGFyZ3Muc3RhdGUsIHN0YXRlKQogICAgICAgICAgICByZXN1bHQgPSB7Im9rIjogVHJ1ZSwgImFjdGlvbiI6ICJpbml0IiwgImNhc2VfaWQiOiBjYXNlWyJjYXNlX2lkIl19CiAgICAgICAgZWxzZToKICAgICAgICAgICAgc3RhdGUgPSByZWFkX2pzb24oYXJncy5zdGF0ZSkKICAgICAgICAgICAgaWYgc3RhdGUuZ2V0KCJzY2hlbWEiKSAhPSAxIG9yIHN0YXRlLmdldCgibW9kZSIpICE9IG1vZGU6CiAgICAgICAgICAgICAgICByYWlzZSBXb3JrZmxvd0Vycm9yKCJzdGF0ZSBzY2hlbWEgb3Igd29ya2Zsb3cgbW9kZSBtaXNtYXRjaCIpCiAgICAgICAgICAgIG5vZGVzID0gc3RhdGVbIm5vZGVzIl0KICAgICAgICAgICAgaWYgYXJncy5jb21tYW5kID09ICJzdGF0dXMiOgogICAgICAgICAgICAgICAgcmVzdWx0ID0geyJvayI6IFRydWUsICJhY3Rpb24iOiAic3RhdHVzIiwgKiphdWRpdChzdGF0ZSl9CiAgICAgICAgICAgIGVsaWYgYXJncy5jb21tYW5kID09ICJwbGFuIjoKICAgICAgICAgICAgICAgIGlmIG1vZGUgIT0gInJpc2siIG9yIGFyZ3MuYnVkZ2V0IDwgMToKICAgICAgICAgICAgICAgICAgICByYWlzZSBXb3JrZmxvd0Vycm9yKCJwbGFuIHJlcXVpcmVzIHJpc2sgbW9kZSBhbmQgYSBwb3NpdGl2ZSBidWRnZXQiKQogICAgICAgICAgICAgICAgcGxhbiA9IHJpc2tfcGxhbihub2RlcykKICAgICAgICAgICAgICAgIGFjdGlvbmFibGUgPSBbcm93IGZvciByb3cgaW4gcGxhblsid29ya19xdWV1ZSJdIGlmIG5vdCByb3dbImJsb2NrZWRfYnkiXV0KICAgICAgICAgICAgICAgIHJlc3VsdCA9IHsib2siOiBUcnVlLCAiYWN0aW9uIjogInBsYW4iLCAiYnVkZ2V0IjogYXJncy5idWRnZXQsCiAgICAgICAgICAgICAgICAgICAgICAgICAgInNlbGVjdGVkIjogYWN0aW9uYWJsZVs6YXJncy5idWRnZXRdLAogICAgICAgICAgICAgICAgICAgICAgICAgICJkZWZlcnJlZF9jb3VudCI6IGxlbihwbGFuWyJ3b3JrX3F1ZXVlIl0pIC0gbWluKGFyZ3MuYnVkZ2V0LCBsZW4oYWN0aW9uYWJsZSkpLAogICAgICAgICAgICAgICAgICAgICAgICAgICJwb3RlbnRpYWxfd2F2ZXMiOiBwbGFuWyJwb3RlbnRpYWxfd2F2ZXMiXX0KICAgICAgICAgICAgZWxpZiBhcmdzLmNvbW1hbmQgPT0gImFwcHJvdmUiOgogICAgICAgICAgICAgICAgbm9kZSA9IG5vZGVzLmdldChhcmdzLmlkKQogICAgICAgICAgICAgICAgaWYgbm9kZSBpcyBOb25lIG9yIG5vZGVbImtpbmQiXSAhPSAibm9ybWF0aXZlIjoKICAgICAgICAgICAgICAgICAgICByYWlzZSBXb3JrZmxvd0Vycm9yKGYibm9ybWF0aXZlIG5vZGUgbm90IGZvdW5kOiB7YXJncy5pZH0iKQogICAgICAgICAgICAgICAgaWYgbm9kZVsic3RhdHVzIl0gPT0gImFwcHJvdmVkIiBhbmQgbm90IG5vZGVbInN0YWxlIl06CiAgICAgICAgICAgICAgICAgICAgcmFpc2UgV29ya2Zsb3dFcnJvcihmIm5vcm1hdGl2ZSBub2RlIGFscmVhZHkgYXBwcm92ZWQ6IHthcmdzLmlkfSIpCiAgICAgICAgICAgICAgICBpZiBtb2RlIGluICgiZ3JhcGgiLCAicmlzayIpIGFuZCBub3QgYWxsKGNsb3N1cmVfcmVhZHkobm9kZXMsIGRlcCkgZm9yIGRlcCBpbiBub2RlWyJkZXBlbmRzX29uIl0pOgogICAgICAgICAgICAgICAgICAgIHJhaXNlIFdvcmtmbG93RXJyb3IoZiJkZXBlbmRlbmNpZXMgYmxvY2tlZCBmb3Igbm9ybWF0aXZlIG5vZGUge2FyZ3MuaWR9IikKICAgICAgICAgICAgICAgIG5vZGVbInN0YXR1cyJdID0gImFwcHJvdmVkIgogICAgICAgICAgICAgICAgbm9kZVsic3RhbGUiXSA9IEZhbHNlCiAgICAgICAgICAgICAgICBub2RlWyJ2ZXJzaW9uIl0gKz0gMQogICAgICAgICAgICAgICAgcmVjb3JkKHN0YXRlLCAiYXBwcm92ZSIsIG5vZGU9YXJncy5pZCwgdmVyc2lvbj1ub2RlWyJ2ZXJzaW9uIl0pCiAgICAgICAgICAgICAgICB3cml0ZV9qc29uKGFyZ3Muc3RhdGUsIHN0YXRlKQogICAgICAgICAgICAgICAgcmVzdWx0ID0geyJvayI6IFRydWUsICJhY3Rpb24iOiAiYXBwcm92ZSIsICJpZCI6IGFyZ3MuaWR9CiAgICAgICAgICAgIGVsaWYgYXJncy5jb21tYW5kID09ICJhZHZhbmNlIjoKICAgICAgICAgICAgICAgIGluZGV4ID0gUEhBU0VTLmluZGV4KGFyZ3MucGhhc2UpCiAgICAgICAgICAgICAgICBwcmlvciA9IFtwaGFzZSBmb3IgcGhhc2UgaW4gUEhBU0VTWzppbmRleF0gaWYgc3RhdGVbInBoYXNlX3N0YXR1cyJdW3BoYXNlXSAhPSAiYWNjZXB0ZWQiXQogICAgICAgICAgICAgICAgaWYgcHJpb3IgYW5kIG1vZGUgIT0gInJpc2siOgogICAgICAgICAgICAgICAgICAgIHJhaXNlIFdvcmtmbG93RXJyb3IoZiJwcmlvciBwaGFzZXMgbm90IGFjY2VwdGVkOiB7JywgJy5qb2luKHByaW9yKX0iKQogICAgICAgICAgICAgICAgcGhhc2Vfbm9kZXMgPSBbKG5vZGVfaWQsIG5vZGUpIGZvciBub2RlX2lkLCBub2RlIGluIG5vZGVzLml0ZW1zKCkgaWYgbm9kZVsicGhhc2UiXSA9PSBhcmdzLnBoYXNlXQogICAgICAgICAgICAgICAgYmxvY2tlZCA9IFsKICAgICAgICAgICAgICAgICAgICBub2RlX2lkIGZvciBub2RlX2lkLCBub2RlIGluIHBoYXNlX25vZGVzCiAgICAgICAgICAgICAgICAgICAgaWYgbm90IChjbG9zdXJlX3JlYWR5KG5vZGVzLCBub2RlX2lkKSBpZiBtb2RlIGluICgiZ3JhcGgiLCAicmlzayIpIGVsc2UgcmVhZHkobm9kZSkpCiAgICAgICAgICAgICAgICBdCiAgICAgICAgICAgICAgICBpZiBibG9ja2VkOgogICAgICAgICAgICAgICAgICAgIHJhaXNlIFdvcmtmbG93RXJyb3IoZiJibG9ja2VkIG5vZGVzIGluIHthcmdzLnBoYXNlfTogeycsICcuam9pbihibG9ja2VkKX0iKQogICAgICAgICAgICAgICAgc3RhdGVbInBoYXNlX3N0YXR1cyJdW2FyZ3MucGhhc2VdID0gImFjY2VwdGVkIgogICAgICAgICAgICAgICAgc3RhdGVbImFjY2VwdGVkX3ZlcnNpb25zIl1bYXJncy5waGFzZV0gPSBjbG9zdXJlX3ZlcnNpb25zKAogICAgICAgICAgICAgICAgICAgIG5vZGVzLCBbbm9kZV9pZCBmb3Igbm9kZV9pZCwgXyBpbiBwaGFzZV9ub2Rlc10KICAgICAgICAgICAgICAgICkKICAgICAgICAgICAgICAgIHJlY29yZChzdGF0ZSwgImFkdmFuY2UiLCBwaGFzZT1hcmdzLnBoYXNlKQogICAgICAgICAgICAgICAgd3JpdGVfanNvbihhcmdzLnN0YXRlLCBzdGF0ZSkKICAgICAgICAgICAgICAgIHJlc3VsdCA9IHsib2siOiBUcnVlLCAiYWN0aW9uIjogImFkdmFuY2UiLCAicGhhc2UiOiBhcmdzLnBoYXNlfQogICAgICAgICAgICBlbGlmIGFyZ3MuY29tbWFuZCA9PSAicmV2aXNlIjoKICAgICAgICAgICAgICAgIG5vZGUgPSBub2Rlcy5nZXQoYXJncy5pZCkKICAgICAgICAgICAgICAgIGlmIG5vZGUgaXMgTm9uZSBvciBub2RlWyJraW5kIl0gPT0gIm5vcm1hdGl2ZSI6CiAgICAgICAgICAgICAgICAgICAgcmFpc2UgV29ya2Zsb3dFcnJvcihmInJldmlzYWJsZSBub25ub3JtYXRpdmUgbm9kZSBub3QgZm91bmQ6IHthcmdzLmlkfSIpCiAgICAgICAgICAgICAgICBpZiBub3QgYXJncy5yZWFzb24uc3RyaXAoKToKICAgICAgICAgICAgICAgICAgICByYWlzZSBXb3JrZmxvd0Vycm9yKCJyZXZpc2lvbiByZWFzb24gbXVzdCBiZSBub25lbXB0eSIpCiAgICAgICAgICAgICAgICBub2RlWyJzdGF0dXMiXSA9IGFyZ3Muc3RhdHVzCiAgICAgICAgICAgICAgICBub2RlWyJ2ZXJzaW9uIl0gKz0gMQogICAgICAgICAgICAgICAgYWZmZWN0ZWQgPSB7YXJncy5pZH0KICAgICAgICAgICAgICAgIGlmIG1vZGUgaW4gKCJncmFwaCIsICJyaXNrIik6CiAgICAgICAgICAgICAgICAgICAgYWZmZWN0ZWQudXBkYXRlKGRlc2NlbmRhbnRzKG5vZGVzLCBhcmdzLmlkKSkKICAgICAgICAgICAgICAgICAgICBmb3IgY2hpbGRfaWQgaW4gYWZmZWN0ZWQgLSB7YXJncy5pZH06CiAgICAgICAgICAgICAgICAgICAgICAgIG5vZGVzW2NoaWxkX2lkXVsic3RhbGUiXSA9IFRydWUKICAgICAgICAgICAgICAgICAgICAgICAgaWYgbm9kZXNbY2hpbGRfaWRdWyJraW5kIl0gPT0gIm5vcm1hdGl2ZSI6CiAgICAgICAgICAgICAgICAgICAgICAgICAgICBub2Rlc1tjaGlsZF9pZF1bInN0YXR1cyJdID0gInBlbmRpbmciCiAgICAgICAgICAgICAgICBmb3IgcGhhc2UgaW4gUEhBU0VTOgogICAgICAgICAgICAgICAgICAgIGlmIHN0YXRlWyJwaGFzZV9zdGF0dXMiXVtwaGFzZV0gPT0gImFjY2VwdGVkIiBhbmQgYW55KAogICAgICAgICAgICAgICAgICAgICAgICBub2Rlc1tub2RlX2lkXVsicGhhc2UiXSA9PSBwaGFzZSBmb3Igbm9kZV9pZCBpbiBhZmZlY3RlZAogICAgICAgICAgICAgICAgICAgICk6CiAgICAgICAgICAgICAgICAgICAgICAgIHN0YXRlWyJwaGFzZV9zdGF0dXMiXVtwaGFzZV0gPSAibmVlZHNfcmV2aWV3IgogICAgICAgICAgICAgICAgcmVjb3JkKHN0YXRlLCAicmV2aXNlIiwgbm9kZT1hcmdzLmlkLCBzdGF0dXM9YXJncy5zdGF0dXMsCiAgICAgICAgICAgICAgICAgICAgICAgcmVhc29uPWFyZ3MucmVhc29uLCBhZmZlY3RlZD1zb3J0ZWQoYWZmZWN0ZWQpKQogICAgICAgICAgICAgICAgd3JpdGVfanNvbihhcmdzLnN0YXRlLCBzdGF0ZSkKICAgICAgICAgICAgICAgIHJlc3VsdCA9IHsib2siOiBUcnVlLCAiYWN0aW9uIjogInJldmlzZSIsICJpZCI6IGFyZ3MuaWQsCiAgICAgICAgICAgICAgICAgICAgICAgICAgImFmZmVjdGVkIjogc29ydGVkKGFmZmVjdGVkKX0KICAgICAgICAgICAgZWxpZiBhcmdzLmNvbW1hbmQgPT0gInJldmlldyI6CiAgICAgICAgICAgICAgICBpZiBtb2RlIG5vdCBpbiAoImdyYXBoIiwgInJpc2siKToKICAgICAgICAgICAgICAgICAgICByYWlzZSBXb3JrZmxvd0Vycm9yKCJyZXZpZXcgaXMgYXZhaWxhYmxlIG9ubHkgaW4gZ3JhcGggb3IgcmlzayBtb2RlIikKICAgICAgICAgICAgICAgIG5vZGUgPSBub2Rlcy5nZXQoYXJncy5pZCkKICAgICAgICAgICAgICAgIGlmIG5vZGUgaXMgTm9uZSBvciBub3Qgbm9kZVsic3RhbGUiXToKICAgICAgICAgICAgICAgICAgICByYWlzZSBXb3JrZmxvd0Vycm9yKGYic3RhbGUgbm9kZSBub3QgZm91bmQ6IHthcmdzLmlkfSIpCiAgICAgICAgICAgICAgICBpZiBub2RlWyJraW5kIl0gPT0gIm5vcm1hdGl2ZSI6CiAgICAgICAgICAgICAgICAgICAgcmFpc2UgV29ya2Zsb3dFcnJvcihmIm5vcm1hdGl2ZSBub2RlIHJlcXVpcmVzIGV4cGxpY2l0IGFwcHJvdmFsOiB7YXJncy5pZH0iKQogICAgICAgICAgICAgICAgaWYgbm90IHJlYWR5KHsqKm5vZGUsICJzdGFsZSI6IEZhbHNlfSkgb3Igbm90IGFsbCgKICAgICAgICAgICAgICAgICAgICBjbG9zdXJlX3JlYWR5KG5vZGVzLCBkZXApIGZvciBkZXAgaW4gbm9kZVsiZGVwZW5kc19vbiJdCiAgICAgICAgICAgICAgICApOgogICAgICAgICAgICAgICAgICAgIHJhaXNlIFdvcmtmbG93RXJyb3IoZiJkZXBlbmRlbmNpZXMgYmxvY2tlZCBmb3IgcmV2aWV3IG9mIHthcmdzLmlkfSIpCiAgICAgICAgICAgICAgICBub2RlWyJzdGFsZSJdID0gRmFsc2UKICAgICAgICAgICAgICAgIG5vZGVbInZlcnNpb24iXSArPSAxCiAgICAgICAgICAgICAgICByZWNvcmQoc3RhdGUsICJyZXZpZXciLCBub2RlPWFyZ3MuaWQsIHZlcnNpb249bm9kZVsidmVyc2lvbiJdKQogICAgICAgICAgICAgICAgd3JpdGVfanNvbihhcmdzLnN0YXRlLCBzdGF0ZSkKICAgICAgICAgICAgICAgIHJlc3VsdCA9IHsib2siOiBUcnVlLCAiYWN0aW9uIjogInJldmlldyIsICJpZCI6IGFyZ3MuaWR9CiAgICAgICAgICAgIGVsc2U6CiAgICAgICAgICAgICAgICByYWlzZSBBc3NlcnRpb25FcnJvcihhcmdzLmNvbW1hbmQpCiAgICAgICAgcHJpbnQoanNvbi5kdW1wcyhyZXN1bHQsIGVuc3VyZV9hc2NpaT1GYWxzZSwgc29ydF9rZXlzPVRydWUpKQogICAgICAgIHJldHVybiAwCiAgICBleGNlcHQgKFdvcmtmbG93RXJyb3IsIEtleUVycm9yLCBUeXBlRXJyb3IpIGFzIGV4YzoKICAgICAgICBwcmludChqc29uLmR1bXBzKHsib2siOiBGYWxzZSwgImVycm9yIjogc3RyKGV4Yyl9LCBlbnN1cmVfYXNjaWk9RmFsc2UsIHNvcnRfa2V5cz1UcnVlKSkKICAgICAgICByZXR1cm4gMgoKCmlmIF9fbmFtZV9fID09ICJfX21haW5fXyI6CiAgICBwcmludCgiSW52b2tlIHNlcXVlbnRpYWwucHkgb3IgZ3JhcGgucHkiLCBmaWxlPXN5cy5zdGRlcnIpCiAgICByYWlzZSBTeXN0ZW1FeGl0KDIpCg==", validate=True)
CORE_SHA256 = "6bf67d5542ac4fb9b9b1f9bd1e122ddb4c3b0a29e2fe26d040f1c401a2828986"
if hashlib.sha256(CORE_BYTES).hexdigest() != CORE_SHA256:
    raise SystemExit("embedded prototype core digest differs")
_core = types.ModuleType("embedded_development_prototype_core")
_core.__file__ = "<embedded prototypes/core.py>"
exec(compile(CORE_BYTES, _core.__file__, "exec"), _core.__dict__)

MODE = {"A": "sequential", "B": "graph", "C": "risk"}
WRITABLE = {"analysis.py", "report.md", "sources.json"}
MAX_REQUEST = 16 * 1024
MAX_FILE = 256 * 1024
MAX_PUBLIC_FILE = 4 * 1024 * 1024
MAX_CHUNK = 8192
MAX_CORE_OUTPUT = 128 * 1024
MAX_STDERR = 8192


class ToolError(ValueError):
    pass


class MethodRejected(ValueError):
    pass


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ToolError("duplicate JSON key")
        result[key] = value
    return result


def strict_json(raw):
    try:
        return json.loads(raw, object_pairs_hook=pairs,
                          parse_constant=lambda _value: (_ for _ in ()).throw(
                              ToolError("nonfinite JSON value")))
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise ToolError("invalid strict JSON") from exc


def canonical(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("ascii")


def exact(value, keys):
    if type(value) is not dict or set(value) != set(keys):
        raise ToolError("request fields differ from operation schema")


def directory(path: Path, name: str):
    if not path.is_absolute() or path.name != name:
        raise ToolError("tool directory identity is invalid")
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode):
        raise ToolError("tool directory is not a real directory")


def file_state(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_nlink,
            info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def regular(path: Path, maximum: int, *, optional=False):
    try:
        info = path.lstat()
    except FileNotFoundError:
        if optional:
            return None
        raise ToolError("required regular file is absent") from None
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > maximum:
        raise ToolError("file is linked, nonregular, or too large")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        observed = os.fstat(fd)
        if not stat.S_ISREG(observed.st_mode) or observed.st_nlink != 1:
            raise ToolError("file identity changed")
        raw = b""
        while len(raw) <= maximum:
            chunk = os.read(fd, maximum - len(raw) + 1)
            if not chunk:
                break
            raw += chunk
        if (len(raw) > maximum or file_state(os.fstat(fd)) != file_state(observed)
                or file_state(path.lstat()) != file_state(observed)):
            raise ToolError("file changed or exceeded limit during read")
        return raw
    finally:
        os.close(fd)


def private_new(path: Path, raw: bytes):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600:
            raise ToolError("private method file was not created with mode 0600")
        with os.fdopen(fd, "wb", closefd=False) as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    finally:
        os.close(fd)
    folder = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(folder)
    finally:
        os.close(folder)


def safe_name(name):
    if (type(name) is not str or not name or name in {".", ".."}
            or "/" in name or "\\" in name or "\x00" in name
            or len(name.encode("utf-8")) > 160):
        raise ToolError("file name is not a flat public name")
    return name


def identity(case: Path, inputs: Path):
    manifest_raw = regular(case / "case.json", 1024 * 1024)
    prompt_raw = regular(inputs / "arm_prompt", 64 * 1024)
    manifest, prompt = strict_json(manifest_raw), strict_json(prompt_raw)
    if type(manifest) is not dict or type(manifest.get("case_id")) is not str or not manifest["case_id"]:
        raise ToolError("case manifest lacks a case identity")
    files, deliverables = manifest.get("files"), manifest.get("deliverables")
    if (type(files) is not list or not 1 <= len(files) <= 64
            or type(deliverables) is not list):
        raise ToolError("case manifest lacks public files or deliverables")
    public = {}
    for item in files:
        if (type(item) is not dict or set(item) != {"path", "sha256", "bytes"}
                or type(item["sha256"]) is not str
                or re.fullmatch(r"[0-9a-f]{64}", item["sha256"]) is None
                or type(item["bytes"]) is not int
                or not 0 <= item["bytes"] <= MAX_PUBLIC_FILE):
            raise ToolError("case manifest file record is invalid")
        name = safe_name(item["path"])
        if name in public:
            raise ToolError("duplicate public file name")
        public[name] = item
    if (any(type(name) is not str or safe_name(name) not in WRITABLE | {"metrics.json"}
            for name in deliverables) or len(set(deliverables)) != len(deliverables)):
        raise ToolError("deliverables are not supported")
    exact(prompt, ("alternative", "mode", "instructions"))
    alternative, mode = prompt["alternative"], prompt["mode"]
    if (alternative not in MODE or mode != MODE[alternative]
            or type(prompt["instructions"]) is not str or not prompt["instructions"].strip()):
        raise ToolError("alternative, mode, or instructions are invalid")
    return manifest, public, set(deliverables), alternative, mode, sha(manifest_raw), sha(prompt_raw)


def state_digest(work: Path):
    raw = regular(work / "method_state.json", MAX_FILE, optional=True)
    return None if raw is None else sha(raw)


def proposal_digest(work: Path):
    raw = regular(work / "proposal.json", MAX_FILE, optional=True)
    return None if raw is None else sha(raw)


def result_base(op, manifest, alternative, mode, manifest_sha, prompt_sha, work):
    return {"schema": 1, "operation": op, "alternative": alternative,
            "mode": mode, "case_id": manifest["case_id"],
            "case_manifest_sha256": manifest_sha, "arm_prompt_sha256": prompt_sha,
            "embedded_core_sha256": CORE_SHA256,
            "method_state_sha256": state_digest(work),
            "proposal_sha256": proposal_digest(work),
            "parallel_work_executed": False}


def run_core(mode, args):
    stdout, stderr = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        code = _core.run(mode, args)
    if code not in {0, 2}:
        raise ToolError("prototype core returned an unexpected exit code")
    raw = stdout.getvalue()
    if len(raw.encode("utf-8")) > MAX_CORE_OUTPUT or len(stderr.getvalue().encode("utf-8")) > MAX_STDERR:
        raise ToolError("prototype core output exceeded its bound")
    outcome = strict_json(raw)
    if type(outcome) is not dict or outcome.get("ok") is not (code == 0):
        raise ToolError("prototype core output disagrees with exit code")
    return code, outcome, stderr.getvalue()


def prototype_operation(request, manifest, mode, work):
    op = request["op"]
    state = work / "method_state.json"
    if op == "init":
        exact(request, ("op", "nodes"))
        nodes = request["nodes"]
        if type(nodes) is not list or not 4 <= len(nodes) <= 64:
            raise MethodRejected("prototype proposal needs 4 to 64 nodes")
        if any(type(node) is not dict or node.get("status") != "pending"
               or not {"id", "kind", "phase", "status", "claim", "depends_on"} <= set(node)
               or set(node) - {"id", "kind", "phase", "status", "claim", "depends_on", "risk"}
               for node in nodes):
            raise MethodRejected("prototype nodes must begin pending with exact fields")
        proposal = {"case_id": manifest["case_id"], "nodes": nodes}
        try:
            validated = _core.validate_case(proposal)
        except _core.WorkflowError as exc:
            raise MethodRejected(str(exc)) from exc
        normative = [key for key, node in validated.items() if node["kind"] == "normative"]
        if not any(node["kind"] == "requirement" and node["phase"] == "engineering"
                   and any(key in _core.closure_versions(validated, [node_id]) for key in normative)
                   for node_id, node in validated.items()):
            raise MethodRejected("engineering requirement lacks pending normative dependency")
        if proposal_digest(work) is not None or state_digest(work) is not None:
            raise MethodRejected("prototype is already initialized")
        private_new(work / "proposal.json", canonical(proposal) + b"\n")
        return run_core(mode, ["init", "--case", str(work / "proposal.json"),
                               "--state", str(state)])
    if state_digest(work) is None:
        raise MethodRejected("prototype is not initialized")
    if op == "status":
        exact(request, ("op",))
        args = ["status"]
    elif op == "revise":
        exact(request, ("op", "id", "status", "reason"))
        if (type(request["id"]) is not str or not request["id"]
                or request["status"] not in {"pending", "supported", "contradicted"}
                or type(request["reason"]) is not str or not request["reason"].strip()):
            raise ToolError("revise arguments are invalid")
        args = ["revise", "--id", request["id"], "--status", request["status"],
                "--reason", request["reason"]]
    elif op == "review":
        exact(request, ("op", "id"))
        if type(request["id"]) is not str or not request["id"]:
            raise ToolError("review id is invalid")
        args = ["review", "--id", request["id"]]
    elif op == "advance":
        exact(request, ("op", "phase"))
        if request["phase"] not in _core.PHASES:
            raise ToolError("advance phase is invalid")
        args = ["advance", "--phase", request["phase"]]
    elif op == "plan":
        exact(request, ("op", "budget"))
        if type(request["budget"]) is not int or not 1 <= request["budget"] <= 64:
            raise ToolError("plan task budget is invalid")
        args = ["plan", "--budget", str(request["budget"])]
    else:
        raise ToolError("prototype operation is not allowed")
    args += ["--state", str(state)]
    return run_core(mode, args)


def read_public(request, case, public):
    exact(request, ("op", "path", "offset", "length"))
    name = safe_name(request["path"])
    if name not in public:
        raise ToolError("public file is not enumerated in case manifest")
    offset, length = request["offset"], request["length"]
    if type(offset) is not int or offset < 0 or type(length) is not int or not 1 <= length <= MAX_CHUNK:
        raise ToolError("read offset or length is invalid")
    record = public[name]
    raw = regular(case / name, MAX_PUBLIC_FILE)
    if len(raw) != record["bytes"] or sha(raw) != record["sha256"]:
        raise ToolError("public source differs from case manifest")
    try:
        raw.decode("utf-8")
    except UnicodeError as exc:
        raise ToolError("public file is not UTF-8 text") from exc
    if offset > len(raw):
        raise ToolError("read offset exceeds file")
    end = min(len(raw), offset + length)
    while end > offset:
        try:
            content = raw[offset:end].decode("utf-8")
            break
        except UnicodeError:
            end -= 1
    else:
        if offset == len(raw):
            content = ""
        else:
            raise ToolError("read range splits a UTF-8 character")
    return {"path": name, "offset": offset, "next_offset": end,
            "eof": end == len(raw), "content": content,
            "source_sha256": record["sha256"]}


def write_deliverable(request, work, deliverables):
    exact(request, ("op", "path", "offset", "content"))
    name = safe_name(request["path"])
    if name not in WRITABLE or name not in deliverables:
        raise ToolError("write path is not an allowed deliverable")
    offset, content = request["offset"], request["content"]
    if type(offset) is not int or offset < 0 or type(content) is not str:
        raise ToolError("write offset or content is invalid")
    raw = content.encode("utf-8")
    if not raw or len(raw) > MAX_CHUNK or offset + len(raw) > MAX_FILE:
        raise ToolError("write chunk or total file exceeds limit")
    path = work / name
    try:
        fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_NOFOLLOW)
    except FileNotFoundError:
        if offset != 0:
            raise ToolError("new deliverable requires offset zero") from None
        fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                or stat.S_IMODE(info.st_mode) != 0o600 or info.st_size != offset):
            raise ToolError("deliverable offset or file identity differs")
        written = os.write(fd, raw)
        if written != len(raw):
            raise ToolError("deliverable write was partial")
        os.fsync(fd)
    finally:
        os.close(fd)
    return {"path": name, "bytes": offset + len(raw),
            "sha256": sha(regular(path, MAX_FILE))}


def replace_deliverable(request, inputs, work, deliverables):
    exact(request, ("op", "path", "expected_sha256", "content"))
    policy = strict_json(regular(inputs / "tool_policy", 128 * 1024))
    if type(policy) is not dict or policy.get("schema") != 2:
        raise ToolError("deliverable replacement requires the opt-in v2 policy")
    name = safe_name(request["path"])
    if name not in WRITABLE or name not in deliverables:
        raise ToolError("replace path is not an allowed deliverable")
    expected, content = request["expected_sha256"], request["content"]
    if (type(expected) is not str or re.fullmatch(r"[0-9a-f]{64}", expected) is None
            or type(content) is not str):
        raise ToolError("replacement content or expected digest is invalid")
    raw = content.encode("utf-8")
    if not raw or len(raw) > MAX_CHUNK:
        raise ToolError("replacement chunk exceeds limit")
    path = work / name
    if sha(regular(path, MAX_FILE)) != expected:
        raise ToolError("deliverable differs from expected replacement digest")
    temporary = work / f".replace-{name}-{os.getpid()}"
    private_new(temporary, raw)
    if sha(regular(path, MAX_FILE)) != expected:
        raise ToolError("deliverable changed before replacement")
    os.replace(temporary, path)
    folder = os.open(work, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(folder)
    finally:
        os.close(folder)
    return {"path": name, "bytes": len(raw), "previous_sha256": expected,
            "sha256": sha(regular(path, MAX_FILE))}


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    try:
        if len(argv) != 4 or len(argv[3].encode("ascii")) > MAX_REQUEST:
            raise ToolError("expected case, inputs, work, and bounded canonical tool args")
        case, inputs, work = map(Path, argv[:3])
        for path, name in ((case, "case"), (inputs, "inputs"), (work, "work")):
            directory(path, name)
        if case.parent != inputs.parent or case.parent != work.parent:
            raise ToolError("tool directories do not share one stage")
        outer = strict_json(argv[3])
        exact(outer, ("request",))
        if type(outer["request"]) is not str or canonical(outer).decode("ascii") != argv[3]:
            raise ToolError("tool args are not canonical or request is not a string")
        request = strict_json(outer["request"])
        if type(request) is not dict or type(request.get("op")) is not str:
            raise ToolError("request must be an operation object")
        manifest, public, deliverables, alternative, mode, manifest_sha, prompt_sha = identity(case, inputs)
        op = request["op"]
        if op in {"init", "advance", "approve"}:
            raise ToolError("branch cannot initialize, approve or advance")
        if op in {"revise", "review"}:
            if request.get("id") not in ["P1"]:
                raise ToolError("operation is outside branch ownership")
        base = result_base(op, manifest, alternative, mode, manifest_sha, prompt_sha, work)
        if op in {"init", "status", "revise", "review", "advance", "plan"}:
            try:
                code, result, stderr = prototype_operation(request, manifest, mode, work)
                details = {"method_result": result, "method_stderr": stderr}
            except MethodRejected as exc:
                code, details = 2, {"method_error": str(exc)}
        elif op == "read":
            code, details = 0, read_public(request, case, public)
        elif op == "write":
            code, details = 0, write_deliverable(request, work, deliverables)
        elif op == "replace":
            code, details = 0, replace_deliverable(request, inputs, work, deliverables)
        elif op == "analyze":
            raise ToolError("analysis execution is disabled; use an independently isolated evaluator")
        else:
            raise ToolError("operation is not allowed")
        base.update(ok=code == 0, method_exit_code=code, details=details,
                    method_state_sha256=state_digest(work),
                    proposal_sha256=proposal_digest(work))
        print(json.dumps(base, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False))
        return 0
    except (ToolError, OSError, TypeError, KeyError, OverflowError, UnicodeError) as exc:
        print(f"development method tool failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
