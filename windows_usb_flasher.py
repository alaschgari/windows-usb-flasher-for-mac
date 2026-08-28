#!/usr/bin/env python3
"""
Windows USB Flasher for macOS / für macOS
==========================================

[EN] Creates a bootable Windows installation USB stick from a Windows ISO
file. Solves the problem that a Windows ISO cannot simply be copied 1:1
(byte-for-byte, like with balenaEtcher) to a USB stick on the Mac, because
modern Windows ISOs contain an `install.wim` file that can be larger than
4 GB and therefore doesn't fit on a FAT32 file system (FAT32 is required
for UEFI boot, though).

[DE] Erstellt einen bootfähigen Windows-Installations-USB-Stick aus einer
Windows-ISO-Datei. Löst das Problem, dass eine Windows-ISO auf dem Mac
nicht einfach 1:1 (byte-für-byte, wie bei balenaEtcher) auf einen USB-Stick
kopiert werden kann, weil moderne Windows-ISOs eine `install.wim`-Datei
enthalten, die größer als 4 GB sein kann und damit nicht auf ein
FAT32-Dateisystem passt (FAT32 ist aber für UEFI-Boot erforderlich).

Solution / Lösung:
  1. Format USB stick with GPT partition table and FAT32.
     USB-Stick mit GPT-Partitionstabelle und FAT32 formatieren.
  2. Mount ISO. / ISO mounten.
  3. Copy all files EXCEPT install.wim to the stick via rsync.
     Alle Dateien AUSSER install.wim per rsync auf den Stick kopieren.
  4. Split install.wim into multiple .swm files < 4 GB with wimlib-imagex
     and write them directly to the stick.
     install.wim mit wimlib-imagex in mehrere .swm-Dateien < 4 GB splitten
     und direkt auf den Stick schreiben.
  5. Cleanly eject ISO and USB stick. / ISO und USB-Stick sauber auswerfen.

Requirements / Voraussetzung:
  - macOS
  - Homebrew package `wimlib` must be installed / muss installiert sein:
        brew install wimlib
    (provides the `wimlib-imagex` command line tool /
     stellt das Kommandozeilen-Tool `wimlib-imagex` bereit)

Run / Ausführen:
    python3 windows_usb_flasher.py

Note / Hinweis: For diskutil operations you may be prompted for your
macOS password (sudo/system dialog). / Für diskutil-Operationen auf dem
Datenträger können Sie zur Eingabe Ihres macOS-Passworts aufgefordert
werden (sudo/Systemdialog).
"""

import os
import re
import shutil
import subprocess
import threading
import webbrowser
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from typing import Optional

WINDOWS_ISO_DOWNLOAD_URL = "https://www.microsoft.com/software-download/windows11"

# [DE] Apps, die per Doppelklick/Finder gestartet werden, erben nicht das
# PATH der Login-Shell und finden Homebrew-Tools (z.B. wimlib-imagex) daher
# oft nicht, obwohl sie installiert sind. Deshalb werden die üblichen
# Homebrew-bin-Verzeichnisse hier explizit ergänzt.
# [EN] Apps launched via double-click/Finder don't inherit the login
# shell's PATH, so Homebrew tools (e.g. wimlib-imagex) are often not found
# even though they're installed. Explicitly add the common Homebrew bin
# directories here.
for _homebrew_bin in ("/opt/homebrew/bin", "/opt/homebrew/sbin", "/usr/local/bin"):
    if _homebrew_bin not in os.environ.get("PATH", "").split(os.pathsep):
        os.environ["PATH"] = _homebrew_bin + os.pathsep + os.environ.get("PATH", "")


class _OperationCancelled(Exception):
    """[DE] Interne Signal-Exception für einen vom Benutzer abgebrochenen Vorgang.
    [EN] Internal signal exception for a user-cancelled operation."""


# --------------------------------------------------------------------------
# i18n / Übersetzungen
# --------------------------------------------------------------------------

