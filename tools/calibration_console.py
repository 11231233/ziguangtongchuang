"""OV5640 digital calibration and host-command console; no automatic device opens."""
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time
from collections import deque
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import cv2
from PIL import Image, ImageTk

import calibration_workflow as flow
from calibration_inputs import BoardInputError, parse_board_inputs, parse_inner_corners
from preview_denoise import PreviewDenoiser, MODES as DENOISE_MODES
from preview_stream import LatestCapture, LatestPreviewFilter


class Console:
    def __init__(self, root):
        self.root = root
        root.title('OV5640 标定与角度控制台')
        root.geometry(f'{min(1180, root.winfo_screenwidth()-60)}x{min(900, root.winfo_screenheight()-90)}')
        self.session = None; self.model = None; self.model_path = None
        self.raw = None; self.raw_source = None; self.cap = None; self.busy = False
        self.jobs = queue.Queue(); self.photo = None; self.capture_after = None
        self.preview_source = None; self.fullscreen_window = None
        self.fullscreen_photo = None; self.preview_resize_after = None
        self.camera = tk.StringVar(value='C1'); self.cols = tk.StringVar(value='9')
        self.rows = tk.StringVar(value='6'); self.square = tk.StringVar(value='')
        self.confirmed = tk.BooleanVar(value=False)
        self.device = tk.StringVar(value='0'); self.preview_mode = tk.StringVar(value='原始输入')
        self.preview_flip_vertical = tk.BooleanVar(value=False)
        self.capture_flip_vertical = tk.BooleanVar(value=False)
        self.denoise_mode = tk.StringVar(value='关闭')
        self.preview_denoiser = PreviewDenoiser()
        self.denoise_input = None; self.denoise_output = None
        self.denoise_snapshot_metadata = None
        self.capture_reader = None; self.capture_sequence = 0
        self.preview_worker = LatestPreviewFilter(); self.preview_job = 0
        self.preview_times = deque(maxlen=90); self.preview_process_ms = 0.
        self.preview_stats_updated = 0.
        self.preview_stats = tk.StringVar(value='取图/预览帧率尚未测量；两者均不是FPGA独立源帧率。')
        self.roll = tk.StringVar(value='0'); self.port = tk.StringVar(value='')
        self.wired = tk.BooleanVar(value=False)
        self.initial_demo = tk.BooleanVar(value=False)
        self.model_source_info = tk.StringVar(value='待发送：尚未加载真实镜头模型。')
        self.info = tk.StringVar(value='未打开采集设备；未连接开发板控制串口；尚无真实镜头标定。')
        top = ttk.Frame(root, padding=8); top.pack(fill='x')
        ttk.Label(top, text='先采集实际镜头数字帧，再标定、独立验证、下发参数。', font=('Microsoft YaHei', 14)).pack(anchor='w')
        ttk.Label(top, text='单目C1 / HDMI 720P60；Q档以视频左上角状态为准。USB-TTL须正确共地；软件启动不会自动连接设备。', wraplength=1140).pack(anchor='w', pady=4)
        book = ttk.Notebook(root); book.pack(fill='x', padx=8)
        capture = ttk.Frame(book, padding=8); control = ttk.Frame(book, padding=8)
        book.add(capture, text='1 采集与标定'); book.add(control, text='2 上位机角度控制')
        row = ttk.Frame(capture); row.pack(fill='x')
        self.board_entries = {}
        for label, var, width in [('相机', self.camera, 4), ('内角点列', self.cols, 4), ('行', self.rows, 4), ('实测格边/mm', self.square, 8)]:
            ttk.Label(row, text=label).pack(side='left', padx=3)
            if var is self.camera:
                ttk.Combobox(row, textvariable=var, values=['C1'], state='readonly', width=width).pack(side='left')
            else:
                entry = ttk.Entry(row, textvariable=var, width=width)
                entry.pack(side='left')
                field = 'cols' if var is self.cols else 'rows' if var is self.rows else 'square'
                self.board_entries[field] = entry
        ttk.Button(row, text='新建会话', command=self.new_session).pack(side='left', padx=6)
        ttk.Button(row, text='打开会话', command=self.open_session).pack(side='left')
        ttk.Checkbutton(capture, text='我确认：实际OV5640数字取图、精确恒等映射/G0/T0/Q1、H0实时、C1、关闭OSD；\n1280×720无缩放裁切，固定焦点和成像模式。', variable=self.confirmed).pack(anchor='w', pady=5)
        row = ttk.Frame(capture); row.pack(fill='x', pady=3)
        ttk.Label(row, text='采集卡设备号').pack(side='left')
        ttk.Entry(row, textvariable=self.device, width=4).pack(side='left', padx=4)
        for label, fn in [('打开采集卡', self.open_capture), ('关闭', self.close_capture),
                          ('打开数字图片', self.open_image)]:
            ttk.Button(row, text=label, command=fn).pack(side='left', padx=2)
        ttk.Checkbutton(row, text='仅预览上下翻转（保存图不变）',
                        variable=self.preview_flip_vertical, command=self.preview_direction_changed).pack(side='left', padx=6)
        ttk.Button(row, text='全屏预览（F11）', command=self.toggle_fullscreen).pack(side='left', padx=4)
        row = ttk.Frame(capture); row.pack(fill='x', pady=3)
        ttk.Checkbutton(row, text='采集输入上下翻转（同时作用于保存图）',
                        variable=self.capture_flip_vertical, command=self.capture_direction_changed).pack(side='left')
        ttk.Label(row, text='用于将采集卡原图方向与HDMI画面对齐；开始保存后不可改。').pack(side='left', padx=6)
        row = ttk.Frame(capture); row.pack(fill='x', pady=3)
        ttk.Label(row, text='仅电脑预览降噪').pack(side='left')
        denoise_box = ttk.Combobox(row, textvariable=self.denoise_mode, values=list(DENOISE_MODES), state='readonly', width=22)
        denoise_box.pack(side='left', padx=4)
        denoise_box.bind('<<ComboboxSelected>>', lambda _: self.denoise_changed())
        ttk.Button(row, text='另存降噪对照', command=self.save_denoise_pair).pack(side='left', padx=4)
        ttk.Label(row, text='不改变HDMI和标定原图；时域模式仅用于实时采集').pack(side='left', padx=4)
        row = ttk.Frame(capture); row.pack(fill='x', pady=3)
        ttk.Button(row, text='检查棋盘角点', command=self.check_board).pack(side='left', padx=2)
        for label, fn in [('保存训练帧', lambda: self.save('train')),
                          ('保存验证帧', lambda: self.save('validation')),
                          ('导入训练图', lambda: self.import_files('train')),
                          ('导入验证图', lambda: self.import_files('validation'))]:
            ttk.Button(row, text=label, command=fn).pack(side='left', padx=2)
        ttk.Button(row, text='另存当前数字帧', command=self.save_digital_frame).pack(side='left', padx=6)
        row = ttk.Frame(capture); row.pack(fill='x', pady=4)
        ttk.Button(row, text='标定并独立验证', command=self.calibrate).pack(side='left')
        ttk.Button(row, text='加载镜头模型', command=self.load_model).pack(side='left', padx=4)
        ttk.Label(row, text='电脑预览').pack(side='left', padx=6)
        box = ttk.Combobox(row, textvariable=self.preview_mode, values=['原始输入', '去镜头畸变', '棋盘平面正视'], state='readonly', width=16)
        box.pack(side='left'); box.bind('<<ComboboxSelected>>', lambda _: self.render())
        self.preview_choice = box
        ttk.Label(capture, text='预览在电脑计算；保存标定帧始终取原始输入。').pack(anchor='w')
        row = ttk.Frame(control); row.pack(fill='x')
        ttk.Label(row, text='平面旋转角/度').pack(side='left')
        ttk.Entry(row, textvariable=self.roll, width=8).pack(side='left', padx=4)
        ttk.Button(row, text='导出角度参数包', command=lambda: self.host(False)).pack(side='left', padx=3)
        ttk.Button(row, text='导出扫角演示包', command=self.sweep).pack(side='left', padx=3)
        ttk.Button(row, text='导出FPGA系数', command=self.export_coeff).pack(side='left', padx=3)
        ttk.Button(control, text='生成免串口标定工程（有真实标定及验证后）', command=self.static_project).pack(anchor='w', pady=4)
        row = ttk.Frame(control); row.pack(fill='x', pady=6)
        ttk.Label(row, text='已确认的控制串口').pack(side='left')
        self.ports = ttk.Combobox(row, textvariable=self.port, width=15); self.ports.pack(side='left', padx=4)
        ttk.Button(row, text='列出串口', command=self.list_ports).pack(side='left')
        ttk.Button(row, text='只读测量串口', command=self.uart_measure).pack(side='left')
        ttk.Button(row, text='发送角度并等待回执', command=lambda: self.host(True)).pack(side='left', padx=4)
        ttk.Button(row, text='发送精确RAW指令', command=lambda: self.host(True, raw=True)).pack(side='left')
        row = ttk.Frame(control); row.pack(fill='x', pady=3)
        ttk.Button(row, text='60秒帧率验收', command=self.uart_fps60).pack(side='left')
        ttk.Button(row, text='发送连续扫角并记录', command=self.live_sweep).pack(side='left', padx=6)
        ttk.Button(row, text='USB-TTL自回环测试', command=self.uart_loopback).pack(side='left', padx=6)
        ttk.Checkbutton(control, text='我已确认控制口与3.3V接线；该端口不是下载器JTAG通道', variable=self.wired).pack(anchor='w')
        ttk.Label(control, text='姿态角需人工或已知水平基准提供；不自动判断物体是否歪。平面正视预览仅针对棋盘，不代表FPGA已实现透视校正。', wraplength=1120).pack(anchor='w', pady=4)
        self.initial_demo_box = ttk.Checkbutton(control, text='仅演示：使用现有C1间接初估参数下发角度（不作为真实标定结果）',
            variable=self.initial_demo, command=self.update_model_source)
        self.initial_demo_box.pack(anchor='w')
        ttk.Label(control, textvariable=self.model_source_info, wraplength=1120).pack(anchor='w', pady=3)
        ttk.Label(root, textvariable=self.info, wraplength=1140, padding=8).pack(fill='x')
        ttk.Label(root, textvariable=self.preview_stats, wraplength=1140).pack(fill='x', padx=8)
        self.preview = tk.Canvas(root, background='black', highlightthickness=0, width=640, height=240)
        self.preview.pack(fill='both', expand=True)
        self.preview.bind('<Configure>', self.preview_resized)
        self.preview.bind('<Double-Button-1>', lambda _: self.toggle_fullscreen())
        root.bind('<F11>', lambda _: self.toggle_fullscreen())
        root.bind('<Escape>', lambda _: self.close_fullscreen())
        self.log = tk.Text(root, height=7, wrap='word', state='disabled'); self.log.pack(fill='x', padx=8, pady=5)
        bottom = ttk.Frame(root); bottom.pack(fill='x', padx=8)
        ttk.Button(bottom, text='连接与操作说明', command=self.guide).pack(side='left')
        ttk.Label(bottom, text='KEY1长按冻结，KEY0同帧对比；KEY4长按切Gamma。').pack(side='left', padx=10)
        root.protocol('WM_DELETE_WINDOW', self.close)
        root.after(100, self.poll)

    def note(self, text):
        self.log.configure(state='normal'); self.log.insert('end', str(text) + '\n')
        self.log.see('end'); self.log.configure(state='disabled')

    def guarded(self, fn):
        try:
            return fn()
        except Exception as exc:
            messagebox.showerror('无法完成', str(exc)); self.note(exc)

    def job(self, fn, done=None):
        if self.busy:
            messagebox.showinfo('正在处理', '请等待当前处理完成'); return
        self.busy = True; self.note('正在处理…')
        def worker():
            try:
                self.jobs.put((True, fn(), done))
            except Exception as exc:
                self.jobs.put((False, str(exc), None))
        threading.Thread(target=worker, daemon=True).start()

    def poll(self):
        try:
            ok, value, done = self.jobs.get_nowait(); self.busy = False
            if ok:
                self.note(value)
                if done: self.guarded(lambda: done(value))
                self.refresh()
            else:
                self.note(value); messagebox.showerror('处理失败', value)
        except queue.Empty:
            pass
        self.root.after(100, self.poll)

    def refresh(self):
        if not self.session:
            return
        data = flow.load_session(self.session)
        train = sum(f['split'] == 'train' for f in data['frames'])
        val = sum(f['split'] == 'validation' for f in data['frames'])
        self.info.set(f"{data['camera']}：训练{train}张 / 验证{val}张；{self.session}；模型：{self.model_path or '尚未估计'}")

    def board_corners(self):
        try:
            cols, rows = parse_inner_corners(self.cols.get(), self.rows.get())
        except BoardInputError as exc:
            self.focus_board_input(exc.field)
            raise
        self.cols.set(str(cols)); self.rows.set(str(rows))
        return cols, rows

    def focus_board_input(self, field):
        entry = self.board_entries.get(field)
        if entry is not None:
            entry.focus_set()
            entry.selection_range(0, tk.END)

    def board_inputs(self):
        try:
            values = parse_board_inputs(self.cols.get(), self.rows.get(), self.square.get())
        except BoardInputError as exc:
            self.focus_board_input(exc.field)
            raise
        self.cols.set(str(values[0])); self.rows.set(str(values[1]))
        self.square.set(format(values[2], '.15g'))
        return values

    def new_session(self):
        if self.busy: return
        def action():
            cols, rows, square = self.board_inputs()
            if not self.confirmed.get():
                raise ValueError('请先核对并勾选“我确认：实际OV5640数字取图……”中的本次取图条件，再新建会话。')
            parent = filedialog.askdirectory(title='选择会话保存父目录')
            if not parent: return
            folder = Path(parent) / ('ov5640_' + self.camera.get() + '_' + flow.stamp())
            flow.create_session(folder, self.camera.get(), cols, rows, square, self.confirmed.get())
            data = flow.load_session(folder)
            data['capture_input_transform'] = {'flip_vertical': self.capture_flip_vertical.get(), 'operator_confirmed_matches_fpga_coordinates': True}
            flow.write_json(folder / 'session.json', data)
            self.session = folder; self.model = None; self.model_path = None
            self.update_model_source()
            self.refresh(); self.note('新建会话，来源和取图条件由操作者声明。')
        self.guarded(action)

    def open_session(self):
        if self.busy: return
        folder = filedialog.askdirectory(title='选择含session.json的会话')
        if not folder: return
        def action():
            data = flow.load_session(folder); self.session = Path(folder)
            self.model = None; self.model_path = None
            self.update_model_source()
            self.camera.set(data['camera']); self.cols.set(str(data['inner_corners'][0])); self.rows.set(str(data['inner_corners'][1]))
            self.square.set(str(data['square_mm_operator_measured'])); self.confirmed.set(False)
            self.capture_flip_vertical.set(data.get('capture_input_transform', {}).get('flip_vertical', False))
            self.preview_flip_vertical.set(False)
            self.reset_preview_processing()
            self.raw = None; self.raw_source = None
            self.refresh()
        self.guarded(action)

    def capture_tick(self):
        self.capture_after = None
        if self.cap is None: return
        started = time.monotonic()
        frame = self.capture_reader.latest(self.capture_sequence)
        if frame is not None:
            self.capture_sequence, captured_at, image = frame
            if self.capture_flip_vertical.get():
                image = cv2.flip(image, 0)
            self.raw = image; self.raw_source = 'capture_device_' + self.device.get() + ';input_flip_vertical=' + str(int(self.capture_flip_vertical.get()))
            # Never run model remapping on every capture tick; raw is retained.
            self.queue_capture_preview(image, captured_at)
            direction = '预览已上下翻转，保存原图不变' if self.preview_flip_vertical.get() else '预览方向未调整'
            normalization = '采集及保存已上下翻转' if self.capture_flip_vertical.get() else '采集及保存方向未调整'
            self.info.set(f'采集返回 {image.shape[1]}×{image.shape[0]}；{normalization}；{direction}。取图来源需人工核对。')
        result = self.preview_worker.latest(self.preview_job)
        if result is not None and DENOISE_MODES[self.denoise_mode.get()] != 'off':
            self.preview_job = result['job']
            self.present_capture_preview(result['original'], result['output'], result['metadata'],
                                         result['mode'], result['processing_ms'], result['replaced_pixels'])
        if self.preview_worker.error:
            self.info.set('电脑预览处理失败：' + self.preview_worker.error + '；可将降噪切回关闭。')
        if self.capture_reader.error:
            self.info.set('采集读取异常：' + self.capture_reader.error)
        self.update_preview_stats()
        elapsed_ms = int((time.monotonic() - started) * 1000)
        self.capture_after = self.root.after(max(1, 33 - elapsed_ms), self.capture_tick)

    def queue_capture_preview(self, image, captured_at=None):
        mode = DENOISE_MODES[self.denoise_mode.get()]
        metadata = {'capture_source': str(self.raw_source), 'capture_sequence': self.capture_sequence,
                    'captured_host_monotonic': captured_at,
                    'capture_input_flip_vertical': self.capture_flip_vertical.get(),
                    'pc_geometry_preview': '原始输入', 'live_capture': True}
        if mode == 'off':
            self.present_capture_preview(image, image, metadata, mode, 0., 0)
        else:
            self.preview_worker.submit(image, mode, metadata)

    def present_capture_preview(self, original, output, metadata, mode, processing_ms, replaced):
        self.denoise_input = original; self.denoise_output = output
        self.denoise_snapshot_metadata = dict(metadata, mode=mode, processing_ms=processing_ms,
                                              heuristic_replaced_pixels=replaced)
        self.preview_process_ms = processing_ms
        self.present_preview_image(output)
        now = time.monotonic(); self.preview_times.append(now)
        self.update_preview_stats()

    def update_preview_stats(self):
        now = time.monotonic()
        if now-self.preview_stats_updated<.5:return
        self.preview_stats_updated=now
        while self.preview_times and now-self.preview_times[0]>3:
            self.preview_times.popleft()
        span = now-self.preview_times[0] if self.preview_times else 0.
        fps = (len(self.preview_times)-1)/span if len(self.preview_times)>1 and span>0 else 0.
        capture_fps = self.capture_reader.fps() if self.capture_reader else 0.
        self.preview_stats.set(f'取图 {capture_fps:.1f} fps（可含重复画面）｜预览 {fps:.1f} fps｜降噪处理 {self.preview_process_ms:.1f} ms；不是FPGA源帧率。')

    def reset_preview_processing(self):
        self.preview_denoiser.reset()
        self.preview_worker.invalidate()
        self.preview_job = 0; self.preview_times.clear(); self.preview_stats_updated = 0.
        self.preview_process_ms = 0.
        self.denoise_input = None; self.denoise_output = None

    def open_capture(self):
        def action():
            self.close_capture()
            self.reset_preview_processing()
            device = int(self.device.get())
            self.cap = cv2.VideoCapture(device, cv2.CAP_DSHOW if os.name == 'nt' else cv2.CAP_ANY)
            if not self.cap.isOpened():
                self.close_capture(); raise ValueError('设备未打开；下载器和普通USB线不能采集HDMI视频')
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280); self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
            self.preview_mode.set('原始输入'); self.note('设备号不证明它是HDMI采集卡，请核对输入画面。')
            self.preview_choice.configure(state='disabled')
            self.capture_sequence = 0
            self.capture_reader = LatestCapture(self.cap)
            self.capture_tick()
        self.guarded(action)

    def close_capture(self):
        if self.capture_after is not None:
            self.root.after_cancel(self.capture_after); self.capture_after = None
        if self.capture_reader is not None:
            self.capture_reader.stop(); self.capture_reader = None
        elif self.cap is not None:
            self.cap.release()
        self.cap = None
        self.reset_preview_processing()
        self.preview_choice.configure(state='readonly')

    def open_image(self):
        path = filedialog.askopenfilename(filetypes=[('数字图像', '*.png *.jpg *.jpeg *.bmp')])
        if not path: return
        def action():
            self.close_capture(); self.raw = flow.read_image(path); self.raw_source = path; self.render()
        self.guarded(action)

    def show(self, image):
        if getattr(self, 'cap', None) is not None and getattr(self, 'capture_reader', None) is not None:
            self.queue_capture_preview(image)
            return
        if hasattr(self, 'preview_denoiser'):
            mode = DENOISE_MODES[self.denoise_mode.get()]
            output = self.preview_denoiser.process(image, mode, use_temporal=self.cap is not None)
            self.denoise_input = image.copy(); self.denoise_output = output.copy()
            self.denoise_snapshot_metadata = {'mode': mode, 'live_capture': self.cap is not None,
                'capture_source': str(self.raw_source),
                'capture_input_flip_vertical': self.capture_flip_vertical.get(),
                'pc_geometry_preview': self.preview_mode.get(),
                'heuristic_replaced_pixels': self.preview_denoiser.corrected_pixels}
            image = output
        self.present_preview_image(image)

    def present_preview_image(self, image):
        if self.preview_flip_vertical.get():
            image = cv2.flip(image, 0)
        self.preview_source = Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
        self.draw_previews()

    def draw_canvas(self, canvas):
        width, height = max(1, canvas.winfo_width()), max(1, canvas.winfo_height())
        canvas.delete('all')
        if self.preview_source is None:
            canvas.create_text(width // 2, height // 2, text='尚无数字图像输入', fill='white')
            return None
        original = self.preview_source
        scale = min(width / original.width, height / original.height)
        size = (max(1, round(original.width * scale)), max(1, round(original.height * scale)))
        pic = original.resize(size, Image.Resampling.BILINEAR)
        photo = ImageTk.PhotoImage(pic, master=canvas)
        canvas.create_image(width // 2, height // 2, image=photo, anchor='center')
        return photo

    def draw_previews(self):
        if self.fullscreen_window is not None:
            self.fullscreen_photo = self.draw_canvas(self.fullscreen_canvas)
        else:
            self.photo = self.draw_canvas(self.preview)

    def preview_resized(self, event=None):
        if self.preview_resize_after is not None:
            self.root.after_cancel(self.preview_resize_after)
        self.preview_resize_after = self.root.after(60, self.redraw_after_resize)

    def redraw_after_resize(self):
        self.preview_resize_after = None
        self.draw_previews()

    def toggle_fullscreen(self):
        if self.fullscreen_window is not None:
            self.close_fullscreen()
            return
        window = tk.Toplevel(self.root)
        self.fullscreen_window = window
        window.title('图像全屏预览 — Esc退出')
        window.configure(background='black')
        # Open on the monitor containing the main console.
        window.geometry(f'{self.root.winfo_width()}x{self.root.winfo_height()}+{self.root.winfo_x()}+{self.root.winfo_y()}')
        self.fullscreen_canvas = tk.Canvas(window, background='black', highlightthickness=0)
        self.fullscreen_canvas.pack(fill='both', expand=True)
        self.fullscreen_canvas.bind('<Configure>', self.preview_resized)
        self.fullscreen_canvas.bind('<Double-Button-1>', lambda _: self.close_fullscreen())
        window.bind('<Escape>', lambda _: self.close_fullscreen())
        window.bind('<F11>', lambda _: self.close_fullscreen())
        window.protocol('WM_DELETE_WINDOW', self.close_fullscreen)
        window.attributes('-fullscreen', True)
        window.focus_set()
        self.draw_previews()

    def close_fullscreen(self):
        if self.fullscreen_window is not None:
            self.fullscreen_window.destroy()
            self.fullscreen_window = None
            self.fullscreen_photo = None
            self.draw_previews()

    def preview_direction_changed(self):
        self.render()
        self.note('电脑预览方向已调整；FPGA、HDMI和保存原始帧均未改变。正式标定前仍须核对原始图与FPGA坐标方向。')

    def denoise_changed(self):
        self.reset_preview_processing()
        self.render()
        self.note('仅电脑预览降噪：' + self.denoise_mode.get() + '；HDMI及标定原图不变。新版小斑点修复只处理平坦背景内的小斑块，仍可能误删真实小目标；保边柔和模式不使用历史帧。')

    def save_denoise_pair(self):
        def action():
            if self.denoise_input is None or self.denoise_output is None:
                raise ValueError('请先打开采集卡或数字图片并选择降噪模式')
            out = self.destination('保存原图与软件降噪对照')
            if out is None: return
            original = self.denoise_input.copy(); filtered = self.denoise_output.copy()
            metadata = dict(self.denoise_snapshot_metadata)
            metadata.update(saved=flow.stamp(), fpga_denoise_applied=False,
                preview_flip_applied_to_files=False, actual_noise_reduction_verified=False,
                calibration_input=False, image_size=[original.shape[1], original.shape[0]])
            def work():
                out.mkdir()
                for name, image in [('original.png', original), ('denoised.png', filtered),
                                    ('difference_x4.png', cv2.convertScaleAbs(cv2.absdiff(original, filtered), alpha=4))]:
                    ok, encoded = cv2.imencode('.png', image)
                    if not ok: raise ValueError('PNG编码失败')
                    (out / name).write_bytes(encoded.tobytes())
                    metadata[name + '_sha256'] = flow.digest(encoded.tobytes())
                flow.write_json(out / 'denoise.json', metadata)
                return '已保存软件降噪对照：' + str(out)
            self.job(work)
        self.guarded(action)

    def capture_direction_changed(self):
        if self.busy:
            self.capture_flip_vertical.set(not self.capture_flip_vertical.get())
            messagebox.showinfo('正在处理', '请等待当前保存或处理完成后再调整方向。')
            return
        if self.session:
            data = flow.load_session(self.session)
            previous = data.get('capture_input_transform', {}).get('flip_vertical', False)
            if data['frames']:
                self.capture_flip_vertical.set(previous)
                messagebox.showinfo('方向已锁定', '此会话已有图像，不能混用方向。请保持原设置，或重新启动控制台建立新会话。')
                return
            data['capture_input_transform'] = {'flip_vertical': self.capture_flip_vertical.get(), 'operator_confirmed_matches_fpga_coordinates': False}
            flow.write_json(self.session / 'session.json', data)
        self.preview_flip_vertical.set(False)
        self.reset_preview_processing()
        self.confirmed.set(False)
        self.raw = None; self.raw_source = None
        self.model = None; self.model_path = None
        self.update_model_source()
        self.note('已调整采集输入方向，并关闭仅预览翻转。请对照HDMI确认方向一致后，重新勾选取图条件；保存图使用同一方向。')

    def render(self):
        if self.raw is None: return
        def action():
            if self.raw.shape[:2] != (720, 1280) and self.preview_mode.get() != '原始输入':
                raise ValueError('校正预览要求1280×720输入')
            if self.preview_mode.get() == '原始输入': self.show(self.raw)
            elif self.model is None: raise ValueError('请先加载对应镜头的标定模型')
            elif self.model.get('camera') in ('C1', 'C2') and self.model['camera'] != self.camera.get():
                raise ValueError('所选相机与模型不一致')
            elif self.preview_mode.get() == '去镜头畸变': self.show(flow.remap_preview(self.raw, self.model))
            else:
                self.show(flow.plane_preview(self.raw, self.model, self.board_corners()))
            self.note('当前预览：' + self.preview_mode.get() + '；电脑预览不作为FPGA实板结果。')
        self.guarded(action)

    def require_session(self):
        if self.session is None: raise ValueError('请先新建或打开数字取图会话')
        if not self.confirmed.get(): raise ValueError('请先核对并勾选本次数字取图条件')
        if flow.load_session(self.session)['camera'] != self.camera.get():
            raise ValueError('会话相机与所选相机不一致；C1/C2需分别建会话')
        data = flow.load_session(self.session)
        if data.get('capture_input_transform', {}).get('flip_vertical', False) != self.capture_flip_vertical.get():
            raise ValueError('采集方向与会话不一致，不能混用坐标方向')
        cols, rows, square = self.board_inputs()
        if (data['inner_corners'] != [cols, rows]
                or data['square_mm_operator_measured'] != square):
            if data['frames']:
                raise ValueError('当前会话已有图片，不能混用不同的棋盘设置。请恢复原设置，或新建会话。')
            data['inner_corners'] = [cols, rows]
            data['square_mm_operator_measured'] = square
            flow.write_json(self.session / 'session.json', data)
            self.note('已将空会话更新为当前填写的棋盘设置。')
        return self.session

    def check_board(self):
        def action():
            if self.raw is None:
                raise ValueError('请先打开采集卡或数字图片，让棋盘出现在画面中。')
            if self.busy:
                raise ValueError('请等待当前处理完成。')
            pattern = self.board_corners()
            image = self.raw.copy()
            out = flow.ROOT / 'reports' / ('checkerboard_check_' + flow.stamp())
            self.job(lambda: flow.check_checkerboard(image, pattern, out), self.show_board_check)
        self.guarded(action)

    def show_board_check(self, report):
        window = tk.Toplevel(self.root)
        window.title('棋盘角点检查：' + ('完整识别' if report['found'] else '尚未完整识别'))
        ttk.Label(window, text=report['message'], wraplength=900,
                  padding=10).pack(fill='x')
        image = flow.read_image(report['overlay_image'])
        rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        preview = Image.fromarray(rgb)
        preview.thumbnail((min(1000, self.root.winfo_screenwidth()-100),
                           min(600, self.root.winfo_screenheight()-220)))
        window.checker_photo = ImageTk.PhotoImage(preview)
        ttk.Label(window, image=window.checker_photo).pack()
        ttk.Label(window, text='检查记录：' + report['report_path'],
                  wraplength=900, padding=8).pack(fill='x')
        ttk.Button(window, text='关闭检查结果', command=window.destroy).pack(pady=8)
        self.note(report['message'] + '\n检查记录：' + report['report_path'])

    def save(self, split):
        def action():
            folder = self.require_session()
            if self.raw is None: raise ValueError('尚无原始输入图像')
            image = self.raw.copy(); source = self.raw_source
            self.job(lambda: flow.save_frame(folder, image, split, source))
        self.guarded(action)

    def save_digital_frame(self):
        def action():
            if self.raw is None:
                raise ValueError('尚无数字输入图像')
            filename = filedialog.asksaveasfilename(title='保存采集输入数字帧（不是电脑校正预览）',
                defaultextension='.png', initialfile='digital_' + flow.stamp() + '.png',
                filetypes=[('PNG数字图像', '*.png')])
            if not filename: return
            path = Path(filename)
            if path.suffix.lower() != '.png':
                raise ValueError('请保存为PNG格式')
            if path.exists() or path.with_suffix('.json').exists():
                raise ValueError('文件已存在，请使用新名称以保留原始记录')
            image = self.raw.copy()
            metadata = {'source': str(self.raw_source), 'image_size': [image.shape[1], image.shape[0]],
                'capture_input_flip_vertical': self.capture_flip_vertical.get(),
                'preview_flip_applied_to_saved_file': False, 'pc_remap_applied': False,
                'pc_preview_denoise_applied_to_saved_file': False,
                'fpga_mapping_mode_operator_unverified': True, 'saved': flow.stamp()}
            def work():
                ok, encoded = cv2.imencode('.png', image)
                if not ok: raise ValueError('PNG编码失败')
                metadata['sha256'] = flow.digest(encoded.tobytes())
                with path.open('xb') as output: output.write(encoded.tobytes())
                with path.with_suffix('.json').open('x', encoding='utf-8') as output:
                    output.write(json.dumps(metadata, ensure_ascii=False, indent=2))
                return '已保存数字帧：' + str(path)
            self.job(work)
        self.guarded(action)

    def import_files(self, split):
        paths = filedialog.askopenfilenames(filetypes=[('数字图像', '*.png *.jpg *.jpeg *.bmp')])
        if not paths: return
        def action():
            folder = self.require_session()
            def work():
                good, errors = 0, []
                for path in paths:
                    try: flow.save_frame(folder, flow.read_image(path), split, path); good += 1
                    except Exception as exc: errors.append(Path(path).name + ': ' + str(exc))
                return f'保存{good}张；未导入{len(errors)}张。\n' + '\n'.join(errors)
            self.job(work)
        self.guarded(action)

    def calibrate(self):
        def action():
            folder = self.require_session()
            self.job(lambda: flow.calibrate(folder), lambda result: self.set_model(result[0] / 'calibration.json'))
        self.guarded(action)

    def set_model(self, path):
        data = json.loads(Path(path).read_text(encoding='utf-8-sig')); flow.camera_matrix(data)
        self.model_path = Path(path); self.model = data
        if (data.get('source_kind_operator_declared') == 'ov5640_raw_digital'
                and not data.get('synthetic_test_data')
                and data.get('camera') == self.camera.get()):
            self.initial_demo.set(False)
            self.note('已选择本相机的真实镜头模型，并关闭“仅演示初估”；下发将使用这个模型。')
        self.note('已加载模型：' + str(path) + '；来源：' + str(data.get('source_kind_operator_declared')))
        self.update_model_source()
        self.refresh()

    def update_model_source(self):
        actual = (self.model is not None
            and self.model.get('source_kind_operator_declared') == 'ov5640_raw_digital'
            and not self.model.get('synthetic_test_data')
            and self.model.get('camera') == self.camera.get())
        if actual:
            self.initial_demo.set(False)
            self.initial_demo_box.configure(state='disabled')
            self.model_source_info.set('待发送：真实' + self.camera.get() + '镜头模型：' + str(self.model_path))
        else:
            self.initial_demo_box.configure(state='normal')
            self.model_source_info.set('待发送：旧间接初估，仅用于演示。' if self.initial_demo.get()
                else '待发送：尚未加载本相机的真实镜头模型；精确RAW可直接使用。')

    def load_model(self):
        path = filedialog.askopenfilename(filetypes=[('标定模型', '*.json')])
        if path: self.guarded(lambda: self.set_model(path))

    def real_model(self):
        if self.model is None: raise ValueError('请先完成实际镜头标定或加载相应JSON')
        if self.model.get('source_kind_operator_declared') != 'ov5640_raw_digital' or self.model.get('synthetic_test_data'):
            raise ValueError('下发和系数导出要求实际OV5640数字帧模型；当前初估/手机/合成模型不能作为实测参数')
        if self.model.get('camera') != self.camera.get():
            raise ValueError('请确认模型对应C1或C2，与所选相机保持一致')
        return self.model_path

    def command(self, args, out):
        env = os.environ.copy(); env['PYTHONIOENCODING'] = 'utf-8'
        run = subprocess.run([sys.executable, *map(str, args)], cwd=flow.ROOT,
                             capture_output=True, text=True, encoding='utf-8', errors='replace', env=env)
        text = run.stdout + run.stderr; Path(out).write_text(text, encoding='utf-8')
        if run.returncode: raise ValueError(text[-1800:] + '\n日志：' + str(out))
        return text + '\n日志：' + str(out)

    def destination(self, title):
        parent = filedialog.askdirectory(title=title)
        return Path(parent) / ('export_' + flow.stamp()) if parent else None

    def host(self, live, raw=False):
        def action():
            if live and not self.port.get().strip():
                raise ValueError('请先点击“列出串口”，选择USB-TTL的CH340端口；不要选择下载器COM口。尚未尝试通信。')
            if live and not self.wired.get():
                raise ValueError('接线确认框尚未勾选。请核对USB-TTL的TXD、RXD、GND和3.3V逻辑电平，再勾选“我已确认控制口与3.3V接线……”后发送。此提示不代表已检测到串口故障。')
            self.update_model_source()
            model = None if raw else (flow.ROOT / 'calib/ov5640_indirect_single_01.json' if self.initial_demo.get() else self.real_model())
            roll = float(self.roll.get())
            out = self.destination('保存指令和操作日志');
            if out is None: return
            out.mkdir()
            args = [flow.ROOT / 'tools/host_control.py', '--out', out / 'packet.bin', '--log', out / 'commands.jsonl']
            args += ['--raw'] if raw else ['--calib', model, '--roll', str(roll), '--zoom', '1']
            if not raw and self.initial_demo.get():args += ['--allow-indirect']
            if live: args += ['--port', self.port.get().strip(), '--watch', '4']
            self.reset_preview_processing()
            self.job(lambda: self.command(args, out / 'host.log'))
        self.guarded(action)

    def sweep(self):
        def action():
            model = self.real_model(); out = self.destination('导出离线±12度扫角包（不发送）')
            if out is None: return
            self.job(lambda: self.command([flow.ROOT / 'tools/host_sweep.py', '--calib', model,
                '--out-dir', out, '--amplitude', '12', '--duration', '8', '--fps', '10'], str(out) + '.log'))
        self.guarded(action)

    def export_coeff(self):
        def action():
            model = self.real_model(); out = self.destination('导出FPGA系数和验证报告')
            if out is None: return
            roll = self.roll.get()
            self.job(lambda: self.command([flow.ROOT / 'tools/calib_to_fpga.py', '--calib', model,
                '--out-dir', out, '--roll', roll, '--zoom', '1'], str(out) + '.log'))
        self.guarded(action)

    def list_ports(self):
        def action():
            from serial.tools import list_ports
            ports = list(list_ports.comports()); self.ports.configure(values=[p.device for p in ports])
            self.note('\n'.join(f'{p.device}: {p.description} [{p.hwid}]' for p in ports) or '未发现串口')
            self.note('仅列出端口；没有自动选择或发送。FTDI下载器通道须核对硬件接线。')
        self.guarded(action)

    def uart_measure(self):
        def action():
            if not self.port.get().strip():raise ValueError('请选择USB-TTL端口')
            out = self.destination('保存15秒串口实测报告（不发送参数）')
            if out is None:return
            out.mkdir()
            self.job(lambda: self.command([flow.ROOT / 'tools/uart_acceptance.py', '--port', self.port.get().strip(), '--seconds', '15', '--out', out / 'uart.json'], out / 'uart.log'))
        self.guarded(action)

    def uart_loopback(self):
        def action():
            if self.busy: raise ValueError('请先等待当前任务结束')
            if not self.port.get().strip(): raise ValueError('请先选择CH340对应的USB-TTL串口')
            confirmed = messagebox.askokcancel('仅测试USB-TTL自身',
                '请先关闭开发板电源，断开USB-TTL与开发板之间的TXD、RXD、GND连线，VCC不接。\n\n'
                '保持USB-TTL的USB连接电脑，用一根杜邦线将适配器自身TXD直接接到自身RXD。\n\n'
                '完成以上隔离自回环接线后，点确定开始测试；未完成请点取消。测试期间不要连接FPGA。')
            if not confirmed: return
            out = self.destination('保存USB-TTL自回环测试结果')
            if out is None: return
            out.mkdir()
            self.wired.set(False)
            self.job(lambda: self.command([flow.ROOT / 'tools/serial_loopback.py', '--port', self.port.get().strip(),
                '--isolated-loopback-confirmed', '--out', out / 'loopback.json'], out / 'loopback.log'))
        self.guarded(action)

    def uart_fps60(self):
        def action():
            if not self.port.get().strip():
                raise ValueError('请选择USB-TTL端口')
            out = self.destination('保存60秒帧率验收结果')
            if out is None: return
            out.mkdir()
            self.job(lambda: self.command([flow.ROOT / 'tools/image30_check.py', '--port', self.port.get().strip(), '--out', out / 'fps60.json'], out / 'fps60.log'))
        self.guarded(action)

    def live_sweep(self):
        def action():
            if not self.wired.get() or not self.port.get().strip():
                raise ValueError('请先确认控制串口和接线')
            model = self.real_model()
            out = self.destination('保存连续扫角轨迹与遥测')
            if out is None: return
            self.job(lambda: self.command([flow.ROOT / 'tools/host_sweep.py', '--calib', model,
                '--out-dir', out, '--port', self.port.get().strip(), '--amplitude', '8',
                '--hz', '0.1', '--duration', '8', '--fps', '20'], str(out) + '.log'))
        self.guarded(action)

    def static_project(self):
        def action():
            model = self.real_model()
            report = model.parent / 'validation/validation.json'
            if not report.is_file(): raise ValueError('需要标定流程生成的独立验证报告：' + str(report))
            out = self.destination('生成新工程，之后可用下载器烧录，无需UART')
            if out is None: return
            self.job(lambda: self.command([flow.ROOT / 'tools/prepare_calibrated_project.py',
                '--calib', model, '--validation', report, '--out', out], str(out) + '.log'))
        self.guarded(action)

    def guide(self):
        messagebox.showinfo('使用流程',
            '1. 实际取图需要HDMI数字采集或专门帧导出通道；普通USB线/下载器不提供本工具的视频输入。\n'
            '2. 固定棋盘于平板，测量格边，使用精确RAW指令、G0/T0/Q1、H0实时，关闭OSD；确认采集端不缩放裁切。\n'
            '3. 每颗镜头独立建会话，建议15—25张训练图和5—10张验证图；允许倾斜，覆盖中心和边缘。\n'
            '4. 标定并独立验证后查看报告，不能仅凭RMS宣称达到比赛标准。\n'
            '5. 角度是指定视图方向；没有水平参照就不能判断现场物体是否本来歪。\n'
            '6. USB-TTL：TXD接J8-15，RXD接J8-16，GND共地，VCC不接；115200/8N1。KEY3退出HST回本地。精确RAW指令不自动关闭Gamma、Q2或OSD，须按键核对。')

    def close(self):
        self.close_fullscreen()
        if self.preview_resize_after is not None:
            self.root.after_cancel(self.preview_resize_after); self.preview_resize_after = None
        self.close_capture(); self.preview_worker.close(); self.root.destroy()


if __name__ == '__main__':
    if os.name == 'nt':
        import ctypes
        ctypes.windll.user32.SetProcessDPIAware()
    app = tk.Tk(); Console(app); app.mainloop()
