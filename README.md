# Windows USB Flasher

Ein grafisches Tool (Python/tkinter) für macOS, mit dem sich aus einer
Windows-ISO-Datei ein bootfähiger USB-Installationsstick erstellen lässt.

## Das Problem

Windows-ISOs lassen sich auf dem Mac nicht einfach 1:1 (byte-für-byte, wie
z. B. mit balenaEtcher) auf einen USB-Stick kopieren. Der Grund: Moderne
Windows-ISOs enthalten eine `install.wim`-Datei, die oft größer als 4 GB
ist. Für UEFI-Boot wird der USB-Stick jedoch mit FAT32 formatiert — und
FAT32 unterstützt keine Dateien über 4 GB.

## Die Lösung

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

## Voraussetzungen

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

## Verwendung

```bash
python3 windows_usb_flasher.py
```

In der GUI:

1. Windows-ISO-Datei über „Durchsuchen…" auswählen.
2. Ziel-USB-Stick aus der Dropdown-Liste wählen (nur externe, entfernbare
   Datenträger werden angezeigt; „Aktualisieren" lädt die Liste neu).
3. Auf „USB-Stick erstellen" klicken und die Sicherheitsabfrage bestätigen.
4. Fortschritt und Status im Log-Fenster verfolgen.

## ⚠️ Achtung

Beim Formatieren werden **alle Daten auf dem gewählten USB-Stick
unwiderruflich gelöscht**. Vor dem Start erscheint eine Sicherheitsabfrage
— bitte den gewählten Datenträger sorgfältig prüfen.

## Manuelle Überprüfung des fertigen Sticks

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

## Lizenz

Privates Projekt, keine Lizenzangabe.
