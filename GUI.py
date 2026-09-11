"""Efi's Photo Studio — a local, non-destructive desktop image workspace."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from queue import Empty, Queue
import tkinter as tk
from tkinter import filedialog, messagebox

import customtkinter as ctk
from PIL import Image, ImageDraw, ImageTk

from image_processing import EFFECTS, EFFECT_BY_KEY, apply_effect, export_batch, list_images, read_image

BG = '#151719'
PANEL = '#1c1f22'
RAISED = '#25292d'
BORDER = '#34393d'
TEXT = '#eeeae2'
MUTED = '#969e9f'
ACCENT = '#dfb879'
INK = '#211d17'


class PhotoStudio(ctk.CTk):
    def __init__(self, initial: Path | None = None):
        ctk.set_appearance_mode('dark')
        super().__init__()
        self.title("Efi's Photo Studio")
        self.geometry('1380x900')
        self.minsize(1080, 720)
        self.configure(fg_color=BG)
        self.font_family = 'Helvetica Neue' if self.tk.call('tk', 'windowingsystem') == 'aqua' else 'Arial'
        self.paths: list[Path] = []
        self.active_path: Path | None = None
        self.original: Image.Image | None = None
        self.processed: Image.Image | None = None
        self.effect: str | None = None
        self.compare_fraction = .5
        self.image_bounds = None
        self.roi = None
        self.selecting_subject = False
        self.drag_start = None
        self.generation = 0
        self.exporting = False
        self.closed = False
        self.jobs = ThreadPoolExecutor(max_workers=2, thread_name_prefix='photo-studio')
        self.events = Queue()
        self.preview_job = None
        self.render_timer = None
        self.threshold_timer = None
        self.effect_buttons = {}
        self.directory = tk.StringVar()
        self.destination = tk.StringVar()
        self.threshold = tk.IntVar(value=40)
        self.view = tk.StringVar(value='Compare')
        self._build()
        self.protocol('WM_DELETE_WINDOW', self.close)
        for shortcut in ('<Control-o>', '<Command-o>'):
            self.bind(shortcut, lambda event: self.open_folder())
        self.bind('<Control-s>', lambda event: self.export())
        self.bind('<Command-s>', lambda event: self.export())
        self.after(70, self._poll)
        if initial:
            self.after(200, lambda: self.load_folder(initial if initial.is_dir() else initial.parent, initial))

    def label(self, parent, text, size=13, color=TEXT, weight='normal', **kwargs):
        return ctk.CTkLabel(parent, text=text, text_color=color,
                            font=(self.font_family, size, weight), **kwargs)

    def button(self, parent, text, command, primary=False, **kwargs):
        return ctk.CTkButton(parent, text=text, command=command, height=36,
                             corner_radius=7, fg_color=ACCENT if primary else RAISED,
                             hover_color='#efcb94' if primary else '#353b40',
                             text_color=INK if primary else TEXT,
                             font=(self.font_family, 12, 'bold'), **kwargs)

    def _build(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        header = ctk.CTkFrame(self, fg_color=PANEL, corner_radius=0, height=86)
        header.grid(row=0, column=0, sticky='ew')
        header.grid_columnconfigure(1, weight=1)
        mark = ctk.CTkFrame(header, width=40, height=40, corner_radius=10, fg_color=ACCENT)
        mark.grid(row=0, column=0, padx=(24, 14), pady=20)
        mark.grid_propagate(False)
        self.label(mark, 'e.', 26, INK, 'bold').place(relx=.5, rely=.45, anchor='center')
        titles = ctk.CTkFrame(header, fg_color='transparent')
        titles.grid(row=0, column=1, sticky='w')
        self.label(titles, "Efi's Photo Studio", 22, weight='bold').pack(anchor='w')
        self.label(titles, 'A little more focus. A different point of view.', 12, MUTED).pack(anchor='w')
        self.button(header, 'Try sample collection', self.open_samples, width=150).grid(row=0, column=2, padx=18)
        self.button(header, 'Open folder', self.open_folder, width=112).grid(row=0, column=3, padx=(0, 24))

        body = ctk.CTkFrame(self, fg_color=BG, corner_radius=0)
        body.grid(row=1, column=0, sticky='nsew', padx=18, pady=(18, 12))
        body.grid_columnconfigure(1, weight=1)
        body.grid_rowconfigure(0, weight=1)
        library = ctk.CTkFrame(body, fg_color=PANEL, width=220, corner_radius=10)
        library.grid(row=0, column=0, sticky='nsew', padx=(0, 12))
        library.grid_propagate(False)
        library.grid_columnconfigure(0, weight=1)
        library.grid_rowconfigure(4, weight=1)
        self.label(library, '01  /  LIBRARY', 11, ACCENT, 'bold').grid(row=0, column=0, sticky='w', padx=18, pady=(18, 4))
        self.library_count = self.label(library, 'Your images, together.', 13)
        self.library_count.grid(row=1, column=0, sticky='w', padx=18, pady=(0, 12))
        path_entry = ctk.CTkEntry(library, textvariable=self.directory, height=34,
                                 fg_color=BG, border_color=BORDER, font=(self.font_family, 11))
        path_entry.grid(row=2, column=0, sticky='ew', padx=14)
        path_entry.bind('<Return>', lambda event: self.load_folder(Path(self.directory.get()).expanduser()))
        self.label(library, 'Paste a folder path and press Return', 10, MUTED).grid(row=3, column=0, pady=(5, 12))
        self.file_list = tk.Listbox(library, selectmode=tk.EXTENDED, exportselection=False,
                                   bg=PANEL, fg=TEXT, selectbackground='#4a4438', selectforeground='#f5d39d',
                                   activestyle='none', highlightthickness=0, bd=0,
                                   font=(self.font_family, 12), relief='flat')
        self.file_list.grid(row=4, column=0, sticky='nsew', padx=(14, 4))
        scrollbar = ctk.CTkScrollbar(library, command=self.file_list.yview, width=10)
        scrollbar.grid(row=4, column=1, sticky='ns', padx=(0, 4))
        self.file_list.configure(yscrollcommand=scrollbar.set)
        self.file_list.bind('<<ListboxSelect>>', self.select_image)
        self.label(library, 'Shift / Cmd / Ctrl for batch selection', 10, MUTED).grid(row=5, column=0, pady=(12, 8))
        actions = ctk.CTkFrame(library, fg_color='transparent')
        actions.grid(row=6, column=0, sticky='ew', padx=14, pady=(0, 16))
        self.button(actions, 'Select all', self.select_all, width=88).pack(side='left')
        self.button(actions, 'Clear', self.clear, width=78).pack(side='right')

        workspace = ctk.CTkFrame(body, fg_color=PANEL, corner_radius=10)
        workspace.grid(row=0, column=1, sticky='nsew', padx=(0, 12))
        workspace.grid_columnconfigure(0, weight=1)
        workspace.grid_rowconfigure(2, weight=1)
        titlebar = ctk.CTkFrame(workspace, fg_color='transparent')
        titlebar.grid(row=0, column=0, sticky='ew', padx=20, pady=(16, 12))
        titlebar.grid_columnconfigure(0, weight=1)
        self.file_title = self.label(titlebar, 'Room for a new perspective.', 18, weight='bold', anchor='w')
        self.file_title.grid(row=0, column=0, sticky='w')
        self.label(titlebar, 'FIT', 10, ACCENT, 'bold').grid(row=0, column=1, padx=(12, 0))
        viewbar = ctk.CTkFrame(workspace, fg_color='transparent')
        viewbar.grid(row=1, column=0, sticky='ew', padx=20, pady=(0, 12))
        self.view_switch = ctk.CTkSegmentedButton(viewbar, values=['Compare', 'Original', 'Result'],
                            variable=self.view, command=lambda value: self.schedule_render(),
                            selected_color='#484235', selected_hover_color='#5a5140',
                            unselected_color=RAISED, unselected_hover_color=BORDER,
                            fg_color=RAISED, text_color=TEXT, height=30,
                            font=(self.font_family, 12))
        self.view_switch.pack(side='left')
        self.button(viewbar, 'Reset effect', self.reset_effect, width=100).pack(side='right')
        self.canvas = tk.Canvas(workspace, bg='#111315', highlightthickness=0, bd=0)
        self.canvas.grid(row=2, column=0, sticky='nsew', padx=12)
        self.canvas.bind('<Configure>', lambda event: self.schedule_render())
        self.canvas.bind('<Button-1>', self.pointer_down)
        self.canvas.bind('<B1-Motion>', self.pointer_move)
        self.canvas.bind('<ButtonRelease-1>', self.pointer_up)
        self.metadata = self.label(workspace, 'Open a folder to begin. Every edit starts from the original.', 11, MUTED)
        self.metadata.grid(row=3, column=0, pady=16)

        inspector = ctk.CTkFrame(body, width=270, fg_color=PANEL, corner_radius=10)
        inspector.grid(row=0, column=2, sticky='nsew')
        inspector.grid_propagate(False)
        inspector.grid_columnconfigure(0, weight=1)
        inspector.grid_rowconfigure(2, weight=1)
        self.label(inspector, '02  /  DEVELOP', 11, ACCENT, 'bold').grid(row=0, column=0, sticky='w', padx=18, pady=(18, 4))
        self.label(inspector, 'Small changes. New character.', 13).grid(row=1, column=0, sticky='w', padx=18, pady=(0, 10))
        effects = ctk.CTkScrollableFrame(inspector, fg_color='transparent', corner_radius=0)
        effects.grid(row=2, column=0, sticky='nsew', padx=10)
        effects.grid_columnconfigure(0, weight=1)
        row = 0
        for group in ('Transform', 'Color & tone', 'Segmentation', 'Creative', 'Refine'):
            self.label(effects, group.upper(), 10, MUTED, 'bold').grid(row=row, column=0, sticky='w', padx=4, pady=(12, 5))
            row += 1
            for effect in (e for e in EFFECTS if e.group == group):
                button = self.button(effects, effect.name, lambda key=effect.key: self.choose_effect(key), anchor='w')
                button.grid(row=row, column=0, sticky='ew', pady=3)
                self.effect_buttons[effect.key] = button
                row += 1
        self.effect_info = self.label(inspector, 'Choose an effect to preview it.\nYour original stays untouched.', 11, MUTED,
                                      wraplength=230, justify='left', anchor='w')
        self.effect_info.grid(row=3, column=0, sticky='ew', padx=18, pady=(12, 6))
        self.threshold_box = ctk.CTkFrame(inspector, fg_color=RAISED, corner_radius=7)
        self.threshold_box.grid(row=4, column=0, sticky='ew', padx=16, pady=8)
        self.threshold_box.grid_columnconfigure(0, weight=1)
        self.label(self.threshold_box, 'Edge threshold', 11).grid(row=0, column=0, sticky='w', padx=12, pady=(8, 0))
        self.threshold_text = self.label(self.threshold_box, '40', 11, ACCENT)
        self.threshold_text.grid(row=0, column=1, padx=12, pady=(8, 0))
        self.slider = ctk.CTkSlider(self.threshold_box, from_=1, to=199, number_of_steps=198,
                                  variable=self.threshold, command=self.change_threshold,
                                  progress_color=ACCENT, button_color=ACCENT, button_hover_color='#efcb94')
        self.slider.grid(row=1, column=0, columnspan=2, sticky='ew', padx=12, pady=12)
        self.threshold_box.grid_remove()
        self.subject_button = self.button(inspector, 'Draw subject rectangle', self.mark_subject)
        self.subject_button.grid(row=4, column=0, sticky='ew', padx=16, pady=8)
        self.subject_button.grid_remove()
        self.label(inspector, '03  /  EXPORT', 11, ACCENT, 'bold').grid(row=5, column=0, sticky='w', padx=18, pady=(14, 8))
        destination = ctk.CTkFrame(inspector, fg_color='transparent')
        destination.grid(row=6, column=0, sticky='ew', padx=16)
        destination.grid_columnconfigure(0, weight=1)
        ctk.CTkEntry(destination, textvariable=self.destination, placeholder_text='Output folder',
                     border_color=BORDER, fg_color=BG, height=34, font=(self.font_family, 11)).grid(row=0, column=0, sticky='ew')
        self.button(destination, '…', self.choose_destination, width=34).grid(row=0, column=1, padx=(6, 0))
        self.export_button = self.button(inspector, 'Export selected', self.export, primary=True)
        self.export_button.grid(row=7, column=0, sticky='ew', padx=16, pady=(10, 8))
        self.export_button.configure(state='disabled')
        self.label(inspector, 'Full resolution · New files · No overwrites', 10, MUTED).grid(row=8, column=0, pady=(0, 16))
        footer = ctk.CTkFrame(self, fg_color='transparent')
        footer.grid(row=2, column=0, sticky='ew', padx=24, pady=(0, 12))
        footer.grid_columnconfigure(0, weight=1)
        self.status = self.label(footer, 'Ready when you are.', 11, MUTED, anchor='w')
        self.status.grid(row=0, column=0, sticky='ew')
        self.progress = ctk.CTkProgressBar(footer, width=120, height=3, progress_color=ACCENT, fg_color=BORDER)
        self.progress.grid(row=0, column=1, padx=20)
        self.progress.set(0)
        self.label(footer, 'PHOTO STUDIO   /   2.0', 10, MUTED).grid(row=0, column=2)

    def open_folder(self):
        path = filedialog.askdirectory(title='Choose your image folder', parent=self)
        if path:
            self.load_folder(Path(path))

    def open_samples(self):
        folder = Path(__file__).resolve().parent / 'docs' / 'samples'
        self.load_folder(folder, folder / 'cheerful-puppy.png')

    def load_folder(self, path: Path, preferred: Path | None = None):
        try:
            paths = list_images(path)
        except OSError as error:
            messagebox.showerror('Could not open folder', str(error), parent=self)
            return
        self.clear()
        self.paths = paths
        self.directory.set(str(path.resolve()))
        self.file_list.delete(0, tk.END)
        for item in paths:
            self.file_list.insert(tk.END, item.name)
        self.library_count.configure(text=f'{len(paths):02d} images in this folder')
        if paths:
            index = paths.index(preferred) if preferred in paths else 0
            self.file_list.selection_set(index)
            self.file_list.activate(index)
            self.file_list.see(index)
            self.select_image()
        else:
            self.status.configure(text='No supported images in this folder. Try PNG, JPG, GIF, BMP, TIFF, or WebP.')

    def _submit(self, kind, token, function, *args):
        future = self.jobs.submit(function, *args)
        future.add_done_callback(lambda completed: self.events.put((kind, token, completed)))
        return future

    def select_image(self, event=None):
        selected = self.file_list.curselection()
        self.update_export_button()
        if not selected:
            return
        active = self.file_list.index(tk.ACTIVE)
        index = active if active in selected else selected[0]
        path = self.paths[index]
        if path == self.active_path and self.original is not None:
            return
        self.generation += 1
        self.active_path = path
        self.roi = None
        self.original = self.processed = None
        self.file_title.configure(text=path.name[:46] + ('…' if len(path.name) > 46 else ''))
        self.metadata.configure(text='Loading full-resolution original…')
        self.status.configure(text=f'Opening {path.name}…')
        self.schedule_render()
        self._submit('load', self.generation, read_image, path)

    def select_all(self):
        self.file_list.selection_set(0, tk.END)
        self.select_image()

    def choose_effect(self, key):
        self.effect = key
        for name, button in self.effect_buttons.items():
            button.configure(fg_color='#484235' if name == key else RAISED,
                             text_color='#f1d09d' if name == key else TEXT)
        self.effect_info.configure(text=EFFECT_BY_KEY[key].description)
        if key == 'edge':
            self.threshold_box.grid()
        else:
            self.threshold_box.grid_remove()
        self.selecting_subject = False
        self.canvas.configure(cursor='')
        if key == 'cutout':
            self.subject_button.grid()
        else:
            self.subject_button.grid_remove()
        self.request_preview()
        self.update_export_button()

    def change_threshold(self, value):
        self.threshold_text.configure(text=str(round(value)))
        if self.threshold_timer:
            self.after_cancel(self.threshold_timer)
        self.threshold_timer = self.after(180, self.request_preview)

    def request_preview(self):
        self.threshold_timer = None
        if self.original is None or self.effect is None:
            return
        self.generation += 1
        if self.preview_job:
            self.preview_job.cancel()
        self.processed = None
        self.status.configure(text=f'Developing {EFFECT_BY_KEY[self.effect].name.lower()}…')
        self.metadata.configure(text='Processing at full resolution…')
        self.schedule_render()
        self.preview_job = self._submit('preview', self.generation, apply_effect,
                                        self.original, self.effect, int(self.threshold.get()), self.roi)

    def reset_effect(self):
        # Do not invalidate an in-flight load: it should still show the selected original.
        if self.original is not None:
            self.generation += 1
        self.effect = None
        self.processed = None
        for button in self.effect_buttons.values():
            button.configure(fg_color=RAISED, text_color=TEXT)
        self.threshold_box.grid_remove()
        self.subject_button.grid_remove()
        self.selecting_subject = False
        self.canvas.configure(cursor='')
        self.effect_info.configure(text='Choose an effect to preview it.\nYour original stays untouched.')
        self.status.configure(text='Original restored. Choose a new effect whenever you like.')
        self.update_export_button()
        self.schedule_render()
        self.update_metadata()

    def clear(self):
        self.generation += 1
        self.paths = []
        self.active_path = None
        self.original = self.processed = None
        self.file_list.delete(0, tk.END)
        self.directory.set('')
        self.destination.set('')
        self.file_title.configure(text='Room for a new perspective.')
        self.library_count.configure(text='Your images, together.')
        self.reset_effect()

    def _poll(self):
        if self.closed:
            return
        try:
            while True:
                kind, token, future = self.events.get_nowait()
                if kind == 'progress':
                    done, total = future
                    self.progress.set(done / max(1, total))
                    self.status.configure(text=f'Exporting {done} of {total} images…')
                    continue
                if kind != 'export' and token != self.generation:
                    continue
                try:
                    result = future.result()
                except Exception as error:
                    if kind == 'export':
                        self.exporting = False
                    self.status.configure(text=f'Could not complete {kind}: {error}')
                    self.update_export_button()
                    messagebox.showerror('Could not complete operation', str(error), parent=self)
                    continue
                if kind == 'load':
                    self.original = result
                    self.update_metadata()
                    if self.effect:
                        self.request_preview()
                    else:
                        self.status.configure(text='Original loaded. Choose an effect in Develop.')
                        self.schedule_render()
                elif kind == 'preview':
                    self.processed = result
                    self.update_metadata()
                    self.status.configure(text='Preview ready. Export applies this effect to each selected original.')
                    self.schedule_render()
                elif kind == 'export':
                    self.exporting = False
                    self.update_export_button()
                    summary = f'Exported {len(result.saved)} image(s). Originals preserved.'
                    self.status.configure(text=summary)
                    if result.errors:
                        details = '\n'.join(f'{p.name}: {error}' for p, error in result.errors[:8])
                        messagebox.showwarning('Export completed with errors', summary + '\n\n' + details, parent=self)
                    else:
                        messagebox.showinfo('Export complete', summary, parent=self)
        except Empty:
            pass
        self.after(70, self._poll)

    def update_metadata(self):
        if self.original is None:
            self.metadata.configure(text='Open a folder to begin. Every edit starts from the original.')
            return
        w, h = self.original.size
        suffix = f'    →    {self.processed.width:,} × {self.processed.height:,}' if self.processed is not None else ''
        self.metadata.configure(text=f'{w:,} × {h:,} px{suffix}    /    {self.original.mode}    /    Fit to workspace')

    def schedule_render(self):
        if self.render_timer:
            self.after_cancel(self.render_timer)
        self.render_timer = self.after(60, self.render_preview)

    def move_divider(self, event):
        if self.view.get() == 'Compare' and self.processed is not None and self.image_bounds:
            x, y, width, height = self.image_bounds
            self.compare_fraction = max(.03, min(.97, (event.x - x) / width))
            self.schedule_render()

    def mark_subject(self):
        if self.original is None:
            return
        self.selecting_subject = True
        self.view.set('Original')
        self.canvas.configure(cursor='crosshair')
        self.status.configure(text='Drag a rectangle enclosing the whole subject, with some background outside it.')
        self.schedule_render()

    def pointer_down(self, event):
        if self.selecting_subject:
            self.drag_start = (event.x, event.y)
        else:
            self.move_divider(event)

    def pointer_move(self, event):
        if self.selecting_subject and self.drag_start:
            self.canvas.delete('subject-box')
            self.canvas.create_rectangle(*self.drag_start, event.x, event.y, outline=ACCENT,
                                         width=2, dash=(5, 3), tags='subject-box')
        else:
            self.move_divider(event)

    def pointer_up(self, event):
        if not (self.selecting_subject and self.drag_start and self.image_bounds):
            return
        x, y, width, height = self.image_bounds
        x0, y0 = self.drag_start
        clamp = lambda value: max(0, min(1, value))
        self.roi = (clamp((min(x0, event.x)-x)/width), clamp((min(y0, event.y)-y)/height),
                    clamp((max(x0, event.x)-x)/width), clamp((max(y0, event.y)-y)/height))
        self.drag_start = None
        self.selecting_subject = False
        self.canvas.configure(cursor='')
        self.view.set('Result')
        self.request_preview()

    def render_preview(self):
        self.render_timer = None
        canvas = self.canvas
        canvas.delete('all')
        w, h = canvas.winfo_width(), canvas.winfo_height()
        if w < 20 or h < 20:
            return
        if self.original is None:
            canvas.create_oval(w / 2 - 30, h / 2 - 92, w / 2 + 30, h / 2 - 32, outline=ACCENT, width=2)
            canvas.create_line(w / 2 - 15, h / 2 - 62, w / 2 + 15, h / 2 - 62, fill=ACCENT, width=2)
            canvas.create_line(w / 2, h / 2 - 77, w / 2, h / 2 - 47, fill=ACCENT, width=2)
            canvas.create_text(w / 2, h / 2, text='Every image has another side.', fill=TEXT,
                               font=(self.font_family, 20), width=w-50)
            canvas.create_text(w / 2, h / 2 + 44, text='Open a folder. Choose an image. Make it yours.',
                               fill=MUTED, font=(self.font_family, 12), width=w-70)
            return
        original = self.original
        result = self.processed if self.processed is not None else original
        compare = self.view.get() == 'Compare' and self.processed is not None
        image = original if self.view.get() == 'Original' else result
        # Fit into one common viewport so the before/after divider stays aligned.
        size = original.size if compare else image.size
        scale = min((w - 44) / size[0], (h - 90) / size[1], 1.0)
        fitted = (max(1, int(size[0] * scale)), max(1, int(size[1] * scale)))
        def display(source):
            rgba = source.convert('RGBA').resize(fitted, Image.Resampling.LANCZOS)
            checker = Image.new('RGBA', fitted, '#292d30')
            draw = ImageDraw.Draw(checker)
            for y in range(0, fitted[1], 16):
                for x in range(0, fitted[0], 16):
                    if (x // 16 + y // 16) % 2:
                        draw.rectangle((x, y, x + 15, y + 15), fill='#32373a')
            return Image.alpha_composite(checker, rgba).convert('RGB')
        visible = display(original if compare else image)
        split = int(fitted[0] * self.compare_fraction)
        if compare:
            after = display(result)
            visible.paste(after.crop((split, 0, fitted[0], fitted[1])), (split, 0))
        self.canvas_image = ImageTk.PhotoImage(visible)
        x, y = (w - fitted[0]) // 2, (h - fitted[1]) // 2
        self.image_bounds = (x, y, fitted[0], fitted[1])
        canvas.create_image(x, y, image=self.canvas_image, anchor='nw')
        caption = 'ORIGINAL' if self.view.get() == 'Original' or self.effect is None else ('BEFORE' if compare else 'RESULT')
        canvas.create_text(x, y - 18, anchor='w', text=caption, fill=MUTED, font=(self.font_family, 10))
        if compare:
            canvas.create_text(x + fitted[0], y - 18, anchor='e', text='AFTER  /  ' + EFFECT_BY_KEY[self.effect].name.upper(),
                               fill=ACCENT, font=(self.font_family, 10))
            divider = x + split
            canvas.create_line(divider, y, divider, y + fitted[1], fill=ACCENT, width=2)
            canvas.create_oval(divider - 12, y + fitted[1] // 2 - 12, divider + 12, y + fitted[1] // 2 + 12,
                               fill=ACCENT, outline=BG)
            canvas.create_text(divider, y + fitted[1] // 2, text='↔', fill=INK, font=(self.font_family, 12))
        canvas.create_text(w // 2, h - 18, text=f'ONE ORIGINAL. {len(EFFECTS)} POSSIBILITIES.', fill='#677074',
                           font=(self.font_family, 9))

    def choose_destination(self):
        path = filedialog.askdirectory(title='Choose an export folder', parent=self)
        if path:
            self.destination.set(path)

    def update_export_button(self):
        count = len(self.file_list.curselection())
        enabled = bool(count and self.effect and not self.exporting)
        self.export_button.configure(state='normal' if enabled else 'disabled',
                                     text='Exporting…' if self.exporting else f'Export selected{f" ({count})" if count else ""}')

    def export(self):
        selected = self.file_list.curselection()
        if not selected or self.effect is None or self.exporting:
            return
        if not self.destination.get().strip():
            self.choose_destination()
        if not self.destination.get().strip():
            return
        destination = Path(self.destination.get()).expanduser()
        if not destination.is_dir():
            messagebox.showerror('Choose an output folder', 'The output folder does not exist.', parent=self)
            return
        paths = [self.paths[index] for index in selected]
        self.exporting = True
        self.update_export_button()
        self.progress.set(0)
        self.status.configure(text=f'Exporting {len(paths)} image(s)…')
        self._submit('export', None, export_batch, paths, destination, self.effect, int(self.threshold.get()),
                     lambda done, total: self.events.put(('progress', None, (done, total))), self.roi)

    def close(self):
        if self.exporting:
            messagebox.showinfo('Export in progress', 'Let the current export finish before closing.', parent=self)
            return
        self.closed = True
        self.jobs.shutdown(wait=False, cancel_futures=True)
        self.destroy()


def main():
    parser = argparse.ArgumentParser(description="Efi's Photo Studio — local image editing")
    parser.add_argument('path', nargs='?', type=Path, help='Image or folder to open')
    args = parser.parse_args()
    PhotoStudio(args.path).mainloop()


if __name__ == '__main__':
    main()