TRANSLATIONS = {
    "de": {
        "app_title": "Windows USB Flasher",
        "language_label": "Sprache",
        "section_iso": "1. Windows-ISO-Datei",
        "browse": "Durchsuchen…",
        "download_iso": "ISO herunterladen…",
        "download_iso_opened": "Offizielle Microsoft-Downloadseite im Browser geöffnet.",
        "cancel_button": "Abbrechen",
        "cancelling": "Breche Vorgang ab…",
        "cancelled_log": "Vorgang abgebrochen.",
        "volume_not_found": "Formatierter Volume 'WINSETUP' wurde nicht gefunden.",
        "step_space_check": "Prüfe verfügbaren Speicherplatz auf dem Stick…",
        "err_insufficient_space": (
            "Nicht genug Speicherplatz auf dem USB-Stick: "
            "benötigt ca. {needed}, verfügbar {available}."
        ),
        "section_usb": "2. Ziel-USB-Stick",
        "refresh": "Aktualisieren",
        "warn_data_loss": "⚠️ Alle Daten auf dem gewählten Datenträger werden gelöscht!",
        "create_button": "USB-Stick erstellen",
        "section_progress": "Fortschritt",
        "err_wimlib_log_1": "FEHLER: 'wimlib-imagex' wurde nicht gefunden.",
        "err_wimlib_log_2": "Bitte installieren Sie es zuerst über Homebrew:",
        "err_wimlib_log_3": "    brew install wimlib",
        "err_wimlib_title": "Voraussetzung fehlt",
        "err_wimlib_body": (
            "Das Kommandozeilen-Tool 'wimlib-imagex' wurde nicht gefunden.\n\n"
            "Bitte installieren Sie es zuerst mit Homebrew:\n\n"
            "    brew install wimlib\n\n"
            "und starten Sie diese Anwendung danach erneut."
        ),
        "select_iso_title": "Windows-ISO auswählen",
        "iso_filetype": "ISO-Dateien",
        "searching_disks": "Suche nach externen USB-Datenträgern…",
        "disks_found": "{count} Datenträger gefunden.",
        "no_disks_found": "Keine externen, entfernbaren Datenträger gefunden.",
        "unknown_disk_name": "Unbekannt",
        "missing_title": "Fehlt",
        "missing_iso": "Bitte zuerst eine Windows-ISO-Datei auswählen.",
        "missing_disk": "Bitte zuerst einen Ziel-USB-Stick auswählen.",
        "confirm_title": "Achtung — Datenverlust!",
        "confirm_body": (
            "Alle Daten auf '/dev/{disk_id}' ({disk_label}) werden "
            "unwiderruflich GELÖSCHT.\n\n"
            "Möchten Sie wirklich fortfahren?"
        ),
        "user_cancelled": "Vorgang vom Benutzer abgebrochen.",
        "step_format": "Formatiere /dev/{disk_id} (GPT, FAT32, Name 'WINSETUP')…",
        "step_mount": "Mounte ISO: {iso_path}…",
        "step_mounted": "ISO gemountet unter: {mount_path}",
        "step_copy": "Kopiere Dateien (außer install.wim) auf den USB-Stick…",
        "step_split": "Spalte install.wim in Teile < 3.8 GB (wimlib-imagex split)…",
        "step_verify": "Verifiziere install.swm (wimlib-imagex info)…",
        "step_verify_ok": "Verifikation erfolgreich: Split-WIM-Dateien sind konsistent.",
        "step_verify_warn": "WARNUNG: Verifikation der install.swm fehlgeschlagen!",
        "step_verify_fail_msg": (
            "Die install.swm-Dateien konnten nicht verifiziert werden. "
            "Der USB-Stick ist möglicherweise nicht bootfähig."
        ),
        "step_unmount_iso": "Werfe ISO-Image aus…",
        "step_eject_usb": "Werfe USB-Stick /dev/{disk_id} sicher aus…",
        "step_done": "Fertig! Der Windows-Installations-USB-Stick wurde erfolgreich erstellt.",
        "success_title": "Erfolg",
        "success_body": "Der bootfähige Windows-USB-Stick wurde erfolgreich erstellt!",
        "error_command_log": "FEHLER bei Befehl: {cmd}",
        "error_title": "Fehler",
        "error_command_body": "Ein Befehl ist fehlgeschlagen:\n\n{error}",
        "error_unexpected_log": "Unerwarteter Fehler: {error}",
        "mount_path_not_found": "Mount-Pfad der ISO konnte nicht ermittelt werden.",
        "usb_device_label": "USB-Datenträger",
    },
    "en": {
        "app_title": "Windows USB Flasher",
        "language_label": "Language",
        "section_iso": "1. Windows ISO File",
        "browse": "Browse…",
        "download_iso": "Download ISO…",
        "download_iso_opened": "Official Microsoft download page opened in your browser.",
        "cancel_button": "Cancel",
        "cancelling": "Cancelling…",
        "cancelled_log": "Operation cancelled.",
        "volume_not_found": "Formatted volume 'WINSETUP' was not found.",
        "step_space_check": "Checking available space on the USB stick…",
        "err_insufficient_space": (
            "Not enough space on the USB stick: "
            "needed approx. {needed}, available {available}."
        ),
        "section_usb": "2. Target USB Stick",
        "refresh": "Refresh",
        "warn_data_loss": "⚠️ All data on the selected drive will be erased!",
        "create_button": "Create USB Stick",
        "section_progress": "Progress",
        "err_wimlib_log_1": "ERROR: 'wimlib-imagex' was not found.",
        "err_wimlib_log_2": "Please install it first via Homebrew:",
        "err_wimlib_log_3": "    brew install wimlib",
        "err_wimlib_title": "Requirement Missing",
        "err_wimlib_body": (
            "The command line tool 'wimlib-imagex' was not found.\n\n"
            "Please install it first with Homebrew:\n\n"
            "    brew install wimlib\n\n"
            "and then restart this application."
        ),
        "select_iso_title": "Select Windows ISO",
        "iso_filetype": "ISO files",
        "searching_disks": "Searching for external USB drives…",
        "disks_found": "{count} drive(s) found.",
        "no_disks_found": "No external, removable drives found.",
        "unknown_disk_name": "Unknown",
        "missing_title": "Missing",
        "missing_iso": "Please select a Windows ISO file first.",
        "missing_disk": "Please select a target USB stick first.",
        "confirm_title": "Warning — Data Loss!",
        "confirm_body": (
            "All data on '/dev/{disk_id}' ({disk_label}) will be "
            "PERMANENTLY ERASED.\n\n"
            "Do you really want to continue?"
        ),
        "user_cancelled": "Operation cancelled by user.",
        "step_format": "Formatting /dev/{disk_id} (GPT, FAT32, name 'WINSETUP')…",
        "step_mount": "Mounting ISO: {iso_path}…",
        "step_mounted": "ISO mounted at: {mount_path}",
        "step_copy": "Copying files (except install.wim) to the USB stick…",
        "step_split": "Splitting install.wim into parts < 3.8 GB (wimlib-imagex split)…",
        "step_verify": "Verifying install.swm (wimlib-imagex info)…",
        "step_verify_ok": "Verification successful: split WIM files are consistent.",
        "step_verify_warn": "WARNING: verification of install.swm failed!",
        "step_verify_fail_msg": (
            "The install.swm files could not be verified. "
            "The USB stick may not be bootable."
        ),
        "step_unmount_iso": "Ejecting ISO image…",
        "step_eject_usb": "Safely ejecting USB stick /dev/{disk_id}…",
        "step_done": "Done! The Windows installation USB stick was created successfully.",
        "success_title": "Success",
        "success_body": "The bootable Windows USB stick was created successfully!",
        "error_command_log": "ERROR running command: {cmd}",
        "error_title": "Error",
        "error_command_body": "A command failed:\n\n{error}",
        "error_unexpected_log": "Unexpected error: {error}",
        "mount_path_not_found": "Could not determine the ISO's mount path.",
        "usb_device_label": "USB Drive",
    },
}


