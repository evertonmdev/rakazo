"""Injected failure regressions; not paid-provider E2E."""
import contextlib
import importlib.machinery
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT / 'vendor'))

def runner_module():
    loader = importlib.machinery.SourceFileLoader('failure_runner', str(ROOT / 'rakazo-ultrafast'))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    runner = importlib.util.module_from_spec(spec)
    loader.exec_module(runner)
    return runner

class RunnerFailures(unittest.TestCase):
    def test_serialization_failure_still_emits_one_safe_json_object(self):
        runner = runner_module()
        out = io.StringIO()
        with patch.object(runner, 'run', return_value=({'ok':True, 'value':float('nan')}, 0)), patch.object(sys, 'argv', ['runner', '{}']), contextlib.redirect_stdout(out):
            code = runner.main()
        result = json.loads(out.getvalue())
        self.assertEqual(code, 1)
        self.assertEqual(result['diagnostic']['code'], 'OUTPUT_ENCODING_FAILED')

    def test_cold_visible_chrome_uses_existing_desktop_launcher(self):
        from unittest.mock import Mock
        runner = runner_module()
        page = Mock()
        page.http_get_json.side_effect = OSError('not started')
        with patch('subprocess.Popen') as launch:
            runner.ensure_visible_cdp(page, 9222)
        self.assertEqual(launch.call_args.args[0], ['/usr/local/bin/rakazo-browser', 'about:blank'])
        page.wait_for_cdp.assert_called_once_with(9222, timeout_s=12)

    def test_live_visible_chrome_is_never_relaunched(self):
        from unittest.mock import Mock
        runner = runner_module()
        page = Mock()
        with patch('subprocess.Popen') as launch:
            runner.ensure_visible_cdp(page, 9222)
        launch.assert_not_called()

    def invoke(self, agent_class, payload=None):
        runner = runner_module()
        out = io.StringIO()
        with patch('jev_ultrafast.agent.Agent', agent_class), patch.dict(os.environ, TYPESAFE_API_KEY='fixture', TEXT_MODEL_API_KEY='fixture'), patch.object(sys, 'argv', ['runner', json.dumps(payload or {'url':'https://example.org/', 'goal':'Collect text'})]), contextlib.redirect_stdout(out):
            code = runner.main()
        self.assertNotIn('FIXTURE_SECRET', out.getvalue())
        return code, json.loads(out.getvalue())

    def test_initialization_failure_is_json_not_empty_stdout(self):
        class FailedAgent:
            def __init__(self, *a, **kw):
                print('third party FIXTURE_SECRET')
                raise TimeoutError('FIXTURE_SECRET browser did not initialize')
        code, result = self.invoke(FailedAgent)
        self.assertEqual(code, 1)
        self.assertEqual(result['diagnostic']['phase'], 'initialize')
        self.assertEqual(result['diagnostic']['code'], 'BROWSER_TIMEOUT')

    def test_model_blocked_is_distinct_from_failed_tick_and_retains_observation(self):
        class BlockedAgent:
            def __init__(self, *a, **kw):
                self.state = {'status':'blocked', 'page':{'url':'https://example.org/', 'text':'Useful visible public text'}, 'history':[], 'decisions':[{'operation':'BLOCKED'}], 'evidence':[]}
            def snapshot(self): return dict(self.state)
            def command(self, *a): return self.snapshot()
        code, result = self.invoke(BlockedAgent)
        self.assertEqual(result['stop_reason'], 'model_blocked')
        self.assertEqual(result['decisions'], 1)
        self.assertEqual(result['steps'], 0)
        self.assertIn('Useful visible', result['observation']['text'])
        self.assertNotIn('diagnostic', result)

    def test_tick_failure_retains_evidence_and_phase_without_raw_error(self):
        from jev_ultrafast.diagnostics import OperationFailure
        class FailedAgent:
            def __init__(self, *a, **kw):
                self.state = {'status':'ready','phase':'choose','page':{},'evidence':[{'kind':'copy_link','url':'https://example.org/pin/123'}]}
            def snapshot(self): return dict(self.state)
            def command(self, *a): raise OperationFailure('PROVIDER_HTTP', 'choose', http_status=429)
        code, result = self.invoke(FailedAgent)
        self.assertEqual(result['diagnostic'], {'code':'PROVIDER_HTTP','phase':'choose','http_status':429, 'recovery':'retry_later'})
        self.assertEqual(result['evidence'][0]['url'], 'https://example.org/pin/123')

    def test_terminal_serialization_is_bounded_structured_and_keeps_link(self):
        runner = runner_module()
        result = runner.terminal_result({'status':'done','page':{'text':'é'*12000},'evidence':[{'kind':'extract_text','text':'é'*12000} for _ in range(20)]+[{'kind':'copy_link','url':'https://example.org/pin/123'}]})
        encoded = runner.encode_result(result)
        self.assertLessEqual(len(encoded.encode()), 60000)
        self.assertIn('https://example.org/pin/123', encoded)
        self.assertTrue(json.loads(encoded)['output_truncated'])

class ProviderFailures(unittest.TestCase):
    def test_expired_runner_budget_never_calls_provider(self):
        import jev_ultrafast.model as model
        with patch.object(model, 'RUN_DEADLINE', 1, create=True), patch.object(model.time, 'monotonic', return_value=2), patch.object(model.CLIENT, 'post') as post:
            with self.assertRaises(Exception) as error:
                model.post_json('https://example.org', 'fixture', {})
        self.assertEqual(getattr(error.exception, 'code', None), 'RUNNER_TIME_BUDGET')
        post.assert_not_called()

    def test_authentication_diagnostic_names_correct_credential_store(self):
        from jev_ultrafast.diagnostics import OperationFailure, diagnostic
        detail = diagnostic(OperationFailure('PROVIDER_HTTP', 'provider', http_status=401), 'text')
        self.assertEqual(detail['recovery'], 'configure_text_model_credentials')

    def test_http_timeout_and_invalid_json_have_safe_distinct_diagnostics(self):
        import httpx
        from jev_ultrafast.model import post_json
        for response, expected in [(httpx.Response(401, text='FIXTURE_SECRET'), 'PROVIDER_HTTP'), (httpx.Response(200, text='FIXTURE_SECRET'), 'PROVIDER_INVALID_JSON'), (httpx.ReadTimeout('FIXTURE_SECRET'), 'PROVIDER_TIMEOUT')]:
            with self.subTest(expected=expected), patch('jev_ultrafast.model.CLIENT.post', side_effect=response if isinstance(response, Exception) else None, return_value=response):
                try: post_json('https://example.org', 'fixture', {})
                except Exception as exc:
                    self.assertEqual(getattr(exc, 'code', None), expected)
                    self.assertNotIn('FIXTURE_SECRET', str(exc))
                else: self.fail('expected a classified failure')

if __name__ == '__main__': unittest.main()
