"""Screenshot/OCR and guarded real keyboard/mouse input. No MCP or UIA."""
from __future__ import annotations

import argparse
import asyncio
import ctypes
from pathlib import Path
import sys
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.common import ROOT,file_sha256,machine_id,utc_now,write_json
from PIL import Image

def desktop_modules():
    # Real Windows primary display pixels; no preview-scale assumptions.
    ctypes.windll.user32.SetProcessDPIAware()
    import pyautogui
    import win32gui
    return pyautogui,win32gui

def observe(output,ocr=False):
    gui,windows=desktop_modules()
    output=Path(output)
    output.parent.mkdir(parents=True,exist_ok=True)
    image=gui.screenshot()
    image.save(output)
    hwnd=windows.GetForegroundWindow()
    receipt={"machine_id":machine_id(),"observed_at_utc":utc_now(),"source":"fresh pyautogui.screenshot","screenshot":str(output.resolve()),"sha256":file_sha256(output),"image_size":list(image.size),"desktop_size":list(gui.size()),"foreground_hwnd":hwnd,"foreground_title":windows.GetWindowText(hwnd),"window_rect":list(windows.GetWindowRect(hwnd))}
    if ocr:
        import winocr
        from winrt.windows.media.ocr import OcrEngine
        languages=[lang.language_tag for lang in OcrEngine.available_recognizer_languages]
        if not languages:raise SystemExit("No Windows OCR language installed; screenshot saved")
        language=next((item for item in languages if item.lower().startswith("zh")),languages[0])
        result=winocr.recognize_pil_sync(image,lang=language)
        receipt["ocr"]=result
        receipt["ocr_language"]=language
    write_json(output.with_suffix(".json"),receipt)
    print(__import__('json').dumps({k:v for k,v in receipt.items() if k!="ocr"},ensure_ascii=False,indent=2))
    if ocr:print("OCR TEXT:",receipt["ocr"].get("text",""))
    return receipt

def focus(hwnd):
    _,windows=desktop_modules()
    if not windows.IsWindow(hwnd):raise SystemExit("Target HWND is gone")
    if windows.GetForegroundWindow()!=hwnd:
        windows.ShowWindow(hwnd,9)
        windows.SetForegroundWindow(hwnd)
        deadline=time.monotonic()+1
        while windows.GetForegroundWindow()!=hwnd and time.monotonic()<deadline:time.sleep(0.05)
    if windows.GetForegroundWindow()!=hwnd:raise SystemExit("Target HWND not focused")
    return windows

def click(args):
    gui,windows=desktop_modules()
    windows=focus(args.hwnd)
    with Image.open(args.screenshot) as image:width,height=image.size
    current=tuple(gui.size())
    if current!=(width,height):raise SystemExit("Screenshot and current desktop dimensions differ")
    stamp=Path(args.screenshot).stat().st_mtime
    if time.time()-stamp>args.max_age:raise SystemExit("Screenshot too old; capture again")
    left,top,view_width,view_height=args.content_rect
    if view_width<=0 or view_height<=0 or not (left<=args.x<left+view_width and top<=args.y<top+view_height):raise SystemExit("Preview content rectangle missing/invalid or point out of bounds")
    x=round((args.x-left)*width/view_width)
    y=round((args.y-top)*height/view_height)
    if not (0<=x<width and 0<=y<height):raise SystemExit("Mapped click out of bounds")
    move_only=getattr(args,'move_only',False)
    if move_only:gui.moveTo(x,y,duration=.15)
    else:gui.click(x,y)
    after=list(gui.size())
    receipt={"machine_id":machine_id(),"observed_at_utc":utc_now(),"source_screenshot":str(Path(args.screenshot).resolve()),"source_sha256":file_sha256(Path(args.screenshot)),"image_size":[width,height],"desktop_before":list(current),"preview_content_rect":args.content_rect,"preview_point":[args.x,args.y],"desktop_point":[x,y],"target_hwnd":args.hwnd,"desktop_after":after,'input_type':'mouse move only' if move_only else 'mouse click',"input_ack":True,"business_result":"unverified; take a fresh screenshot/OCR"}
    write_json(Path(args.receipt),receipt)
    if after!=list(current):raise SystemExit("Desktop dimensions changed after input; receipt saved, stop and observe")
    print("Mouse input sent; business result requires fresh screenshot/OCR")

