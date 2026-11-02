"""Re-run the repo's image renderer with logging to find where contended values landed on each scanned page."""
import json, math, random, re, sys, os
OUT=os.path.dirname(os.path.abspath(__file__))
REPO=os.path.dirname(OUT)
sys.path.insert(0, REPO+'/generator')
from PIL import Image, ImageDraw, ImageChops
import render_images as R

preds={}
for l in open(REPO+'/runs/kimi_alone/test.jsonl'):
    r=json.loads(l); preds[r['case_id']]=r
cases=[json.loads(l) for l in open(REPO+'/data/test.jsonl')]
cases=[c for c in cases if c.get('images')]

LOG={}
_text=ImageDraw.ImageDraw.text
def text(self,xy,t,*a,**k):
    if LOG.get('on') and self.im.size==(R.W,R.H):
        LOG['runs'].append((xy[0],xy[1],t,k.get('font')))
    return _text(self,xy,t,*a,**k)
ImageDraw.ImageDraw.text=text
_hand=R.draw_hand
def hand(page,x,y,t,fs,rng):
    x2=_hand(page,x,y,t,fs,rng)
    LOG['hand'].append((x,y,t,x2,fs)); return x2
R.draw_hand=hand
_rot=Image.Image.rotate
def rot(self,ang,*a,**k):
    if k.get('expand') is False: LOG['ang']=ang
    return _rot(self,ang,*a,**k)
Image.Image.rotate=rot
_page=R.render_text_page
def page(t,tpl,rng):
    LOG.update(on=True,runs=[],hand=[],text=t)
    p=_page(t,tpl,rng)
    LOG['on']=False
    LOG['WH']=(R.W,R.H)
    return p
R.render_text_page=page

def render(case):
    rng=random.Random('img-'+case['case_id'])
    pages={}
    for doc in ('po','shipping_notice','gr','invoice'):
        t=case['documents'][doc]
        if t is None: continue
        p=R.render_text_page(t,case['template_ids'][doc],rng)
        info=dict(runs=LOG['runs'],hand=LOG['hand'],text=t,WH=LOG['WH'])
        info['clean']=p.copy()
        if rng.random()<0.5: R.stamp(p,rng,doc)
        p=R.degrade(p,rng)
        info['ang']=LOG['ang']; info['img']=p
        pages[doc]=info
    return pages

