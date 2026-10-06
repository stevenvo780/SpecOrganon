"""Explicit file/document author syntax for non-engine comparators.

No ledger steps, judgments, approvals, execution receipts or repairs are inferred.
Admission, chronology, resource limits and package review belong to the separate
comparator controller. Toolkit author formats remain manifest-v1/items-v1.
"""
from __future__ import annotations

import copy
import re

from .role_jobs import canonical


PATH_PATTERN = r'^[A-Za-z0-9_-][A-Za-z0-9_.-]*(/[A-Za-z0-9_-][A-Za-z0-9_.-]*)*$'


def neutral_author_content(value):
    if (type(value) is not dict or set(value) != {'schema', 'files', 'documents', 'reason'}
            or type(value['schema']) is not int or value['schema'] != 1
            or type(value['reason']) is not str or not value['reason'].strip()
            or any(type(value[name]) is not dict for name in ('files', 'documents'))
            or not (value['files'] or value['documents'])):
        raise ValueError('invalid explicit neutral author content')
    for group in ('files', 'documents'):
        if any(type(name) is not str or len(name) > 200 or re.fullmatch(PATH_PATTERN, name) is None
               or type(text) is not str for name,text in value[group].items()):
            raise ValueError('neutral content needs safe relative names and text')
    # Verify finite UTF-8 JSON without changing a byte of the authored content.
    canonical(value)
    return copy.deepcopy(value)