def keys(args):
    gui,windows=desktop_modules()
    focus(args.hwnd)
    user=ctypes.windll.user32
    user.LoadKeyboardLayoutW.restype=ctypes.c_void_p
    layout=user.LoadKeyboardLayoutW("00000409",1)
    user.SendMessageW(args.hwnd,0x0050,0,ctypes.c_void_p(layout))
    import win32process
    thread,_=win32process.GetWindowThreadProcessId(args.hwnd)
    user.GetKeyboardLayout.restype=ctypes.c_void_p
    langid=user.GetKeyboardLayout(thread)&0xffff
    if langid!=0x0409:raise SystemExit(f"Keyboard LANGID is {langid:#06x}, expected 0x0409")
    if windows.GetForegroundWindow()!=args.hwnd:raise SystemExit("Focus changed")
    if args.text_file is not None:args.text=Path(args.text_file).read_text(encoding="utf-8").strip()
    text_readback=None
    scan_events=None
    if args.scan_codes:
        if args.text is not None:raise SystemExit('Scan-code mode is for explicit keys/hotkeys only, not clipboard text')
        from tools.keyboard_scan_codes import send_keys
        scan_events=send_keys(args.hotkey or [args.key])
    elif args.text is not None:
        import win32clipboard
        win32clipboard.OpenClipboard()
        try:
            win32clipboard.EmptyClipboard()
            win32clipboard.SetClipboardText(args.text,13)
        finally:win32clipboard.CloseClipboard()
        gui.hotkey("ctrl","a")
        gui.hotkey("ctrl","v")
        time.sleep(0.15)
        # Read the focused text field through real keys and the OS clipboard.
        # No accessibility/control API is used to read or set the field.
        gui.hotkey("ctrl","a")
        gui.hotkey("ctrl","c")
        time.sleep(0.15)
        win32clipboard.OpenClipboard()
        try:text_readback=win32clipboard.GetClipboardData(13)
        finally:win32clipboard.CloseClipboard()
        if text_readback!=args.text:
            write_json(Path(args.receipt),{"machine_id":machine_id(),"observed_at_utc":utc_now(),"target_hwnd":args.hwnd,"langid":"0x0409","input_ack":True,"text":args.text,"text_readback":text_readback,"business_result":"text-mismatch; no further action authorized by this receipt"})
            raise SystemExit("Focused text field readback differs from requested text; stop and observe")
    elif args.hotkey:gui.hotkey(*args.hotkey)
    else:gui.press(args.key)
    write_json(Path(args.receipt),{"machine_id":machine_id(),"observed_at_utc":utc_now(),"target_hwnd":args.hwnd,"langid":"0x0409","input_ack":True,'input_backend':'Windows SendInput real keyboard scan codes' if args.scan_codes else 'pyautogui virtual-key keyboard events','scan_events':scan_events,"keys":args.hotkey or args.key,"text":args.text,"text_readback":text_readback,"business_result":"Text verified via real Ctrl+A/Ctrl+C where supplied; page/action effect still requires screenshot/OCR"})
    print("Keyboard input sent; business result requires fresh screenshot/OCR")

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest="command",required=True)
    sub.add_parser("windows")
    shot=sub.add_parser("observe")
    shot.add_argument("--output",required=True)
    shot.add_argument("--ocr",action="store_true")
    mouse=sub.add_parser("click")
    mouse.add_argument("--screenshot",required=True)
    mouse.add_argument("--content-rect",nargs=4,type=float,required=True,metavar=("LEFT","TOP","WIDTH","HEIGHT"))
    mouse.add_argument("--x",type=float,required=True)
    mouse.add_argument("--y",type=float,required=True)
    mouse.add_argument("--hwnd",type=int,required=True)
    mouse.add_argument("--receipt",required=True)
    mouse.add_argument("--max-age",type=int,default=120)
    mouse.add_argument('--move-only',action='store_true',help='Move the real cursor through the same coordinate guard, without clicking')
    keyboard=sub.add_parser("keys")
    keyboard.add_argument("--hwnd",type=int,required=True)
    keyboard.add_argument("--receipt",required=True)
    keyboard.add_argument('--scan-codes',action='store_true',help='Real SendInput keyboard scan codes for DirectX key/hotkey input; result still needs screenshot readback')
    group=keyboard.add_mutually_exclusive_group(required=True)
    group.add_argument("--key")
    group.add_argument("--hotkey",nargs="+")
    group.add_argument("--text")
    group.add_argument("--text-file")
    args=parser.parse_args()
    if args.command=="windows":
        _,windows=desktop_modules()
        rows=[]
        def collect(hwnd,_):
            title=windows.GetWindowText(hwnd)
            if windows.IsWindowVisible(hwnd) and title:rows.append({"hwnd":hwnd,"title":title,"rect":list(windows.GetWindowRect(hwnd))})
        windows.EnumWindows(collect,None)
        print(__import__('json').dumps({"machine_id":machine_id(),"observed_at_utc":utc_now(),"source":"OS visible top-level HWND metadata only; no controls or game state","windows":rows},ensure_ascii=False,indent=2))
    elif args.command=="observe":observe(args.output,args.ocr)
    elif args.command=="click":click(args)
    else:keys(args)

if __name__=="__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
