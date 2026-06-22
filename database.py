import sqlite3
from datetime import datetime
import os
import hashlib
import re
from contextlib import closing

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_NAME = os.path.join(_BASE_DIR, 'media_platform.db')
UPLOAD_FOLDER = os.path.join(_BASE_DIR, "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


def normalize_tag_name(name: str) -> str:
    """Единый формат имён тегов (кириллица: SQLite NOCASE не помогает)."""
    return (name or "").strip().casefold()


def validate_personal_tag_name(name: str) -> str | None:
    """Проверяет имя персонального тега автора."""
    norm = normalize_tag_name(name)
    if len(norm) < 2 or len(norm) > 32:
        return None
    if not re.fullmatch(r"[a-zа-яё0-9_\-]+", norm):
        return None
    return norm


def get_db_connection():
    """Создает и возвращает подключение к БД."""
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.row_factory = sqlite3.Row
    return conn

def initialize_database():
    """Инициализация таблиц базы данных."""
    with closing(get_db_connection()) as conn:
        with conn: # Автоматический commit/rollback
            conn.executescript('''
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    email TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    registration_date TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT 'viewer' CHECK(role IN ('admin', 'viewer'))
                );
                CREATE TABLE IF NOT EXISTS authors (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER UNIQUE NOT NULL,
                    first_name TEXT,
                    second_name TEXT,
                    bio TEXT,
                    phone TEXT,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS tags (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL COLLATE NOCASE
                );
                CREATE TABLE IF NOT EXISTS media (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    description TEXT,
                    upload_date TEXT NOT NULL,
                    author_id INTEGER NOT NULL,
                    media_type TEXT NOT NULL CHECK(media_type IN ('image', 'audio', 'video', 'document')),
                    file_path TEXT NOT NULL UNIQUE,
                    status TEXT NOT NULL DEFAULT 'published' CHECK(status IN ('draft', 'published', 'private', 'archived')),
                    views INTEGER DEFAULT 0,
                    FOREIGN KEY (author_id) REFERENCES authors(id) ON DELETE RESTRICT
                );
                CREATE TABLE IF NOT EXISTS media_tags (
                    media_id INTEGER NOT NULL,
                    tag_id INTEGER NOT NULL,
                    votes INTEGER DEFAULT 0,
                    PRIMARY KEY (media_id, tag_id),
                    FOREIGN KEY (media_id) REFERENCES media(id) ON DELETE CASCADE,
                    FOREIGN KEY (tag_id) REFERENCES tags(id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS comments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    media_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    comment_text TEXT NOT NULL,
                    comment_date TEXT NOT NULL,
                    FOREIGN KEY (media_id) REFERENCES media(id) ON DELETE CASCADE,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS likes (
                    user_id INTEGER NOT NULL,
                    media_id INTEGER NOT NULL,
                    is_like INTEGER NOT NULL CHECK(is_like IN (-1, 1)),
                    like_date TEXT NOT NULL,
                    PRIMARY KEY (user_id, media_id),
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                    FOREIGN KEY (media_id) REFERENCES media(id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS playlists (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    description TEXT,
                    creation_date TEXT NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                    UNIQUE(user_id, name)
                );
                CREATE TABLE IF NOT EXISTS playlist_media (
                    playlist_id INTEGER NOT NULL,
                    media_id INTEGER NOT NULL,
                    added_date TEXT NOT NULL,
                    PRIMARY KEY (playlist_id, media_id),
                    FOREIGN KEY (playlist_id) REFERENCES playlists(id) ON DELETE CASCADE,
                    FOREIGN KEY (media_id) REFERENCES media(id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    media_id INTEGER NOT NULL,
                    viewed_at TEXT NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                    FOREIGN KEY (media_id) REFERENCES media(id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS standard_tags (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL COLLATE NOCASE,
                    description TEXT,
                    color TEXT DEFAULT '#ff0000'
                );
                CREATE TABLE IF NOT EXISTS tag_user_votes (
                    user_id INTEGER NOT NULL,
                    media_id INTEGER NOT NULL,
                    tag_id INTEGER NOT NULL,
                    vote INTEGER NOT NULL CHECK(vote IN (-1, 1)),
                    PRIMARY KEY (user_id, media_id, tag_id),
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                    FOREIGN KEY (media_id) REFERENCES media(id) ON DELETE CASCADE,
                    FOREIGN KEY (tag_id) REFERENCES tags(id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS reports (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    reporter_id INTEGER NOT NULL,
                    reported_author_id INTEGER NOT NULL,
                    media_id INTEGER,
                    reason TEXT NOT NULL,
                    details TEXT,
                    status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending', 'reviewed', 'dismissed')),
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (reporter_id) REFERENCES users(id) ON DELETE CASCADE,
                    FOREIGN KEY (reported_author_id) REFERENCES authors(id) ON DELETE CASCADE,
                    FOREIGN KEY (media_id) REFERENCES media(id) ON DELETE SET NULL
                );
            ''')
            _run_migrations(conn)
            # Initialize some default standard tags if empty
            if not conn.execute("SELECT 1 FROM standard_tags LIMIT 1").fetchone():
                conn.executemany("INSERT INTO standard_tags (name, description, color) VALUES (?, ?, ?)", [
                    ('образование', 'Контент обучающего характера', '#4CAF50'),
                    ('развлечение', 'Юмористические и игровые видео', '#FF9800'),
                    ('музыка', 'Музыкальные клипы и аудио', '#2196F3'),
                    ('технологии', 'Обзоры гаджетов и IT', '#9C27B0'),
                    ('важное', 'Официальные объявления', '#f44336')
                ])
            _migrate_normalize_tags(conn)

REPORT_REASONS = {
    'plagiarism': 'Плагиат или нарушение авторских прав',
    'harassment': 'Оскорбления и домогательства',
    'hate': 'Язык вражды и дискриминация',
    'violence': 'Насилие или опасный контент',
    'spam': 'Спам и вводящая в заблуждение информация',
    'misleading': 'Ложная или вводящая в заблуждение информация',
    'child_safety': 'Нарушение безопасности детей',
    'other': 'Другое',
}

FEED_PAGE_SIZE = 24


def _run_migrations(conn):
    cols = {r[1] for r in conn.execute("PRAGMA table_info(media)").fetchall()}
    if 'thumbnail_path' not in cols:
        conn.execute("ALTER TABLE media ADD COLUMN thumbnail_path TEXT")
    user_cols = {r[1] for r in conn.execute("PRAGMA table_info(users)").fetchall()}
    if 'consent_accepted_at' not in user_cols:
        conn.execute("ALTER TABLE users ADD COLUMN consent_accepted_at TEXT")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS subscriptions (
            user_id INTEGER NOT NULL,
            author_id INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY (user_id, author_id),
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (author_id) REFERENCES authors(id) ON DELETE CASCADE
        )
    """)
    author_cols = {r[1] for r in conn.execute("PRAGMA table_info(authors)").fetchall()}
    if "personal_tag" not in author_cols:
        conn.execute("ALTER TABLE authors ADD COLUMN personal_tag TEXT")
    mt_cols = {r[1] for r in conn.execute("PRAGMA table_info(media_tags)").fetchall()}
    if "is_author_tag" not in mt_cols:
        conn.execute("ALTER TABLE media_tags ADD COLUMN is_author_tag INTEGER NOT NULL DEFAULT 0")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            type TEXT NOT NULL DEFAULT 'channel_upload',
            media_id INTEGER NOT NULL,
            author_id INTEGER NOT NULL,
            is_read INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (media_id) REFERENCES media(id) ON DELETE CASCADE,
            FOREIGN KEY (author_id) REFERENCES authors(id) ON DELETE CASCADE
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_notifications_user_unread
        ON notifications(user_id, is_read, created_at DESC)
    """)


