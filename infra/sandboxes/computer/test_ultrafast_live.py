"""Opt-in real visible-Chrome integration: RAKAZO_ULTRAFAST_LIVE=1 python -m unittest ..."""
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import sys
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = Path(__file__).parent

@unittest.skipUnless(os.environ.get('RAKAZO_ULTRAFAST_LIVE') == '1', 'requires live visible Chrome')
class VisibleReadTests(unittest.TestCase):
    def test_reads_visible_chrome_and_network_without_model(self):
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, format, *args): pass
            def do_GET(self):
                api = self.path.startswith(('/data', '/private'))
                content = (b'{"title":"Fixture network result","access_token":"FIXTURE_SECRET"}' if api else
                    b'<title>Jev fixture</title><h1>Fixture page text</h1><a href="/pin/123?token=FIXTURE_SECRET&q=public">Observed pin</a><script>Promise.all([fetch("/data").then(r=>r.text()),fetch("/private",{headers:{Authorization:"Bearer FIXTURE_SECRET"}}).then(r=>r.text())]).then(()=>document.body.dataset.loaded="yes")</script>')
                self.send_response(200)
                self.send_header('Content-Type', 'application/json' if api else 'text/html')
                self.send_header('Content-Length', str(len(content)))
                self.end_headers()
                self.wfile.write(content)
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        loader = importlib.machinery.SourceFileLoader('ultrafast_runner', str(ROOT / 'rakazo-ultrafast'))
        spec = importlib.util.spec_from_loader(loader.name, loader)
        assert spec is not None
        runner = importlib.util.module_from_spec(spec)
        loader.exec_module(runner)
        sys.path.insert(0, str(ROOT / 'vendor'))
        browser = None
        page_mod = runner.load_page_browser()
        runner.ensure_visible_cdp(page_mod, page_mod.cdp_port())
        client = page_mod.CdpClient(page_mod.discover_ws_url(page_mod.cdp_port()))
        client.connect()
        session = page_mod.attach_page(client)
        previous = client.call('Runtime.evaluate', {'expression':'location.href','returnByValue':True}, session_id=session)['result']['value']
        try:
            url = 'http://127.0.0.1:%d/' % server.server_port
            browser = runner.VisibleBrowser(url)
            deadline = time.monotonic() + 5
            while browser.evaluate('document.body.dataset.loaded') != 'yes':
                if time.monotonic() > deadline: self.fail('fixture fetch did not finish')
                time.sleep(0.02)
            page = browser.observe(screenshot=False)
            self.assertTrue({'read_url','extract_text','inspect_network','copy_link'} <= {a['kind'] for a in page['actions']})
            results = {}
            for kind in ('read_url','copy_link','extract_text','inspect_network'):
                action = next(a for a in page['actions'] if a['kind'] == kind)
                results[kind] = browser.act(action, page)
                page = browser.observe(screenshot=False)
            self.assertEqual(results['read_url']['url'], url)
            self.assertIn('/pin/123', results['copy_link']['url'])
            self.assertIn('Fixture page text', results['extract_text']['text'])
            self.assertTrue(any(r['url'] == url for r in results['inspect_network']['requests']))
            action = next(a for a in page['actions'] if a['kind'] == 'read_response' and '/data' in a['label'])
            results['read_response'] = browser.act(action, page)
            self.assertEqual(results['read_response']['body']['title'], 'Fixture network result')
            private_action = next(a for a in page['actions'] if a['kind'] == 'read_response' and '/private' in a['label'])
            results['private_response'] = browser.act(private_action, page)
            self.assertIn('omitted', results['private_response'])
            self.assertNotIn('FIXTURE_SECRET', json.dumps(results))
            with self.assertRaises(ValueError):
                browser.act({'id':'unobserved', 'kind':'read_response','request_id':'arbitrary'}, page)
            terminal = runner.terminal_result({'status':'done','page':page,'evidence':list(results.values())})
            self.assertEqual(len(terminal['evidence']), 6)
            self.assertIn('Fixture network result', json.dumps(terminal))
            # Real DOM node guard rejects a changed link, never copying a stale href.
            browser.evaluate('document.querySelector("a").href="/different"')
            from jev_ultrafast.browser import StalePage
            with self.assertRaises(StalePage):
                browser.act(next(a for a in page['actions'] if a['kind'] == 'copy_link'), page)
            print('LIVE_EVIDENCE=' + json.dumps(results))
        finally:
            if browser: browser.close()
            client.call('Page.navigate', {'url':previous}, session_id=session)
            client.close()
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

if __name__ == '__main__': unittest.main()
