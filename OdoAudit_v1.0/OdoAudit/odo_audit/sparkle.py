import cv2, numpy as np, os
_T=None
def _tpl():
    global _T
    if _T is None: _T=np.load(os.path.join(os.path.dirname(__file__),'sparkle_template.npy')).astype(np.float32)
    return _T
def _astroid(n):
    c=(n-1)/2; yy,xx=np.mgrid[0:n,0:n]; x=np.abs(xx-c)/c; y=np.abs(yy-c)/c
    return (np.sqrt(x)+np.sqrt(y))<=1.0
def sparkle_score(gray):
    """Score 0-1 for the 4-point sparkle mark (as added by Google Gemini) in the bottom-right corner."""
    h,w=gray.shape; y0,x0=int(h*.75),int(w*.65); roi=gray[y0:,x0:]; best=0.0
    T=_tpl()
    for s in np.linspace(0.45,1.6,13):
        t=cv2.resize(T,None,fx=s*w/502,fy=s*w/502)
        k=t.shape[0]
        if k<9 or k>=roi.shape[0] or k>=roi.shape[1]: continue
        r=cv2.matchTemplate(roi,t,cv2.TM_CCOEFF_NORMED)
        for _ in range(4):
            _,mx,_,(px,py)=cv2.minMaxLoc(r)
            if mx<0.65: break
            r[max(0,py-k//2):py+k//2+1,max(0,px-k//2):px+k//2+1]=-1
            pad=max(1,int(k*3/33)); n=k-2*pad
            patch=roi[py+pad:py+pad+n,px+pad:px+pad+n]
            if patch.shape!=(n,n) or n<7: continue
            mask=_astroid(n); inside=patch[mask].mean(); outside=patch[~mask].mean(); contrast=inside-outside
            ring=roi[max(0,py-k//2):py+k+k//2, max(0,px-k//2):px+k+k//2].astype(np.float32).copy()
            ring[py-max(0,py-k//2):py-max(0,py-k//2)+k, px-max(0,px-k//2):px-max(0,px-k//2)+k]=np.nan
            bright=float(np.nanmean(ring>inside-0.5*contrast)) if np.isfinite(ring).any() else 1.0
            if 15<contrast<110 and bright<0.08:
                best=max(best,float(mx))
    return best
