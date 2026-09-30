"""
Unit tests for the local pipeline pieces (classifier + local image gen).
Run with: python -m unittest tests/test.py
No remote API calls required for these to pass.
"""

import os
import sys
import unittest

# Add the project root to sys.path so `app` can be imported from tests/test.py.
########################### Failure Setup Start ######################################
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
########################### Failure Setup Done #######################################

from dance_of_lyfe import can_you_dance

class TestLocalPipeline(unittest.TestCase):

    def test_classify_audio_handles_none(self):
        op_1 = can_you_dance(2)
        op_2 = can_you_dance(3)

        self.assertEqual(op_1, True)
        self.assertEqual(op_2, False)

if __name__ == "__main__":
    unittest.main()
