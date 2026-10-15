#!/usr/bin/env python3
"""Reference deletion must revalidate after a competing writer commits."""
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
from drlink_control_db import ControlPlaneError
from drlink_control_plane import ControlPlane
import drlink_v24 as v24


class ReferenceDeleteSerialization(unittest.TestCase):
    def test_reference_added_after_delete_preflight_is_preserved(self):
        for kind in ('network', 'service'):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as root:
                config = Path(root, 'etc/drlink/config.json')
                config.parent.mkdir(parents=True)
                config.write_text('{"role":"server"}\n')
                with mock.patch.dict(os.environ, {'FRP_DEPLOY_TEST_ROOT': root,
                                                 'DRLINK_CONFIRM': 'yes'}):
                    deleting = ControlPlane(root)
                    concurrent = ControlPlane(root)
                    try:
                        if kind == 'network':
                            v24.set_network_object(deleting, 'target', type='ip',
                                                   value='203.0.113.19', oneshot=True)
                            add_reference = lambda: v24.set_network_group(
                                concurrent, 'retained', members=['target'], oneshot=True)
                            delete = lambda: deleting.unset_object('target', confirm=True)
                            table, members, ref_column = 'objects', 'object_group_members', 'member_id'
                        else:
                            v24.set_service_object(deleting, 'target', type='tcp',
                                                   port=2222, oneshot=True)
                            add_reference = lambda: v24.set_service_group(
                                concurrent, 'retained', members=['target'], oneshot=True)
                            delete = lambda: v24.unset_service_object(deleting, 'target', confirm=True)
                            table, members, ref_column = 'service_objects', 'service_group_members', 'service_object_id'
                        original_mutate = deleting._mutate

                        def competing_write_then_delete(*args, **kwargs):
                            add_reference()
                            return original_mutate(*args, **kwargs)

                        with mock.patch.object(deleting, '_mutate', side_effect=competing_write_then_delete):
                            with self.assertRaisesRegex(ControlPlaneError, '(?i)referenc'):
                                delete()
                        obj = deleting.conn.execute('SELECT id FROM '+table+' WHERE name=?', ('target',)).fetchone()
                        self.assertIsNotNone(obj)
                        self.assertIsNotNone(deleting.conn.execute(
                            'SELECT 1 FROM '+members+' WHERE '+ref_column+'=?', (obj['id'],)).fetchone())
                    finally:
                        concurrent.close()
                        deleting.close()


if __name__ == '__main__':
    unittest.main()
