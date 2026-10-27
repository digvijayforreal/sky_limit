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

DATE_TIME_TOOL = [{
    'type': 'function',
    'function': {
        'name': 'get_current_datetime',
        'description': 'Get the current date and time in the application server local timezone.',
        'parameters': {
            'type': 'object',
            'properties': {},
            'required': [],
            'additionalProperties': False,
        },
    },
}]

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

WEB_TOOLS = [
    {
        'type': 'function',
        'function': {
            'name': 'web_search',
            'description': 'Search the public web for current information when the user asks for web research or up-to-date facts.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'query': {'type': 'string', 'description': 'A focused web search query.'},
                },
                'required': ['query'],
                'additionalProperties': False,
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'web_scrape',
            'description': 'Fetch and extract readable content from a public web page URL supplied or requested by the user.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'url': {'type': 'string', 'description': 'The public HTTP or HTTPS URL to extract.'},
                },
                'required': ['url'],
                'additionalProperties': False,
            },
        },
    },
]
