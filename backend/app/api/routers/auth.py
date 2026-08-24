import re
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_db
from app.core.deps import get_current_user
from app.core.security import create_access_token, hash_password, verify_password
from app.models.user import User
from app.services.otp_service import OtpVerifyError, request_otp, verify_otp
from app.services.rbac import get_role_actions
from app.services.session_service import create_session

router = APIRouter(prefix="/auth", tags=["auth"])
settings = get_settings()

PHONE_RE = re.compile(r"^255[0-9]{9}$")


def _client_ip(request: Request) -> str | None:
    return request.headers.get("x-real-ip") or request.headers.get("x-forwarded-for") or (
        request.client.host if request.client else None
    )


def _find_user_by_identifier(db: Session, identifier: str) -> User | None:
    """Login (and forgot-password) accept either a phone (255XXXXXXXXX)
    or an email as the identifier - one input field, disambiguated by
    shape server-side."""
    identifier = identifier.strip()
    if PHONE_RE.match(identifier):
        return db.query(User).filter(User.phone == identifier, User.is_active.is_(True)).first()
    return db.query(User).filter(User.email == identifier.lower(), User.is_active.is_(True)).first()


def _issue_session_and_token(db: Session, user: User, request: Request) -> "TokenResponse":
    ip = _client_ip(request)
    user_agent = request.headers.get("user-agent")
    session = create_session(db, user_id=user.id, ip_address=ip, user_agent=user_agent)

    user.last_login_at = datetime.now(timezone.utc)
    user.last_login_ip = ip
    user.last_login_browser = session.browser
    db.commit()

    token = create_access_token(subject=user.email, role=user.role, session_token=session.session_token)
    return TokenResponse(access_token=token)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class LoginResponse(BaseModel):
    requires_otp: bool
    pending_token: str | None = None
    access_token: str | None = None
    token_type: str = "bearer"


class CurrentUserResponse(BaseModel):
    id: int
    email: str
    role: str
    full_name: str | None
    phone: str | None
    two_factor_enabled: bool
    permissions: list[str]
    session_idle_timeout_minutes: int


def _current_user_response(current_user: User, db: Session) -> CurrentUserResponse:
    permissions = sorted(get_role_actions(db, current_user.role))
    return CurrentUserResponse(
        id=current_user.id,
        email=current_user.email,
        role=current_user.role,
        full_name=current_user.full_name,
        phone=current_user.phone,
        two_factor_enabled=current_user.two_factor_enabled,
        permissions=permissions,
        session_idle_timeout_minutes=settings.session_idle_timeout_minutes,
    )


@router.post("/login", response_model=LoginResponse)
def login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
) -> LoginResponse:
    """form_data.username accepts either an email or a 255XXXXXXXXX phone
    number (OAuth2PasswordRequestForm's field is just named "username" by
    the spec, not a hard requirement on shape). If the account has 2FA
    on (the default) and a phone on file, returns a pending_token instead
    of a token - the client must then call /auth/login/verify-otp with
    the SMS code before a real session/access_token is issued."""
    user = _find_user_by_identifier(db, form_data.username)
    if not user or not verify_password(form_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email/phone or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if user.two_factor_enabled and user.phone:
        pending_token = request_otp(db, user=user, purpose="LOGIN_2FA")
        db.commit()
        return LoginResponse(requires_otp=True, pending_token=pending_token)

    token = _issue_session_and_token(db, user, request)
    return LoginResponse(requires_otp=False, access_token=token.access_token)


class VerifyLoginOtpRequest(BaseModel):
    pending_token: str
    code: str


@router.post("/login/verify-otp", response_model=TokenResponse)
def verify_login_otp(
    request: Request, req: VerifyLoginOtpRequest, db: Session = Depends(get_db)
) -> TokenResponse:
    try:
        user = verify_otp(db, pending_token=req.pending_token, code=req.code, purpose="LOGIN_2FA")
    except OtpVerifyError as exc:
        db.commit()  # persist the attempt_count increment even on failure
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc)) from exc

    return _issue_session_and_token(db, user, request)


