import math
import database
from contextlib import closing
from datetime import datetime

STATIC_COVERS = {
    "document": "/static/img/cover-document.svg",
    "audio": "/static/img/cover-audio.svg",
    "video": "/static/img/cover-video.svg",
}


def format_thumbnail(item: dict) -> dict:
    """Добавляет thumbnail и preview_url к элементу медиа."""
    item = dict(item)
    media_type = item.get("media_type", "media")
    fp = item.get("file_path")

    if media_type == "video" and fp:
        item["preview_url"] = "/" + str(fp).replace("\\", "/")

    if media_type == "document":
        item["thumbnail"] = STATIC_COVERS["document"]
        return item

    thumb = item.get("thumbnail_path")
    if thumb and str(thumb).strip():
        item["thumbnail"] = "/" + str(thumb).replace("\\", "/")
        return item

    if media_type == "image" and fp:
        item["thumbnail"] = "/" + str(fp).replace("\\", "/")
        return item

    item["thumbnail"] = STATIC_COVERS.get(media_type, STATIC_COVERS["video"])
    return item


def _recency_score(upload_date: str) -> float:
    try:
        uploaded = datetime.strptime(upload_date, "%Y-%m-%d %H:%M:%S")
        days = max(0, (datetime.now() - uploaded).days)
        return 1.0 / (1.0 + days / 14.0)
    except Exception:
        return 0.5


def _diversify_by_author(items: list[dict], limit: int, max_per_author: int = 2) -> list[dict]:
    result, author_counts = [], {}
    for item in items:
        aid = item.get("author_id")
        if author_counts.get(aid, 0) >= max_per_author:
            continue
        result.append(item)
        author_counts[aid] = author_counts.get(aid, 0) + 1
        if len(result) >= limit:
            break
    return result


def _load_media_tags_map(conn) -> dict[int, list[dict]]:
    tags_by_media: dict[int, list[dict]] = {}
    for row in conn.execute("SELECT media_id, tag_id, votes FROM media_tags").fetchall():
        tags_by_media.setdefault(row["media_id"], []).append(dict(row))
    return tags_by_media


def _build_tag_preferences(conn, user_id: int) -> dict[int, float]:
    """Собирает веса тегов из лайков, истории и голосов пользователя за теги."""
    tag_prefs: dict[int, float] = {}

    for row in conn.execute("""
        SELECT mt.tag_id, l.is_like FROM likes l
        JOIN media_tags mt ON l.media_id = mt.media_id WHERE l.user_id = ?
    """, (user_id,)).fetchall():
        w = 6 if row["is_like"] == 1 else -4
        tag_prefs[row["tag_id"]] = tag_prefs.get(row["tag_id"], 0) + w

    for i, row in enumerate(conn.execute("""
        SELECT mt.tag_id, m.media_type FROM history h
        JOIN media m ON h.media_id = m.id
        JOIN media_tags mt ON m.id = mt.media_id
        WHERE h.user_id = ?
        ORDER BY h.viewed_at DESC LIMIT 50
    """, (user_id,)).fetchall()):
        decay = max(0.4, 1.0 - i * 0.012)
        tag_prefs[row["tag_id"]] = tag_prefs.get(row["tag_id"], 0) + 2 * decay
        # type_prefs built separately in caller if needed

    for row in conn.execute(
        "SELECT tag_id, vote FROM tag_user_votes WHERE user_id = ?", (user_id,)
    ).fetchall():
        w = 5 if row["vote"] > 0 else -3
        tag_prefs[row["tag_id"]] = tag_prefs.get(row["tag_id"], 0) + w

    return tag_prefs


def _tag_affinity_score(tags: list[dict], tag_prefs: dict[int, float]) -> float:
    if not tags or not tag_prefs:
        return 0.0
    score = 0.0
    matches = 0
    for t in tags:
        pref = tag_prefs.get(t["tag_id"], 0)
        if pref == 0:
            continue
        votes = t.get("votes") or 0
        score += pref * (1 + math.log1p(votes))
        if pref > 0:
            matches += 1
    if matches > 1:
        score += (matches - 1) * 1.5
    return score


def _user_has_activity(conn, user_id: int) -> bool:
    return bool(conn.execute("""
        SELECT 1 FROM likes WHERE user_id = ?
        UNION SELECT 1 FROM history WHERE user_id = ?
        UNION SELECT 1 FROM tag_user_votes WHERE user_id = ?
        LIMIT 1
    """, (user_id, user_id, user_id)).fetchone())


