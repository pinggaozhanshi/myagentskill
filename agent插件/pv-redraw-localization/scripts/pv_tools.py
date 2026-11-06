"""Optional portable checks for PV manifests, audio lag, unchanged video streams and source motion complexity."""
import argparse,copy,hashlib,itertools,json,math,sys
from fractions import Fraction
from pathlib import Path

def validate_manifest(m,reject_example=False):
    example=m.get('verification',{}).get('status')=='schema-example-only'
    if reject_example and example:raise ValueError('Template example is not a measured project; replace it before production')
    source=m['source'];total=source['frame_count']
    assert isinstance(total,int) and total>0
    assert Fraction(source['frame_rate'])>0 and source['width']>0 and source['height']>0
    assert source['timing'] in ['CFR','VFR']
    if source['timing']=='VFR':assert source.get('pts_table'),'VFR requires a measured PTS table'
    cursor=0;ids=set()
    for shot in m['shots']:
        a,b=shot['start'],shot['end'];assert isinstance(a,int) and isinstance(b,int)
        assert shot['id'] not in ids and a==cursor and a<b<=total
        ids.add(shot['id']);cursor=b;end=a
        for exposure in shot.get('exposures',[]):
            assert shot['character'] and exposure['start']==end and exposure['start']<exposure['end']<=b
            assert exposure['pose_id'] and exposure['file'];end=exposure['end']
        if shot['character']:assert end==b,'Missing last frame or an exposure gap'
        else:assert not shot.get('exposures'),'Character layer leaked into an empty shot'
    assert cursor==total
    frames=m.get('verification',{}).get('must_check_frames',[])
    assert all(isinstance(n,int) and 0<=n<total for n in frames)
    return {'valid_structure':True,'frame_count':total,'shots':len(ids),'asset_files_checked':False,'example_only':example,'ready_to_render':False}

def global_tick(note_pos,clip_geometry):
    return clip_geometry['pos']+note_pos

def find_lag(ref,other,start,window,search):
    import numpy as np
    a=ref[start:start+window].astype(float);j=max(0,start-search)
    b=other[j:min(len(other),start+window+search)].astype(float)
    if len(a)!=window or len(b)<window:raise ValueError('Window outside audio')
    ea=float(np.sum(a*a))
    if ea<1e-10:raise ValueError('Reference window is silent')
    length=1<<(len(a)+len(b)-1).bit_length()
    corr=np.fft.irfft(np.fft.rfft(b,length)*np.conj(np.fft.rfft(a,length)),length)[:len(b)-len(a)+1]
    cumulative=np.r_[0,np.cumsum(b*b)];energy=cumulative[len(a):]-cumulative[:-len(a)]
    score=corr/np.sqrt(np.maximum(1e-20,energy*ea));k=int(np.argmax(np.abs(score)))
    return j+k-start,float(score[k])

def read_audio(path,rate):
    import av,numpy as np
    arrays=[];first=None;expected=None
    with av.open(str(path)) as con:
        resampler=av.AudioResampler(format='fltp',layout='stereo',rate=rate)
        def append(frame):
            nonlocal first,expected
            t=float(frame.pts*frame.time_base) if frame.pts is not None else expected
            if first is None:first=0.0 if t is None else t
            if t is not None and expected is not None and abs(t-expected)>2/rate:
                raise ValueError('Non-contiguous audio timeline; resolve gaps in an editor')
            arrays.append(frame.to_ndarray());expected=(first if t is None and expected is None else expected if t is None else t)+frame.samples/rate
        for frame in con.decode(audio=0):
            for converted in resampler.resample(frame):append(converted)
        for converted in resampler.resample(None):append(converted)
    if not arrays:raise ValueError('No audio decoded')
    audio=np.concatenate(arrays,axis=1);offset=round(first*rate)
    if offset>0:audio=np.pad(audio,((0,0),(offset,0)))
    elif offset<0:audio=audio[:,-offset:]
    return audio

