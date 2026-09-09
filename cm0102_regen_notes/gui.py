"""Tkinter GUI wrapping snapshot / match / annotate.

Deliberately a thin shell over the same functions the CLI uses. All disk work
runs on a worker thread so the window never freezes; results come back to the
Tk thread via ``root.after``.
"""

from __future__ import annotations

import csv
import queue
import subprocess
import sys
import threading
import traceback
import unicodedata
from pathlib import Path
from tkinter import (
    BOTH, END, LEFT, RIGHT, VERTICAL, W, X, Y,
    BooleanVar, StringVar, Tk, filedialog, font as tkfont, messagebox, ttk,
)
from tkinter.scrolledtext import ScrolledText

from . import __version__
from .annotate import AnnotatePlan, apply_annotations_in_place
from .match import RegenMatch, find_regens, write_csv
from .notes import NOTE_TEXT_MAX
from .snapshot import write_snapshot

# Characters that NFKD doesn't decompose but players will still type plainly.
_FOLD_MAP = str.maketrans({
    "ø": "o", "œ": "oe", "æ": "ae", "ð": "d", "þ": "th",
    "ł": "l", "đ": "d", "ħ": "h", "ı": "i", "ŧ": "t", "ŋ": "n",
})


def _fold(text: str) -> str:
    """Lower-case and strip accents so "german" matches "Germán"."""
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return stripped.translate(_FOLD_MAP)


def _cm0102_running() -> bool:
    """True if the CM 01/02 game is running.

    Matches ``cm0102.exe`` and patched variants like ``cm0102_GDI.exe`` /
    ``cm0102_Saturn.exe`` -- but not the editor (``cm0102ed.exe``) and not this
    tool (``cm0102-regen-notes.exe``).
    """
    if sys.platform != "win32":
        return False
    try:
        out = subprocess.run(
            ["tasklist", "/NH", "/FO", "CSV"],
            capture_output=True, text=True, timeout=5,
            creationflags=0x08000000,  # CREATE_NO_WINDOW - don't flash a console
        )
    except (OSError, subprocess.SubprocessError):
        return False

    self_exe = Path(sys.executable).name.lower()
    for row in csv.reader(out.stdout.splitlines()):
        if not row:
            continue
        name = row[0].strip().lower()
        if name == self_exe:
            continue
        if name == "cm0102.exe" or (name.startswith("cm0102_") and name.endswith(".exe")):
            return True
    return False


COLUMNS = [
    ("slot", "Player ID", 70),
    ("staff_id", "Staff ID", 70),
    ("original_name", "Original Player", 205),
    ("current_name", "Regen", 205),
    ("current_ca", "CA", 45),
    ("current_pa", "PA", 45),
]
NAME_COLS = ("original_name", "current_name")


