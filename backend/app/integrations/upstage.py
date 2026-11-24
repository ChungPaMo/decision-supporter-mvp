"""Upstage transport for explicitly approved synthetic review inputs."""
from base64 import b64encode
from dataclasses import dataclass
from hashlib import sha256
import json
import logging
import re
from time import monotonic
from typing import Literal, Protocol
from uuid import uuid4

import httpx

from app.config import Settings
from contracts.interfaces.ai_ingestion import ProviderUsage, ReviewRun
from contracts.mapping_review import SOLAR_PREVIEW, solar_chat_payload, solar_responses_payload, strict_json


LOGGER = logging.getLogger(__name__)
BASE_URL = 'https://api.upstage.ai/v1'
MAX_DOCUMENT_PAGES = 100
Capability = Literal['chat', 'embedding', 'parse', 'extract', 'classify', 'ocr']
FLAGS = {'chat': 'ai_mapping_enabled', 'embedding': 'ai_embedding_enabled', 'parse': 'document_parse_enabled',
         'extract': 'information_extract_enabled', 'classify': 'document_classify_enabled', 'ocr': 'document_ocr_enabled'}
MODELS = {'chat': r'solar-(?:mini-?4|pro-?4)(?:-\d{6})?|solar-mini-4-5-preview',
          'embedding': r'solar-embedding-2-(?:query|passage)', 'parse': r'document-parse(?:-\d{6})?',
          'extract': r'information-extract(?:-\d{6})?', 'classify': r'document-classify(?:-\d{6})?', 'ocr': r'ocr'}
MIME = {'xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 'pdf': 'application/pdf',
        'png': 'image/png', 'jpg': 'image/jpeg'}
SIGNATURE = {'xlsx': b'PK\x03\x04', 'pdf': b'%PDF-', 'png': b'\x89PNG\r\n\x1a\n', 'jpg': b'\xff\xd8\xff'}


class ProviderError(Exception):
    def __init__(self, code, *, request_id=None, retry_after=None):
        super().__init__(code)
        self.code = code
        self.request_id = request_id
        self.retry_after = retry_after


@dataclass(frozen=True)
class ApprovedSource:
    dataset_id: str
    source_sha256: str


def check_permission(settings: Settings, capability: Capability, source: ApprovedSource, *, requested: bool):
    if not settings.upstage_api_enabled or not getattr(settings, FLAGS[capability]):
        raise ProviderError('AI_DISABLED')
    if not requested or not settings.ai_external_data_allowed:
        raise ProviderError('EXTERNAL_TRANSFER_NOT_APPROVED')
    if source.source_sha256 not in settings.ai_external_synthetic_sources.get(source.dataset_id, ()):
        raise ProviderError('SOURCE_NOT_APPROVED')
    key = settings.upstage_api_key.get_secret_value() if settings.upstage_api_key else ''
    if not re.fullmatch(r'[\x21-\x7e]+', key):
        raise ProviderError('UPSTAGE_KEY_MISSING')
    return key


@dataclass(frozen=True)
class CostRequest:
    request_id: str
    capability: Capability
    model: str
    input_bytes: int
    max_output_tokens: int | None
    max_pages: int | None
    mode: str | None


class CostTracker(Protocol):
    def reserve(self, request: CostRequest) -> bool:
        """Atomically reserve maximum allowed usage; False denies the call."""
        ...

    def complete(self, request: CostRequest, usage: ProviderUsage | None, outcome: str) -> None:
        """Record usage; retain unverified reservations even on an HTTP error."""
        ...


@dataclass(frozen=True)
class ProviderResult:
    body: dict
    run: ReviewRun
    endpoint: str


def usage_of(body):
    usage = body.get('usage')
    usage = usage if isinstance(usage, dict) else {}
    metadata = body.get('metadata')
    pages = usage.get('pages')
    if pages is None and isinstance(metadata, dict):
        pages = metadata.get('pages')

    def count(value):
        return value if type(value) is int and 0 <= value < 2**31 else None

    return ProviderUsage(input_tokens=count(usage.get('prompt_tokens', usage.get('input_tokens'))),
                         output_tokens=count(usage.get('completion_tokens', usage.get('output_tokens'))), pages=count(pages))


