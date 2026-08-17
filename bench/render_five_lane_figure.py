#!/usr/bin/env python3
"""Render the five-lane evidence figure from the real benchmark JSON.

Pure stdlib (PIL). Reads runtime/five_lane_evidence.json (produced by
bench/five_lane_demo.py) and draws a clean dark card per lane.
"""
import json, os, sys
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
EVID = os.path.join(os.path.dirname(HERE), "runtime", "five_lane_evidence.json")
FONT_DIR = "/usr/share/fonts/truetype/dejavu"

def F(sz):
    for p in ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
              "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
        if os.path.exists(p): return ImageFont.truetype(p, sz)
    return ImageFont.load_default()

BG=(10,12,17); CARD=(16,19,27); BORD=(40,48,64); TXT=(210,220,235); DIM=(130,140,158)
GREEN=(0,230,118); RED=(255,69,58); CYAN=(80,190,255); PURPLE=(151,117,250)

def load():
    if not os.path.exists(EVID): raise SystemExit(f"missing {EVID}; run bench/five_lane_demo.py first")
    return json.load(open(EVID))

def rows(d):
    A,B,C,D,E,F=d["lane_a"],d["lane_b"],d["lane_c"],d["lane_d"],d["lane_e"],d["lane_f"]
    return [
      ("A · PROVENANCE-WEIGHTED", f"unverified {A['unverified_capped_weight']}  →  verified {A['verified_boosted_weight']}  (poisoning-resistant)",
       GREEN if A["poisoning_resistant"] else RED),
      ("B · FORGETTING AS FEATURE", f"supersede → stale-leak {str(B['recalled_stale']).lower()} · current recall {str(B['recalled_current']).lower()}",
       GREEN if B["no_stale_truth"] else RED),
      ("C · PAY-TO-REMEMBER (x402)", f"unpaid blocked {str(C['unpaid_blocked']).lower()} · payment gate enforced",
       GREEN if C["unpaid_blocked"] else RED),
      ("D · MEMORY → LoRA DATA", f"{D['examples']} fine-tune examples written (sleep-distilled)",
       CYAN),
      ("E · PROSPECTIVE MEMORY", f"{len(E['due_now'])} intent surfaced before due · snoozable {str(E['snoozable']).lower()}",
       PURPLE),
      ("F · WORKING-MEMORY BUDGET", f"kept {F['kept']} / evicted {F['evicted']} @ {F['budget']} tok · non-destructive",
       CYAN),
    ]

def main():
    d=load(); rows_list=rows(d)
    W,H=1280,840; pad=46; card_h=(H-2*pad-5*16)//len(rows_list)
    img=Image.new("RGB",(W,H),BG); dr=ImageDraw.Draw(img)
    ft=F(34); ft_lbl=F(26); ft_sub=F(24)
    dr.text((pad,26),"NEURAL_MESH — SIX-LANE AGENTIC MEMORY EVIDENCE",font=ft,fill=TXT)
    dr.text((pad,64),"measured on the real engine (reproduce: bench/five_lane_demo.py)",font=F(20),fill=DIM)
    y=pad+56
    for title,sub,color in rows_list:
        dr.rounded_rectangle([pad,y,W-pad,y+card_h],radius=12,outline=BORD,fill=CARD,width=1)
        dr.line([pad+22,y+card_h/2,pad+22,y+card_h-22],fill=color,width=5)
        dr.text((pad+46,y+18),title,font=ft_lbl,fill=color)
        dr.text((pad+46,y+card_h-56),sub,font=ft_sub,fill=TXT)
        y+=card_h+16
    out=os.path.join(os.path.dirname(HERE),"docs","assets","five_lane_evidence.png")
    os.makedirs(os.path.dirname(out),exist_ok=True)
    img.save(out)
    print("wrote",out)

if __name__=="__main__":
    main()
