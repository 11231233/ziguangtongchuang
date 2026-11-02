"""Release a diagnostic candidate without claiming an unmeasured hardware fix."""
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import hashlib,json,re,shutil,difflib,zipfile
p=Path(__file__).resolve().parents[1];old=Path('F:/codex_jibian_single_60hz')
b=p/'build/c1_dupont_diagnostic_720p60_20261026_b'
def sha(f):return hashlib.sha256(f.read_bytes()).hexdigest()
def load(f):return json.loads(f.read_text(encoding='utf-8'))
def save(f,obj):f.write_text(json.dumps(obj,indent=2,ensure_ascii=False),encoding='utf-8')
def need(ok,msg):
 if not ok:raise RuntimeError(msg)
preserved={}
for root,record in [
 (old,p/'reports/previous_60hz_sha256.json'),
 (Path('F:/codex_jibian_single_uart'),p/'reports/previous_single_sha256.json'),
 (Path('F:/codex_jibian_c2_fix'),p/'reports/previous_c2_sha256.json'),
 (Path('F:/codex_jibian_dual_q2'),Path('F:/codex_jibian_c2_fix/reports/previous_dual_q2_sha256.json')),
 (Path('F:/codex_jibian_quality_test'),Path('F:/codex_jibian_dual_q2/reports/previous_quality_project_sha256.json')),
 (Path('F:/codex_jibian'),Path('F:/codex_jibian_dual_q2/reports/original_working_project_sha256.json')),
 (Path('F:/FPGA_qianrushi'),Path('F:/codex_jibian/reports/original_source_sha256.json'))]:
 entries=load(record)
 for n,h in entries.items():need(sha(root/n)==h,'Previous source changed: '+str(root/n))
 preserved[str(root)]=len(entries)
for folder in ['rtl/warp','rtl/mem','rtl/cam','rtl/common','rtl/hdmi','rtl/ip','calib','targets','tools']:
 for f in (old/folder).rglob('*'):
  if f.is_file() and '__pycache__' not in f.parts:need(sha(p/f.relative_to(old))==sha(f),'Protected baseline changed: '+str(f))
for n in ['rtl/video/quality_display.v','rtl/ddr/sync_vg.v','constr/ddr3_pins.fdc']:
 need(sha(p/n)==sha(old/n),'Protected baseline changed: '+n)
def attrs(s):return {(a,b):v for a,b,v in re.findall(r'define_attribute\s+\{p:([^}]+)\}\s+\{([^}]+)\}\s+\{([^}]+)\}',s)}
a=attrs((old/'constr/board_pins.fdc').read_text(encoding='utf-8'));c=attrs((p/'constr/board_pins.fdc').read_text(encoding='utf-8'))
official=attrs((p/'reports/evidence/official_camera.fdc').read_text(encoding='utf-8-sig'))
changed={n for n in a.keys()|c.keys() if a.get(n)!=c.get(n)}
need(changed=={(f'cam_d[{i}]','PAP_IO_STANDARD') for i in range(8)},'Unexpected pin attribute changes')
for i in range(8):
 for attribute in ['PAP_IO_DIRECTION','PAP_IO_LOC','PAP_IO_VCCIO','PAP_IO_STANDARD','PAP_IO_NONE']:
  need(c[(f'cam_d[{i}]',attribute)]==official[(f'cmos1_data[{i}]',attribute)],'C1 input differs from official example')
validation=load(b/'validation.json');need(validation['passed'] and not validation['errors'],'PDS failed')
inputs=load(b/'input_manifest.json')
for n,h in inputs.items():need(sha(p/n)==h==sha(b/'snapshot'/n),'Build source mismatch: '+n)
log=(b/'console.log').read_text(errors='replace')
need(not re.search(r'^E:',log,re.M) and 'Executing : gen_bit_stream successfully.' in log,'PDS errors/incomplete generation')
timing=(b/'report_timing/top_pangu50.rtr').read_text(errors='replace')
need('Design Summary : All Constraints Met' in timing,'Timing failed')
def clock_line(name):return next(s for s in timing.splitlines() if s.strip().startswith(name+' ') and 'MHz' in s)
need('74.250 MHz' in clock_line('clk_pix'),'Not 720P60 pixel clock')
pixel_slack=float(clock_line('clk_pix').split()[-1]);ddr_slack=float(clock_line('ddrphy_clkin').split()[-1])
def ports(s):return {m.group(1):m.group(2) for m in re.finditer(r'^def_port \{([^}]+)\} (.*)$',s,re.M)}
pcf=(b/'device_map/top_pangu50.pcf').read_text(errors='replace')
before=ports((old/'reports/implemented_ports.pcf').read_text(errors='replace'));after=ports(pcf)
need(before.keys()==after.keys(),'External port inventory changed')
for name,value in before.items():
 if name in {f'cam_d[{i}]' for i in range(8)}:value=value.replace('IOSTANDARD=LVCMOS33','IOSTANDARD=LVCMOS12')
 need(value==after[name],'Implemented pin change outside intended scope: '+name)