@router.get("/me", response_model=CurrentUserResponse)
def read_current_user(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> CurrentUserResponse:
    """Includes the user's actual granted permissions (not just their role
    name) so the portal's UI gating (frontend AuthProvider.can()) reflects
    real, possibly-GUI-edited role permissions rather than a hand-kept
    static mirror that would go stale the moment someone edits a role."""
    return _current_user_response(current_user, db)


class UpdateProfileRequest(BaseModel):
    full_name: str | None = None
    email: str | None = None
    phone: str | None = None

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: str | None) -> str | None:
        if v is not None and not PHONE_RE.match(v):
            raise ValueError("phone must be in 255XXXXXXXXX format")
        return v


@router.put("/me", response_model=CurrentUserResponse)
def update_profile(
    req: UpdateProfileRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CurrentUserResponse:
    if req.full_name is not None:
        current_user.full_name = req.full_name.strip()
    if req.email is not None:
        current_user.email = req.email.strip().lower()
    if req.phone is not None:
        current_user.phone = req.phone.strip()
    db.commit()

    return _current_user_response(current_user, db)


class UpdateTwoFactorRequest(BaseModel):
    enabled: bool


@router.put("/me/2fa")
def update_two_factor(
    req: UpdateTwoFactorRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    if req.enabled and not current_user.phone:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Add a phone number before enabling 2FA")
    current_user.two_factor_enabled = req.enabled
    db.commit()
    return {"two_factor_enabled": current_user.two_factor_enabled}


class RequestPasswordChangeOtpRequest(BaseModel):
    current_password: str


class PendingTokenResponse(BaseModel):
    pending_token: str


@router.post("/change-password/request", response_model=PendingTokenResponse)
def request_password_change(
    req: RequestPasswordChangeOtpRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PendingTokenResponse:
    """A password change always requires OTP confirmation, regardless of
    the account's 2FA login setting - see docs/decisions.md."""
    if not verify_password(req.current_password, current_user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Current password is incorrect")
    if not current_user.phone:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Add a phone number before changing your password")

    pending_token = request_otp(db, user=current_user, purpose="PASSWORD_CHANGE")
    db.commit()
    return PendingTokenResponse(pending_token=pending_token)


class ConfirmPasswordChangeRequest(BaseModel):
    pending_token: str
    code: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("password must be at least 8 characters")
        return v


@router.post("/change-password/confirm")
def confirm_password_change(
    req: ConfirmPasswordChangeRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    try:
        otp_user = verify_otp(db, pending_token=req.pending_token, code=req.code, purpose="PASSWORD_CHANGE")
    except OtpVerifyError as exc:
        db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc)) from exc

    if otp_user.id != current_user.id:
        db.rollback()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Code does not match your account")

    current_user.password_hash = hash_password(req.new_password)
    db.commit()
    return {"detail": "Password updated."}


class ForgotPasswordRequest(BaseModel):
    identifier: str


@router.post("/forgot-password/request", response_model=PendingTokenResponse)
def forgot_password_request(req: ForgotPasswordRequest, db: Session = Depends(get_db)) -> PendingTokenResponse:
    """Always returns a pending_token and never reveals whether the
    identifier matched a real account - forgot-password requires OTP
    confirmation even when the account has 2FA disabled (see
    docs/decisions.md), and this is the one flow where the response
    itself must not leak account existence, so a non-match still returns
    a syntactically valid (but permanently unverifiable) pending_token
    rather than a 404."""
    import secrets as _secrets

    user = _find_user_by_identifier(db, req.identifier)
    if user is not None and user.phone:
        pending_token = request_otp(db, user=user, purpose="PASSWORD_RESET")
        db.commit()
    else:
        pending_token = _secrets.token_urlsafe(32)
    return PendingTokenResponse(pending_token=pending_token)


class ResetPasswordRequest(BaseModel):
    pending_token: str
    code: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("password must be at least 8 characters")
        return v


@router.post("/forgot-password/reset")
def reset_password(req: ResetPasswordRequest, db: Session = Depends(get_db)) -> dict:
    try:
        user = verify_otp(db, pending_token=req.pending_token, code=req.code, purpose="PASSWORD_RESET")
    except OtpVerifyError as exc:
        db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc)) from exc

    user.password_hash = hash_password(req.new_password)
    db.commit()
    return {"detail": "Password reset successfully. You can now sign in with your new password."}
