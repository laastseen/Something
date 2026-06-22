from fastapi import FastAPI, Request, File, UploadFile, Form, HTTPException, Depends, Response, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from contextlib import asynccontextmanager
import database
import auth
import recommendations
import documents
import os
import shutil
import uuid
from datetime import datetime
import asyncio

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
UPLOADS_DIR = os.path.join(BASE_DIR, "uploads")
THUMBS_DIR = os.path.join(UPLOADS_DIR, "thumbs")
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
ALLOWED_THUMB_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif"}

async def tag_cleanup_task():
    while True:
        try:
            database.cleanup_zero_votes_tags()
        except Exception as e:
            print(f"Cleanup error: {e}")
        await asyncio.sleep(60)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Выполняется при старте
    database.initialize_database()
    with database.get_db_connection() as conn:
        if not conn.execute("SELECT 1 FROM users LIMIT 1").fetchone():
            database.add_user("admin", "admin@admin.com", "admin", "admin")
            database.add_or_update_author_profile(1, "Админ", "Сайта", "Автор по умолчанию")
    
    asyncio.create_task(tag_cleanup_task())
    try:
        import seed_content
        seed_content.run_seed()
        seed_content.backfill_thumbnails()
    except Exception as e:
        print(f"Seed skipped: {e}")
    yield

app = FastAPI(lifespan=lifespan)

templates = Jinja2Templates(directory=TEMPLATES_DIR)

def to_url(path):
    if not path: return ""
    return "/" + path.replace(os.sep, "/")

templates.env.globals.update(to_url=to_url)

def _feed_type_param(type_str: str | None) -> str:
    if not type_str:
        return "video"
    t = type_str.rstrip("s")
    if t in ("video", "image", "audio", "document"):
        return t
    return "video"


@app.get("/", response_class=HTMLResponse)
def read_item(request: Request, q: str = None, type: str = None, current_user: dict | None = Depends(auth.get_current_user_optional)):
    user_id = current_user['id'] if current_user else None
    recommended_media = recommendations.get_personalized_recommendations(user_id, limit=8)
    tag_name = None
    if q and q.strip().startswith("#"):
        tag_name = database.normalize_tag_name(q.strip()[1:])

    feed_config = {
        "q": (q or "").strip() or None,
        "tag": tag_name,
        "type": _feed_type_param(type),
        "authorId": None,
    }

    return templates.TemplateResponse(
        request=request, name="index.html",
        context={
            "recommended": recommended_media,
            "user": current_user,
            "query": q,
            "active_type": type or "videos",
            "feed_config": feed_config,
        }
    )


@app.get("/api/feed")
def api_feed(
    request: Request,
    type: str = "video",
    page: int = 1,
    limit: int = database.FEED_PAGE_SIZE,
    q: str | None = None,
    tag: str | None = None,
    author_id: int | None = None,
):
    media_type = _feed_type_param(type)
    search = q.strip() if q and q.strip() and not (q.strip().startswith("#")) else None
    tag_name = tag or (database.normalize_tag_name(q.strip()[1:]) if q and q.strip().startswith("#") else None)
    items, has_more = database.list_media_feed(
        media_type=media_type,
        search_term=search,
        tag_name=tag_name,
        author_id=author_id,
        page=page,
        limit=limit,
    )
    items = [recommendations.format_thumbnail(i) for i in items]
    return {"items": items, "has_more": has_more, "page": page}


@app.get("/author/{author_id}", response_class=HTMLResponse)
def author_channel(
    request: Request,
    author_id: int,
    type: str | None = None,
    current_user: dict | None = Depends(auth.get_current_user_optional),
):
    author = database.get_author_public(author_id)
    if not author:
        return HTMLResponse("Канал не найден", status_code=404)
    subscribed = False
    is_self = False
    if current_user:
        subscribed = database.is_subscribed(current_user["id"], author_id)
        is_self = author["user_id"] == current_user["id"]
    display_name = f"{author.get('first_name', '')} {author.get('second_name', '')}".strip() or author["username"]
    feed_config = {
        "q": None,
        "tag": None,
        "type": _feed_type_param(type),
        "authorId": author_id,
    }
    return templates.TemplateResponse(
        request=request,
        name="author.html",
        context={
            "author": author,
            "display_name": display_name,
            "user": current_user,
            "subscribed": subscribed,
            "is_self": is_self,
            "feed_config": feed_config,
            "active_type": type or "videos",
        },
    )