def audio_lag(args):
    import numpy as np
    if args.rate<=0 or args.window<=0 or args.max_lag<0:raise ValueError('Invalid measurement options')
    ref=read_audio(args.reference,args.rate);other=read_audio(args.other,args.rate)
    side1=ref[0]-ref[1];side2=other[0]-other[1];mode='side'
    if min(float(np.sqrt(np.mean(side1**2))),float(np.sqrt(np.mean(side2**2))))<1e-6:
        side1=ref.mean(axis=0);side2=other.mean(axis=0);mode='mono-fallback'
    rows=[]
    for time in map(float,args.starts.split(',')):
        if time<0:raise ValueError('Negative window start')
        lag,corr=find_lag(side1,side2,round(time*args.rate),round(args.window*args.rate),round(args.max_lag*args.rate))
        rows.append({'window_start_sec':time,'other_minus_reference_samples':lag,'lag_seconds':lag/args.rate,'correlation':corr})
    if not rows:raise ValueError('No windows')
    median=int(np.median([r['other_minus_reference_samples'] for r in rows]));spread=max(r['other_minus_reference_samples'] for r in rows)-min(r['other_minus_reference_samples'] for r in rows)
    return {'measurement_channel':mode,'sample_rate':args.rate,'windows':rows,'median_lag_samples':median,'suggested_shift_samples':-median,'suggested_shift_seconds':-median/args.rate,'spread_samples':spread,'resolution_sec':1/args.rate,'sign_definition':'other minus reference; positive suggested shift means delay other','lyric_identity_checked':False}

def video_signature(path):
    import av
    content=hashlib.sha256();timing=hashlib.sha256();count=0
    with av.open(str(path)) as con:
        s=con.streams.video[0];ctx=s.codec_context
        meta={'codec':ctx.name,'width':ctx.width,'height':ctx.height,'rate':str(s.average_rate),'extradata_sha256':hashlib.sha256(ctx.extradata or b'').hexdigest()}
        for p in con.demux(s):
            if p.pts is None:continue
            content.update(bytes(p));count+=1
            times=[str(Fraction(value)*p.time_base) if value is not None else 'None' for value in [p.pts,p.dts,p.duration]]
            timing.update(('|'.join(times)+'\n').encode())
    return {'metadata':meta,'packets':count,'payload_sha256':content.hexdigest(),'timing_sha256':timing.hexdigest()}

def compare_video(args):
    import av
    a=video_signature(args.reference);b=video_signature(args.other)
    result={'reference':a,'other':b,'bitstream_and_timing_unchanged':a==b}
    if args.decode:
        with av.open(str(args.reference)) as ca,av.open(str(args.other)) as cb:
            count=0;pixels=True;times=True
            for fa,fb in itertools.zip_longest(ca.decode(video=0),cb.decode(video=0)):
                if fa is None or fb is None:pixels=False;times=False;break
                pixels&=(fa.width,fa.height)==(fb.width,fb.height) and fa.to_ndarray(format='rgb24').tobytes()==fb.to_ndarray(format='rgb24').tobytes()
                times&=Fraction(fa.pts)*fa.time_base==Fraction(fb.pts)*fb.time_base;count+=1
        result.update({'decoded_frames_compared':count,'decoded_pixels_identical':pixels,'decoded_times_identical':times})
    return result

# Motion profile: thresholds are for 8-bit luma at the default 320px analysis width, calibrated on three real PVs (references/motion-complexity.md).
TH={'luma':24,'hold_c':0.002,'hold_blk':10,'draw_c':0.03,'draw_blk':30,'big_c':0.15,'cut_hist':0.5,'revisit_c':0.01,'revisit_blk':15}
ADVICE={'T0':'保持为主：关键姿势+原曝光表；口型/眨眼做局部替换',
        'T1':'有限动画：源片每次换画都重绘一张，停格照抄源片，不插值、不拉伸',
        'T2':'逐帧动画：几乎每帧都要新画，按源片逐帧对应重绘；纯故障/闪白帧可人工改为特效合成'}

def phase_shift(a,b,win):
    import numpy as np
    R=np.fft.rfft2(a*win)*np.conj(np.fft.rfft2(b*win));r=np.fft.irfft2(R/np.maximum(np.abs(R),1e-6),s=a.shape)
    dy,dx=(int(v) for v in np.unravel_index(int(np.argmax(r)),r.shape))
    if dy>a.shape[0]//2:dy-=a.shape[0]
    if dx>a.shape[1]//2:dx-=a.shape[1]
    return dx,dy,float(r.max())

def block_max(d,weight=None,n=8):
    import numpy as np
    h,w=d.shape;bh,bw=h//n,w//n
    pool=lambda x:x[:bh*n,:bw*n].reshape(n,bh,n,bw).mean(axis=(1,3))
    if weight is None:return float(pool(d).max())
    cover=pool(weight);ok=cover>=0.25
    return float((pool(d*weight)[ok]/cover[ok]).max()) if ok.any() else 0.0

