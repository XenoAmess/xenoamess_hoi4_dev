"""Bound display-only image transport; never rewrite a generated PNG master."""
import argparse
import base64
import io
import json
import sys
from pathlib import Path
from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.common import ROOT,file_sha256

MAX_PREVIEW_BYTES=12288
MAX_PREVIEW_JSON_BYTES=20000

def preview(path):
    digest=file_sha256(path)
    with Image.open(path) as opened:
        source=opened.convert('RGBA')
    for edge in (320,256,192,128,96,64):
        display=source.copy();display.thumbnail((edge,edge),Image.Resampling.LANCZOS)
        stream=io.BytesIO();display.save(stream,format='PNG',compress_level=9)
        data=stream.getvalue()
        if len(data)<=MAX_PREVIEW_BYTES:break
    assert len(data)<=MAX_PREVIEW_BYTES
    assert file_sha256(path)==digest,'Original bytes changed during display preparation'
    result={'image_url':'data:image/png;base64,'+base64.b64encode(data).decode('ascii'),
            'preview_bytes':len(data),'preview_size':list(display.size),'original_sha256':digest,
            'original_path':str(path),'output_hint':'Display-only reduced preview, not a game payload or art-review substitute. Unmodified full-resolution original retained at '+str(path)+'; SHA256 '+digest+'. Canonical Git archive is populated by the normal sole-writer import.'}
    # Base64 expands the PNG by 4/3; budget the entire ASCII envelope below
    # the observed 24576-character shell transport truncation boundary.
    assert len(json.dumps(result,ensure_ascii=True).encode('ascii'))<=MAX_PREVIEW_JSON_BYTES
    return result

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--image',required=True)
    args=parser.parse_args();print(json.dumps(preview(Path(args.image)),ensure_ascii=True))
