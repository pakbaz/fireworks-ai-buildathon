import json, re, sys, numpy as np, soundfile as sf
d=sys.argv[1]
y,sr=sf.read(f"{d}/maya2.wav"); w=json.load(open(f"{d}/maya2.json"))
k=[re.sub(r'[^a-z0-9]','',x['w'].lower()) for x in w]
heads=[["the","hard"],["a","frontier"],["why"],["on","ordinary"],["one","invoice"]]
st=[];i=0
for h in heads:
    while k[i:i+len(h)]!=h: i+=1
    st.append(i); i+=1
win=int(sr*.01); n=len(y)//win
db=20*np.log10(np.sqrt(np.array([np.mean(y[q*win:(q+1)*win]**2) for q in range(n)])+1e-12))
def boundary(j):
    t0,t1=w[j-1]['e'],w[j]['s']
    a=max(0,int((t0-.3)/.01)); b=min(n,int((t1+.4)/.01))
    # centre of the longest silent stretch around the boundary
    best=(0,None);q=a
    while q<b:
        if db[q]<-38:
            r=q
            while r<b and db[r]<-38: r+=1
            if r-q>best[0]: best=(r-q,(q+r)/2*.01)
            q=r
        else: q+=1
    return best[1] if best[1] else (t0+t1)/2
cuts=[0.0]+[boundary(j) for j in st[1:]]+[len(y)/sr]
for i in range(5):
    a,b=cuts[i],cuts[i+1]
    last=(st[i+1] if i<4 else len(w))
    if i==3:  # the chart already shows Kimi's 1; the spoken line ends on ours
        j=next(q for q in range(st[3],last) if k[q:q+2]==["the","frontier"])
        b=boundary(j); last=j
    sf.write(f"{d}/r{i+1}.wav",y[int(a*sr):int(b*sr)],sr,subtype='PCM_24')
    ws=[dict(s=x['s']-a,e=x['e']-a,w=x['w']) for x in w[st[i]:last]]
    json.dump(ws,open(f"{d}/r{i+1}.json","w"))
    print(i+1,round(b-a,2),' '.join(x['w'] for x in ws)[:80])
