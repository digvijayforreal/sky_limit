from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIR = PROJECT_ROOT / 'frontend'
ASSETS_DIR = FRONTEND_DIR / 'assets'

SYSTEM_PROMPT = (
    'You are OmniAgent, a helpful, precise AI assistant. Respect conversation '
    'context and answer clearly. Use saved personal memories if provided. Do '
    'not claim access to tools or the internet that have not been provided.'
)
MAX_CONTEXT_CHARS = 65000

EMAIL_TOOLS = [{
    'type': 'function',
    'function': {
        'name': 'send_email',
        'description': 'Prepare an email to send. The user must explicitly approve the preview before anything is sent.',
        'parameters': {
            'type': 'object',
            'properties': {
                'to': {'type': 'string', 'description': 'One or more recipient email addresses.'},
                'subject': {'type': 'string'},
                'body': {'type': 'string'},
            },
            'required': ['to', 'subject', 'body'],
            'additionalProperties': False,
        },
    },
}]
