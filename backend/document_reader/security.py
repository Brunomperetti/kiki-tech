"""Linux seccomp for parser children, including native extensions. Fail closed."""
import ctypes
import errno
import os
import platform


class Filter(ctypes.Structure):
    _fields_ = [('code',ctypes.c_ushort),('jt',ctypes.c_ubyte),('jf',ctypes.c_ubyte),('k',ctypes.c_uint)]


class Program(ctypes.Structure):
    _fields_ = [('len',ctypes.c_ushort),('filter',ctypes.POINTER(Filter))]


# No socket creation, network I/O, process creation, tracing, namespace escape,
# io_uring bypass or filesystem mutations. Existing UDS read/write remain allowed.
NUMBERS = {
 'x86_64': (0xc000003e, [41,42,43,44,45,46,47,48,49,50,51,52,53,54,55,56,57,58,59,62,76,77,82,83,84,85,86,87,88,90,91,92,93,94,101,155,161,165,166,169,175,176,246,248,249,250,258,259,260,263,264,265,266,268,272,280,288,298,299,303,304,307,308,310,311,313,316,317,319,321,322,323,424,425,426,427,434,435,437,438], 2,257),
 'aarch64': (0xc00000b7, [33,34,35,36,37,38,39,40,41,45,46,51,52,53,54,55,97,104,105,106,117,129,130,131,142,198,199,200,201,202,203,204,205,206,207,208,209,210,211,212,220,221,224,225,241,242,243,264,265,268,269,270,271,276,277,279,280,281,282,424,425,426,427,434,435,437,438], None,56),
}


def restrict():
    if platform.machine() not in NUMBERS:
        raise RuntimeError('Arquitectura sin perfil de aislamiento validado.')
    arch, denied, open_nr, openat_nr = NUMBERS[platform.machine()]
    ins = [(0x20,0,0,4),(0x15,1,0,arch),(0x06,0,0,0x80000000),(0x20,0,0,0)]
    if platform.machine() == 'x86_64':
        ins += [(0x35,0,1,0x40000000),(0x06,0,0,0x50000 | errno.EPERM)]
    for nr, offset in [(open_nr,24),(openat_nr,32)]:
        if nr is None:continue
        mask=os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND|(getattr(os,'O_TMPFILE',0)&~os.O_DIRECTORY)
        ins += [(0x15,0,4,nr),(0x20,0,0,offset),(0x45,0,1,mask),(0x06,0,0,0x50000 | errno.EPERM),(0x20,0,0,0)]
    for nr in sorted(set(denied)):
        ins += [(0x15,0,1,nr),(0x06,0,0,0x50000 | errno.EPERM)]
    ins += [(0x06,0,0,0x7fff0000)]
    filters=(Filter*len(ins))(*(Filter(*i) for i in ins))
    program=Program(len(filters),filters)
    libc=ctypes.CDLL(None,use_errno=True)
    if libc.prctl(38,1,0,0,0) != 0 or libc.prctl(22,2,ctypes.byref(program),0,0) != 0:
        raise RuntimeError('No fue posible aplicar seccomp al lector.')
