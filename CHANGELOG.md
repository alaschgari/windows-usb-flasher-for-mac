# Changelog

## Unreleased

- Add "Download ISO…" button that opens the official Microsoft Windows ISO
  download page in the browser.
- Add MIT license.
- Set repository description and topics for GitHub search discoverability.
- Fix: determine the actual mount path of the formatted `WINSETUP` volume
  instead of assuming `/Volumes/WINSETUP` (avoids writing to the wrong
  volume if the name was already taken by another mounted disk).
- Add a free-space check before copying, comparing the ISO size against
  available space on the USB stick.
- Add a "Cancel" button to stop the flashing process between steps.
- Add unit tests for the pure helper functions (`tests/`).
- Add GitHub Actions CI workflow (compile check + unit tests).
- Add `.gitignore`.

## 1.0.0 — Initial release

- Bilingual (DE/EN) GUI to create a bootable Windows installation USB stick
  on macOS from a Windows ISO, working around the `install.wim` > 4 GB /
  FAT32 limitation via `wimlib-imagex` split.
