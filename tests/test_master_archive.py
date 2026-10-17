"""Round trips protect the generated master bytes, rather than a ZIP layout."""
import hashlib
import io
import tempfile
import unittest
import zipfile
from pathlib import Path

from mod_nailong.tools.master_archive import StoredZip


class MasterArchiveTests(unittest.TestCase):
    def test_original_bytes_roundtrip_and_repeated_stream_identity(self):
        original = bytes(range(256)) * 8193
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "source.png"
            path.write_bytes(original)
            digest = hashlib.sha256(original).hexdigest()
            archive = StoredZip([("png/" + digest + ".png", path, digest), ("index.json", b"{}\n", hashlib.sha256(b"{}\n").hexdigest())])
            first = b"".join(archive)
            self.assertEqual(len(first), len(archive))
            self.assertEqual(hashlib.sha256(first).hexdigest(), archive.sha256)
            self.assertEqual(first, b"".join(archive))
            with zipfile.ZipFile(io.BytesIO(first)) as reader:
                self.assertIsNone(reader.testzip())
                self.assertEqual(original, reader.read("png/" + digest + ".png"))
                self.assertEqual(b"{}\n", reader.read("index.json"))

    def test_changed_source_cannot_be_archived_under_old_sha(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "source.png"
            path.write_bytes(b"original")
            digest = hashlib.sha256(b"original").hexdigest()
            archive = StoredZip([("master.png", path, digest)])
            path.write_bytes(b"modified")
            with self.assertRaisesRegex(ValueError, "changed during"):
                b"".join(archive)
            with self.assertRaisesRegex(ValueError, "changed before"):
                StoredZip([("master.png", path, digest)])


if __name__ == "__main__":
    unittest.main()
