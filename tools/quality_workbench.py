"""Local photo-assisted engineering workbench; never auto-applies camera coefficients."""
import datetime
import queue
import subprocess
import sys
import threading
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
from PIL import Image, ImageTk
from rectify_monitor import load_image, rectify
from measure_sfr import save as save_sfr

ROOT = Path(__file__).resolve().parents[1]


class Workbench:
    def __init__(self, root):
        self.root=root; root.title('FPGA 图像质量工作台 — 手机拍屏为间接测量')
        self.path=None; self.points=[]; self.phone=None; self.image=None; self.scale=1
        self.jobs=queue.Queue(); self.busy=False
        bar=ttk.Frame(root); bar.pack(fill='x')
        for title, command in [('打开照片',self.open),('手机标定模型',self.phone_model),
                               ('清除选点',self.clear),('展开屏幕',self.export),
                               ('测量斜边 SFR',self.sfr),('棋盘标定',self.calibrate),
                               ('RAW/COR直线度',self.straightness),('操作说明',self.guide)]:
            ttk.Button(bar,text=title,command=command).pack(side='left',padx=2,pady=5)
        options=ttk.Frame(root); options.pack(fill='x')
        self.selection=tk.StringVar(value='屏幕四角'); self.mode=tk.StringVar(value='RAW')
        self.gamma=tk.StringVar(value='G0'); self.test=tk.StringVar(value='T0')
        self.source=tk.StringVar(value='phone_screen')
        for label,var,values in [('选点',self.selection,['屏幕四角','斜边ROI']),('画面',self.mode,['RAW','COR']),
                                 ('Gamma',self.gamma,['G0','G1','G2','G3']),('测试',self.test,['T0','T1','T2']),
                                 ('SFR来源',self.source,['phone_screen','monitor_rectified','digital_hdmi'])]:
            ttk.Label(options,text=label).pack(side='left',padx=4)
            ttk.Combobox(options,textvariable=var,values=values,state='readonly',width=18).pack(side='left')
        ttk.Label(root,text='屏幕四角：依次点有效画面左上、右上、右下、左下（不是外壳）。斜边ROI：点矩形对角两点。切换选点方式前清除。').pack()
        self.canvas=tk.Canvas(root,width=1000,height=620,bg='#202020'); self.canvas.pack()
        self.canvas.bind('<Button-1>',self.click)
        self.status=tk.StringVar(value='请打开原始照片；间接估计不等同原始数字帧标定。')
        ttk.Label(root,textvariable=self.status,wraplength=1000).pack(fill='x',padx=5,pady=5)
        self.root.after(100,self.poll)

    def open(self):
        path=filedialog.askopenfilename(filetypes=[('图像','*.jpg *.jpeg *.png *.bmp'),('全部','*.*')])
        if not path:return
        try:
            im=load_image(path); self.path=Path(path); self.image=im
            self.scale=min(1000/im.shape[1],620/im.shape[0],1)
            pic=Image.fromarray(im[:,:,::-1]); pic=pic.resize((round(im.shape[1]*self.scale),round(im.shape[0]*self.scale)))
            self.photo=ImageTk.PhotoImage(pic); self.canvas.delete('all')
            self.canvas.create_image(0,0,anchor='nw',image=self.photo); self.points=[]
            self.status.set(str(self.path))
        except Exception as e: messagebox.showerror('读取失败',str(e))

    def phone_model(self):
        path=filedialog.askopenfilename(title='选择 phone_direct 标定 JSON；取消则清除模型',filetypes=[('JSON','*.json')])
        self.phone=Path(path) if path else None
        self.status.set('手机模型：'+str(self.phone))

    def clear(self):
        self.points=[]; self.canvas.delete('mark')

    def click(self,event):
        if self.image is None:return
        x,y=event.x/self.scale,event.y/self.scale
        if x>=self.image.shape[1] or y>=self.image.shape[0]:return
        limit=4 if self.selection.get()=='屏幕四角' else 2
        if len(self.points)>=limit:self.clear()
        self.points.append([x,y]); self.canvas.create_oval(event.x-4,event.y-4,event.x+4,event.y+4,fill='red',tags='mark')
        self.canvas.create_text(event.x+12,event.y,text=str(len(self.points)),fill='yellow',tags='mark')

    def destination(self,prefix):
        parent=filedialog.askdirectory(title='选择输出父目录；自动创建新目录保留证据')
        return Path(parent)/(prefix+'_'+datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f')) if parent else None

    def export(self):
        if self.path is None or len(self.points)!=4 or self.selection.get()!='屏幕四角':
            messagebox.showerror('需要四角','打开照片，并依次选择有效画面的四角。'); return
        out=self.destination('screen')
        if out:
            args=(self.path,list(self.points),out,self.phone,self.mode.get(),self.gamma.get(),self.test.get())
            self.run(lambda: str(rectify(*args))+'\n输出：'+str(out))

    def sfr(self):
        if self.path is None or len(self.points)!=2 or self.selection.get()!='斜边ROI':
            messagebox.showerror('需要ROI','选择斜边ROI，并点矩形对角两点。'); return
        exponent=simpledialog.askfloat('响应曲线','显式线性化指数：未知时保留1，并仅作工程对照。',initialvalue=1,minvalue=.1,maxvalue=5)
        if exponent is None:return
        out=self.destination('sfr')
        if not out:return
        a,b=self.points; x,y=round(min(a[0],b[0])),round(min(a[1],b[1]))
        roi=[x,y,round(abs(a[0]-b[0])),round(abs(a[1]-b[1]))]
        path,source=self.path,self.source.get()
        def job():
            result=save_sfr(path,roi,out,source,exponent)
            return 'MTF50='+str(result['mtf50_cycles_per_pixel'])+' cycles/pixel\n'+result['scope']+'\n'+str(out)
        self.run(job)

    def command(self,args,out):
        r=subprocess.run([sys.executable,*map(str,args)],cwd=ROOT,capture_output=True,text=True,encoding='utf-8',errors='replace')
        log=r.stdout+r.stderr
        Path(str(out)+'.log').write_text(log,encoding='utf-8')
        if r.returncode:raise ValueError(log)
        return log

    def calibrate(self):
        role=simpledialog.askstring('标定对象','输入 phone_direct（手机直接拍棋盘）或 monitor_rectified（展开的RAW/G0/T0屏幕）',initialvalue='phone_direct')
        if role not in ('phone_direct','monitor_rectified'):return
        folder=filedialog.askdirectory(title='选择标定图片父目录')
        if not folder:return
        pattern=simpledialog.askstring('图片路径','相对该目录的通配式；展开帧可填 */screen.png',initialvalue='*.jpg' if role=='phone_direct' else '*/screen.png')
        if not pattern:return
        cols=simpledialog.askinteger('内角点','内角点列数（不是格子数）',initialvalue=9,minvalue=3)
        rows=simpledialog.askinteger('内角点','内角点行数',initialvalue=6,minvalue=3)
        square=simpledialog.askfloat('实测格子边长','输入实际测量的单格边长，毫米；不要照抄模板',minvalue=.01)
        if None in (cols,rows,square):return
        out=filedialog.asksaveasfilename(title='保存到新JSON文件',defaultextension='.json')
        if out:self.run(lambda:self.command([ROOT/'tools/calib_ov5640.py','--images',str(Path(folder)/pattern),'--cols',cols,'--rows',rows,'--square',square,'--source-kind',role,'--out',out],out))

    def straightness(self):
        raw=filedialog.askopenfilename(title='选择RAW手机照片'); cor=filedialog.askopenfilename(title='选择COR手机照片') if raw else ''
        if not cor:return
        cols=simpledialog.askinteger('棋盘','内角点列数',initialvalue=9,minvalue=3)
        rows=simpledialog.askinteger('棋盘','内角点行数',initialvalue=6,minvalue=3)
        if None in (cols,rows):return
        out=self.destination('straightness')
        if out:self.run(lambda:self.command([ROOT/'tools/compare_straightness.py','--raw',raw,'--cor',cor,'--cols',cols,'--rows',rows,'--source','phone_screen','--out',out],out))

    def run(self,job):
        if self.busy:messagebox.showinfo('正在计算','请等待当前任务结束。'); return
        self.busy=True; self.status.set('正在计算，请稍候……')
        def worker():
            try:self.jobs.put((True,job()))
            except Exception as e:self.jobs.put((False,str(e)))
        threading.Thread(target=worker,daemon=True).start()

    def poll(self):
        try:
            good,text=self.jobs.get_nowait(); self.busy=False
            self.status.set('完成' if good else '失败，详见提示')
            window=tk.Toplevel(self.root); window.title('结果' if good else '检查输入')
            box=tk.Text(window,width=110,height=30,wrap='word'); box.pack(fill='both',expand=True); box.insert('1.0',text)
        except queue.Empty:pass
        self.root.after(100,self.poll)

    def guide(self):
        window=tk.Toplevel(self.root); window.title('操作说明与验收边界')
        box=tk.Text(window,width=110,height=38,wrap='word'); box.pack(fill='both',expand=True)
        box.insert('1.0',(ROOT/'docs/35_赛题完整性与无采集卡工作台.md').read_text(encoding='utf-8'))
        box.configure(state='disabled')


if __name__=='__main__':
    app=tk.Tk(); Workbench(app); app.mainloop()
