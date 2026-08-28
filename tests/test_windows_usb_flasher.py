"""
[DE] Unit-Tests für die reinen Hilfsfunktionen (kein echtes diskutil/hdiutil
nötig, alles wird gemockt). Deckt keine tkinter-GUI ab.
[EN] Unit tests for the pure helper functions (no real diskutil/hdiutil
needed, everything is mocked). Does not cover the tkinter GUI.
"""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import windows_usb_flasher as app  # noqa: E402


class FormatSizeTests(unittest.TestCase):
    def test_zero_bytes(self):
        self.assertEqual(app._format_size(0), "0.0 GB")

    def test_one_gb(self):
        self.assertEqual(app._format_size(1_000_000_000), "1.0 GB")

    def test_fractional_gb(self):
        self.assertEqual(app._format_size(15_500_000_000), "15.5 GB")


class TextFallbackParserTests(unittest.TestCase):
    SAMPLE_OUTPUT = (
        "/dev/disk4 (external, physical):\n"
        "   #:                       TYPE NAME                    SIZE       IDENTIFIER\n"
        "   0:     GUID_partition_scheme                        *15.5 GB    disk4\n"
    )

    @patch("subprocess.run")
    def test_parses_disk_identifier_and_size(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout=self.SAMPLE_OUTPUT)
        disks = app._list_removable_disks_text_fallback(usb_label="USB Drive")
        self.assertEqual(len(disks), 1)
        self.assertEqual(disks[0]["identifier"], "disk4")
        self.assertEqual(disks[0]["size"], "15.5 GB")
        self.assertEqual(disks[0]["name"], "USB Drive")

    @patch("subprocess.run")
    def test_no_disks_found(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="")
        disks = app._list_removable_disks_text_fallback()
        self.assertEqual(disks, [])

    @patch("subprocess.run")
    def test_command_failure_returns_empty_list(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stdout="")
        disks = app._list_removable_disks_text_fallback()
        self.assertEqual(disks, [])


class FindVolumeMountPointTests(unittest.TestCase):
    @patch("subprocess.run")
    def test_finds_matching_volume(self, mock_run):
        import plistlib

        list_plist = plistlib.dumps({
            "AllDisksAndPartitions": [
                {"Partitions": [{"DeviceIdentifier": "disk4s1"}]}
            ]
        })
        info_plist = plistlib.dumps({
            "VolumeName": "WINSETUP",
            "MountPoint": "/Volumes/WINSETUP",
        })
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout=list_plist.decode("utf-8")),
            MagicMock(returncode=0, stdout=info_plist.decode("utf-8")),
        ]
        result = app.find_volume_mount_point("disk4", "WINSETUP")
        self.assertEqual(result, "/Volumes/WINSETUP")

    @patch("subprocess.run")
    def test_returns_none_when_no_match(self, mock_run):
        import plistlib

        list_plist = plistlib.dumps({
            "AllDisksAndPartitions": [
                {"Partitions": [{"DeviceIdentifier": "disk4s1"}]}
            ]
        })
        info_plist = plistlib.dumps({
            "VolumeName": "SOMETHING_ELSE",
            "MountPoint": "/Volumes/SOMETHING_ELSE",
        })
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout=list_plist.decode("utf-8")),
            MagicMock(returncode=0, stdout=info_plist.decode("utf-8")),
        ]
        result = app.find_volume_mount_point("disk4", "WINSETUP")
        self.assertIsNone(result)

    @patch("subprocess.run")
    def test_returns_none_on_command_failure(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stdout="")
        result = app.find_volume_mount_point("disk4", "WINSETUP")
        self.assertIsNone(result)


class GetFreeSpaceBytesTests(unittest.TestCase):
    @patch("os.statvfs")
    def test_computes_bytes_from_statvfs(self, mock_statvfs):
        mock_statvfs.return_value = MagicMock(f_bavail=1000, f_frsize=4096)
        result = app.get_free_space_bytes("/Volumes/WINSETUP")
        self.assertEqual(result, 1000 * 4096)


class CheckWimlibInstalledTests(unittest.TestCase):
    @patch("shutil.which", return_value="/opt/homebrew/bin/wimlib-imagex")
    def test_returns_true_when_found(self, _mock_which):
        self.assertTrue(app.check_wimlib_installed())

    @patch("shutil.which", return_value=None)
    def test_returns_false_when_missing(self, _mock_which):
        self.assertFalse(app.check_wimlib_installed())


if __name__ == "__main__":
    unittest.main()
