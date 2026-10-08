"""Optional portable checks for PV manifests, audio lag and unchanged video streams."""
import argparse,copy,hashlib,itertools,json,sys
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
    return result

def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
    sub.add_parser('self-test')
    m=sub.add_parser('manifest-check');m.add_argument('manifest',type=Path);m.add_argument('--output',type=Path);m.add_argument('--reject-example',action='store_true')
    a=sub.add_parser('audio-lag');a.add_argument('reference',type=Path);a.add_argument('other',type=Path);a.add_argument('--rate',type=int,default=8000);a.add_argument('--starts',default='3,20,65');a.add_argument('--window',type=float,default=3);a.add_argument('--max-lag',type=float,default=2);a.add_argument('--output',type=Path)
    v=sub.add_parser('compare-video');v.add_argument('reference',type=Path);v.add_argument('other',type=Path);v.add_argument('--decode',action='store_true');v.add_argument('--output',type=Path)
    args=p.parse_args()
    if args.command=='self-test':result=self_test()
    elif args.command=='manifest-check':result=validate_manifest(json.loads(args.manifest.read_text(encoding='utf-8-sig')),args.reject_example)
    elif args.command=='audio-lag':result=audio_lag(args)
    else:result=compare_video(args)
    encoded=json.dumps(result,ensure_ascii=False,indent=2)
    if getattr(args,'output',None):
        with args.output.open('x',encoding='utf-8') as f:f.write(encoded+'\n')
    print(encoded)
    if args.command=='compare-video' and not(result['bitstream_and_timing_unchanged'] or (result.get('decoded_pixels_identical') and result.get('decoded_times_identical'))):return 1
    return 0

if __name__=='__main__':
    try:sys.exit(main())
    except (ValueError,AssertionError,KeyError,ImportError,OSError) as exc:print(f'Check failed: {exc}',file=sys.stderr);sys.exit(2)
