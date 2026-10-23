"""Stdlib regressions for typed, read-only Jev evidence."""
import json
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).with_name('vendor')))

class SafetyTests(unittest.TestCase):
    def test_sanitizing_model_state_preserves_all_typed_choice_identifiers(self):
        from jev_ultrafast.evidence import sanitize
        criteria = {str(i):'Observed element' for i in range(250)}
        self.assertEqual(set(sanitize(criteria)), set(criteria))
        self.assertEqual(len(sanitize(list(range(250)))), 250)

    def test_oauth_codes_financial_fields_and_token_paths_are_redacted(self):
        from jev_ultrafast.evidence import sanitize
        result = sanitize({'url':'https://example.org/reset-password/SECRET?code=SECRET&key=SECRET&q=public', 'card_number':'SECRET', 'cvv':'SECRET'})
        self.assertNotIn('SECRET', json.dumps(result))
        self.assertIn('q=public', result['url'])

    def test_credentials_removed_recursively_and_from_urls(self):
        from jev_ultrafast.evidence import sanitize
        result = sanitize({'url':'https://user:pass@example.org/p?q=cat&access_token=SECRET#token=SECRET',
                           'Authorization':'Bearer SECRET', 'nested':{'session_id':'SECRET','title':'Public result'}})
        self.assertNotIn('SECRET', json.dumps(result))
        self.assertNotIn('user:pass', json.dumps(result))
        self.assertIn('q=cat', result['url'])
        self.assertEqual(result['nested']['title'], 'Public result')

class NetworkTests(unittest.TestCase):
    def test_capture_is_bounded_session_scoped_and_redacts_before_retaining(self):
        from jev_ultrafast.evidence import NetworkCapture
        cap = NetworkCapture('s', limit=2)
        cap.event({'sessionId':'other','method':'Network.requestWillBeSent','params':{'requestId':'x','request':{'url':'https://example.org'}}})
        self.assertEqual(cap.records, {})
        for i in range(4):
            cap.event({'sessionId':'s','method':'Network.requestWillBeSent','params':{'requestId':str(i),'type':'Fetch','request':{'url':'https://example.org/api?token=SECRET','method':'GET','headers':{'Cookie':'SECRET'},'postData':'SECRET'}}})
        self.assertEqual(len(cap.records), 2)
        self.assertNotIn('SECRET', json.dumps(cap.records))
        self.assertTrue(cap.records['3']['sensitive'])

    def test_extra_info_credentials_disable_body_reads_without_retaining_values(self):
        from jev_ultrafast.evidence import NetworkCapture
        for before in (True, False):
            cap = NetworkCapture('s')
            extra = {'sessionId':'s','method':'Network.requestWillBeSentExtraInfo','params':{'requestId':'1','headers':{'Cookie':'SECRET'}}}
            request = {'sessionId':'s','method':'Network.requestWillBeSent','params':{'requestId':'1','request':{'url':'https://example.org/data','method':'GET'}}}
            for event in ([extra, request] if before else [request, extra]): cap.event(event)
            self.assertTrue(cap.records['1']['sensitive'])
            self.assertNotIn('SECRET', repr(cap.__dict__))

    def test_only_finished_small_public_json_bodies_are_read(self):
        from jev_ultrafast.evidence import NetworkCapture
        cap = NetworkCapture('s')
        cap.records['1'] = dict(request_id='1', url='https://example.org/data', method='GET', mime='application/json', finished=True, size=80, sensitive=False)
        calls = []
        def call(method, **params):
            calls.append((method, params))
            return {'body':'{"title":"Public result", "access_token":"SECRET"}', 'base64Encoded':False}
        result = cap.read_body('1', call)
        self.assertEqual(result['body']['title'], 'Public result')
        self.assertNotIn('SECRET', json.dumps(result))
        for change in ({'sensitive':True}, {'size':100000}, {'mime':'text/html'}, {'finished':False}, {'method':'POST'}):
            original = dict(cap.records['1'])
            cap.records['1'].update(change)
            calls.clear()
            self.assertIn('omitted', cap.read_body('1', call))
            self.assertEqual(calls, [])
            cap.records['1'] = original
        self.assertIn('omitted', cap.read_body('missing', call))

