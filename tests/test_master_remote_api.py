import json
import subprocess
import unittest
from unittest.mock import patch

from mod_nailong.tools.master_git_remote import json_api


class RemoteMetadataReadTests(unittest.TestCase):
    def test_transient_transport_retries_the_identical_read(self):
        failures=[subprocess.CalledProcessError(1,['gh'],stderr='net/http: TLS handshake timeout'),
                  subprocess.CalledProcessError(1,['gh'],stderr='unexpected end of JSON input')]
        with patch('mod_nailong.tools.master_git_remote.subprocess.check_output',side_effect=failures+['{"tree":[],"truncated":false}']) as run,patch('mod_nailong.tools.master_git_remote.time.sleep') as sleep:
            self.assertEqual(json_api('repos/example/git/trees/fixed'),{'tree':[],'truncated':False})
            self.assertEqual(run.call_count,3)
            self.assertEqual(run.call_args_list[0],run.call_args_list[1])
            self.assertEqual(run.call_args_list[1],run.call_args_list[2])
            self.assertEqual([c.args for c in sleep.call_args_list],[(2,),(5,)])

    def test_authorization_failure_is_not_retried(self):
        error=subprocess.CalledProcessError(1,['gh'],stderr='HTTP 403: Resource not accessible')
        with patch('mod_nailong.tools.master_git_remote.subprocess.check_output',side_effect=error) as run,patch('mod_nailong.tools.master_git_remote.time.sleep') as sleep:
            with self.assertRaises(subprocess.CalledProcessError) as caught:json_api('repos/example/git/trees/fixed')
            self.assertIn('HTTP 403: Resource not accessible',' '.join(caught.exception.__notes__))
            self.assertEqual(run.call_count,1);sleep.assert_not_called()

    def test_persistent_transport_failure_has_three_attempt_bound(self):
        error=subprocess.TimeoutExpired(['gh'],180)
        with patch('mod_nailong.tools.master_git_remote.subprocess.check_output',side_effect=error) as run,patch('mod_nailong.tools.master_git_remote.time.sleep') as sleep:
            with self.assertRaises(subprocess.TimeoutExpired):json_api('repos/example/git/trees/fixed')
            self.assertEqual(run.call_count,3);self.assertEqual(sleep.call_count,2)

    def test_successful_command_with_invalid_json_surfaces_immediately(self):
        with patch('mod_nailong.tools.master_git_remote.subprocess.check_output',return_value='{') as run,patch('mod_nailong.tools.master_git_remote.time.sleep') as sleep:
            with self.assertRaises(json.JSONDecodeError):json_api('repos/example/git/trees/fixed')
            self.assertEqual(run.call_count,1);sleep.assert_not_called()

    def test_error_diagnostics_redact_credential_shapes(self):
        error=subprocess.CalledProcessError(1,['gh'],stderr='HTTP 403 Bearer private-value ghp_sensitive123 github_pat_secret456')
        with patch('mod_nailong.tools.master_git_remote.subprocess.check_output',side_effect=error):
            with self.assertRaises(subprocess.CalledProcessError) as caught:json_api('repos/example/git/trees/fixed')
        notes=' '.join(caught.exception.__notes__)
        for secret in ['private-value','ghp_sensitive123','github_pat_secret456']:self.assertNotIn(secret,notes)
        self.assertIn('HTTP 403',notes)


if __name__=='__main__':unittest.main()
