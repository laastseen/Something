import hmac
import hashlib
import base64
import json
import time
from fastapi import Request, HTTPException, status
from fastapi.responses import RedirectResponse
import database

SECRET_KEY = b"secure_diploma_video_hosting_key_2026_v1"
SESSION_COOKIE_NAME = "session_token"
SESSION_EXPIRY_SECONDS = 7 * 24 * 3600  # 1 week

def create_session_token(user_id: int, username: str, role: str) -> str:
    """Создает криптографически подписанный сессионный токен."""
    payload = {
        "user_id": user_id,
        "username": username,
        "role": role,
        "exp": int(time.time()) + SESSION_EXPIRY_SECONDS
    }
    serialized = json.dumps(payload).encode('utf-8')
    b64_data = base64.urlsafe_b64encode(serialized).decode('utf-8')
    signature = hmac.new(SECRET_KEY, b64_data.encode('utf-8'), hashlib.sha256).digest()
    b64_sig = base64.urlsafe_b64encode(signature).decode('utf-8')
    return f"{b64_data}.{b64_sig}"

def verify_session_token(token: str) -> dict | None:
    """Проверяет токен и подпись. Возвращает payload или None."""
    try:
        parts = token.split('.')
        if len(parts) != 2:
            return None
        b64_data, b64_sig = parts
        
        # Проверка HMAC подписи
        expected_sig = hmac.new(SECRET_KEY, b64_data.encode('utf-8'), hashlib.sha256).digest()
        actual_sig = base64.urlsafe_b64decode(b64_sig.encode('utf-8'))
        if not hmac.compare_digest(expected_sig, actual_sig):
            return None
        
        # Декодирование полезной нагрузки
        serialized = base64.urlsafe_b64decode(b64_data.encode('utf-8'))
        payload = json.loads(serialized.decode('utf-8'))
        
        # Проверка срока действия
        if payload.get("exp", 0) < time.time():
            return None
            
        return payload
    except Exception:
        return None

def get_current_user_optional(request: Request) -> dict | None:
    """Зависимость для получения текущего пользователя, если он авторизован (не блокирует гостей)."""
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        return None
    
    payload = verify_session_token(token)
    if not payload:
        return None
    
    user = database.get_user_by_id(payload.get("user_id"))
    return user

def get_current_user_required(request: Request) -> dict:
    """Зависимость для получения текущего пользователя. Перенаправляет на /login при отсутствии сессии."""
    user = get_current_user_optional(request)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_307_TEMPORARY_REDIRECT,
            headers={"Location": "/login"}
        )
    return user

def get_current_user_api(request: Request) -> dict:
    """Зависимость для API. Возвращает 401 если не авторизован."""
    user = get_current_user_optional(request)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Нужна авторизация")
    return user
