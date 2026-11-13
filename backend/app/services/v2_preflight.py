"""Explicit READ ONLY schema audit. No app settings, session engine or user rows.

Default: Unix socket of an explicitly named isolated database/role. Remote mode
requires a separate opt-in and verify-full. No endpoint runs this automatically.
"""
import argparse
import hashlib
import json
import os
import sys


def inspect_schema(connection, schema="public"):
    from sqlalchemy import inspect
    from app.database.models import Base
    from app.services.documental.storage import ResearchBase
    from app.services.editorial_batches.storage import EditorialBase
    inspector=inspect(connection)
    tables=set(inspector.get_table_names(schema=schema))
    result={}
    essential={
        'kiki_evidence_documents':{'kiki_evidence_documents_variant'},
        'kiki_editorial_batches':{'kiki_editorial_batches_created','kiki_editorial_claimable'},
        'kiki_editorial_batch_items':{'kiki_editorial_items_state','kiki_editorial_active_identity'},
    }
    for name,metadata in [('core',Base.metadata),('documents',ResearchBase.metadata),('batches',EditorialBase.metadata)]:
        issues=[]
        for table in metadata.sorted_tables:
            if table.name not in tables:
                issues.append({'table':table.name,'problem':'MISSING_TABLE'});continue
            columns={c['name']:c for c in inspector.get_columns(table.name,schema=schema)}
            for expected in table.columns:
                actual=columns.get(expected.name)
                prefix={'table':table.name,'column':expected.name}
                if actual is None:issues.append({**prefix,'problem':'MISSING_COLUMN'});continue
                actual_type=str(actual['type'].compile(dialect=connection.dialect)).upper()
                expected_type=str(expected.type.compile(dialect=connection.dialect)).upper()
                if actual_type!=expected_type:
                    issues.append({**prefix,'problem':'TYPE_REVIEW','expected':expected_type,'actual':actual_type})
                if actual['nullable']!=expected.nullable:
                    issues.append({**prefix,'problem':'NULLABILITY_REVIEW'})
            pk=set(inspector.get_pk_constraint(table.name,schema=schema)['constrained_columns'])
            if pk!={c.name for c in table.primary_key.columns}:
                issues.append({'table':table.name,'problem':'PRIMARY_KEY_REVIEW'})
            from sqlalchemy import UniqueConstraint
            unique={tuple(sorted(c['column_names'])) for c in inspector.get_unique_constraints(table.name,schema=schema)}
            for constraint in table.constraints:
                if isinstance(constraint,UniqueConstraint) and tuple(sorted(c.name for c in constraint.columns)) not in unique:
                    issues.append({'table':table.name,'problem':'UNIQUE_REVIEW','columns':sorted(c.name for c in constraint.columns)})
            foreign=inspector.get_foreign_keys(table.name,schema=schema)
            for constraint in table.foreign_key_constraints:
                match=any(f['constrained_columns']==list(constraint.column_keys) and f['referred_table']==constraint.referred_table.name and f['referred_columns']==[e.column.name for e in constraint.elements] and (f.get('options',{}).get('ondelete') or '')==(constraint.ondelete or '') for f in foreign)
                if not match:issues.append({'table':table.name,'problem':'FOREIGN_KEY_REVIEW'})
            indices={i['name'] for i in inspector.get_indexes(table.name,schema=schema)}
            for index in sorted((essential.get(table.name,set())|({i.name for i in table.indexes} if name == "core" else set()))-indices):issues.append({'table':table.name,'problem':'MISSING_INDEX','index':index})
        result[name]=issues
    return {'contract':'kiki-schema-preflight-v1','groups':result,'findings_digest':hashlib.sha256(json.dumps(result,sort_keys=True).encode()).hexdigest(),'reads_user_rows':False}


def connect_readonly(dsn, expected_database, expected_user, expected_host, expected_port=5432, permit_remote=False):
    from psycopg.conninfo import conninfo_to_dict
    from sqlalchemy import create_engine, URL
    from sqlalchemy.pool import NullPool
    params=conninfo_to_dict(dsn.replace('postgresql+psycopg://','postgresql://',1))
    if set(params)-{'host','port','dbname','user','password','sslmode','sslrootcert'}:
        raise ValueError('DSN contiene parámetros no admitidos; no se usa service ni fallback.')
    if not all((expected_database,expected_user,expected_host)) or any(params.get(k)!=v for k,v in [('dbname',expected_database),('user',expected_user),('host',expected_host)]) or int(params.get('port',5432))!=expected_port:
        raise ValueError('Identidad de destino no coincide; conexión bloqueada antes de abrir sockets.')
    local=expected_host.startswith('/')
    if not local and (not permit_remote or params.get('sslmode')!='verify-full' or not params.get('sslrootcert')):
        raise ValueError('Destino remoto requiere autorización separada y TLS verify-full con CA explícita.')
    url=URL.create('postgresql+psycopg',username=expected_user,password=params.get('password',''),host=expected_host,port=expected_port,database=expected_database)
    engine=create_engine(url,poolclass=NullPool,hide_parameters=True,connect_args={
        'connect_timeout':5,'options':'-c default_transaction_read_only=on -c statement_timeout=10000 -c lock_timeout=1000',
        'passfile':'/dev/null','sslcert':'','sslkey':'',
        'sslmode':'disable' if local else 'verify-full','sslrootcert':params.get('sslrootcert',''),
    })
    return engine


def audit(engine,expected_database,expected_user):
    with engine.connect() as connection:
        with connection.begin():
            connection.exec_driver_sql('SET TRANSACTION READ ONLY')
            identity=connection.exec_driver_sql('SELECT current_database(), current_user').one()
            if tuple(identity)!=(expected_database,expected_user) or connection.exec_driver_sql('SHOW transaction_read_only').scalar()!='on':
                raise ValueError('Identidad o modo de transacción no verificado.')
            result=inspect_schema(connection)
            result['transaction_read_only']=True
            return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dsn-env',default='KIKI_PREFLIGHT_DSN')
    parser.add_argument('--expected-database',required=True)
    parser.add_argument('--expected-user',required=True)
    parser.add_argument('--expected-host',required=True)
    parser.add_argument('--expected-port',type=int,default=5432)
    parser.add_argument('--permit-remote-read',action='store_true')
    parser.add_argument('--require',default='core')
    args=parser.parse_args()
    engine=None
    try:
        required=args.require.split(',')
        if not required or set(required)-{'core','documents','batches'}:raise ValueError('Grupos requeridos inválidos.')
        dsn=os.environ.get(args.dsn_env)
        if not dsn:raise ValueError('DSN explícito ausente; no se carga .env ni DATABASE_URL.')
        engine=connect_readonly(dsn,args.expected_database,args.expected_user,args.expected_host,args.expected_port,args.permit_remote_read)
        result=audit(engine,args.expected_database,args.expected_user)
        print(json.dumps(result,ensure_ascii=False,sort_keys=True))
        return 0 if all(not result['groups'][group] for group in required) else 3
    except Exception as exc:
        # libpq/SQLAlchemy errors may contain DSNs; never echo their values.
        print(json.dumps({'error':'PREFLIGHT_BLOCKED','type':type(exc).__name__}),file=sys.stderr)
        return 2
    finally:
        if engine:engine.dispose()


if __name__=='__main__':raise SystemExit(main())