top=(p/'rtl/top/top_pangu50.v').read_text(encoding='utf-8')
need('ov5640_checked_config u_cam_cfg' in top and '.config_ok(cam_cfg_done)' in top and '.scl(cam_scl),.sda(cam_sda)' in top,'Checked SCCB not connected to C1')
need('dvp_capture_phase u_cap' in top and 'camera_probe #(' in top,'Capture diagnostics missing')
need('cam2_pclk' not in top and 'quality_display #(.DEFAULT_MODE(2))' in top,'Single/Q2 defaults changed')
regpath=sorted((p/'sim/results').glob('*/summary.json'))[-1];reg=load(regpath)
need(reg['passed'] and reg['complete'] and len(reg['tests'])==40 and all(t['passed'] for t in reg['tests']),'Basic regression failed')
for n,h in reg['rtl_sha256'].items():need(sha(p/n)==h,'Regression source mismatch: '+n)
names=['camera_probe','sensor_diag','single_uart','quality_display','quality_controls','clock_720p60','c2_checked','c2_status_rom','dvp_phase']
for name in names:
 t=load(p/'reports'/(name+'_test.json'));need(t['passed'],'Failed suite: '+name)
 for n,h in t['source_sha256'].items():need(sha(p/n)==h,'Suite source mismatch: '+n)
 for ext in ['.log','_compile.log']:shutil.copy2(p/'sim/out'/(name+ext),p/'reports'/(name+ext))
for ext in ['.log','_compile.log']:shutil.copy2(p/'sim/out'/('raster_720p60'+ext),p/'reports'/('raster_720p60'+ext))
structure=load(p/'sim/out/top_structure.json');need(structure['passed'],'Structural check failed')
for n,h in structure['rtl_sha256'].items():need(sha(p/n)==h,'Structural source mismatch: '+n)
for src,dst in [(regpath,'rtl_regression_40.json'),(p/'sim/out/top_structure.json','top_structure.json'),(b/'validation.json','build_validation.json'),(b/'input_manifest.json','build_input_manifest.json'),(b/'report_timing/top_pangu50.rtr','timing_full.rtr'),(b/'device_map/top_pangu50.pcf','implemented_ports.pcf'),(b/'place_route/top_pangu50.prr','place_route.prr'),(b/'device_map/top_pangu50.dmr','device_map.dmr')]:shutil.copy2(src,p/'reports'/dst)
reglogs=p/'reports/rtl_regression_logs';reglogs.mkdir(exist_ok=True)
for f in regpath.parent.glob('*.log'):shutil.copy2(f,reglogs/f.name)
patch=[]
for n in ['rtl/top/top_pangu50.v','rtl/video/metrics_osd.v','constr/board_pins.fdc','constr/timing.fdc']:
 patch.extend(difflib.unified_diff((old/n).read_text(encoding='utf-8').splitlines(True),(p/n).read_text(encoding='utf-8').splitlines(True),fromfile='previous/'+n,tofile='diagnostic/'+n))