class AgentEvidenceTests(unittest.TestCase):
    def test_read_results_survive_three_nonmutating_steps_and_are_returned(self):
        from unittest.mock import patch
        from jev_ultrafast.agent import Agent
        actions = [{'id':k, 'kind':k, 'label':k} for k in ('read_url','extract_text','inspect_network')]
        page = dict(actions=actions, url='https://example.org/', title='Fixture', text='Public', fingerprint='stable')
        class FixtureBrowser:
            def __init__(self, url): pass
            def observe(self, **kw): return dict(page)
            def fresh(self, *args): return True
            def act(self, action, page, text=None): return {'kind':action['kind'], 'text':'Collected public evidence'}
            def close(self): pass
        with patch('jev_ultrafast.agent.Browser', FixtureBrowser):
            agent = Agent(page['url'], 'Read URL, text and network')
            for action in actions:
                agent.state['started_at'] = __import__('time').perf_counter()
                agent.state['decision'] = dict(choice=action['id'], probabilities={action['id']:1}, confidence=1, latency_ms=0, operation=action['id'], target=None, usage={})
                last = agent.command('act', {'fingerprint':'stable'})
            self.assertEqual(last['status'], 'ready')
            self.assertEqual(len(last['evidence']), 3)
            self.assertEqual(last['page']['evidence'], last['evidence'])

class ModelEvidenceTests(unittest.TestCase):
    def test_typed_link_response_targets_and_evidence_reach_model(self):
        from unittest.mock import patch
        from jev_ultrafast.model import choose
        actions = [dict(id='link',kind='copy_link',node=1,label='Observed pin'), dict(id='body',kind='read_response',request_id='r',label='Public JSON')]
        page = dict(actions=actions,url='https://example.org/?token=SECRET',title='Public',text='Public',evidence=[{'kind':'read_url','url':'https://example.org/pin/123'}])
        def transport(url, key, body):
            self.assertIn('COPY_LINK', body['questions']['operation']['criteria'])
            self.assertIn('READ_RESPONSE', body['questions']['operation']['criteria'])
            self.assertEqual(body['state']['collected_evidence'], page['evidence'])
            self.assertNotIn('SECRET', json.dumps(body))
            def answer(criteria, chosen):
                return dict(choice=chosen, confidence=1, probabilities={k:int(k==chosen) for k in criteria})
            return dict(model='test-boundary',answers={'operation':answer(body['questions']['operation']['criteria'],'COPY_LINK'), 'copy_link_target':answer(body['questions']['copy_link_target']['criteria'],'1')})
        with patch.dict('os.environ', TYPESAFE_API_KEY='test-boundary'), patch('jev_ultrafast.model.post_json', transport):
            self.assertEqual(choose(page,'Collect URL',[])['choice'], 'link')

class RunnerResultTests(unittest.TestCase):
    def test_terminal_result_contains_sanitized_evidence_even_when_blocked(self):
        import importlib.machinery
        import importlib.util
        loader = importlib.machinery.SourceFileLoader('runner_result_test', str(Path(__file__).with_name('rakazo-ultrafast')))
        spec = importlib.util.spec_from_loader(loader.name, loader)
        runner = importlib.util.module_from_spec(spec)
        loader.exec_module(runner)
        last = dict(status='blocked', page={'url':'https://example.org/?token=SECRET','title':'Public'}, evidence=[{'kind':'extract_text','text':'Collected public content'}], evidence_dropped=2, history=[{}])
        result = runner.terminal_result(last)
        self.assertEqual(result['evidence'], last['evidence'])
        self.assertEqual(result['evidence_dropped'], 2)
        self.assertFalse(result['ok'])
        self.assertNotIn('SECRET', json.dumps(result))

if __name__ == '__main__': unittest.main()
