"""Explicit owner configuration; private credentials are read only at admission."""
import copy
from pathlib import Path

from .agents import strict_json
from .evidence import fingerprint
from .individual_capture import safe_directory_path
from .individual_jobs import need
from .individual_remote_capture import load_private_credential, validate_request
from .public_cases import PublicCaseManager, public_policy
from .qloo import Settings
from .remote_pacing import pacing_policy

LIMITS=('case_session_limit','case_write_limit','case_read_limit')
POLICY=('maximum_sessions','maximum_plans','maximum_executions','plans_per_session',
        'executions_per_session','session_hours')


def read_configuration(path):
    path=safe_directory_path(Path(path))
    need(path.is_file() and path.stat().st_size<=100_000,'Configure one bounded owner case configuration file.')
    value=strict_json(path.read_bytes())
    need(set(value)=={'schema_version','request','policy','minimum_model_interval_seconds','http_limits'}
         and type(value['schema_version']) is int and value['schema_version']==1,'Unexpected owner configuration fields.')
    request=validate_request(value['request'])
    policy=value['policy']
    need(isinstance(policy,dict) and all(key in policy for key in POLICY),'Explicit public policy is required.')
    expected=public_policy(**{key:policy[key] for key in POLICY})
    need(fingerprint(expected)==fingerprint(policy),'Public policy must be closed and exact.')
    cadence=pacing_policy(value['minimum_model_interval_seconds'])
    need(cadence['configured'],'Select an explicit remote cadence.')
    limits=value['http_limits']
    need(isinstance(limits,dict) and set(limits)==set(LIMITS)
         and all(type(x) is int and 1<=x<=600 for x in limits.values()),'Select bounded HTTP limits.')
    return {'schema_version':1,'request':request,'policy':copy.deepcopy(expected),
            'minimum_model_interval_seconds':cadence['minimum_interval_seconds'],'http_limits':copy.deepcopy(limits)}


def _private_file(path):
    need(path is not None and Path(path).is_absolute(),'Use an explicit absolute private credential path.')
    checked=safe_directory_path(Path(path))
    need(checked.is_file() and checked.stat().st_size<=100_000,'Private credential file is unavailable or oversized.')
    return checked


def configure_cases(config_file,storage,*,origin,execution_enabled=False,qloo_env=None,model_env=None):
    need(type(execution_enabled) is bool,'Execution requires an explicit boolean.')
    config=read_configuration(config_file)
    need(storage is not None and Path(storage).is_absolute(),'Choose one absolute persistent case storage root.')
    settings_loader=remote_loader=None
    if execution_enabled:
        qloo_path,model_path=_private_file(qloo_env),_private_file(model_env)
        def settings_loader():
            checked=_private_file(qloo_path)
            return Settings.from_environment(checked,use_process_environment=False)
        def remote_loader():
            return load_private_credential(_private_file(model_path))
    manager=PublicCaseManager(storage,config['request'],origin=origin,policy=config['policy'],
        minimum_model_interval_seconds=config['minimum_model_interval_seconds'],
        execution_enabled=execution_enabled,settings_loader=settings_loader,remote_key_loader=remote_loader)
    return manager,config['http_limits']
