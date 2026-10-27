from fastapi import APIRouter, HTTPException
from starlette.concurrency import run_in_threadpool

from ...api.schemas import EmailConfirmation, EmailSettingsInput
from ...repositories import database
from ...services import email_workflow
from ...tools import email as email_tool

router = APIRouter(prefix='/api/email')


@router.get('/settings')
def get_email_settings():
    return email_tool.get_settings()


@router.put('/settings')
def update_email_settings(payload: EmailSettingsInput):
    try:
        email_tool.save_settings(
            payload.host,
            payload.port,
            payload.username,
            payload.password,
            payload.from_email,
            payload.security,
        )
        email_workflow.clear_pending_confirmations()
        return email_tool.get_settings()
    except email_tool.EmailToolError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.delete('/settings')
def delete_email_settings():
    email_tool.clear_settings()
    email_workflow.clear_pending_confirmations()
    return {'ok': True}


@router.post('/confirm')
async def confirm_email(payload: EmailConfirmation):
    pending = email_workflow.take_confirmation(payload.confirmation_id)
    if not pending:
        raise HTTPException(404, 'Email preview expired or was already handled.')
    if not database.get_chat(pending['chat_id']):
        raise HTTPException(404, 'Chat not found.')
    recipient = payload.to if payload.to is not None else pending['to']
    subject = payload.subject if payload.subject is not None else pending['subject']
    body = payload.body if payload.body is not None else pending['body']
    try:
        await run_in_threadpool(
            email_tool.send_email,
            recipient,
            subject,
            body,
        )
    except email_tool.EmailToolError as exc:
        raise HTTPException(502, str(exc)) from exc

    result = f"Email sent to {recipient} with subject: {subject}"
    database.save_assistant_message(pending['chat_id'], result)
    return {'ok': True, 'message': result}


@router.post('/cancel')
def cancel_email(payload: EmailConfirmation):
    pending = email_workflow.take_confirmation(payload.confirmation_id)
    if not pending:
        raise HTTPException(404, 'Email preview expired or was already handled.')
    if not database.get_chat(pending['chat_id']):
        raise HTTPException(404, 'Chat not found.')
    database.save_assistant_message(
        pending['chat_id'], 'Email draft canceled; nothing was sent.'
    )
    return {'ok': True}