@app.post("/api/subscribe")
def api_subscribe(author_id: int = Form(...), current_user: dict = Depends(auth.get_current_user_api)):
    author = database.get_author_public(author_id)
    if not author:
        return JSONResponse({"status": "error", "message": "Автор не найден"}, status_code=404)
    if author["user_id"] == current_user["id"]:
        return JSONResponse({"status": "error", "message": "Нельзя подписаться на себя"}, status_code=400)
    subscribed, count = database.toggle_subscription(current_user["id"], author_id)
    return {"status": "ok", "subscribed": subscribed, "subscriber_count": count}

@app.get("/view/{media_id}", response_class=HTMLResponse)
def view_media(request: Request, media_id: int, current_user: dict | None = Depends(auth.get_current_user_optional)):
    if current_user:
        database.log_view_history(current_user['id'], media_id)
        
    with database.get_db_connection() as conn:
        with conn:
            conn.execute("UPDATE media SET views = views + 1 WHERE id = ?", (media_id,))
        media = conn.execute("""
            SELECT m.*, u.username as owner_username,
                   COALESCE(a.first_name,'') || ' ' || COALESCE(a.second_name,'') AS author_name
            FROM media m
            JOIN authors a ON m.author_id = a.id
            JOIN users u ON a.user_id = u.id
            WHERE m.id = ?
        """, (media_id,)).fetchone()
        
        if not media: return HTMLResponse("Контент не найден", status_code=404)
        media_dict = dict(media)
        media_dict['web_path'] = to_url(media_dict['file_path'])
        tags = database.get_media_tags_extended(media_id)
        comments = conn.execute("""
            SELECT c.*, u.username FROM comments c JOIN users u ON c.user_id = u.id 
            WHERE c.media_id = ? ORDER BY c.comment_date DESC
        """, (media_id,)).fetchall()
    
    recs = recommendations.get_content_based_recommendations(media_id, limit=5)
    user_like, playlists = 0, []
    if current_user:
        user_like = database.get_user_like(current_user['id'], media_id)
        playlists = database.get_user_playlists(current_user['id'])
    likes_info = database.get_likes_count(media_id)

    doc_view = None
    if media_dict.get("media_type") == "document":
        doc_view = documents.get_document_view(media_dict["file_path"], BASE_DIR)

    is_owner = False
    subscribed_author = False
    author_personal_tag = None
    has_author_tag_on_media = False
    if current_user:
        is_owner = database.user_owns_media(current_user["id"], media_id)
        subscribed_author = database.is_subscribed(current_user["id"], media_dict["author_id"])

    author_row = database.get_author_public(media_dict["author_id"])
    if author_row:
        author_personal_tag = author_row.get("personal_tag")
    has_author_tag_on_media = any(t.get("is_author_tag") for t in tags)

    return templates.TemplateResponse(
        request=request, name="view.html", 
        context={
            "media": media_dict, "tags": tags, "comments": comments, "recommendations": recs,
            "user": current_user, "user_like": user_like, "likes": likes_info, "playlists": playlists,
            "report_reasons": database.REPORT_REASONS,
            "doc_view": doc_view,
            "is_owner": is_owner,
            "subscribed_author": subscribed_author,
            "author_personal_tag": author_personal_tag,
            "has_author_tag_on_media": has_author_tag_on_media,
        }
    )

@app.get("/wiki", response_class=HTMLResponse)
def wiki_page(request: Request, current_user: dict | None = Depends(auth.get_current_user_optional)):
    std_tags = database.get_standard_tags()
    return templates.TemplateResponse(request=request, name="wiki.html", context={"tags": std_tags, "user": current_user})

@app.post("/api/wiki/save")
def save_wiki_tag(id: int = Form(None), name: str = Form(...), description: str = Form(...), color: str = Form(...), current_user: dict = Depends(auth.get_current_user_required)):
    if current_user['role'] != 'admin': raise HTTPException(status_code=403, detail="Доступ запрещен")
    if id: database.update_standard_tag(id, name, description, color)
    else: database.add_standard_tag(name, description, color)
    return RedirectResponse("/wiki", status_code=303)

@app.post("/api/wiki/delete")
def delete_wiki_tag(id: int = Form(...), current_user: dict = Depends(auth.get_current_user_required)):
    if current_user['role'] != 'admin': raise HTTPException(status_code=403, detail="Доступ запрещен")
    database.delete_standard_tag(id)
    return RedirectResponse("/wiki", status_code=303)

