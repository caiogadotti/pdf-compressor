import ctypes
import os
import re
import sys
import threading
from tkinter import PhotoImage, filedialog

import customtkinter as ctk
from tkinterdnd2 import DND_FILES, TkinterDnD

from core import collect_pdfs, compress_pdf

ACCENT = "#2563EB"
ACCENT_HOVER = "#1D4ED8"
TEXT_DARK = "#1F2937"
TEXT_MUTED = "#6B7280"
BG = "#F5F6F8"
CARD = "#FFFFFF"
BORDER = "#E3E7EA"

ctk.set_appearance_mode("light")
ctk.set_default_color_theme("blue")


def resource_path(name):
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, name)


def parse_drop_data(data):
    """Turns the raw drop-event string into a list of paths."""
    return [p.strip("{}") for p in re.findall(r"\{[^}]*\}|\S+", data)]


class App(ctk.CTk, TkinterDnD.DnDWrapper):
    def __init__(self):
        super().__init__()
        self.TkdndVersion = TkinterDnD._require(self)
        self.title("PDF Compressor")
        self.geometry("620x640")
        self.minsize(560, 560)
        self.configure(fg_color=BG)

        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("pdfcompressor.app.1.0.0")
        except Exception:
            pass

        try:
            self.iconbitmap(resource_path("icon.ico"))
            self._icon_photo = PhotoImage(file=resource_path("icon.png"))
            self.iconphoto(True, self._icon_photo)
        except Exception:
            pass

        self.selected = []
        self.last_output_dir = None

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        container = ctk.CTkFrame(self, fg_color="transparent")
        container.grid(row=0, column=0, sticky="nsew", padx=24, pady=24)
        container.grid_columnconfigure(0, weight=1)
        container.grid_rowconfigure(3, weight=1)

        # ---------- Header ----------
        header = ctk.CTkFrame(container, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", pady=(0, 20))
        header.grid_columnconfigure(1, weight=1)

        badge = ctk.CTkFrame(header, width=44, height=44, corner_radius=12, fg_color=ACCENT)
        badge.grid(row=0, column=0, rowspan=2, sticky="w")
        badge.grid_propagate(False)
        ctk.CTkLabel(badge, text="📄", font=ctk.CTkFont(size=20), text_color="white").place(
            relx=0.5, rely=0.5, anchor="center"
        )

        texts = ctk.CTkFrame(header, fg_color="transparent")
        texts.grid(row=0, column=1, rowspan=2, sticky="w", padx=(14, 0))

        ctk.CTkLabel(
            texts, text="PDF Compressor", font=ctk.CTkFont(size=20, weight="bold"), text_color=TEXT_DARK
        ).pack(anchor="w")
        ctk.CTkLabel(
            texts,
            text="Shrink PDF file size for email, WhatsApp and uploads",
            font=ctk.CTkFont(size=12),
            text_color=TEXT_MUTED,
        ).pack(anchor="w")

        # ---------- Drop area ----------
        self.drop_area = ctk.CTkFrame(
            container, fg_color=CARD, corner_radius=14, border_width=2, border_color=BORDER
        )
        self.drop_area.grid(row=1, column=0, sticky="ew", pady=(0, 14))
        self.drop_area.grid_columnconfigure(0, weight=1)

        self.drop_icon = ctk.CTkLabel(self.drop_area, text="📄", font=ctk.CTkFont(size=34), text_color=ACCENT)
        self.drop_icon.pack(pady=(28, 6))

        self.drop_title = ctk.CTkLabel(
            self.drop_area,
            text="Drag PDF files or a folder here",
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color=TEXT_DARK,
        )
        self.drop_title.pack()

        self.drop_sub = ctk.CTkLabel(
            self.drop_area, text="or use the buttons below", font=ctk.CTkFont(size=12), text_color=TEXT_MUTED
        )
        self.drop_sub.pack(pady=(2, 20))

        for widget in (self.drop_area, self.drop_icon, self.drop_title, self.drop_sub):
            widget.drop_target_register(DND_FILES)
            widget.dnd_bind("<<Drop>>", self.on_drop)
            widget.dnd_bind("<<DragEnter>>", self.on_drag_enter)
            widget.dnd_bind("<<DragLeave>>", self.on_drag_leave)

        # ---------- Selection buttons ----------
        buttons_frame = ctk.CTkFrame(container, fg_color="transparent")
        buttons_frame.grid(row=2, column=0, sticky="ew", pady=(0, 14))
        buttons_frame.grid_columnconfigure((0, 1, 2), weight=1)

        ctk.CTkButton(
            buttons_frame,
            text="Select file(s)",
            fg_color=ACCENT,
            hover_color=ACCENT_HOVER,
            text_color="white",
            corner_radius=8,
            height=36,
            command=self.select_files,
        ).grid(row=0, column=0, padx=(0, 6), sticky="ew")

        ctk.CTkButton(
            buttons_frame,
            text="Select folder",
            fg_color=ACCENT,
            hover_color=ACCENT_HOVER,
            text_color="white",
            corner_radius=8,
            height=36,
            command=self.select_folder,
        ).grid(row=0, column=1, padx=6, sticky="ew")

        ctk.CTkButton(
            buttons_frame,
            text="Clear",
            fg_color="transparent",
            hover_color="#EDEFF1",
            text_color=TEXT_MUTED,
            border_width=1,
            border_color=BORDER,
            corner_radius=8,
            height=36,
            command=self.clear,
        ).grid(row=0, column=2, padx=(6, 0), sticky="ew")

        # ---------- Selection / log ----------
        self.selection_card = ctk.CTkFrame(container, fg_color=CARD, corner_radius=14, border_width=1, border_color=BORDER)
        self.selection_card.grid(row=3, column=0, sticky="nsew", pady=(0, 14))
        self.selection_card.grid_columnconfigure(0, weight=1)
        self.selection_card.grid_rowconfigure(1, weight=1)

        self.selection_title = ctk.CTkLabel(
            self.selection_card,
            text="Nothing selected yet",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=TEXT_MUTED,
            anchor="w",
        )
        self.selection_title.grid(row=0, column=0, sticky="ew", padx=16, pady=(12, 4))

        self.log_box = ctk.CTkTextbox(
            self.selection_card,
            font=ctk.CTkFont(family="Consolas", size=12),
            fg_color=CARD,
            text_color=TEXT_DARK,
            border_width=0,
            wrap="none",
        )
        self.log_box.grid(row=1, column=0, sticky="nsew", padx=16, pady=(0, 12))
        self.log_box.configure(state="disabled")

        # ---------- Footer ----------
        footer = ctk.CTkFrame(container, fg_color="transparent")
        footer.grid(row=4, column=0, sticky="ew")
        footer.grid_columnconfigure(0, weight=1)

        self.progress = ctk.CTkProgressBar(footer, progress_color=ACCENT, fg_color=BORDER, height=8)
        self.progress.set(0)
        self.progress.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 12))

        self.status_label = ctk.CTkLabel(footer, text="", font=ctk.CTkFont(size=12), text_color=TEXT_MUTED)
        self.status_label.grid(row=1, column=0, sticky="w")

        final_buttons = ctk.CTkFrame(footer, fg_color="transparent")
        final_buttons.grid(row=1, column=1, sticky="e")

        self.btn_open_folder = ctk.CTkButton(
            final_buttons,
            text="Open folder",
            fg_color="transparent",
            hover_color="#EDEFF1",
            text_color=ACCENT,
            border_width=1,
            border_color=ACCENT,
            corner_radius=8,
            height=38,
            width=110,
            command=self.open_output_folder,
            state="disabled",
        )
        self.btn_open_folder.grid(row=0, column=0, padx=(0, 8))

        self.btn_compress = ctk.CTkButton(
            final_buttons,
            text="Compress",
            fg_color=ACCENT,
            hover_color=ACCENT_HOVER,
            text_color="white",
            corner_radius=8,
            height=38,
            width=140,
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self.start_compress,
        )
        self.btn_compress.grid(row=0, column=1)

    # ---------- Drag & drop ----------
    def on_drag_enter(self, _event):
        self.drop_area.configure(border_color=ACCENT, fg_color="#EAF1FE")

    def on_drag_leave(self, _event):
        self.drop_area.configure(border_color=BORDER, fg_color=CARD)

    def on_drop(self, event):
        self.on_drag_leave(event)
        paths = [p for p in parse_drop_data(event.data) if os.path.exists(p)]
        if paths:
            self.selected = paths
            self.update_selection_label()

    # ---------- Manual selection ----------
    def select_files(self):
        files = filedialog.askopenfilenames(title="Select one or more PDFs", filetypes=[("PDF", "*.pdf")])
        if files:
            self.selected = list(files)
            self.update_selection_label()

    def select_folder(self):
        folder = filedialog.askdirectory(title="Select the folder with PDFs")
        if folder:
            self.selected = [folder]
            self.update_selection_label()

    def clear(self):
        self.selected = []
        self.last_output_dir = None
        self.update_selection_label()
        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.configure(state="disabled")
        self.progress.set(0)
        self.status_label.configure(text="")
        self.btn_open_folder.configure(state="disabled")

    def update_selection_label(self):
        if not self.selected:
            self.selection_title.configure(text="Nothing selected yet")
            return
        if len(self.selected) == 1 and os.path.isdir(self.selected[0]):
            self.selection_title.configure(text=f"Selected folder: {self.selected[0]}")
        else:
            self.selection_title.configure(text=f"{len(self.selected)} file(s) selected")

    # ---------- Log ----------
    def log(self, text):
        self.log_box.configure(state="normal")
        self.log_box.insert("end", text + "\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def open_output_folder(self):
        if self.last_output_dir and os.path.isdir(self.last_output_dir):
            os.startfile(self.last_output_dir)

    # ---------- Compression ----------
    def start_compress(self):
        if not self.selected:
            self.status_label.configure(text="Select files or a folder first.", text_color="#DC2626")
            return
        self.btn_compress.configure(state="disabled", text="Compressing...")
        self.btn_open_folder.configure(state="disabled")
        self.status_label.configure(text="Processing...", text_color=TEXT_MUTED)
        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.configure(state="disabled")
        threading.Thread(target=self.compress, daemon=True).start()

    def compress(self):
        jobs = collect_pdfs(self.selected)
        if not jobs:
            self.log("No PDF found in the selection.")
            self.status_label.configure(text="No PDF found.", text_color="#DC2626")
            self.btn_compress.configure(state="normal", text="Compress")
            return

        total = len(jobs)
        total_before = 0
        total_after = 0
        ok = 0
        failed = 0
        output_dir = None

        for i, (src, dest_dir) in enumerate(jobs, start=1):
            os.makedirs(dest_dir, exist_ok=True)
            output_dir = dest_dir
            out_path = os.path.join(dest_dir, os.path.basename(src))
            try:
                before = os.path.getsize(src)
                compress_pdf(src, out_path)
                after = os.path.getsize(out_path)
                total_before += before
                total_after += after
                ok += 1
                pct = (1 - after / before) * 100 if before else 0
                self.log(f"OK   {os.path.basename(src)}   {before/1024:.0f}KB → {after/1024:.0f}KB  ({pct:.0f}% smaller)")
            except Exception as e:
                failed += 1
                self.log(f"ERROR {os.path.basename(src)}: {e}")

            self.progress.set(i / total)
            self.status_label.configure(text=f"{i}/{total} files processed", text_color=TEXT_MUTED)

        self.log(f"\n{ok} file(s) compressed, {failed} failed.")
        if total_before:
            reduction = (1 - total_after / total_before) * 100
            self.log(f"Total: {total_before/1024/1024:.2f}MB → {total_after/1024/1024:.2f}MB ({reduction:.0f}% smaller)")
            self.status_label.configure(
                text=f"Done: {total_before/1024/1024:.1f}MB → {total_after/1024/1024:.1f}MB",
                text_color=ACCENT,
            )
        else:
            self.status_label.configure(text="Done.", text_color=ACCENT)

        self.last_output_dir = output_dir
        self.btn_open_folder.configure(state="normal" if output_dir else "disabled")
        self.btn_compress.configure(state="normal", text="Compress")


if __name__ == "__main__":
    App().mainloop()
