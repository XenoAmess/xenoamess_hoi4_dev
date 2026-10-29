import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from runtime import high131_exact_api_publish as publish


BASE = "cb1040af1c6f6af21235246c6dc28cd6687595bb"
TARGET = "a23980233e210e837e5ddb03f064ad4c09a4f5bd"


class FakeApi:
    def __init__(self, remote=BASE, mismatch_tree=False, comparison="behind"):
        self.remote = remote
        self.mismatch_tree = mismatch_tree
        self.comparison = comparison
        self.posts = []
        self.patches = []

    def get_json(self, endpoint, expected_sha=None):
        if endpoint == "git/ref/heads/master":
            return {"object": {"sha": self.remote}}
        if endpoint == "rate_limit":
            return {"resources": {"core": {"remaining": 5000}}}
        if endpoint.startswith("compare/"):
            return {"status": self.comparison}
        raise AssertionError(endpoint)

    def get_optional(self, endpoint, expected_sha=None):
        return None

    def post_json(self, endpoint, payload, expected_sha):
        self.posts.append((endpoint, payload, expected_sha))
        return {"sha": "0" * 40 if endpoint == "git/trees" and self.mismatch_tree else expected_sha}

    def request(self, endpoint, method, payload, timeout):
        return self.runner(publish.api_endpoint(endpoint), method, payload, timeout)

    def runner(self, endpoint, method, payload, timeout):
        if endpoint == "repos/XenoAmess/xenoamess_hoi4_dev/git/refs/heads/master" and method == "PATCH":
            self.patches.append(payload)
            self.remote = TARGET
            return {"ref": "refs/heads/master", "object": {"sha": TARGET}}
        raise AssertionError((endpoint, method))