def _migrate_normalize_tags(conn):
    """Сливает дубликаты тегов (Образование/образование) и синхронизирует wiki с контентом."""
    for row in conn.execute("SELECT id, name FROM standard_tags").fetchall():
        norm = normalize_tag_name(row["name"])
        if norm == row["name"]:
            continue
        dup = conn.execute(
            "SELECT id FROM standard_tags WHERE name = ? AND id != ?",
            (norm, row["id"]),
        ).fetchone()
        if dup:
            conn.execute("DELETE FROM standard_tags WHERE id = ?", (row["id"],))
        else:
            conn.execute("UPDATE standard_tags SET name = ? WHERE id = ?", (norm, row["id"]))

    canonical = {}
    for row in conn.execute("SELECT id, name FROM tags ORDER BY id").fetchall():
        norm = normalize_tag_name(row["name"])
        if norm in canonical:
            keep_id = canonical[norm]
            dup_id = row["id"]
            for mt in conn.execute(
                "SELECT media_id, votes FROM media_tags WHERE tag_id = ?", (dup_id,)
            ).fetchall():
                conn.execute(
                    """INSERT INTO media_tags (media_id, tag_id, votes) VALUES (?, ?, ?)
                       ON CONFLICT(media_id, tag_id) DO UPDATE SET
                       votes = MAX(media_tags.votes, excluded.votes)""",
                    (mt["media_id"], keep_id, mt["votes"]),
                )
                conn.execute(
                    "DELETE FROM media_tags WHERE media_id = ? AND tag_id = ?",
                    (mt["media_id"], dup_id),
                )
            conn.execute("DELETE FROM tags WHERE id = ?", (dup_id,))
        else:
            canonical[norm] = row["id"]
            if norm != row["name"]:
                conn.execute("UPDATE tags SET name = ? WHERE id = ?", (norm, row["id"]))

    for row in conn.execute("SELECT name FROM standard_tags").fetchall():
        conn.execute("INSERT OR IGNORE INTO tags (name) VALUES (?)", (row["name"],))

def cleanup_zero_votes_tags():
    """Удаляет теги с 0 голосов, которые находятся в таком состоянии дольше 1 минуты."""
    with closing(get_db_connection()) as conn:
        with conn:
            # Находим медиа-теги с 0 голосов
            # Примечание: Для полноценного отслеживания "времени обнуления" нужно было бы поле last_updated в media_tags.
            # Но мы можем упростить: если голосов 0, мы удаляем их (логика "дольше минуты" в фоновом процессе).
            conn.execute("DELETE FROM media_tags WHERE votes = 0 AND COALESCE(is_author_tag, 0) = 0")
            # Также удаляем сиротские теги (не связанные ни с чем), если они не стандартные
            conn.execute("""
                DELETE FROM tags
                WHERE id NOT IN (SELECT tag_id FROM media_tags)
                AND name NOT IN (SELECT name FROM standard_tags)
            """)

def get_standard_tags():
    with closing(get_db_connection()) as conn:
        rows = conn.execute("SELECT * FROM standard_tags ORDER BY name").fetchall()
        return [dict(r) for r in rows]

