"""Owner-selected new repeatable store and provider ledger; legacy store stays immutable."""
from pathlib import Path
import copy
import re

from .agents import strict_json
from .evidence import fingerprint
from .individual_capture import safe_directory_path
from .individual_jobs import need
from .individual_remote_capture import validate_request, load_private_credential
from .public_case_config import LIMITS, _private_file
from .qloo import Settings
from .remote_pacing import pacing_policy
from .repeatable_cases import RepeatableCaseManager, repeatable_policy


def read_configuration(path):
    path=safe_directory_path(Path(path))
    need(path.is_file() and path.stat().st_size<=100_000,'Explicit bounded repeatable configuration required.')
    value=strict_json(path.read_bytes())
    required={'schema_version','admission_mode','request','policy','minimum_model_interval_seconds','http_limits','provider_limits'}
    need(isinstance(value,dict) and set(value)==required and type(value['schema_version']) is int
         and value['schema_version']==2 and value['admission_mode']=='repeatable-v1','Unexpected repeatable configuration.')
    request=validate_request(value['request'])
    policy=value['policy']
    need(isinstance(policy,dict) and policy==repeatable_policy(**{k:policy[k] for k in ('access_until_utc','maximum_queued_jobs')}),
         'Closed repeatable policy required.')
    cadence=pacing_policy(value['minimum_model_interval_seconds']);need(cadence['configured'],'Explicit remote cadence required.')
    limits=value['http_limits']
    need(isinstance(limits,dict) and set(limits)==set(LIMITS)
         and all(type(x) is int and 1<=x<=600 for x in limits.values()),'Bounded HTTP limits required.')
    provider=value['provider_limits']
    need(isinstance(provider,dict) and set(provider)=={'groq','qloo'},'Explicit independent provider windows required.')
    for name,windows in provider.items():
        need(isinstance(windows,list) and 1<=len(windows)<=12,'Provide bounded provider quota windows.')
        names=set()
        for row in windows:
            need(isinstance(row,dict) and set(row)=={'name','capacity','seconds','metric','basis'},'Closed quota window required.')
            need(isinstance(row['name'],str) and re.fullmatch(r'[a-z][a-z0-9_-]{0,63}',row['name'])
                 and row['name'] not in names and len(row['name'])<=64,'Distinct bounded quota window names required.')
            names.add(row['name'])
            need(type(row['capacity']) is int and 1<=row['capacity']<=100_000_000
                 and type(row['seconds']) in (int,float) and 1<=row['seconds']<=366*86400
                 and row['metric'] in ('requests','tokens','input_tokens','output_tokens') and row['basis'] in ('conservative','observed'),
                 'Invalid provider window; quota is not inferred from a plan attempt bound.')
    return {'schema_version':2,'admission_mode':'repeatable-v1','request':request,'policy':copy.deepcopy(policy),
            'minimum_model_interval_seconds':cadence['minimum_interval_seconds'],
            'http_limits':copy.deepcopy(limits),'provider_limits':copy.deepcopy(provider)}


def configure_repeatable_cases(config_file,storage,*,origin,execution_enabled=False,qloo_env=None,model_env=None,
                               legacy_root=None):
    need(type(execution_enabled) is bool,'Execution requires an explicit boolean.')
    config=read_configuration(config_file)
    need(storage is not None and Path(storage).is_absolute(),'Explicit absolute NEW persistent storage root required.')
    root=safe_directory_path(Path(storage))
    from .wide_cinema_tokens import WideHarmonyTokenEstimator
    estimator=WideHarmonyTokenEstimator(Path(__file__).resolve().parents[2]/'assets/tokenizers/o200k_base.tiktoken')
    # Root creation/binding is handled by the manager; scheduler starts only after
    # the new policy has been validated and written in this separate store.
    settings_loader=remote_loader=None
    if execution_enabled:
        qloo_path,model_path=_private_file(qloo_env),_private_file(model_env)
        def settings_loader():return Settings.from_environment(_private_file(qloo_path),use_process_environment=False)
        def remote_loader():return load_private_credential(_private_file(model_path))
    manager=RepeatableCaseManager(root,config['request'],origin=origin,policy=config['policy'],
        minimum_model_interval_seconds=config['minimum_model_interval_seconds'],execution_enabled=False,
        settings_loader=settings_loader,remote_key_loader=remote_loader,legacy_root=legacy_root,
        token_estimator=estimator,_test_autostart=False)
    try:
        from .provider_scheduler import ProviderScheduler, QuotaWindow
        limits={name:tuple(QuotaWindow(**window) for window in windows) for name,windows in config['provider_limits'].items()}
        scheduler=ProviderScheduler(root/'provider-scheduler.sqlite3',limits=limits)
        from .qloo_cache import PrivateQlooCache
        manager.manager.qloo_cache=PrivateQlooCache(root/'private-qloo-cache')
        manager.manager.scheduler=scheduler
        manager.manager.reconcile_terminal_reservations()
        manager.manager.enabled=execution_enabled
        manager.manager.autostart=True
        if execution_enabled:manager.manager._ensure_worker()
    except BaseException:
        manager.close();raise
    return manager,config['http_limits']

# Compatibility entry point used by owner CLI routing.
configure_cases=configure_repeatable_cases