import numpy as np
def ink(im,scale=2):
    a=np.asarray(im.resize((im.width//scale,im.height//scale),Image.BILINEAR),dtype=np.float32)
    a=255-a
    return a-a.mean()
def corr(a,bf):
    c=np.fft.irfft2(np.fft.rfft2(a)*bf,s=a.shape)
    i=np.unravel_index(np.argmax(c),c.shape)
    dy=i[0] if i[0]<a.shape[0]/2 else i[0]-a.shape[0]
    dx=i[1] if i[1]<a.shape[1]/2 else i[1]-a.shape[1]
    return c[i],dx,dy
def register(clean,ref):
    '''Find the rotation and shift that map the clean rendered page onto the committed scan.'''
    bf=np.conj(np.fft.rfft2(ink(clean)))  # placeholder shape holder
    rf=ink(ref)
    best=None
    for grid in (np.arange(-3.4,3.41,0.2),None):
        angs=grid if grid is not None else np.arange(best[1]-0.2,best[1]+0.21,0.04)
        for ang in angs:
            r=clean.rotate(float(ang),resample=Image.BILINEAR,expand=False,fillcolor=255)
            c,dx,dy=corr(rf,np.conj(np.fft.rfft2(ink(r))))
            if best is None or c>best[0]: best=(float(c),float(ang),dx*2,dy*2)
    return best

def glyphs(info):
    """per y: list of (x, char, charwidth)"""
    rows={}
    for x,y,t,f in info['runs']:
        for i,ch in enumerate(t):
            if ch==' ':continue
            cx=x+f.getlength(t[:i]); w=f.getlength(ch)
            rows.setdefault(round(y,3),[]).append((cx,ch,w,f.size))
    for r in rows.values(): r.sort()
    return rows

def transform(info,box):
    W,H=info['WH']; a=math.radians(info['fit_ang']); cx,cy=W/2,H/2
    pts=[]
    for x,y in ((box[0],box[1]),(box[2],box[1]),(box[0],box[3]),(box[2],box[3])):
        dx,dy=x-cx,y-cy
        pts.append((cx+dx*math.cos(a)+dy*math.sin(a), cy-dx*math.sin(a)+dy*math.cos(a)))
    ox,oy=info.get('shift',(0,0))
    return [min(p[0] for p in pts)+ox,min(p[1] for p in pts)+oy,max(p[0] for p in pts)+ox,max(p[1] for p in pts)+oy]

def line_ys(info):
    lines=info['text'].rstrip('\n').split('\n')
    rows=sorted(glyphs(info).keys())
    return lines,rows

def find_box(info,token,sku_token=None,hand_ok=True):
    lines,rows=line_ys(info)
    g=glyphs(info)
    start=0
    if sku_token:
        for i,l in enumerate(lines):
            if sku_token in l: start=i;break
    target=re.sub(r'\s','',token)
    # y of each text line: map by order of non-blank lines
    fs=g[rows[0]][0][3]; lh=fs*1.3
    y0=rows[0]-next(i for i,l in enumerate(lines) if l.strip())*lh
    for i in range(start,min(len(lines),start+7 if sku_token else len(lines))):
        l=lines[i]
        ly=y0+i*lh
        key=min(rows,key=lambda y:abs(y-ly))
        if abs(key-ly)>lh/2: continue
        gl=g[key]; s=''.join(c[1] for c in gl)
        j=s.find(target)
        if j>=0:
            box=[gl[j][0]-1,key-1,gl[j+len(target)-1][0]+gl[j+len(target)-1][2]+1,key+fs*1.15]
            return i,box,fs
    return None

def union(a,b): return [min(a[0],b[0]),min(a[1],b[1]),max(a[2],b[2]),max(a[3],b[3])]

def hand_on_line(info,i,fs):
    lines,rows=line_ys(info)
    g=glyphs(info)
    lh=fs*1.3
    y0=rows[0]-next(k for k,l in enumerate(lines) if l.strip())*lh
    ly=y0+i*lh
    for x,y,t,x2,hf in info['hand']:
        if abs(y-ly)<lh/2: return (t,[x,y-fs*.4,x2,y+fs*1.5])
    return None

def tok(meta,doc,field,sku=None):
    for t in meta['tokens']:
        if t['doc']==doc and t['field']==field and (sku is None or t['sku']==sku): return t['text']
    return None

SK=dict(po='Purchase order',shipping_notice='Shipping notice',gr='Goods receipt',invoice='Invoice')
result=[];fails=[]
def fmtq(q): return f"{q:,}" if isinstance(q,int) else f"{q:,g}"
def usd(v): return f"${v:,.2f}"

for c in cases:
    lab=c['label']
    if not lab['real_discrepancy']: continue
    if c['case_id'] not in preds: continue
    pages=render(c)
    # confirm the replay reproduces the committed scan
    diffs={}
    for d,info in pages.items():
        ref=Image.open(os.path.join(REPO,c['images'][d])).convert('L')
        info['WH']=ref.size
        _,fa,ox,oy=register(info['clean'],ref)
        info['fit_ang']=fa;info['shift']=(ox,oy)
        hist=ImageChops.difference(ref,info['img']).histogram()
        diffs[d]=round(sum(i*v for i,v in enumerate(hist))/sum(hist),3)
    meta=lab['render_meta']; gold=lab['gold']; mut=lab['mutation']; rc=lab['reason_code']
    marks=[]
    def add(doc,field,says,bad,sku=None,token=None):
        t=token or tok(meta,doc,field,sku)
        info=pages[doc]; sk=tok(meta,doc,'sku',sku) if sku else None
        struck=re.search(r"\[struck-out: ([^\]]*)\]",t or '')
        if t and '[handwritten' in t:
            sk_line=next((n for n,l in enumerate(info['text'].split('\n')) if sk and sk in l),None)
            full=next((n for n,l in enumerate(info['text'].split('\n')) if t in l and (sk_line is None or n>=sk_line)),None)
            gl=glyphs(info);rows=sorted(gl);fs=gl[rows[0]][0][3]
            lines=info['text'].rstrip('\n').split('\n');lh=fs*1.3
            y0=rows[0]-next(n for n,l in enumerate(lines) if l.strip())*lh
            ly=y0+full*lh
            hb=[(x,y-fs*.4,x2,y+fs*1.5) for x,y,_,x2,_ in info['hand'] if abs(y-ly)<lh/2]
            box=list(hb[0]) if hb else None
            if struck:
                key=min(rows,key=lambda y:abs(y-ly));row=gl[key];txt=''.join(r[1] for r in row);tg=re.sub(r'\s','',struck.group(1))
                j=txt.rfind(tg)
                if j>=0:
                    sb=[row[j][0]-3,key-1,row[j+len(tg)-1][0]+row[j+len(tg)-1][2]+3,key+fs*1.15]
                    box=union(box,sb) if box else sb
            marks.append(dict(doc=doc,label=SK[doc],says=says,bad=bad,box=[round(v,1) for v in transform(info,box)],hand=True))
            return
        loc=find_box(info,t,sk) if t else None
        if loc is None and t and sku: loc=find_box(info,t,None)
        if loc is None: fails.append((c['case_id'],doc,field,t)); return
        i,box,fs=loc
        h=hand_on_line(info,i,fs) if doc=='gr' and field=='qty_received' else None
        if h: box=union(box,h[1]) if h else box
        marks.append(dict(doc=doc,label=SK[doc],says=says,bad=bad,box=[round(v,1) for v in transform(info,box)],hand=bool(h)))
    sku=mut.get('sku')
    if rc in('lost_in_transit','short_shipped','qty_mismatch'):
        inv,rec,shp=mut['invoiced'],mut['received'],mut.get('shipped')
        po=next(l['qty'] for l in gold['po']['lines'] if l['sku']==sku)
        add('gr','qty_received',f"Received {fmtq(rec)}",True,sku)
        add('invoice','qty',f"Billed {fmtq(inv)}",True,sku)
        if 'shipping_notice' in pages: add('shipping_notice','qty_shipped',f"Shipped {fmtq(shp)}",False,sku)
        add('po','qty',f"Ordered {fmtq(po)}",False,sku)
    elif rc=='price_mismatch':
        add('invoice','unit_price',f"Billed {usd(mut['invoice_price'])}",True,sku)
        add('po','unit_price',f"PO price {usd(mut['po_price'])}",False,sku)
    elif rc=='wrong_po':
        add('invoice','po_ref',f"Cites {mut['invoice_po']}",True)
        add('po','po_number',f"Ordered on {mut['received_po']}",False)
        add('gr','po_ref',f"Received on {mut['received_po']}",False)
    elif rc=='duplicate_invoice':
        add('invoice','invoice_number',f"Invoice {mut['invoice_number']}",True)
    p=preds[c['case_id']]
    result.append(dict(id=c['case_id'],company=c['company'],supplier=gold['po']['supplier_name'],reason=rc,next=lab['next_step'],
        inv=gold['invoice']['invoice_number'],po=gold['po']['po_number'],carrier=(gold.get('shipping_notice') or {}).get('carrier'),
        sku=sku,lines=[{'sku':l['sku'],'desc':l['description'],'qty':l['qty'],'price':l['unit_price']} for l in gold['po']['lines']],
        mut=mut,history=[h for h in c['billing_history'] if rc=='duplicate_invoice' and h['invoice_number']==mut.get('invoice_number')],
        action=p['action'],risk=p['risk'],atRisk=p['at_risk_usd'],goldAtRisk=lab['at_risk_usd'],loss=p['dial']['expected_loss_if_paid_usd'],miss=p['dial']['cost_of_miss_usd'],
        modelReason=p['reason_code'],evidence=p['evidence'],noise=lab['noise_types'],
        docs={d:{'w':pages[d]['WH'][0],'h':pages[d]['WH'][1]} for d in pages},marks=marks,diff=diffs))
json.dump(result,open(OUT+'/located.json','w'),indent=0)
print(len(result),'cases; failures:',fails)
print('max pixel diff per case',{r['id']:max(r['diff'].values()) for r in result})
if len(sys.argv)<2: sys.exit()
# optional check sheet of every mark drawn over the committed scans: locate_disputes.py <sheet.png>
from PIL import ImageFont
sheet=[]
for r in result:
    for m in r['marks']:
        im=Image.open(f"{REPO}/data/images/{r['id']}/{m['doc']}.png").convert('RGB')
        b=m['box'];W,H=im.size;cw=max(320,b[2]-b[0]+120);ch=cw*.3
        cx,cy=(b[0]+b[2])/2,(b[1]+b[3])/2
        x0=max(0,min(W-cw,cx-cw/2));y0=max(0,min(H-ch,cy-ch/2))
        ImageDraw.Draw(im).rectangle(b,outline=(255,90,0),width=2)
        crop=im.crop((int(x0),int(y0),int(x0+cw),int(y0+ch))).resize((400,120))
        lab=Image.new('RGB',(400,16),'white');ImageDraw.Draw(lab).text((2,2),f"{r['id']} {m['doc']} {m['says']}",fill='black')
        t=Image.new('RGB',(400,136),'white');t.paste(lab,(0,0));t.paste(crop,(0,16));sheet.append(t)
cols=4;rows=math.ceil(len(sheet)/cols)
S=Image.new('RGB',(cols*404,rows*140),'white')
for i,t in enumerate(sheet): S.paste(t,((i%cols)*404,(i//cols)*140))
S.save(sys.argv[1]);print(S.size)