@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request, current_user: dict | None = Depends(auth.get_current_user_optional)):
    if current_user: return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse(request=request, name="login.html")

@app.post("/login")
def login_action(username_or_email: str = Form(...), password: str = Form(...)):
    user = database.verify_user_credentials(username_or_email, password)
    if not user: return HTMLResponse("Неверные учетные данные. <a href='/login'>Попробовать еще раз</a>", status_code=400)
    token = auth.create_session_token(user['id'], user['username'], user['role'])
    response = RedirectResponse("/", status_code=303)
    response.set_cookie(key=auth.SESSION_COOKIE_NAME, value=token, httponly=True, max_age=auth.SESSION_EXPIRY_SECONDS, samesite="lax")
    return response

@app.get("/register", response_class=HTMLResponse)
def register_page(request: Request, current_user: dict | None = Depends(auth.get_current_user_optional)):
    if current_user: return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse(request=request, name="register.html")

@app.post("/register")
def register_action(
    request: Request,
    username: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    consent_pd: str | None = Form(None),
):
    if consent_pd != "1":
        return templates.TemplateResponse(
            request=request, name="register.html",
            context={"error": "Необходимо согласие на обработку персональных данных."},
            status_code=400,
        )
    success = database.add_user(
        username, email, password,
        consent_accepted_at=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    )
    if not success:
        return templates.TemplateResponse(
            request=request, name="register.html",
            context={"error": "Ошибка регистрации. Возможно, такой логин или email уже занят."},
            status_code=400,
        )
    return RedirectResponse("/login", status_code=303)

@app.get("/privacy", response_class=HTMLResponse)
def privacy_page(request: Request):
    return templates.TemplateResponse(request=request, name="privacy.html")

@app.get("/personal-data", response_class=HTMLResponse)
def personal_data_page(request: Request):
    return templates.TemplateResponse(request=request, name="personal-data.html")

@app.get("/cookies", response_class=HTMLResponse)
def cookies_page(request: Request):
    return templates.TemplateResponse(request=request, name="cookies.html")

@app.get("/logout")
def logout_action():
    response = RedirectResponse("/", status_code=303)
    response.delete_cookie(auth.SESSION_COOKIE_NAME)
    return response

@app.get("/admin", response_class=HTMLResponse)
def admin_page(request: Request, current_user: dict = Depends(auth.get_current_user_required)):
    if current_user['role'] != 'admin': raise HTTPException(status_code=403, detail="Доступ запрещен")
    return templates.TemplateResponse(request=request, name="admin.html", context={
        "users": database.get_all_users(), "media": database.get_all_media_admin(),
        "reports": database.get_all_reports(), "report_reasons": database.REPORT_REASONS,
        "user": current_user,
    })

@app.post("/api/admin/delete/user")
def admin_delete_user(id: int = Form(...), current_user: dict = Depends(auth.get_current_user_required)):
    if current_user['role'] != 'admin': raise HTTPException(status_code=403, detail="Доступ запрещен")
    if id == current_user['id']: raise HTTPException(status_code=400, detail="Нельзя удалить самого себя")
    database.delete_user(id)
    return {"status": "ok"}

@app.post("/api/admin/delete/media")
def admin_delete_media(id: int = Form(...), current_user: dict = Depends(auth.get_current_user_required)):
    if current_user['role'] != 'admin':
        media = None
        with database.get_db_connection() as conn:
            media = conn.execute("SELECT author_id FROM media WHERE id = ?", (id,)).fetchone()
        author = database.get_author_by_user_id(current_user['id'])
        if not media or not author or media['author_id'] != author['id']: raise HTTPException(status_code=403, detail="Доступ запрещен")
    database.delete_media(id, BASE_DIR)
    return {"status": "ok"}


@app.post("/api/media/delete")
def delete_own_media(id: int = Form(...), current_user: dict = Depends(auth.get_current_user_required)):
    if not database.user_owns_media(current_user["id"], id):
        if current_user["role"] != "admin":
            raise HTTPException(status_code=403, detail="Доступ запрещен")
    database.delete_media(id, BASE_DIR)
    return {"status": "ok"}


