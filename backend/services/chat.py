import json

from starlette.concurrency import run_in_threadpool

from ..core.config import EMAIL_TOOLS, MAX_CONTEXT_CHARS, SYSTEM_PROMPT
from ..repositories import database
from ..services import model_router
from ..tools import email as email_tool
from . import email_workflow


class ChatServiceError(Exception):
    pass


def build_context(previous, new_message):
    remaining = MAX_CONTEXT_CHARS - len(new_message)
    selected = []
    for item in reversed(previous):
        if len(item['content']) > remaining:
            break
        selected.append({'role': item['role'], 'content': item['content']})
        remaining -= len(item['content'])
    selected.reverse()

    memories = database.list_memories()[:40]
    memory_text = '\n'.join('- ' + item['content'][:500] for item in memories)[:8500]
    system = SYSTEM_PROMPT + (
        '\nSaved user memories (from prior chats; user can edit/delete):\n' + memory_text
        if memory_text else ''
    )
    return [{'role': 'system', 'content': system}, *selected, {
        'role': 'user',
        'content': new_message,
    }]


async def send_message(chat_id, message, model):
    if not database.get_chat(chat_id):
        raise LookupError('Chat not found')

    clean_message = message.strip()
    messages = build_context(database.get_messages(chat_id), clean_message)
    tools = EMAIL_TOOLS if email_tool.get_settings()['configured'] else None
    if tools:
        messages[0]['content'] += (
            '\nAn SMTP email tool is available. Use it only when the user asks '
            'you to send an email. The tool only prepares a preview; never '
            'claim an email was sent until the user approves it.'
        )

    try:
        if tools:
            response, metadata = await run_in_threadpool(
                model_router.completion, model, messages, False, tools, True
            )
            calls = response.get('tool_calls') or []
            if calls:
                function = (
                    calls[0].get('function')
                    if isinstance(calls, list) and isinstance(calls[0], dict)
                    else None
                )
                if (
                    len(calls) != 1
                    or not isinstance(function, dict)
                    or function.get('name') != 'send_email'
                ):
                    raise model_router.RouterError(
                        'The model requested an unsupported email action.'
                    )

                try:
                    arguments = json.loads(function['arguments'])
                    recipient = arguments['to']
                    subject = arguments['subject']
                    body = arguments['body']
                    confirmation_id = email_tool.create_confirmation(
                        recipient, subject, body
                    )
                except (
                    ValueError,
                    KeyError,
                    TypeError,
                    email_tool.EmailToolError,
                ) as exc:
                    raise model_router.RouterError(
                        f'The model returned an invalid email draft: {exc}'
                    ) from exc

                email_workflow.remember_confirmation(
                    confirmation_id, chat_id, recipient, subject, body
                )
                answer = response.get('content') or (
                    'Email draft prepared. Review the preview and approve it to send.'
                )
                database.save_exchange(chat_id, clean_message, answer)
                return {
                    'answer': answer,
                    'meta': metadata,
                    'email_confirmation': {
                        'id': confirmation_id,
                        'to': recipient,
                        'subject': subject,
                        'body': body,
                    },
                }

            answer = response.get('content')
            if not isinstance(answer, str) or not answer.strip():
                raise model_router.RouterError('Provider returned an empty response.')
        else:
            answer, metadata = await run_in_threadpool(
                model_router.completion, model, messages
            )
    except model_router.RouterError as exc:
        raise ChatServiceError(str(exc)) from exc

    database.save_exchange(chat_id, clean_message, answer)
    return {'answer': answer, 'meta': metadata}
