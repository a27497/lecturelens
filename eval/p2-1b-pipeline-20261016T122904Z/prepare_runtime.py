"""One-time isolated schema preparation; no provider calls and no container operations."""
import hashlib
import json
import subprocess
from runtime_support import *


def command(env, mode):
    return ['java', '-Djdk.httpclient.HttpClient.log=', '-Djava.io.tmpdir='+str(PRIVATE/'tmp'),
            '-Dp21.private='+str(PRIVATE), '-cp',
            ':'.join(str(PRIVATE/p) for p in ('runtime/extra','runtime/BOOT-INF/classes','runtime/BOOT-INF/lib/*')),
            'com.example.courselingo.systemmodel.P21Bootstrap', mode]


def main():
    env=deployment()
    guard()
    assert guard()['headroom_below_85_bytes'] >= 2**31
    redis_empty(env)
    assert hashlib.file_digest(JAR.open('rb'),'sha256').hexdigest()==json.loads((PUBLIC/'candidate-artifact.json').read_text())['jar_sha256']
    (PRIVATE/'tmp').mkdir(exist_ok=True)
    source=json.loads((ROOT/'eval/baseline-asr-20261015/assets.lock.json').read_text())['sources']
    for item in source:
        assert hashlib.file_digest((ROOT/item['evaluation_video_file']).open('rb'),'sha256').hexdigest()==item['evaluation_video_sha256']
    for mode in ['selftest','preflight']:
        args=command(env,mode)
        if mode=='preflight':args+=['--spring.config.additional-location=file:/home/dev/projects/lecturelens-asr-b/.data/asr-b-deploy/asr-bailian.yml']
        r=subprocess.run(args,env=env,text=True,capture_output=True,timeout=30)
        (PRIVATE/(mode+'-final.log')).write_text(r.stdout+r.stderr)
        assert r.returncode==0, mode+' failed (private log)'
    conn=db(env)
    assert not query(conn,'SELECT SCHEMA_NAME FROM information_schema.schemata WHERE SCHEMA_NAME=%s',(SCHEMA,)), 'Schema already exists; never overwrite'
    query(conn,f'CREATE DATABASE `{SCHEMA}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci')
    # Add privileges only for the new schema, preserving all existing grants.
    for account in query(conn,'SELECT User,Host FROM mysql.user WHERE User=%s',(env['MYSQL_USERNAME'],)):
        query(conn,f'GRANT ALL PRIVILEGES ON `{SCHEMA}`.* TO %s@%s',(account['User'],account['Host']))
    migration_env=isolated(env)
    migration_env.update(MYSQL_USERNAME='root',MYSQL_PASSWORD=env['MYSQL_ROOT_PASSWORD'])
    r=subprocess.run(command(env,'migrate'),env=migration_env,capture_output=True,text=True,timeout=60)
    (PRIVATE/'migration.log').write_text(r.stdout+r.stderr)
    assert r.returncode==0,'migration failed (private log)'
    for table in ['system_model_config_version','system_model_provider','system_model','system_model_binding']:
        columns=[r['COLUMN_NAME'] for r in query(conn,'SELECT COLUMN_NAME FROM information_schema.columns WHERE table_schema=%s AND table_name=%s ORDER BY ORDINAL_POSITION',(SCHEMA,table))]
        cols=','.join('`'+col+'`' for col in columns)
        where=' WHERE version>0 AND version<=10 ORDER BY version' if table=='system_model_config_version' else ''
        query(conn,f'INSERT INTO `{SCHEMA}`.`{table}` ({cols}) SELECT {cols} FROM courselingo.`{table}`'+where)
    query(conn,f'UPDATE `{SCHEMA}`.system_model_config_state SET current_version=10 WHERE id=1')
    query(conn,f"INSERT INTO `{SCHEMA}`.user_account(id,email,password_hash,status,role) VALUES(9,'p21-eval@localhost.invalid','DISABLED_PASSWORD_LOGIN','ACTIVE','ADMIN')")
    refs=[]
    for item in source:
        upload=query(conn,"SELECT id FROM courselingo.upload_session WHERE user_id=9 AND size_bytes=%s AND filename=%s AND status='STORED' ORDER BY created_at DESC LIMIT 1",(item['evaluation_video_bytes'],Path(item['evaluation_video_file']).name))
        assert len(upload)==1
        uid=upload[0]['id']
        # Database-internal copy preserves the authorized existing raw-object reference.
        columns=[r['COLUMN_NAME'] for r in query(conn,'SELECT COLUMN_NAME FROM information_schema.columns WHERE table_schema=%s AND table_name=\'upload_session\' ORDER BY ORDINAL_POSITION',(SCHEMA,))]
        cols=','.join('`'+col+'`' for col in columns)
        query(conn,f'INSERT INTO `{SCHEMA}`.upload_session ({cols}) SELECT {cols} FROM courselingo.upload_session WHERE id=%s AND user_id=9',(uid,))
        refs.append(dict(source_id=item['id'],upload_id=uid,source_sha256=item['evaluation_video_sha256']))
    save(PRIVATE/'media-references.json',refs)
    save(PUBLIC/'runtime-preparation.json',dict(completed_at_utc=utc(),schema=SCHEMA,migration_count=len(query(conn,f'SELECT version FROM `{SCHEMA}`.flyway_schema_history WHERE success=1')),version=10,environment_fingerprint_equal=True,media=refs,redis_database=15,redis_preflight_empty=True,provider_calls=0,disk=guard(),launcher_sha256=hashlib.sha256((PUBLIC/'runtime/P21Bootstrap.java').read_bytes()).hexdigest()))
    print('P21_PREPARATION_PASS',flush=True)


if __name__=='__main__':
    main()
