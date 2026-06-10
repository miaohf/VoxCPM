import logging

from fastapi import FastAPI, HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

logger = logging.getLogger("voxcpm.api")


def api_error(
    status_code: int,
    code: str,
    message: str,
    *,
    retryable: bool = False,
) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"code": code, "message": message, "retryable": retryable},
    )


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(HTTPException)
    def http_exception_handler(request, exc: HTTPException):
        detail = exc.detail
        if isinstance(detail, dict) and {"code", "message", "retryable"} <= detail.keys():
            error = detail
        else:
            error = {
                "code": "HTTP_ERROR",
                "message": str(detail),
                "retryable": 500 <= exc.status_code < 600,
            }
        logger.warning(
            "HTTP error status=%s method=%s path=%s client=%s code=%s message=%s",
            exc.status_code,
            request.method,
            request.url.path,
            request.client.host if request.client else "-",
            error.get("code"),
            error.get("message"),
        )
        return JSONResponse(status_code=exc.status_code, content={"error": error})

    @app.exception_handler(RequestValidationError)
    def validation_exception_handler(request, exc: RequestValidationError):
        details = jsonable_encoder(exc.errors())
        logger.warning(
            "Request validation error method=%s path=%s client=%s details=%s",
            request.method,
            request.url.path,
            request.client.host if request.client else "-",
            details,
        )
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": "Request validation failed.",
                    "retryable": False,
                    "details": details,
                }
            },
        )