def update_standard_tag(tag_id, name, description, color):
    name = normalize_tag_name(name)
    with closing(get_db_connection()) as conn:
        with conn:
            conn.execute("UPDATE standard_tags SET name=?, description=?, color=? WHERE id=?", 
                         (name, description, color, tag_id))
            conn.execute("INSERT OR IGNORE INTO tags (name) VALUES (?)", (name,))

def add_standard_tag(name, description, color):
    name = normalize_tag_name(name)
    with closing(get_db_connection()) as conn:
        with conn:
            conn.execute("INSERT INTO standard_tags (name, description, color) VALUES (?, ?, ?)", 
                         (name, description, color))
            conn.execute("INSERT OR IGNORE INTO tags (name) VALUES (?)", (name,))

def delete_standard_tag(tag_id):
    with closing(get_db_connection()) as conn:
        with conn:
            conn.execute("DELETE FROM standard_tags WHERE id=?", (tag_id,))

def toggle_like(user_id, media_id, is_like):
    """Добавляет, обновляет или УДАЛЯЕТ лайк/дизлайк (если кликнули повторно)."""
    with closing(get_db_connection()) as conn:
        with conn:
            existing = conn.execute("SELECT is_like FROM likes WHERE user_id = ? AND media_id = ?", (user_id, media_id)).fetchone()
            if existing:
                if existing['is_like'] == is_like:
                    # Повторный клик по тому же - убираем оценку
                    conn.execute("DELETE FROM likes WHERE user_id = ? AND media_id = ?", (user_id, media_id))
                    return "removed"
                else:
                    # Смена лайка на дизлайк или наоборот
                    conn.execute("UPDATE likes SET is_like = ?, like_date = ? WHERE user_id = ? AND media_id = ?", 
                                 (is_like, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), user_id, media_id))
                    return "updated"
            else:
                conn.execute("INSERT INTO likes (user_id, media_id, is_like, like_date) VALUES (?, ?, ?, ?)",
                             (user_id, media_id, is_like, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
                return "added"

def vote_tag_limited(user_id, media_id, tag_id, delta):
    """Голосование за тег: один голос от одного пользователя на один тег одного медиа."""
    with closing(get_db_connection()) as conn:
        author_tag = conn.execute(
            "SELECT 1 FROM media_tags WHERE media_id = ? AND tag_id = ? AND COALESCE(is_author_tag, 0) = 1",
            (media_id, tag_id),
        ).fetchone()
        if author_tag:
            return "forbidden"
        with conn:
            # Проверяем, голосовал ли уже
            existing = conn.execute("SELECT vote FROM tag_user_votes WHERE user_id=? AND media_id=? AND tag_id=?", 
                                    (user_id, media_id, tag_id)).fetchone()
            
            delta_val = 1 if delta > 0 else -1
            
            if existing:
                if existing['vote'] == delta_val:
                    # Убираем голос
                    conn.execute("DELETE FROM tag_user_votes WHERE user_id=? AND media_id=? AND tag_id=?", 
                                 (user_id, media_id, tag_id))
                    conn.execute("UPDATE media_tags SET votes = votes - ? WHERE media_id=? AND tag_id=?", 
                                 (delta_val, media_id, tag_id))
                    return "removed"
                else:
                    # Меняем голос с +1 на -1 (или наоборот)
                    conn.execute("UPDATE tag_user_votes SET vote = ? WHERE user_id=? AND media_id=? AND tag_id=?", 
                                 (delta_val, user_id, media_id, tag_id))
                    conn.execute("UPDATE media_tags SET votes = votes + ? WHERE media_id=? AND tag_id=?", 
                                 (delta_val * 2, media_id, tag_id))
                    return "updated"
            else:
                # Новый голос
                conn.execute("INSERT INTO tag_user_votes (user_id, media_id, tag_id, vote) VALUES (?, ?, ?, ?)", 
                             (user_id, media_id, tag_id, delta_val))
                conn.execute("UPDATE media_tags SET votes = votes + ? WHERE media_id=? AND tag_id=?", 
                             (delta_val, media_id, tag_id))
                return "added"

def get_media_tags_extended(media_id):
    """Возвращает теги медиа с пометкой стандартного и авторского тега."""
    with closing(get_db_connection()) as conn:
        rows = conn.execute("""
            SELECT t.id, t.name, mt.votes, COALESCE(mt.is_author_tag, 0) AS is_author_tag,
                   (SELECT color FROM standard_tags WHERE name = t.name) as std_color
            FROM tags t
            JOIN media_tags mt ON t.id = mt.tag_id
            WHERE mt.media_id = ?
            ORDER BY COALESCE(mt.is_author_tag, 0) DESC, (std_color IS NOT NULL) DESC, mt.votes DESC
        """, (media_id,)).fetchall()
        return [dict(r) for r in rows]

def get_media_by_tag_name(tag_name, media_type=None):
    """Поиск контента по конкретному тегу."""
    tag_name = normalize_tag_name(tag_name)
    if not tag_name:
        return []
    with closing(get_db_connection()) as conn:
        base_query = """
            SELECT m.*, COALESCE(a.first_name,'') || ' ' || COALESCE(a.second_name,'') AS author_name
            FROM media m
            JOIN authors a ON m.author_id = a.id
            JOIN media_tags mt ON m.id = mt.media_id
            JOIN tags t ON mt.tag_id = t.id
            WHERE t.name = ?
        """
        params = [tag_name]
        if media_type:
            base_query += " AND m.media_type = ?"
            params.append(media_type)
        
        rows = conn.execute(base_query + " ORDER BY m.upload_date DESC", params).fetchall()
        return [dict(r) for r in rows]

def search_media(search_term=None, media_type=None):
    with closing(get_db_connection()) as conn:
        base_query = """
            SELECT m.id, m.title, m.description, m.upload_date,
                   COALESCE(a.first_name,'') || ' ' || COALESCE(a.second_name,'') AS author_name,
                   u.email AS author_email,
                   m.media_type, m.status, m.file_path, m.thumbnail_path, m.views
            FROM media m
            JOIN authors a ON m.author_id=a.id
            JOIN users u ON a.user_id=u.id
        """
        params, wc = [],[]

        if media_type:
            wc.append("m.media_type = ?")
            params.append(media_type)

        if search_term and search_term.strip():
            raw = search_term.strip()
            if raw.startswith("#"):
                raw = raw[1:]
            term = f"%{normalize_tag_name(raw)}%"
            wc.append("""
                (m.title LIKE ? OR m.description LIKE ? OR m.id IN (
                    SELECT mt.media_id
                    FROM media_tags mt
                    JOIN tags t ON mt.tag_id = t.id
                    WHERE t.name LIKE ?
                ))
            """)
            params.extend([term, term, term])

        final_query = base_query + (" WHERE " + " AND ".join(wc) if wc else "") + " ORDER BY m.upload_date DESC"
        results = conn.execute(final_query, params).fetchall()
        return [dict(r) for r in results]

def get_media_by_type(media_type):
    return search_media(media_type=media_type)

def add_user(username, email, password, role='viewer', consent_accepted_at=None):
    with closing(get_db_connection()) as conn:
        try:
            with conn:
                reg_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                salt = os.urandom(16)
                pwd_hash = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, 100000)
                db_password = salt.hex() + ':' + pwd_hash.hex()
                
                cursor = conn.execute(
                    "INSERT INTO users (username, email, password_hash, registration_date, role, consent_accepted_at) VALUES (?, ?, ?, ?, ?, ?)",
                    (username, email, db_password, reg_date, role, consent_accepted_at)
                )
                user_id = cursor.lastrowid
                # Automatically create an author profile for each user to make things seamless
                conn.execute(
                    "INSERT OR IGNORE INTO authors (user_id, first_name, second_name, bio) VALUES (?, ?, ?, ?)",
                    (user_id, username, "", "Новый автор")
                )
            return True
        except sqlite3.IntegrityError:
            return False

def verify_user_credentials(username_or_email, password):
    with closing(get_db_connection()) as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE username = ? OR email = ?",
            (username_or_email, username_or_email)
        ).fetchone()
        if not row:
            return None
        
        stored_hash = row['password_hash']
        try:
            salt_hex, hash_hex = stored_hash.split(':')
            salt = bytes.fromhex(salt_hex)
            pwd_hash = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, 100000)
            if pwd_hash.hex() == hash_hex:
                return dict(row)
        except Exception:
            pass
        return None

