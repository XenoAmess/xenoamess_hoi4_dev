"""Real Windows SendInput scan codes for DirectX keyboard focus; no game API."""
import ctypes,time

SCAN={'esc':0x01,'tab':0x0f,'enter':0x1c,'ctrl':0x1d,'shift':0x2a,'alt':0x38,'space':0x39,'f4':0x3e,'a':0x1e,'c':0x2e,'v':0x2f}

def send_keys(keys):
    codes=[SCAN[key.lower()] for key in keys] # Validate every key before input.
    class MI(ctypes.Structure):_fields_=[('dx',ctypes.c_int32),('dy',ctypes.c_int32),('mouseData',ctypes.c_uint32),('dwFlags',ctypes.c_uint32),('time',ctypes.c_uint32),('dwExtraInfo',ctypes.c_size_t)]
    class KI(ctypes.Structure):_fields_=[('wVk',ctypes.c_uint16),('wScan',ctypes.c_uint16),('dwFlags',ctypes.c_uint32),('time',ctypes.c_uint32),('dwExtraInfo',ctypes.c_size_t)]
    class U(ctypes.Union):_fields_=[('mi',MI),('ki',KI)]
    class INPUT(ctypes.Structure):_fields_=[('type',ctypes.c_uint32),('u',U)]
    assert ctypes.sizeof(INPUT)==(40 if ctypes.sizeof(ctypes.c_void_p)==8 else 28)
    user=ctypes.windll.user32;user.SendInput.argtypes=[ctypes.c_uint,ctypes.POINTER(INPUT),ctypes.c_int];user.SendInput.restype=ctypes.c_uint
    result=[];pressed=[]
    def emit(code,up):
        event=INPUT(type=1,u=U(ki=KI(0,code,0x0008|(0x0002 if up else 0),0,0)))
        ack=user.SendInput(1,ctypes.byref(event),ctypes.sizeof(INPUT))
        result.append({'scan_code':code,'key_up':up,'ack':ack})
        if ack!=1:raise OSError('Windows SendInput did not acknowledge the keyboard event')
        time.sleep(.1)
    try:
        for code in codes:emit(code,False);pressed.append(code)
    finally:
        for code in reversed(pressed):emit(code,True)
    return result
