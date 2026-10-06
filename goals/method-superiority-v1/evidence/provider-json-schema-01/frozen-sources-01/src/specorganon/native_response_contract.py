"""Output syntax only: no authored facts, judgments, approval or test receipts.

The engine/controller still enforce phase, dependencies, mandate, budgets and
measured tests. A schema constrains the provider before generation; it never
extracts, trims or repairs a response after generation.
"""
from __future__ import annotations

from jsonschema import Draft7Validator

from .engine import ITEM_ID
from .workflow import KIND_TO_PHASE


def response_schema(role, *, author_format='manifest-v1', approval=False):
    if (type(role) is not str or role not in {'author', 'review'}
            or type(author_format) is not str or author_format not in {'manifest-v1', 'items-v1'}
            or type(approval) is not bool or approval and role != 'review'):
        raise ValueError('unsupported native response contract')
    text = {'type': 'string', 'pattern': r'\S'}
    item_id = {'type': 'string', 'pattern': ITEM_ID.pattern}
    fields = {'schema': {'type': 'integer', 'enum': [1]}, 'reason': text}
    if role == 'review':
        fields.update(verdict={'type': 'string', 'enum': ['accept', 'reject', 'inconclusive']},
                      findings={'type': 'array', 'items': {'type': 'object', 'minProperties': 1}},
                      tests_executed={'type': 'boolean', 'enum': [False]})
        if approval:
            # No fixed verdict/conformity/target values: the reviewer decides.
            fields.update(mandate_conformity={'type': 'boolean'},
                          approval_targets={'type': 'array', 'items': item_id, 'uniqueItems': True})
    else:
        put = {'id': item_id, 'kind': {'type': 'string', 'enum': sorted(KIND_TO_PHASE)},
               'text': text, 'refs': {'type': 'array', 'items': item_id, 'uniqueItems': True},
               'data': {'type': 'object'}}
        required_put = list(put)
        if author_format == 'manifest-v1':
            put.update(op={'type': 'string', 'enum': ['put']},
                       expected_version={'type': 'integer', 'minimum': 0},
                       expected_deps={'type': 'object', 'additionalProperties': {'type': 'integer', 'minimum': 1}})
            required_put.append('op')
        collection = {'type': 'array', 'minItems': 1, 'maxItems': 32,
                      'items': {'type': 'object', 'properties': put, 'required': required_put,
                                'additionalProperties': False}}
        fields['files'] = {'type': 'object', 'additionalProperties': {'type': 'string'}}
        if author_format == 'items-v1':
            fields['items'] = collection
        else:
            fields['manifest'] = {'type': 'object', 'properties': {
                'schema': {'type': 'integer', 'enum': [1]}, 'steps': collection,
                'name': text, 'description': {'type': 'string'}},
                'required': ['schema', 'steps'], 'additionalProperties': False}
    return {'$schema': 'http://json-schema.org/draft-07/schema#', 'type': 'object',
            'properties': fields, 'required': list(fields), 'additionalProperties': False}


def validate_response_schema(value, schema):
    """Reject a mismatch unchanged; do not echo arbitrary native content."""
    Draft7Validator.check_schema(schema)
    if next(Draft7Validator(schema).iter_errors(value), None) is not None:
        raise ValueError('native response violates the bound output schema')
