"""Confidence intervals and paired tests behind docs/presentation.html, recomputed from saved predictions. No API calls.
Intervals are exact Clopper-Pearson 95%; paired tests are exact McNemar on the same invoices.
    python3 eval/presentation_stats.py
"""
import json,math,statistics as st
from math import comb
def cdf(k,n,p): return sum(comb(n,i)*p**i*(1-p)**(n-i) for i in range(k+1))
def cp(k,n,a=.05):
    def bis(f):
        lo,hi=0.,1.
        for _ in range(60):
            m=(lo+hi)/2
            if f(m): lo=m
            else: hi=m
        return (lo+hi)/2
    L=0. if k==0 else bis(lambda p:1-cdf(k-1,n,p)<a/2)
    U=1. if k==n else bis(lambda p:cdf(k,n,p)>a/2)
    return round(100*L,1),round(100*U,1)
def mcn(b,c):
    n=b+c
    return 1.0 if n==0 else min(1.0,2*cdf(min(b,c),n,.5))
K={s:{json.loads(l)['case_id']:json.loads(l) for l in open(f'data/{s}.jsonl')} for s in('test','test_context')}
def P(row,f): return {json.loads(l)['case_id']:json.loads(l) for l in open(f'runs/{row}/{f}.jsonl')}
def cmp(name,s,a,b,fa=None,fb=None):
    A,B=P(a,fa or s),P(b,fb or s)
    ids=sorted(set(A)&set(B)); k=K[s]
    real=[i for i in ids if k[i]['label']['real_discrepancy']]
    fine=[i for i in ids if not k[i]['label']['real_discrepancy'] and k[i]['label']['stratum']!='in_transit']
    e=lambda p:p['action']=='ESCALATE'
    ca=sum(e(A[i]) for i in real);cb=sum(e(B[i]) for i in real)
    fa_=sum(e(A[i]) for i in fine);fb_=sum(e(B[i]) for i in fine)
    d1=sum(e(A[i]) and not e(B[i]) for i in real);d2=sum(e(B[i]) and not e(A[i]) for i in real)
    f1=sum(e(A[i]) and not e(B[i]) for i in fine);f2=sum(e(B[i]) and not e(A[i]) for i in fine)
    print(name,'n',len(ids))
    print(' caught',a,ca,len(real),cp(ca,len(real)),'|',b,cb,len(real),cp(cb,len(real)),'discordant',d1,d2,'McNemar p=%.2e'%mcn(d1,d2))
    print(' falsealarm',a,fa_,len(fine),cp(fa_,len(fine)),'|',b,fb_,len(fine),cp(fb_,len(fine)),'discordant',f1,f2,'p=%.2e'%mcn(f1,f2))
    miss=lambda X:sum((k[i]['label'].get('at_risk_usd') or 0) for i in real if not e(X[i]))
    print(' missed $ exposure',a,round(miss(A)),b,round(miss(B)))
    for nm,X in((a,A),(b,B)):
        la=sorted(X[i]['latency_ms']/1000 for i in ids if X[i].get('latency_ms'))
        print(' ',nm,'cost',round(sum(X[i]['cost_usd'] for i in ids),4),'median',round(st.median(la),2),'p95',round(la[int(.95*len(la))],1),'next-step ok',sum(X[i].get('next_step')==k[i]['label'].get('next_step') for i in real if e(X[i])))
cmp('HISTORY','test_context','kimi_alone','glm_harness_wiki_low')
cmp('HIST kimi+checks','test_context','kimi_harness_wiki','glm_harness_wiki_low')
cmp('HIST glm alone','test_context','glm_alone_low','glm_harness_wiki_low')
cmp('HIST no knowledge','test_context','glm_harness_low','glm_harness_wiki_low')
cmp('DOCS','test','kimi_alone','glm_harness_wiki_low')
cmp('DOCS 300 no knowledge','test','glm_harness_low','glm_harness_wiki_low')
cmp('DOCS 300 glm alone','test','glm_alone_low','glm_harness_wiki_low')
A,B=P('kimi_alone_v2','test_images'),P('glm_harness_wiki_low','test_images')
k=K['test'];ids=sorted(set(A)&set(B))
real=[i for i in ids if k[i]['label']['real_discrepancy']];fine=[i for i in ids if not k[i]['label']['real_discrepancy'] and k[i]['label']['stratum']!='in_transit']
e=lambda p:p['action']=='ESCALATE'
print('SCANS caught',sum(e(A[i]) for i in real),sum(e(B[i]) for i in real),'fa',sum(e(A[i]) for i in fine),sum(e(B[i]) for i in fine),'fa CI ours',cp(18,50),'kimi',cp(2,50),'McNemar fa',mcn(sum(e(A[i]) and not e(B[i]) for i in fine),sum(e(B[i]) and not e(A[i]) for i in fine)))
