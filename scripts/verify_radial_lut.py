"""Simulate rtl/warp/radial_lut.v against the generated ROM and check it bit-exactly.

Chain under test:
    double-precision rational model  (validated by gen_radial_lut_rom.py)
      -> 2048-cell Q24 ROM + Q16 interpolation  (this script's golden vectors)
        -> radial_lut.v RTL                     (iverilog)

The script owns a private report directory so it can run concurrently with the
shared `sim/out` regressions.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import os
from pathlib import Path

import numpy as np

IVERILOG = Path(os.environ.get("IVERILOG", r"D:/iverilog/bin/iverilog.exe"))
VVP = Path(os.environ.get("VVP", r"D:/iverilog/bin/vvp.exe"))
ROOT = Path(__file__).resolve().parents[1]

R2_Q16_MAX = 2097152


def emulate(words: np.ndarray, r2_q16: np.ndarray) -> np.ndarray:
    r2 = np.asarray(r2_q16, dtype=np.int64)
    endpoint = r2 >= R2_Q16_MAX
    address = np.where(endpoint, 2047, (r2 >> 10) & 2047)
    frac = np.where(endpoint, 1024, r2 & 1023)
    raw = words[address]
    hi = (raw >> np.uint64(32)).astype(np.int64)
    lo = (raw & np.uint64(0xFFFFFFFF)).astype(np.int64)
    base = np.where(hi >= (1 << 31), hi - (1 << 32), hi)
    delta = np.where(lo >= (1 << 31), lo - (1 << 32), lo)
    return ((base << 10) + delta * frac + (1 << 17)) >> 18


def build_vectors(rom: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    words = np.array([int(line, 16) for line in rom.read_text().split()], dtype=np.uint64)
    if words.size != 2048:
        raise SystemExit(f"{rom} holds {words.size} words, expected 2048")

    edge = [0, 1, 511, 512, 1023, 1024, 1025, 10239, 10240, 65535, 65536,
            1048575, 1048576, 2097151, 2097152]
    outside = [-1, -1024, -65536, 2097153, 4194304, 0x7FFFFFFF]
    sweep = list(range(0, R2_Q16_MAX + 1, 1009))
    r2 = np.array(sorted(set(edge + outside + sweep)), dtype=np.int64)

    factor = emulate(words, r2)
    in_range = ((r2 >= 0) & (r2 <= R2_Q16_MAX)).astype(np.int64)
    return r2, factor, in_range


def tb_source(rom_posix: str) -> str:
    return f"""`timescale 1ns/1ps
`default_nettype none
module tb_radial_lut;
 reg clk=0,rstn=0,valid_i=0;
 reg signed [31:0] r2=0;
 wire valid_o,in_range_o;
 wire signed [31:0] factor_q16;
 integer fd,n,i,errs_f,errs_r,valid_hits;
 integer vec_r2,vec_f,vec_ok;
 reg signed [31:0] got_f;
 reg got_ok;

 radial_lut #(.ROM_FILE("{rom_posix}")) dut(
  .clk(clk),.rstn(rstn),.valid_i(valid_i),.r2_q16(r2),
  .valid_o(valid_o),.in_range_o(in_range_o),.factor_q16(factor_q16));

 always #5 clk=~clk;

 initial begin
  errs_f=0;errs_r=0;valid_hits=0;
  fd=$fopen("vectors.hex","r");
  if(fd==0) begin $display("FAIL cannot open vectors.hex"); $finish; end
  n=0;
  while(!$feof(fd)) begin
   if($fscanf(fd,"%h %h %h\\n",vec_r2,vec_f,vec_ok)==3) n=n+1;
  end
  $fclose(fd);
  $display("vectors=%0d",n);
  reset_and_run;
  $display("RESULT errors_factor=%0d errors_range=%0d valid_pulses=%0d",errs_f,errs_r,valid_hits);
  if(errs_f==0 && errs_r==0 && valid_hits==n) $display("PASS");
  else $display("FAIL");
  $finish;
 end

 task reset_and_run;
  begin
   rstn=1'b0;repeat(4) @(posedge clk);@(negedge clk);rstn=1'b1;@(negedge clk);
   fd=$fopen("vectors.hex","r");
   i=0;
   while(!$feof(fd)) begin
    if($fscanf(fd,"%h %h %h\\n",vec_r2,vec_f,vec_ok)!=3) disable reset_and_run;
    @(negedge clk); r2=vec_r2; valid_i=1'b1;
    @(negedge clk); valid_i=1'b0;
    repeat(2) @(negedge clk);
    if(!valid_o) begin
     errs_f=errs_f+1;
     $display("MISSING valid_o r2=%h exp=%h",vec_r2,vec_f);
    end else begin
     valid_hits=valid_hits+1;
     got_f=factor_q16; got_ok=in_range_o;
     if(got_f!==vec_f) begin
      errs_f=errs_f+1;
      if(errs_f<=8) $display("FACTOR r2=%h got=%h exp=%h",vec_r2,got_f,vec_f);
     end
     if(got_ok!==vec_ok[0]) begin
      errs_r=errs_r+1;
      if(errs_r<=8) $display("RANGE r2=%h got=%0b exp=%b",vec_r2,got_ok,vec_ok[0]);
     end
    end
    repeat(2) @(negedge clk);
    i=i+1;
   end
   $fclose(fd);
  end
 endtask