(p/'reports/diagnostic_changes.patch').write_text(''.join(patch),encoding='utf-8')
bit=p/'firmware/OV5640_C1_DUPONT_DIAGNOSTIC_720P60.sbit';shutil.copy2(b/'generate_bitstream/top_pangu50.sbit',bit)
need(bit.stat().st_size==2101696,'Unexpected bitstream size')
rollback=p/'firmware/ROLLBACK_SINGLE_C1_720P60.sbit'
need(sha(rollback)=='c280db068ecbf1ba7debc4cd8ad6ce0a2c97c5bad625cb53ca2501031d4c7dfd','Rollback differs')
manifest={'date':datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(),'bitstream':bit.name,'bytes':bit.stat().st_size,'sha256':sha(bit),'rollback':rollback.name,'rollback_sha256':sha(rollback),'build_validation':validation,'pixel7425_setup_slack_ns':pixel_slack,'ddr100_setup_slack_ns':ddr_slack,'nominal_HDMI_refresh_hz':60,'camera':'C1 only','quality':'Q2','C1_checked_init':True,'C1_native_bars':True,'C1_phase_switch_at_VS':True,'C1_format_switch_at_VS':True,'C1_data_input_attributes_match_official':True,'raw_probe_position':'y=360; x=80+160*n, n=0..7','raw_probe_has_VS_ack_mailbox':True,'UART_tx_edges_and_RX_bytes_displayed':True,'basic_RTL_regression_tests_passed':40,'additional_suites_passed':names,'physical_60Hz_whole_module_color_normal_user_confirmed':True,'physical_60Hz_Dupont_color_fault_user_confirmed':True,'physical_two_GND_wires_user_confirmed':True,'physical_diagnostic_firmware_tested':False,'specific_fault_bit_or_electrical_cause_confirmed':False,'hardware_color_fixed_confirmed':False,'hardware_UART_communication_passed':False,'real_lens_calibration_complete':False,'external_DVP_input_delay_constraints_complete':False,'preserved_source_counts':preserved}
save(p/'firmware/manifest_diagnostic.json',manifest)
(p/'firmware/SHA256SUMS.txt').write_text(''.join(sha(f)+'  '+f.name+'\n' for f in [bit,rollback]),encoding='ascii')
(p/'firmware/DOWNLOAD_NOW.txt').write_text('C1杜邦线诊断版：'+str(bit)+'\n默认C1/Q2/COR，R0/S0/B0。先整插下载并看I1 E0 D60，KEY0切RAW、KEY5长按开B1，等2秒拍诊断区作基准。再断电改杜邦线，上电重新下载同一SBIT，重复RAW/B1后比较S0/S1。KEY6短按切相位。\n探针显示8个原始字、O/A、V/M/像素总数、UART T/R计数。TFF且电脑0字节时检查J8-16到USB-TTL RXD。\n已确认旧固件整插正常、杜邦线偏绿；本候选仍需实板验证，未宣布修好。\n回退：'+str(rollback)+'\n',encoding='utf-8')
(p/'reports/交付摘要.md').write_text(f'# C1杜邦线诊断版交付\n\n时间：{manifest["date"]}\n\nSBIT：{bit.name}，{bit.stat().st_size}字节。SHA256：`{sha(bit)}`。\n\nPDS通过，DDR100MHz setup slack {ddr_slack:+.3f}ns，像素74.25MHz setup slack {pixel_slack:+.3f}ns。外部DVP输入延迟约束仍不完整。\n\n基础40项与9组补充套件通过，包含配置读回与重试、两种采样相位、数据位故障注入和跨时钟快照、单目顶层、诊断键/OSD、Q2与标准720P60。\n\n用户已确认前版同固件整插颜色正常、杜邦线偏绿且两根GND。异常与连接条件相关，尚未确认具体数据位或电气根因。本版对齐官方C1数据输入属性，并加入配置、采样和原始字诊断；改善后仍需区分各项作用。没有伪造新固件的实板验证或串口通过记录。\n\n原有全部版本源码校验通过，回退位流保留。\n',encoding='utf-8')
archive=p/'OV5640_C1_DUPONT_DIAGNOSTIC_20261026.zip';files=[]
for folder in ['rtl','constr','calib','targets','scripts','tools','sim/tb','sim/model','docs','firmware','reports']:
 files.extend(f for f in (p/folder).rglob('*') if f.is_file() and '__pycache__' not in f.parts and f.name!='delivery_file_hashes.json')
files.append(p/'README.md');need(len(files)==len(set(files)),'Duplicate archive path')
save(p/'reports/delivery_file_hashes.json',{f.relative_to(p).as_posix():sha(f) for f in files});files.append(p/'reports/delivery_file_hashes.json')
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
 for f in sorted(files):z.write(f,f.relative_to(p).as_posix())
with zipfile.ZipFile(archive) as z:
 need(z.testzip() is None,'Archive CRC failed')
 for f in files:need(hashlib.sha256(z.read(f.relative_to(p).as_posix())).hexdigest()==sha(f),'Archive content mismatch')
(p/'SHA256SUMS_delivery.txt').write_text(sha(archive)+'  '+archive.name+'\n',encoding='ascii')
print(json.dumps({'passed':True,'bitstream':str(bit),'sha256':sha(bit),'archive':str(archive),'archive_sha256':sha(archive),'DDR100_slack_ns':ddr_slack,'pixel7425_slack_ns':pixel_slack},indent=2))
