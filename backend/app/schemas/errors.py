from pydantic import BaseModel


class FieldError(BaseModel):
    field: str
    type: str
    message: str


class ErrorBody(BaseModel):
    code: str
    message: str
    details: list[FieldError] | None = None


class ErrorResponse(BaseModel):
    error: ErrorBody
