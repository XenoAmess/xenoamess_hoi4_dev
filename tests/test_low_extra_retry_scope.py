import unittest
from tools.common import read_json,write_json,file_sha256
from mod_nailong.tools import image_retries as retries
from tests import test_source_scoped_retry_round as fixtures


class LowExtraRetryScopeTests(unittest.TestCase):
    setUp=fixtures.SourceScopedRetryRoundTests.setUp
    authorize=fixtures.SourceScopedRetryRoundTests.authorize

    def test_variable_scope_still_requires_exact_authorized_source_count(self):
        settings,manifest=self.authorize(count=7)
        frozen=read_json(manifest);frozen['source_count']=9;write_json(manifest,frozen)
        settings['source_scoped_extra_retry_rounds'][0]['authorization_manifest_sha256']=file_sha256(manifest)
        write_json(self.mod/'data/image-retry-policy.json',settings)
        with self.assertRaises(AssertionError):retries.policy()


if __name__=='__main__':unittest.main()
