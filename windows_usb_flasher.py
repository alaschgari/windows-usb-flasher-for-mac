#!/usr/bin/env python3
"""
Windows USB Flasher für macOS
==============================

Erstellt einen bootfähigen Windows-Installations-USB-Stick aus einer
Windows-ISO-Datei. Löst das Problem, dass eine Windows-ISO auf dem Mac
nicht einfach 1:1 (byte-für-byte, wie bei balenaEtcher) auf einen USB-Stick
kopiert werden kann, weil moderne Windows-ISOs eine `install.wim`-Datei
enthalten, die größer als 4 GB sein kann und damit nicht auf ein
FAT32-Dateisystem passt (FAT32 ist aber für UEFI-Boot erforderlich).

Die Lösung:
  1. USB-Stick mit GPT-Partitionstabelle und FAT32 formatieren.
  2. ISO mounten.
  3. Alle Dateien AUSSER install.wim per rsync auf den Stick kopieren.
  4. install.wim mit wimlib-imagex in mehrere .swm-Dateien < 4 GB splitten
     und direkt auf den Stick schreiben.
  5. ISO und USB-Stick sauber auswerfen.

Voraussetzung:
  - macOS
  - Homebrew-Paket `wimlib` muss installiert sein:
        brew install wimlib
    (stellt das Kommandozeilen-Tool `wimlib-imagex` bereit)

Ausführen:
    python3 windows_usb_flasher.py

Hinweis: Für diskutil-Operationen auf dem Datenträger können Sie zur
Eingabe Ihres macOS-Passworts aufgefordert werden (sudo/Systemdialog).
"""

import os
import re
import shutil
import subprocess
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox


# --------------------------------------------------------------------------
# Hilfsfunktionen (Backend-Logik)
# --------------------------------------------------------------------------

def check_wimlib_installed() -> bool:
    """Prüft, ob wimlib-imagex im PATH verfügbar ist."""
    return shutil.which("wimlib-imagex") is not None


