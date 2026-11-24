"""Provider-independent review wire rules used by the API and offline replay."""
from collections import Counter
from dataclasses import dataclass, field
import json


SYSTEM = ('Identify each synthetic column business meaning. Use only allowed fields. Use HOLD if ambiguous, incompatible, '
          'unrelated, or needing aggregation or transformation. Never repeat a target field. Return every column ID.')
KEYED_INSTRUCTION = ' Return one JSON object keyed by source column ID, not an array.'
SOLAR_PREVIEW = 'solar-mini-4-5-preview'
HOLD_CONCEPTS = {
    'HOLD': 'Unknown or ambiguous',
    'ORDER_OR_RETURN': 'Purchase order or returns, outside registration definition',
    'MONEY_OR_PARTY': 'Money, unit price or trading party identifier',
    'NEEDS_TRANSFORM': 'Aggregation, reshape or conversion required',
}


def concept_vocabulary(fields):
    return {f'concept_{i:02d}': name for i, name in enumerate(fields, 1)} | dict.fromkeys(HOLD_CONCEPTS)


def solar_chat_payload(model, system, content, schema, max_tokens, *, explicit_reasoning=False):
    payload = {'model': model, 'temperature': 0, 'max_tokens': max_tokens, 'messages': [
        {'role': 'system', 'content': system}, {'role': 'user', 'content': content}],
        'response_format': {'type': 'json_schema', 'json_schema': {'name': 'mapping_result', 'strict': True, 'schema': schema}}}
    if explicit_reasoning:
        payload['reasoning_effort'] = 'none'
    return payload


def solar_responses_payload(chat):
    system, user = chat['messages']
    contract = chat['response_format']['json_schema']
    return {'model': chat['model'], 'instructions': system['content'], 'input': user['content'],
            'max_output_tokens': chat['max_tokens'], 'reasoning': {'effort': 'none'}, 'store': False,
            'text': {'format': {'type': 'json_schema', **contract}}}


def mapping_schema(allowed, vocabulary, *, keyed):
    def choices(fields):
        return [token for token, target in vocabulary.items() if target is None or target in fields]

    if keyed:
        properties = {key: {'type': 'string', 'enum': choices(fields)} for key, fields in allowed.items()}
        return {'type': 'object', 'additionalProperties': False, 'properties': properties, 'required': list(properties)}
    all_fields = set().union(*allowed.values())
    row = {'type': 'object', 'required': ['id', 'field'], 'additionalProperties': False,
           'properties': {'id': {'type': 'string', 'enum': list(allowed)},
                          'field': {'type': 'string', 'enum': choices(all_fields)}}}
    return {'type': 'object', 'required': ['mapping'], 'additionalProperties': False,
            'properties': {'mapping': {'type': 'array', 'items': row}}}


class DuplicateKey(ValueError):
    pass


def unique_object(items):
    result = {}
    for key, value in items:
        if key in result:
            raise DuplicateKey('Duplicate JSON key')
        result[key] = value
    return result


def reject_constant(_):
    raise ValueError('Non-JSON numeric constant')


def strict_json(raw):
    return json.loads(raw, object_pairs_hook=unique_object, parse_constant=reject_constant)


@dataclass
class DecodedMapping:
    values: dict[str, str | None] = field(default_factory=dict)
    concepts: dict[str, str] = field(default_factory=dict)
    issues: Counter = field(default_factory=Counter)
    rejected: dict[str, str] = field(default_factory=dict)
    fatal: str | None = None


def finished_text(body, endpoint):
    if endpoint == '/responses':
        if body['status'] != 'completed':
            reason = (body.get('incomplete_details') or {}).get('reason')
            return None, 'OUTPUT_LIMIT' if reason == 'max_output_tokens' else 'UNFINISHED_OR_REFUSED'
        blocks = [part for item in body['output'] if item['type'] == 'message' for part in item['content']]
        if any(block['type'] == 'refusal' for block in blocks):
            return None, 'REFUSAL'
        return ''.join(block['text'] for block in blocks if block['type'] == 'output_text'), None
    choices = body['choices']
    if not isinstance(choices, list) or len(choices) != 1:
        raise ValueError('Expected a single completion')
    choice = choices[0]
    if choice['finish_reason'] != 'stop':
        return None, 'OUTPUT_LIMIT' if choice['finish_reason'] == 'length' else 'UNFINISHED_OR_REFUSED'
    if choice['message'].get('refusal'):
        return None, 'REFUSAL'
    return choice['message']['content'], None


def decode_mapping(body, endpoint, allowed, vocabulary, *, keyed):
    def fatal(reason):
        return DecodedMapping(issues=Counter({reason: 1}), fatal=reason)

    try:
        raw, failure = finished_text(body, endpoint)
        if failure:
            return fatal(failure)
        obj = strict_json(raw)
    except DuplicateKey:
        return fatal('DUPLICATE_JSON_KEY')
    except (AttributeError, KeyError, TypeError, IndexError, ValueError, RecursionError):
        return fatal('INVALID_JSON_OR_PROVIDER_SCHEMA')
    if not isinstance(obj, dict) or (not keyed and (set(obj) != {'mapping'} or not isinstance(obj['mapping'], list))):
        return fatal('INVALID_WRAPPER')

    result = DecodedMapping()
    if keyed:
        pairs = list(obj.items())
    else:
        pairs = []
        for row in obj['mapping']:
            if isinstance(row, dict) and set(row) == {'id', 'field'} and isinstance(row['id'], str):
                pairs.append((row['id'], row['field']))
            else:
                result.issues['INVALID_ITEM'] += 1
                if isinstance(row, dict) and isinstance(row.get('id'), str):
                    pairs.append((row['id'], None))
    counts = Counter(key for key, _ in pairs)
    missing = set(allowed) - counts.keys()
    result.issues.update({'MISSING_ID': len(missing), 'EXTRA_ID': len(counts.keys() - allowed.keys())})
    result.rejected.update(dict.fromkeys(missing, 'MISSING_ID'))
    for key, token in pairs:
        if key not in allowed:
            continue
        if counts[key] != 1:
            reason = 'DUPLICATE_ID'
        elif (not isinstance(token, str) or token not in vocabulary
              or (vocabulary[token] is not None and vocabulary[token] not in allowed[key])):
            reason = 'INVALID_FIELD'
        else:
            result.values[key] = vocabulary[token]
            result.concepts[key] = token
            continue
        result.issues[reason] += 1
        result.rejected[key] = reason
    result.issues = +result.issues
    return result


def validate_mapping(proposals, locked, compatible):
    safe = dict(locked)
    counts = Counter(target for target in proposals.values() if target is not None)
    occupied = set(locked.values())
    rejected = {}
    for key, target in proposals.items():
        if target is None:
            continue
        if key in locked or target in occupied:
            rejected[key] = 'EXISTING_MAPPING_CONFLICT'
        elif counts[target] > 1:
            rejected[key] = 'DUPLICATE_TARGET'
        elif (reason := compatible(key, target)):
            rejected[key] = reason
        else:
            safe[key] = target
    return safe, rejected
