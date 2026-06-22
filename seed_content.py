"""Заполнение БД демо-контентом со стоковых источников."""
import os
import random
import shutil
import ssl
import time
import urllib.request
from urllib.parse import quote
import database

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOADS = os.path.join(_BASE_DIR, "uploads")
STOCK = os.path.join(UPLOADS, "stock")
THUMBS = os.path.join(UPLOADS, "thumbs")
DEMO_THUMBS_DIR = os.path.join(_BASE_DIR, "static", "img", "demo")

CREATORS = [
    ("studio_nova", "nova@demo.local", "Нова", "Студия", ["технологии", "образование"]),
    ("pixel_anna", "anna@demo.local", "Анна", "Пиксель", ["развлечение", "музыка"]),
    ("doc_ivan", "ivan@demo.local", "Иван", "Док", ["образование", "важное"]),
    ("art_luna", "luna@demo.local", "Луна", "Арт", ["музыка", "развлечение"]),
]

# Каждый элемент: метаданные строго соответствуют реальному файлу/картинке.
DEMO_ITEMS = [
    {
        "media_type": "video",
        "stock_name": "flower",
        "url": "https://interactive-examples.mdn.mozilla.net/media/cc0-videos/flower.mp4",
        "title": "Раскрывающийся цветок",
        "description": "Короткий ролик с макросъёмкой цветка в движении (демо CC0).",
        "tags": ["развлечение", "образование"],
        "views": 1240,
    },
    {
        "media_type": "video",
        "stock_name": "bbb",
        "url": "https://www.w3schools.com/html/mov_bbb.mp4",
        "title": "Big Buck Bunny",
        "description": "Анимационный короткометражный фильм с зайцем Баки. Blender Foundation, открытая лицензия.",
        "tags": ["развлечение"],
        "views": 3560,
    },
    {
        "media_type": "video",
        "stock_name": "movie",
        "url": "https://www.w3schools.com/html/movie.mp4",
        "title": "Морские волны",
        "description": "Короткий ролик с видом на море. Демонстрационное видео для HTML5-плеера.",
        "tags": ["развлечение"],
        "views": 890,
    },
    {
        "media_type": "image",
        "stock_name": "item_6_image",
        "title": "Городской закат",
        "description": "Закат над морским пляжем, тёплые оттенки неба.",
        "tags": ["развлечение"],
        "views": 420,
    },
    {
        "media_type": "image",
        "stock_name": "item_7_image",
        "title": "Рабочий стол",
        "description": "Минималистичная рабочая зона с компьютером.",
        "tags": ["технологии"],
        "views": 310,
    },
    {
        "media_type": "image",
        "stock_name": "item_8_image",
        "title": "Архитектурная геометрия",
        "description": "Современный архитектурный проход с геометричными линиями.",
        "tags": ["развлечение"],
        "views": 180,
    },
    {
        "media_type": "image",
        "stock_name": "item_9_image",
        "title": "Горы и озеро",
        "description": "Вид на горную вершину Эверест с ледником.",
        "tags": ["развлечение"],
        "views": 670,
    },
    {
        "media_type": "image",
        "stock_name": "item_10_image",
        "title": "Чашка кофе",
        "description": "Небольшая чашка кофе крупным планом.",
        "tags": ["образование"],
        "views": 290,
    },
    {
        "media_type": "image",
        "stock_name": "item_11_image",
        "title": "Ночной город",
        "description": "Ночной вид на городской пейзаж с огнями.",
        "tags": ["развлечение", "технологии"],
        "views": 810,
    },
    {
        "media_type": "audio",
        "stock_name": "item_12_audio",
        "url": "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-1.mp3",
        "title": "SoundHelix — композиция №1",
        "description": "Инструментальная электронная композиция для фона.",
        "tags": ["музыка"],
        "views": 220,
    },
    {
        "media_type": "audio",
        "stock_name": "item_13_audio",
        "url": "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-2.mp3",
        "title": "SoundHelix — композиция №2",
        "description": "Спокойный инструментальный трек.",
        "tags": ["музыка", "развлечение"],
        "views": 540,
    },
    {
        "media_type": "audio",
        "stock_name": "item_14_audio",
        "url": "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-3.mp3",
        "title": "SoundHelix — композиция №3",
        "description": "Ритмичная инструментальная композиция.",
        "tags": ["музыка"],
        "views": 380,
    },
    {
        "media_type": "document",
        "stock_name": "item_14_document",
        "title": "Гайд по тегам платформы",
        "description": "Правила использования тегов на платформе Something.",
        "tags": ["важное", "образование"],
        "views": 95,
    },
    {
        "media_type": "document",
        "stock_name": "item_15_document",
        "title": "Чеклист загрузки видео",
        "description": "Требования к форматам, обложке и описанию ролика.",
        "tags": ["важное"],
        "views": 120,
    },
    {
        "media_type": "document",
        "stock_name": "item_16_document",
        "title": "Политика модерации",
        "description": "Как обрабатываются жалобы пользователей.",
        "tags": ["важное"],
        "views": 210,
    },
    {
        "media_type": "document",
        "stock_name": "item_17_document",
        "title": "Соглашение авторов",
        "description": "Права на контент и ответственность загружающего.",
        "tags": ["важное"],
        "views": 88,
    },
]

