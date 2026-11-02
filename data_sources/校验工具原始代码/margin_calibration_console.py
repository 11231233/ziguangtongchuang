"""Full-window RAW capture/calibration assistant; devices open only on click."""
from pathlib import Path
import json,threading,queue,tkinter as tk,os,hashlib
from tkinter import ttk,filedialog,messagebox
from PIL import Image,ImageTk
import cv2
from margin_geometry import load,identity,ROOT
from reconstruct_margin_frame import reconstruct,decode,canonical_capture
from preview_stream import LatestCapture
import margin_dataset
from margin_calibration import calibrate
from calibration_inputs import parse_inner_corners,parse_board_inputs
from prepare_margin_runtime import prepare
from margin_feedback import frame_feedback,calibration_summary
from checkerboard_detection import detect_checkerboard,CheckerboardNotFound
class Console:
 def __init__(self,root):
  self.root=root;root.title('C1 全窗口原始采集与真实标定');root.geometry('1150x900')
  self.folder=None;self.pages=[];self.result=None;self.busy=False;self.q=queue.Queue();self.photo=None
  self.device=tk.StringVar(value='0');self.capture_status=tk.StringVar(value='采集卡未打开；按CRC标签恢复整帧方向，不做降噪或电脑校正。')
  self.reader=None;self.raw=None;self.sequence=0;self.live_preview=True;self.saved_pages={};self.saved_fid=None
  root.protocol('WM_DELETE_WINDOW',self.exit)
  self.cols=tk.StringVar(value='6');self.rows=tk.StringVar(value='9');self.square=tk.StringVar(value='')
  self.confirmed=tk.BooleanVar(value=False);self.status=tk.StringVar(value='先在采集固件H1冻结，保存同一F编号的P0—P3四张数字PNG。')
  self.coverage_lines=tk.BooleanVar(value=True)
  panel=ttk.Frame(root,padding=10);panel.pack(fill='x')
  ttk.Label(panel,text='1296×972原始全窗口 → 新真实标定 → 固定720P视野、±20°实时工程',font=('Microsoft YaHei',14)).pack(anchor='w')
  ttk.Label(panel,text=f'几何编号 {identity(load())[1]:08X}；不使用旧720P模型，不自动打开相机、串口或下板。').pack(anchor='w')
  row=ttk.Frame(panel);row.pack(fill='x',pady=6)
  ttk.Label(row,text='采集卡设备号（不是COM号）').pack(side='left');ttk.Entry(row,textvariable=self.device,width=5).pack(side='left')
  for text,fn in [('打开采集卡',self.open_capture),('关闭采集卡',self.close_capture),('实时原图预览',self.resume_preview),('保存当前页',self.save_page),('预览方向',self.cycle_preview)]:ttk.Button(row,text=text,command=fn).pack(side='left',padx=3)
  ttk.Label(panel,textvariable=self.capture_status).pack(anchor='w')
  row=ttk.Frame(panel);row.pack(fill='x',pady=6)
  for text,fn in [('新建数据集',self.new),('打开数据集',self.open),('选择四页PNG',self.choose),('重建检查',self.preview),('保存训练帧',lambda:self.save('train')),('保存验证帧',lambda:self.save('validation'))]:ttk.Button(row,text=text,command=fn).pack(side='left',padx=3)
  row=ttk.Frame(panel);row.pack(fill='x')
  for text,var in [('内角点列',self.cols),('行',self.rows),('实测格边/mm',self.square)]:
   ttk.Label(row,text=text).pack(side='left');ttk.Entry(row,textvariable=var,width=8).pack(side='left',padx=4)
  ttk.Checkbutton(panel,text='我确认：新全窗口原始画面已核对，镜头焦点/模式固定；本数据集保持同一次下板，训练与验证姿态分开。',variable=self.confirmed).pack(anchor='w',pady=5)
  ttk.Checkbutton(panel,text='重建图显示边缘线、角点和四角计数（四边累计8点；四角只需有观测；仅预览）',variable=self.coverage_lines).pack(anchor='w')
  row=ttk.Frame(panel);row.pack(fill='x')
  ttk.Button(row,text='计算并独立验证（20训练+6验证后）',command=self.calibrate).pack(side='left',padx=3)
  ttk.Button(row,text='生成通过校验的实时源码工程',command=self.export).pack(side='left',padx=3)
  ttk.Label(panel,textvariable=self.status,wraplength=1020).pack(anchor='w',pady=8)
  self.image_label=ttk.Label(root);self.image_label.pack(expand=True)
  self.preview_mode=self.load_preview_mode()
  self.log=tk.Text(root,height=8);self.log.pack(fill='x');self.root.after(100,self.poll)
  self.root.after(100,self.capture_tick)
 def show(self,image):
  im=Image.fromarray(cv2.cvtColor(image,cv2.COLOR_BGR2RGB));im.thumbnail((1000,400));self.photo=ImageTk.PhotoImage(im);self.image_label.configure(image=self.photo)
 PREVIEW_MODES=(('原样',None),('旋转180°',cv2.ROTATE_180),('水平镜像','h'),('垂直翻转','v'))
 def preview_file(self):return Path(__file__).with_name('.preview_orientation.json')
 def load_preview_mode(self):
  try:return int(json.loads(self.preview_file().read_text(encoding='utf-8')).get('mode',0))%len(self.PREVIEW_MODES)
  except (OSError,ValueError,TypeError):return 0
 def apply_preview(self,image):
  # Display-only transform. The frame written by 保存当前页 is always the untouched
  # transport raster, so the preview can never change capture evidence.
  mode=self.PREVIEW_MODES[self.preview_mode][1]
  if mode is None:return image
  if isinstance(mode,int):return cv2.rotate(image,mode)
  return cv2.flip(image,1) if mode=='h' else cv2.flip(image,0)
 def cycle_preview(self):
  self.preview_mode=(self.preview_mode+1)%len(self.PREVIEW_MODES)
  try:self.preview_file().write_text(json.dumps({'mode':self.preview_mode}),encoding='utf-8')
  except OSError:pass
  self.capture_status.set('预览方向：'+self.PREVIEW_MODES[self.preview_mode][0]+'（只影响预览，保存不受影响）')
 def open_capture(self):
  def action():
   self.close_capture()
   try:device=int(self.device.get())
   except ValueError:raise ValueError('设备号填0、1、2等整数，不填COM口')
   if device<0:raise ValueError('设备号不能为负数')
   cap=cv2.VideoCapture(device,cv2.CAP_DSHOW if os.name=='nt' else cv2.CAP_ANY)
   if not cap.isOpened():cap.release();raise ValueError('采集卡未打开；关闭其他占用视频设备的软件，核对设备号')
   cap.set(cv2.CAP_PROP_FRAME_WIDTH,1280);cap.set(cv2.CAP_PROP_FRAME_HEIGHT,720)
   self.reader=LatestCapture(cap);self.raw=None;self.sequence=0;self.live_preview=True
   self.capture_status.set('采集卡已打开；请核对画面来自FPGA HDMI，并确认底部CALIB文字朝向正确')
  self.guarded(action)
 def close_capture(self):
  if self.reader is not None:self.reader.stop();self.reader=None
  self.raw=None;self.capture_status.set('采集卡已关闭')
 def resume_preview(self):self.live_preview=True
 def capture_tick(self):
  if self.reader is not None:
   frame=self.reader.latest(self.sequence)
   if frame is not None:
    self.sequence,_,self.raw=frame
    try:
     shown,tag,orientation=canonical_capture(self.raw)
     direction='已依据标签恢复整帧上下翻转' if orientation=='vertical' else '整帧方向正常'
    except ValueError:
     shown=self.raw;direction='等待有效的新窗口标签；不猜测画面方向'
    if self.live_preview and not self.busy:self.show(self.apply_preview(shown))
    self.capture_status.set(f'采集返回{self.raw.shape[1]}×{self.raw.shape[0]}；{direction}；保存保持原尺寸')
   if self.reader.error:self.capture_status.set('采集异常：'+self.reader.error)
  self.root.after(100,self.capture_tick)
 def save_page(self):
  def action():
   if self.folder is None:raise ValueError('先新建/打开数据集；原始页会保存在该目录incoming_pages')
   if self.raw is None:raise ValueError('先打开采集卡')
   transport=self.raw.copy();image,_,orientation=canonical_capture(transport);tag=decode(image);fid=tag['source_frame_id'];page=tag['page']
   folder=self.folder/'incoming_pages';folder.mkdir(exist_ok=True)
   path=folder/f'F{fid:08X}_P{page}_{margin_dataset.stamp()}.png';ok,data=cv2.imencode('.png',image)
   if not ok:raise ValueError('PNG编码失败')
   path.write_bytes(data.tobytes())
   if orientation!='identity':
    originals=folder/'transport_originals';originals.mkdir(exist_ok=True)
    original=originals/path.name;original.write_bytes(cv2.imencode('.png',transport)[1].tobytes())
    path.with_suffix('.json').write_text(json.dumps(dict(schema='margin_transport_restore_v1',
     normalization=orientation,original=str(original.resolve()),original_sha256=hashlib.sha256(original.read_bytes()).hexdigest(),
     canonical_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),footer_crc_verified=True),indent=2),encoding='utf-8')
   if self.saved_fid!=fid:self.saved_pages={};self.saved_fid=fid
   self.saved_pages[page]=str(path);self.pages=[self.saved_pages[p] for p in sorted(self.saved_pages)]
   text=f'已保存P{page}，F{fid:08X}；本组已有'+','.join('P'+str(p) for p in sorted(self.saved_pages))
   if len(self.pages)==4:text+='；四页齐全，点击“重建检查”'
   self.status.set(text);self.log.insert('end',str(path)+'\n');self.log.see('end')
  self.guarded(action)
 def exit(self):self.close_capture();self.root.destroy()
 def count(self):
  if self.folder:return f'训练{len(list((self.folder/"train").glob("*.png")))}/20；验证{len(list((self.folder/"validation").glob("*.png")))}/6；{self.folder}'
  return '尚无数据集'
 def guarded(self,fn):
  try:
   if self.busy:raise ValueError('请等待当前处理完成')
   fn()
  except Exception as exc:messagebox.showerror('无法完成',str(exc))
 def job(self,fn):
  self.busy=True;self.status.set('处理中……')
  def run():
   try:self.q.put((True,fn()))
   except Exception as exc:self.q.put((False,str(exc)))
  threading.Thread(target=run,daemon=True).start()
 def poll(self):
  try:
   ok,value=self.q.get_nowait();self.busy=False
   if ok:
    text,image=value;self.status.set(text);self.log.insert('end',text+'\n');self.log.see('end')
    if image is not None:
     self.live_preview=False;self.show(image)
   else:self.status.set(value);self.log.insert('end',value+'\n');messagebox.showerror('未通过',value)
  except queue.Empty:pass
  self.root.after(100,self.poll)
 def new(self):
  def action():
   parent=filedialog.askdirectory(title='选择新全窗口数据集的父目录',initialdir='F:/chuankou')
   if parent:self.folder=margin_dataset.create(parent);self.result=None;self.reset_pages();self.status.set(self.count())
  self.guarded(action)
 def open(self):
  def action():
   path=filedialog.askdirectory(title='选择含dataset.json的新全窗口数据集')
   if path:self.folder=margin_dataset.validate(path);self.result=None;self.reset_pages();self.status.set(self.count())
  self.guarded(action)
 def reset_pages(self):self.pages=[];self.saved_pages={};self.saved_fid=None
 def choose(self):
  def action():
   paths=filedialog.askopenfilenames(title='选择同一冻结F编号的P0、P1、P2、P3四张数字PNG',filetypes=[('PNG','*.png')])
   if paths:
    if len(paths)!=4:raise ValueError('必须正好选择四张PNG，不选JSON')
    self.pages=list(paths);self.status.set('已选择四页；点重建检查')
  self.guarded(action)
 def preview(self):
  def action():
   if len(self.pages)!=4:raise ValueError('先选择同一冻结帧的四页PNG')
   pattern=parse_inner_corners(self.cols.get(),self.rows.get());show_lines=self.coverage_lines.get()
   def work():
    image,meta=reconstruct(self.pages);text=f'重建通过：1296×972，F={meta["source_frame_id"]}，几何={meta["geometry_id"]:08X}；'+self.count()
    if show_lines:
     try:points=detect_checkerboard(image,pattern)['points']
     except CheckerboardNotFound:points=None
     image,guidance=frame_feedback(image,points);text+='\n'+guidance
    return text,image
   self.job(work)
  self.guarded(action)
 def save(self,split):
  def action():
   if self.folder is None:raise ValueError('先新建/打开数据集')
   pattern=parse_inner_corners(self.cols.get(),self.rows.get())
   def work():
    path=margin_dataset.save(self.folder,self.pages,split,pattern);self.result=None;return ('已保存 '+str(path)+'；'+self.count(),None)
   self.job(work)
  self.guarded(action)
 def calibrate(self):
  def action():
   if self.folder is None:raise ValueError('先新建/打开数据集')
   values=parse_board_inputs(self.cols.get(),self.rows.get(),self.square.get())
   cols,rows,square=values;pattern=(cols,rows);confirmed=self.confirmed.get()
   result=self.folder/'results'/('calib_'+margin_dataset.stamp())
   def work():
    report=calibrate(self.folder,result,pattern,square,confirmed);self.result=result
    return ('标定结果 '+str(result)+'\n'+calibration_summary(report),None)
   self.job(work)
  self.guarded(action)
 def export(self):
  def action():
   if self.result is None:raise ValueError('先计算并独立验证本次新窗口模型')
   parent=filedialog.askdirectory(title='选择新实时源码工程的父目录（不要放在采集工程内部）')
   if not parent:return
   out=Path(parent)/('C1_margin20_runtime_'+margin_dataset.stamp())
   def work():
    prepare(self.result/'calibration.json',self.result/'validation.json',out)
    return ('已生成实时源码 '+str(out)+'；仍需本模型RTL验证、PDS构建及实板验收，尚未下板。',None)
   self.job(work)
  self.guarded(action)
if __name__=='__main__':
 root=tk.Tk();Console(root);root.mainloop()
