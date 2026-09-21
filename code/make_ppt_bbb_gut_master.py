#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""make_ppt_bbb_gut_master.py - 新增问题专项PPT，ppt-master精美版
4大问题：计算方法细节、AMP-AD结合、肠道菌群调控、BBB穿透
"""

from __future__ import annotations
import argparse, json, re, shutil, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUTLINE = ROOT / "docs" / "ppt_outline_bbb_gut.json"
FIGDIR = ROOT / "results" / "figures"
BUILD = ROOT / "build"
OUT_DIR = ROOT / "deliverable"
PM = BUILD / "ppt-master" / "skills" / "ppt-master"
PM_EXPORT = PM / "scripts" / "svg_to_pptx.py"

W, H = 1280, 720
MARGIN = 72
MIN_PX = 20

CN = "Microsoft YaHei, Arial, sans-serif"
MONO = "Consolas, Microsoft YaHei, monospace"
SERIF = "Georgia, SimSun, serif"

STYLES = {
    "F": {
        "name": "深色科技风",
        "bg": "#070B16",
        "grid": "#16324D",
        "panel": "#0B1220",
        "panel_line": "#1E3A5F",
        "title": "#F1F5F9",
        "body": "#CBD5E1",
        "muted": "#7C8CA1",
        "accent": "#22D3EE",
        "accent2": "#F5A524",
        "chip_fill": "#0E1A2B",
        "chip_line": "#1E3A5F",
        "rule": "#1B3350",
        "kicker_family": MONO,
        "title_family": CN,
        "body_family": CN,
        "title_px": 36,
        "cover_title_px": 46,
        "band": True,
    },
    "G": {
        "name": "学术期刊风",
        "bg": "#FFFFFF",
        "grid": "#F1F3F5",
        "panel": "#FAFAF8",
        "panel_line": "#E3E1DC",
        "title": "#141414",
        "body": "#2B2B2B",
        "muted": "#767472",
        "accent": "#B03A2E",
        "accent2": "#2F5D62",
        "chip_fill": "#FBF6F5",
        "chip_line": "#EADCD9",
        "rule": "#DEDCD7",
        "kicker_family": SERIF,
        "title_family": SERIF,
        "body_family": CN,
        "title_px": 36,
        "cover_title_px": 44,
        "band": False,
    },
    "M": {
        "name": "深蓝金·机制专属",
        "bg": "#0A1931",
        "grid": "#1A2F5A",
        "panel": "#102542",
        "panel_line": "#2A4A7A",
        "title": "#F8FAFC",
        "body": "#D1DCE8",
        "muted": "#8A9BB5",
        "accent": "#FBBF24",
        "accent2": "#38BDF8",
        "chip_fill": "#122A4A",
        "chip_line": "#2A4A7A",
        "rule": "#1E3A5F",
        "kicker_family": MONO,
        "title_family": CN,
        "body_family": CN,
        "title_px": 36,
        "cover_title_px": 48,
        "band": True,
    },
}

_font_cache = {}
def _font(px):
    from PIL import ImageFont
    if px not in _font_cache:
        cands = sorted(Path("/tmp/fonts").glob("*CJK*.otf"))
        _font_cache[px] = ImageFont.truetype(str(cands[0]), px) if cands else ImageFont.load_default()
    return _font_cache[px]

def text_w(s, px):
    from PIL import Image, ImageDraw
    d = ImageDraw.Draw(Image.new("RGB", (1,1)))
    return d.textlength(s, font=_font(px))

def wrap(s, width_px, px):
    out, cur = [], ""
    for ch in s:
        if text_w(cur+ch, px) > width_px and cur:
            out.append(cur)
            cur = ch
        else:
            cur += ch
    if cur:
        out.append(cur)
    return out or [""]

def esc(s): return s.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")

def t(x,y,s,*,px,fill,family=CN,weight="normal",anchor="start",ls=None):
    a = f' text-anchor="{anchor}"' if anchor!="start" else ""
    w = f' font-weight="{weight}"' if weight!="normal" else ""
    l = f' letter-spacing="{ls}"' if ls else ""
    return f'<text x="{x:.0f}" y="{y:.0f}" font-family="{family}" font-size="{px}"{w}{a}{l} fill="{fill}">{esc(s)}</text>'

def block(x,y,s,*,px,fill,width,lh=1.45,family=CN,weight="normal",max_lines=None):
    lines = wrap(s, width, px)
    if max_lines and len(lines)>max_lines:
        lines = lines[:max_lines]
    out = [t(x, y+i*px*lh, ln, px=px, fill=fill, family=family, weight=weight) for i,ln in enumerate(lines)]
    return "\n  ".join(out), y+len(lines)*px*lh

def rect(x,y,w,h,fill,*,stroke=None,sw=1,rx=None,op=None):
    s = f'<rect x="{x:.0f}" y="{y:.0f}" width="{w:.0f}" height="{h:.0f}"'
    if rx: s+=f' rx="{rx}"'
    s+=f' fill="{fill}"'
    if stroke: s+=f' stroke="{stroke}" stroke-width="{sw}"'
    if op is not None: s+=f' fill-opacity="{op}"'
    return s+'/>'

def line(x1,y1,x2,y2,color,sw=1):
    return f'<line x1="{x1:.0f}" y1="{y1:.0f}" x2="{x2:.0f}" y2="{y2:.0f}" stroke="{color}" stroke-width="{sw}"/>'

def frame(st, kicker, idx, total, grid=True):
    out = [rect(0,0,W,H,st["bg"])]
    if grid and st.get("grid"):
        g=[]
        for x in range(0,W+1,320): g.append(f"M{x} 0V{H}")
        for y in range(0,H+1,180): g.append(f"M0 {y}H{W}")
        out.append(f'<g stroke="{st["grid"]}" stroke-width="1" opacity="0.55" fill="none"><path d="{"".join(g)}" fill="none"/></g>')
    if kicker:
        out.append(t(MARGIN,74,kicker,px=20,fill=st["accent"],family=st["kicker_family"],weight="bold",ls=1.5))
    out.append(t(W-MARGIN,74,f"{idx:02d} / {total}",px=20,fill=st["muted"],anchor="end",family=MONO))
    return out

def heading(st, title, subtitle=None, top=110):
    out=[]
    y=top
    px=st["title_px"]
    lines=wrap(title, W-2*MARGIN-70, px)
    if len(lines)>2:
        px=int(px*0.86)
        lines=wrap(title, W-2*MARGIN-70, px)
    for i,ln in enumerate(lines):
        out.append(t(MARGIN, y+i*px*1.22, ln, px=px, fill=st["title"], family=st["title_family"], weight="bold"))
    y+=(len(lines)-1)*px*1.22
    if subtitle:
        out.append(t(MARGIN, y+32, subtitle, px=20, fill=st["accent2"], family=st["kicker_family"]))
        y+=32
    y+=18
    out.append(line(MARGIN,y,W-MARGIN,y,st["rule"],1.5))
    return out, y+30

def takeaway(st, text):
    top,height=630,60
    out=[]
    if st["band"]:
        out.append(rect(0,top,W,height,st["panel"]))
        out.append(rect(0,top,8,height,st["accent"]))
        x=MARGIN
    else:
        out.append(line(MARGIN,top,W-MARGIN,top,st["rule"],1.5))
        out.append(rect(MARGIN,top+22,14,14,st["accent"]))
        x=MARGIN+30
    px=20
    lines=wrap(text, W-x-MARGIN, px)
    y=top+35 if len(lines)==1 else top+26
    for i,ln in enumerate(lines[:2]):
        out.append(t(x,y+i*px*1.35,ln,px=px,fill=st["title"] if st["band"] else st["body"],family=st["body_family"],weight="bold"))
    return out

def figure_page(st,s,idx,total,content_top):
    out=[]
    body=s.get("body")
    img=FIGDIR / s.get("figure")
    top=content_top-4
    has_takeaway = bool(s.get("takeaway"))
    max_bottom = 600
    avail_h = max_bottom - top
    panel_h = avail_h if not body else int(avail_h*0.55)
    out.append(rect(MARGIN-8,top,W-2*MARGIN+16,panel_h,st["panel"],stroke=st["panel_line"],sw=1,rx=10))
    from PIL import Image
    try:
        iw,ih=Image.open(img).size
        pad=14
        maxw,maxh=W-2*MARGIN-pad*2,panel_h-pad*2
        scale=min(maxw/iw, maxh/ih, 1.0)
        dw,dh=iw*scale, ih*scale
        dw = min(dw, W-2*MARGIN-20)
        dh = min(dh, panel_h-20)
        x=(W-dw)/2
        y=top+(panel_h-dh)/2
        rel=f"../images/{img.name}"
        out.append(f'<image href="{rel}" x="{x:.0f}" y="{y:.0f}" width="{dw:.0f}" height="{dh:.0f}"/>')
    except Exception as e:
        out.append(t(MARGIN,top+40,f"[图缺失 {img.name}]",px=20,fill=st["muted"]))
    if body:
        body_top = top+panel_h+14
        max_lines = 3 if has_takeaway else 4
        if 600 - body_top < 70:
            max_lines = 2
        xml,_=block(MARGIN, body_top, body, px=20, fill=st["body"], width=1000, lh=1.32, family=st["body_family"], max_lines=max_lines)
        out.append(xml)
    return out

def bullets_page(st,s,idx,total,content_top):
    out=[]
    bullets=s.get("bullets",[])
    callout=s.get("callout")
    bottom=580 if not callout else 450
    y=content_top+6
    for b in bullets:
        if y>bottom-40:
            break
        tag,_,rest=b.partition("　")
        if rest:
            out.append(rect(MARGIN, y-12, 8, 8, st["accent"]))
            out.append(t(MARGIN+22, y, tag, px=20, fill=st["accent2"], family=st["body_family"], weight="bold"))
            xml,ny=block(MARGIN+22+text_w(tag,20)+12, y, rest, px=20, fill=st["body"], width=1000-text_w(tag,20)-34, lh=1.32, family=st["body_family"], max_lines=2)
        else:
            out.append(rect(MARGIN, y-12, 8, 8, st["accent"]))
            xml,ny=block(MARGIN+22, y, b, px=20, fill=st["body"], width=1000, lh=1.32, family=st["body_family"], max_lines=3)
        out.append(xml)
        y=ny+14
        if y>bottom:
            break
    if callout:
        top=480
        out.append(rect(MARGIN,top,W-2*MARGIN,110,st["chip_fill"],stroke=st["chip_line"],sw=1,rx=10))
        out.append(rect(MARGIN,top,6,110,st["accent"]))
        out.append(t(MARGIN+22, top+36, callout["label"], px=20, fill=st["accent2"], family=st["body_family"], weight="bold"))
        xml,_=block(MARGIN+22, top+64, callout["text"], px=20, fill=st["body"], width=1000, lh=1.30, family=st["body_family"], max_lines=2)
        out.append(xml)
    return out

def cards_page(st,s,idx,total,content_top):
    out=[]
    bullets=s.get("bullets",[])
    cards=s.get("cards",[])
    y=content_top+8
    for b in bullets:
        if y>500:
            break
        xml,ny=block(MARGIN,y,"· "+b,px=20,fill=st["body"],width=600,lh=1.30,family=st["body_family"],max_lines=2)
        out.append(xml)
        y=ny+10
    cy=content_top+4
    ch=78
    for label,desc,tone in cards:
        if cy+ch>600:
            break
        col=st["accent"] if tone=="A" else st["accent2"]
        out.append(rect(760,cy,448,ch,st["chip_fill"],stroke=st["chip_line"],sw=1,rx=8))
        out.append(rect(760,cy,6,ch,col))
        out.append(t(784,cy+28,label,px=20,fill=col,family=st["body_family"],weight="bold"))
        xml,_=block(784,cy+50,desc,px=20,fill=st["body"],width=400,lh=1.20,family=st["body_family"],max_lines=2)
        out.append(xml)
        cy+=ch+8
    return out

def steps_page(st,s,idx,total,content_top):
    out=[]
    y=content_top+10
    steps=s.get("steps",[])
    for k,(tag,text) in enumerate(steps):
        if y+68>600:
            break
        out.append(rect(MARGIN,y,6,66,st["accent"] if k%2==0 else st["accent2"]))
        out.append(t(MARGIN+22,y+26,tag,px=20,fill=st["title"],family=st["body_family"],weight="bold"))
        xml,_=block(MARGIN+22,y+48,text,px=20,fill=st["body"],width=1000,lh=1.30,family=st["body_family"],max_lines=2)
        out.append(xml)
        y+=66+14
    return out

def toc_page(st,s,idx,total,content_top):
    out=[]
    items=s.get("items",[])
    col_w=(W-2*MARGIN-60)/2
    for k,item in enumerate(items):
        col,row=divmod(k,7)
        x=MARGIN+col*(col_w+60)
        y=content_top+16+row*78
        if y>600:
            continue
        out.append(t(x,y,f"{k+1:02d}",px=24,fill=st["accent"],family=st["kicker_family"],weight="bold"))
        xml,_=block(x+48,y,item,px=20,fill=st["body"],width=col_w-48,lh=1.22,family=st["body_family"],max_lines=2)
        out.append(xml)
        out.append(line(x,y+38,x+col_w,y+38,st["rule"],1))
    return out

def cover(st,s,idx,total,meta):
    out=[rect(0,0,W,H,st["bg"])]
    if st["band"]:
        out.append(rect(0,0,W,8,st["accent"]))
        out.append(rect(W-300,110,220,10,st["accent"]))
        out.append(rect(W-300,135,150,10,st["accent2"]))
    else:
        out.append(line(MARGIN,90,W-MARGIN,90,st["title"],3))
        out.append(line(MARGIN,98,W-MARGIN,98,st["rule"],1))
    out.append(t(MARGIN,140,s.get("eyebrow",""),px=20,fill=st["accent"],family=st["kicker_family"],weight="bold",ls=1.5))
    px=st["cover_title_px"]
    titles=[s["title"], s.get("title2","")]
    lines=[]
    for tt in titles:
        if tt: lines+=wrap(tt, W-2*MARGIN-100, px)
    for i,ln in enumerate([x for x in lines if x][:3]):
        out.append(t(MARGIN, 210+i*px*1.25, ln, px=px, fill=st["title"], family=st["title_family"], weight="bold"))
    y=210+len(lines)*px*1.25+24
    out.append(line(MARGIN,y,MARGIN+220,y,st["accent"],3))
    metas=[meta.get("presenter",""), meta.get("advisor",""), meta.get("major",""), meta.get("date",""), meta.get("footer","")]
    for i,m in enumerate([x for x in metas if x]):
        out.append(t(MARGIN, y+48+i*34, m, px=20, fill=st["body"], family=st["body_family"]))
    out.append(t(W-MARGIN, H-50, f"{idx:02d} / {total}", px=20, fill=st["muted"], anchor="end", family=MONO))
    return out

def end_page(st,s,idx,total):
    out=[rect(0,0,W,H,st["bg"])]
    if st["band"]: out.append(rect(0,0,W,8,st["accent"]))
    else: out.append(line(MARGIN,90,W-MARGIN,90,st["title"],3))
    out.append(t(MARGIN,280,s.get("title",""),px=44,fill=st["title"],family=st["title_family"],weight="bold"))
    if s.get("title2"):
        out.append(t(MARGIN,350,s["title2"],px=30,fill=st["accent"],family=st["title_family"],weight="bold"))
    out.append(line(MARGIN,410,MARGIN+220,410,st["accent"],3))
    return out

def render(style_key, outline):
    st=STYLES[style_key]
    slides=outline["slides"]
    meta=outline["meta"]
    total=len(slides)
    proj=BUILD / f"svgproj_bbb_{style_key}"
    if proj.exists(): shutil.rmtree(proj)
    (proj/"svg_output").mkdir(parents=True)
    (proj/"notes").mkdir()
    (proj/"images").mkdir()
    for png in FIGDIR.glob("*.png"):
        shutil.copy(png, proj/"images"/png.name)

    for s in slides:
        n,kind=s["n"], s["type"]
        idx=n
        if kind=="title":
            body=cover(st, s, idx, total, meta)
        elif kind=="end":
            body=end_page(st,s,idx,total)
        else:
            dark=st["band"]
            kicker=f"// {idx:02d} / {s.get('subtitle','')}" if dark else ""
            head=frame(st,kicker,idx,total)
            h,y=heading(st, s["title"], None if dark else s.get("subtitle"))
            head+=h
            fn={"toc":toc_page,"figure":figure_page,"bullets":bullets_page,"cards":cards_page,"steps":steps_page}[kind]
            head+=fn(st,s,idx,total,y)
            if s.get("takeaway"):
                head+=takeaway(st, s["takeaway"])
            body=head
        svg=f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" font-family="{CN}">\n  '+"\n  ".join(body)+"\n</svg>\n"
        (proj/"svg_output"/f"{n:02d}_{kind}.svg").write_text(svg, encoding="utf-8")
        if s.get("note"):
            (proj/"notes"/f"{n:02d}_{kind}.md").write_text(s["note"]+"\n", encoding="utf-8")

    (proj/"spec_lock.md").write_text(f"""<!-- ppt-master-schema: spec-lock/v1 -->
