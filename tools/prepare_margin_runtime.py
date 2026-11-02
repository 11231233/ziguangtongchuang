"""Prepare a separate calibrated real-time FPGA project. No automatic flash."""
from pathlib import Path
import argparse,hashlib,json,re,shutil
from margin_geometry import load,identity,ROOT
from margin_calibration import coefficients,require_runtime_model
FIELDS=('A','B','C','D','E','F','k1','k2','p1','p2','fx','fy','cx','cy')
def packed(c):return sum((c[k]&0xffffffff)<<(32*i) for i,k in enumerate(FIELDS))
def render_controls(model,certified=False):
 if model.get('synthetic_test_data') or model.get('source_kind')!='verified_margin_raw_calibration':certified=False
 text=(ROOT/'tools/templates/margin_runtime_controls.v.tpl').read_text(encoding='utf-8');rows=[]
 for angle in range(-20,21):
  cor=packed(coefficients(model,angle));raw=packed(coefficients(model,angle,True));n=abs(angle)
  bcd=((angle<0)<<12)|((n//100)<<8)|(((n//10)%10)<<4)|(n%10)
  literal=("-10'sd"+str(-angle)) if angle<0 else ("10'sd"+str(angle))
  rows.append(f"   6'd{angle+20}:begin cor<=448'h{cor:0112x};raw<=448'h{raw:0112x};bcd<=13'h{bcd:04x};angle<={literal};end")
 return text.replace('@CERTIFIED@',str(int(certified))).replace('@ROWS@','\n'.join(rows)).replace('@ZERO@',f'{packed(coefficients(model,0)):0112x}').replace('@ZERO_RAW@',f'{packed(coefficients(model,0,True)):0112x}')

def prepare(model_path,report_path,out):
 out=Path(out)
 if out.exists():raise ValueError('Choose a NEW runtime project directory; source and captures will not be overwritten')
 if out.resolve().is_relative_to(ROOT.resolve()):raise ValueError('Runtime project must be a sibling/outside acquisition source, not nested inside it')
 model,report=require_runtime_model(model_path,report_path)
 # Evidence must still exist and match the independent calibration report.
 from margin_calibration import load_verified_frame
 g=load()
 if report.get('training_frames',0)<20 or report.get('validation_frames',0)<6:raise ValueError('Need 20 train + 6 held-out verified real captures')
 for item in report.get('source_images',[]):
  _,_,digest=load_verified_frame(item['file'],g)
  if digest!=item['sha256']:raise ValueError('Calibration data changed: '+item['file'])
 if len(report.get('source_images',[]))<26:raise ValueError('Missing real source evidence')
 return _write_project(model,model_path,report_path,out,True)

def _write_project(model,model_path,report_path,out,certified=False):
 out=Path(out);g=load()
 certified=bool(certified and not model.get('synthetic_test_data') and model.get('source_kind')=='verified_margin_raw_calibration')
 out.mkdir(parents=True)
 for name in ['rtl','constr','scripts','tools','targets','sim']:
  shutil.copytree(ROOT/name,out/name,ignore=shutil.ignore_patterns('__pycache__','out','results'))
 (out/'rtl/common/margin_runtime_controls.v').write_text(render_controls(model,certified),encoding='utf-8')
 rational=model.get('model_kind','poly2')=='rational5x6'
 if rational:
  rom=Path(model_path).parent/'radial_lut.hex'
  if not rom.is_file():raise ValueError('radial_lut.hex must sit next to the model: '+str(rom))
  shutil.copy2(rom,out/'rtl/warp/radial_lut.hex')
  rom_literal=(out/'rtl/warp/radial_lut.hex').resolve().as_posix()
 top=out/'rtl/top/top_pangu50.v';s=top.read_text(encoding='utf-8')
 if rational:
  anchor='.TILE(16),.AFFINE_FRAC_BITS(24)) u_warp_frame ('
  if s.count(anchor)!=1:raise ValueError('warp_frame parameter list changed; cannot enable the radial LUT')
  s=s.replace(anchor,'.TILE(16),.AFFINE_FRAC_BITS(24),\n                 .RADIAL_MODEL_LUT(1),\n                 .RADIAL_LUT_FILE("'+rom_literal+'")) u_warp_frame (')
  port='.start(wp_start), .busy(wp_busy), .done(wp_done),'
  if s.count(port)!=1:raise ValueError('warp_frame port list changed; cannot wire lut_enable')
  s=s.replace(port,'.start(wp_start), .lut_enable(local_correction_active),\n         .busy(wp_busy), .done(wp_done),')
 s=s.replace('wire display_visible_slot,metadata_ready;','wire display_visible_slot,runtime_certified,runtime_capture_ok;')
 s=s.replace('wire signed [9:0] active_angle=0;wire [12:0] angle_bcd=0;wire angle_toggle=0;',
             'wire signed [9:0] active_angle;wire [12:0] angle_bcd;wire angle_toggle;\n    wire[447:0]runtime_coeff;')
 old="{32'd0,32'd0,32'd33554432,32'd33554432,32'd0,32'd0,32'd0,32'd0,\n         (32'd128*roi_y),32'd32768,32'd0,(32'd128*roi_x),32'd0,32'd32768};"
 if s.count(old)!=1:raise ValueError('Acquisition top changed; inspect coefficient injection')
 s=s.replace(old,'runtime_coeff;')
 s,n=re.subn(r'assign local_correction_active=0;.*?\.roi_y\(roi_y\)\);',
 '''assign local_strength_active=0;assign local_zoom_active=0;assign restore_defaults=0;
    margin_runtime_controls u_controls(.clk(ddr_clk),.rstn(ddr_init_done),.frame_start(accept_source),
      .key_n({key3,key2,1'b1,raw_key_n}),.coeff(runtime_coeff),.active_enabled(local_correction_active),
      .active_angle(active_angle),.angle_bcd(angle_bcd),.angle_toggle(angle_toggle),.certified(runtime_certified));''',s,flags=re.S)
 if n!=1:raise ValueError('Controller injection failed')
 s=s.replace('.frame_valid(fw_frame_valid),.frame_seq', '.frame_valid(fw_frame_valid && runtime_capture_ok),.frame_seq')
 s=s.replace('.freeze_wanted(freeze_wanted),', '.freeze_wanted(freeze_wanted && runtime_capture_ok),')
 s=s.replace('.process_overflow(wp_ovf || !metadata_ready)', '.process_overflow(wp_ovf)')
 s=s.replace('.SRC_H(SRC_H),.V_ACT(688)', '.SRC_H(SRC_H),.V_ACT(720)')
 start=s.index('    wire [7:0] capture_flags=');end=s.index('    reg de_aligned=',start)
 s=s[:start]+'    assign runtime_capture_ok=runtime_certified && config_sync[1] && !fault_sync[1];\n\n'+s[end:]
 fragment=(ROOT/'tools/templates/margin_runtime_osd.vfrag').read_text(encoding='utf-8')
 s,n=re.subn(r'margin_footer u_footer\(.*?\.overlay\(osd_overlay\)\);',fragment.strip(),s,flags=re.S)
 if n!=1:raise ValueError('OSD injection failed')
 top.write_text(s,encoding='utf-8')
 osd=out/'rtl/video/metrics_osd.v';text=osd.read_text(encoding='utf-8')
 text=text.replace('4:character="S";','4:character="M";').replace('5:character=visible[41]?"-":("0"+{6\'d0,visible[39:38]});','5:character="1";')
 osd.write_text(text,encoding='utf-8')
 (out/'calib').mkdir();shutil.copy2(model_path,out/'calib/calibration.json');shutil.copy2(report_path,out/'calib/validation.json')
 (out/'reports').mkdir();record=dict(geometry_sha256=identity(g)[0],model_sha256=hashlib.sha256(Path(model_path).read_bytes()).hexdigest(),
  output_camera=model['output_camera'],angle_limits=[-20,20],no_auto_zoom=True,source_size=g['source_size'],
  runtime_source_prepared=True,certified_real_model=certified,rtl_runtime_tested=False,pds_built=False,hardware_tested=False)
 (out/'reports/calibrated_runtime_origin.json').write_text(json.dumps(record,indent=2),encoding='utf-8')
 (out/'README.md').write_text('''# 新窗口真实标定实时工程（源码已生成，尚未构建/下板）

固定720P输出与虚拟相机参数，按键角度限制±20°，无自动缩放或镜像补边。COR使用calib中的已独立验证模型；KEY0短按RAW/COR，KEY1长按冻结，KEY2/3加减角且按住连调，双键归零/长按恢复COR。KEY0长按不再缩放，KEY1短按不修改真实标定系数。OSD显示COR M1 Z0及生效角度。

仍需对本模型运行真实RTL全帧、DDR并发和PDS构建，再做实际画质/30fps验收。原始采集固件与运行固件职责不同，运行模式不输出WRAW取图页。不能将已生成源码当作已完成下板。
''',encoding='utf-8')
 return record

def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--model',type=Path,required=True);ap.add_argument('--validation',type=Path,required=True);ap.add_argument('--out',type=Path,required=True);a=ap.parse_args()
 print(json.dumps(prepare(a.model,a.validation,a.out),indent=2))
if __name__=='__main__':main()