def get_content_based_recommendations(media_id: int, limit: int = 8) -> list[dict]:
    with closing(database.get_db_connection()) as conn:
        current = conn.execute(
            "SELECT media_type, author_id FROM media WHERE id = ?", (media_id,)
        ).fetchone()
        if not current:
            return []

        media_type = current["media_type"]
        author_id = current["author_id"]

        query_tags = """
            SELECT m.id, m.title, m.media_type, m.file_path, m.thumbnail_path, m.views, m.upload_date,
                   m.author_id, u.username AS owner_username,
                   COALESCE(a.first_name,'') || ' ' || COALESCE(a.second_name,'') AS author_name,
                   COUNT(mt2.tag_id) AS shared_tags,
                   SUM(mt2.votes) AS tag_score
            FROM media_tags mt1
            JOIN media_tags mt2 ON mt1.tag_id = mt2.tag_id AND mt2.media_id != mt1.media_id
            JOIN media m ON mt2.media_id = m.id
            JOIN authors a ON m.author_id = a.id
            JOIN users u ON a.user_id = u.id
            WHERE mt1.media_id = ? AND m.status = 'published'
            GROUP BY m.id
            ORDER BY shared_tags DESC, tag_score DESC, m.views DESC
            LIMIT ?
        """
        rows = conn.execute(query_tags, (media_id, limit * 3)).fetchall()
        scored = []
        for r in rows:
            d = dict(r)
            score = d["shared_tags"] * 4 + math.log1p(d.get("tag_score") or 0) + math.log1p(d["views"])
            if d["media_type"] == media_type:
                score += 2
            if d["author_id"] == author_id:
                score -= 1
            score += _recency_score(d["upload_date"]) * 2
            d["_score"] = score
            scored.append(d)

        scored.sort(key=lambda x: x["_score"], reverse=True)
        recs = _diversify_by_author(scored, limit, max_per_author=1)

        if len(recs) < limit:
            exclude = [r["id"] for r in recs] + [media_id]
            ph = ",".join("?" * len(exclude))
            fallback = conn.execute(f"""
                SELECT m.id, m.title, m.media_type, m.file_path, m.thumbnail_path, m.views, m.upload_date,
                       m.author_id, u.username AS owner_username,
                       COALESCE(a.first_name,'') || ' ' || COALESCE(a.second_name,'') AS author_name
                FROM media m JOIN authors a ON m.author_id = a.id
                JOIN users u ON a.user_id = u.id
                WHERE m.media_type = ? AND m.status = 'published' AND m.id NOT IN ({ph})
                ORDER BY m.views DESC LIMIT ?
            """, [media_type, *exclude, limit - len(recs)]).fetchall()
            recs.extend(dict(r) for r in fallback)

        return [format_thumbnail(r) for r in recs[:limit]]