def get_user_by_id(user_id):
    with closing(get_db_connection()) as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return dict(row) if row else None

def get_author_by_user_id(user_id):
    with closing(get_db_connection()) as conn:
        row = conn.execute("SELECT * FROM authors WHERE user_id = ?", (user_id,)).fetchone()
        return dict(row) if row else None


def get_author_public(author_id: int) -> dict | None:
    with closing(get_db_connection()) as conn:
        row = conn.execute("""
            SELECT a.*, u.username, u.id AS user_id,
                   (SELECT COUNT(*) FROM subscriptions s WHERE s.author_id = a.id) AS subscriber_count,
                   (SELECT COUNT(*) FROM media m WHERE m.author_id = a.id AND m.status = 'published') AS media_count
            FROM authors a
            JOIN users u ON a.user_id = u.id
            WHERE a.id = ?
        """, (author_id,)).fetchone()
        return dict(row) if row else None


def get_subscriber_count(author_id: int) -> int:
    with closing(get_db_connection()) as conn:
        return conn.execute(
            "SELECT COUNT(*) FROM subscriptions WHERE author_id = ?", (author_id,)
        ).fetchone()[0]


def is_subscribed(user_id: int, author_id: int) -> bool:
    with closing(get_db_connection()) as conn:
        return bool(conn.execute(
            "SELECT 1 FROM subscriptions WHERE user_id = ? AND author_id = ?",
            (user_id, author_id),
        ).fetchone())


def toggle_subscription(user_id: int, author_id: int) -> tuple[bool, int]:
    """Возвращает (подписан ли сейчас, число подписчиков)."""
    with closing(get_db_connection()) as conn:
        with conn:
            exists = conn.execute(
                "SELECT 1 FROM subscriptions WHERE user_id = ? AND author_id = ?",
                (user_id, author_id),
            ).fetchone()
            if exists:
                conn.execute(
                    "DELETE FROM subscriptions WHERE user_id = ? AND author_id = ?",
                    (user_id, author_id),
                )
                subscribed = False
            else:
                conn.execute(
                    "INSERT INTO subscriptions (user_id, author_id, created_at) VALUES (?, ?, ?)",
                    (user_id, author_id, datetime.now().strftime('%Y-%m-%d %H:%M:%S')),
                )
                subscribed = True
        count = get_subscriber_count(author_id)
        return subscribed, count


def get_subscribed_author_ids(user_id: int) -> list[int]:
    with closing(get_db_connection()) as conn:
        rows = conn.execute(
            "SELECT author_id FROM subscriptions WHERE user_id = ?", (user_id,)
        ).fetchall()
        return [r["author_id"] for r in rows]


