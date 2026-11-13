"""Offline smoke of the ACTUAL production Dockerfile; no ports or providers."""
import base64
import hashlib
import json
from pathlib import Path
import subprocess
import time

ROOT=Path(__file__).resolve().parents[1]
DOCKER=['docker','--host=unix:///var/run/docker.sock']
NAME='kiki-activation-image-check'
IMAGE='kiki-tech-production:activation-local'
RPC='''import json,socket,struct,sys
body=sys.stdin.buffer.read()
with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as s:
 s.settimeout(12);s.connect('/opt/kiki-reader/run/parser.sock');s.sendall(struct.pack('!I',len(body))+body)
 with s.makefile('rb') as f:
  n=struct.unpack('!I',f.read(4))[0];assert 0<n<=524288
  result=json.loads(f.read(n))
print(json.dumps(result))
'''


def rpc(data):
    r=subprocess.run(DOCKER+['exec','-i','--user','10000:10000',NAME,'python','-c',RPC],input=json.dumps(data).encode(),capture_output=True,check=True)
    return json.loads(r.stdout)


def main():
    raw=(ROOT/'integration/fixtures/hileret-original.pdf').read_bytes()
    assert hashlib.sha256(raw).hexdigest()=='bd99c29548cbf683e57b1fd6f2973f37ccef76477e2f6bc45379017a63599291'
    inspect=json.loads(subprocess.check_output(DOCKER+['image','inspect',IMAGE]))[0]
    assert 'KIKI_AUTO_CREATE_SCHEMA=false' in inspect['Config']['Env']
    # Explicit SQLite override ONLY for this network=none image smoke. PG tests are separate.
    subprocess.run(DOCKER+['run','--detach','--name',NAME,'--network','none','--read-only','--cap-drop','ALL','--cap-add','SYS_CHROOT','--cap-add','SETUID','--cap-add','SETGID','--cap-add','KILL','--memory','512m','--pids-limit','32','--tmpfs','/tmp:rw,size=16m','--tmpfs','/opt/kiki-reader/run:rw,uid=10001,gid=10000,mode=0750,size=1m','-e','DATABASE_URL=sqlite:////tmp/fixture.db','-e','KIKI_AUTO_CREATE_SCHEMA=true','-e','KIKI_AI_API_KEY=SYNTHETIC-SENTINEL-NOT-A-CREDENTIAL','-e','APP_SESSION_SECRET=SYNTHETIC-SENTINEL-NOT-A-CREDENTIAL',IMAGE],check=True,capture_output=True)
    try:
        for _ in range(60):
            try:
                health=rpc({'operation':'health'})
                if health['ok']:break
            except (subprocess.CalledProcessError,ValueError):pass
            time.sleep(.25)
        else:raise AssertionError('No inició lector productivo aislado')
        details=health['result']
        assert details['kernel_guard'] and details['native_network_denied']
        assert not any(details[k] for k in ('backend_visible','proc_visible','secret_environment_present'))
        print('Lector: seccomp nativo, chroot, sin /app, /proc ni entorno de credenciales: PASS',flush=True)
        for _ in range(40):
            check=subprocess.run(DOCKER+['exec','--user','10000:10000',NAME,'python','-c',"import http.client; c=http.client.HTTPConnection('127.0.0.1',8000); c.request('GET','/health'); r=c.getresponse(); assert r.status==200; print('API original y lector en una imagen, v2 desactivada: PASS')"],capture_output=True,text=True)
            if check.returncode==0:break
            time.sleep(.25)
        else:raise AssertionError('No inició la API original')
        status=check.stdout
        print(status.strip(),flush=True)
        payload={'filename':'hileret-original.pdf','content_type':'application/pdf','content_base64':base64.b64encode(raw).decode()}
        results=[]
        for number in range(6):
            start=time.monotonic()
            try:result=rpc(payload)
            except subprocess.CalledProcessError as exc:
                last=(exc.stderr or b'').decode(errors='replace').splitlines()[-1:]
                result={'ok':False,'transport_error':last[0] if last else 'no response'}
            elapsed=time.monotonic()-start
            entry={'attempt':number+1,'ok':result.get('ok') is True,'seconds':round(elapsed,3)}
            if not result.get('ok'):entry['error']=result.get('transport_error',result.get('error_code','DOCUMENT_REJECTED'))
            results.append(entry)
            print('Intento independiente: '+json.dumps(entry),flush=True)
            if result.get('ok'):
                parsed=result['result'];claims={c['field']:c for c in parsed['claims']}
                assert claims['ean']['value']=='7794940000796'
                assert claims['logistic_dun']['value']=='97794940000799'
                assert claims['logistic_units']['value']=='9'
                assert claims['presentation']['value']=='200 ml'
                assert all('pagina/2/tabla/stevia/' in c['location'] for c in parsed['claims'])
                assert not any(c['field'] in {'ingredients','allergens','certification'} or c['field'].startswith('nutrition.') for c in parsed['claims'])
        print('PDF auténtico, seis intentos sin reintento oculto: '+json.dumps(results),flush=True)
        assert all(r['ok'] for r in results),'Rechazo del original: conservar bloqueo y diagnosticar sin ampliar límites'
        for body in [dict(payload,content_base64=base64.b64encode(raw[:-1]+b'X').decode()),dict(payload,content_type='text/plain'),{'filename':'big.txt','content_type':'text/plain','content_base64':base64.b64encode(b'x'*524289).decode()},{'filename':'active.html','content_type':'text/html','content_base64':base64.b64encode(b'<script>alert(1)</script>').decode()}]:
            assert rpc(body)['ok'] is False
        print('Hash alterado, MIME incorrecto, 512 KiB y HTML activo rechazados: PASS',flush=True)
        peak=subprocess.run(DOCKER+['exec',NAME,'python','-c',"from pathlib import Path; p=Path('/sys/fs/cgroup/memory.peak'); print(p.read_text().strip() if p.exists() else 'no disponible')"],capture_output=True,text=True)
        print('Lectura del cgroup visible, no usada como medición aislada del servicio: '+peak.stdout.strip(),flush=True)
    except Exception:
        logs=subprocess.run(DOCKER+['logs','--tail','60',NAME],capture_output=True,text=True)
        print(logs.stdout+logs.stderr,flush=True)
        stats=subprocess.run(DOCKER+['exec',NAME,'python','-c',"from pathlib import Path; print({n:Path('/sys/fs/cgroup/'+n).read_text() for n in ['memory.peak','memory.events','pids.events'] if Path('/sys/fs/cgroup/'+n).exists()})"],capture_output=True,text=True)
        print('Diagnóstico de recursos: '+stats.stdout,flush=True)
        raise
    finally:
        subprocess.run(DOCKER+['stop','--time','40',NAME],check=True,capture_output=True)
        subprocess.run(DOCKER+['rm',NAME],check=True,capture_output=True)


