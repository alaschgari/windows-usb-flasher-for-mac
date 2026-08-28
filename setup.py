"""
[DE] py2app-Buildskript, um windows_usb_flasher.py als eigenständige
macOS-App (.app) zu paketieren.
[EN] py2app build script to package windows_usb_flasher.py as a
standalone macOS .app bundle.

Usage / Verwendung:
    pip3 install py2app
    python3 setup.py py2app

The resulting .app is created in dist/. / Die fertige .app liegt in dist/.
"""

from setuptools import setup

APP = ["windows_usb_flasher.py"]
OPTIONS = {
    "argv_emulation": False,
    "plist": {
        "CFBundleName": "Windows USB Flasher",
        "CFBundleDisplayName": "Windows USB Flasher",
        "CFBundleIdentifier": "com.alaschgari.windowsusbflasher",
        "NSHumanReadableCopyright": "MIT License",
    },
}

setup(
    app=APP,
    options={"py2app": OPTIONS},
    setup_requires=["py2app"],
)