def list_media_feed(
    media_type: str | None = None,
    search_term: str | None = None,
    tag_name: str | None = None,
    author_id: int | None = None,
    page: int = 1,
    limit: int = FEED_PAGE_SIZE,
) -> tuple[list[dict], bool]:
    """Публичная лента с пагинацией. Возвращает (items, has_more)."""
    page = max(1, page)
    limit = max(1, min(limit, 48))
    offset = (page - 1) * limit

    base = """
        SELECT m.id, m.title, m.description, m.upload_date, m.media_type,
               m.file_path, m.thumbnail_path, m.views, m.author_id, m.status,
               COALESCE(a.first_name,'') || ' ' || COALESCE(a.second_name,'') AS author_name,
               u.username AS owner_username
        FROM media m
        JOIN authors a ON m.author_id = a.id
        JOIN users u ON a.user_id = u.id
    """
    wc = ["m.status = 'published'"]
    params: list = []

    if media_type:
        wc.append("m.media_type = ?")
        params.append(media_type)
    if author_id:
        wc.append("m.author_id = ?")
        params.append(author_id)
    if tag_name:
        tag_name = normalize_tag_name(tag_name)
        wc.append("""
            m.id IN (
                SELECT mt.media_id FROM media_tags mt
                JOIN tags t ON mt.tag_id = t.id WHERE t.name = ?
            )
        """)
        params.append(tag_name)
    if search_term and search_term.strip():
        raw = search_term.strip()
        if raw.startswith("#"):
            raw = raw[1:]
        term = f"%{normalize_tag_name(raw)}%"
        wc.append("""
            (m.title LIKE ? OR m.description LIKE ? OR m.id IN (
                SELECT mt.media_id FROM media_tags mt
                JOIN tags t ON mt.tag_id = t.id WHERE t.name LIKE ?
            ))
        """)
        params.extend([term, term, term])

    where = " WHERE " + " AND ".join(wc)
    query = base + where + " ORDER BY m.upload_date DESC LIMIT ? OFFSET ?"
    params.extend([limit + 1, offset])

    with closing(get_db_connection()) as conn:
        rows = conn.execute(query, params).fetchall()
    items = [dict(r) for r in rows[:limit]]
    has_more = len(rows) > limit
    return items, has_more


def get_continue_watching(user_id: int, limit: int = 12) -> list[dict]:
    with closing(get_db_connection()) as conn:
        rows = conn.execute("""
            SELECT m.*, h.viewed_at,
                   COALESCE(a.first_name,'') || ' ' || COALESCE(a.second_name,'') AS author_name,
                   u.username AS owner_username
            FROM (
                SELECT media_id, MAX(viewed_at) AS viewed_at
                FROM history WHERE user_id = ?
                GROUP BY media_id
            ) h
            JOIN media m ON m.id = h.media_id
            JOIN authors a ON m.author_id = a.id
            JOIN users u ON a.user_id = u.id
            WHERE m.status = 'published'
            ORDER BY h.viewed_at DESC
            LIMIT ?
        """, (user_id, limit)).fetchall()
        return [dict(r) for r in rows]


def user_owns_media(user_id: int, media_id: int) -> bool:
    with closing(get_db_connection()) as conn:
        row = conn.execute("""
            SELECT 1 FROM media m
            JOIN authors a ON m.author_id = a.id
            WHERE m.id = ? AND a.user_id = ?
        """, (media_id, user_id)).fetchone()
        return bool(row)


def update_media_fields(media_id: int, title: str, description: str, thumbnail_path: str | None = None) -> bool:
    with closing(get_db_connection()) as conn:
        try:
            with conn:
                if thumbnail_path is not None:
                    conn.execute(
                        "UPDATE media SET title = ?, description = ?, thumbnail_path = ? WHERE id = ?",
                        (title.strip(), (description or "").strip(), thumbnail_path, media_id),
                    )
                else:
                    conn.execute(
                        "UPDATE media SET title = ?, description = ? WHERE id = ?",
                        (title.strip(), (description or "").strip(), media_id),
                    )
            return True
        except Exception:
            return False

def add_or_update_author_profile(user_id, first_name, second_name, bio=None, phone=None):
    with closing(get_db_connection()) as conn:
        try:
            with conn:
                author_profile = conn.execute("SELECT id FROM authors WHERE user_id = ?", (user_id,)).fetchone()
                if author_profile:
                    conn.execute("UPDATE authors SET first_name=?, second_name=?, bio=?, phone=? WHERE id=?",
                                 (first_name, second_name, bio, phone, author_profile['id']))
                else:
                    conn.execute("INSERT INTO authors (user_id, first_name, second_name, bio, phone) VALUES (?,?,?,?,?)",
                                (user_id, first_name, second_name, bio, phone))
            return True
        except sqlite3.Error:
            return False


