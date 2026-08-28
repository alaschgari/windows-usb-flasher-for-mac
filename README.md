# Windows USB Flasher

*[Deutsch](#deutsch) | [English](#english)*

The GUI itself is bilingual — switch between German and English anytime via
the language dropdown in the top-right corner of the app.
Die GUI selbst ist zweisprachig — die Sprache lässt sich jederzeit über das
Dropdown oben rechts umschalten.

---

## Deutsch

Ein grafisches Tool (Python/tkinter) für macOS, mit dem sich aus einer
Windows-ISO-Datei ein bootfähiger USB-Installationsstick erstellen lässt.

### Das Problem

Windows-ISOs lassen sich auf dem Mac nicht einfach 1:1 (byte-für-byte, wie
z. B. mit balenaEtcher) auf einen USB-Stick kopieren. Der Grund: Moderne
Windows-ISOs enthalten eine `install.wim`-Datei, die oft größer als 4 GB
ist. Für UEFI-Boot wird der USB-Stick jedoch mit FAT32 formatiert — und
FAT32 unterstützt keine Dateien über 4 GB.

### Die Lösung

Dieses Tool automatisiert den kompletten Workaround:

1. **Formatieren** — der USB-Stick wird mit GPT-Partitionstabelle und
   FAT32-Dateisystem (Name `WINSETUP`) formatiert.
2. **ISO mounten** — die ausgewählte ISO wird per `hdiutil` eingebunden.
3. **Kopieren** — alle Dateien und Ordner aus der ISO werden per `rsync`
   auf den Stick kopiert, **außer** `sources/install.wim`.
4. **Splitten** — `install.wim` wird mit `wimlib-imagex` in mehrere
   Teile < 4 GB (`install.swm`, `install2.swm`, …) zerlegt und direkt auf
   den Stick geschrieben. Der Windows-Installer kann Multi-Part-WIM-Dateien
   nativ lesen.
5. **Verifizieren** — die gesplitteten WIM-Dateien werden automatisch mit
   `wimlib-imagex info` auf Konsistenz geprüft.
6. **Auswerfen** — ISO und USB-Stick werden sauber ausgeworfen.

### Voraussetzungen

- macOS
- Python 3 mit tkinter (bei den meisten macOS-Python-Installationen bereits
  enthalten)
- [Homebrew](https://brew.sh) sowie das Paket `wimlib`:

  ```bash
  brew install wimlib
  ```

  Dies stellt das Kommandozeilen-Tool `wimlib-imagex` bereit, das für den
  Split-Schritt benötigt wird. Das Tool prüft diese Voraussetzung beim
  Start und zeigt andernfalls eine entsprechende Fehlermeldung an.

### Verwendung

```bash
python3 windows_usb_flasher.py
```

In der GUI:

0. Oben rechts bei Bedarf die Sprache auf „English" umstellen.
1. Windows-ISO-Datei über „Durchsuchen…" auswählen.
2. Ziel-USB-Stick aus der Dropdown-Liste wählen (nur externe, entfernbare
   Datenträger werden angezeigt; „Aktualisieren" lädt die Liste neu).
3. Auf „USB-Stick erstellen" klicken und die Sicherheitsabfrage bestätigen.
4. Fortschritt und Status im Log-Fenster verfolgen. Über „Abbrechen" lässt
   sich der Vorgang zwischen den einzelnen Schritten stoppen (ein bereits
   laufender Kopier-/Split-Befehl wird dabei zu Ende geführt, bevor der
   Abbruch greift).

### ⚠️ Achtung

Beim Formatieren werden **alle Daten auf dem gewählten USB-Stick
unwiderruflich gelöscht**. Vor dem Start erscheint eine Sicherheitsabfrage
— bitte den gewählten Datenträger sorgfältig prüfen.

### Manuelle Überprüfung des fertigen Sticks

Nach dem Flash-Vorgang lässt sich der Stick zusätzlich manuell prüfen:

```bash
# Struktur/Inhalt
ls -la /Volumes/WINSETUP/
ls -la /Volumes/WINSETUP/sources/

# Partitionsschema (sollte GUID_partition_scheme / GPT sein)
diskutil list /dev/diskN

# Integrität der gesplitteten WIM-Dateien
wimlib-imagex info /Volumes/WINSETUP/sources/install.swm
```

Der zuverlässigste Test bleibt jedoch der reale Boot-Versuch an einem PC
oder in einer UEFI-fähigen VM.

### Tests

```bash
python3 -m unittest discover -s tests -v
```

Deckt die reinen Hilfsfunktionen ab (Parsing, Speicherplatz-Berechnung,
Volume-Erkennung); die tkinter-GUI selbst wird nicht automatisiert getestet.

### Eigenständige macOS-App bauen (optional)

Mit [py2app](https://py2app.readthedocs.io/) lässt sich ein `.app`-Bundle
zum Doppelklick-Start erzeugen:

```bash
pip3 install py2app
python3 setup.py py2app
```

Die fertige App liegt danach in `dist/Windows USB Flasher.app`.

### Lizenz

MIT-Lizenz, siehe [LICENSE](LICENSE).

---

## English

A graphical tool (Python/tkinter) for macOS that creates a bootable
Windows installation USB stick from a Windows ISO file.

### The Problem

On a Mac, Windows ISOs can't simply be copied 1:1 (byte-for-byte, e.g.
with balenaEtcher) to a USB stick. The reason: modern Windows ISOs contain
an `install.wim` file that is often larger than 4 GB. For UEFI boot,
though, the USB stick needs to be formatted as FAT32 — and FAT32 doesn't
support files over 4 GB.

### The Solution

This tool automates the full workaround:

1. **Format** — the USB stick is formatted with a GPT partition table and
   a FAT32 file system (name `WINSETUP`).
2. **Mount ISO** — the selected ISO is mounted via `hdiutil`.
3. **Copy** — all files and folders from the ISO are copied to the stick
   via `rsync`, **except** `sources/install.wim`.
4. **Split** — `install.wim` is split into multiple parts < 4 GB
   (`install.swm`, `install2.swm`, …) with `wimlib-imagex` and written
   directly to the stick. The Windows installer natively reads
   multi-part WIM files.
5. **Verify** — the split WIM files are automatically checked for
   consistency with `wimlib-imagex info`.
6. **Eject** — the ISO and the USB stick are cleanly ejected.

### Requirements

- macOS
- Python 3 with tkinter (included with most macOS Python installations)
- [Homebrew](https://brew.sh) and the `wimlib` package:

  ```bash
  brew install wimlib
  ```

  This provides the `wimlib-imagex` command line tool needed for the
  split step. The app checks for this requirement on startup and shows
  an error message if it's missing.

### Usage

```bash
python3 windows_usb_flasher.py
```

In the GUI:

0. Switch the language to "English" in the top-right corner if needed.
1. Select the Windows ISO file via "Browse…".
2. Select the target USB stick from the dropdown list (only external,
   removable drives are shown; "Refresh" reloads the list).
3. Click "Create USB Stick" and confirm the safety prompt.
4. Follow progress and status in the log window. Click "Cancel" to stop the
   process between steps (a command that's already running, like copying
   or splitting, will finish first before the cancellation takes effect).

### ⚠️ Warning

Formatting **permanently erases all data on the selected USB stick**. A
safety confirmation appears before the process starts — please double
check the selected drive.

### Manually verifying the finished stick

After flashing, the stick can also be checked manually:

```bash
# Structure/contents
ls -la /Volumes/WINSETUP/
ls -la /Volumes/WINSETUP/sources/

# Partition scheme (should be GUID_partition_scheme / GPT)
diskutil list /dev/diskN

# Integrity of the split WIM files
wimlib-imagex info /Volumes/WINSETUP/sources/install.swm
```

The most reliable test, however, remains an actual boot attempt on a PC
or in a UEFI-capable VM.

### Tests

```bash
python3 -m unittest discover -s tests -v
```

Covers the pure helper functions (parsing, free-space calculation, volume
detection); the tkinter GUI itself is not covered by automated tests.

### Building a standalone macOS app (optional)

You can build a double-clickable `.app` bundle with
[py2app](https://py2app.readthedocs.io/):

```bash
pip3 install py2app
python3 setup.py py2app
```

The resulting app is created at `dist/Windows USB Flasher.app`.

### License

MIT License, see [LICENSE](LICENSE).