# Тематические изображения — стабильные URL Wikimedia Commons.
IMAGE_SOURCES = {
    "item_6_image": "https://upload.wikimedia.org/wikipedia/commons/thumb/1/10/Red_Sky_at_Sunset_on_Beach.jpg/1280px-Red_Sky_at_Sunset_on_Beach.jpg",
    "item_7_image": "https://upload.wikimedia.org/wikipedia/commons/thumb/9/9a/Laptop_open_on_desk.jpg/1280px-Laptop_open_on_desk.jpg",
    "item_8_image": "https://upload.wikimedia.org/wikipedia/commons/thumb/3/3f/Walkway_with_architecture.jpg/1280px-Walkway_with_architecture.jpg",
    "item_9_image": "https://upload.wikimedia.org/wikipedia/commons/thumb/e/e7/Everest_North_Face_toward_Base_Camp_Tibet_Luca_Galuzzi_2006.jpg/1280px-Everest_North_Face_toward_Base_Camp_Tibet_Luca_Galuzzi_2006.jpg",
    "item_10_image": "https://upload.wikimedia.org/wikipedia/commons/thumb/4/45/A_small_cup_of_coffee.JPG/1280px-A_small_cup_of_coffee.JPG",
    "item_11_image": "https://upload.wikimedia.org/wikipedia/commons/thumb/0/0c/Cityscape_of_Sydney%2C_Australia_at_night.jpg/1280px-Cityscape_of_Sydney%2C_Australia_at_night.jpg",
}

def _commons_thumb(filename: str, width: int = 640) -> str:
    return f"https://commons.wikimedia.org/wiki/Special:FilePath/{quote(filename)}?width={width}"


# Превью для видео и аудио (тематические обложки).
THUMB_SOURCES = {
    "flower": _commons_thumb("Sunflower_from_Silesia2.jpg"),
    "bbb": _commons_thumb("Big_buck_bunny_poster_big.jpg"),
    "movie": _commons_thumb("Red_Sky_at_Sunset_on_Beach.jpg"),
    "item_12_audio": _commons_thumb("Piano.jpg"),
    "item_13_audio": _commons_thumb("Playing_the_steelpan.jpg"),
    "item_14_audio": _commons_thumb("Fender_Stratocaster_001.jpg"),
}

THUMB_FALLBACKS = {
    "flower": "https://interactive-examples.mdn.mozilla.net/media/cc0-images/grapefruit-slice-332-332.jpg",
    "bbb": "https://peach.blender.org/wp-content/uploads/bbb-splash.png",
    "movie": _commons_thumb("Ist_ous_sea_waves.jpg"),
}


def _download(url: str, dest: str, timeout=45) -> bool:
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    req = urllib.request.Request(url, headers={
        "User-Agent": "SomethingPlatform/1.0 (demo seed)",
        "Accept": "*/*",
    })
    last_err = None
    for verify_ssl in (True, False):
        try:
            ctx = ssl.create_default_context()
            if not verify_ssl:
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
            with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp, open(dest, "wb") as f:
                f.write(resp.read())
            return os.path.getsize(dest) > 0
        except Exception as e:
            last_err = e
            if verify_ssl:
                continue
    print(f"  skip download {url}: {last_err}")
    return False