@app.post("/api/media/update")
def update_own_media(
    media_id: int = Form(...),
    title: str = Form(...),
    description: str = Form(""),
    thumbnail: UploadFile | None = File(None),
    current_user: dict = Depends(auth.get_current_user_required),
):
    if not database.user_owns_media(current_user["id"], media_id):
        raise HTTPException(status_code=403, detail="Доступ запрещен")
    thumb_path = None
    if thumbnail and thumbnail.filename:
        thumb_ext = os.path.splitext(thumbnail.filename)[1].lower()
        if thumb_ext not in ALLOWED_THUMB_EXT:
            return JSONResponse({"status": "error", "message": "Превью: JPG, PNG, WebP или GIF"}, status_code=400)
        saved = _save_upload(thumbnail, THUMBS_DIR, "uploads/thumbs")
        if not saved:
            return JSONResponse({"status": "error", "message": "Ошибка превью"}, status_code=500)
        thumb_path = saved[1]
    if not database.update_media_fields(media_id, title, description, thumb_path):
        return JSONResponse({"status": "error", "message": "Ошибка сохранения"}, status_code=500)
    return {"status": "ok"}


@app.get("/profile", response_class=HTMLResponse)
def profile_page(request: Request, current_user: dict = Depends(auth.get_current_user_required)):
    author = database.get_author_by_user_id(current_user['id'])
    my_uploads = []
    if author:
        with database.get_db_connection() as conn:
            my_uploads = [dict(r) for r in conn.execute(
                "SELECT * FROM media WHERE author_id = ? ORDER BY upload_date DESC",
                (author['id'],),
            ).fetchall()]

    continue_watching = database.get_continue_watching(current_user['id'], limit=12)
    continue_watching = [recommendations.format_thumbnail(i) for i in continue_watching]
    my_uploads = [recommendations.format_thumbnail(i) for i in my_uploads]

    return templates.TemplateResponse(
        request=request,
        name="profile.html",
        context={
            "user": current_user,
            "playlists": database.get_user_playlists(current_user['id']),
            "continue_watching": continue_watching,
            "uploads": my_uploads,
            "author": author,
        },
    )

