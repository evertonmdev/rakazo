"""Bounded read evidence. Never retain request headers, cookies or POST data."""
import json
import re
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

READ_KINDS = frozenset({'read_url', 'copy_link', 'extract_text', 'inspect_network', 'read_response'})
SECRET = re.compile(r'auth|cookie|token|secret|password|passwd|session|credential|api.?key|signature|csrf|xsrf|jwt|private.?key|client.?key|card.?number|cvv|cvc|ssn|(?:^|[_-])(?:key|code|sid|otp)(?:$|[_-])', re.I)
URL = re.compile(r'https?://[^\s<>"\']+')

class NetworkCapture:
    """Consume CDP events synchronously; raw headers/bodies are never buffered."""
    def __init__(self, session, limit=60):
        self.session, self.limit = session, limit
        self.records = {}
        self.dropped = 0
        self.extra_sensitive = {}

    def read_body(self, rid, call):
        r = self.records.get(rid)
        result = {'request_id':rid, 'url':r.get('url') if r else None}
        if not r or not r.get('finished') or r.get('failed'):
            return {**result, 'omitted':'request unavailable, failed or unfinished'}
        if r.get('sensitive') or r.get('method') != 'GET':
            return {**result, 'omitted':'sensitive or non-GET request'}
        if r.get('size', 100000) > 16384 or 'json' not in r.get('mime', '').lower():
            return {**result, 'omitted':'only small public JSON responses are eligible'}
        try:
            response = call('Network.getResponseBody', requestId=rid)
            body = response.get('body', '')
            if response.get('base64Encoded') or len(body.encode('utf-8')) > 16384:
                return {**result, 'omitted':'encoded or oversized response'}
            data = sanitize(json.loads(body))
            if len(json.dumps(data)) > 6000:
                return {**result, 'omitted':'sanitized JSON exceeds evidence budget'}
            return {**result, 'body':data}
        except (RuntimeError, ValueError, KeyError, TypeError):
            return {**result, 'omitted':'body unavailable or not valid JSON'}

    def event(self, message):
        if message.get('sessionId') != self.session:
            return
        method, p = message.get('method'), message.get('params', {})
        rid = p.get('requestId')
        if not isinstance(rid, str):
            return
        if method in ('Network.requestWillBeSentExtraInfo', 'Network.responseReceivedExtraInfo'):
            sensitive = bool(p.get('associatedCookies')) or any(SECRET.search(k) for k in p.get('headers', {}))
            if sensitive:
                self.extra_sensitive[rid] = True
                if rid in self.records:
                    self.records[rid]['sensitive'] = True
                while len(self.extra_sensitive) > self.limit:
                    del self.extra_sensitive[next(iter(self.extra_sensitive))]
            return
        if method == 'Network.requestWillBeSent':
            req = p.get('request', {})
            url = req.get('url', '')
            old = self.records.get(rid, {})
            sensitive = old.get('sensitive', False) or self.extra_sensitive.get(rid, False) or bool(SECRET.search(url)) or bool(re.search(r'login|signin|oauth|account|payment|checkout|billing|reset', url, re.I)) or any(SECRET.search(k) for k in req.get('headers', {}))
            self.records.pop(rid, None)
            self.records[rid] = {'request_id':rid, 'url':safe_url(url)[:1000], 'method':str(req.get('method', ''))[:16],
                                 'type':str(p.get('type', ''))[:24], 'sensitive':sensitive, 'finished':False}
            while len(self.records) > self.limit:
                del self.records[next(iter(self.records))]
                self.dropped += 1
        elif rid in self.records:
            r = self.records[rid]
            if method == 'Network.responseReceived':
                response = p.get('response', {})
                r.update(status=response.get('status'), mime=str(response.get('mimeType', ''))[:100])
                r['sensitive'] |= any(SECRET.search(k) for k in response.get('headers', {}))
            elif method == 'Network.loadingFinished':
                r.update(finished=True, size=p.get('encodedDataLength', 0))
            elif method == 'Network.loadingFailed':
                r.update(finished=True, failed=True)


def read_page(browser, action, page):
    """Only code-owned operations and observed node IDs; no selectors/JS from the model."""
    kind = action['kind']
    if kind == 'read_url':
        return {'kind':kind, 'url':safe_url(browser.evaluate('location.href'))}
    if kind == 'extract_text':
        text = browser.evaluate('(document.body?.innerText || "").slice(0, 12001)') or ''
        return {'kind':kind, 'url':safe_url(page['url']), 'text':sanitize(text[:12000]), 'truncated':len(text)>12000}
    if kind == 'copy_link':
        node = action['node']
        if type(node) is not int:
            raise ValueError('Invalid observed link')
        href = browser.evaluate(f'window.__jevFast?.nodes.get({node})?.href || null')
        if not href or not href.startswith(('http://', 'https://')):
            raise ValueError('Observed link is no longer an HTTP URL')
        return {'kind':kind, 'url':safe_url(href), 'label':sanitize(action['label'])}
    raise ValueError('Unsupported read action')


def safe_url(value):
    try:
        p = urlsplit(value)
        if p.scheme not in ('http', 'https'):
            return '[unsupported URL]'
        host = p.netloc.rsplit('@', 1)[-1]
        query = urlencode([(k, '[redacted]' if SECRET.search(k) else v) for k, v in parse_qsl(p.query, keep_blank_values=True)])
        path = re.sub(r'(?i)(/(?:reset-password|reset|token|auth|secret|api-key)/)[^/]+', r'\1[redacted]', p.path)
        return urlunsplit((p.scheme, host, path, query, ''))[:4000]
    except ValueError:
        return '[invalid URL]'

def sanitize(value, depth=0):
    if depth > 12:
        return '[depth limit]'
    if isinstance(value, dict):
        return {str(k)[:120]: '[redacted]' if SECRET.search(str(k)) else sanitize(v, depth+1)
                for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [sanitize(v, depth+1) for v in value]
    if isinstance(value, str):
        value = URL.sub(lambda m: safe_url(m[0]), value[:12000])
        value = re.sub(r'(?i)\b(?:bearer|basic)\s+[a-z0-9._~+/=-]+', '[redacted]', value)
        value = re.sub(r'(?i)([\w.-]*(?:token|secret|password|cookie|authorization|api[_-]?key|session[_-]?id)[\w.-]*[\s"\']*[:=]\s*["\']?)[^\s,"\';<>}]+', r'\1[redacted]', value)
        value = re.sub(r'\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b', '[redacted]', value)
    return value