def _download_picsum_id(image_id: int, dest: str, force: bool = False) -> bool:
    if not force and os.path.exists(dest) and os.path.getsize(dest) > 0:
        return True
    return _download(f"https://picsum.photos/id/{image_id}/1280/720", dest)


def _thumb_from_picsum(seed: str, dest: str, picsum_id: int | None = None) -> bool:
    if os.path.exists(dest) and os.path.getsize(dest) > 0:
        return True
    if picsum_id is not None:
        return _download_picsum_id(picsum_id, dest)
    urls = [
        f"https://picsum.photos/seed/{seed}/640/360",
        f"https://picsum.photos/640/360?random={hash(seed) % 10000}",
    ]
    for url in urls:
        if _download(url, dest):
            return True
    return False


def _rel_thumb_path(filename: str) -> str:
    return os.path.join("uploads", "thumbs", filename).replace("\\", "/")


def _stock_rel_path(filename: str) -> str:
    return os.path.join("uploads", "stock", filename).replace("\\", "/")


def _match_keys_for_item(item: dict) -> list[str]:
    """Ключи для поиска записей в БД по file_path."""
    keys = [item["stock_name"]]
    media_type = item["media_type"]
    if media_type == "video":
        keys.append(f"{item['stock_name']}.mp4")
    elif media_type == "audio":
        keys.extend([f"{item['stock_name']}.mp3", f"{item['stock_name']}.txt"])
    elif media_type == "image":
        keys.append(f"{item['stock_name']}.jpg")
    elif media_type == "document":
        keys.append(f"{item['stock_name']}.txt")
    return keys


def _ensure_item_thumbnail(item: dict, force: bool = False) -> str | None:
    """Возвращает относительный путь превью для демо-элемента."""
    media_type = item["media_type"]
    stock_name = item["stock_name"]

    if media_type == "image":
        disk = os.path.join(STOCK, f"{stock_name}.jpg")
        if os.path.exists(disk) and os.path.getsize(disk) > 5000:
            return _stock_rel_path(f"{stock_name}.jpg")
        return None

    if media_type == "document":
        return None

    url = THUMB_SOURCES.get(stock_name)
    fname = f"thumb_{stock_name}.jpg"
    disk = os.path.join(THUMBS, fname)
    local_src = os.path.join(DEMO_THUMBS_DIR, fname)

    if force or not os.path.exists(disk) or os.path.getsize(disk) < 5000:
        if os.path.exists(local_src) and os.path.getsize(local_src) > 5000:
            shutil.copy2(local_src, disk)
        elif url:
            urls = [url]
            fallback = THUMB_FALLBACKS.get(stock_name)
            if fallback and fallback not in urls:
                urls.append(fallback)
            for src in urls:
                if _download(src, disk):
                    break
            time.sleep(1.0)

    return _rel_thumb_path(fname) if os.path.exists(disk) and os.path.getsize(disk) > 5000 else None


def sync_demo_thumbnails(force: bool = False):
    """Обновляет превью демо-записей в БД."""
    os.makedirs(THUMBS, exist_ok=True)
    updated = 0
    with database.get_db_connection() as conn:
        rows = conn.execute(
            "SELECT id, title, description, file_path, media_type, thumbnail_path FROM media"
        ).fetchall()
        for row in rows:
            path_norm = (row["file_path"] or "").replace("\\", "/").lower()
            if "/stock/" not in path_norm:
                continue
            matched = None
            for item in DEMO_ITEMS:
                if item["media_type"] != row["media_type"]:
                    continue
                for key in _match_keys_for_item(item):
                    if key.lower() in path_norm:
                        matched = item
                        break
                if matched:
                    break
            if not matched:
                continue
            thumb = _ensure_item_thumbnail(matched, force=force)
            if not thumb:
                continue
            old = (row["thumbnail_path"] or "").replace("\\", "/")
            if old == thumb and not force:
                continue
            with conn:
                conn.execute(
                    "UPDATE media SET thumbnail_path = ? WHERE id = ?",
                    (thumb, row["id"]),
                )
            updated += 1
            print(f"  thumb: {matched['title']}")
    if updated:
        print(f"Seed: обновлено превью для {updated} записей.")
    return updated


