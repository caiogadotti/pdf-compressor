import ctypes
import os
import re
import sys
import threading
from tkinter import PhotoImage, filedialog

import customtkinter as ctk
from tkinterdnd2 import DND_FILES, TkinterDnD

from core import collect_pdfs, compress_pdf, render_preview, simulate_compression

ACCENT = "#2563EB"
ACCENT_HOVER = "#1D4ED8"
TEXT_DARK = "#1F2937"
TEXT_MUTED = "#6B7280"
BG = "#F5F6F8"
CARD = "#FFFFFF"
BORDER = "#E3E7EA"

# min/max of what the slider actually drives: JPEG quality and the max side
# length embedded images get downscaled to. One slider controls both at
# once, because in practice nobody wants to tune two numbers separately,
# they want "compress more" or "compress less".
QUALITY_RANGE = (25, 90)
MAX_DIM_RANGE = (700, 2000)
DEFAULT_STRENGTH = 50

ctk.set_appearance_mode("light")
ctk.set_default_color_theme("blue")


def strength_to_params(strength):
    """Maps the slider's 1-100 "how much to compress" into (max_dim, quality).

    Higher strength = smaller max_dim and lower JPEG quality = smaller file,
    more visible loss. Both ends of the range were picked by eye: below
    quality 25 text starts smearing, above max_dim 2000 there's rarely any
    size gain worth the extra pixels for a document scan.
    """
    t = (strength - 1) / 99
    quality = round(QUALITY_RANGE[1] - t * (QUALITY_RANGE[1] - QUALITY_RANGE[0]))
    max_dim = round(MAX_DIM_RANGE[1] - t * (MAX_DIM_RANGE[1] - MAX_DIM_RANGE[0]))
    return max_dim, quality


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
        self.geometry("600x760")
        self.minsize(560, 700)
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
        self.preview_files = []
        self.preview_index = 0
        self.preview_before_image = None
        self.preview_before_ctk = None
        self.preview_after_ctk = None

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        container = ctk.CTkFrame(self, fg_color="transparent")
        container.grid(row=0, column=0, sticky="nsew", padx=18, pady=16)
        container.grid_columnconfigure(0, weight=1)
        container.grid_rowconfigure(5, weight=1)

        # ---------- Header ----------
        header = ctk.CTkFrame(container, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", pady=(0, 12))
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
        self.drop_area.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        self.drop_area.grid_columnconfigure(0, weight=1)

        self.drop_icon = ctk.CTkLabel(self.drop_area, text="📄", font=ctk.CTkFont(size=26), text_color=ACCENT)
        self.drop_icon.pack(pady=(14, 3))

        self.drop_title = ctk.CTkLabel(
            self.drop_area,
            text="Drag PDF files or a folder here",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=TEXT_DARK,
        )
        self.drop_title.pack()

        self.drop_sub = ctk.CTkLabel(
            self.drop_area, text="or use the buttons below", font=ctk.CTkFont(size=11), text_color=TEXT_MUTED
        )
        self.drop_sub.pack(pady=(2, 12))

        for widget in (self.drop_area, self.drop_icon, self.drop_title, self.drop_sub):
            widget.drop_target_register(DND_FILES)
            widget.dnd_bind("<<Drop>>", self.on_drop)
            widget.dnd_bind("<<DragEnter>>", self.on_drag_enter)
            widget.dnd_bind("<<DragLeave>>", self.on_drag_leave)

        # ---------- Selection buttons ----------
        buttons_frame = ctk.CTkFrame(container, fg_color="transparent")
        buttons_frame.grid(row=2, column=0, sticky="ew", pady=(0, 10))
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

        # ---------- Compression strength slider ----------
        slider_frame = ctk.CTkFrame(container, fg_color=CARD, corner_radius=14, border_width=1, border_color=BORDER)
        slider_frame.grid(row=3, column=0, sticky="ew", pady=(0, 14))
        slider_frame.grid_columnconfigure(0, weight=1)

        slider_header = ctk.CTkFrame(slider_frame, fg_color="transparent")
        slider_header.grid(row=0, column=0, sticky="ew", padx=16, pady=(10, 2))
        slider_header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            slider_header, text="Compression strength", font=ctk.CTkFont(size=13, weight="bold"), text_color=TEXT_DARK
        ).grid(row=0, column=0, sticky="w")
        self.strength_value_label = ctk.CTkLabel(
            slider_header, text="", font=ctk.CTkFont(size=12), text_color=TEXT_MUTED
        )
        self.strength_value_label.grid(row=0, column=1, sticky="e")

        self.strength_slider = ctk.CTkSlider(
            slider_frame, from_=1, to=100, number_of_steps=99, height=14, progress_color=ACCENT, button_color=ACCENT,
            button_hover_color=ACCENT_HOVER, command=self.on_strength_change,
        )
        self.strength_slider.set(DEFAULT_STRENGTH)
        self.strength_slider.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 4))

        scale_row = ctk.CTkFrame(slider_frame, fg_color="transparent")
        scale_row.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 10))
        scale_row.grid_columnconfigure((0, 1), weight=1)
        ctk.CTkLabel(scale_row, text="Lighter, better quality", font=ctk.CTkFont(size=11), text_color=TEXT_MUTED).grid(
            row=0, column=0, sticky="w"
        )
        ctk.CTkLabel(scale_row, text="Smaller file, more loss", font=ctk.CTkFont(size=11), text_color=TEXT_MUTED).grid(
            row=0, column=1, sticky="e"
        )

        # ---------- Before/after preview ----------
        self.preview_card = ctk.CTkFrame(container, fg_color=CARD, corner_radius=14, border_width=1, border_color=BORDER)
        self.preview_card.grid(row=4, column=0, sticky="ew", pady=(0, 10))
        self.preview_card.grid_columnconfigure(0, weight=1)

        preview_nav = ctk.CTkFrame(self.preview_card, fg_color="transparent")
        preview_nav.grid(row=0, column=0, sticky="ew", padx=12, pady=(10, 2))
        preview_nav.grid_columnconfigure(1, weight=1)

        self.btn_prev = ctk.CTkButton(
            preview_nav, text="‹", width=30, height=28, fg_color="transparent", hover_color="#EDEFF1",
            text_color=TEXT_DARK, border_width=1, border_color=BORDER, command=lambda: self.step_preview(-1),
            state="disabled",
        )
        self.btn_prev.grid(row=0, column=0)

        self.preview_filename_label = ctk.CTkLabel(
            preview_nav, text="Select files to see a preview", font=ctk.CTkFont(size=12, weight="bold"),
            text_color=TEXT_DARK,
        )
        self.preview_filename_label.grid(row=0, column=1, sticky="ew")

        self.btn_next = ctk.CTkButton(
            preview_nav, text="›", width=30, height=28, fg_color="transparent", hover_color="#EDEFF1",
            text_color=TEXT_DARK, border_width=1, border_color=BORDER, command=lambda: self.step_preview(1),
            state="disabled",
        )
        self.btn_next.grid(row=0, column=2)

        preview_images = ctk.CTkFrame(self.preview_card, fg_color="transparent")
        preview_images.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 8))
        preview_images.grid_columnconfigure((0, 1), weight=1)

        before_col = ctk.CTkFrame(preview_images, fg_color="transparent")
        before_col.grid(row=0, column=0, sticky="n", padx=(0, 6))
        ctk.CTkLabel(before_col, text="Before", font=ctk.CTkFont(size=11), text_color=TEXT_MUTED).pack()
        self.before_image_label = ctk.CTkLabel(before_col, text="", fg_color=BG, corner_radius=8, width=130, height=130)
        self.before_image_label.pack(pady=(4, 0))

        after_col = ctk.CTkFrame(preview_images, fg_color="transparent")
        after_col.grid(row=0, column=1, sticky="n", padx=(6, 0))
        ctk.CTkLabel(after_col, text="After", font=ctk.CTkFont(size=11), text_color=TEXT_MUTED).pack()
        self.after_image_label = ctk.CTkLabel(after_col, text="", fg_color=BG, corner_radius=8, width=130, height=130)
        self.after_image_label.pack(pady=(4, 0))

        # ---------- Selection / log ----------
        self.selection_card = ctk.CTkFrame(container, fg_color=CARD, corner_radius=14, border_width=1, border_color=BORDER)
        self.selection_card.grid(row=5, column=0, sticky="nsew", pady=(0, 10))
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
        footer.grid(row=6, column=0, sticky="ew")
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

        self.update_strength_label()

    # ---------- Compression strength ----------
    def update_strength_label(self):
        max_dim, quality = strength_to_params(round(self.strength_slider.get()))
        self.strength_value_label.configure(text=f"quality {quality} · up to {max_dim}px")

    def on_strength_change(self, _value):
        self.update_strength_label()
        self.update_after_preview()

    # ---------- Preview ----------
    def refresh_preview(self):
        """Rebuilds the list of previewable PDFs from the current selection and shows the first one."""
        self.preview_files = [src for src, _dest in collect_pdfs(self.selected)]
        self.preview_index = 0
        self.show_preview_at(0)

    def step_preview(self, delta):
        if not self.preview_files:
            return
        self.preview_index = (self.preview_index + delta) % len(self.preview_files)
        self.show_preview_at(self.preview_index)

    def show_preview_at(self, index):
        has_files = bool(self.preview_files)
        many = len(self.preview_files) > 1
        self.btn_prev.configure(state="normal" if many else "disabled")
        self.btn_next.configure(state="normal" if many else "disabled")

        if not has_files:
            self.preview_filename_label.configure(text="Select files to see a preview")
            self.before_image_label.configure(image=None, text="")
            self.after_image_label.configure(image=None, text="")
            self.preview_before_image = None
            return

        path = self.preview_files[index]
        counter = f"  ({index + 1}/{len(self.preview_files)})" if many else ""
        self.preview_filename_label.configure(text=f"{os.path.basename(path)}{counter}")

        try:
            self.preview_before_image = render_preview(path)
        except Exception:
            self.preview_before_image = None
            self.preview_filename_label.configure(text=f"{os.path.basename(path)} (couldn't preview this file)")
            self.before_image_label.configure(image=None, text="")
            self.after_image_label.configure(image=None, text="")
            return

        self.preview_before_ctk = ctk.CTkImage(light_image=self.preview_before_image, size=self.preview_before_image.size)
        self.before_image_label.configure(image=self.preview_before_ctk, text="")
        self.update_after_preview()

    def update_after_preview(self):
        if self.preview_before_image is None:
            return
        max_dim, quality = strength_to_params(round(self.strength_slider.get()))
        after_img = simulate_compression(self.preview_before_image, max_dim=max_dim, quality=quality)
        self.preview_after_ctk = ctk.CTkImage(light_image=after_img, size=after_img.size)
        self.after_image_label.configure(image=self.preview_after_ctk, text="")

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
            self.refresh_preview()

    # ---------- Manual selection ----------
    def select_files(self):
        files = filedialog.askopenfilenames(title="Select one or more PDFs", filetypes=[("PDF", "*.pdf")])
        if files:
            self.selected = list(files)
            self.update_selection_label()
            self.refresh_preview()

    def select_folder(self):
        folder = filedialog.askdirectory(title="Select the folder with PDFs")
        if folder:
            self.selected = [folder]
            self.update_selection_label()
            self.refresh_preview()

    def clear(self):
        self.selected = []
        self.last_output_dir = None
        self.preview_files = []
        self.preview_index = 0
        self.update_selection_label()
        self.show_preview_at(0)
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
        max_dim, quality = strength_to_params(round(self.strength_slider.get()))
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
                compress_pdf(src, out_path, max_dim=max_dim, quality=quality)
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