# Execution Lock
## canvas
- viewBox: 0 0 {W} {H}
- format: PPT 16:9
## communication
- primary_language: zh-Hans-CN
- audience: 生命科学学院答辩评委，关注计算方法细节与新增机制问题
- objective: 回答计算方法如何做、AMP-AD结合、肠道菌群调控、BBB穿透，补充具体文献实现细节
- core_message: 计算预测可行性已被大规模验证，AMP经结合+肠-血-脑轴形成正反馈，BBB穿透以阳离子AMT为主
## mode
- mode: custom
- mode_behavior: 新增问题专项，按计算-结合-肠道-BBB展开
## visual_style
- visual_style: custom
- visual_style_behavior: {st['name']}精美版
## colors
- primary: {st['accent']}
- accent: {st['accent2']}
- background: {st['bg']}
- surface: {st['panel']}
- secondary_text: {st['muted']}
- divider: {st['rule']}
## typography
- font_family: {CN}
- title_family: {st['title_family']}
- body_family: {st['body_family']}
- body: 20
- title: {st['title_px']}
## icons
- library: none
- inventory: none
## page_rhythm
"""+ "\n".join(f"- P{n:02d}: {'breathing' if n in (1,2,total) else 'dense'}" for n in range(1,total+1))+"""
## pptx_structure
- mode: flat
## forbidden
- mask, style, class, external CSS, foreignObject, textPath, @font-face, animate, script, iframe
- HTML named entities; escape XML reserved
- <15pt
""", encoding="utf-8")

    bad=[]
    for f in sorted((proj/"svg_output").glob("*.svg")):
        for m in re.finditer(r'font-size="([\d.]+)"', f.read_text(encoding="utf-8")):
            if float(m.group(1))<MIN_PX:
                bad.append((f.name,m.group(1)))
    if bad:
        raise SystemExit(f"SVG字号<{MIN_PX}px: {bad}")

    out=OUT_DIR / f"抗菌肽新增问题_计算结合肠道BBB_{style_key}_{st['name']}.pptx"
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    cmd=[sys.executable, str(PM_EXPORT), str(proj), "-q", "--enable-dangerous-nonconforming-svg-export", "-o", str(out)]
    print("  ", " ".join(str(c) for c in cmd[:4]), "...")
    r=subprocess.run(cmd, capture_output=True, text=True)
    tail=(r.stdout or "").strip().splitlines()
    print("\n".join(tail[-4:]) if tail else r.stderr[-800:])
    if r.returncode!=0 or not out.exists():
        raise SystemExit(f"导出失败：\n{r.stdout[-2000:]}\n{r.stderr[-2000:]}")
    print(f"  -> {out.relative_to(ROOT)}")
    return out

def main(argv=None):
    ap=argparse.ArgumentParser()
    ap.add_argument("--style", choices=list(STYLES)+["all"], default="all")
    ap.add_argument("--outline", default=str(OUTLINE))
    a=ap.parse_args(argv)
    if not PM_EXPORT.exists():
        raise SystemExit(f"没找到 ppt-master：{PM_EXPORT}\n先运行：python code/fetch_ppt_master.py")
    outline=json.loads(Path(a.outline).read_text(encoding="utf-8"))
    keys=list(STYLES) if a.style=="all" else [a.style]
    for k in keys:
        print(f"\n=== 新增问题 风格 {k}（{STYLES[k]['name']}）")
        render(k, outline)
    return 0

if __name__=="__main__":
    raise SystemExit(main())