def dilate(m,r=3):
    import numpy as np
    p=np.pad(m,r);h,w=m.shape;out=np.zeros_like(m)
    for dy in range(2*r+1):
        for dx in range(2*r+1):out|=p[dy:dy+h,dx:dx+w]
    return out

def measure_transition(prev,cur,win,mask=None):
    """Change of cur vs prev. With a character mask, change is counted inside the mask only (still as a fraction of the frame)."""
    import numpy as np
    d=np.abs(cur-prev);changed=d>TH['luma'];full=float(changed.mean())
    dx,dy,peak=phase_shift(cur,prev,win);h,w=cur.shape
    resid=full if not(dx or dy) else float((np.abs(cur[max(0,dy):h+min(0,dy),max(0,dx):w+min(0,dx)]-prev[max(0,-dy):h+min(0,-dy),max(0,-dx):w+min(0,-dx)])>TH['luma']).mean())
    hist=lambda x:np.bincount(np.clip(x//8,0,31).astype(np.int64).ravel(),minlength=32)/x.size
    m={'dx':dx,'dy':dy,'peak':round(peak,3),'resid':round(resid,5),'full':round(full,5),'hist':round(float(np.abs(hist(cur)-hist(prev)).sum()),4)}
    if mask is not None and mask.mean()>=0.01:
        m.update(c24=round(float((changed&mask).sum())/d.size,5),blk=round(block_max(d,mask.astype(np.float32)),2),bg=round(float((changed&~mask).mean()),5))
    else:m.update(c24=round(full,5),blk=round(block_max(d),2))
    m['camera']=bool((dx or dy) and peak>=0.2 and resid<TH['draw_c'] and resid<0.5*full)
    m['cut']=bool(m['hist']>=TH['cut_hist'] and full>=0.3)
    if m['camera']:m['kind']='camera'
    elif m['c24']>=TH['draw_c'] or m['blk']>=TH['draw_blk']:m['kind']='big' if m['c24']>=TH['big_c'] else 'draw'
    elif m['c24']>TH['hold_c'] or m['blk']>TH['hold_blk']:m['kind']='minor'
    else:m['kind']='hold'
    return m

def summarize_frames(rows,dt,cells):
    """rows: per-frame dicts in order; the first row of a range is counted as a drawing slot."""
    n=len(rows);kinds=[r['kind'] for r in rows];draw=[k in('draw','big','first') for k in kinds]
    trans=sum(1 for k in kinds if k in('draw','big'));slots=sum(draw);rev=sum(1 for r,dr in zip(rows,draw) if dr and r.get('revisit_of') is not None)
    on1=sum(1 for r in rows if r['kind'] in('draw','big') and r.get('after_change'))
    big=kinds.count('big');dur=max(n*dt,1e-9);dps=slots/dur;on1s=on1/trans if trans else 0.0;bigs=big/trans if trans else 0.0
    tier='T0' if dps<3 else 'T2' if (dps>=15 or(on1s>=0.4 and dps>=8)) else 'T1'
    flags=[f for f,ok in [('big_motion',bigs>=0.5 and trans>=3),('loop_reuse',slots>0 and rev/slots>=0.3),('camera_move',kinds.count('camera')>=0.3*n),
                          ('busy_background',sum(1 for r in rows if r.get('bg',0)>=TH['draw_c'])>=0.5*n)] if ok]
    return {'frames':n,'seconds':round(dur,3),'drawing_slots':slots,'revisits':rev,'unique_drawings':slots-rev,'local_slots':kinds.count('minor'),
            'camera_frames':kinds.count('camera'),'drawings_per_sec':round(dps,2),'on_ones_share':round(on1s,3),'big_share':round(bigs,3),
            'tier':tier,'flags':flags,'advice':ADVICE[tier],'images_at_cells':math.ceil((slots-rev)/cells)}

def profile_frames(items,window=1.0,cells=8,shots=None,library_size=16):
    """items: iterable of (frame_index, pts_seconds, gray float32 HxW, mask bool HxW or None)."""
    import numpy as np
    rows=[];prev=None;pmask=None;win=None;library=[]
    for idx,t,g,mask in items:
        if prev is None:
            win=np.outer(np.hanning(g.shape[0]),np.hanning(g.shape[1])).astype(np.float32)
            row={'frame':idx,'t':t,'kind':'first'};library.append((idx,g))
        else:
            union=dilate(mask|pmask) if mask is not None and pmask is not None else None
            row={'frame':idx,'t':t,**measure_transition(prev,g,win,union)}
            if row['kind'] in('draw','big'):
                best=None
                for j,ref in library:
                    d=np.abs(g-ref)
                    if (d>TH['luma']).mean()<TH['revisit_c'] and block_max(d)<TH['revisit_blk']:best=j;break
                row['revisit_of']=best
                if best is None:library=[(idx,g)]+library[:library_size-1]
        if rows:row['after_change']=rows[-1]['kind'] in('first','draw','big')
        rows.append(row);prev=g;pmask=mask
    if not rows:raise ValueError('No frames in the requested range')
    times=[r['t'] for r in rows];dt=float(np.median(np.diff(times))) if len(times)>1 else 1/30
    t0=times[0];groups={}
    for r in rows:groups.setdefault(int((r['t']-t0+1e-9)//window),[]).append(r)
    windows=[{'start_sec':round(t0+k*window,3),'end_sec':round(t0+(k+1)*window,3),**summarize_frames(groups[k],dt,cells)} for k in sorted(groups)]
    out={'frames':len(rows),'first_frame':rows[0]['frame'],'last_frame':rows[-1]['frame'],'start_sec':round(t0,4),'frame_duration':round(dt,6),
         'thresholds':TH,'windows':windows}
    if shots:
        out['shots']=[]
        for s in shots:
            part=[r for r in rows if s['start']<=r['frame']<s['end']]
            if part:out['shots'].append({'id':s['id'],'start':s['start'],'end':s['end'],**summarize_frames([dict(part[0],kind='first')]+part[1:],dt,cells)})
    total=summarize_frames(rows,dt,cells);by=lambda key:{t:sum(w[key] for w in windows if w['tier']==t) for t in('T0','T1','T2')}
    total.update(frames_by_tier=by('frames'),windows_by_tier={t:sum(1 for w in windows if w['tier']==t) for t in('T0','T1','T2')},cells_per_image=cells,
                 per_frame_upper_bound=len(rows),new_drawing_frames=[r['frame'] for r in rows if r['kind'] in('first','draw','big') and r.get('revisit_of') is None],
                 reuse_map={str(r['frame']):r['revisit_of'] for r in rows if r.get('revisit_of') is not None})
    out['totals']=total;out['rows']=rows
    return out

def make_segmenter(model):
    import numpy as np,onnxruntime as ort
    sess=ort.InferenceSession(str(model),providers=[p for p in('CUDAExecutionProvider','CPUExecutionProvider') if p in ort.get_available_providers()])
    inp=sess.get_inputs()[0];size=inp.shape[-1] if isinstance(inp.shape[-1],int) else 1024
    def run(frame,shape):
        s=size/max(frame.width,frame.height);nh,nw=max(2,round(frame.height*s)//2*2),max(2,round(frame.width*s)//2*2)
        x=np.zeros((size,size,3),np.float32);ph,pw=(size-nh)//2,(size-nw)//2
        x[ph:ph+nh,pw:pw+nw]=frame.reformat(width=nw,height=nh,format='rgb24').to_ndarray().astype(np.float32)/255
        m=sess.run(None,{inp.name:x.transpose(2,0,1)[None]})[0][0,0,ph:ph+nh,pw:pw+nw]
        return m[np.ix_((np.arange(shape[0])*nh//shape[0]),(np.arange(shape[1])*nw//shape[1]))]>0.5
    return run

def decode_gray(path,start,end,width,roi,segment=None,every=1):
    import av,numpy as np
    with av.open(str(path)) as con:
        s=con.streams.video[0];s.thread_type='AUTO';idx=-1;mask=None;h=None
        for f in con.decode(s):
            idx+=1
            if f.pts is None:raise ValueError('Frame without PTS; remux before profiling')
            t=float(f.pts*f.time_base)
            if t<start-1e-6:continue
            if end is not None and t>=end-1e-6:break
            if h is None:h=max(2,round(f.height*width/f.width/2)*2)
            g=f.reformat(width=width,height=h,format='gray').to_ndarray().astype(np.float32)
            if segment and(mask is None or idx%every==0):mask=segment(f,g.shape)
            if roi:
                x0,y0,x1,y1=round(roi[0]*width),round(roi[1]*h),round((roi[0]+roi[2])*width),round((roi[1]+roi[3])*h)
                yield idx,t,g[y0:y1,x0:x1],(mask[y0:y1,x0:x1] if mask is not None else None)
            else:yield idx,t,g,mask

def motion_profile(args):
    if args.window<=0 or args.width<64 or args.cells<1 or args.mask_every<1:raise ValueError('Invalid motion-profile options')
    roi=tuple(float(v) for v in args.roi.split(',')) if args.roi else None
    if roi and(len(roi)!=4 or min(roi)<0 or roi[0]+roi[2]>1 or roi[1]+roi[3]>1 or roi[2]<=0 or roi[3]<=0):raise ValueError('--roi is x,y,w,h as fractions of the frame')
    shots=json.loads(args.manifest.read_text(encoding='utf-8-sig'))['shots'] if args.manifest else None
    segment=make_segmenter(args.mask_model) if args.mask_model else None
    out=profile_frames(decode_gray(args.video,args.start,args.end,args.width,roi,segment,args.mask_every),args.window,args.cells,shots)
    out['source']={'video':str(args.video),'start':args.start,'end':args.end,'analysis_width':args.width,'roi':roi,'character_mask':str(args.mask_model) if args.mask_model else None,
                   'note':'Candidate tiers only; confirm on frames and an encoded sample before generating.'}
    if args.csv:
        keys=['frame','t','kind','c24','blk','bg','full','resid','dx','dy','peak','hist','cut','revisit_of']
        with args.csv.open('x',newline='',encoding='utf-8-sig') as f:
            import csv;w=csv.DictWriter(f,fieldnames=keys,extrasaction='ignore');w.writeheader();w.writerows(out['rows'])
    return out

def self_test():
    fixture={'source':{'frame_count':4,'frame_rate':'30000/1001','width':1920,'height':1080,'timing':'CFR'},'shots':[{'id':'one','start':0,'end':3,'character':True,'exposures':[{'start':0,'end':1,'pose_id':'A','file':'a.png'},{'start':1,'end':2,'pose_id':'B','file':'b.png'},{'start':2,'end':3,'pose_id':'A','file':'a.png'}]},{'id':'empty','start':3,'end':4,'character':False,'exposures':[]}]}
    validate_manifest(fixture);bad=copy.deepcopy(fixture);bad['shots'][0]['exposures'][-1]['end']=2
    try:validate_manifest(bad)
    except AssertionError:pass
    else:raise AssertionError('Missing last frame was accepted')
    example=copy.deepcopy(fixture);example['verification']={'status':'schema-example-only'}
    assert validate_manifest(example)['example_only']
    try:validate_manifest(example,reject_example=True)
    except ValueError:pass
    else:raise AssertionError('Production guard accepted the example manifest')
    assert global_tick(720,{'pos':960,'clipPos':480,'clipBegin':1440})==1680
    assert abs(1680*60/(88*480)-2.386363636)<1e-8
    result={'frame_boundary_and_tick_checks':'passed'}
    try:import numpy as np
    except ImportError:result['audio_lag_checks']='not run: NumPy unavailable'
    else:
        x=np.random.default_rng(17).normal(size=10000)
        for shift in [171,-171]:
            y=np.r_[np.zeros(shift),x] if shift>=0 else x[-shift:]
            lag,corr=find_lag(x,y,1000,3000,300);assert lag==shift and abs(corr-1)<1e-8,(lag,corr)
        result['audio_lag_checks']='passed for late and early audio; recommended shift is inverse sign'
        rng=np.random.default_rng(5);base=np.kron(rng.integers(0,256,(18,32)),np.ones((10,10))).astype(np.float32)
        win=np.outer(np.hanning(180),np.hanning(320)).astype(np.float32)
        def patch(img,y,x,s,invert=False):
            out=img.copy();out[y:y+s,x:x+s]=(out[y:y+s,x:x+s]+128)%256 if invert else rng.integers(0,256,(s,s));return out
        kind=lambda a,b,mask=None:measure_transition(a,b,win,mask)['kind']
        assert kind(base,base)=='hold' and kind(base,patch(base,50,50,12,True))=='minor'
        assert kind(base,patch(base,40,40,60))=='draw' and kind(base,patch(base,10,10,160))=='big'
        assert kind(base,np.roll(base,6,axis=1))=='camera','held drawing moved by the camera must not count as a new drawing'
        mask=np.zeros((180,320),bool);mask[40:140,100:220]=True;m=measure_transition(base,patch(base,0,0,40),win,dilate(mask))
        assert m['kind']=='hold' and m['bg']>0.01,'background-only change must not count inside the character mask'
        A,B,C=base,patch(base,40,40,60),patch(base,100,200,60)
        prof=profile_frames(((i,i/30,f,None) for i,f in enumerate([A,A,A,B,B,B,A,A,A,C,C,C])),window=1.0,cells=8);rows=prof['rows']
        assert [r['kind'] for r in rows]==['first','hold','hold','draw','hold','hold','draw','hold','hold','draw','hold','hold']
        assert rows[6]['revisit_of']==0 and rows[3]['revisit_of'] is None and prof['totals']['unique_drawings']==3,'A->B->A must reuse A'
        imgs=[patch(base,(k*13)%120,(k*29)%250,60) for k in range(40)]
        tier=lambda expo:profile_frames(((i,i/30,f,None) for i,f in enumerate([imgs[k] for k,e in enumerate(expo) for _ in range(e)])),window=10)['totals']['tier']
        assert tier([3]*10)=='T1' and tier([1]*30)=='T2' and tier([15,15])=='T0'
        result['motion_profile_checks']='passed: hold/minor/draw/big/camera kinds, mask ignores background, A->B->A reuse, T0/T1/T2 tiers'
    return result

def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
    sub.add_parser('self-test')
    m=sub.add_parser('manifest-check');m.add_argument('manifest',type=Path);m.add_argument('--output',type=Path);m.add_argument('--reject-example',action='store_true')
    a=sub.add_parser('audio-lag');a.add_argument('reference',type=Path);a.add_argument('other',type=Path);a.add_argument('--rate',type=int,default=8000);a.add_argument('--starts',default='3,20,65');a.add_argument('--window',type=float,default=3);a.add_argument('--max-lag',type=float,default=2);a.add_argument('--output',type=Path)
    v=sub.add_parser('compare-video');v.add_argument('reference',type=Path);v.add_argument('other',type=Path);v.add_argument('--decode',action='store_true');v.add_argument('--output',type=Path)
    mp=sub.add_parser('motion-profile');mp.add_argument('video',type=Path);mp.add_argument('--start',type=float,default=0.0);mp.add_argument('--end',type=float)
    mp.add_argument('--window',type=float,default=1.0);mp.add_argument('--width',type=int,default=320);mp.add_argument('--roi');mp.add_argument('--manifest',type=Path)
    mp.add_argument('--mask-model',type=Path);mp.add_argument('--mask-every',type=int,default=1);mp.add_argument('--cells',type=int,default=8)
    mp.add_argument('--csv',type=Path);mp.add_argument('--output',type=Path)
    args=p.parse_args()
    if args.command=='self-test':result=self_test()
    elif args.command=='manifest-check':result=validate_manifest(json.loads(args.manifest.read_text(encoding='utf-8-sig')),args.reject_example)
    elif args.command=='audio-lag':result=audio_lag(args)
    elif args.command=='motion-profile':result=motion_profile(args)
    else:result=compare_video(args)
    encoded=json.dumps(result,ensure_ascii=False,indent=2)
    if getattr(args,'output',None):
        with args.output.open('x',encoding='utf-8') as f:f.write(encoded+'\n')
    if args.command=='motion-profile':
        brief={k:v for k,v in result['totals'].items() if k not in('new_drawing_frames','reuse_map','advice')}
        brief['windows']=[f"{w['start_sec']:.1f}-{w['end_sec']:.1f}s {w['tier']} slots={w['drawing_slots']} unique={w['unique_drawings']} local={w['local_slots']} "
                          f"d/s={w['drawings_per_sec']} on1={w['on_ones_share']} big={w['big_share']} {','.join(w['flags'])}".rstrip() for w in result['windows']]
        print(json.dumps(brief,ensure_ascii=False,indent=1))
    else:print(encoded)
    if args.command=='compare-video' and not(result['bitstream_and_timing_unchanged'] or (result.get('decoded_pixels_identical') and result.get('decoded_times_identical'))):return 1
    return 0

if __name__=='__main__':
    try:sys.exit(main())
    except (ValueError,AssertionError,KeyError,ImportError,OSError) as exc:print(f'Check failed: {exc}',file=sys.stderr);sys.exit(2)
