"""Root-only launch boundary. No backend imports, environment secrets or engine."""
import os
import sys

if os.getuid() != 0:
    raise SystemExit('El lector requiere la frontera chroot; no hay fallback inseguro.')
os.chroot('/opt/kiki-reader')
os.chdir('/')
os.setgroups([])
os.setgid(10000)
os.setuid(10001)
sys.path = ['/usr/local/lib/python3.12/site-packages','/usr/local/lib/python3.12','/usr/local/lib/python3.12/lib-dynload']
from document_reader import worker  # noqa: E402
worker.SOCKET='/run/parser.sock'
worker.serve(kernel_guard=True)
