from pydantic import BaseModel, Field


class AddKey(BaseModel):
    name: str = Field(default='API Key', max_length=70)
    api_key: str = Field(min_length=15, max_length=300)
    provider: str = Field(default='groq', pattern='^(groq|google)$')
    remember: bool = True


class ChatRequest(BaseModel):
    chat_id: str
    message: str = Field(min_length=1, max_length=16000)
    model: str = Field(min_length=1, max_length=220)


class RenameRequest(BaseModel):
    title: str = Field(min_length=1, max_length=100)


class EmailSettingsInput(BaseModel):
    host: str = Field(min_length=1, max_length=253)
    port: int = Field(ge=1, le=65535)
    username: str = Field(default='', max_length=320)
    password: str = Field(default='', max_length=1000)
    from_email: str = Field(min_length=3, max_length=320)
    security: str = Field(default='starttls', pattern='^(starttls|ssl)$')


class SearchSettingsInput(BaseModel):
    tavily_api_key: str = Field(min_length=10, max_length=500)


class EmailConfirmation(BaseModel):
    confirmation_id: str
    to: str | None = Field(default=None, max_length=2000)
    subject: str | None = Field(default=None, max_length=250)
    body: str | None = Field(default=None, max_length=20000)


class DesignRequest(BaseModel):
    prompt: str = Field(min_length=3, max_length=1000)
    model: str = Field(min_length=1, max_length=220)


class DesignPreview(BaseModel):
    preview_id: str = Field(min_length=1, max_length=64)


class FailoverTest(BaseModel):
    model: str


class MemoryInput(BaseModel):
    content: str = Field(min_length=1, max_length=1000)
    ttl_hours: int | None = Field(default=None, ge=1, le=8760)