endmodule
`default_nettype wire
"""


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--rom", default=str(ROOT / "rtl/warp/radial_lut.hex"))
    ap.add_argument("--rtl", default=str(ROOT / "rtl/warp/radial_lut.v"))
    ap.add_argument("--report-root", default=str(ROOT / "reports"))
    args = ap.parse_args(argv)

    rom = Path(args.rom).resolve()
    rtl = Path(args.rtl).resolve()
    if not rom.is_file():
        raise SystemExit(f"ROM not found: {rom} (run scripts/gen_radial_lut_rom.py first)")
    if not rtl.is_file():
        raise SystemExit(f"RTL not found: {rtl}")

    stamp = time.strftime("%Y%m%d_%H%M%S")
    out = Path(args.report_root) / f"radial_lut_{stamp}"
    out.mkdir(parents=True, exist_ok=True)

    r2, factor, in_range = build_vectors(rom)
    with (out / "vectors.hex").open("w", encoding="ascii", newline="\n") as fh:
        for a, b, c in zip(r2.tolist(), factor.tolist(), in_range.tolist()):
            fh.write(f"{a & 0xFFFFFFFF:08x} {b & 0xFFFFFFFF:08x} {c:01x}\n")

    (out / "tb_radial_lut.v").write_text(tb_source(rom.as_posix()), encoding="utf-8")

    compile_cmd = [str(IVERILOG), "-g2012", "-o", str(out / "radial_lut.vvp"),
                   str(out / "tb_radial_lut.v"), str(rtl)]
    comp = subprocess.run(compile_cmd, cwd=out, capture_output=True, text=True)
    (out / "compile.log").write_text(comp.stdout + comp.stderr, encoding="utf-8")
    if comp.returncode != 0:
        print(comp.stdout + comp.stderr)
        raise SystemExit("iverilog failed")

    run = subprocess.run([str(VVP), str(out / "radial_lut.vvp")], cwd=out,
                         capture_output=True, text=True)
    log = run.stdout + run.stderr
    (out / "run.log").write_text(log, encoding="utf-8")
    print(log.strip())

    passed = "PASS" in log and "FAIL" not in log
    result = dict(
        report_dir=str(out),
        rtl=str(rtl),
        rom=str(rom),
        vectors=int(r2.size),
        passed=bool(passed),
        log_tail=log.strip().splitlines()[-3:],
        checks=dict(
            bit_exact_factor="errors_factor=0" in log,
            in_range_flags="errors_range=0" in log,
            one_valid_pulse_per_vector="valid_pulses=" in log,
        ),
        note="Simulation equality only. Does not prove PDS synthesis or on-board behaviour.",
    )
    (out / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())