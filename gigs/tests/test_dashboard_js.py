import shutil
import subprocess
from pathlib import Path

from django.test import SimpleTestCase


class DashboardProfileJsTests(SimpleTestCase):
    """Runs the Node regression tests for the profile page's pending media state."""

    def test_pending_media_state_and_save_recovery(self):
        node = shutil.which('node')
        if node is None:
            self.skipTest('node is not installed')
        script = Path(__file__).parent / 'js' / 'dashboard_profile.test.js'
        result = subprocess.run([node, str(script)], capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
