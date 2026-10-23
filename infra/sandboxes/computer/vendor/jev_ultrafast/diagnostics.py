"""Safe actionable diagnostics: never include exception messages, headers or bodies."""

class OperationFailure(RuntimeError):
    def __init__(self, code, phase, *, http_status=None):
        super().__init__(code)
        self.code, self.phase, self.http_status = code, phase, http_status


def diagnostic(exc, phase):
    if isinstance(exc, OperationFailure):
        result = {'code':exc.code, 'phase':exc.phase if exc.phase != 'provider' else phase}
        if exc.http_status is not None:
            result['http_status'] = exc.http_status
            if exc.http_status in {401, 403}:
                result['recovery'] = 'configure_text_model_credentials' if result['phase'] == 'text' else 'configure_typesafe_credentials'
            elif exc.http_status == 429 or exc.http_status >= 500:
                result['recovery'] = 'retry_later'
        return result
    if isinstance(exc, TimeoutError):
        code = 'BROWSER_TIMEOUT'
    elif isinstance(exc, (ImportError, ModuleNotFoundError)):
        code = 'DEPENDENCY_MISSING'
    elif isinstance(exc, (ValueError, KeyError, TypeError)):
        code = 'INVALID_OPERATION_STATE'
    else:
        code = 'BROWSER_OPERATION_FAILED' if phase in {'initialize', 'observe', 'act'} else 'RUNNER_FAILED'
    return {'code':code, 'phase':phase, 'cause_type':type(exc).__name__}