def _ensure_stock_audio():
    """Скачивает MP3 для демо-аудио и обновляет пути в БД (вместо .txt-заглушек)."""
    os.makedirs(STOCK, exist_ok=True)
    updated = 0
    for item in DEMO_ITEMS:
        if item["media_type"] != "audio":
            continue
        fname = f"{item['stock_name']}.mp3"
        disk = os.path.join(STOCK, fname)
        rel_mp3 = _stock_rel_path(fname)
        if not os.path.exists(disk) or os.path.getsize(disk) < 10000:
            print(f"  audio: {item['title']}")
            if not _download(item["url"], disk, timeout=120):
                print(f"  skip audio: {item['title']}")
                continue
        with database.get_db_connection() as conn:
            rows = conn.execute(
                "SELECT id, file_path FROM media WHERE media_type = 'audio'"
            ).fetchall()
            for row in rows:
                path_norm = (row["file_path"] or "").replace("\\", "/").lower()
                if item["stock_name"].lower() not in path_norm:
                    continue
                if path_norm.endswith(".mp3"):
                    continue
                with conn:
                    conn.execute(
                        "UPDATE media SET file_path = ? WHERE id = ?",
                        (rel_mp3, row["id"]),
                    )
                updated += 1
                print(f"  audio path: {item['title']}")
    if updated:
        print(f"Seed: обновлено аудио-файлов для {updated} записей.")
    return updated


def sync_demo_metadata():
    """Обновляет названия и описания демо-записей по реальному содержимому файлов."""
    _ensure_stock_images()
    _ensure_stock_audio()
    updated = 0
    with database.get_db_connection() as conn:
        rows = conn.execute(
            "SELECT id, title, description, file_path, media_type FROM media"
        ).fetchall()
        for row in rows:
            path_norm = (row["file_path"] or "").replace("\\", "/").lower()
            if "/stock/" not in path_norm:
                continue
            matched = None
            for item in DEMO_ITEMS:
                if item["media_type"] != row["media_type"]:
                    continue
                for key in _match_keys_for_item(item):
                    if key.lower() in path_norm:
                        matched = item
                        break
                if matched:
                    break
            if not matched:
                continue
            title = matched["title"]
            desc = matched["description"]
            if row["title"] == title and row["description"] == desc:
                continue
            database.update_media_fields(row["id"], title, desc)
            updated += 1
            print(f"  meta: {title}")
    if updated:
        print(f"Seed: обновлено метаданных для {updated} записей.")
    sync_demo_thumbnails(force=False)
    return updated


def _ensure_stock_images():
    """Скачивает стоковые изображения, если файла ещё нет."""
    os.makedirs(STOCK, exist_ok=True)
    for item in DEMO_ITEMS:
        if item["media_type"] != "image":
            continue
        url = IMAGE_SOURCES.get(item["stock_name"])
        if not url:
            continue
        disk = os.path.join(STOCK, f"{item['stock_name']}.jpg")
        if os.path.exists(disk) and os.path.getsize(disk) > 5000:
            continue
        print(f"  image: {item['title']}")
        _download(url, disk)


def _ensure_thumbnail_for_media(media_id: int, media_type: str, file_path: str, seed: str) -> str | None:
    if media_type == "document":
        return None
    if media_type == "image" and file_path:
        return file_path.replace("\\", "/")

    fname = f"thumb_{media_id}_{seed}.jpg"
    disk = os.path.join(THUMBS, fname)
    if _thumb_from_picsum(seed, disk):
        return _rel_thumb_path(fname)
    return None


def backfill_thumbnails():
    """Добавляет превью записям без обложки (в т.ч. пользовательским)."""
    os.makedirs(THUMBS, exist_ok=True)
    sync_demo_thumbnails(force=False)
    updated = 0
    with database.get_db_connection() as conn:
        rows = conn.execute("""
            SELECT id, title, media_type, file_path, thumbnail_path
            FROM media
            WHERE thumbnail_path IS NULL OR TRIM(thumbnail_path) = ''
        """).fetchall()
        for row in rows:
            if row["media_type"] == "image" and row["file_path"]:
                thumb = row["file_path"].replace("\\", "/")
            else:
                thumb = None
            if thumb:
                with conn:
                    conn.execute(
                        "UPDATE media SET thumbnail_path = ? WHERE id = ?",
                        (thumb, row["id"]),
                    )
                updated += 1
                print(f"  thumb fill: {row['title'][:40]}")
    if updated:
        print(f"Seed: обновлено превью для {updated} записей.")