def without_boundary():
    subprocess.run(DOCKER+['run','--detach','--name',NAME,'--user','10000:10000','--network','none','--read-only','--cap-drop','ALL','--memory','512m','--pids-limit','32','--tmpfs','/tmp:rw,size=16m','-e','DATABASE_URL=sqlite:////tmp/fixture.db','-e','KIKI_AUTO_CREATE_SCHEMA=true',IMAGE],check=True,capture_output=True)
    try:
        code="import http.client; from app.services.documental.local_documents import reader_available; c=http.client.HTTPConnection('127.0.0.1',8000); c.request('GET','/health'); assert c.getresponse().status==200; assert reader_available() is False"
        for _ in range(60):
            result=subprocess.run(DOCKER+['exec',NAME,'python','-c',code],capture_output=True)
            if result.returncode==0:break
            time.sleep(.25)
        else:raise AssertionError('Sin chroot debe continuar la API con lector bloqueado')
        print('Sin frontera/root: API anterior disponible y lector bloqueado, sin fallback: PASS',flush=True)
    finally:
        subprocess.run(DOCKER+['stop','--time','40',NAME],check=True,capture_output=True)
        subprocess.run(DOCKER+['rm',NAME],check=True,capture_output=True)


if __name__=='__main__':
    main()
    without_boundary()