def parse_usage(body, usage, mode):
    data = body.get('usage')
    if not isinstance(data, dict) or not 1 <= (usage.pages or 0) <= MAX_DOCUMENT_PAGES:
        raise ProviderError('UPSTAGE_RESPONSE_FORMAT')
    groups = [data.get('standard'), data.get('enhanced')]
    if groups == [None, None] and mode != 'auto':
        return usage
    if any(not isinstance(group, list) or any(type(page) is not int for page in group) for group in groups):
        raise ProviderError('UPSTAGE_RESPONSE_FORMAT')
    standard, enhanced = groups
    pages = standard + enhanced
    if (len(pages) != usage.pages or set(pages) != set(range(1, usage.pages + 1))
            or (mode == 'standard' and enhanced) or (mode == 'enhanced' and standard)):
        raise ProviderError('UPSTAGE_RESPONSE_FORMAT')
    return usage.model_copy(update={'standard_pages': len(standard), 'enhanced_pages': len(enhanced)})


def encoded(payload):
    return json.dumps(payload, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode('utf-8')


def model_id(capability, model):
    if not re.fullmatch(MODELS[capability], model):
        raise ProviderError('UNSUPPORTED_MODEL')
    return model


def canonical_model(model):
    return model.replace('solar-mini-4', 'solar-mini4').replace('solar-pro-4', 'solar-pro4')


def http_error(response):
    code = {400: 'UPSTAGE_BAD_REQUEST', 401: 'UPSTAGE_AUTHENTICATION', 403: 'UPSTAGE_AUTHENTICATION',
            413: 'UPSTAGE_INPUT_LIMIT', 422: 'UPSTAGE_BAD_REQUEST', 429: 'UPSTAGE_RATE_LIMIT'}.get(response.status_code)
    retry = response.headers.get('retry-after', '')
    return ProviderError(code or 'UPSTAGE_HTTP_ERROR',
                         retry_after=min(int(retry), 3600) if response.status_code == 429 and re.fullmatch(r'[0-9]{1,8}', retry) else None)


def extraction_fields(schema):
    """The supported subset is a root object with one array of flat typed row objects."""
    try:
        root = schema['properties']
        rows = root['rows']
        row = rows['items']
        fields = row['properties']
        rules = {'type', 'properties', 'required', 'additionalProperties'}
        if (schema['type'] != 'object' or set(root) != {'rows'} or set(schema) - rules
                or rows['type'] != 'array' or set(rows) - {'type', 'items', 'description'}
                or row['type'] != 'object' or set(row) - rules or not 1 <= len(fields) <= 64
                or len(encoded(schema)) > 15000):
            raise ValueError
        for key, spec in fields.items():
            if (not re.fullmatch(r'[a-z][a-z0-9_]{0,63}', key) or set(spec) - {'type', 'description'}
                    or spec['type'] not in ('string', 'integer', 'number', 'boolean')
                    or ('description' in spec and not isinstance(spec['description'], str))):
                raise ValueError
        required = row.get('required', [])
        if not isinstance(required, list) or len(required) != len(set(required)) or set(required) - fields.keys():
            raise ValueError
        if (schema.get('required', ['rows']) != ['rows'] or schema.get('additionalProperties', False) is not False
                or row.get('additionalProperties', False) is not False):
            raise ValueError
        return {key: spec['type'] for key, spec in fields.items()}, set(required)
    except (ValueError, TypeError, KeyError, AttributeError, RecursionError):
        raise ProviderError('UNSUPPORTED_SCHEMA') from None


class UpstageClient:
    def __init__(self, settings: Settings, tracker: CostTracker | None = None, *, transport: httpx.BaseTransport | None = None):
        self.settings = settings
        self.tracker = tracker
        self.transport = transport

    def _send(self, capability, source, requested, model, endpoint, data, *, mime='application/json',
              max_tokens=None, max_pages=None, mode=None):
        key = check_permission(self.settings, capability, source, requested=requested)
        model_id(capability, model)
        cap = self.settings.ai_mapping_max_input_bytes if capability in ('chat', 'embedding') else self.settings.upstage_document_max_input_bytes
        if len(data) > cap:
            raise ProviderError('UPSTAGE_INPUT_LIMIT')
        request_id = uuid4().hex
        reservation = CostRequest(request_id, capability, model, len(data), max_tokens, max_pages, mode)
        try:
            permitted = self.tracker is not None and self.tracker.reserve(reservation)
        except Exception:
            raise ProviderError('COST_POLICY_UNAVAILABLE') from None
        if not permitted:
            raise ProviderError('COST_POLICY_REQUIRED')

        usage, outcome = None, 'UPSTAGE_NETWORK'
        started = monotonic()
        try:
            with httpx.Client(timeout=self.settings.ai_mapping_timeout_seconds, trust_env=False, follow_redirects=False,
                              transport=self.transport) as client:
                with client.stream('POST', BASE_URL + endpoint, content=data, headers={
                    'Authorization': 'Bearer ' + key, 'Content-Type': mime, 'Accept-Encoding': 'identity',
                    'X-Request-ID': request_id,
                }) as response:
                    if not response.is_success:
                        raise http_error(response)
                    if response.headers.get('content-encoding', 'identity').lower() != 'identity':
                        raise ProviderError('UPSTAGE_RESPONSE_FORMAT')
                    limit = self.settings.upstage_max_response_bytes
                    content_length = response.headers.get('content-length', '')
                    if content_length.isdecimal() and (len(content_length) > 12 or int(content_length) > limit):
                        raise ProviderError('UPSTAGE_RESPONSE_LIMIT')
                    buffer = bytearray()
                    for chunk in response.iter_bytes():
                        if monotonic() - started > self.settings.ai_mapping_timeout_seconds:
                            raise ProviderError('UPSTAGE_TIMEOUT')
                        if len(buffer) + len(chunk) > limit:
                            raise ProviderError('UPSTAGE_RESPONSE_LIMIT')
                        buffer.extend(chunk)
            try:
                body = strict_json(buffer)
                if not isinstance(body, dict):
                    raise ValueError
            except (ValueError, RecursionError):
                raise ProviderError('UPSTAGE_RESPONSE_FORMAT') from None
            usage = usage_of(body)
            if max_pages is not None and usage.pages is not None and not 1 <= usage.pages <= max_pages:
                raise ProviderError('UPSTAGE_RESPONSE_FORMAT')
            if capability == 'parse':
                usage = parse_usage(body, usage, mode)
            reported = body.get('model')
            observed = model
            if reported is not None:
                if not isinstance(reported, str) or not re.fullmatch(MODELS[capability], reported):
                    raise ProviderError('UPSTAGE_MODEL_MISMATCH')
                requested_name, observed_name = canonical_model(model), canonical_model(reported)
                if observed_name != requested_name and not (not re.search(r'-\d{6}$', requested_name)
                                                           and re.fullmatch(re.escape(requested_name) + r'-\d{6}', observed_name)):
                    raise ProviderError('UPSTAGE_MODEL_MISMATCH')
                observed = reported
            snapshot = observed if re.search(r'-\d{6}$', observed) else None
            outcome = 'RECEIVED'
            return ProviderResult(body, ReviewRun(request_id=request_id, model=observed, snapshot=snapshot,
                elapsed_ms=int((monotonic() - started) * 1000), usage=usage), endpoint)
        except httpx.TimeoutException:
            outcome = 'UPSTAGE_TIMEOUT'
            raise ProviderError(outcome, request_id=request_id) from None
        except (httpx.HTTPError, OSError):
            outcome = 'UPSTAGE_NETWORK'
            raise ProviderError(outcome, request_id=request_id) from None
        except ProviderError as exc:
            outcome = exc.code
            raise ProviderError(outcome, request_id=request_id, retry_after=exc.retry_after) from None
        finally:
            LOGGER.info('Upstage request=%s capability=%s outcome=%s', request_id, capability, outcome)
            try:
                self.tracker.complete(reservation, usage, outcome)
            except Exception:
                # The earlier reservation remains in place if metering fails.
                raise ProviderError('COST_POLICY_UNAVAILABLE', request_id=request_id) from None

    def chat(self, source: ApprovedSource, *, requested: bool, system: str, data: dict, schema: dict, max_tokens: int):
        model = self.settings.ai_mapping_model
        if not 1 <= max_tokens <= 4096:
            raise ProviderError('UPSTAGE_INPUT_LIMIT')
        content = encoded(data).decode('utf-8')
        payload = solar_chat_payload(model, system, content, schema, max_tokens, explicit_reasoning=True)
        endpoint = '/chat/completions'
        if model == SOLAR_PREVIEW:
            endpoint, payload = '/responses', solar_responses_payload(payload)
        return self._send('chat', source, requested, model, endpoint, encoded(payload), max_tokens=max_tokens)

    def embedding(self, source: ApprovedSource, *, requested: bool, model: str, inputs: list[str]):
        if not 1 <= len(inputs) <= 100 or any(not value or len(value.encode('utf-8')) > 8192 for value in inputs):
            raise ProviderError('UPSTAGE_INPUT_LIMIT')
        result = self._send('embedding', source, requested, model, '/embeddings', encoded({'model': model, 'input': inputs}))
        try:
            rows = result.body['data']
            vectors = {row['index']: row['embedding'] for row in rows}
            if len(rows) != len(inputs) or set(vectors) != set(range(len(inputs))):
                raise ValueError
            for index, vector in vectors.items():
                if type(index) is not int or not isinstance(vector, list) or len(vector) != 1024 or any(
                    type(value) not in (int, float) or not -1 <= value <= 1 for value in vector):
                    raise ValueError
            return [vectors[i] for i in range(len(inputs))], result.run
        except (ValueError, TypeError, KeyError):
            raise ProviderError('UPSTAGE_RESPONSE_FORMAT', request_id=result.run.request_id) from None

    def _document(self, capability, source, requested, data, kind, options, schema=None):
        check_permission(self.settings, capability, source, requested=requested)
        if kind not in MIME or not data.startswith(SIGNATURE[kind]):
            raise ProviderError('UNSUPPORTED_DOCUMENT')
        if len(data) > self.settings.upstage_document_max_input_bytes:
            raise ProviderError('UPSTAGE_INPUT_LIMIT')
        if sha256(data).hexdigest() != source.source_sha256:
            raise ProviderError('SOURCE_NOT_APPROVED')
        if schema is None:
            # Fixed generic file name. The HTTP request never contains the original filename.
            form = httpx.Request('POST', BASE_URL, data=options,
                                 files={'document': (f'synthetic.{kind}', data, MIME[kind])})
            wire, mime = form.read(), form.headers['content-type']
            endpoint = '/document-digitization'
        else:
            message = {'role': 'user', 'content': [{'type': 'image_url', 'image_url': {
                'url': 'data:application/octet-stream;base64,' + b64encode(data).decode('ascii')}}]}
            wire, mime = encoded({**options, 'messages': [message], 'response_format': {
                'type': 'json_schema', 'json_schema': {'name': 'synthetic_review', 'schema': schema}}}), 'application/json'
            endpoint = '/information-extraction' if capability == 'extract' else '/document-classification'
        return self._send(capability, source, requested, options['model'], endpoint, wire, mime=mime,
                          max_pages=MAX_DOCUMENT_PAGES, mode=options.get('mode'))

    def parse(self, source, *, requested, data, kind):
        model = self.settings.upstage_document_parse_model
        mode = self.settings.upstage_document_parse_mode
        snapshot = re.search(r'-(\d{6})$', model)
        if snapshot and mode != 'standard' and snapshot[1] < '260128':
            raise ProviderError('UNSUPPORTED_MODE')
        return self._document('parse', source, requested, data, kind, {'model': model,
            'mode': mode, 'output_formats': '["html","markdown","text"]',
            'coordinates': 'true', 'chart_recognition': 'false', 'ocr': 'auto'})

    def extract(self, source, *, requested, data, kind, schema):
        extraction_fields(schema)
        return self._document('extract', source, requested, data, kind, {'model': self.settings.upstage_information_extract_model,
            'mode': self.settings.upstage_information_extract_mode, 'split': False, 'location': True,
            'location_granularity': 'element'}, schema)

    def classify(self, source, *, requested, data, kind, classes: dict[str, str]):
        if not 1 <= len(classes) <= 32 or any(
            not isinstance(key, str) or not 1 <= len(key) <= 64
            or not isinstance(description, str) or not 1 <= len(description) <= 500 for key, description in classes.items()
        ):
            raise ProviderError('UNSUPPORTED_SCHEMA')
        schema = {'type': 'string', 'oneOf': [{'const': key, 'description': description} for key, description in classes.items()]}
        result = self._document('classify', source, requested, data, kind, {'model': self.settings.upstage_document_classify_model,
                                'split': False}, schema)
        try:
            choice = result.body['choices'][0]
            value = choice['message']['content'].strip()
            if value.startswith('"'):
                value = strict_json(value)
            if choice['finish_reason'] != 'stop' or choice['message'].get('refusal') or not isinstance(value, str) or value not in classes:
                raise ValueError
        except (AttributeError, TypeError, ValueError, KeyError, IndexError):
            raise ProviderError('UPSTAGE_RESPONSE_FORMAT', request_id=result.run.request_id) from None
        return value, result.run

    def ocr(self, source, *, requested, data, kind):
        result = self._document('ocr', source, requested, data, kind, {'model': 'ocr'})
        pages = result.body.get('pages')
        if not isinstance(pages, list) or not 1 <= len(pages) <= MAX_DOCUMENT_PAGES or any(not isinstance(p, dict) for p in pages):
            raise ProviderError('UPSTAGE_RESPONSE_FORMAT', request_id=result.run.request_id)
        if any(not isinstance(p.get('words'), list) or any(not isinstance(w, dict) or not isinstance(w.get('text'), str)
                                                         for w in p['words']) for p in pages):
            raise ProviderError('UPSTAGE_RESPONSE_FORMAT', request_id=result.run.request_id)
        return result