def set_author_personal_tag(user_id: int, tag_name: str) -> tuple[bool, str]:
    """Задаёт персональный тег автора (уникальный среди авторов)."""
    norm = validate_personal_tag_name(tag_name)
    if not norm:
        return False, "Тег: 2–32 символа, только буквы, цифры, _ и -"
    with closing(get_db_connection()) as conn:
        author = conn.execute("SELECT id, personal_tag FROM authors WHERE user_id = ?", (user_id,)).fetchone()
        if not author:
            return False, "Сначала создайте профиль автора"
        taken = conn.execute(
            "SELECT id FROM authors WHERE personal_tag = ? AND id != ?",
            (norm, author["id"]),
        ).fetchone()
        if taken:
            return False, "Этот персональный тег уже занят другим автором"
        with conn:
            old_tag = author["personal_tag"]
            conn.execute("UPDATE authors SET personal_tag = ? WHERE id = ?", (norm, author["id"]))
            conn.execute("INSERT OR IGNORE INTO tags (name) VALUES (?)", (norm,))
            if old_tag and old_tag != norm:
                tag_row = conn.execute("SELECT id FROM tags WHERE name = ?", (old_tag,)).fetchone()
                if tag_row:
                    conn.execute(
                        "DELETE FROM media_tags WHERE tag_id = ? AND COALESCE(is_author_tag, 0) = 1 AND media_id IN (SELECT id FROM media WHERE author_id = ?)",
                        (tag_row["id"], author["id"]),
                    )
        return True, norm


def clear_author_personal_tag(user_id: int) -> bool:
    with closing(get_db_connection()) as conn:
        author = conn.execute("SELECT id, personal_tag FROM authors WHERE user_id = ?", (user_id,)).fetchone()
        if not author or not author["personal_tag"]:
            return False
        with conn:
            tag_row = conn.execute("SELECT id FROM tags WHERE name = ?", (author["personal_tag"],)).fetchone()
            if tag_row:
                conn.execute(
                    "DELETE FROM media_tags WHERE tag_id = ? AND COALESCE(is_author_tag, 0) = 1 AND media_id IN (SELECT id FROM media WHERE author_id = ?)",
                    (tag_row["id"], author["id"]),
                )
            conn.execute("UPDATE authors SET personal_tag = NULL WHERE id = ?", (author["id"],))
        return True


def toggle_media_author_tag(user_id: int, media_id: int) -> tuple[bool, str, str]:
    """Добавляет или убирает персональный тег автора на своём медиа."""
    with closing(get_db_connection()) as conn:
        row = conn.execute("""
            SELECT m.author_id, a.personal_tag, a.user_id
            FROM media m
            JOIN authors a ON m.author_id = a.id
            WHERE m.id = ?
        """, (media_id,)).fetchone()
        if not row or row["user_id"] != user_id:
            return False, "error", "Доступ запрещён"
        personal_tag = row["personal_tag"]
        if not personal_tag:
            return False, "error", "Сначала задайте персональный тег в личном кабинете"
        with conn:
            conn.execute("INSERT OR IGNORE INTO tags (name) VALUES (?)", (personal_tag,))
            tag_row = conn.execute("SELECT id FROM tags WHERE name = ?", (personal_tag,)).fetchone()
            if not tag_row:
                return False, "error", "Ошибка тега"
            tag_id = tag_row["id"]
            existing = conn.execute(
                "SELECT COALESCE(is_author_tag, 0) AS is_author_tag FROM media_tags WHERE media_id = ? AND tag_id = ?",
                (media_id, tag_id),
            ).fetchone()
            if existing:
                if existing["is_author_tag"]:
                    conn.execute("DELETE FROM media_tags WHERE media_id = ? AND tag_id = ?", (media_id, tag_id))
                    return True, "removed", personal_tag
                conn.execute(
                    "UPDATE media_tags SET is_author_tag = 1, votes = CASE WHEN votes < 1 THEN 1 ELSE votes END WHERE media_id = ? AND tag_id = ?",
                    (media_id, tag_id),
                )
                return True, "added", personal_tag
            conn.execute(
                "INSERT INTO media_tags (media_id, tag_id, votes, is_author_tag) VALUES (?, ?, 1, 1)",
                (media_id, tag_id),
            )
        return True, "added", personal_tag


def is_reserved_personal_tag(name: str) -> bool:
    norm = normalize_tag_name(name)
    if not norm:
        return False
    with closing(get_db_connection()) as conn:
        return bool(conn.execute(
            "SELECT 1 FROM authors WHERE personal_tag = ?", (norm,)
        ).fetchone())

def get_eligible_authors_for_dropdown():
    with closing(get_db_connection()) as conn:
        authors = conn.execute("""
            SELECT a.id, u.email, a.first_name, a.second_name 
            FROM authors a JOIN users u ON a.user_id=u.id ORDER BY u.email
        """).fetchall()
        return [{"id": r['id'], "name": f"{r['first_name'] or ''} {r['second_name'] or ''} ({r['email']})".strip()} for r in authors]

def add_media(title, description, author_id, media_type, file_path, thumbnail_path=None, views=0) -> int | None:
    with closing(get_db_connection()) as conn:
        try:
            with conn:
                cur = conn.execute("""
                    INSERT INTO media (title, description, upload_date, author_id, media_type, file_path, thumbnail_path, status, views) 
                    VALUES (?,?,?,?,?,?,?, 'published', ?)
                """, (title, description, datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                      author_id, media_type, file_path, thumbnail_path, views))
            return int(cur.lastrowid)
        except Exception as e:
            print(f"Ошибка при добавлении медиа: {e}")
            return None


def notify_subscribers_new_upload(author_id: int, media_id: int) -> int:
    """Уведомляет подписчиков канала о новой публикации. Возвращает число созданных уведомлений."""
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    with closing(get_db_connection()) as conn:
        author_user = conn.execute(
            "SELECT user_id FROM authors WHERE id = ?", (author_id,)
        ).fetchone()
        author_user_id = author_user["user_id"] if author_user else None
        rows = conn.execute(
            "SELECT user_id FROM subscriptions WHERE author_id = ?", (author_id,)
        ).fetchall()
        created = 0
        with conn:
            for row in rows:
                uid = row["user_id"]
                if uid == author_user_id:
                    continue
                conn.execute("""
                    INSERT INTO notifications (user_id, type, media_id, author_id, is_read, created_at)
                    VALUES (?, 'channel_upload', ?, ?, 0, ?)
                """, (uid, media_id, author_id, now))
                created += 1
        return created