class NullLock:
    def __init__(self, batch, target):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class ExactApiPublishTests(unittest.TestCase):
    def publish(self, api, scope="import"):
        with tempfile.TemporaryDirectory(dir=publish.ROOT / "runtime") as directory, patch.object(publish, "PublishLock", NullLock):
            publisher = publish.ExactApiPublisher(BASE, TARGET, scope, "fixture", api=api, receipt_path=Path(directory) / "receipt.json")
            return publisher.publish()

    def test_exact_objects_and_non_forced_fast_forward(self):
        api = FakeApi()
        result = self.publish(api)
        self.assertEqual(result["status"], "published_pending_original_readback")
        self.assertTrue(result["ref_updated"])
        self.assertEqual(result["remote_master_observed"], TARGET)
        self.assertEqual(api.patches, [{"sha": TARGET, "force": False}])
        details = publish.commit_details(TARGET)
        commit_call = [call for call in api.posts if call[0] == "git/commits"][-1][1]
        self.assertEqual(commit_call["message"], details["message"])
        self.assertEqual(commit_call["tree"], details["tree"])
        self.assertEqual(commit_call["parents"], [details["parent"]])
        self.assertEqual(commit_call["author"], details["author"])
        self.assertEqual(commit_call["committer"], details["committer"])
        tree_call = [call for call in api.posts if call[0] == "git/trees"][-1]
        self.assertEqual(tree_call[1]["base_tree"], details["base_tree"])
        for entry in tree_call[1]["tree"]:
            if entry["path"].endswith(".json"):
                self.assertNotIn("sha", entry)
                self.assertEqual(entry["content"], publish.git_bytes("show", TARGET + ":" + entry["path"]).decode("utf-8"))
            else:
                self.assertNotIn("content", entry)
        self.assertEqual(tree_call[2], details["tree"])

    def test_sha_mismatch_never_updates_reference(self):
        api = FakeApi(mismatch_tree=True)
        with self.assertRaises(publish.ExactPublishError):
            self.publish(api)
        self.assertEqual(api.patches, [])

    def test_diverged_remote_and_already_public_do_not_upload_or_overwrite(self):
        api = FakeApi(remote="1" * 40, comparison="diverged")
        with self.assertRaises(publish.ExactPublishError):
            self.publish(api)
        self.assertEqual(api.posts, [])
        self.assertEqual(api.patches, [])
        api = FakeApi(remote=TARGET)
        result = self.publish(api)
        self.assertEqual(result["status"], "already_public_pending_original_readback")
        self.assertFalse(result["ref_updated"])
        self.assertEqual(api.posts, [])
        self.assertEqual(api.patches, [])

    def test_transient_creation_failure_recovers_by_content_sha_only(self):
        expected = "a" * 40
        calls = []
        def runner(endpoint, method, payload, timeout):
            calls.append((endpoint, method))
            if method == "POST" and sum(item[1] == "POST" for item in calls) == 1:
                raise publish.ApiError("TLS handshake timeout", transient=True)
            if method == "GET" and endpoint == "repos/XenoAmess/xenoamess_hoi4_dev/git/blobs/" + expected:
                return {"sha": expected}
            raise AssertionError((endpoint, method))
        with patch.object(publish.time, "sleep"):
            result = publish.Api(runner).post_json("git/blobs", {"content": "YQ==", "encoding": "base64"}, expected)
        self.assertEqual(result["sha"], expected)
        self.assertEqual(calls, [("repos/XenoAmess/xenoamess_hoi4_dev/git/blobs", "POST"), ("repos/XenoAmess/xenoamess_hoi4_dev/git/blobs/" + expected, "GET")])
        calls = []
        def forbidden(endpoint, method, payload, timeout):
            calls.append((endpoint, method))
            raise publish.ApiError("HTTP 403", transient=False, status=403)
        with self.assertRaises(publish.ApiError):
            publish.Api(forbidden).post_json("git/blobs", {}, expected)
        self.assertEqual(len(calls), 1)

    def test_forcibly_closed_connection_is_retried_with_repository_path(self):
        responses = [
            publish.subprocess.CompletedProcess([], 1, stdout=b"", stderr=b"wsarecv: An existing connection was forcibly closed by the remote host."),
            publish.subprocess.CompletedProcess([], 7, stdout=b"", stderr=b"curl: (7) Failed to connect to 127.0.0.1 port 10808: Could not connect to server"),
            publish.subprocess.CompletedProcess([], 0, stdout=b'{"object":{"sha":"' + b"c" * 40 + b'"}}', stderr=b""),
        ]
        with patch.object(publish.subprocess, "run", side_effect=responses) as run, patch.object(publish.time, "sleep") as sleep:
            body = publish.Api(token="fixturetoken").get_json("git/ref/heads/master")
        self.assertEqual(body["object"]["sha"], "c" * 40)
        self.assertEqual(run.call_count, 3)
        sleep.assert_called_once_with(5)
        self.assertEqual(run.call_args_list[0].args[0][2], "repos/XenoAmess/xenoamess_hoi4_dev/git/ref/heads/master")
        with patch.object(publish.subprocess, "run", return_value=publish.subprocess.CompletedProcess([], 52, stdout=b"", stderr=b"curl: (52) Empty reply from server")):
            with self.assertRaises(publish.ApiError) as caught:
                publish.Api(token="fixturetoken")._run_curl("git/ref/heads/master", "GET", None, 60)
        self.assertTrue(caught.exception.transient)

    def test_curl_credentials_stay_out_of_arguments_and_tls_stays_enabled(self):
        expected = "c" * 40
        calls = []
        def run(arguments, **kwargs):
            calls.append((arguments, kwargs))
            return publish.subprocess.CompletedProcess(arguments, 0, stdout=b'{"sha":"' + expected.encode() + b'"}', stderr=b"")
        with patch.object(publish.subprocess, "run", side_effect=run):
            result = publish.Api(token="fixture-token")._run_curl("git/blobs/" + expected, "GET", None, 120)
        self.assertEqual(result["sha"], expected)
        arguments, kwargs = calls[0]
        self.assertNotIn("fixture-token", " ".join(arguments))
        self.assertIn(b"fixture-token", kwargs["input"])
        self.assertNotIn("--insecure", arguments)
        self.assertIn("api.github.com:443:140.82.113.6", arguments)
        self.assertEqual(arguments[arguments.index("--connect-timeout") + 1], "60")
        self.assertEqual(kwargs["env"]["HTTPS_PROXY"], "http://127.0.0.1:10808")
        self.assertEqual(arguments[-2:], ["--config", "-"])

    def test_only_transient_failure_switches_to_verified_curl_transport(self):
        calls = []
        def curl(endpoint, method, payload, timeout):
            calls.append((endpoint, method))
            return {"object": {"sha": "c" * 40}}
        api = publish.Api(token="fixture-token", curl_runner=curl)
        def failed(*args):
            raise publish.ApiError("TLS handshake timeout", transient=True)
        api.runner = failed
        result = api.request("git/ref/heads/master", "GET", None, 120)
        self.assertEqual(result["object"]["sha"], "c" * 40)
        self.assertEqual(calls, [("repos/XenoAmess/xenoamess_hoi4_dev/git/ref/heads/master", "GET")])
        def forbidden(*args):
            raise publish.ApiError("HTTP 403", transient=False, status=403)
        api.runner = forbidden
        with self.assertRaises(publish.ApiError):
            api.request("git/ref/heads/master", "GET", None, 120)
        self.assertEqual(len(calls), 1)

    def test_github_cli_bytes_are_decoded_before_validation(self):
        with patch.object(publish.subprocess, "check_output", return_value=b"fixturetoken\n"):
            token = publish.Api().github_token()
        self.assertEqual(token, "fixturetoken")
        self.assertIsInstance(token, str)

    def test_expected_base_does_not_compare_an_unpublished_target(self):
        publisher = object.__new__(publish.ExactApiPublisher)
        publisher.base, publisher.target = BASE, TARGET
        api = FakeApi()
        publisher.api = api
        with patch.object(api, "get_json", side_effect=AssertionError("Unexpected comparison")):
            self.assertTrue(publisher.require_publication_parent(BASE))
        with patch.object(api, "get_json", side_effect=publish.ApiError("HTTP 404", status=404)):
            self.assertFalse(publisher.remote_contains("1" * 40))

    def test_existing_blob_is_reused_and_checkpointed(self):
        change = publish.commit_details(TARGET)["changes"][0]
        publisher = object.__new__(publish.ExactApiPublisher)
        api = FakeApi()
        publisher.api = api
        publisher.known_blobs = set()
        publisher.receipt = {}
        with tempfile.TemporaryDirectory(dir=publish.ROOT / "runtime") as directory:
            publisher.receipt_path = Path(directory) / "receipt.json"
            with patch.object(api, "get_optional", return_value={"sha": change["sha"]}):
                publisher.ensure_blob(TARGET, change)
        self.assertEqual(api.posts, [])
        self.assertEqual(publisher.known_blobs, {change["sha"]})
        self.assertEqual(publisher.receipt["verified_blob_shas"], [change["sha"]])

    def test_resume_uses_only_matching_checkpoint_blobs(self):
        details = publish.commit_details(TARGET)
        first, second = (row["sha"] for row in details["changes"][:2])
        previous = {"schema": "high131-exact-api-publish-v1", "machine_id": publish.machine_id(),
                    "base_commit": BASE, "target_commit": TARGET, "scope": "import",
                    "verified_blob_shas": [first, "f" * 40, "invalid"], "last_blob_sha": second}
        with tempfile.TemporaryDirectory(dir=publish.ROOT / "runtime") as directory:
            path = Path(directory) / "receipt.json"
            publish.write_json(path, previous)
            publisher = publish.ExactApiPublisher(BASE, TARGET, "import", "fixture", api=FakeApi(), receipt_path=path)
        self.assertEqual(publisher.known_blobs, {first, second})
        self.assertEqual(publisher.receipt["verified_blob_shas"], sorted(publisher.known_blobs))

    def test_unexpected_path_or_deletion_is_rejected_before_upload(self):
        detail = {"commit": TARGET, "parent": BASE, "changes": [{"path": "../secret", "mode": "100644", "type": "blob", "sha": "a" * 40}]}
        with patch.object(publish, "commit_details", return_value=detail), patch.object(publish, "git_text", return_value=TARGET):
            with self.assertRaises(publish.ExactPublishError):
                publish.ExactApiPublisher(BASE, TARGET, "delivery", "fixture")
        def raw(*args, input_bytes=None):
            if args[:2] == ("cat-file", "-p"):
                return b"tree 1234\nparent 5678\nauthor A <a@b> 1 +0000\ncommitter A <a@b> 1 +0000\n\nmessage\n"
            if args[0] == "diff-tree":
                return b":100644 100644 " + b"a" * 40 + b" " + b"b" * 40 + b" D\0mod_nailong/data/generated.json\0"
            return b"1234"
        with patch.object(publish, "git_bytes", side_effect=raw):
            with self.assertRaisesRegex(publish.ExactPublishError, "deletion"):
                publish.commit_details(TARGET)


if __name__ == "__main__":
    unittest.main()
