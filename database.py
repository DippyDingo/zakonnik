from __future__ import annotations

import json
import random
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Any


DEFAULT_TRAINING_MODE = "mixed"
CARD_TYPE_FLASHCARD = "flashcard"
CARD_TYPE_MULTIPLE = "multiple_choice"
CARD_TYPE_TRUE_FALSE = "true_false"
CARD_TYPE_SCENARIO = "scenario"


class Database:
    def __init__(self, db_path: Path, mastered_streak: int = 3) -> None:
        self.db_path = Path(db_path)
        self.mastered_streak = mastered_streak
        self._lock = threading.Lock()
        self._random = random.SystemRandom()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        with self.conn:
            self.conn.executescript(
                """
                PRAGMA foreign_keys = ON;

                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    selected_chapters TEXT NOT NULL DEFAULT '[]',
                    session_size INTEGER NOT NULL DEFAULT 5,
                    hints_enabled INTEGER NOT NULL DEFAULT 1,
                    reminder_enabled INTEGER NOT NULL DEFAULT 0,
                    reminder_time TEXT NOT NULL DEFAULT '19:00',
                    daily_target INTEGER NOT NULL DEFAULT 5,
                    points INTEGER NOT NULL DEFAULT 0,
                    streak INTEGER NOT NULL DEFAULT 0,
                    best_streak INTEGER NOT NULL DEFAULT 0,
                    last_mode TEXT NOT NULL DEFAULT 'study',
                    preferred_training_mode TEXT NOT NULL DEFAULT 'mixed',
                    mixed_mode_enabled INTEGER NOT NULL DEFAULT 1,
                    options_enabled INTEGER NOT NULL DEFAULT 1,
                    last_training_mode TEXT NOT NULL DEFAULT 'mixed',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS cards (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chapter_code TEXT NOT NULL,
                    chapter_title TEXT NOT NULL,
                    article TEXT NOT NULL,
                    question TEXT NOT NULL,
                    answer TEXT NOT NULL,
                    hint TEXT,
                    example TEXT,
                    card_type TEXT NOT NULL DEFAULT 'flashcard',
                    explanation TEXT,
                    difficulty TEXT,
                    options_json TEXT,
                    correct_option INTEGER,
                    UNIQUE(chapter_code, article, question)
                );

                CREATE TABLE IF NOT EXISTS user_card_progress (
                    user_id INTEGER NOT NULL,
                    card_id INTEGER NOT NULL,
                    status TEXT NOT NULL DEFAULT 'new',
                    correct_streak INTEGER NOT NULL DEFAULT 0,
                    total_correct INTEGER NOT NULL DEFAULT 0,
                    total_incorrect INTEGER NOT NULL DEFAULT 0,
                    last_result TEXT,
                    last_answered_at TEXT,
                    learned_at TEXT,
                    PRIMARY KEY (user_id, card_id),
                    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
                    FOREIGN KEY (card_id) REFERENCES cards(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS answer_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    card_id INTEGER NOT NULL,
                    answered_at TEXT NOT NULL,
                    is_correct INTEGER NOT NULL,
                    points_awarded INTEGER NOT NULL DEFAULT 0,
                    streak_after INTEGER NOT NULL DEFAULT 0,
                    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
                    FOREIGN KEY (card_id) REFERENCES cards(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS session_state (
                    user_id INTEGER PRIMARY KEY,
                    mode TEXT NOT NULL,
                    training_mode TEXT NOT NULL DEFAULT 'mixed',
                    current_card_id INTEGER,
                    current_payload_json TEXT,
                    queue_json TEXT NOT NULL DEFAULT '[]',
                    started_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
                    FOREIGN KEY (current_card_id) REFERENCES cards(id) ON DELETE SET NULL
                );
                """
            )

        self._ensure_column("users", "preferred_training_mode", "TEXT NOT NULL DEFAULT 'mixed'")
        self._ensure_column("users", "mixed_mode_enabled", "INTEGER NOT NULL DEFAULT 1")
        self._ensure_column("users", "options_enabled", "INTEGER NOT NULL DEFAULT 1")
        self._ensure_column("users", "last_training_mode", "TEXT NOT NULL DEFAULT 'mixed'")
        self._ensure_column("cards", "card_type", "TEXT NOT NULL DEFAULT 'flashcard'")
        self._ensure_column("cards", "explanation", "TEXT")
        self._ensure_column("cards", "difficulty", "TEXT")
        self._ensure_column("cards", "options_json", "TEXT")
        self._ensure_column("cards", "correct_option", "INTEGER")
        self._ensure_column("session_state", "training_mode", "TEXT NOT NULL DEFAULT 'mixed'")
        self._ensure_column("session_state", "current_payload_json", "TEXT")

    def _ensure_column(self, table: str, column: str, ddl: str) -> None:
        columns = {
            row["name"] for row in self.conn.execute(f"PRAGMA table_info({table})").fetchall()
        }
        if column not in columns:
            with self.conn:
                self.conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")

    def seed_cards(self, cards_file: Path) -> int:
        payload = json.loads(cards_file.read_text(encoding="utf-8"))
        inserted = 0
        with self.conn:
            for raw_item in payload:
                item = self._normalize_card_item(raw_item)
                exists = self.conn.execute(
                    """
                    SELECT 1
                    FROM cards
                    WHERE chapter_code = ? AND article = ? AND question = ?
                    """,
                    (item["chapter_code"], item["article"], item["question"]),
                ).fetchone()
                self.conn.execute(
                    """
                    INSERT INTO cards (
                        chapter_code,
                        chapter_title,
                        article,
                        question,
                        answer,
                        hint,
                        example,
                        card_type,
                        explanation,
                        difficulty,
                        options_json,
                        correct_option
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(chapter_code, article, question) DO UPDATE SET
                        chapter_title = excluded.chapter_title,
                        answer = excluded.answer,
                        hint = excluded.hint,
                        example = excluded.example,
                        card_type = excluded.card_type,
                        explanation = excluded.explanation,
                        difficulty = excluded.difficulty,
                        options_json = excluded.options_json,
                        correct_option = excluded.correct_option
                    """,
                    (
                        item["chapter_code"],
                        item["chapter_title"],
                        item["article"],
                        item["question"],
                        item["answer"],
                        item.get("hint"),
                        item.get("example"),
                        item["card_type"],
                        item.get("explanation"),
                        item.get("difficulty"),
                        item.get("options_json"),
                        item.get("correct_option"),
                    ),
                )
                if exists is None:
                    inserted += 1
        return inserted

    def _normalize_card_item(self, raw_item: dict[str, Any]) -> dict[str, Any]:
        chapter_code = str(raw_item.get("chapter_code") or raw_item.get("chapter") or "")
        if not chapter_code:
            raise ValueError("В карточке отсутствует chapter_code/chapter")

        card_type = str(raw_item.get("type") or CARD_TYPE_FLASHCARD)
        options = raw_item.get("options")
        correct_option = raw_item.get("correct_option")

        if card_type == CARD_TYPE_TRUE_FALSE and correct_option is None:
            if "correct_bool" in raw_item:
                correct_option = 0 if bool(raw_item["correct_bool"]) else 1
            else:
                answer_text = str(raw_item.get("answer", "")).strip().lower()
                if answer_text.startswith("верно"):
                    correct_option = 0
                elif answer_text.startswith("неверно"):
                    correct_option = 1

        options_json = None
        if isinstance(options, list) and options:
            options_json = json.dumps(options, ensure_ascii=False)

        if correct_option is not None:
            correct_option = int(correct_option)

        return {
            "chapter_code": chapter_code,
            "chapter_title": raw_item["chapter_title"],
            "article": raw_item["article"],
            "question": raw_item["question"],
            "answer": raw_item["answer"],
            "hint": raw_item.get("hint"),
            "example": raw_item.get("example"),
            "card_type": card_type,
            "explanation": raw_item.get("explanation"),
            "difficulty": raw_item.get("difficulty"),
            "options_json": options_json,
            "correct_option": correct_option,
        }

    def upsert_user(self, tg_user: Any) -> None:
        now = self._now()
        with self._lock, self.conn:
            self.conn.execute(
                """
                INSERT INTO users (user_id, username, first_name, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    username = excluded.username,
                    first_name = excluded.first_name,
                    updated_at = excluded.updated_at
                """,
                (tg_user.id, tg_user.username, tg_user.first_name, now),
            )

    def get_user(self, user_id: int) -> sqlite3.Row | None:
        return self.conn.execute(
            "SELECT * FROM users WHERE user_id = ?",
            (user_id,),
        ).fetchone()

    def get_user_settings(self, user_id: int) -> dict[str, Any]:
        row = self.get_user(user_id)
        if row is None:
            raise ValueError(f"Пользователь {user_id} не найден")
        return {
            "selected_chapters": json.loads(row["selected_chapters"]),
            "session_size": row["session_size"],
            "hints_enabled": bool(row["hints_enabled"]),
            "reminder_enabled": bool(row["reminder_enabled"]),
            "reminder_time": row["reminder_time"],
            "daily_target": row["daily_target"],
            "points": row["points"],
            "streak": row["streak"],
            "best_streak": row["best_streak"],
            "last_mode": row["last_mode"],
            "preferred_training_mode": row["preferred_training_mode"] or DEFAULT_TRAINING_MODE,
            "mixed_mode_enabled": bool(row["mixed_mode_enabled"]),
            "options_enabled": bool(row["options_enabled"]),
            "last_training_mode": row["last_training_mode"] or DEFAULT_TRAINING_MODE,
        }

    def list_chapters(self) -> list[sqlite3.Row]:
        return self.conn.execute(
            """
            SELECT chapter_code, chapter_title, COUNT(*) AS cards_count
            FROM cards
            GROUP BY chapter_code, chapter_title
            ORDER BY CAST(chapter_code AS REAL)
            """
        ).fetchall()

    def set_selected_chapters(self, user_id: int, chapter_codes: list[str]) -> None:
        with self._lock, self.conn:
            self.conn.execute(
                """
                UPDATE users
                SET selected_chapters = ?, updated_at = ?
                WHERE user_id = ?
                """,
                (json.dumps(sorted(set(chapter_codes))), self._now(), user_id),
            )

    def set_session_size(self, user_id: int, session_size: int) -> None:
        with self._lock, self.conn:
            self.conn.execute(
                """
                UPDATE users
                SET session_size = ?, updated_at = ?
                WHERE user_id = ?
                """,
                (session_size, self._now(), user_id),
            )

    def set_hints_enabled(self, user_id: int, enabled: bool) -> None:
        with self._lock, self.conn:
            self.conn.execute(
                """
                UPDATE users
                SET hints_enabled = ?, updated_at = ?
                WHERE user_id = ?
                """,
                (1 if enabled else 0, self._now(), user_id),
            )

    def set_reminder_enabled(self, user_id: int, enabled: bool) -> None:
        with self._lock, self.conn:
            self.conn.execute(
                """
                UPDATE users
                SET reminder_enabled = ?, updated_at = ?
                WHERE user_id = ?
                """,
                (1 if enabled else 0, self._now(), user_id),
            )

    def set_reminder_time(self, user_id: int, reminder_time: str) -> None:
        with self._lock, self.conn:
            self.conn.execute(
                """
                UPDATE users
                SET reminder_time = ?, updated_at = ?
                WHERE user_id = ?
                """,
                (reminder_time, self._now(), user_id),
            )

    def set_daily_target(self, user_id: int, daily_target: int) -> None:
        with self._lock, self.conn:
            self.conn.execute(
                """
                UPDATE users
                SET daily_target = ?, updated_at = ?
                WHERE user_id = ?
                """,
                (daily_target, self._now(), user_id),
            )

    def set_last_mode(self, user_id: int, mode: str) -> None:
        with self._lock, self.conn:
            self.conn.execute(
                """
                UPDATE users
                SET last_mode = ?, updated_at = ?
                WHERE user_id = ?
                """,
                (mode, self._now(), user_id),
            )

    def set_last_training_mode(self, user_id: int, training_mode: str) -> None:
        with self._lock, self.conn:
            self.conn.execute(
                """
                UPDATE users
                SET last_training_mode = ?, updated_at = ?
                WHERE user_id = ?
                """,
                (training_mode, self._now(), user_id),
            )

    def set_preferred_training_mode(self, user_id: int, training_mode: str) -> None:
        with self._lock, self.conn:
            self.conn.execute(
                """
                UPDATE users
                SET preferred_training_mode = ?, updated_at = ?
                WHERE user_id = ?
                """,
                (training_mode, self._now(), user_id),
            )

    def set_mixed_mode_enabled(self, user_id: int, enabled: bool) -> None:
        with self._lock, self.conn:
            self.conn.execute(
                """
                UPDATE users
                SET mixed_mode_enabled = ?, updated_at = ?
                WHERE user_id = ?
                """,
                (1 if enabled else 0, self._now(), user_id),
            )

    def set_options_enabled(self, user_id: int, enabled: bool) -> None:
        with self._lock, self.conn:
            self.conn.execute(
                """
                UPDATE users
                SET options_enabled = ?, updated_at = ?
                WHERE user_id = ?
                """,
                (1 if enabled else 0, self._now(), user_id),
            )

    def get_card(self, card_id: int) -> sqlite3.Row | None:
        return self.conn.execute(
            "SELECT * FROM cards WHERE id = ?",
            (card_id,),
        ).fetchone()

    def _chapter_filter_sql(self, selected_chapters: list[str]) -> tuple[str, list[Any]]:
        if not selected_chapters:
            return "", []
        placeholders = ",".join("?" for _ in selected_chapters)
        return f" AND c.chapter_code IN ({placeholders})", list(selected_chapters)

    def create_session(
        self,
        user_id: int,
        mode: str,
        training_mode: str | None = None,
    ) -> dict[str, Any] | None:
        settings = self.get_user_settings(user_id)
        effective_training_mode = training_mode or settings["preferred_training_mode"]
        if effective_training_mode == "mixed" and not settings["mixed_mode_enabled"]:
            effective_training_mode = settings["preferred_training_mode"]
            if effective_training_mode == "mixed":
                effective_training_mode = "flashcard"

        payloads = self.build_session_payloads(user_id, mode, effective_training_mode)
        if not payloads:
            self.clear_session(user_id)
            self.set_last_mode(user_id, mode)
            self.set_last_training_mode(user_id, effective_training_mode)
            return None

        current_payload = payloads[0]
        queue = payloads[1:]
        now = self._now()
        with self._lock, self.conn:
            self.conn.execute(
                """
                INSERT INTO session_state (
                    user_id,
                    mode,
                    training_mode,
                    current_card_id,
                    current_payload_json,
                    queue_json,
                    started_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    mode = excluded.mode,
                    training_mode = excluded.training_mode,
                    current_card_id = excluded.current_card_id,
                    current_payload_json = excluded.current_payload_json,
                    queue_json = excluded.queue_json,
                    started_at = excluded.started_at,
                    updated_at = excluded.updated_at
                """,
                (
                    user_id,
                    mode,
                    effective_training_mode,
                    current_payload["card_id"],
                    self._dump_json(current_payload),
                    self._dump_json(queue),
                    now,
                    now,
                ),
            )
        self.set_last_mode(user_id, mode)
        self.set_last_training_mode(user_id, effective_training_mode)
        return self.get_session(user_id)

    def build_session_payloads(
        self,
        user_id: int,
        mode: str,
        training_mode: str,
    ) -> list[dict[str, Any]]:
        settings = self.get_user_settings(user_id)
        selected_chapters = settings["selected_chapters"]
        session_size = settings["session_size"]
        chapter_sql, chapter_params = self._chapter_filter_sql(selected_chapters)
        options_enabled = settings["options_enabled"]

        if mode == "review":
            status_filter = "(COALESCE(p.total_correct, 0) + COALESCE(p.total_incorrect, 0)) > 0"
            order_sql = """
                CASE
                    WHEN COALESCE(p.last_result, '') = 'incorrect' THEN 0
                    WHEN COALESCE(p.status, 'new') = 'learning' THEN 1
                    WHEN COALESCE(p.status, 'new') = 'mastered' THEN 2
                    ELSE 3
                END,
                COALESCE(p.total_incorrect, 0) DESC,
                CASE WHEN p.last_answered_at IS NULL THEN 1 ELSE 0 END,
                p.last_answered_at ASC,
                RANDOM()
            """
        else:
            status_filter = "COALESCE(p.status, 'new') != 'mastered'"
            order_sql = """
                CASE
                    WHEN COALESCE(p.status, 'new') = 'learning' THEN 0
                    WHEN COALESCE(p.last_result, '') = 'incorrect' THEN 1
                    WHEN COALESCE(p.status, 'new') = 'new' THEN 2
                    ELSE 3
                END,
                COALESCE(p.total_incorrect, 0) DESC,
                RANDOM()
            """

        rows = self.conn.execute(
            f"""
            SELECT
                c.*,
                COALESCE(p.status, 'new') AS progress_status,
                COALESCE(p.correct_streak, 0) AS progress_correct_streak,
                COALESCE(p.total_correct, 0) AS progress_total_correct,
                COALESCE(p.total_incorrect, 0) AS progress_total_incorrect,
                COALESCE(p.last_result, '') AS progress_last_result,
                p.last_answered_at AS progress_last_answered_at
            FROM cards c
            LEFT JOIN user_card_progress p
                ON p.card_id = c.id AND p.user_id = ?
            WHERE {status_filter}
            {chapter_sql}
            ORDER BY {order_sql}
            LIMIT ?
            """,
            (user_id, *chapter_params, max(session_size * 8, 12)),
        ).fetchall()

        payloads: list[dict[str, Any]] = []
        used_card_ids: set[int] = set()
        for row in rows:
            if row["id"] in used_card_ids:
                continue
            payload = self._build_payload_for_card(row, training_mode, options_enabled)
            if payload is None:
                continue
            payloads.append(payload)
            used_card_ids.add(row["id"])
            if len(payloads) >= session_size:
                break
        return payloads

    def _build_payload_for_card(
        self,
        card: sqlite3.Row,
        training_mode: str,
        options_enabled: bool,
    ) -> dict[str, Any] | None:
        card_type = card["card_type"] or CARD_TYPE_FLASHCARD

        if training_mode == "flashcard":
            return self._build_reveal_payload(card)

        if training_mode == "multiple_choice":
            return self._build_multiple_choice_payload(
                card,
                allow_generated=options_enabled,
                force_mode=True,
            )

        if training_mode == "true_false":
            return self._build_true_false_payload(card)

        if card_type == CARD_TYPE_MULTIPLE:
            payload = self._build_multiple_choice_payload(
                card,
                allow_generated=options_enabled,
                force_mode=False,
            )
            if payload is not None:
                return payload
            return self._build_reveal_payload(card)

        if card_type == CARD_TYPE_TRUE_FALSE:
            payload = self._build_true_false_payload(card)
            if payload is not None:
                return payload
            return self._build_reveal_payload(card)

        if card_type == CARD_TYPE_SCENARIO:
            payload = self._build_multiple_choice_payload(
                card,
                allow_generated=options_enabled,
                force_mode=False,
                presentation_type="scenario_choice",
            )
            if payload is not None:
                return payload
            return self._build_reveal_payload(card, presentation_type=CARD_TYPE_SCENARIO)

        return self._build_reveal_payload(card)

    def _build_reveal_payload(
        self,
        card: sqlite3.Row,
        presentation_type: str = CARD_TYPE_FLASHCARD,
    ) -> dict[str, Any]:
        return {
            "card_id": card["id"],
            "presentation_type": presentation_type,
            "revealed": False,
        }

    def _build_true_false_payload(self, card: sqlite3.Row) -> dict[str, Any] | None:
        if (card["card_type"] or CARD_TYPE_FLASHCARD) != CARD_TYPE_TRUE_FALSE:
            return None
        correct_option = card["correct_option"]
        if correct_option not in (0, 1):
            return None
        return {
            "card_id": card["id"],
            "presentation_type": CARD_TYPE_TRUE_FALSE,
            "options": ["Верно", "Неверно"],
            "correct_option": int(correct_option),
            "revealed": False,
        }

    def _build_multiple_choice_payload(
        self,
        card: sqlite3.Row,
        *,
        allow_generated: bool,
        force_mode: bool,
        presentation_type: str = CARD_TYPE_MULTIPLE,
    ) -> dict[str, Any] | None:
        explicit_options = self._load_options(card["options_json"])
        if explicit_options:
            correct_option = card["correct_option"]
            if correct_option is None or not 0 <= int(correct_option) < len(explicit_options):
                return None if force_mode else self._build_reveal_payload(card)
            options = list(explicit_options)
            correct_text = options[int(correct_option)]
            self._random.shuffle(options)
            return {
                "card_id": card["id"],
                "presentation_type": presentation_type,
                "options": options,
                "correct_option": options.index(correct_text),
                "revealed": False,
            }

        if not allow_generated:
            return None if force_mode else self._build_reveal_payload(card)

        distractors = self.get_distractors_for_card(card["id"], card["chapter_code"], card["article"])
        if len(distractors) < 3:
            return None if force_mode else self._build_reveal_payload(card)

        options = [card["article"], *distractors[:3]]
        correct_text = card["article"]
        self._random.shuffle(options)
        return {
            "card_id": card["id"],
            "presentation_type": presentation_type,
            "options": options,
            "correct_option": options.index(correct_text),
            "revealed": False,
        }

    def get_distractors_for_card(
        self,
        card_id: int,
        chapter_code: str,
        article: str,
    ) -> list[str]:
        same_chapter = self.conn.execute(
            """
            SELECT DISTINCT article
            FROM cards
            WHERE chapter_code = ?
              AND id != ?
              AND article != ?
            ORDER BY RANDOM()
            LIMIT 6
            """,
            (chapter_code, card_id, article),
        ).fetchall()
        distractors = [row["article"] for row in same_chapter]
        if len(distractors) < 3:
            extra = self.conn.execute(
                """
                SELECT DISTINCT article
                FROM cards
                WHERE id != ?
                  AND article != ?
                  AND chapter_code != ?
                ORDER BY RANDOM()
                LIMIT 6
                """,
                (card_id, article, chapter_code),
            ).fetchall()
            for row in extra:
                if row["article"] not in distractors:
                    distractors.append(row["article"])
        return distractors[:3]

    def get_session(self, user_id: int) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT * FROM session_state WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        if row is None:
            return None

        training_mode = row["training_mode"] or self.get_user_settings(user_id)["last_training_mode"]
        queue = self._load_json(row["queue_json"], default=[])
        queue = self._normalize_payload_list(queue, training_mode, user_id)

        current_payload = self._load_json(row["current_payload_json"], default=None)
        if current_payload is None and row["current_card_id"] is not None:
            current_payload = self._normalize_payload_value(row["current_card_id"], training_mode, user_id)
        elif current_payload is not None:
            current_payload = self._normalize_payload_value(current_payload, training_mode, user_id)

        return {
            "mode": row["mode"],
            "training_mode": training_mode,
            "current_card_id": current_payload["card_id"] if current_payload else None,
            "current_payload": current_payload,
            "queue": queue,
            "started_at": row["started_at"],
            "updated_at": row["updated_at"],
        }

    def _normalize_payload_list(
        self,
        values: list[Any],
        training_mode: str,
        user_id: int,
    ) -> list[dict[str, Any]]:
        payloads: list[dict[str, Any]] = []
        for value in values:
            payload = self._normalize_payload_value(value, training_mode, user_id)
            if payload is not None:
                payloads.append(payload)
        return payloads

    def _normalize_payload_value(
        self,
        value: Any,
        training_mode: str,
        user_id: int,
    ) -> dict[str, Any] | None:
        if isinstance(value, dict):
            return value
        if isinstance(value, int):
            card = self.get_card(value)
            if card is None:
                return None
            settings = self.get_user_settings(user_id)
            return self._build_payload_for_card(card, training_mode, settings["options_enabled"])
        return None

    def update_session(
        self,
        user_id: int,
        *,
        current_payload: dict[str, Any] | None,
        queue: list[dict[str, Any]],
        mode: str | None = None,
        training_mode: str | None = None,
    ) -> None:
        session = self.get_session(user_id)
        if session is None:
            return
        new_mode = mode or session["mode"]
        new_training_mode = training_mode or session["training_mode"]
        with self._lock, self.conn:
            self.conn.execute(
                """
                UPDATE session_state
                SET
                    mode = ?,
                    training_mode = ?,
                    current_card_id = ?,
                    current_payload_json = ?,
                    queue_json = ?,
                    updated_at = ?
                WHERE user_id = ?
                """,
                (
                    new_mode,
                    new_training_mode,
                    current_payload["card_id"] if current_payload else None,
                    self._dump_json(current_payload) if current_payload else None,
                    self._dump_json(queue),
                    self._now(),
                    user_id,
                ),
            )

    def clear_session(self, user_id: int) -> None:
        with self._lock, self.conn:
            self.conn.execute(
                "DELETE FROM session_state WHERE user_id = ?",
                (user_id,),
            )

    def pop_next_card(self, user_id: int) -> dict[str, Any] | None:
        session = self.get_session(user_id)
        if session is None:
            return None
        if session["current_payload"] is not None:
            return session
        if not session["queue"]:
            return None

        next_payload = session["queue"][0]
        remaining = session["queue"][1:]
        self.update_session(
            user_id,
            current_payload=next_payload,
            queue=remaining,
        )
        return self.get_session(user_id)

    def record_answer(self, user_id: int, card_id: int, is_correct: bool) -> dict[str, Any]:
        now = self._now()
        with self._lock, self.conn:
            self.conn.execute(
                """
                INSERT OR IGNORE INTO user_card_progress (
                    user_id,
                    card_id,
                    status,
                    correct_streak,
                    total_correct,
                    total_incorrect
                )
                VALUES (?, ?, 'new', 0, 0, 0)
                """,
                (user_id, card_id),
            )

            progress = self.conn.execute(
                """
                SELECT * FROM user_card_progress
                WHERE user_id = ? AND card_id = ?
                """,
                (user_id, card_id),
            ).fetchone()
            user = self.conn.execute(
                "SELECT points, streak, best_streak FROM users WHERE user_id = ?",
                (user_id,),
            ).fetchone()
            if progress is None or user is None:
                raise RuntimeError("Не удалось получить прогресс пользователя")

            card_streak = progress["correct_streak"]
            total_correct = progress["total_correct"]
            total_incorrect = progress["total_incorrect"]
            user_streak = user["streak"]
            best_streak = user["best_streak"]
            status = progress["status"]
            learned_at = progress["learned_at"]
            awarded_points = 0
            bonus = 0

            if is_correct:
                card_streak += 1
                total_correct += 1
                user_streak += 1
                if card_streak >= self.mastered_streak:
                    status = "mastered"
                    learned_at = now
                else:
                    status = "learning"
                awarded_points = 1
                if user_streak % 5 == 0:
                    bonus = 2
                    awarded_points += bonus
                best_streak = max(best_streak, user_streak)
            else:
                status = "learning"
                card_streak = 0
                total_incorrect += 1
                user_streak = 0

            self.conn.execute(
                """
                UPDATE user_card_progress
                SET
                    status = ?,
                    correct_streak = ?,
                    total_correct = ?,
                    total_incorrect = ?,
                    last_result = ?,
                    last_answered_at = ?,
                    learned_at = ?
                WHERE user_id = ? AND card_id = ?
                """,
                (
                    status,
                    card_streak,
                    total_correct,
                    total_incorrect,
                    "correct" if is_correct else "incorrect",
                    now,
                    learned_at,
                    user_id,
                    card_id,
                ),
            )

            self.conn.execute(
                """
                UPDATE users
                SET
                    points = points + ?,
                    streak = ?,
                    best_streak = ?,
                    updated_at = ?
                WHERE user_id = ?
                """,
                (awarded_points, user_streak, best_streak, now, user_id),
            )

            self.conn.execute(
                """
                INSERT INTO answer_history (
                    user_id,
                    card_id,
                    answered_at,
                    is_correct,
                    points_awarded,
                    streak_after
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    card_id,
                    now,
                    1 if is_correct else 0,
                    awarded_points,
                    user_streak,
                ),
            )

        return {
            "status": status,
            "card_streak": card_streak,
            "awarded_points": awarded_points,
            "bonus": bonus,
            "user_streak": user_streak,
            "mastered_now": is_correct and status == "mastered",
        }

    def get_stats(self, user_id: int) -> dict[str, Any]:
        settings = self.get_user_settings(user_id)
        selected_chapters = settings["selected_chapters"]
        chapter_sql, chapter_params = self._chapter_filter_sql(selected_chapters)

        totals = self.conn.execute(
            f"""
            SELECT
                COUNT(*) AS total_cards,
                SUM(CASE WHEN COALESCE(p.status, 'new') = 'mastered' THEN 1 ELSE 0 END) AS mastered,
                SUM(CASE WHEN COALESCE(p.status, 'new') = 'learning' THEN 1 ELSE 0 END) AS learning
            FROM cards c
            LEFT JOIN user_card_progress p
                ON p.card_id = c.id AND p.user_id = ?
            WHERE 1 = 1
            {chapter_sql}
            """,
            (user_id, *chapter_params),
        ).fetchone()

        answer_totals = self.conn.execute(
            """
            SELECT
                SUM(CASE WHEN is_correct = 1 THEN 1 ELSE 0 END) AS correct_answers,
                SUM(CASE WHEN is_correct = 0 THEN 1 ELSE 0 END) AS incorrect_answers
            FROM answer_history
            WHERE user_id = ?
            """,
            (user_id,),
        ).fetchone()

        chapter_rows = self.conn.execute(
            f"""
            SELECT
                c.chapter_code,
                c.chapter_title,
                COUNT(*) AS total_cards,
                SUM(CASE WHEN COALESCE(p.status, 'new') = 'mastered' THEN 1 ELSE 0 END) AS mastered_cards,
                SUM(CASE WHEN COALESCE(p.status, 'new') = 'learning' THEN 1 ELSE 0 END) AS learning_cards
            FROM cards c
            LEFT JOIN user_card_progress p
                ON p.card_id = c.id AND p.user_id = ?
            WHERE 1 = 1
            {chapter_sql}
            GROUP BY c.chapter_code, c.chapter_title
            ORDER BY CAST(c.chapter_code AS REAL)
            """,
            (user_id, *chapter_params),
        ).fetchall()

        today_correct = self.conn.execute(
            """
            SELECT COUNT(*) AS today_correct
            FROM answer_history
            WHERE user_id = ?
              AND is_correct = 1
              AND DATE(answered_at) = DATE('now', 'localtime')
            """,
            (user_id,),
        ).fetchone()

        total_cards = totals["total_cards"] or 0
        mastered = totals["mastered"] or 0
        learning = totals["learning"] or 0
        new_cards = max(total_cards - mastered - learning, 0)

        return {
            "total_cards": total_cards,
            "mastered": mastered,
            "learning": learning,
            "new_cards": new_cards,
            "correct_answers": answer_totals["correct_answers"] or 0,
            "incorrect_answers": answer_totals["incorrect_answers"] or 0,
            "points": settings["points"],
            "streak": settings["streak"],
            "best_streak": settings["best_streak"],
            "today_correct": today_correct["today_correct"] or 0,
            "daily_target": settings["daily_target"],
            "selected_chapters": selected_chapters,
            "preferred_training_mode": settings["preferred_training_mode"],
            "mixed_mode_enabled": settings["mixed_mode_enabled"],
            "options_enabled": settings["options_enabled"],
            "chapters": [dict(row) for row in chapter_rows],
        }

    def reset_progress(self, user_id: int) -> None:
        with self._lock, self.conn:
            self.conn.execute("DELETE FROM answer_history WHERE user_id = ?", (user_id,))
            self.conn.execute("DELETE FROM user_card_progress WHERE user_id = ?", (user_id,))
            self.conn.execute("DELETE FROM session_state WHERE user_id = ?", (user_id,))
            self.conn.execute(
                """
                UPDATE users
                SET
                    points = 0,
                    streak = 0,
                    best_streak = 0,
                    last_mode = 'study',
                    last_training_mode = 'mixed',
                    updated_at = ?
                WHERE user_id = ?
                """,
                (self._now(), user_id),
            )

    def list_reminder_users(self) -> list[sqlite3.Row]:
        return self.conn.execute(
            """
            SELECT user_id, daily_target, reminder_time
            FROM users
            WHERE reminder_enabled = 1
            """
        ).fetchall()

    def _load_options(self, raw: str | None) -> list[str]:
        if not raw:
            return []
        try:
            value = json.loads(raw)
        except json.JSONDecodeError:
            return []
        return [str(item) for item in value if str(item).strip()]

    def _dump_json(self, value: Any) -> str:
        return json.dumps(value, ensure_ascii=False)

    def _load_json(self, raw: str | None, default: Any) -> Any:
        if not raw:
            return default
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return default

    def _now(self) -> str:
        return datetime.now().isoformat(timespec="seconds")
