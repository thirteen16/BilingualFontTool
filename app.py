import ctypes
import datetime
import json
import os
from pathlib import Path
import queue
import shutil
import sys
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from PIL import Image, ImageDraw, ImageFont, ImageTk
from font_engine import faces, build

ROOT = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).parent
RESOURCES = Path(getattr(sys, '_MEIPASS', Path(__file__).parent))
SAMPLE = '中文界面 · 文件管理器 · 设置\nWindows Settings  ABC abc  0123456789\n文件 File  编辑 Edit  查看 View\n你好，世界！Hello, world!  ￥128.00'


class App:
    def __init__(self, root):
        self.root = root
        self.events = queue.Queue()
        self.output = None
        self.busy = False
        root.title('字体合成 · Font Studio')
        root.iconbitmap(default=str(RESOURCES / 'assets' / 'app.ico'))
        self.scale = max(1, root.winfo_fpixels('1i') / 96)
        px = lambda n: round(n * self.scale)
        self.px = px
        root.geometry('%dx%d' % (min(root.winfo_screenwidth() - 80, px(940)), min(root.winfo_screenheight() - 100, px(740))))
        root.minsize(px(820), min(root.winfo_screenheight() - 100, px(680)))
        bg, ink, muted, accent = '#F5F6F8', '#202630', '#7B8492', '#4065E0'
        root.configure(bg=bg)
        style = ttk.Style()
        style.theme_use('clam')
        style.configure('.', font=('Microsoft YaHei UI', 10), background=bg, foreground=ink)
        style.configure('TFrame', background=bg)
        style.configure('TLabel', background=bg, foreground=ink)
        style.configure('Card.TFrame', background='white')
        style.configure('Card.TLabel', background='white')
        style.configure('Muted.TLabel', foreground=muted)
        style.configure('TButton', background='#EBEEF4', foreground='#475265', borderwidth=0, relief='flat', padding=(px(14), px(9)), focusthickness=0)
        style.map('TButton', background=[('active', '#E0E5EF'), ('disabled', '#F0F2F6')], foreground=[('disabled', '#A6ADBA')])
        style.configure('Accent.TButton', background=accent, foreground='white', padding=(px(24), px(11)))
        style.map('Accent.TButton', background=[('active', '#3152C6'), ('disabled', '#BEC8E7')], foreground=[('disabled', 'white')])
        style.configure('Link.TButton', background=bg, foreground='#69758A', padding=(px(8), px(8)))
        style.map('Link.TButton', background=[('active', '#E9EDF5')])
        style.configure('TEntry', fieldbackground='white', bordercolor='#E1E5ED', lightcolor='#E1E5ED', darkcolor='#E1E5ED', padding=px(9))
        style.configure('TCombobox', fieldbackground='#F6F7FA', background='#F6F7FA', bordercolor='#F6F7FA', lightcolor='#F6F7FA', darkcolor='#F6F7FA', arrowcolor='#7B8492', padding=px(9))
        style.map('TCombobox', fieldbackground=[('readonly', '#F6F7FA')], selectbackground=[('readonly', '#F6F7FA')], selectforeground=[('readonly', ink)])
        style.configure('TSpinbox', fieldbackground='#F6F7FA', background='#F6F7FA', bordercolor='#F6F7FA', lightcolor='#F6F7FA', darkcolor='#F6F7FA', padding=px(7), arrowsize=px(12))
        style.configure('TProgressbar', background=accent, troughcolor=bg, borderwidth=0, thickness=px(3))
        main = ttk.Frame(root, padding=(px(28), px(22)))
        main.pack(fill='both', expand=True)
        header = ttk.Frame(main)
        header.pack(fill='x', pady=(0, px(20)))
        heading = ttk.Frame(header)
        heading.pack(side='left')
        ttk.Label(heading, text='字体合成', font=('Microsoft YaHei UI', 22, 'bold')).pack(anchor='w')
        ttk.Label(heading, text='两种风格，一款属于你的字体。', style='Muted.TLabel').pack(anchor='w', pady=(px(4), 0))
        ttk.Button(header, text='使用说明  ↗', style='Link.TButton', command=self.help).pack(side='right')
        self.vars, self.face_boxes, self.source_labels = {}, {}, {}
        columns = ttk.Frame(main)
        columns.pack(fill='x')
        columns.columnconfigure((0, 1), weight=1, uniform='cards')
        for col, key, title, sample in [(0, 'cn', '中文字体', '中'), (1, 'en', '英文字体', 'Aa')]:
            card = ttk.Frame(columns, style='Card.TFrame', padding=px(18))
            card.grid(row=0, column=col, sticky='nsew', padx=(0, px(8)) if col == 0 else (px(8), 0))
            top = ttk.Frame(card, style='Card.TFrame')
            top.pack(fill='x', pady=(0, px(12)))
            tk.Label(top, text=sample, bg='#EFF3FF', fg=accent, font=('Microsoft YaHei UI', 17, 'bold'), padx=px(10), pady=px(3)).pack(side='left')
            ttk.Label(top, text=title, style='Card.TLabel', font=('Microsoft YaHei UI', 12, 'bold')).pack(side='left', padx=px(12))
            self.vars[key + '_path'] = tk.StringVar()
            self.face_boxes[key] = ttk.Combobox(card, state='readonly', width=20)
            self.face_boxes[key].pack(fill='x')
            self.face_boxes[key].bind('<<ComboboxSelected>>', lambda event: self.invalidate())
            self.source_labels[key] = tk.StringVar(value='尚未选择字体')
            ttk.Label(card, textvariable=self.source_labels[key], style='Card.TLabel', foreground=muted, font=('Microsoft YaHei UI', 8)).pack(anchor='w', pady=(px(5), px(12)))
            row = ttk.Frame(card, style='Card.TFrame')
            row.pack(fill='x')
            ttk.Button(row, text='导入文件', command=lambda k=key: self.browse(k)).pack(side='left')
            ttk.Button(row, text='系统字体', command=lambda k=key: self.system_picker(k)).pack(side='left', padx=px(6))
            self.vars[key + '_size'] = tk.StringVar(value='12' if key == 'cn' else '11')
            ttk.Label(row, text='pt', style='Card.TLabel', foreground=muted).pack(side='right')
            ttk.Spinbox(row, from_=6, to=72, increment=0.5, textvariable=self.vars[key + '_size'], width=4).pack(side='right', padx=px(6))
        settings = ttk.Frame(main)
        settings.pack(fill='x', pady=(px(18), px(14)))
        ttk.Label(settings, text='字体名称', foreground='#596475').pack(side='left')
        self.vars['name'] = tk.StringVar(value='Twelve Mix ' + datetime.datetime.now().strftime('%m%d%H%M'))
        ttk.Entry(settings, textvariable=self.vars['name'], width=26).pack(side='left', padx=px(12))
        self.explanation = tk.StringVar()
        ttk.Label(settings, textvariable=self.explanation, style='Muted.TLabel', font=('Microsoft YaHei UI', 9)).pack(side='right')
        preview = ttk.Frame(main, style='Card.TFrame', padding=px(20))
        preview.pack(fill='both', expand=True)
        preview_header = ttk.Frame(preview, style='Card.TFrame')
        preview_header.pack(fill='x')
        ttk.Label(preview_header, text='字体预览', style='Card.TLabel', font=('Microsoft YaHei UI', 11, 'bold')).pack(side='left')
        self.preview_note = tk.StringVar(value='生成后显示实际效果')
        ttk.Label(preview_header, textvariable=self.preview_note, style='Card.TLabel', foreground=muted, font=('Microsoft YaHei UI', 9)).pack(side='right')
        self.canvas = tk.Canvas(preview, bg='white', highlightthickness=0, height=px(180))
        self.canvas.pack(fill='both', expand=True, pady=(px(12), 0))
        self.canvas.bind('<Configure>', lambda e: self.render() if self.output and not self.busy else self.empty_preview() if not self.output else None)
        footer = ttk.Frame(main)
        footer.pack(fill='x', pady=(px(14), 0))
        self.generate_button = ttk.Button(footer, text='生成字体  →', style='Accent.TButton', command=self.generate)
        self.generate_button.pack(side='right')
        self.install_button = ttk.Button(footer, text='安装字体', command=self.install, state='disabled')
        self.install_button.pack(side='right', padx=px(10))
        ttk.Button(footer, text='输出目录', style='Link.TButton', command=self.folder).pack(side='left')
        ttk.Button(footer, text='noMeiryoUI  ↗', style='Link.TButton', command=self.nomeiryo).pack(side='left', padx=px(4))
        self.status = tk.StringVar(value='就绪 · 支持 TTF / OTF / TTC')
        ttk.Label(main, textvariable=self.status, style='Muted.TLabel', font=('Microsoft YaHei UI', 9), wraplength=px(850)).pack(anchor='w', pady=(px(10), 0))
        self.bar = ttk.Progressbar(main, mode='indeterminate')
        self.bar.pack(fill='x', pady=(px(7), 0))
        for variable in self.vars.values():
            variable.trace_add('write', lambda *args: self.invalidate())
        self.load()
        self.invalidate()
        self.root.after(100, self.poll)
        root.protocol('WM_DELETE_WINDOW', self.close)

    def empty_preview(self):
        self.canvas.delete('all')
        x, y = self.canvas.winfo_width() / 2, self.canvas.winfo_height() / 2
        self.canvas.create_text(x, y - self.px(24), text='Aa  中', font=('Microsoft YaHei UI', 34), fill='#CDD5E4')
        self.canvas.create_text(x, y + self.px(27), text='选好字体，生成你的专属搭配', font=('Microsoft YaHei UI', 10), fill='#929CAF')

    def help(self):
        messagebox.showinfo('使用说明', '1. 分别选择中文和英文字体，设置期望字号。\n2. 输入新字体名称，点击“生成字体”导出 TTF。\n3. 安装后，在 noMeiryoUI 中选择新字体。\n\n系统字号请设为中文字号，英文按比例缩放。\n中文标点随中文；英文、数字、半角标点随英文。\n\nTTF 优先使用 FontTools 原生合并；CFF/OTF 使用轮廓兼容模式。可变字体使用默认字重。每次修改建议使用新名称，避免系统缓存。')

    def invalidate(self):
        try:
            cn, en = float(self.vars['cn_size'].get()), float(self.vars['en_size'].get())
            text = '中文 %g / 英文 %g  ·  系统设为 %g pt' % (cn, en, cn)
        except ValueError:
            text = '请输入 6–72 之间的字号。'
        self.explanation.set(text)
        if self.output:
            self.status.set('设置已更改 · 重新生成后生效')
            self.preview_note.set('上次生成的效果')

    def set_path(self, key, path, index=0):
        values = faces(path)
        self.vars[key + '_path'].set(str(path))
        self.face_boxes[key]['values'] = values
        self.face_boxes[key].current(min(index, len(values) - 1))
        filename = Path(path).name
        self.source_labels[key].set(filename if len(filename) < 43 else filename[:39] + '…')

    def browse(self, key):
        path = filedialog.askopenfilename(title='选择中文字体' if key == 'cn' else '选择英文字体', filetypes=[('字体文件', '*.ttf *.otf *.ttc *.otc')])
        if path:
            try:
                self.set_path(key, path)
            except Exception as error:
                messagebox.showerror('无法读取字体', str(error))

    def system_picker(self, key):
        dialog = tk.Toplevel(self.root)
        dialog.title('选择已安装的字体')
        dialog.geometry('%dx%d' % (int(720 * self.scale), int(500 * self.scale)))
        query = tk.StringVar()
        ttk.Label(dialog, text='搜索字体名称或文件名（读取中…）').pack(anchor='w', padx=15, pady=8)
        entry = ttk.Entry(dialog, textvariable=query)
        entry.pack(fill='x', padx=15)
        frame = ttk.Frame(dialog)
        frame.pack(fill='both', expand=True, padx=15, pady=10)
        listing = tk.Listbox(frame, font=('Microsoft YaHei UI', 10), exportselection=False)
        scroll = ttk.Scrollbar(frame, orient='vertical', command=listing.yview)
        listing.configure(yscrollcommand=scroll.set)
        listing.pack(side='left', fill='both', expand=True)
        scroll.pack(side='right', fill='y')
        rows, shown = [], []
        results = queue.Queue()

        def scan():
            import winreg
            files = set()
            for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
                try:
                    with winreg.OpenKey(hive, r'SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts') as reg:
                        for i in range(winreg.QueryInfoKey(reg)[1]):
                            value = winreg.EnumValue(reg, i)[1]
                            if isinstance(value, str):
                                path = Path(os.path.expandvars(value))
                                if not path.is_absolute():
                                    path = Path(os.environ['WINDIR']) / 'Fonts' / path
                                if path.exists():
                                    files.add(path)
                except OSError:
                    pass
            for path in files:
                try:
                    for index, name in enumerate(faces(path)):
                        results.put((name + '  [' + path.name + ']', path, index))
                except Exception:
                    pass
            results.put(None)

        def refresh(*args):
            shown[:] = [r for r in rows if query.get().casefold() in r[0].casefold()]
            listing.delete(0, 'end')
            for row in shown:
                listing.insert('end', row[0])

        def poll():
            if not dialog.winfo_exists():
                return
            done = False
            while not results.empty():
                row = results.get()
                if row is None:
                    done = True
                else:
                    rows.append(row)
            rows.sort(key=lambda row: row[0].casefold())
            refresh()
            if not done:
                dialog.after(300, poll)
            else:
                dialog.winfo_children()[0].configure(text='搜索字体名称或文件名（%d 个字体）' % len(rows))

        def choose(event=None):
            if listing.curselection():
                _, path, index = shown[listing.curselection()[0]]
                self.set_path(key, path, index)
                dialog.destroy()
        listing.bind('<Double-Button-1>', choose)
        ttk.Button(dialog, text='使用选中的字体', command=choose).pack(pady=(0, 12))
        query.trace_add('write', refresh)
        threading.Thread(target=scan, daemon=True).start()
        poll()
        entry.focus_set()

    def config(self):
        config = {key: value.get() for key, value in self.vars.items()}
        for key in ('cn', 'en'):
            config[key + '_index'] = self.face_boxes[key].current()
            if config[key + '_index'] < 0 or not Path(config[key + '_path']).is_file():
                raise ValueError('请先选择有效的中文字体和英文字体文件。')
        return config

    def generate(self):
        if self.busy:
            return
        try:
            config = self.config()
        except Exception as error:
            messagebox.showerror('请检查设置', str(error))
            return
        directory = ROOT / 'output'
        directory.mkdir(exist_ok=True)
        filename = ''.join(c for c in config['name'] if c not in '<>:"/\\|?*').strip() or 'BilingualFont'
        path = filedialog.asksaveasfilename(title='导出字体文件（不覆盖已有文件）', initialdir=str(directory), initialfile=filename + '.ttf', defaultextension='.ttf', filetypes=[('TrueType 字体', '*.ttf')])
        if not path:
            return
        self.save(config)
        self.busy = True
        self.generate_button.configure(state='disabled', text='正在生成…')
        self.install_button.configure(state='disabled')
        self.bar.start()
        self.status.set('开始合成…')

        def worker():
            try:
                result = build(config, path, lambda text: self.events.put(('progress', text)))
                self.events.put(('done', result))
            except Exception as error:
                self.events.put(('error', str(error)))
        threading.Thread(target=worker, daemon=True).start()

    def poll(self):
        while not self.events.empty():
            kind, value = self.events.get()
            if kind == 'progress':
                self.status.set(value)
                continue
            self.busy = False
            self.bar.stop()
            self.generate_button.configure(state='normal', text='生成字体  →')
            if kind == 'error':
                self.status.set('生成失败：' + value)
                messagebox.showerror('生成失败', value)
                if self.output:
                    self.install_button.configure(state='normal')
            else:
                self.output = value['output']
                self.report = value
                self.install_button.configure(state='normal')
                self.status.set('已保存 %s · 在 noMeiryoUI 中设为 %s pt' % (Path(self.output).name, value['cn_size']))
                self.preview_note.set('%s 个字符 · TTF' % format(value['characters'], ','))
                self.render()
        self.root.after(100, self.poll)

    def render(self):
        try:
            width = max(600, self.canvas.winfo_width())
            height = max(185, self.canvas.winfo_height())
            image = Image.new('RGB', (width, height), 'white')
            draw = ImageDraw.Draw(image)
            font = ImageFont.truetype(self.output, int(22 * self.scale))
            box = draw.multiline_textbbox((0, 0), SAMPLE, font=font, spacing=int(12 * self.scale))
            y = max(self.px(8), (height - (box[3] - box[1])) // 2 - box[1])
            draw.multiline_text((self.px(10), y), SAMPLE, font=font, fill='#303B50', spacing=int(12 * self.scale))
            self.preview_image = ImageTk.PhotoImage(image)
            self.canvas.delete('all')
            self.canvas.create_image(0, 0, anchor='nw', image=self.preview_image)
        except Exception as error:
            self.status.set('字体已导出，但预览失败：' + str(error))

    def install(self):
        if self.output:
            os.startfile(self.output)

    def folder(self):
        path = Path(self.output).parent if self.output else ROOT / 'output'
        path.mkdir(exist_ok=True)
        os.startfile(str(path))

    def nomeiryo(self):
        path = Path(shutil.which('noMeiryoUI.exe') or ROOT / 'noMeiryoUI.exe')
        if not path.exists():
            selected = filedialog.askopenfilename(title='定位 noMeiryoUI.exe', filetypes=[('noMeiryoUI', '*.exe')])
            if not selected:
                return
            path = Path(selected)
        os.startfile(str(path))

    def save(self, config):
        try:
            (ROOT / 'settings.json').write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding='utf-8')
        except OSError:
            pass

    def load(self):
        try:
            config = json.loads((ROOT / 'settings.json').read_text(encoding='utf-8'))
        except (OSError, ValueError):
            config = {}
        for key in ('name', 'cn_size', 'en_size'):
            if key in config:
                self.vars[key].set(config[key])
        for key in ('cn', 'en'):
            try:
                self.set_path(key, config[key + '_path'], config.get(key + '_index', 0))
            except Exception:
                pass

    def close(self):
        if self.busy:
            messagebox.showinfo('正在生成', '请等待字体生成完成后再关闭，避免中断导出。')
            return
        try:
            self.save(self.config())
        except Exception:
            pass
        self.root.destroy()


if __name__ == '__main__':
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    window = tk.Tk()
    App(window)
    window.mainloop()