@app.post("/api/comment")
def add_comment(media_id: int = Form(...), text: str = Form(...), current_user: dict = Depends(auth.get_current_user_required)):
    if not text.strip(): return JSONResponse({"status": "error", "message": "Комментарий пуст"}, status_code=400)
    with database.get_db_connection() as conn:
        with conn: conn.execute("INSERT INTO comments (media_id, user_id, comment_text, comment_date) VALUES (?, ?, ?, ?)", (media_id, current_user['id'], text.strip(), datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
    return {"status": "ok"}

@app.post("/api/like")
def add_like_api(media_id: int = Form(...), is_like: int = Form(...), current_user: dict = Depends(auth.get_current_user_api)):
    if is_like not in (-1, 1): return JSONResponse({"status": "error", "message": "Некорректно"}, status_code=400)
    act = database.toggle_like(current_user['id'], media_id, is_like)
    return {"status": "ok", "action": act, "likes": database.get_likes_count(media_id)}

@app.post("/api/playlist/create")
def create_playlist_api(name: str = Form(...), description: str = Form(""), current_user: dict = Depends(auth.get_current_user_required)):
    if not name.strip(): return JSONResponse({"status": "error", "message": "Пусто"}, status_code=400)
    if database.create_playlist(current_user['id'], name.strip(), description): return {"status": "ok"}
    return JSONResponse({"status": "error", "message": "Уже есть"}, status_code=400)

@app.post("/api/playlist/add")
def add_to_playlist_api(playlist_id: int = Form(...), media_id: int = Form(...), current_user: dict = Depends(auth.get_current_user_required)):
    pl = database.get_playlist_details(playlist_id)
    if not pl or pl['user_id'] != current_user['id']: return JSONResponse({"status": "error", "message": "Нет доступа"}, status_code=403)
    if database.add_to_playlist(playlist_id, media_id): return {"status": "ok"}
    return JSONResponse({"status": "error", "message": "Ошибка"}, status_code=500)

@app.post("/api/playlist/remove")
def remove_from_playlist_api(playlist_id: int = Form(...), media_id: int = Form(...), current_user: dict = Depends(auth.get_current_user_required)):
    pl = database.get_playlist_details(playlist_id)
    if not pl or pl['user_id'] != current_user['id']: return JSONResponse({"status": "error", "message": "Нет доступа"}, status_code=403)
    if database.remove_from_playlist(playlist_id, media_id): return {"status": "ok"}
    return JSONResponse({"status": "error", "message": "Ошибка"}, status_code=500)

@app.get("/playlists/{playlist_id}", response_class=HTMLResponse)
def view_playlist(request: Request, playlist_id: int, current_user: dict | None = Depends(auth.get_current_user_optional)):
    pl = database.get_playlist_details(playlist_id)
    if not pl: return HTMLResponse("Не найден", status_code=404)
    items = database.get_playlist_media(playlist_id)
    items = [recommendations.format_thumbnail(i) for i in items]
    return templates.TemplateResponse(request=request, name="playlist.html", context={"playlist": pl, "media_items": items, "owner": database.get_user_by_id(pl['user_id']), "user": current_user})

@app.post("/api/tag/vote")
def vote_tag_api(media_id: int = Form(...), tag_id: int = Form(...), delta: int = Form(...), current_user: dict = Depends(auth.get_current_user_api)):
    act = database.vote_tag_limited(current_user['id'], media_id, tag_id, delta)
    if act == "forbidden":
        return JSONResponse({"status": "error", "message": "За персональный тег автора нельзя голосовать"}, status_code=403)
    return {"status": "ok", "action": act}


@app.post("/api/author/personal-tag")
def set_author_personal_tag_api(name: str = Form(...), current_user: dict = Depends(auth.get_current_user_required)):
    author = database.get_author_by_user_id(current_user["id"])
    if not author:
        database.add_or_update_author_profile(current_user["id"], current_user["username"], "")
    ok, result = database.set_author_personal_tag(current_user["id"], name)
    if not ok:
        return JSONResponse({"status": "error", "message": result}, status_code=400)
    return {"status": "ok", "personal_tag": result}


@app.post("/api/author/personal-tag/clear")
def clear_author_personal_tag_api(current_user: dict = Depends(auth.get_current_user_required)):
    database.clear_author_personal_tag(current_user["id"])
    return {"status": "ok"}


@app.post("/api/tag/author")
def toggle_author_tag_api(media_id: int = Form(...), current_user: dict = Depends(auth.get_current_user_required)):
    ok, action, msg = database.toggle_media_author_tag(current_user["id"], media_id)
    if not ok:
        return JSONResponse({"status": "error", "message": msg}, status_code=403)
    return {"status": "ok", "action": action, "tag": msg}


@app.get("/api/notifications")
def api_notifications(current_user: dict = Depends(auth.get_current_user_api)):
    items = database.get_notifications(current_user["id"], limit=20)
    for item in items:
        thumb = item.get("thumbnail_path")
        if thumb:
            item["thumbnail"] = "/" + str(thumb).replace("\\", "/")
        else:
            item["thumbnail"] = recommendations.STATIC_COVERS.get(
                item.get("media_type", "video"), recommendations.STATIC_COVERS["video"]
            )
    return {"items": items, "unread": database.get_unread_notification_count(current_user["id"])}


@app.get("/api/notifications/unread-count")
def api_notifications_unread_count(current_user: dict = Depends(auth.get_current_user_api)):
    return {"unread": database.get_unread_notification_count(current_user["id"])}


@app.post("/api/notifications/read")
def api_notifications_read(
    ids: str | None = Form(None),
    current_user: dict = Depends(auth.get_current_user_api),
):
    id_list = None
    if ids and ids.strip():
        try:
            id_list = [int(x.strip()) for x in ids.split(",") if x.strip()]
        except ValueError:
            return JSONResponse({"status": "error", "message": "Некорректные id"}, status_code=400)
    count = database.mark_notifications_read(current_user["id"], id_list)
    return {"status": "ok", "marked": count, "unread": database.get_unread_notification_count(current_user["id"])}

@app.post("/api/report")
def report_content(
    reported_author_id: int = Form(...),
    media_id: int = Form(None),
    reason: str = Form(...),
    details: str = Form(""),
    current_user: dict = Depends(auth.get_current_user_api),
):
    author = database.get_author_by_user_id(current_user["id"])
    if author and author["id"] == reported_author_id:
        return JSONResponse({"status": "error", "message": "Нельзя пожаловаться на себя"}, status_code=400)
    ok, msg = database.create_report(current_user["id"], reported_author_id, media_id, reason, details)
    if ok:
        return {"status": "ok", "message": msg}
    return JSONResponse({"status": "error", "message": msg}, status_code=400)

@app.post("/api/admin/report/status")
def admin_report_status(id: int = Form(...), status: str = Form(...), current_user: dict = Depends(auth.get_current_user_required)):
    if current_user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Доступ запрещен")
    if database.update_report_status(id, status):
        return {"status": "ok"}
    return JSONResponse({"status": "error", "message": "Ошибка"}, status_code=400)

@app.post("/api/tag/add")
def add_tag(media_id: int = Form(...), name: str = Form(...)):
    name = database.normalize_tag_name(name)
    if not name: return {"status": "error", "message": "Пусто"}
    if database.is_reserved_personal_tag(name):
        return JSONResponse(
            {"status": "error", "message": "Это персональный тег автора — добавить может только он"},
            status_code=403,
        )
    with database.get_db_connection() as conn:
        with conn:
            conn.execute("INSERT OR IGNORE INTO tags (name) VALUES (?)", (name,))
            tag_row = conn.execute("SELECT id FROM tags WHERE name = ?", (name,)).fetchone()
            if tag_row: conn.execute("INSERT OR IGNORE INTO media_tags (media_id, tag_id, votes) VALUES (?, ?, 0)", (media_id, tag_row['id']))
    return {"status": "ok"}

def _save_upload(upload: UploadFile, folder: str, subpath: str) -> tuple[str, str] | None:
    """Сохраняет файл, возвращает (disk_path, db_relative_path) или None."""
    ext = os.path.splitext(upload.filename or "")[1].lower()
    if not ext:
        return None
    filename = f"{uuid.uuid4().hex}{ext}"
    disk_path = os.path.join(folder, filename)
    rel_path = os.path.join(subpath, filename).replace("\\", "/")
    try:
        with open(disk_path, "wb") as buffer:
            shutil.copyfileobj(upload.file, buffer)
        return disk_path, rel_path
    except Exception:
        return None


@app.post("/upload")
def upload_media(
    title: str = Form(...),
    description: str = Form(None),
    media_type: str = Form(...),
    file: UploadFile = File(...),
    thumbnail: UploadFile | None = File(None),
    consent_rights: str | None = Form(None),
    current_user: dict = Depends(auth.get_current_user_required),
):
    if consent_rights != "1":
        return JSONResponse(
            {"status": "error", "message": "Необходимо подтвердить права на публикуемый контент."},
            status_code=400,
        )
    author = database.get_author_by_user_id(current_user["id"])
    if not author:
        database.add_or_update_author_profile(current_user["id"], current_user["username"], "")
        author = database.get_author_by_user_id(current_user["id"])

    saved = _save_upload(file, UPLOADS_DIR, "uploads")
    if not saved:
        return JSONResponse({"status": "error", "message": "Ошибка файла"}, status_code=500)
    disk_path, file_path = saved

    thumb_disk, thumb_path = None, None
    if media_type == "document":
        thumb_path = None
    elif thumbnail and thumbnail.filename:
        thumb_ext = os.path.splitext(thumbnail.filename)[1].lower()
        if thumb_ext not in ALLOWED_THUMB_EXT:
            if os.path.exists(disk_path):
                os.remove(disk_path)
            return JSONResponse(
                {"status": "error", "message": "Превью: только JPG, PNG, WebP или GIF"},
                status_code=400,
            )
        thumb_saved = _save_upload(thumbnail, THUMBS_DIR, "uploads/thumbs")
        if not thumb_saved:
            if os.path.exists(disk_path):
                os.remove(disk_path)
            return JSONResponse({"status": "error", "message": "Ошибка загрузки превью"}, status_code=500)
        thumb_disk, thumb_path = thumb_saved
    elif media_type == "image":
        thumb_path = file_path

    if media_id := database.add_media(title, description, author["id"], media_type, file_path, thumb_path):
        database.notify_subscribers_new_upload(author["id"], media_id)
        return JSONResponse({"status": "ok"})
    if thumb_disk and os.path.exists(thumb_disk):
        os.remove(thumb_disk)
    if os.path.exists(disk_path):
        os.remove(disk_path)
    return JSONResponse({"status": "error", "message": "Ошибка БД"}, status_code=500)

os.makedirs(UPLOADS_DIR, exist_ok=True)
os.makedirs(THUMBS_DIR, exist_ok=True)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.mount("/uploads", StaticFiles(directory=UPLOADS_DIR), name="uploads")

if __name__ == "__main__":
    import uvicorn
    os.chdir(BASE_DIR)
    uvicorn.run("main:app", host="127.0.0.1", port=8001, reload=True)
