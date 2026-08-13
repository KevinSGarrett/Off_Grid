from __future__ import annotations

import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / 'scripts'))

from packlib import (  # noqa: E402
    MANDATORY_CUMULATIVE, MANDATORY_HYDRATION, collect_repo_files,
    parse_checksum_text, verify_zip,
)


class PackProtocolTests(unittest.TestCase):
    def test_private_source_files_are_collectable_but_generated_zips_are_excluded(self):
        files = {p.as_posix() for p in collect_repo_files(REPO)}
        self.assertIn('context/private_source_documents/Stafford-Technology-Campus-Phases-3-4.pdf', files)
        self.assertIn('context/private_source_documents/EE-Reed-Construction-Houston-HQ.pdf', files)
        self.assertFalse(any(x.endswith('.zip') for x in files))

    def test_stale_generated_pack_metadata_is_not_treated_as_source_payload(self):
        files = {p.as_posix() for p in collect_repo_files(REPO)}
        for name in {
            'PACK_MANIFEST.json', 'PACK_FILE_TREE.txt', 'PACK_CHECKSUMS.sha256',
            'PACK_BUILD_INFO.json', 'CUMULATIVE_INTEGRITY_REPORT.md',
        }:
            self.assertNotIn(name, files)

    def test_checksum_parser(self):
        parsed = parse_checksum_text('abc  a.txt\ndef  nested/b.txt\n')
        self.assertEqual({'a.txt': 'abc', 'nested/b.txt': 'def'}, parsed)

    def test_mandatory_sets_contain_control_files(self):
        self.assertIn('PACK_MANIFEST.json', MANDATORY_CUMULATIVE)
        self.assertIn('PACK_STATE.json', MANDATORY_HYDRATION)
        self.assertIn('REHYDRATION_PROMPT.md', MANDATORY_HYDRATION)

    def test_bad_zip_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / 'bad.zip'
            p.write_bytes(b'not-a-zip')
            report = verify_zip(p)
            self.assertFalse(report['pass'])

    def test_unknown_empty_zip_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / 'empty.zip'
            with zipfile.ZipFile(p, 'w'):
                pass
            report = verify_zip(p)
            self.assertFalse(report['pass'])


if __name__ == '__main__':
    unittest.main()
