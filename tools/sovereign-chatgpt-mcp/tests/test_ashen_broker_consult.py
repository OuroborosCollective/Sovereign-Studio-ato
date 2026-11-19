"""Input contract for a targeted council; never a simulated Runtime assertion."""
import unittest
from ashen_broker_adapter import select_departments

class CouncilSelection(unittest.TestCase):
    def test_narrow_selection_and_explicit_full_council(self):
        allowed={"world_design","combat_design","lore","quality_assurance"}
        self.assertEqual(("world_design",),select_departments(["world_design"],allowed))
        self.assertEqual(("world_design","lore"),select_departments(["world_design","lore"],allowed))
        self.assertEqual(("world_design","combat_design","lore","quality_assurance"),
                         select_departments(["world_design","combat_design","lore","quality_assurance"],
                                            allowed,full_council=True))
        for depts,full in [([],False),(["world_design"]*2,False),
                           (["world_design","combat_design","lore","quality_assurance"],False),
                           (["unknown_department"],False),(["../world"],False)]:
            with self.subTest(depts=depts),self.assertRaises(ValueError):
                select_departments(depts,allowed,full_council=full)

if __name__=="__main__":unittest.main()