def list_removable_disks():
    """
    Liest `diskutil list` aus und gibt eine Liste von externen,
    entfernbaren (removable) Datenträgern zurück.

    Rückgabe: Liste von Dicts: {"identifier": "disk2", "size": "15.5 GB", "name": "..."}
    """
    result = subprocess.run(
        ["diskutil", "list", "-plist", "external", "physical"],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        # Fallback auf Text-Parsing, falls -plist nicht unterstützt wird
        return _list_removable_disks_text_fallback()

    # plistlib-Parsing der externen physischen Datenträger
    import plistlib
    try:
        data = plistlib.loads(result.stdout.encode("utf-8"))
    except Exception:
        return _list_removable_disks_text_fallback()

    disks = []
    for disk_identifier in data.get("WholeDisks", []):
        info = subprocess.run(
            ["diskutil", "info", "-plist", disk_identifier],
            capture_output=True, text=True
        )
        if info.returncode != 0:
            continue
        try:
            disk_info = plistlib.loads(info.stdout.encode("utf-8"))
        except Exception:
            continue

        removable = disk_info.get("RemovableMedia", False) or disk_info.get("Ejectable", False)
        internal = disk_info.get("Internal", True)

        if removable and not internal:
            size_bytes = disk_info.get("TotalSize", 0)
            size_str = _format_size(size_bytes)
            name = disk_info.get("MediaName", "Unbekannt")
            disks.append({
                "identifier": disk_identifier,
                "size": size_str,
                "name": name,
            })
    return disks


def _list_removable_disks_text_fallback():
    """Einfacher Text-Parser für `diskutil list external physical` als Fallback."""
    result = subprocess.run(
        ["diskutil", "list", "external", "physical"],
        capture_output=True, text=True
    )
    disks = []
    if result.returncode != 0:
        return disks

    current_disk = None
    for line in result.stdout.splitlines():
        m = re.match(r"^/dev/(disk\d+)\s*\(external, physical\):", line)
        if m:
            current_disk = m.group(1)
            continue
        if current_disk and re.match(r"^\s*0:\s+GUID_partition_scheme", line):
            size_match = re.search(r"\*([\d.]+\s*\w+)", line)
            size_str = size_match.group(1) if size_match else "unbekannt"
            disks.append({
                "identifier": current_disk,
                "size": size_str,
                "name": "USB-Datenträger",
            })
            current_disk = None
    return disks


def _format_size(size_bytes: int) -> str:
    """Formatiert Bytes in eine lesbare Größe (GB)."""
    gb = size_bytes / (1000 ** 3)
    return f"{gb:.1f} GB"


# --------------------------------------------------------------------------
# GUI
# --------------------------------------------------------------------------

class WindowsUSBFlasherApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Windows USB Flasher")
        self.root.geometry("640x560")
        self.root.minsize(600, 500)

        self.iso_path = tk.StringVar(value="")
        self.selected_disk = tk.StringVar(value="")
        self.disk_map = {}  # Anzeigetext -> Identifier (z.B. "disk2")

        self._setup_style()
        self._build_ui()

        # Voraussetzung prüfen
        if not check_wimlib_installed():
            self._show_wimlib_missing_error()
        else:
            self.refresh_disks()

    # ---------------------------------------------------------------- UI --

    def _setup_style(self):
        style = ttk.Style()
        try:
            style.theme_use("aqua")
        except tk.TclError:
            style.theme_use(style.theme_names()[0])

        style.configure("Title.TLabel", font=("SF Pro Text", 16, "bold"))
        style.configure("Section.TLabel", font=("SF Pro Text", 12, "bold"))
        style.configure("Big.TButton", font=("SF Pro Text", 13, "bold"), padding=10)

    def _build_ui(self):
        outer = ttk.Frame(self.root, padding=20)
        outer.pack(fill="both", expand=True)

        title = ttk.Label(outer, text="Windows USB Flasher", style="Title.TLabel")
        title.pack(anchor="w", pady=(0, 15))

        # --- ISO-Auswahl ---
        iso_frame = ttk.LabelFrame(outer, text="1. Windows-ISO-Datei", padding=12)
        iso_frame.pack(fill="x", pady=(0, 12))

        iso_row = ttk.Frame(iso_frame)
        iso_row.pack(fill="x")
        self.iso_entry = ttk.Entry(iso_row, textvariable=self.iso_path, state="readonly")
        self.iso_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        ttk.Button(iso_row, text="Durchsuchen…", command=self.select_iso).pack(side="left")

        # --- USB-Auswahl ---
        usb_frame = ttk.LabelFrame(outer, text="2. Ziel-USB-Stick", padding=12)
        usb_frame.pack(fill="x", pady=(0, 12))

        usb_row = ttk.Frame(usb_frame)
        usb_row.pack(fill="x")
        self.disk_combo = ttk.Combobox(usb_row, textvariable=self.selected_disk, state="readonly")
        self.disk_combo.pack(side="left", fill="x", expand=True, padx=(0, 8))
        ttk.Button(usb_row, text="Aktualisieren", command=self.refresh_disks).pack(side="left")

        warn = ttk.Label(
            usb_frame,
            text="⚠️ Alle Daten auf dem gewählten Datenträger werden gelöscht!",
            foreground="#b00020",
        )
        warn.pack(anchor="w", pady=(8, 0))

        # --- Erstellen-Button ---
        self.create_button = ttk.Button(
            outer, text="USB-Stick erstellen", style="Big.TButton",
            command=self.on_create_clicked
        )
        self.create_button.pack(fill="x", pady=(4, 16))

        # --- Fortschritt ---
        progress_frame = ttk.LabelFrame(outer, text="Fortschritt", padding=12)
        progress_frame.pack(fill="both", expand=True)

        self.progress = ttk.Progressbar(progress_frame, mode="determinate", maximum=100)
        self.progress.pack(fill="x", pady=(0, 10))

        self.log_text = tk.Text(progress_frame, height=14, wrap="word", state="disabled",
                                 background="#1e1e1e", foreground="#e0e0e0",
                                 insertbackground="#e0e0e0", font=("Menlo", 11))
        self.log_text.pack(fill="both", expand=True)

        log_scroll = ttk.Scrollbar(self.log_text, command=self.log_text.yview)
        self.log_text["yscrollcommand"] = log_scroll.set
        log_scroll.pack(side="right", fill="y")

    def _show_wimlib_missing_error(self):
        self.log("FEHLER: 'wimlib-imagex' wurde nicht gefunden.")
        self.log("Bitte installieren Sie es zuerst über Homebrew:")
        self.log("    brew install wimlib")
        self.create_button.configure(state="disabled")
        messagebox.showerror(
            "Voraussetzung fehlt",
            "Das Kommandozeilen-Tool 'wimlib-imagex' wurde nicht gefunden.\n\n"
            "Bitte installieren Sie es zuerst mit Homebrew:\n\n"
            "    brew install wimlib\n\n"
            "und starten Sie diese Anwendung danach erneut."
        )

    # ------------------------------------------------------------ Logging --

    def log(self, message: str):
        def _append():
            self.log_text.configure(state="normal")
            self.log_text.insert("end", message + "\n")
            self.log_text.see("end")
            self.log_text.configure(state="disabled")
        self.root.after(0, _append)

    def set_progress(self, value: float):
        self.root.after(0, lambda: self.progress.configure(value=value))

    # ------------------------------------------------------------ Actions --

    def select_iso(self):
        path = filedialog.askopenfilename(
            title="Windows-ISO auswählen",
            filetypes=[("ISO-Dateien", "*.iso")]
        )
        if path:
            self.iso_path.set(path)

    def refresh_disks(self):
        self.log("Suche nach externen USB-Datenträgern…")
        disks = list_removable_disks()
        self.disk_map = {}
        display_values = []
        for d in disks:
            label = f"{d['name']} — {d['size']} ({'/dev/' + d['identifier']})"
            display_values.append(label)
            self.disk_map[label] = d["identifier"]

        self.disk_combo["values"] = display_values
        if display_values:
            self.disk_combo.current(0)
            self.log(f"{len(display_values)} Datenträger gefunden.")
        else:
            self.selected_disk.set("")
            self.log("Keine externen, entfernbaren Datenträger gefunden.")

    def on_create_clicked(self):
        iso = self.iso_path.get()
        disk_label = self.selected_disk.get()

        if not iso:
            messagebox.showwarning("Fehlt", "Bitte zuerst eine Windows-ISO-Datei auswählen.")
            return
        if not disk_label or disk_label not in self.disk_map:
            messagebox.showwarning("Fehlt", "Bitte zuerst einen Ziel-USB-Stick auswählen.")
            return

        disk_id = self.disk_map[disk_label]

        confirmed = messagebox.askyesno(
            "Achtung — Datenverlust!",
            f"Alle Daten auf '/dev/{disk_id}' ({disk_label}) werden "
            "unwiderruflich GELÖSCHT.\n\n"
            "Möchten Sie wirklich fortfahren?",
            icon="warning"
        )
        if not confirmed:
            self.log("Vorgang vom Benutzer abgebrochen.")
            return

        self.create_button.configure(state="disabled")
        self.set_progress(0)

        thread = threading.Thread(
            target=self.run_flash_process, args=(iso, disk_id), daemon=True
        )
        thread.start()

    # ------------------------------------------------------- Worker Thread --

    def run_flash_process(self, iso_path: str, disk_id: str):
        mounted_iso_path = None
        try:
            # Schritt 1: Formatieren
            self.log(f"Formatiere /dev/{disk_id} (GPT, FAT32, Name 'WINSETUP')…")
            self._run_command([
                "diskutil", "partitionDisk", f"/dev/{disk_id}",
                "GPT", "FAT32", "WINSETUP", "0b"
            ])
            self.set_progress(15)

            # Schritt 2: ISO mounten
            self.log(f"Mounte ISO: {iso_path}…")
            mounted_iso_path = self._mount_iso(iso_path)
            self.log(f"ISO gemountet unter: {mounted_iso_path}")
            self.set_progress(25)

            # Schritt 3: rsync ohne install.wim
            self.log("Kopiere Dateien (außer install.wim) auf den USB-Stick…")
            self._run_command([
                "rsync", "-avh", "--progress",
                "--exclude=/sources/install.wim",
                f"{mounted_iso_path}/", "/Volumes/WINSETUP/"
            ], log_output=True)
            self.set_progress(65)

            # Schritt 4: install.wim splitten
            wim_source = os.path.join(mounted_iso_path, "sources", "install.wim")
            dest_dir = "/Volumes/WINSETUP/sources"
            os.makedirs(dest_dir, exist_ok=True)
            swm_dest = os.path.join(dest_dir, "install.swm")

            self.log("Spalte install.wim in Teile < 3.8 GB (wimlib-imagex split)…")
            self._run_command([
                "wimlib-imagex", "split", wim_source, swm_dest, "3800"
            ], log_output=True)
            self.set_progress(88)

            # Schritt 4b: Verifikation der gesplitteten WIM-Dateien
            self.log("Verifiziere install.swm (wimlib-imagex info)…")
            try:
                info_result = self._run_command(
                    ["wimlib-imagex", "info", swm_dest], log_output=True
                )
                self.log("Verifikation erfolgreich: Split-WIM-Dateien sind konsistent.")
            except subprocess.CalledProcessError as verify_err:
                error_output = (verify_err.stderr or verify_err.stdout or str(verify_err)).strip()
                self.log("WARNUNG: Verifikation der install.swm fehlgeschlagen!")
                self.log(error_output)
                raise RuntimeError(
                    "Die install.swm-Dateien konnten nicht verifiziert werden. "
                    "Der USB-Stick ist möglicherweise nicht bootfähig."
                )
            self.set_progress(90)

            # Schritt 5: Auswerfen
            self.log("Werfe ISO-Image aus…")
            self._run_command(["hdiutil", "unmount", mounted_iso_path])
            mounted_iso_path = None

            self.log(f"Werfe USB-Stick /dev/{disk_id} sicher aus…")
            self._run_command(["diskutil", "eject", f"/dev/{disk_id}"])
            self.set_progress(100)

            # Schritt 6: Erfolg
            self.log("Fertig! Der Windows-Installations-USB-Stick wurde erfolgreich erstellt.")
            self.root.after(0, lambda: messagebox.showinfo(
                "Erfolg",
                "Der bootfähige Windows-USB-Stick wurde erfolgreich erstellt!"
            ))

        except subprocess.CalledProcessError as e:
            error_output = (e.stderr or e.stdout or str(e)).strip()
            self.log(f"FEHLER bei Befehl: {' '.join(e.cmd)}")
            self.log(error_output)
            self.root.after(0, lambda: messagebox.showerror(
                "Fehler", f"Ein Befehl ist fehlgeschlagen:\n\n{error_output}"
            ))
        except Exception as e:
            self.log(f"Unerwarteter Fehler: {e}")
            self.root.after(0, lambda: messagebox.showerror("Fehler", str(e)))
        finally:
            # Best-effort Aufräumen, falls ISO noch gemountet ist
            if mounted_iso_path:
                subprocess.run(["hdiutil", "unmount", mounted_iso_path],
                                capture_output=True, text=True)
            self.root.after(0, lambda: self.create_button.configure(state="normal"))

    # ------------------------------------------------------------ Helpers --

    def _run_command(self, cmd, log_output=False):
        """Führt einen Befehl aus, wirft bei Fehler CalledProcessError."""
        self.log(f"$ {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True)
        if log_output and result.stdout:
            for line in result.stdout.splitlines()[-20:]:
                self.log(line)
        if result.returncode != 0:
            raise subprocess.CalledProcessError(
                result.returncode, cmd, output=result.stdout, stderr=result.stderr
            )
        return result

    def _mount_iso(self, iso_path: str) -> str:
        """Mountet die ISO via hdiutil und gibt den Mount-Pfad zurück."""
        result = subprocess.run(
            ["hdiutil", "mount", iso_path],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            raise subprocess.CalledProcessError(
                result.returncode, ["hdiutil", "mount", iso_path],
                output=result.stdout, stderr=result.stderr
            )
        # Letzte Spalte der letzten Zeile enthält üblicherweise den Mount-Pfad
        match = re.search(r"(/Volumes/[^\n]+)", result.stdout)
        if not match:
            raise RuntimeError("Mount-Pfad der ISO konnte nicht ermittelt werden.")
        return match.group(1).strip()


# --------------------------------------------------------------------------
# Entry Point
# --------------------------------------------------------------------------

def main():
    root = tk.Tk()
    app = WindowsUSBFlasherApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