# --------------------------------------------------------------------------
# Hilfsfunktionen / Helper functions (Backend-Logik / backend logic)
# --------------------------------------------------------------------------

def check_wimlib_installed() -> bool:
    """[DE] Prüft, ob wimlib-imagex im PATH verfügbar ist.
    [EN] Checks whether wimlib-imagex is available on the PATH."""
    return shutil.which("wimlib-imagex") is not None


def list_removable_disks(unknown_label="Unknown", usb_label="USB Drive"):
    """
    [DE] Liest `diskutil list` aus und gibt eine Liste von externen,
    entfernbaren (removable) Datenträgern zurück.
    [EN] Reads `diskutil list` and returns a list of external, removable
    disks.

    Rückgabe / Return: list of dicts:
        {"identifier": "disk2", "size": "15.5 GB", "name": "..."}
    """
    result = subprocess.run(
        ["diskutil", "list", "-plist", "external", "physical"],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        return _list_removable_disks_text_fallback(usb_label)

    import plistlib
    try:
        data = plistlib.loads(result.stdout.encode("utf-8"))
    except Exception:
        return _list_removable_disks_text_fallback(usb_label)

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
            name = disk_info.get("MediaName", unknown_label)
            disks.append({
                "identifier": disk_identifier,
                "size": size_str,
                "name": name,
            })
    return disks


def _list_removable_disks_text_fallback(usb_label="USB Drive"):
    """[DE] Einfacher Text-Parser als Fallback.
    [EN] Simple text parser fallback."""
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
            size_str = size_match.group(1) if size_match else "unknown"
            disks.append({
                "identifier": current_disk,
                "size": size_str,
                "name": usb_label,
            })
            current_disk = None
    return disks


def _format_size(size_bytes: int) -> str:
    """[DE] Formatiert Bytes in eine lesbare Größe (GB).
    [EN] Formats bytes into a human-readable size (GB)."""
    gb = size_bytes / (1000 ** 3)
    return f"{gb:.1f} GB"


def find_volume_mount_point(disk_id: str, volume_name: str) -> Optional[str]:
    """
    [DE] Findet den tatsächlichen Mount-Pfad eines frisch formatierten
    Volumes anhand seines Namens, statt einen festen Pfad wie
    '/Volumes/WINSETUP' anzunehmen (der bei Namenskollision mit einem
    anderen Datenträger falsch wäre).
    [EN] Finds the actual mount path of a freshly formatted volume by its
    name, instead of assuming a fixed path like '/Volumes/WINSETUP' (which
    would be wrong if another mounted disk already used that name).
    """
    import plistlib

    result = subprocess.run(
        ["diskutil", "list", "-plist", disk_id],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        return None
    try:
        data = plistlib.loads(result.stdout.encode("utf-8"))
    except Exception:
        return None

    partition_ids = []
    for disk in data.get("AllDisksAndPartitions", []):
        for partition in disk.get("Partitions", []):
            identifier = partition.get("DeviceIdentifier")
            if identifier:
                partition_ids.append(identifier)

    for identifier in partition_ids:
        info = subprocess.run(
            ["diskutil", "info", "-plist", identifier],
            capture_output=True, text=True
        )
        if info.returncode != 0:
            continue
        try:
            partition_info = plistlib.loads(info.stdout.encode("utf-8"))
        except Exception:
            continue
        if partition_info.get("VolumeName") == volume_name:
            return partition_info.get("MountPoint")
    return None


def get_free_space_bytes(mount_point: str) -> int:
    """[DE] Gibt den freien Speicherplatz (Bytes) am Mount-Pfad zurück.
    [EN] Returns the free space (bytes) at the given mount point."""
    stat = os.statvfs(mount_point)
    return stat.f_bavail * stat.f_frsize


# --------------------------------------------------------------------------
# GUI
# --------------------------------------------------------------------------

class WindowsUSBFlasherApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.lang = "de"

        self.iso_path = tk.StringVar(value="")
        self.selected_disk = tk.StringVar(value="")
        self.disk_map = {}  # Anzeigetext -> Identifier / display text -> identifier
        self.cancel_event = threading.Event()

        self.root.geometry("640x600")
        self.root.minsize(600, 520)

        self._setup_style()
        self._build_ui()
        self._apply_language()

        # Voraussetzung prüfen / check requirement
        if not check_wimlib_installed():
            self._show_wimlib_missing_error()
        else:
            self.refresh_disks()

    # -------------------------------------------------------------- i18n --

    def t(self, key: str, **kwargs) -> str:
        text = TRANSLATIONS[self.lang][key]
        return text.format(**kwargs) if kwargs else text

    def on_language_changed(self, event=None):
        label = self.language_var.get()
        self.lang = "en" if label == "English" else "de"
        self._apply_language()
        self.refresh_disks()

    def _apply_language(self):
        self.root.title(self.t("app_title"))
        self.title_label.configure(text=self.t("app_title"))
        self.language_frame_label.configure(text=self.t("language_label"))
        self.iso_frame.configure(text=self.t("section_iso"))
        self.browse_button.configure(text=self.t("browse"))
        self.download_iso_button.configure(text=self.t("download_iso"))
        self.usb_frame.configure(text=self.t("section_usb"))
        self.refresh_button.configure(text=self.t("refresh"))
        self.warn_label.configure(text=self.t("warn_data_loss"))
        self.create_button.configure(text=self.t("create_button"))
        self.cancel_button.configure(text=self.t("cancel_button"))
        self.progress_frame.configure(text=self.t("section_progress"))

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

        # --- Titelzeile mit Sprachauswahl / Title row with language switch ---
        header_row = ttk.Frame(outer)
        header_row.pack(fill="x", pady=(0, 15))

        self.title_label = ttk.Label(header_row, text="", style="Title.TLabel")
        self.title_label.pack(side="left")

        lang_box = ttk.Frame(header_row)
        lang_box.pack(side="right")
        self.language_frame_label = ttk.Label(lang_box, text="")
        self.language_frame_label.pack(side="left", padx=(0, 6))
        self.language_var = tk.StringVar(value="Deutsch")
        self.language_combo = ttk.Combobox(
            lang_box, textvariable=self.language_var, state="readonly",
            values=["Deutsch", "English"], width=10
        )
        self.language_combo.pack(side="left")
        self.language_combo.bind("<<ComboboxSelected>>", self.on_language_changed)

        # --- ISO-Auswahl / ISO selection ---
        self.iso_frame = ttk.LabelFrame(outer, text="", padding=12)
        self.iso_frame.pack(fill="x", pady=(0, 12))

        iso_row = ttk.Frame(self.iso_frame)
        iso_row.pack(fill="x")
        self.iso_entry = ttk.Entry(iso_row, textvariable=self.iso_path, state="readonly")
        self.iso_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.browse_button = ttk.Button(iso_row, text="", command=self.select_iso)
        self.browse_button.pack(side="left", padx=(0, 8))
        self.download_iso_button = ttk.Button(iso_row, text="", command=self.open_iso_download_page)
        self.download_iso_button.pack(side="left")

        # --- USB-Auswahl / USB selection ---
        self.usb_frame = ttk.LabelFrame(outer, text="", padding=12)
        self.usb_frame.pack(fill="x", pady=(0, 12))

        usb_row = ttk.Frame(self.usb_frame)
        usb_row.pack(fill="x")
        self.disk_combo = ttk.Combobox(usb_row, textvariable=self.selected_disk, state="readonly")
        self.disk_combo.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.refresh_button = ttk.Button(usb_row, text="", command=self.refresh_disks)
        self.refresh_button.pack(side="left")

        self.warn_label = ttk.Label(self.usb_frame, text="", foreground="#b00020")
        self.warn_label.pack(anchor="w", pady=(8, 0))

        # --- Erstellen-Button / Create button ---
        button_row = ttk.Frame(outer)
        button_row.pack(fill="x", pady=(4, 16))

        self.create_button = ttk.Button(
            button_row, text="", style="Big.TButton",
            command=self.on_create_clicked
        )
        self.create_button.pack(side="left", fill="x", expand=True, padx=(0, 8))

        self.cancel_button = ttk.Button(
            button_row, text="", command=self.on_cancel_clicked, state="disabled"
        )
        self.cancel_button.pack(side="left")

        # --- Fortschritt / Progress ---
        self.progress_frame = ttk.LabelFrame(outer, text="", padding=12)
        self.progress_frame.pack(fill="both", expand=True)

        self.progress = ttk.Progressbar(self.progress_frame, mode="determinate", maximum=100)
        self.progress.pack(fill="x", pady=(0, 10))

        self.log_text = tk.Text(self.progress_frame, height=14, wrap="word", state="disabled",
                                 background="#1e1e1e", foreground="#e0e0e0",
                                 insertbackground="#e0e0e0", font=("Menlo", 11))
        self.log_text.pack(fill="both", expand=True)

        log_scroll = ttk.Scrollbar(self.log_text, command=self.log_text.yview)
        self.log_text["yscrollcommand"] = log_scroll.set
        log_scroll.pack(side="right", fill="y")

    def _show_wimlib_missing_error(self):
        self.log(self.t("err_wimlib_log_1"))
        self.log(self.t("err_wimlib_log_2"))
        self.log(self.t("err_wimlib_log_3"))
        self.create_button.configure(state="disabled")
        messagebox.showerror(self.t("err_wimlib_title"), self.t("err_wimlib_body"))

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
            title=self.t("select_iso_title"),
            filetypes=[(self.t("iso_filetype"), "*.iso")]
        )
        if path:
            self.iso_path.set(path)

    def open_iso_download_page(self):
        webbrowser.open(WINDOWS_ISO_DOWNLOAD_URL)
        self.log(self.t("download_iso_opened"))

    def refresh_disks(self):
        self.log(self.t("searching_disks"))
        disks = list_removable_disks(
            unknown_label=self.t("unknown_disk_name"),
            usb_label=self.t("usb_device_label"),
        )
        self.disk_map = {}
        display_values = []
        for d in disks:
            label = f"{d['name']} — {d['size']} ({'/dev/' + d['identifier']})"
            display_values.append(label)
            self.disk_map[label] = d["identifier"]

        self.disk_combo["values"] = display_values
        if display_values:
            self.disk_combo.current(0)
            self.log(self.t("disks_found", count=len(display_values)))
        else:
            self.selected_disk.set("")
            self.log(self.t("no_disks_found"))

    def on_create_clicked(self):
        iso = self.iso_path.get()
        disk_label = self.selected_disk.get()

        if not iso:
            messagebox.showwarning(self.t("missing_title"), self.t("missing_iso"))
            return
        if not disk_label or disk_label not in self.disk_map:
            messagebox.showwarning(self.t("missing_title"), self.t("missing_disk"))
            return

        disk_id = self.disk_map[disk_label]

        confirmed = messagebox.askyesno(
            self.t("confirm_title"),
            self.t("confirm_body", disk_id=disk_id, disk_label=disk_label),
            icon="warning"
        )
        if not confirmed:
            self.log(self.t("user_cancelled"))
            return

        self.create_button.configure(state="disabled")
        self.cancel_button.configure(state="normal")
        self.cancel_event.clear()
        self.set_progress(0)

        thread = threading.Thread(
            target=self.run_flash_process, args=(iso, disk_id), daemon=True
        )
        thread.start()

    def on_cancel_clicked(self):
        self.cancel_event.set()
        self.log(self.t("cancelling"))
        self.cancel_button.configure(state="disabled")

    def _check_cancelled(self):
        if self.cancel_event.is_set():
            raise _OperationCancelled()

    # ------------------------------------------------------- Worker Thread --

    def run_flash_process(self, iso_path: str, disk_id: str):
        mounted_iso_path = None
        try:
            # Schritt 1: Formatieren / Step 1: format
            self.log(self.t("step_format", disk_id=disk_id))
            self._run_command([
                "diskutil", "partitionDisk", f"/dev/{disk_id}",
                "GPT", "FAT32", "WINSETUP", "0b"
            ])
            self.set_progress(10)
            self._check_cancelled()

            # Schritt 1b: tatsächlichen Mount-Pfad des Volumes ermitteln
            # Step 1b: determine the actual mount path of the volume
            usb_mount_path = find_volume_mount_point(disk_id, "WINSETUP")
            if not usb_mount_path:
                raise RuntimeError(self.t("volume_not_found"))
            self.set_progress(15)

            # Schritt 2: ISO mounten / Step 2: mount ISO
            self.log(self.t("step_mount", iso_path=iso_path))
            mounted_iso_path = self._mount_iso(iso_path)
            self.log(self.t("step_mounted", mount_path=mounted_iso_path))
            self.set_progress(22)
            self._check_cancelled()

            # Schritt 2b: Speicherplatz prüfen / Step 2b: check free space
            self.log(self.t("step_space_check"))
            iso_size = os.path.getsize(iso_path)
            free_space = get_free_space_bytes(usb_mount_path)
            # [DE] install.wim wird durch split-.swm-Dateien ersetzt, keine
            # zusätzliche Kompression -> Größe der ISO ist eine sichere obere
            # Schätzung für den benötigten Platz.
            # [EN] install.wim is replaced by split .swm files without extra
            # compression -> the ISO size is a safe upper-bound estimate.
            if free_space < iso_size:
                raise RuntimeError(self.t(
                    "err_insufficient_space",
                    needed=_format_size(iso_size),
                    available=_format_size(free_space),
                ))
            self.set_progress(25)
            self._check_cancelled()

            # Schritt 3: rsync ohne install.wim / Step 3: rsync excluding install.wim
            self.log(self.t("step_copy"))
            self._run_command([
                "rsync", "-avh", "--progress",
                "--exclude=/sources/install.wim",
                f"{mounted_iso_path}/", f"{usb_mount_path}/"
            ], log_output=True)
            self.set_progress(65)
            self._check_cancelled()

            # Schritt 4: install.wim splitten / Step 4: split install.wim
            wim_source = os.path.join(mounted_iso_path, "sources", "install.wim")
            dest_dir = os.path.join(usb_mount_path, "sources")
            os.makedirs(dest_dir, exist_ok=True)
            swm_dest = os.path.join(dest_dir, "install.swm")

            self.log(self.t("step_split"))
            self._run_command([
                "wimlib-imagex", "split", wim_source, swm_dest, "3800"
            ], log_output=True)
            self.set_progress(88)

            # Schritt 4b: Verifikation / Step 4b: verification
            self.log(self.t("step_verify"))
            try:
                self._run_command(
                    ["wimlib-imagex", "info", swm_dest], log_output=True
                )
                self.log(self.t("step_verify_ok"))
            except subprocess.CalledProcessError as verify_err:
                error_output = (verify_err.stderr or verify_err.stdout or str(verify_err)).strip()
                self.log(self.t("step_verify_warn"))
                self.log(error_output)
                raise RuntimeError(self.t("step_verify_fail_msg"))
            self.set_progress(90)

            # Schritt 5: Auswerfen / Step 5: eject
            self.log(self.t("step_unmount_iso"))
            self._run_command(["hdiutil", "unmount", mounted_iso_path])
            mounted_iso_path = None

            self.log(self.t("step_eject_usb", disk_id=disk_id))
            self._run_command(["diskutil", "eject", f"/dev/{disk_id}"])
            self.set_progress(100)

            # Schritt 6: Erfolg / Step 6: success
            self.log(self.t("step_done"))
            self.root.after(0, lambda: messagebox.showinfo(
                self.t("success_title"), self.t("success_body")
            ))

        except _OperationCancelled:
            self.log(self.t("cancelled_log"))
        except subprocess.CalledProcessError as e:
            error_output = (e.stderr or e.stdout or str(e)).strip()
            self.log(self.t("error_command_log", cmd=" ".join(e.cmd)))
            self.log(error_output)
            self.root.after(0, lambda: messagebox.showerror(
                self.t("error_title"), self.t("error_command_body", error=error_output)
            ))
        except Exception as e:
            self.log(self.t("error_unexpected_log", error=e))
            self.root.after(0, lambda: messagebox.showerror(self.t("error_title"), str(e)))
        finally:
            # Best-effort Aufräumen / best-effort cleanup
            if mounted_iso_path:
                subprocess.run(["hdiutil", "unmount", mounted_iso_path],
                                capture_output=True, text=True)
            self.root.after(0, lambda: self.create_button.configure(state="normal"))
            self.root.after(0, lambda: self.cancel_button.configure(state="disabled"))

    # ------------------------------------------------------------ Helpers --

    def _run_command(self, cmd, log_output=False):
        """[DE] Führt einen Befehl aus, wirft bei Fehler CalledProcessError.
        [EN] Runs a command, raises CalledProcessError on failure."""
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
        """[DE] Mountet die ISO via hdiutil und gibt den Mount-Pfad zurück.
        [EN] Mounts the ISO via hdiutil and returns the mount path."""
        result = subprocess.run(
            ["hdiutil", "mount", iso_path],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            raise subprocess.CalledProcessError(
                result.returncode, ["hdiutil", "mount", iso_path],
                output=result.stdout, stderr=result.stderr
            )
        match = re.search(r"(/Volumes/[^\n]+)", result.stdout)
        if not match:
            raise RuntimeError(self.t("mount_path_not_found"))
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
