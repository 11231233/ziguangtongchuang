"""Display-only calibration guidance. Never changes saved images or gates."""
import cv2,numpy as np

LABELS={'left':'左','right':'右','top':'上','bottom':'下'}
CORNER_LABELS={'tl':'左上','tr':'右上','bl':'左下','br':'右下'}
def edge_counts(points,size):
 w,h=size;p=np.asarray(points).reshape(-1,2)
 return dict(left=int((p[:,0]<w*.15).sum()),right=int((p[:,0]>w*.85).sum()),
             top=int((p[:,1]<h*.15).sum()),bottom=int((p[:,1]>h*.85).sum()))

def corner_counts(points,size):
 w,h=size;p=np.asarray(points).reshape(-1,2)
 return {name:int((((p[:,0]<w*.25) if left else (p[:,0]>w*.75)) &
                   ((p[:,1]<h*.25) if top else (p[:,1]>h*.75))).sum())
         for name,left,top in [('tl',True,True),('tr',False,True),('bl',True,False),('br',False,False)]}

def frame_feedback(image,points=None):
 """Return an annotated COPY; dataset saving continues to use reconstructed RAW."""
 shown=image.copy();h,w=image.shape[:2]
 for x in (round(w*.15),round(w*.85)):cv2.line(shown,(x,0),(x,h-1),(0,0,255),2)
 for y in (round(h*.15),round(h*.85)):cv2.line(shown,(0,y),(w-1,y),(0,0,255),2)
 if points is None:return shown,'未识别到完整棋盘；辅助线仅用于定位原图边缘，不影响保存。'
 counts=edge_counts(points,(w,h))
 for x,y in np.asarray(points).reshape(-1,2):cv2.circle(shown,(round(float(x)),round(float(y))),3,(0,255,0),1)
 text='本张边缘角点：'+ '、'.join(LABELS[n]+str(v) for n,v in counts.items())
 corners=corner_counts(points,(w,h))
 text+='；本张四角：'+'、'.join(CORNER_LABELS[n]+str(v) for n,v in corners.items())
 return shown,text+'。四边每侧累计≥8点且训练至少2姿态，不要求单张8点；四角各有观测即可，不要求8点，也不是红线交点外的小格。棋盘及白边仍须完整；不要求单张覆盖四边。'

def calibration_summary(report):
 if report.get('ready_for_runtime'):return '标定与±20°覆盖检查通过，可生成实时源码；实际画质与帧率仍需实板验收。'
 lines=['暂不能生成正式实时源码，原有图片已保留。']
 if report.get('train_rms_px') is not None:lines.append(f'训练误差 {report["train_rms_px"]:.2f} 像素。')
 if report.get('heldout_rms_px') is not None:lines.append(f'独立验证误差 {report["heldout_rms_px"]:.2f} 像素。')
 coverage=report.get('spatial_coverage',{})
 if coverage.get('edges'):
  missing=[LABELS[n] for n,v in coverage['edges'].items() if v['views']<2 or v['points']<8]
  if missing:lines.append('训练边缘覆盖不足：'+'、'.join(missing)+'；每边至少2个姿态、累计8个角点。')
 corners={'tl':'左上','tr':'右上','bl':'左下','br':'右下'}
 missing=[corners[n] for n,v in coverage.get('corners',{}).items() if v==0]
 if missing:lines.append('训练四角缺少：'+'、'.join(missing)+'；各角有观测即可，不要求8点；角部范围为图宽/高各25%，并非红线外15%的交叉小格。')
 edges=report.get('heldout_edge_errors',{})
 missing=[LABELS[n] for n,v in edges.items() if v['points']<8]
 if missing:lines.append('验证边缘角点不足：'+'、'.join(missing)+'；每边累计至少8点。')
 if report.get('mapping_coverage',{}).get('passed'):lines.append('当前候选的±20°坐标覆盖检查通过，尚不代表真实画质达标。')
 for reason in report.get('reasons',[]):
  if reason.startswith('Independent image residual'):lines.append('图像拟合/独立验证误差超限，需检查图像与模型，不能仅靠补足数量。')
  elif reason.startswith('Independent validation edges'):lines.append('独立验证外圈观测不足或误差超限。')
  elif reason.startswith('Fixed-view'):lines.append('固定视野±20°的覆盖、定点误差或取块范围未通过。')
  elif not reason.startswith('Full-window'):lines.append(str(reason))
 return '\n'.join(lines)