def get_notifications(user_id: int, limit: int = 20) -> list[dict]:
    limit = max(1, min(limit, 50))
    with closing(get_db_connection()) as conn:
        rows = conn.execute("""
            SELECT n.id, n.type, n.media_id, n.author_id, n.is_read, n.created_at,
                   m.title AS media_title, m.media_type, m.thumbnail_path,
                   COALESCE(NULLIF(TRIM(COALESCE(a.first_name,'') || ' ' || COALESCE(a.second_name,'')), ''), u.username) AS author_name,
                   u.username AS author_username
            FROM notifications n
            JOIN media m ON n.media_id = m.id
            JOIN authors a ON n.author_id = a.id
            JOIN users u ON a.user_id = u.id
            WHERE n.user_id = ?
            ORDER BY n.created_at DESC
            LIMIT ?
        """, (user_id, limit)).fetchall()
        return [dict(r) for r in rows]


def get_unread_notification_count(user_id: int) -> int:
    with closing(get_db_connection()) as conn:
        return conn.execute(
            "SELECT COUNT(*) FROM notifications WHERE user_id = ? AND is_read = 0",
            (user_id,),
        ).fetchone()[0]


def mark_notifications_read(user_id: int, notification_ids: list[int] | None = None) -> int:
    with closing(get_db_connection()) as conn:
        with conn:
            if notification_ids:
                placeholders = ",".join("?" * len(notification_ids))
                cur = conn.execute(
                    f"UPDATE notifications SET is_read = 1 WHERE user_id = ? AND id IN ({placeholders})",
                    [user_id, *notification_ids],
                )
            else:
                cur = conn.execute(
                    "UPDATE notifications SET is_read = 1 WHERE user_id = ? AND is_read = 0",
                    (user_id,),
                )
        return cur.rowcount

def attach_tags_to_media(media_id, tag_names, initial_votes=3):
    with closing(get_db_connection()) as conn:
        with conn:
            for name in tag_names:
                name = normalize_tag_name(name)
                if not name:
                    continue
                conn.execute("INSERT OR IGNORE INTO tags (name) VALUES (?)", (name,))
                tag_row = conn.execute("SELECT id FROM tags WHERE name = ?", (name,)).fetchone()
                if tag_row:
                    conn.execute(
                        "INSERT OR IGNORE INTO media_tags (media_id, tag_id, votes) VALUES (?, ?, ?)",
                        (media_id, tag_row['id'], initial_votes)
                    )

def get_media_count():
    with closing(get_db_connection()) as conn:
        return conn.execute("SELECT COUNT(*) FROM media").fetchone()[0]

