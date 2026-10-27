import re
import time
import uuid
from threading import RLock

from ..repositories import database as db

MAX_RULES = 30
MAX_VALUE_LENGTH = 160
ALLOWED_SELECTORS = {
    ':root', 'body', '.sidebar', '.brand-mark', '.new-btn', '.main', '.topbar',
    '.crumb', '.status-pill', '.chat-panel', '.empty-state', '.empty-state h1',
    '.empty-state h1 em', '.quick-actions button', '.message', '.message.user',
    '.message.assistant', '.avatar', '.message-header', '.message-text',
    '.composer-wrap', '.model-strip', '.composer', '.composer textarea',
    '.composer-bottom button', '.footnote', '.nav-btn',
}
ALLOWED_PROPERTIES = {
    'align-items', 'background', 'background-color', 'border', 'border-color',
    'border-radius', 'border-width', 'box-shadow', 'color', 'display', 'font-family',
    'font-size', 'font-weight', 'gap', 'grid-template-columns', 'height',
    'justify-content', 'letter-spacing', 'line-height', 'margin', 'max-width',
    'min-height', 'opacity', 'padding', 'text-align', 'text-transform', 'width',
}
FORBIDDEN_VALUE = re.compile(r'url\s*\(|expression\s*\(|javascript\s*:|@import|!important|[;{}<>\\]', re.I)
lock = RLock()
pending = {}


class DesignError(Exception):
    pass


def validate_rules(value):
    if not isinstance(value, list) or len(value) > MAX_RULES:
        raise DesignError(f'The design must contain no more than {MAX_RULES} style rules.')
    result = []
    for rule in value:
        if not isinstance(rule, dict) or set(rule) != {'selector', 'declarations'}:
            raise DesignError('The model returned an invalid style rule.')
        selector = rule['selector']
        declarations = rule['declarations']
        if selector not in ALLOWED_SELECTORS:
            raise DesignError(f'The selector "{selector}" is not allowed.')
        if not isinstance(declarations, dict) or not declarations or len(declarations) > 15:
            raise DesignError('Each style rule must contain between 1 and 15 declarations.')
        clean = {}
        for property_name, value in declarations.items():
            if property_name not in ALLOWED_PROPERTIES:
                raise DesignError(f'The CSS property "{property_name}" is not allowed.')
            if not isinstance(value, str) or not value.strip() or len(value) > MAX_VALUE_LENGTH:
                raise DesignError(f'The value for "{property_name}" is invalid.')
            value = value.strip()
            if FORBIDDEN_VALUE.search(value) or any(ord(char) < 32 for char in value):
                raise DesignError(f'The value for "{property_name}" contains unsupported content.')
            clean[property_name] = value
        result.append({'selector': selector, 'declarations': clean})
    return result


def to_css(rules):
    return '\n'.join(
        selector + ' {' + ''.join(f'{name}: {value};' for name, value in declarations.items()) + '}'
        for selector, declarations in ((rule['selector'], rule['declarations']) for rule in rules)
    )


def current_rules():
    return db.get_design_rules()


def create_preview(rules, summary):
    rules = validate_rules(rules)
    if not isinstance(summary, str) or not summary.strip() or len(summary) > 300:
        raise DesignError('The model did not provide a valid preview summary.')
    preview_id = str(uuid.uuid4())
    with lock:
        pending.clear()
        pending[preview_id] = {'rules': rules, 'summary': summary.strip(), 'expires_at': time.monotonic() + 600}
    return {'id': preview_id, 'rules': rules, 'css': to_css(rules), 'summary': summary.strip()}


def apply_preview(preview_id):
    with lock:
        proposal = pending.pop(preview_id, None)
    if not proposal or proposal['expires_at'] <= time.monotonic():
        raise DesignError('This design preview expired or was already applied.')
    db.save_design_rules(proposal['rules'])
    return {'rules': proposal['rules'], 'css': to_css(proposal['rules'])}


def discard_preview(preview_id):
    with lock:
        proposal = pending.pop(preview_id, None)
        return bool(proposal and proposal['expires_at'] > time.monotonic())


def reset_design():
    with lock:
        pending.clear()
    db.save_design_rules([])
    return {'rules': [], 'css': ''}
