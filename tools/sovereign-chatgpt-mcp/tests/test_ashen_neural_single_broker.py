"""Bounded read-only broker contract: no fake runtime substitutions."""
import unittest
from ashen_broker_adapter import validate_owner, validate_advice

SRC="a"*40
UNITY="b"*40
REPO="https://github.com/OuroborosCollective/ARPG-ARE-D4SC-LOGIC"
ISSUE={"number":62,"state":"open","title":"Test input (caller supplied)","url":REPO+"/issues/62"}

def args(**kw):
    v={"department":"world_design","expected_source_sha":SRC,
       "expected_unity_sha":UNITY,"issues":[ISSUE]}
    v.update(kw)
    return v

class BrokerBoundary(unittest.TestCase):
    def test_owner_guard(self):
        self.assertTrue(validate_owner(True))
        with self.assertRaisesRegex(ValueError,"OWNER_REQUIRED"):validate_owner(False)

    def test_valid_caller_supplied_inputs(self):
        got,body=validate_advice(args(),SRC,UNITY)
        self.assertEqual("world_design",got["department"])
        self.assertEqual("CALLER_SUPPLIED_UNVERIFIED",got["sourceVerification"])
        self.assertIn(b'"issues"',body)

    def test_stale_sha_and_unknown_department_fail(self):
        for change in ({"expected_source_sha":"c"*40},
                       {"expected_unity_sha":"c"*40},
                       {"department":"../runtime"},
                       {"department":"x"},
                       {"department":"really_unknown_department"}):
            with self.subTest(change=change),self.assertRaises(ValueError):
                validate_advice(args(**change),SRC,UNITY,departments={"world_design"})

    def test_issue_integrity_and_effect_gates(self):
        for change in ({"issues":[]},{"issues":None},
                       {"issues":[ISSUE,ISSUE]},
                       {"issues":[dict(ISSUE,url=REPO+"/issues/63")]},
                       {"issues":[dict(ISSUE,state="draft")]},
                       {"issues":[dict(ISSUE,command="do something")]},
                       {"issues":[dict(ISSUE,title="x"*301)]},
                       {"issues":[ISSUE]*65},
                       {"execute":True},{"owner_approved":True}):
            with self.subTest(change=str(change)[:60]),self.assertRaises(ValueError):
                validate_advice(args(**change),SRC,UNITY,departments={"world_design"})

if __name__=="__main__":unittest.main()
