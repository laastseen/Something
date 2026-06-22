# Izmeneniya — подробное описание доработок платформы Something

Документ описывает все существенные изменения, внесённые в проект **Something** (медиа-платформа в стиле YouTube на FastAPI + SQLite + Jinja2).  
Рабочая директория: `c:\Users\ketov\Downloads\src (1)\src`.

---

## Содержание

1. [Инфраструктура и запуск](#1-инфраструктура-и-запуск)
2. [База данных](#2-база-данных)
3. [Система жалоб (модерация)](#3-система-жалоб-модерация)
4. [Рекомендации](#4-рекомендации)
5. [Демо-контент (seed)](#5-демо-контент-seed)
6. [Загрузка контента и превью](#6-загрузка-контента-и-превью)
7. [Дизайн, тема и общий UI](#7-дизайн-тема-и-общий-ui)
8. [Wiki тегов](#8-wiki-тегов)
9. [Исправление поиска по тегам](#9-исправление-поиска-по-тегам)
10. [Просмотр документов](#10-просмотр-документов)
11. [Канал автора и подписки](#11-канал-автора-и-подписки)
12. [Редактирование своего контента](#12-редактирование-своего-контента)
13. [История просмотров и «Продолжить просмотр»](#13-история-просмотров-и-продолжить-просмотр)
14. [Пагинация ленты и превью при наведении](#14-пагинация-ленты-и-превью-при-наведении)
15. [Оформление шапки канала автора](#15-оформление-шапки-канала-автора)
16. [Новые и изменённые файлы](#16-новые-и-изменённые-файлы)
17. [API — сводная таблица](#17-api--сводная-таблица)

---

## 1. Инфраструктура и запуск

### Пути и статика (`main.py`)

- Введены константы `BASE_DIR`, `STATIC_DIR`, `UPLOADS_DIR`, `THUMBS_DIR`, `TEMPLATES_DIR` — пути считаются от каталога проекта, а не от текущей рабочей директории.
- При старте выполняется `os.chdir(BASE_DIR)`, чтобы относительные пути к БД и `uploads/` были стабильными.
- Монтирование `/static` и `/uploads` вынесено в **конец** `main.py` (после объявления всех маршрутов).
- Глобальная функция Jinja2 `to_url()` преобразует путь файла в URL (`uploads/...` → `/uploads/...`).

### Жизненный цикл приложения (`lifespan`)

При старте сервера:

1. `database.initialize_database()` — создание таблиц и миграции.
2. Если нет пользователей — создаётся демо-админ: **admin** / **admin** (`admin@admin.com`).
3. Запускается фоновая задача `tag_cleanup_task()` (каждые 60 секунд).
4. Вызывается `seed_content.run_seed()` и `seed_content.backfill_thumbnails()` (ошибки сида не роняют приложение).

Запуск: `python main.py` → обычно `http://127.0.0.1:8001/`.

### Отладка (`.vscode/launch.json`)

Добавлена конфигурация запуска/отладки FastAPI из VS Code/Cursor.

---

## 2. База данных

Файл: `database.py`, файл БД: `media_platform.db`.

### Существующие таблицы (без изменений схемы, кроме миграций)

- `users`, `authors`, `tags`, `media`, `media_tags`, `comments`, `likes`
- `playlists`, `playlist_media`, `history`
- `standard_tags`, `tag_user_votes`

### Миграции (`_run_migrations`)

| Изменение | Описание |
|-----------|----------|
| `media.thumbnail_path` | Колонка для пути к обложке/превью в ленте |
| `subscriptions` | Новая таблица подписок на авторов |

```sql
CREATE TABLE subscriptions (
    user_id INTEGER NOT NULL,
    author_id INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (user_id, author_id),
    ...
);
```

### Таблица `reports` (жалобы)

Поля: `reporter_id`, `reported_author_id`, `media_id` (nullable), `reason`, `details`, `status` (`pending` / `reviewed` / `dismissed`), `created_at`.

Словарь причин: `REPORT_REASONS` (плагиат, оскорбления, hate, насилие, спам, misleading, child_safety, other).

### Нормализация тегов

- Функция `normalize_tag_name(name)` — `.strip().casefold()` для единого формата имён (важно для **кириллицы**: SQLite `COLLATE NOCASE` не сравнивает русские буквы по регистру).
- `_migrate_normalize_tags(conn)` при инициализации:
  - приводит имена в `standard_tags` и `tags` к нижнему регистру;
  - сливает дубликаты (`Образование` / `образование`) в одну запись;
  - синхронизирует стандартные теги с таблицей `tags`.

Стартовые стандартные теги в нижнем регистре: `образование`, `развлечение`, `музыка`, `технологии`, `важное`.

### Исправление очистки «сиротских» тегов

В `cleanup_zero_votes_tags()` удаление неиспользуемых тегов сравнивает **имя** с `standard_tags`, а не `id` (раньше `standard_tags.id` и `tags.id` — разные последовательности, логика была неверной).

### Новые функции БД (ключевые)

| Функция | Назначение |
|---------|------------|
| `get_author_public(author_id)` | Публичный профиль канала + счётчики подписчиков и публикаций |
| `get_subscriber_count`, `is_subscribed`, `toggle_subscription` | Подписки |
| `get_subscribed_author_ids(user_id)` | Список ID авторов для рекомендаций |
| `list_media_feed(...)` | Пагинированная лента только `published` |
| `get_continue_watching(user_id)` | Уникальные последние просмотры по каждому медиа |
| `user_owns_media`, `update_media_fields` | Редактирование своего контента |
| `delete_media(media_id, base_dir)` | Удаление записи + файлов на диске (основной файл и превью) |
| `create_report`, `get_all_reports`, `update_report_status` | Жалобы |

Константа: `FEED_PAGE_SIZE = 24`.

---

## 3. Система жалоб (модерация)

### Поведение

- На странице просмотра (`view.html`) у авторизованных пользователей — кнопка **«Пожаловаться»** и модальное окно с причинами.
- `POST /api/report` — создание жалобы (нельзя жаловаться на себя).
- В админ-панели (`admin.html`) вкладка **«Жалобы»** со списком и сменой статуса.
- `POST /api/admin/report/status` — обновление статуса (`reviewed`, `dismissed` и т.д.).

### Файлы

- `database.py` — таблица и функции
- `main.py` — эндпоинты
- `templates/view.html`, `static/js/view.js`, `static/css/view.css`
- `templates/admin.html`

---

## 4. Рекомендации

Файл: `recommendations.py`.

### `format_thumbnail(item)`

- Для **документов** — статичная SVG `/static/img/cover-document.svg`.
- Для **аудио/видео** без своего превью — `cover-audio.svg`, `cover-video.svg`.
- Если есть `thumbnail_path` — URL превью из uploads.
- Для **изображений** без обложки — превью = сам файл.
- Для **видео** добавляется `preview_url` — путь к файлу для hover-превью в ленте.

### `get_content_based_recommendations(media_id)`

Гибридный подбор «похожего» на странице просмотра:

- общие теги и голоса по тегам;
- бонус за тот же `media_type`;
- штраф за того же автора (разнообразие);
- свежесть (`_recency_score`);
- диверсификация: не больше N карточек от одного автора.

### `get_personalized_recommendations(user_id)`

Для авторизованных пользователей с активностью (лайки / история):

- веса по тегам из лайков и истории;
- коллаборативная фильтрация по похожим пользователям (лайки);
- популярность и свежесть;
- **бонус +12** за контент авторов из подписок (`get_subscribed_author_ids`);
- диверсификация по авторам;
- дополнение трендами, если мало кандидатов.

Для гостей или без активности — `get_trending_media()`.

### `get_trending_media()`

Скоринг: просмотры + лайки − дизлайки, диверсификация по авторам.

### Исправление в ленте (связано с БД)

В `search_media` / выборках для главной ранее не всегда передавался `thumbnail_path` — после правок превью в карточках подтягиваются через `format_thumbnail()`.

---

## 5. Демо-контент (seed)

Файл: `seed_content.py`.

### Что создаётся

- **Авторы** (`CREATORS`): studio_nova, pixel_anna, doc_ivan, art_luna с тегами и профилями.
- **Контент** (`CONTENT`): видео, изображения, аудио, документы с описаниями, тегами, просмотрами.
- **Видео**: загрузка с MDN / W3Schools (mp4).
- **Изображения**: Picsum (превью и файлы).
- **Аудио**: SoundHelix MP3 или fallback `.txt`.
- **Документы**: `.txt` с заголовком и описанием.
- **Превью**: `uploads/thumbs/` через Picsum; `backfill_thumbnails()` для уже существующих записей без обложки.

Сид не дублирует записи с тем же `title`. Пароль демо-авторов в сиде: **demo123** (отдельно от admin).

---

## 6. Загрузка контента и превью

### `POST /upload` (`main.py`)

- Поля: `title`, `description`, `media_type`, `file`, опционально `thumbnail`.
- Для **документов** превью в ленте не загружается — всегда иконка документа.
- Для **изображений** без обложки `thumbnail_path` = путь к основному файлу.
- Для **видео/аудио** — отдельный файл обложки (JPG, PNG, WebP, GIF); при отсутствии — предупреждение в UI.
- Файлы сохраняются в `uploads/` и `uploads/thumbs/` с UUID-именами.

### UI (`templates/index.html`, `static/js/script.js`)

- Модальное окно загрузки с предпросмотром обложки.
- Подсказки по типу контента; для документов — список форматов с inline-просмотром.

---

## 7. Дизайн, тема и общий UI

### Базовый шаблон (`templates/base.html`)

- Общий header (логотип Something, переключатель темы).
- Блоки `header_center`, `header_right`, `sidebar`, `content`, `scripts`.
- Подключение Roboto, `style.css`, `theme.css`, Lucide Icons.
- Inline-скрипт темы до отрисовки (без «мигания»).

### Тема (`static/css/theme.css`, `static/js/theme.js`)

- CSS-переменные для светлой и тёмной темы (`data-theme="light"` / `"dark"`).
- Сохранение выбора в `localStorage` (`something-theme`).
- Кнопка `#theme-toggle`, учёт `prefers-color-scheme`.
- Стили для header, sidebar, модалок, админ-таблиц.

### Сайдбар (`templates/partials/sidebar.html`)

- Навигация: главная, типы контента, Wiki, профиль.
- Подключается на главной, wiki, profile, author.

### Логотип

- Встроенный SVG (треугольник play), не зависит от загрузки Lucide.

### Страницы авторизации

- `login.html`, `register.html` — в общем стиле платформы.

---

## 8. Wiki тегов

### Страница `/wiki` (`templates/wiki.html`, `static/css/wiki.css`)

- Hero-блок с описанием.
- Сетка карточек тегов (цвет, название, описание, ссылка на ленту `/?q=#тег`).
- **Клиентский поиск** `#wiki-filter` — фильтрация по `data-name` / `data-desc` без перезагрузки.
- Для **admin** — панель создания/редактирования/удаления стандартных тегов с превью цвета `#RRGGBB`.

### API

- `POST /api/wiki/save` — создать/обновить (только admin).
- `POST /api/wiki/delete` — удалить (только admin).

---

## 9. Исправление поиска по тегам

### Проблема

1. В Wiki теги: `Образование`, в контенте сида: `образование` — разные строки в `tags`.
2. Ссылки Wiki вели на `/#Образование` → 0 результатов.
3. Текстовый поиск учитывал только теги из `standard_tags`, не все теги на медиа.

### Решение

- Единая нормализация при сохранении и поиске (`normalize_tag_name`).
- Миграция слияния дубликатов.
- `get_media_by_tag_name` — нормализованное имя.
- `search_media` — поиск по любым тегам на медиа; поддержка `#` в запросе.
- `main.py`: `q.startswith("#")` → `normalize_tag_name(q[1:])`.

---

## 10. Просмотр документов

Новый модуль: `documents.py`.

### Типы просмотра (`get_document_view`)

| `kind` | Форматы | Отображение |
|--------|---------|-------------|
| `pdf` | `.pdf` | `<iframe>` на странице |
| `image` | jpg, png, webp, gif, svg, bmp | `<img>` |
| `text` | txt, md, json, csv, xml, yaml, код, html | `<pre>` до 512 КБ |
| `download` | остальное | кнопка скачивания + пояснение |
| `missing` | файл не найден | fallback |

Безопасность: путь только внутри `uploads/`, запрет `..`.

### UI

- `templates/view.html` — ветки для pdf / text / image / download.
- `static/css/view.css` — `.doc-iframe`, `.doc-text-viewer`, toolbar.

---

## 11. Канал автора и подписки

### Страница `GET /author/{author_id}`

Шаблон: `templates/author.html`.

- Шапка канала (баннер, аватар, имя, @username, статистика, био).
- Кнопка **Подписаться** / **Отписаться** (или вход / личный кабинет для своего канала).
- Вкладки типов контента + лента с бесконечной подгрузкой (тот же `Feed.init`, `authorId` в конфиге).

### API

- `POST /api/subscribe` — переключение подписки; ответ: `{ subscribed, subscriber_count }`.
- Нельзя подписаться на себя.

### Интеграция в UI

- Ссылки `/author/{id}` с карточек ленты, блока рекомендаций, страницы просмотра.
- На `view.html` — кликабельный блок автора + кнопка подписки.

### Рекомендации

Подписки увеличивают вес контента соответствующих авторов в `get_personalized_recommendations`.

---

## 12. Редактирование своего контента

### API (без админки)

| Метод | Путь | Описание |
|-------|------|----------|
| POST | `/api/media/update` | `media_id`, `title`, `description`, опционально `thumbnail` |
| POST | `/api/media/delete` | `id` — владелец или admin |

Проверка: `user_owns_media(user_id, media_id)`.

### UI

- **Профиль** (`profile.html`): кнопки «Изменить» / «Удалить» у каждой публикации; модалка редактирования.
- **Просмотр** (`view.html`): для владельца — «Редактировать» / «Удалить» и модалка.
- Удаление через `/api/media/delete` (раньше в профиле ошибочно вызывался только admin-эндпоинт).

---

## 13. История просмотров и «Продолжить просмотр»

### Запись истории

При открытии `/view/{id}` для авторизованного пользователя: `log_view_history(user_id, media_id)` — новая строка в `history` с `viewed_at`.

### Отображение

- `get_continue_watching(user_id, limit=12)` — **по одному** последнему просмотру на каждое `media_id`, сортировка по дате.
- В **профиле** — горизонтальная секция **«Продолжить просмотр»** (карточки с превью и временем просмотра).
- Старая секция «История просмотров» списком заменена/упрощена в пользу continue-блока.

---

## 14. Пагинация ленты и превью при наведении

### Архитектура

Раньше главная загружала **весь** контент каждого типа в JSON `data` в HTML.  
Теперь:

- `GET /api/feed?type=video&page=1&limit=24` (+ `q`, `tag`, `author_id`).
- `database.list_media_feed()` — только `status = 'published'`, offset/limit, флаг `has_more`.

### Клиент (`static/js/feed.js`)

- `Feed.init(feedConfig)` — первая страница + `IntersectionObserver` на `#feed-sentinel`.
- Переключение вкладок без полной перезагрузки (кроме поиска с `?q=` — редирект с типом).
- `createCard()` — карточки с ссылкой на автора, превью, метаданные.
- **Hover-превью** для видео: при наведении ~3 с проигрывается `preview_url` (muted, `playsinline`).

### Главная (`index.html`)

- `feedConfig` вместо полного `data`.
- Блок «Рекомендовано для вас» — по-прежнему серверный; карточки с `data-preview-url` и hover.
- Подключены `feed-vibe.css`, `feed.js`.

### Стили (`static/css/feed-vibe.css`)

- `.vibe-card`, `.thumbnail-wrap`, `.hover-preview-video`
- Секция continue watching, базовые стили канала (см. §15).

---

## 15. Оформление шапки канала автора

Доработка блока на `/author/{id}` (вайб, YouTube-подобный вид).

### Структура HTML

- Кнопка «На главную» — `.channel-back` (pill).
- `.channel-banner` — цветной градиентный баннер (mesh + shine).
- Аватар с кольцом, наезжает на баннер (`.channel-hero-inner`, `margin-top: -44px`).
- Строка: заголовок + кнопка действия справа.
- Статистика в «пилюлях» с иконками Lucide (`users`, `layers`).
- Вкладки `.channel-tabs` — сегментированный control.

### CSS

- Тень карточки, отдельный градиент баннера для `[data-theme="dark"]`.
- Кнопки: `.subscribe-btn`, `.subscribe-btn--accent`, `.subscribe-btn.subscribed`.
- Адаптив ≤720px: колонка, центрирование, кнопка на всю ширину.

### JS

- `toggleSubscribe` обновляет `<strong>` внутри `#subscriber-count`.

---

## 16. Новые и изменённые файлы

### Новые

| Файл | Назначение |
|------|------------|
| `documents.py` | Логика просмотра документов |
| `seed_content.py` | Наполнение БД демо-контентом |
| `static/js/feed.js` | Лента, пагинация, hover-превью, подписка |
| `static/css/feed-vibe.css` | Стили ленты, канала, continue watching |
| `static/css/theme.css` | CSS-переменные темы |
| `static/css/wiki.css` | Стили Wiki |
| `static/css/view.css` | Стили страницы просмотра |
| `static/js/theme.js` | Переключение темы |
| `static/img/cover-*.svg` | Иконки типов в ленте |
| `templates/base.html` | Базовый layout |
| `templates/author.html` | Страница канала |
| `templates/partials/sidebar.html` | Боковое меню |
| `Izmeneniya.md` | Этот документ |

### Существенно изменённые

| Файл |
|------|
| `main.py` |
| `database.py` |
| `recommendations.py` |
| `auth.py` (без больших изменений в последних итерациях) |
| `templates/index.html`, `view.html`, `profile.html`, `wiki.html`, `admin.html` |
| `static/js/script.js`, `static/js/view.js` |
| `static/css/style.css` |

---

## 17. API — сводная таблица

| Метод | URL | Auth | Описание |
|-------|-----|------|----------|
| GET | `/` | — | Главная, рекомендации, feedConfig |
| GET | `/api/feed` | — | Пагинированная лента |
| GET | `/author/{id}` | — | Канал автора |
| POST | `/api/subscribe` | да | Подписка/отписка |
| GET | `/view/{id}` | — | Просмотр медиа |
| GET | `/wiki` | — | Wiki тегов |
| POST | `/api/wiki/save` | admin | Сохранить тег |
| POST | `/api/wiki/delete` | admin | Удалить тег |
| GET/POST | `/login`, `/register`, `/logout` | — | Сессия (cookie) |
| GET | `/admin` | admin | Админ-панель |
| POST | `/api/admin/delete/user` | admin | Удалить пользователя |
| POST | `/api/admin/delete/media` | admin/owner | Удалить медиа |
| POST | `/api/media/delete` | owner | Удалить своё медиа |
| POST | `/api/media/update` | owner | Редактировать медиа |
| GET | `/profile` | да | Личный кабинет |
| POST | `/api/comment` | да | Комментарий |
| POST | `/api/like` | да | Лайк/дизлайк |
| POST | `/api/playlist/*` | да | Плейлисты |
| GET | `/playlists/{id}` | — | Просмотр плейлиста |
| POST | `/api/tag/vote` | да | Голос за тег |
| POST | `/api/tag/add` | — | Добавить тег к медиа |
| POST | `/api/report` | да | Жалоба |
| POST | `/api/admin/report/status` | admin | Статус жалобы |
| POST | `/upload` | да | Загрузка контента |

---

## Зависимости (`requirements.txt`)

```
fastapi
uvicorn[standard]
jinja2
python-multipart
```

---

## Учётные данные для проверки

| Роль | Логин | Пароль |
|------|-------|--------|
| Админ (создаётся при пустой БД) | admin | admin |
| Демо-авторы сида | studio_nova и др. | demo123 |

---

## Известные ограничения (на момент документа)

1. **`cleanup_zero_votes_tags`** — удаляет все связи `media_tags` с `votes = 0` каждую минуту; новые теги с 0 голосов могут быстро исчезать (задуманная «упрощённая» логика без таймстемпа).
2. Часть URL видео в сиде может не скачаться (403) — остаётся только превью.
3. DOCX/XLSX — только скачивание, без inline-просмотра.
4. `playlist.html` — без бокового сайдбара (в отличие от profile/wiki/author).
5. Демо-админ `admin/admin` создаётся автоматически — для production нужны env и отключение сида.

---

*Документ сформирован по итогам сессии разработки платформы Something. Для актуального списка маршрутов см. `main.py`.*
