"""Permission and contention failures must precede resume authorization writes."""
from contextlib import contextmanager
from pathlib import Path
import sys
import unittest
from unittest import mock
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'skills/task-checkpoint/scripts'))
import checkpoint as cp
import monitor
import reserve
import test_reserve_policy as fixtures
import test_reserve_integration as integration


class ResumeLockTests(unittest.TestCase):
    setUp = fixtures.ReserveTests.setUp
    signals = fixtures.ReserveTests.signals
    review = integration.ReserveIntegrationTests.review

    def prepare(self, owned=False):
        if owned:
            cp.Ownership(self.root, self.binding, self.store).acquire('fixture')
        self.account = self.root / 'collector'
        self.account.mkdir()
        cp.atomic(self.account/'config.json', cp.encoded({'guard_percent':20}))
        cp.atomic(self.account/'signals.json', cp.encoded(self.signals(14)))
        # Ignore this fixture-only collector before taking the stop snapshot.
        (self.root/'.gitignore').write_text('.checkpoint/\ncollector/\n')
        monitor.stop_for_signals(self.root, self.signals(14), account_state=self.account)
        reserve.grant(self.root, 'ten', self.signals(14), 'Test continuation', 'Current test instruction')
        return self.review()

    def state(self):
        names = ('resume.json','owner.json','allowance-override.json','automatic-stop.json','latest.json')
        return {n:(self.store/n).read_bytes() if (self.store/n).exists() else None for n in names}

    def test_denied_collector_lock_does_not_activate_or_acquire(self):
        review = self.prepare()
        before = self.state()
        real_lock = cp.lock
        @contextmanager
        def denied(path):
            if path.resolve() == (self.account/'preservation').resolve():
                raise PermissionError('fixture denied')
            with real_lock(path):
                yield
        with mock.patch.object(cp, 'lock', denied):
            with self.assertRaisesRegex(cp.Fault, 'collector lock directory'):
                cp.resume(self.root, review, 'fixture', [])
        self.assertEqual(before, self.state())
        self.assertFalse(cp.Ownership(self.root,self.binding,self.store).tip())

    def test_busy_collector_preserves_existing_lease_and_pending_grant(self):
        review = self.prepare(owned=True)
        before = self.state()
        guard = self.account/'preservation'; guard.mkdir()
        with cp.lock(guard):
            with self.assertRaisesRegex(cp.Fault, 'Writer lock'):
                cp.resume(self.root, review, 'fixture', [])
        self.assertEqual(before, self.state())

    def test_scoped_access_resumes_with_same_lease_under_collector_lock(self):
        review = self.prepare(owned=True)
        owner = (self.store/'owner.json').read_bytes()
        activate = reserve.activate
        def checked(root):
            self.assertTrue((self.account/'preservation/writer.lock').exists())
            self.assertTrue((self.store/'writer.lock').exists())
            return activate(root)
        with mock.patch.object(reserve, 'activate', checked):
            result = cp.resume(self.root, review, 'fixture', [])
        self.assertTrue(result['implementation_allowed'])
        self.assertEqual(owner, (self.store/'owner.json').read_bytes())
        self.assertEqual(cp.read(self.store/'allowance-override.json')['state'], 'active')
        self.assertFalse((self.store/'automatic-stop.json').exists())
        self.assertFalse((self.account/'preservation/writer.lock').exists())

if __name__ == '__main__':
    unittest.main()
