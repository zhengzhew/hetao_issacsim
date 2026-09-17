import ast,io,pathlib,base64
from types import SimpleNamespace
import numpy as np
from PIL import Image
p=pathlib.Path(__file__).parents[1]/'bridge/core/streaming.py'
tree=ast.parse(p.read_text(encoding='utf-8'))
ns={'np':np,'_CAPTURE':{'encoder':None}}
exec(compile(ast.Module(body=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in ('_encode_frame','_encode_png','capture_frame','finish_capture')],type_ignores=[]),str(p),'exec'),ns)
rng=np.random.default_rng(42)
frame=rng.integers(0,256,(1080,1920,4),dtype=np.uint8)
def old(f):
    a=np.ascontiguousarray(f[:,:,:3].astype(np.uint8)); b=io.BytesIO();Image.fromarray(a).save(b,format='JPEG',quality=90,optimize=False);return b.getvalue()
def new(f):return ns['_encode_frame'](np.ascontiguousarray(f,dtype=np.uint8),90)[1]
assert old(frame)==new(frame),'RGBA JPEG differs'
assert old(frame[:,:,:3])==new(frame[:,:,:3]),'RGB JPEG differs'
ns['_CAPTURE']['encoder']='png'
_,png=ns['_encode_frame'](frame,90)
assert np.array_equal(np.array(Image.open(io.BytesIO(png))),frame[:,:,:3]),'PNG fallback differs'
ns['_CAPTURE']['encoder']=None
print('PASS: JPEG bytes identical; PNG pixels identical')
expected=old(frame)
ns.update(base64=base64,ARGS=SimpleNamespace(capture_width=1920,capture_height=1080),session=SimpleNamespace(),note_activity=lambda _:None,_ensure_capture=lambda *a:None)
ns['_CAPTURE']['annotator']=SimpleNamespace(get_data=lambda:frame)
pending=ns['capture_frame']({'_defer_encode':True,'quality':90})
assert not np.shares_memory(pending['_pixels'],frame)
frame[:]=0
finished=ns['finish_capture'](pending)
assert base64.b64decode(finished['data'])==expected,'Frame changed during deferred encoding'
assert '_pixels' not in finished
print('PASS: deferred frame owns pixels; concurrent source changes cannot corrupt it')
