"""Closed private diagnostics; never store arbitrary HTTP error contents."""
import copy

from .agents import strict_json

MAX_ERROR_BYTES = 8192
ERROR_TYPES = frozenset(('invalid_request_error','server_error','validation_error','api_error'))
ERROR_CODES = frozenset(('json_validate_failed','tool_use_failed','model_not_found',
    'invalid_request_error','context_length_exceeded','invalid_json_schema',
    'json_schema_validation_failed','invalid_schema','invalid_parameter','unsupported_model','model_error'))
CONTRACT = {'schema_version':1,'request_receipt':'discovery-prepared-request-v1',
            'failure_receipt':'discovery-http-enums-v1','maximum_error_body_bytes':MAX_ERROR_BYTES,
            'raw_message_or_generation_recorded':False,'external_dispatch_attested':False}


def http_diagnostic(error):
    """A malformed/large/unreadable body must not hide its known HTTP status."""
    value = {'schema_version':1,'http_status':error.code,
             'provider_error_type':None,'provider_error_code':None}
    try:
        raw = error.read(MAX_ERROR_BYTES+1)
        if type(raw) is bytes and len(raw) <= MAX_ERROR_BYTES:
            body = strict_json(raw)
            detail = body.get('error') if type(body) is dict else None
            if type(detail) is dict:
                for key,allowed in (('type',ERROR_TYPES),('code',ERROR_CODES)):
                    token = detail.get(key)
                    if type(token) is str and token in allowed:
                        value['provider_error_'+key] = token
    except Exception:
        pass  # The original known status remains available; no body is kept.
    finally:
        try: error.close()
        except Exception: pass
    return value


def closed_http(value):
    """Reject foreign exception attributes rather than recording their text."""
    if not (type(value) is dict and set(value) == {'schema_version','http_status',
        'provider_error_type','provider_error_code'} and type(value['schema_version']) is int
        and value['schema_version'] == 1 and type(value['http_status']) is int
        and 100 <= value['http_status'] <= 599):
        return None
    for key,allowed in (('provider_error_type',ERROR_TYPES),('provider_error_code',ERROR_CODES)):
        if value[key] is not None and not (type(value[key]) is str and value[key] in allowed):
            return None
    return copy.deepcopy(value)