class App:
    def __init__(self, root: Tk):
        self.root = root
        root.title(f"CM 01/02 Regen Note Writer  {__version__}")
        root.geometry("900x600")
        root.minsize(720, 460)

        self.save_path = StringVar()
        self.baseline_path = StringVar()
        self.min_pa = StringVar(value="150")
        self.backup_first = BooleanVar(value=True)
        self.filter_original = StringVar()
        self.filter_regen = StringVar()
        self.status = StringVar(value="Pick a save file and a regen file to get started")

        self._all_matches: list[RegenMatch] = []
        self._folded: list[tuple[str, str]] = []
        self._shown: list[RegenMatch] = []
        self._busy = False
        self._q: queue.Queue = queue.Queue()

        self._build_form()
        self._build_filter_bar()
        self._build_table()
        self._build_log()
        self._poll_queue()

    # ---- layout ----------------------------------------------------------

    def _build_form(self):
        f = ttk.Frame(self.root, padding=10)
        f.pack(fill=X)

        ttk.Label(f, text="Save file (.sav)").grid(row=0, column=0, sticky=W, pady=2)
        ttk.Entry(f, textvariable=self.save_path).grid(row=0, column=1, sticky="ew", padx=6)
        ttk.Button(f, text="Browse…", command=self._pick_save).grid(row=0, column=2, sticky=W)

        ttk.Label(f, text="Regen file (.gpf2 or .rnw)").grid(row=1, column=0, sticky=W, pady=2)
        ttk.Entry(f, textvariable=self.baseline_path).grid(row=1, column=1, sticky="ew", padx=6)
        bf = ttk.Frame(f)
        bf.grid(row=1, column=2, sticky=W)
        ttk.Button(bf, text="Browse…", command=self._pick_baseline).pack(side=LEFT)
        ttk.Button(bf, text="Take snapshot now", command=self._take_snapshot).pack(side=LEFT, padx=(6, 0))

        opts = ttk.Frame(f)
        opts.grid(row=2, column=0, columnspan=3, sticky=W, pady=(8, 0))
        ttk.Label(opts, text="Min PA").pack(side=LEFT)
        ttk.Spinbox(opts, from_=0, to=999, width=5, textvariable=self.min_pa,
                    command=self._refilter).pack(side=LEFT, padx=(4, 16))

        actions = ttk.Frame(f)
        actions.grid(row=3, column=0, columnspan=3, sticky=W, pady=(10, 0))
        self._find_btn = ttk.Button(actions, text="Find Regens", command=self._find)
        self._find_btn.pack(side=LEFT)
        self._csv_btn = ttk.Button(actions, text="Export CSV…", command=self._export_csv, state="disabled")
        self._csv_btn.pack(side=LEFT, padx=6)
        self._write_btn = ttk.Button(actions, text="Write notes to save", command=self._write_notes,
                                     state="disabled")
        self._write_btn.pack(side=LEFT)
        ttk.Checkbutton(actions, text="back up save", variable=self.backup_first).pack(
            side=LEFT, padx=(10, 0))

        f.columnconfigure(1, weight=1)

        for var in (self.save_path, self.baseline_path):
            var.trace_add("write", lambda *_: self._invalidate())

    def _build_filter_bar(self):
        fb = ttk.Frame(self.root, padding=(10, 0))
        fb.pack(fill=X)
        ttk.Label(fb, text="Filter  —  Original Player").pack(side=LEFT)
        ttk.Entry(fb, textvariable=self.filter_original, width=26).pack(side=LEFT, padx=(4, 14))
        ttk.Label(fb, text="Regen").pack(side=LEFT)
        ttk.Entry(fb, textvariable=self.filter_regen, width=26).pack(side=LEFT, padx=(4, 14))
        ttk.Button(fb, text="Clear", command=self._clear_filters).pack(side=LEFT)
        for var in (self.filter_original, self.filter_regen):
            var.trace_add("write", lambda *_: self._refilter())

    def _clear_filters(self):
        self.filter_original.set("")
        self.filter_regen.set("")

    def _build_table(self):
        wrap = ttk.Frame(self.root, padding=(10, 4))
        wrap.pack(fill=BOTH, expand=True)

        base = tkfont.nametofont("TkDefaultFont")
        self._heading_font = tkfont.Font(font=base)
        self._heading_font.configure(weight="bold")
        ttk.Style().configure("Treeview.Heading", font=self._heading_font)

        self.tree = ttk.Treeview(wrap, columns=[c[0] for c in COLUMNS], show="headings")
        for key, label, width in COLUMNS:
            heading_anchor = W if key in NAME_COLS else "center"
            self.tree.heading(key, text=label, anchor=heading_anchor,
                              command=lambda k=key: self._sort_by(k))
            self.tree.column(key, width=width, anchor=(W if key in NAME_COLS else "center"),
                             stretch=(key in NAME_COLS))
        vsb = ttk.Scrollbar(wrap, orient=VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side=LEFT, fill=BOTH, expand=True)
        vsb.pack(side=RIGHT, fill=Y)
        self._sort_state: dict[str, bool] = {}

    def _build_log(self):
        bar = ttk.Frame(self.root, padding=10)
        bar.pack(fill=X)
        ttk.Label(bar, textvariable=self.status).pack(side=LEFT)
        self.log = ScrolledText(self.root, height=6, state="disabled", wrap="word")
        self.log.pack(fill=X, padx=10, pady=(0, 10))

    # ---- helpers -------------------------------------------------------

    def _logline(self, msg: str):
        self.log.configure(state="normal")
        self.log.insert(END, msg.rstrip() + "\n")
        self.log.see(END)
        self.log.configure(state="disabled")

    def _set_busy(self, busy: bool, status: str | None = None):
        self._busy = busy
        self._find_btn.configure(state=("disabled" if busy else "normal"))
        for b in (self._csv_btn, self._write_btn):
            b.configure(state=("disabled" if busy or not self._shown else "normal"))
        if status:
            self.status.set(status)
        self.root.configure(cursor="watch" if busy else "")

    def _invalidate(self):
        self._all_matches = []
        self._folded = []
        self._shown = []
        self.tree.delete(*self.tree.get_children())
        self._csv_btn.configure(state="disabled")
        self._write_btn.configure(state="disabled")

    def _pick_save(self):
        p = filedialog.askopenfilename(title="Choose save", filetypes=[("CM saves", "*.sav"), ("All", "*.*")])
        if not p:
            return
        self.save_path.set(p)
        self._logline(f"save: {Path(p).name}")
        for ext in (".gpf2", ".rnw"):
            cand = Path(p + ext)
            if cand.exists():
                self.baseline_path.set(str(cand))
                self._logline(f"found a regen file next to it: {cand.name}")
                break

    def _pick_baseline(self):
        p = filedialog.askopenfilename(title="Choose regen file",
                                       filetypes=[("Regen files", "*.gpf2 *.rnw"), ("All", "*.*")])
        if p:
            self.baseline_path.set(p)
            self._logline(f"regen file: {Path(p).name}")

    def _run_async(self, fn, on_done, status: str):
        if self._busy:
            return
        self._set_busy(True, status)

        def worker():
            try:
                self._q.put(("ok", on_done, fn()))
            except Exception as e:  # noqa: BLE001 - surfaced to the user
                self._q.put(("err", on_done, (e, traceback.format_exc())))

        threading.Thread(target=worker, daemon=True).start()

    def _poll_queue(self):
        try:
            kind, on_done, payload = self._q.get_nowait()
        except queue.Empty:
            pass
        else:
            self._set_busy(False)
            if kind == "err":
                exc, tb = payload
                self._logline(tb)
                messagebox.showerror("Something went wrong", str(exc))
                self.status.set("Error — see the log below.")
            else:
                on_done(payload)
        self.root.after(120, self._poll_queue)

    # ---- actions -----------------------------------------------------

    def _take_snapshot(self):
        save = self.save_path.get().strip()
        if not save:
            messagebox.showinfo("No save", "Choose a save file first.")
            return
        out = filedialog.asksaveasfilename(
            title="Write .rnw snapshot", defaultextension=".rnw",
            initialfile=Path(save).name + ".rnw", filetypes=[("Regen-note snapshot", "*.rnw")])
        if not out:
            return
        self._run_async(lambda: write_snapshot(save, out), self._snapshot_done,
                        "Reading save and writing snapshot…")

    def _snapshot_done(self, result):
        out, data = result
        gd = data["game_date"]
        self._logline(f"wrote regen file: {Path(out).name}  "
                      f"({data['player_count']:,} players, in-game day {gd['day']} of {gd['year']})")
        self._logline("  note: this is only a useful regen file if the save is on/near day one.")
        self.baseline_path.set(str(out))
        self.status.set("Regen file written and selected.")

    def _find(self):
        save = self.save_path.get().strip()
        base = self.baseline_path.get().strip()
        if not save or not base:
            messagebox.showinfo("Missing input", "Choose both a save file and a regen file.")
            return
        self._run_async(
            lambda: find_regens(save, base, include_empty_origin=False),
            self._find_done, "Reading the save and matching it against the regen file…")

    def _find_done(self, matches: list[RegenMatch]):
        self._all_matches = matches
        self._folded = [(_fold(m.original_name), _fold(m.current_name)) for m in matches]
        self._logline(f"found {len(matches):,} regens in the save")
        self._refilter()

    def _refilter(self):
        if not self._all_matches:
            return
        try:
            pa_min = int(self.min_pa.get() or 0)
        except ValueError:
            pa_min = 0
        q_orig = _fold(self.filter_original.get().strip())
        q_regen = _fold(self.filter_regen.get().strip())

        rows = []
        for m, (orig_folded, regen_folded) in zip(self._all_matches, self._folded):
            if m.current_pa < pa_min:
                continue
            if q_orig and q_orig not in orig_folded:
                continue
            if q_regen and q_regen not in regen_folded:
                continue
            rows.append(m)

        self._shown = rows
        self.tree.delete(*self.tree.get_children())
        for m in sorted(rows, key=lambda m: (-m.current_pa, m.slot)):
            self.tree.insert("", END, values=(
                m.slot, m.current_staff_id, m.original_name, m.current_name,
                m.current_ca, m.current_pa,
            ))
        noun = "player" if len(rows) == 1 else "players"
        shown_note = f"{len(rows):,} {noun} shown of {len(self._all_matches):,} regens"
        if q_orig or q_regen:
            shown_note += "  [filtered]"
        self.status.set(shown_note)
        self._csv_btn.configure(state=("normal" if rows else "disabled"))
        self._write_btn.configure(state=("normal" if rows else "disabled"))

    def _sort_by(self, key: str):
        rows = list(self.tree.get_children())
        descending = self._sort_state.get(key, False)

        def sort_key(iid):
            v = self.tree.set(iid, key)
            try:
                return (0, float(v))
            except ValueError:
                return (1, v.lower())

        for pos, iid in enumerate(sorted(rows, key=sort_key, reverse=descending)):
            self.tree.move(iid, "", pos)
        self._sort_state[key] = not descending

    def _export_csv(self):
        if not self._shown:
            return
        out = filedialog.asksaveasfilename(
            title="Export CSV", defaultextension=".csv",
            initialfile="regens.csv", filetypes=[("CSV", "*.csv")])
        if not out:
            return
        write_csv(self._shown, out)
        self._logline(f"exported {len(self._shown):,} row(s) -> {out}")
        self.status.set(f"CSV written: {out}")

    def _write_notes(self):
        if not self._shown:
            return
        save = Path(self.save_path.get().strip())

        writable, too_long = [], []
        for m in self._shown:
            if m.original_was_empty:
                continue
            if len(m.original_name.encode("latin-1", "replace")) > NOTE_TEXT_MAX:
                too_long.append(m)
            else:
                writable.append(m)
        if not writable:
            messagebox.showinfo("Nothing to write", "No eligible regens in the current view.")
            return

        if _cm0102_running() and not messagebox.askokcancel(
            "CM 01/02 is running",
            "CM01/02 appears to be running. If you write these notes to a save file "
            "currently in play you will overwrite them with whatever is currently there "
            "when you next save.\n\nWrite anyway?",
            icon="warning",
        ):
            return

        do_backup = self.backup_first.get()
        lines = [
            f"Write {len(writable):,} notes directly into:",
            f"    {save.name}",
            "",
            "Each regen will have the name of their original player written to "
            "their Notes section. Any Note already in there will be replaced.",
        ]
        if too_long:
            lines.append(f"\n{len(too_long)} skipped — original name too long for the Notes field.")
        lines.append("\nSave will be backed up." if do_backup
                     else "\nNo backup will be made.")
        lines.append("\nProceed?")
        if not messagebox.askokcancel("Overwrite notes in this save?", "\n".join(lines),
                                      icon="warning"):
            return

        plan = AnnotatePlan(to_write=writable, skipped_empty_origin=[], skipped_too_long=too_long)
        self._run_async(lambda: apply_annotations_in_place(str(save), plan, backup=do_backup),
                        self._write_done,
                        f"Writing {len(writable):,} notes into {save.name}…")

    def _write_done(self, summary: dict):
        if summary.get("backup"):
            self._logline(f"backup: {summary['backup']}")
        self._logline(
            f"wrote {summary['notes_written']:,} note(s) "
            f"({summary['appended']} new, {summary['overwrote']} updated); "
            f"notes.dat delta {summary['delta']:+}  ->  {summary['out_path']}")
        self.status.set(f"Done — {summary['notes_written']:,} notes written to {Path(summary['out_path']).name}")
        msg = f"{summary['notes_written']:,} notes written into\n{summary['out_path']}"
        if summary.get("backup"):
            msg += f"\n\nBackup:\n{summary['backup']}"
        messagebox.showinfo("Finished", msg)
        self._invalidate()


def main(argv: list[str] | None = None) -> int:
    root = Tk()
    try:
        ttk.Style().theme_use("vista")
    except Exception:  # noqa: BLE001 - non-Windows / theme missing
        pass
    App(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