def _ensure_creators():
    author_ids = []
    for username, email, first, second, _ in CREATORS:
        if not database.verify_user_credentials(username, "demo123"):
            database.add_user(username, email, "demo123")
        user = database.verify_user_credentials(username, "demo123")
        database.add_or_update_author_profile(user["id"], first, second, f"Канал {first} {second}")
        author = database.get_author_by_user_id(user["id"])
        author_ids.append(author["id"])
    return author_ids


def _prepare_media_files(item: dict) -> tuple[str | None, str | None]:
    """Скачивает файлы и возвращает (rel_file, rel_thumb)."""
    media_type = item["media_type"]
    stock_name = item["stock_name"]
    rel_file = None
    rel_thumb = None

    if media_type == "video":
        fname = f"{stock_name}.mp4"
        disk = os.path.join(STOCK, fname)
        if not os.path.exists(disk):
            print(f"  video: {item['title']}")
            if not _download(item["url"], disk):
                return None, None
        rel_file = _stock_rel_path(fname)
        rel_thumb = _ensure_item_thumbnail(item)

    elif media_type == "image":
        fname = f"{stock_name}.jpg"
        disk = os.path.join(STOCK, fname)
        img_url = IMAGE_SOURCES.get(stock_name)
        if not os.path.exists(disk):
            print(f"  image: {item['title']}")
            if img_url and not _download(img_url, disk):
                return None, None
            if not img_url and not _thumb_from_picsum(stock_name, disk):
                return None, None
        rel_file = _stock_rel_path(fname)
        rel_thumb = rel_file

    elif media_type == "audio":
        fname = f"{stock_name}.mp3"
        disk = os.path.join(STOCK, fname)
        txt_disk = os.path.join(STOCK, f"{stock_name}.txt")
        if not os.path.exists(disk) or os.path.getsize(disk) < 10000:
            print(f"  audio: {item['title']}")
            if not _download(item["url"], disk, timeout=120):
                if not os.path.exists(txt_disk):
                    with open(txt_disk, "w", encoding="utf-8") as f:
                        f.write(f"# {item['title']}\n{item['description']}\n")
                rel_file = _stock_rel_path(f"{stock_name}.txt")
            else:
                rel_file = _stock_rel_path(fname)
        else:
            rel_file = _stock_rel_path(fname)
        rel_thumb = _ensure_item_thumbnail(item)

    else:
        fname = f"{stock_name}.txt"
        disk = os.path.join(STOCK, fname)
        if not os.path.exists(disk):
            print(f"  document: {item['title']}")
            with open(disk, "w", encoding="utf-8") as f:
                f.write(f"{item['title']}\n\n{item['description']}\n")
        rel_file = _stock_rel_path(fname)

    return rel_file, rel_thumb


def run_seed(force: bool = False):
    if not force and database.get_media_count() >= 10:
        print("Seed: контент уже есть, синхронизация...")
        sync_demo_metadata()
        sync_demo_thumbnails(force=True)
        backfill_thumbnails()
        return

    os.makedirs(STOCK, exist_ok=True)
    os.makedirs(THUMBS, exist_ok=True)
    print("Seed: загрузка стокового контента...")
    author_ids = _ensure_creators()

    for i, item in enumerate(DEMO_ITEMS):
        author_id = author_ids[i % len(author_ids)]
        rel_file, rel_thumb = _prepare_media_files(item)
        if not rel_file:
            continue

        title = item["title"]
        with database.get_db_connection() as conn:
            existing = conn.execute(
                "SELECT id FROM media WHERE title=? OR file_path LIKE ?",
                (title, f"%{item['stock_name']}%"),
            ).fetchone()
            if existing:
                database.update_media_fields(existing["id"], title, item["description"], rel_thumb)
                continue

        mid = database.add_media(
            title, item["description"], author_id, item["media_type"],
            rel_file, rel_thumb, item["views"],
        )
        if mid:
            database.attach_tags_to_media(mid, item["tags"], initial_votes=random.randint(2, 12))

    sync_demo_metadata()
    sync_demo_thumbnails(force=True)
    backfill_thumbnails()
    print(f"Seed: готово. Записей в media: {database.get_media_count()}")


if __name__ == "__main__":
    database.initialize_database()
    sync_demo_metadata()
    sync_demo_thumbnails(force=True)
    run_seed(force=False)
