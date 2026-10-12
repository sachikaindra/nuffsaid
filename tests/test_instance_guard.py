import subprocess
import sys
import unittest
import uuid
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from instance_guard import InstanceGuard


class InstanceGuardTests(unittest.TestCase):
    def name(self):
        return 'Local\\DictationApp-test-' + uuid.uuid4().hex

    def test_second_launch_activates_primary_and_can_restart(self):
        name = self.name()
        first = InstanceGuard(name)
        second = InstanceGuard(name)
        try:
            self.assertTrue(first.is_primary)
            self.assertFalse(second.is_primary)
            self.assertFalse(first.activation_requested())
            second.activate()
            self.assertTrue(first.activation_requested())
            self.assertFalse(first.activation_requested())
        finally:
            second.close()
            first.close()
        restarted = InstanceGuard(name)
        try:
            self.assertTrue(restarted.is_primary)
        finally:
            restarted.close()

    def test_crashed_process_leaves_no_stale_instance_lock(self):
        name = self.name()
        code = 'from instance_guard import InstanceGuard; import sys; g=InstanceGuard(sys.argv[1]); print("ready", flush=True); sys.stdin.read()'
        # Use the interpreter itself, not Windows' venv launcher (which spawns
        # a child and can exit while that child still owns the instance handle).
        interpreter = getattr(sys, '_base_executable', sys.executable)
        process = subprocess.Popen([interpreter, '-c', code, name], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
        try:
            self.assertEqual(process.stdout.readline().strip(), 'ready')
            second = InstanceGuard(name)
            try:
                self.assertFalse(second.is_primary)
            finally:
                second.close()
            process.terminate()
            process.wait(timeout=5)
            restarted = InstanceGuard(name)
            try:
                self.assertTrue(restarted.is_primary)
            finally:
                restarted.close()
        finally:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=5)
            process.stdin.close()
            process.stdout.close()


if __name__ == '__main__':
    unittest.main()
