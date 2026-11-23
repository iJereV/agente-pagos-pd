"""HTTP driving adapter: the sign-in page and the API it calls."""

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field

from .domain import Purpose, Rejection
from .page import IdentityConfig, render_link_page
from .service import Failure, LinkService, SignInError

PAGE_HEADERS = {
    # The link token travels in the query string: never leak it through Referer or caches.
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
}

STATUS_BY_CODE: dict[Failure | Rejection, int] = {
    Failure.INVALID_LINK: 400,
    Failure.INVALID_IDENTITY: 401,
    Failure.GOOGLE_ACCOUNT_REQUIRED: 403,
    Rejection.TOKEN_NOT_FOUND: 400,
    Rejection.TOKEN_MISMATCH: 400,
    Rejection.TOKEN_USED: 410,
    Rejection.TOKEN_EXPIRED: 410,
    Rejection.NOT_LINKED: 409,
    Rejection.NUMBER_LINKED_TO_OTHER_ACCOUNT: 409,
    Rejection.ACCOUNT_LINKED_TO_OTHER_NUMBER: 409,
    Rejection.ACCOUNT_MISMATCH: 409,
}

RESULT_BY_PURPOSE = {Purpose.LINK: "linked", Purpose.REAUTH: "reauthenticated"}


class LinkRequest(BaseModel):
    link_token: str = Field(min_length=1, max_length=4096)
    id_token: str = Field(min_length=1, max_length=8192)


def create_app(service: LinkService, identity_config: IdentityConfig) -> FastAPI:
    app = FastAPI(title="link-web", docs_url=None, redoc_url=None, openapi_url=None)
    page = render_link_page(identity_config)

    @app.get("/link", response_class=HTMLResponse)
    def link_page() -> HTMLResponse:
        return HTMLResponse(page, headers=PAGE_HEADERS)

    @app.post("/api/link")
    def complete_link(body: LinkRequest) -> JSONResponse:
        try:
            purpose = service.complete(body.link_token, body.id_token)
        except SignInError as error:
            return JSONResponse(
                {"status": error.code.value},
                status_code=STATUS_BY_CODE[error.code],
                headers={"Cache-Control": "no-store"},
            )
        return JSONResponse(
            {"status": RESULT_BY_PURPOSE[purpose]}, headers={"Cache-Control": "no-store"}
        )

    return app
