"""Standalone proof: audited in a NEW trusted container process, not a subprocess bypass."""
import os
import sys
from .policy import preflight, DATABASE_URL
preflight()
os.environ['DATABASE_URL']='postgresql://blocked.invalid/NEVER'
from app.services.v2_preflight import connect_readonly,audit  # noqa: E402
engine=connect_readonly(DATABASE_URL,'kiki_integration','kiki_integration','/var/run/postgresql')
try:
    result=audit(engine,'kiki_integration','kiki_integration')
    assert not any(result['groups'].values()),result
    assert 'app.database.session' not in sys.modules
    assert 'app.core.config' not in sys.modules
    print('Standalone preflight READ ONLY; no settings or backend engine imported: PASS')
finally:engine.dispose()
