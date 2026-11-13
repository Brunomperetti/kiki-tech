"""Existing API + existing isolated parser in ONE image/service. No DB operations."""
import os
import signal
import socket
import struct
import json
import subprocess
import sys
import time


def health(path):
    try:
        with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as sock:
            sock.settimeout(1)
            sock.connect(path)
            data=b'{"operation":"health"}'
            sock.sendall(struct.pack('!I',len(data))+data)
            with sock.makefile('rb') as stream:
                size=struct.unpack('!I',stream.read(4))[0]
                if not 0<size<4096:return False
                result=json.loads(stream.read(size))
            return result.get('ok') and result['result'].get('kernel_guard') is True and result['result'].get('native_network_denied') is True and result['result'].get('secret_environment_present') is False
    except (OSError,ValueError,KeyError,struct.error):return False


def main():
    boundary = os.getuid() == 0
    if boundary:
        try:
            os.setgroups([])
            os.setgid(10000)
        except OSError:
            boundary = False
    reader=None
    if not boundary:
        print('Lector bloqueado: frontera de usuarios/chroot no disponible; se conserva la API existente.',flush=True)
    if boundary and os.environ.get('KIKI_DOCUMENT_PARSER_ENABLED','true').lower()=='true':
        reader=subprocess.Popen([sys.executable,'/app/reader_launcher.py'],env={'PATH':'/usr/local/bin:/usr/bin','LANG':'C.UTF-8','PYTHONDONTWRITEBYTECODE':'1','PYTHONUNBUFFERED':'1'},close_fds=True)
        deadline=time.monotonic()+8
        while time.monotonic()<deadline and reader.poll() is None:
            if health('/opt/kiki-reader/run/parser.sock'):break
            time.sleep(.1)
        else:
            if reader.poll() is None:reader.terminate();reader.wait(timeout=3)
            print('Lector documental no disponible: carga bloqueada; API anterior conservada.',flush=True)
    if '--reader-only' in sys.argv:
        if not reader or reader.poll() is not None:raise SystemExit(1)
        api=None
    else:
        port=int(os.environ.get('PORT','8000'))
        if not 1024<=port<=65535:raise SystemExit('Puerto de API fuera de rango.')
        command=[sys.executable,'-m','uvicorn','app.main:app','--host','0.0.0.0','--port',str(port)]
        try:
            api=subprocess.Popen(command,**({'user':10000,'group':10000,'extra_groups':[]} if boundary else {}),close_fds=True)
        except PermissionError:
            # Preserve the historical API user; NEVER fall back to in-process PDF parsing.
            print('No se pudo cambiar el usuario API; se conserva el usuario de ejecución existente.',flush=True)
            api=subprocess.Popen(command,close_fds=True)
    children=[p for p in (api,reader) if p]
    def stop(signum,frame):
        for p in children:
            if p.poll() is None:p.terminate()
    signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
    try:
        target=api or reader
        return target.wait()
    finally:
        stop(None,None)
        for p in children:
            try:p.wait(timeout=35)
            except subprocess.TimeoutExpired:p.kill();p.wait()


if __name__=='__main__':raise SystemExit(main())
