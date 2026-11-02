#!/usr/bin/env python3
"""Analyze paired clock readings from the SAME phone photo; never infer latency from CALC."""
import argparse,csv,json,math,statistics
from pathlib import Path

def analyze(rows):
    delays=[]
    for i,row in enumerate(rows,2):
        try:reference=float(row['reference_s']);hdmi=float(row['hdmi_s'])
        except (KeyError,TypeError,ValueError) as e:raise ValueError(f'CSV row {i}: reference_s/hdmi_s must be seconds') from e
        if not math.isfinite(reference) or not math.isfinite(hdmi) or reference<hdmi or hdmi<0:
            raise ValueError(f'CSV row {i}: invalid or reversed readings; do not take absolute values')
        delays.append((reference-hdmi)*1000)
    if not delays:raise ValueError('No actual paired readings provided')
    ordered=sorted(delays)
    return {'samples':len(delays),'latency_ms':delays,'median_ms':statistics.median(delays),
            'mean_ms':statistics.mean(delays),'min_ms':ordered[0],'max_ms':ordered[-1],
            'p95_ms_nearest_rank':ordered[math.ceil(.95*len(ordered))-1],
            'method':'paired direct-screen and HDMI clock readings from same phone photo',
            'limitations':'Includes display/exposure/phone readout effects; clock digits do not imply millisecond accuracy'}

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('csv',type=Path);ap.add_argument('--out',type=Path);a=ap.parse_args()
    with a.csv.open(encoding='utf-8-sig',newline='') as f:result=analyze(csv.DictReader(f))
    text=json.dumps(result,ensure_ascii=False,indent=2)
    if a.out:a.out.write_text(text,encoding='utf-8')
    print(text)

if __name__=='__main__':main()