def create_report(reporter_id, reported_author_id, media_id, reason, details=""):
    if reason not in REPORT_REASONS:
        return False, "Некорректная причина"
    with closing(get_db_connection()) as conn:
        if media_id:
            existing = conn.execute(
                "SELECT 1 FROM reports WHERE reporter_id=? AND media_id=? AND reason=? AND status='pending'",
                (reporter_id, media_id, reason),
            ).fetchone()
        else:
            existing = conn.execute(
                """SELECT 1 FROM reports WHERE reporter_id=? AND reported_author_id=?
                   AND media_id IS NULL AND reason=? AND status='pending'""",
                (reporter_id, reported_author_id, reason),
            ).fetchone()
        if existing:
            return False, "Вы уже отправили жалобу по этой причине"
        try:
            with conn:
                conn.execute(
                    """INSERT INTO reports (reporter_id, reported_author_id, media_id, reason, details, created_at)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (reporter_id, reported_author_id, media_id, reason, details.strip(),
                     datetime.now().strftime('%Y-%m-%d %H:%M:%S')),
                )
            return True, "Жалоба отправлена"
        except sqlite3.Error:
            return False, "Ошибка сохранения"

def get_all_reports():
    with closing(get_db_connection()) as conn:
        rows = conn.execute("""
            SELECT r.*, u.username AS reporter_username,
                   COALESCE(a.first_name,'') || ' ' || COALESCE(a.second_name,'') AS reported_author_name,
                   m.title AS media_title
            FROM reports r
            JOIN users u ON r.reporter_id = u.id
            JOIN authors a ON r.reported_author_id = a.id
            LEFT JOIN media m ON r.media_id = m.id
            ORDER BY r.created_at DESC
        """).fetchall()
        return [dict(r) for r in rows]

def update_report_status(report_id, status):
    if status not in ('pending', 'reviewed', 'dismissed'):
        return False
    with closing(get_db_connection()) as conn:
        with conn:
            conn.execute("UPDATE reports SET status=? WHERE id=?", (status, report_id))
        return True

def add_like(user_id, media_id, is_like):
    """Добавляет или обновляет лайк (1) или дизлайк (-1)."""
    with closing(get_db_connection()) as conn:
        try:
            with conn:
                conn.execute("""
                    INSERT INTO likes (user_id, media_id, is_like, like_date)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(user_id, media_id) DO UPDATE SET is_like = excluded.is_like, like_date = excluded.like_date
                """, (user_id, media_id, is_like, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
            return True
        except Exception as e:
            print(f"Ошибка при добавлении лайка: {e}")
            return False

def get_likes_count(media_id):
    """Возвращает количество лайков и дизлайков."""
    with closing(get_db_connection()) as conn:
        likes = conn.execute("SELECT count(*) FROM likes WHERE media_id = ? AND is_like = 1", (media_id,)).fetchone()[0]
        dislikes = conn.execute("SELECT count(*) FROM likes WHERE media_id = ? AND is_like = -1", (media_id,)).fetchone()[0]
        return {"likes": likes, "dislikes": dislikes}

def get_user_like(user_id, media_id):
    """Возвращает лайк конкретного пользователя (1, -1 или 0)."""
    if not user_id:
        return 0
    with closing(get_db_connection()) as conn:
        row = conn.execute("SELECT is_like FROM likes WHERE user_id = ? AND media_id = ?", (user_id, media_id)).fetchone()
        return row['is_like'] if row else 0

def create_playlist(user_id, name, description=""):
    with closing(get_db_connection()) as conn:
        try:
            with conn:
                conn.execute(
                    "INSERT INTO playlists (user_id, name, description, creation_date) VALUES (?, ?, ?, ?)",
                    (user_id, name, description, datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
                )
            return True
        except sqlite3.IntegrityError:
            return False

def add_to_playlist(playlist_id, media_id):
    with closing(get_db_connection()) as conn:
        try:
            with conn:
                conn.execute(
                    "INSERT OR IGNORE INTO playlist_media (playlist_id, media_id, added_date) VALUES (?, ?, ?)",
                    (playlist_id, media_id, datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
                )
            return True
        except Exception:
            return False

def remove_from_playlist(playlist_id, media_id):
    with closing(get_db_connection()) as conn:
        try:
            with conn:
                conn.execute(
                    "DELETE FROM playlist_media WHERE playlist_id = ? AND media_id = ?",
                    (playlist_id, media_id)
                )
            return True
        except Exception:
            return False

def get_user_playlists(user_id):
    with closing(get_db_connection()) as conn:
        rows = conn.execute("SELECT * FROM playlists WHERE user_id = ? ORDER BY creation_date DESC", (user_id,)).fetchall()
        return [dict(r) for r in rows]

def get_playlist_details(playlist_id):
    with closing(get_db_connection()) as conn:
        row = conn.execute("SELECT * FROM playlists WHERE id = ?", (playlist_id,)).fetchone()
        return dict(row) if row else None

def get_playlist_media(playlist_id):
    with closing(get_db_connection()) as conn:
        rows = conn.execute("""
            SELECT m.*, COALESCE(a.first_name,'') || ' ' || COALESCE(a.second_name,'') AS author_name
            FROM media m
            JOIN playlist_media pm ON m.id = pm.media_id
            JOIN authors a ON m.author_id = a.id
            WHERE pm.playlist_id = ?
            ORDER BY pm.added_date DESC
        """, (playlist_id,)).fetchall()
        return [dict(r) for r in rows]

def log_view_history(user_id, media_id):
    if not user_id:
        return
    with closing(get_db_connection()) as conn:
        try:
            with conn:
                # Log a view history
                conn.execute(
                    "INSERT INTO history (user_id, media_id, viewed_at) VALUES (?, ?, ?)",
                    (user_id, media_id, datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
                )
        except Exception:
            pass

def get_user_history(user_id, limit=20):
    with closing(get_db_connection()) as conn:
        rows = conn.execute("""
            SELECT m.*, h.viewed_at, COALESCE(a.first_name,'') || ' ' || COALESCE(a.second_name,'') AS author_name
            FROM media m
            JOIN history h ON m.id = h.media_id
            JOIN authors a ON m.author_id = a.id
            WHERE h.user_id = ?
            ORDER BY h.viewed_at DESC
            LIMIT ?
        """, (user_id, limit)).fetchall()
        return [dict(r) for r in rows]

def get_all_users():
    with closing(get_db_connection()) as conn:
        rows = conn.execute("SELECT id, username, email, registration_date, role FROM users ORDER BY registration_date DESC").fetchall()
        return [dict(r) for r in rows]

def get_all_media_admin():
    with closing(get_db_connection()) as conn:
        rows = conn.execute("""
            SELECT m.*, COALESCE(a.first_name,'') || ' ' || COALESCE(a.second_name,'') AS author_name, u.username as author_username
            FROM media m
            JOIN authors a ON m.author_id = a.id
            JOIN users u ON a.user_id = u.id
            ORDER BY m.upload_date DESC
        """).fetchall()
        return [dict(r) for r in rows]

def delete_user(user_id):
    with closing(get_db_connection()) as conn:
        try:
            with conn:
                conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
            return True
        except Exception:
            return False

def delete_media(media_id, base_dir: str | None = None):
    base = base_dir or _BASE_DIR
    with closing(get_db_connection()) as conn:
        try:
            media = conn.execute(
                "SELECT file_path, thumbnail_path FROM media WHERE id = ?", (media_id,)
            ).fetchone()
            if media:
                for rel in (media["file_path"], media["thumbnail_path"]):
                    if not rel:
                        continue
                    path = os.path.normpath(os.path.join(base, rel.replace("/", os.sep)))
                    if os.path.isfile(path):
                        try:
                            os.remove(path)
                        except OSError:
                            pass
            with conn:
                conn.execute("DELETE FROM media WHERE id = ?", (media_id,))
            return True
        except Exception:
            return False