def get_personalized_recommendations(user_id: int | None, limit: int = 8) -> list[dict]:
    if not user_id:
        return get_trending_media(limit)

    with closing(database.get_db_connection()) as conn:
        if not _user_has_activity(conn, user_id):
            return get_trending_media(limit)

        tag_prefs = _build_tag_preferences(conn, user_id)
        type_prefs: dict[str, float] = {}
        for row in conn.execute("""
            SELECT m.media_type FROM history h
            JOIN media m ON h.media_id = m.id
            WHERE h.user_id = ?
            ORDER BY h.viewed_at DESC LIMIT 50
        """, (user_id,)).fetchall():
            type_prefs[row["media_type"]] = type_prefs.get(row["media_type"], 0) + 1

        seen = {r["media_id"] for r in conn.execute(
            "SELECT media_id FROM history WHERE user_id = ? UNION SELECT media_id FROM likes WHERE user_id = ?",
            (user_id, user_id),
        ).fetchall()}

        subscribed_authors = set(database.get_subscribed_author_ids(user_id))
        tags_by_media = _load_media_tags_map(conn)

        my_likes = {r["media_id"]: r["is_like"] for r in conn.execute(
            "SELECT media_id, is_like FROM likes WHERE user_id = ?", (user_id,)
        ).fetchall()}
        user_sims = {}
        if my_likes:
            my_norm = math.sqrt(sum(v * v for v in my_likes.values())) or 1
            others = conn.execute(
                "SELECT user_id, media_id, is_like FROM likes WHERE user_id != ?", (user_id,)
            ).fetchall()
            buckets = {}
            for o in others:
                buckets.setdefault(o["user_id"], {})[o["media_id"]] = o["is_like"]
            for uid, likes in buckets.items():
                dot = sum(my_likes.get(m, 0) * v for m, v in likes.items())
                norm = math.sqrt(sum(v * v for v in likes.values())) or 1
                sim = dot / (my_norm * norm)
                if sim > 0.05:
                    user_sims[uid] = sim

        candidates = conn.execute("""
            SELECT m.id, m.title, m.media_type, m.file_path, m.thumbnail_path, m.views, m.upload_date,
                   m.author_id, u.username AS owner_username,
                   COALESCE(a.first_name,'') || ' ' || COALESCE(a.second_name,'') AS author_name
            FROM media m JOIN authors a ON m.author_id = a.id
            JOIN users u ON a.user_id = u.id
            WHERE m.status = 'published'
        """).fetchall()

        likes_by_media: dict[int, list] = {}
        for lc in conn.execute("SELECT media_id, user_id, is_like FROM likes").fetchall():
            likes_by_media.setdefault(lc["media_id"], []).append(lc)

        scored = []
        for cand in candidates:
            cid = cand["id"]
            if cid in seen:
                continue
            c = dict(cand)
            tags = tags_by_media.get(cid, [])
            cb = _tag_affinity_score(tags, tag_prefs)
            tp = type_prefs.get(c["media_type"], 0) * 1.5
            collab = sum(
                user_sims.get(lc["user_id"], 0) * lc["is_like"]
                for lc in likes_by_media.get(cid, [])
            )
            pop = math.log1p(c["views"])
            fresh = _recency_score(c["upload_date"])
            sub_boost = 12.0 if c["author_id"] in subscribed_authors else 0.0
            total = 0.48 * cb + 0.2 * collab + 0.12 * pop + 0.08 * tp + 0.05 * fresh + sub_boost
            if total <= 0:
                total = pop + fresh
            c["recommendation_score"] = total
            scored.append(c)

        scored.sort(key=lambda x: x["recommendation_score"], reverse=True)
        recs = _diversify_by_author(scored, limit, max_per_author=2)

        if len(recs) < limit:
            have = {r["id"] for r in recs}
            for t in get_trending_media(limit * 2):
                if t["id"] not in have and t["id"] not in seen:
                    recs.append(t)
                    if len(recs) >= limit:
                        break

        return [format_thumbnail(r) for r in recs[:limit]]


def get_trending_media(limit: int = 8) -> list[dict]:
    with closing(database.get_db_connection()) as conn:
        rows = conn.execute("""
            SELECT m.id, m.title, m.media_type, m.file_path, m.thumbnail_path, m.views, m.upload_date,
                   m.author_id, u.username AS owner_username,
                   COALESCE(a.first_name,'') || ' ' || COALESCE(a.second_name,'') AS author_name,
                   (m.views * 1.0
                    + COALESCE(l.likes, 0) * 8
                    + COALESCE(l.dislikes, 0) * -2
                    + COALESCE(tv.tag_score, 0) * 4) AS trend_score
            FROM media m
            JOIN authors a ON m.author_id = a.id
            JOIN users u ON a.user_id = u.id
            LEFT JOIN (
                SELECT media_id,
                       SUM(CASE WHEN is_like = 1 THEN 1 ELSE 0 END) AS likes,
                       SUM(CASE WHEN is_like = -1 THEN 1 ELSE -1 END) AS dislikes
                FROM likes GROUP BY media_id
            ) l ON m.id = l.media_id
            LEFT JOIN (
                SELECT media_id, SUM(votes) AS tag_score
                FROM media_tags GROUP BY media_id
            ) tv ON m.id = tv.media_id
            WHERE m.status = 'published'
            ORDER BY trend_score DESC, m.upload_date DESC
            LIMIT ?
        """, (limit * 2,)).fetchall()
        items = [dict(r) for r in rows]
        diversified = _diversify_by_author(items, limit, max_per_author=2)
        return [format_thumbnail(r) for r in diversified]


def get_globally_popular_media(limit: int = 6) -> list[dict]:
    return get_trending_media(limit)
