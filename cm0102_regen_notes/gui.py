"""Tkinter GUI wrapping snapshot / match / annotate.

Deliberately a thin shell over the same functions the CLI uses. All disk work
runs on a worker thread so the window never freezes; results come back to the
Tk thread via ``root.after``.
"""

from __future__ import annotations

import queue
import threading
import traceback
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

COLUMNS = [
    ("slot", "Slot", 55),
    ("original_name", "Original Player", 210),
    ("current_name", "Regen", 210),
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
        self.include_pregens = BooleanVar(value=False)
        self.backup_first = BooleanVar(value=True)
        self.filter_original = StringVar()
        self.filter_regen = StringVar()
        self.status = StringVar(value="Pick a save file and a day-one baseline.")

        self._all_matches: list[RegenMatch] = []
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
        ttk.Button(f, text="Browse…", command=self._pick_save).grid(row=0, column=2)

        ttk.Label(f, text="Day-one baseline (.gpf2 / .rnw)").grid(row=1, column=0, sticky=W, pady=2)
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
        ttk.Checkbutton(opts, text="Include pregens",
                        variable=self.include_pregens, command=self._refilter).pack(side=LEFT)

        actions = ttk.Frame(f)
        actions.grid(row=3, column=0, columnspan=3, sticky=W, pady=(10, 0))
        self._find_btn = ttk.Button(actions, text="Find regens", command=self._find)
        self._find_btn.pack(side=LEFT)
        self._csv_btn = ttk.Button(actions, text="Export CSV…", command=self._export_csv, state="disabled")
        self._csv_btn.pack(side=LEFT, padx=6)
        self._write_btn = ttk.Button(actions, text="Write notes to save", command=self._write_notes,
                                     state="disabled")
        self._write_btn.pack(side=LEFT)
        ttk.Checkbutton(actions, text="back up the save first", variable=self.backup_first).pack(
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
        self._italic_font = tkfont.Font(font=base)
        self._italic_font.configure(slant="italic")
        ttk.Style().configure("Treeview.Heading", font=self._heading_font)

        self.tree = ttk.Treeview(wrap, columns=[c[0] for c in COLUMNS], show="headings")
        for key, label, width in COLUMNS:
            heading_anchor = W if key in NAME_COLS else "center"
            self.tree.heading(key, text=label, anchor=heading_anchor,
                              command=lambda k=key: self._sort_by(k))
            self.tree.column(key, width=width, anchor=(W if key in NAME_COLS else "center"),
                             stretch=(key in NAME_COLS))
        self.tree.tag_configure("pregen", font=self._italic_font)
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
        self._shown = []
        self.tree.delete(*self.tree.get_children())
        self._csv_btn.configure(state="disabled")
        self._write_btn.configure(state="disabled")

    def _pick_save(self):
        p = filedialog.askopenfilename(title="Choose save", filetypes=[("CM saves", "*.sav"), ("All", "*.*")])
        if not p:
            return
        self.save_path.set(p)
        for ext in (".gpf2", ".rnw"):
            cand = Path(p + ext)
            if cand.exists():
                self.baseline_path.set(str(cand))
                self._logline(f"auto-selected baseline {cand.name}")
                break

    def _pick_baseline(self):
        p = filedialog.askopenfilename(title="Choose day-one baseline",
                                       filetypes=[("Baselines", "*.gpf2 *.rnw"), ("All", "*.*")])
        if p:
            self.baseline_path.set(p)

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
        self._logline(f"snapshot: {out}  ({data['player_count']:,} slots, in-game day {gd['day']} of {gd['year']})")
        self._logline("  reminder: a snapshot is only a baseline if taken on/near day one of a new save.")
        self.baseline_path.set(str(out))
        self.status.set("Snapshot written and selected as the baseline.")

    def _find(self):
        save = self.save_path.get().strip()
        base = self.baseline_path.get().strip()
        if not save or not base:
            messagebox.showinfo("Missing input", "Choose both a save file and a baseline.")
            return
        self._run_async(
            lambda: find_regens(save, base, include_empty_origin=True),
            self._find_done, "Reading save and matching against the baseline…")

    def _find_done(self, matches: list[RegenMatch]):
        self._all_matches = matches
        self._logline(f"found {len(matches):,} changed slot(s) total")
        self._refilter()

    def _refilter(self):
        if not self._all_matches:
            return
        try:
            pa_min = int(self.min_pa.get() or 0)
        except ValueError:
            pa_min = 0
        inc_pregens = self.include_pregens.get()
        fo = self.filter_original.get().strip().lower()
        fr = self.filter_regen.get().strip().lower()

        rows = []
        for m in self._all_matches:
            if m.current_pa < pa_min:
                continue
            if m.original_was_empty and not inc_pregens:
                continue
            if fo and fo not in m.original_name.lower():
                continue
            if fr and fr not in m.current_name.lower():
                continue
            rows.append(m)

        self._shown = rows
        self.tree.delete(*self.tree.get_children())
        for m in sorted(rows, key=lambda m: (-m.current_pa, m.slot)):
            self.tree.insert("", END, tags=(("pregen",) if m.original_was_empty else ()), values=(
                m.slot, m.original_name or "(pregen)", m.current_name,
                m.current_ca, m.current_pa,
            ))
        shown_note = f"{len(rows):,} regen(s) shown  (of {len(self._all_matches):,} changed slots)"
        if fo or fr:
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

        do_backup = self.backup_first.get()
        lines = [
            f"Write {len(writable):,} note(s) directly into:",
            f"    {save.name}",
            "",
            "Each regen's Notes tab will be set to their original player's name.",
            "A note you already have on a regen will be replaced; notes on",
            "everyone else are left untouched.",
        ]
        if too_long:
            lines.append(f"\n{len(too_long)} skipped — original name too long for the Notes field.")
        lines.append("\nBack up the save first." if do_backup
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
