#!/usr/bin/env python3
"""probe/test_rig_p1c.py — device-free negative/positive suite for
probe/rig_p1c.py (TASK-677 H-1). Fixtures are the exact lines EXP-026 §2
recorded, so this pins the driver's parsing to a transcript that is already
known-good rather than a synthetic guess.

    python3 app/tools/probe/test_rig_p1c.py [-v]
"""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from probe import rig_p1c as rp


# EXP-026 §2's raw transcript, run 1 of 4 (scanLoop 60), plus the interleaved
# [bod] TRIP / reason=201 lines a real slice would also carry.
_SLICE_RUN1 = """\
[wifi-sup] kick=1 attempt for "<home-ssid>" cand=1/2
reason=201 sta=1
reason=201 sta=1
[bod] TRIP tag=run t=1234ms thres=7 trips=1 det=0 us=100 dur=0 min=7 ctx=03
{"ok":true,"cmd":"set","var":"scanLoop","secs":60,"r201":600,"disc":24,"bodTrips":0,"reconnected":0,"savedSsid":"<home-ssid>"}
"""

_BOD_REPLY = """\
some interleaved boot chatter
{"ok":true,"cmd":"get","var":"bod","count":1,"dropped":0,"firstUs":100,"lastUs":100,"minLevel":7,"maxDurUs":0,"hist":[0,0,0,0,0,0,0,1],"phaseAtFirst":3,"thres":7,"armed":true,"rearms":1,"holdoffs":0,"disarmed":false,"descend":false,"armedLevel":7,"floor":8,"stepsDown":0,"stepsUp":0,"quietMs":30000,"last":true}
"""


class TestParseSlice(unittest.TestCase):
    def test_pulls_the_scanloop_reply(self):
        r = rp.parse_slice(_SLICE_RUN1)
        self.assertIsNotNone(r["scanLoop"])
        self.assertEqual(r["scanLoop"]["r201"], 600)
        self.assertEqual(r["scanLoop"]["disc"], 24)
        self.assertEqual(r["scanLoop"]["secs"], 60)

    def test_counts_trips_and_reason201(self):
        r = rp.parse_slice(_SLICE_RUN1)
        self.assertEqual(r["tripsInSlice"], 1)
        self.assertEqual(r["reason201InSlice"], 2)

    def test_no_scanloop_reply_yields_none(self):
        r = rp.parse_slice("nothing relevant here\n")
        self.assertIsNone(r["scanLoop"])
        self.assertEqual(r["tripsInSlice"], 0)
        self.assertEqual(r["reason201InSlice"], 0)

    def test_takes_the_last_scanloop_reply_if_several(self):
        two = _SLICE_RUN1 + _SLICE_RUN1.replace('"r201":600', '"r201":700')
        r = rp.parse_slice(two)
        self.assertEqual(r["scanLoop"]["r201"], 700)


class TestParseBod(unittest.TestCase):
    def test_parses_the_widened_f6_fields(self):
        b = rp.parse_bod(_BOD_REPLY)
        self.assertIsNotNone(b)
        self.assertEqual(b["armedLevel"], 7)
        self.assertEqual(b["floor"], 8)
        self.assertFalse(b["descend"])

    def test_missing_reply_yields_none(self):
        self.assertIsNone(rp.parse_bod("no get bod line here\n"))


class TestSummaryLine(unittest.TestCase):
    def test_missing_scanloop_falls_back_to_question_marks(self):
        line = rp.summary_line({"secs": 60, "scanLoop": None,
                                "tripsInSlice": 0, "reason201InSlice": 0})
        self.assertIn("?", line)
        self.assertIn("60", line)


if __name__ == "__main__":
    unittest.main()
