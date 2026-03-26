from __future__ import annotations

import logging
from datetime import datetime, time
from typing import Any

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)

from config import Settings
from database import Database


LOGGER = logging.getLogger(__name__)
CHAPTERS_PAGE_SIZE = 5

TRAINING_MODE_LABELS = {
    "flashcard": "Обычные карточки",
    "multiple_choice": "Тест с вариантами",
    "true_false": "Верно / неверно",
    "mixed": "Смешанный режим",
}

SESSION_MODE_LABELS = {
    "study": "Обучение",
    "review": "Ревизия",
}

PRESENTATION_LABELS = {
    "flashcard": "Обычная карточка",
    "multiple_choice": "Тест с вариантами",
    "true_false": "Верно / неверно",
    "scenario": "Ситуационная задача",
    "scenario_choice": "Ситуационная задача",
}


def main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🎯 Начать тренировку", callback_data="menu:start"),
                InlineKeyboardButton("▶️ Продолжить", callback_data="menu:continue"),
            ],
            [
                InlineKeyboardButton("🗂️ Выбрать главы", callback_data="menu:chapters"),
                InlineKeyboardButton("📊 Статистика", callback_data="menu:stats"),
            ],
            [
                InlineKeyboardButton("⚙️ Настройки", callback_data="menu:settings"),
                InlineKeyboardButton("❓ Помощь", callback_data="menu:help"),
            ],
        ]
    )


def start_kind_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🎓 Обучение", callback_data="sessionkind:study"),
                InlineKeyboardButton("🔁 Ревизия", callback_data="sessionkind:review"),
            ],
            [InlineKeyboardButton("⬅️ Назад", callback_data="menu:root")],
        ]
    )


def training_mode_keyboard(session_mode: str, settings: dict[str, Any]) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton("🧠 Обычные карточки", callback_data=f"training:{session_mode}:flashcard"),
            InlineKeyboardButton("📝 Тест с вариантами", callback_data=f"training:{session_mode}:multiple_choice"),
        ],
        [InlineKeyboardButton("⚖️ Верно / неверно", callback_data=f"training:{session_mode}:true_false")],
    ]
    if settings["mixed_mode_enabled"]:
        rows.append(
            [InlineKeyboardButton("🎲 Смешанный режим", callback_data=f"training:{session_mode}:mixed")]
        )
    rows.append([InlineKeyboardButton("⬅️ Назад", callback_data="menu:start")])
    return InlineKeyboardMarkup(rows)


def settings_keyboard(settings: dict[str, Any]) -> InlineKeyboardMarkup:
    hints_label = "💡 Подсказки: вкл" if settings["hints_enabled"] else "💡 Подсказки: выкл"
    mixed_label = "🎲 Смешанный режим: вкл" if settings["mixed_mode_enabled"] else "🎲 Смешанный режим: выкл"
    options_label = (
        "📝 Варианты ответа: вкл" if settings["options_enabled"] else "📝 Варианты ответа: выкл"
    )
    reminder_label = (
        f"🔔 Напоминания: {settings['reminder_time']}"
        if settings["reminder_enabled"]
        else "🔔 Напоминания: выкл"
    )
    preferred_label = TRAINING_MODE_LABELS.get(
        settings["preferred_training_mode"],
        TRAINING_MODE_LABELS["mixed"],
    )
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(f"🎯 Режим по умолчанию: {preferred_label}", callback_data="settings:preferred_mode")],
            [InlineKeyboardButton(mixed_label, callback_data="settings:mixed")],
            [InlineKeyboardButton(options_label, callback_data="settings:options_default")],
            [InlineKeyboardButton("📚 Карточек за сессию", callback_data="settings:size")],
            [InlineKeyboardButton(hints_label, callback_data="settings:hints")],
            [InlineKeyboardButton(reminder_label, callback_data="settings:reminders")],
            [InlineKeyboardButton("♻️ Сбросить прогресс", callback_data="settings:reset")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="menu:root")],
        ]
    )


def preferred_mode_keyboard(current_mode: str, mixed_enabled: bool) -> InlineKeyboardMarkup:
    rows = []
    for mode in ("flashcard", "multiple_choice", "true_false", "mixed"):
        if mode == "mixed" and not mixed_enabled:
            continue
        prefix = "• " if current_mode == mode else ""
        rows.append(
            [InlineKeyboardButton(f"{prefix}{TRAINING_MODE_LABELS[mode]}", callback_data=f"pref:set:{mode}")]
        )
    rows.append([InlineKeyboardButton("⬅️ Назад", callback_data="menu:settings")])
    return InlineKeyboardMarkup(rows)


def session_size_keyboard(current_size: int) -> InlineKeyboardMarkup:
    rows = []
    for size in (5, 10, 15, 20):
        prefix = "• " if size == current_size else ""
        rows.append([InlineKeyboardButton(f"{prefix}{size} карточек", callback_data=f"size:set:{size}")])
    rows.append([InlineKeyboardButton("⬅️ Назад", callback_data="menu:settings")])
    return InlineKeyboardMarkup(rows)


def reminder_keyboard(settings: dict[str, Any]) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                "🔕 Выключить" if settings["reminder_enabled"] else "🔔 Включить",
                callback_data="reminder:toggle",
            )
        ],
        [
            InlineKeyboardButton("5 в день", callback_data="reminder:target:5"),
            InlineKeyboardButton("10 в день", callback_data="reminder:target:10"),
            InlineKeyboardButton("15 в день", callback_data="reminder:target:15"),
        ],
        [
            InlineKeyboardButton("09:00", callback_data="reminder:time:09-00"),
            InlineKeyboardButton("19:00", callback_data="reminder:time:19-00"),
            InlineKeyboardButton("21:00", callback_data="reminder:time:21-00"),
        ],
        [InlineKeyboardButton("⬅️ Назад", callback_data="menu:settings")],
    ]
    return InlineKeyboardMarkup(rows)


def reset_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Да, сбросить", callback_data="reset:confirm"),
                InlineKeyboardButton("Отмена", callback_data="menu:settings"),
            ]
        ]
    )


def chapter_keyboard(chapters: list[dict[str, Any]], selected: list[str], page: int = 0) -> InlineKeyboardMarkup:
    total = len(chapters)
    total_pages = max((total + CHAPTERS_PAGE_SIZE - 1) // CHAPTERS_PAGE_SIZE, 1)
    current_page = min(max(page, 0), total_pages - 1)
    start = current_page * CHAPTERS_PAGE_SIZE
    end = start + CHAPTERS_PAGE_SIZE
    page_chapters = chapters[start:end]

    rows: list[list[InlineKeyboardButton]] = []
    for chapter in page_chapters:
        marker = "✅" if chapter["chapter_code"] in selected else "◻️"
        rows.append(
            [
                InlineKeyboardButton(
                    f"{marker} Глава {chapter['chapter_code']}. {chapter['chapter_title']}",
                    callback_data=f"chapter:toggle:{current_page}:{chapter['chapter_code']}",
                )
            ]
        )

    if total_pages > 1:
        nav_row: list[InlineKeyboardButton] = []
        if current_page > 0:
            nav_row.append(
                InlineKeyboardButton("⬅️ Назад", callback_data=f"chapter:page:{current_page - 1}")
            )
        nav_row.append(
            InlineKeyboardButton(f"📄 {current_page + 1}/{total_pages}", callback_data="chapter:noop")
        )
        if current_page < total_pages - 1:
            nav_row.append(
                InlineKeyboardButton("Вперёд ➡️", callback_data=f"chapter:page:{current_page + 1}")
            )
        rows.append(nav_row)

    rows.extend(
        [
            [
                InlineKeyboardButton("✅ Выбрать все", callback_data="chapter:all"),
                InlineKeyboardButton("🧹 Очистить", callback_data="chapter:clear"),
            ],
            [
                InlineKeyboardButton("💾 Сохранить", callback_data="chapter:save"),
                InlineKeyboardButton("🏠 В меню", callback_data="menu:root"),
            ],
        ]
    )
    return InlineKeyboardMarkup(rows)


def finish_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🎯 Новая тренировка", callback_data="menu:start"),
                InlineKeyboardButton("📊 Статистика", callback_data="menu:stats"),
            ],
            [InlineKeyboardButton("🏠 В меню", callback_data="menu:root")],
        ]
    )


def stats_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("▶️ Продолжить", callback_data="menu:continue"),
                InlineKeyboardButton("🔁 Ревизия", callback_data="menu:review"),
            ],
            [
                InlineKeyboardButton("🗂️ Выбрать главы", callback_data="menu:chapters"),
                InlineKeyboardButton("⚙️ Настройки", callback_data="menu:settings"),
            ],
            [InlineKeyboardButton("🏠 В меню", callback_data="menu:root")],
        ]
    )


class CriminalCodeBot:
    def __init__(self, settings: Settings, db: Database) -> None:
        self.settings = settings
        self.db = db

    def build_application(self) -> Application:
        application = (
            Application.builder()
            .token(self.settings.token)
            .post_init(self.post_init)
            .build()
        )
        application.bot_data["db"] = self.db
        application.bot_data["settings"] = self.settings

        application.add_handler(CommandHandler("start", self.start))
        application.add_handler(CommandHandler("menu", self.menu))
        application.add_handler(CallbackQueryHandler(self.handle_callback))
        return application

    async def post_init(self, application: Application) -> None:
        await application.bot.set_my_commands(
            [
                ("start", "Открыть бот"),
                ("menu", "Главное меню"),
            ]
        )
        for row in self.db.list_reminder_users():
            self.schedule_reminder(
                application,
                row["user_id"],
                row["reminder_time"],
                row["daily_target"],
            )

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.effective_user is None or update.effective_chat is None:
            return
        self.db.upsert_user(update.effective_user)
        await update.effective_chat.send_message(
            text=self.render_home_text(update.effective_user.id),
            reply_markup=main_menu_keyboard(),
        )

    async def menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.effective_user is None or update.effective_chat is None:
            return
        self.db.upsert_user(update.effective_user)
        await update.effective_chat.send_message(
            self.render_home_text(update.effective_user.id),
            reply_markup=main_menu_keyboard(),
        )

    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        user = update.effective_user
        if query is None or user is None:
            return

        self.db.upsert_user(user)
        data = query.data or ""

        try:
            if data == "menu:root":
                await query.answer()
                await query.edit_message_text(
                    self.render_home_text(user.id),
                    reply_markup=main_menu_keyboard(),
                )
                return
            if data == "menu:start":
                await query.answer()
                await query.edit_message_text(
                    "🎯 Начать тренировку\n\n"
                    "Выберите режим: обучение для нового материала или ревизию для повторения.",
                    reply_markup=start_kind_keyboard(),
                )
                return
            if data == "menu:review":
                await query.answer()
                await self.show_training_modes(query, "review")
                return
            if data == "menu:continue":
                await query.answer()
                await self.continue_session(query)
                return
            if data == "menu:chapters":
                await query.answer()
                await self.show_chapters(query)
                return
            if data == "menu:stats":
                await query.answer()
                await self.show_stats(query)
                return
            if data == "menu:settings":
                await query.answer()
                await self.show_settings(query)
                return
            if data == "menu:help":
                await query.answer()
                await self.show_help(query)
                return
            if data.startswith("sessionkind:"):
                await query.answer()
                session_mode = data.split(":", maxsplit=1)[1]
                await self.show_training_modes(query, session_mode)
                return
            if data.startswith("training:"):
                await query.answer()
                _, session_mode, training_mode = data.split(":", maxsplit=2)
                await self.start_session(query, session_mode, training_mode)
                return
            if data.startswith("chapter:toggle:"):
                await query.answer()
                _, _, page_raw, chapter_code = data.split(":", maxsplit=3)
                await self.toggle_chapter(query, chapter_code, int(page_raw))
                return
            if data.startswith("chapter:page:"):
                await query.answer()
                page = int(data.rsplit(":", maxsplit=1)[1])
                await self.show_chapters(query, page=page)
                return
            if data == "chapter:noop":
                await query.answer()
                return
            if data == "chapter:all":
                await query.answer("Выбраны все главы")
                chapters = [row["chapter_code"] for row in self.db.list_chapters()]
                self.db.set_selected_chapters(user.id, chapters)
                await self.show_chapters(query)
                return
            if data == "chapter:clear":
                await query.answer("Выбор глав очищен")
                self.db.set_selected_chapters(user.id, [])
                await self.show_chapters(query)
                return
            if data == "chapter:save":
                await query.answer("Главы сохранены")
                await query.edit_message_text(
                    self.render_home_text(user.id),
                    reply_markup=main_menu_keyboard(),
                )
                return
            if data == "card:reveal":
                await query.answer()
                await self.reveal_answer(query)
                return
            if data == "card:hint":
                await self.show_hint(query)
                return
            if data == "card:skip":
                await self.skip_card(query)
                return
            if data == "answer:know":
                await query.answer("Ответ засчитан")
                await self.process_binary_answer(query, is_correct=True)
                return
            if data == "answer:dont":
                await query.answer("Карточка вернётся в повторение")
                await self.process_binary_answer(query, is_correct=False)
                return
            if data.startswith("answer:option:"):
                await query.answer()
                option_index = int(data.rsplit(":", maxsplit=1)[1])
                await self.process_choice_answer(query, option_index)
                return
            if data == "card:next":
                await query.answer()
                await self.move_to_next_card(query)
                return
            if data == "card:finish":
                await query.answer()
                self.db.clear_session(user.id)
                await query.edit_message_text(
                    "🏁 Сессия завершена\n\n"
                    "Можно начать новую тренировку, открыть статистику или вернуться в меню.",
                    reply_markup=finish_keyboard(),
                )
                return
            if data == "settings:preferred_mode":
                await query.answer()
                settings = self.db.get_user_settings(user.id)
                await query.edit_message_text(
                    "🎯 Режим по умолчанию\n\n"
                    "Этот формат бот будет предлагать первым.",
                    reply_markup=preferred_mode_keyboard(
                        settings["preferred_training_mode"],
                        settings["mixed_mode_enabled"],
                    ),
                )
                return
            if data.startswith("pref:set:"):
                training_mode = data.rsplit(":", maxsplit=1)[1]
                self.db.set_preferred_training_mode(user.id, training_mode)
                await query.answer("Режим по умолчанию обновлён")
                await self.show_settings(query)
                return
            if data == "settings:mixed":
                settings = self.db.get_user_settings(user.id)
                new_state = not settings["mixed_mode_enabled"]
                self.db.set_mixed_mode_enabled(user.id, new_state)
                if not new_state and settings["preferred_training_mode"] == "mixed":
                    self.db.set_preferred_training_mode(user.id, "flashcard")
                await query.answer("Смешанный режим обновлён")
                await self.show_settings(query)
                return
            if data == "settings:options_default":
                settings = self.db.get_user_settings(user.id)
                self.db.set_options_enabled(user.id, not settings["options_enabled"])
                await query.answer("Настройка вариантов ответа обновлена")
                await self.show_settings(query)
                return
            if data == "settings:size":
                await query.answer()
                settings = self.db.get_user_settings(user.id)
                await query.edit_message_text(
                    "📚 Размер сессии\n\nСколько карточек удобно проходить за один подход?",
                    reply_markup=session_size_keyboard(settings["session_size"]),
                )
                return
            if data.startswith("size:set:"):
                await query.answer("Размер сессии обновлён")
                size = int(data.rsplit(":", maxsplit=1)[1])
                self.db.set_session_size(user.id, size)
                await self.show_settings(query)
                return
            if data == "settings:hints":
                settings = self.db.get_user_settings(user.id)
                self.db.set_hints_enabled(user.id, not settings["hints_enabled"])
                await query.answer("Подсказки обновлены")
                await self.show_settings(query)
                return
            if data == "settings:reminders":
                await query.answer()
                settings = self.db.get_user_settings(user.id)
                await query.edit_message_text(
                    self.render_reminder_text(settings),
                    reply_markup=reminder_keyboard(settings),
                )
                return
            if data == "reminder:toggle":
                settings = self.db.get_user_settings(user.id)
                new_state = not settings["reminder_enabled"]
                self.db.set_reminder_enabled(user.id, new_state)
                refreshed = self.db.get_user_settings(user.id)
                self.reschedule_reminder(context.application, user.id, refreshed)
                await query.answer("Напоминания обновлены")
                await query.edit_message_text(
                    self.render_reminder_text(refreshed),
                    reply_markup=reminder_keyboard(refreshed),
                )
                return
            if data.startswith("reminder:target:"):
                target = int(data.rsplit(":", maxsplit=1)[1])
                self.db.set_daily_target(user.id, target)
                refreshed = self.db.get_user_settings(user.id)
                self.reschedule_reminder(context.application, user.id, refreshed)
                await query.answer("Дневная цель обновлена")
                await query.edit_message_text(
                    self.render_reminder_text(refreshed),
                    reply_markup=reminder_keyboard(refreshed),
                )
                return
            if data.startswith("reminder:time:"):
                reminder_time = data.rsplit(":", maxsplit=1)[1].replace("-", ":")
                self.db.set_reminder_time(user.id, reminder_time)
                refreshed = self.db.get_user_settings(user.id)
                self.reschedule_reminder(context.application, user.id, refreshed)
                await query.answer("Время напоминания обновлено")
                await query.edit_message_text(
                    self.render_reminder_text(refreshed),
                    reply_markup=reminder_keyboard(refreshed),
                )
                return
            if data == "settings:reset":
                await query.answer()
                await query.edit_message_text(
                    "♻️ Сброс прогресса\n\n"
                    "Будут очищены ответы, прогресс по карточкам и текущая сессия.\n"
                    "Главы и общие настройки сохранятся.",
                    reply_markup=reset_keyboard(),
                )
                return
            if data == "reset:confirm":
                self.db.reset_progress(user.id)
                await query.answer("Прогресс сброшен")
                await query.edit_message_text(
                    "Готово: прогресс обнулён.\n\n"
                    "Выбранные главы и остальные настройки сохранены.",
                    reply_markup=InlineKeyboardMarkup(
                        [[InlineKeyboardButton("⚙️ В настройки", callback_data="menu:settings")]]
                    ),
                )
                return

            await query.answer("Неизвестное действие", show_alert=True)
        except Exception as exc:
            LOGGER.exception("Ошибка обработки callback %s", data, exc_info=exc)
            await query.answer("Что-то пошло не так. Попробуйте ещё раз.", show_alert=True)

    async def show_training_modes(self, query, session_mode: str) -> None:
        settings = self.db.get_user_settings(query.from_user.id)
        title = "обучения" if session_mode == "study" else "ревизии"
        await query.edit_message_text(
            f"🧩 Формат {title}\n\n"
            "Выберите, как именно хотите отвечать на карточки.",
            reply_markup=training_mode_keyboard(session_mode, settings),
        )

    async def show_chapters(self, query, page: int = 0) -> None:
        user_id = query.from_user.id
        settings = self.db.get_user_settings(user_id)
        chapters = [dict(row) for row in self.db.list_chapters()]
        selected = settings["selected_chapters"]
        count = len(selected)
        total_pages = max((len(chapters) + CHAPTERS_PAGE_SIZE - 1) // CHAPTERS_PAGE_SIZE, 1)
        current_page = min(max(page, 0), total_pages - 1)
        if selected:
            preview = ", ".join(f"гл. {code}" for code in selected[:5])
            if len(selected) > 5:
                preview += ", ..."
        else:
            preview = "все доступные главы"
        await query.edit_message_text(
            "🗂️ Выбор глав\n\n"
            f"Выбрано: {count if count else 'все'}\n"
            f"Сейчас в подборке: {preview}\n\n"
            f"Страница: {current_page + 1}/{total_pages}\n\n"
            "Отметьте нужные главы. Если ничего не выбрано, бот использует все карточки.",
            reply_markup=chapter_keyboard(chapters, selected, page=current_page),
        )

    async def toggle_chapter(self, query, chapter_code: str, page: int = 0) -> None:
        user_id = query.from_user.id
        settings = self.db.get_user_settings(user_id)
        selected = set(settings["selected_chapters"])
        if chapter_code in selected:
            selected.remove(chapter_code)
        else:
            selected.add(chapter_code)
        self.db.set_selected_chapters(user_id, list(selected))
        await self.show_chapters(query, page=page)

    async def show_settings(self, query) -> None:
        user_id = query.from_user.id
        settings = self.db.get_user_settings(user_id)
        selected = settings["selected_chapters"]
        selected_text = ", ".join(selected) if selected else "все доступные"
        preferred_label = TRAINING_MODE_LABELS.get(
            settings["preferred_training_mode"],
            TRAINING_MODE_LABELS["mixed"],
        )
        text = (
            "⚙️ Настройки\n\n"
            "Подстройте темп и формат обучения под себя.\n\n"
            f"Режим по умолчанию: {preferred_label}\n"
            f"Смешанный режим: {'включён' if settings['mixed_mode_enabled'] else 'выключен'}\n"
            f"Варианты ответа: {'включены' if settings['options_enabled'] else 'выключены'}\n"
            f"Карточек за сессию: {settings['session_size']}\n"
            f"Подсказки: {'включены' if settings['hints_enabled'] else 'выключены'}\n"
            f"Напоминания: {'включены' if settings['reminder_enabled'] else 'выключены'}\n"
            f"Ежедневная цель: {settings['daily_target']}\n"
            f"Время напоминания: {settings['reminder_time']}\n"
            f"Главы в фильтре: {selected_text}"
        )
        await query.edit_message_text(text, reply_markup=settings_keyboard(settings))

    async def show_stats(self, query) -> None:
        user_id = query.from_user.id
        stats = self.db.get_stats(user_id)
        selected_text = ", ".join(stats["selected_chapters"]) if stats["selected_chapters"] else "все"
        total_answers = stats["correct_answers"] + stats["incorrect_answers"]
        success_rate = round((stats["correct_answers"] / total_answers) * 100) if total_answers else 0
        chapter_lines = []
        for item in stats["chapters"]:
            progress = round((item["mastered_cards"] / item["total_cards"]) * 100) if item["total_cards"] else 0
            chapter_lines.append(
                f"Глава {item['chapter_code']}: {item['mastered_cards']}/{item['total_cards']} · {progress}%"
            )
        if not chapter_lines:
            chapter_lines.append("Нет данных по выбранным главам")

        text = (
            "📊 Моя статистика\n\n"
            "Общий прогресс\n"
            f"Всего карточек: {stats['total_cards']}\n"
            f"Изучено: {stats['mastered']}\n"
            f"В процессе: {stats['learning']}\n"
            f"Ошибок: {stats['incorrect_answers']}\n"
            f"Ждут ревизии: {stats['review_ready']}\n\n"
            "Результаты\n"
            f"Правильных ответов: {stats['correct_answers']}\n"
            f"Успешность: {success_rate}%\n"
            f"Баллы: {stats['points']}\n"
            f"Текущая серия: {stats['streak']}\n"
            f"Лучшая серия: {stats['best_streak']}\n\n"
            "Сегодня\n"
            f"Выполнено: {stats['today_correct']}/{stats['daily_target']}\n"
            f"Выбранные главы: {selected_text}\n\n"
            "Прогресс по главам\n"
            + "\n".join(chapter_lines)
        )
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("🏠 В меню", callback_data="menu:root")]]
            ),
        )

    async def show_stats(self, query) -> None:
        user_id = query.from_user.id
        stats = self.db.get_stats(user_id)
        total_answers = stats["correct_answers"] + stats["incorrect_answers"]
        success_rate = round((stats["correct_answers"] / total_answers) * 100) if total_answers else 0
        overall_progress = round((stats["mastered"] / stats["total_cards"]) * 100) if stats["total_cards"] else 0

        selected_count = len(stats["selected_chapters"])
        if stats["selected_chapters"]:
            selected_text = ", ".join(f"гл. {code}" for code in stats["selected_chapters"][:5])
            if selected_count > 5:
                selected_text = f"{selected_text} и ещё {selected_count - 5}"
        else:
            selected_text = "все главы"

        chapter_lines = self.compose_chapter_summary(stats["chapters"])
        daily_bar = self.progress_bar(
            min(stats["today_correct"], stats["daily_target"]),
            max(stats["daily_target"], 1),
        )
        last_activity = self.format_last_activity(stats.get("last_activity"))
        recommendation = self.stats_recommendation(stats, success_rate)

        text = (
            "📊 Статистика\n\n"
            f"{self.stats_headline(stats, success_rate)}\n\n"
            "Прогресс\n"
            f"• Всего карточек: {stats['total_cards']}\n"
            f"• Изучено: {stats['mastered']} ({overall_progress}%)\n"
            f"• В работе: {stats['learning']}\n"
            f"• Новые: {stats['new_cards']}\n"
            f"• Ждут ревизии: {stats['review_ready']}\n"
            f"• Осталось пройти: {stats['remaining_cards']}\n\n"
            "Ответы\n"
            f"• Верных: {stats['correct_answers']}\n"
            f"• Ошибок: {stats['incorrect_answers']}\n"
            f"• Успешность: {success_rate}%\n"
            f"• Карточек с ошибками: {stats['cards_with_errors']}\n"
            f"• Серия сейчас: {stats['streak']}\n"
            f"• Лучшая серия: {stats['best_streak']}\n"
            f"• Баллы: {stats['points']}\n\n"
            "Сегодня\n"
            f"• Цель: {stats['today_correct']}/{stats['daily_target']}\n"
            f"• Прогресс дня: {daily_bar}\n"
            f"• Активные главы: {selected_text}\n"
            f"• Последняя активность: {last_activity}\n\n"
            "Главы\n"
            + "\n".join(chapter_lines)
            + "\n\n"
            "Что дальше\n"
            f"{recommendation}"
        )
        await query.edit_message_text(text, reply_markup=stats_keyboard())

    async def start_session(self, query, session_mode: str, training_mode: str) -> None:
        user_id = query.from_user.id
        session = self.db.create_session(user_id, session_mode, training_mode)
        if session is None:
            await query.edit_message_text(
                self.empty_session_message(session_mode, training_mode),
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton("🗂️ Выбрать главы", callback_data="menu:chapters"),
                            InlineKeyboardButton("🔄 Другой формат", callback_data=f"sessionkind:{session_mode}"),
                        ],
                        [InlineKeyboardButton("🏠 В меню", callback_data="menu:root")],
                    ]
                ),
            )
            return
        await self.show_current_card(query, session)

    async def continue_session(self, query) -> None:
        user_id = query.from_user.id
        session = self.db.get_session(user_id)
        if session is None:
            settings = self.db.get_user_settings(user_id)
            training_mode = settings["last_training_mode"]
            if training_mode == "mixed" and not settings["mixed_mode_enabled"]:
                training_mode = settings["preferred_training_mode"]
                if training_mode == "mixed":
                    training_mode = "flashcard"
            await self.start_session(query, settings["last_mode"], training_mode)
            return

        if session["current_payload"] is None:
            session = self.db.pop_next_card(user_id)
            if session is None:
                self.db.clear_session(user_id)
                await query.edit_message_text(
                    "Активная сессия уже завершена.",
                    reply_markup=InlineKeyboardMarkup(
                        [[InlineKeyboardButton("🏠 В меню", callback_data="menu:root")]]
                    ),
                )
                return
        await self.show_current_card(query, session)

    async def show_current_card(self, query, session: dict[str, Any]) -> None:
        payload = session["current_payload"]
        if payload is None:
            await query.edit_message_text(
                "В этой сессии карточки закончились.",
                reply_markup=finish_keyboard(),
            )
            return

        card = self.db.get_card(payload["card_id"])
        if card is None:
            await query.edit_message_text(
                "Карточка не найдена. Сессия будет завершена.",
                reply_markup=finish_keyboard(),
            )
            return

        settings = self.db.get_user_settings(query.from_user.id)
        card_progress = self.db.get_card_progress(query.from_user.id, card["id"])
        text, keyboard = self.render_card(card, payload, session, settings, card_progress)
        await query.edit_message_text(text, reply_markup=keyboard)

    def render_card(
        self,
        card,
        payload: dict[str, Any],
        session: dict[str, Any],
        settings: dict[str, Any],
        card_progress: dict[str, Any],
    ) -> tuple[str, InlineKeyboardMarkup]:
        presentation = payload["presentation_type"]
        total_cards = max(int(session.get("total_cards", 0) or 0), 1)
        answered_cards = int(session.get("answered_cards", 0) or 0)
        current_number = min(answered_cards + 1, total_cards)
        reveal_article = bool(payload.get("revealed"))
        article_line = f"Статья: {card['article']}" if reveal_article else "Статья: скрыта до ответа"
        header = (
            f"{self.session_mode_icon(session['mode'])} {SESSION_MODE_LABELS.get(session['mode'], 'Обучение')} · карточка {current_number}/{total_cards}\n"
            f"{self.progress_bar(current_number, total_cards)}\n\n"
            f"Глава {card['chapter_code']}. {card['chapter_title']}\n"
            f"{article_line}\n"
            f"Тип: {PRESENTATION_LABELS.get(presentation, 'Карточка')}\n"
            f"Сложность: {self.difficulty_label(card['difficulty'])}\n"
            f"Статус: {self.card_status_label(card_progress['status'], card_progress['correct_streak'])}\n"
            f"Прогресс карточки: {min(card_progress['correct_streak'], self.settings.mastered_streak)}/{self.settings.mastered_streak}"
        )

        if presentation in {"multiple_choice", "scenario_choice"}:
            prompt_label = "Ситуация" if presentation == "scenario_choice" else "Вопрос"
            text = (
                f"{header}\n\n"
                f"— {prompt_label}\n{card['question']}\n\n"
                "Выберите вариант ниже."
            )
            return text, self.choice_keyboard(payload.get("options", []), settings["hints_enabled"], bool(card["hint"]))

        if presentation == "true_false":
            text = (
                f"{header}\n\n"
                f"— Утверждение\n{card['question']}\n\n"
                "Выберите, верно это утверждение или нет."
            )
            return text, self.true_false_keyboard(settings["hints_enabled"], bool(card["hint"]))

        prompt_label = "Ситуация" if presentation == "scenario" else "Вопрос"
        text = f"{header}\n\n— {prompt_label}\n{card['question']}"
        if payload.get("revealed"):
            answer_block = self.compose_answer_block(card)
            text = f"{text}\n\n{answer_block}"
        return text, self.reveal_keyboard(
            revealed=bool(payload.get("revealed")),
            hints_enabled=settings["hints_enabled"],
            has_hint=bool(card["hint"]),
        )

    def reveal_keyboard(
        self,
        *,
        revealed: bool,
        hints_enabled: bool,
        has_hint: bool,
    ) -> InlineKeyboardMarkup:
        rows: list[list[InlineKeyboardButton]] = []
        if not revealed:
            rows.append([InlineKeyboardButton("👀 Показать ответ", callback_data="card:reveal")])
        if hints_enabled and has_hint:
            rows.append([InlineKeyboardButton("💡 Подсказка", callback_data="card:hint")])
        rows.append(
            [
                InlineKeyboardButton("✅ Знаю", callback_data="answer:know"),
                InlineKeyboardButton("🤔 Не знаю", callback_data="answer:dont"),
            ]
        )
        rows.append([InlineKeyboardButton("⏭️ Пропустить", callback_data="card:skip")])
        rows.append([InlineKeyboardButton("🏠 В меню", callback_data="menu:root")])
        return InlineKeyboardMarkup(rows)

    def choice_keyboard(
        self,
        options: list[str],
        hints_enabled: bool,
        has_hint: bool,
    ) -> InlineKeyboardMarkup:
        rows = [
            [InlineKeyboardButton(option, callback_data=f"answer:option:{index}")]
            for index, option in enumerate(options)
        ]
        if hints_enabled and has_hint:
            rows.append([InlineKeyboardButton("💡 Подсказка", callback_data="card:hint")])
        rows.append([InlineKeyboardButton("⏭️ Пропустить", callback_data="card:skip")])
        rows.append([InlineKeyboardButton("🏠 В меню", callback_data="menu:root")])
        return InlineKeyboardMarkup(rows)

    def true_false_keyboard(self, hints_enabled: bool, has_hint: bool) -> InlineKeyboardMarkup:
        rows = [
            [
                InlineKeyboardButton("✅ Верно", callback_data="answer:option:0"),
                InlineKeyboardButton("❌ Неверно", callback_data="answer:option:1"),
            ]
        ]
        if hints_enabled and has_hint:
            rows.append([InlineKeyboardButton("💡 Подсказка", callback_data="card:hint")])
        rows.append([InlineKeyboardButton("⏭️ Пропустить", callback_data="card:skip")])
        rows.append([InlineKeyboardButton("🏠 В меню", callback_data="menu:root")])
        return InlineKeyboardMarkup(rows)

    async def reveal_answer(self, query) -> None:
        user_id = query.from_user.id
        session = self.db.get_session(user_id)
        if session is None or session["current_payload"] is None:
            await query.answer("Нет активной карточки", show_alert=True)
            return

        payload = dict(session["current_payload"])
        payload["revealed"] = True
        self.db.update_session(
            user_id,
            current_payload=payload,
            queue=session["queue"],
        )
        refreshed = self.db.get_session(user_id)
        if refreshed is None:
            return
        await self.show_current_card(query, refreshed)

    async def show_hint(self, query) -> None:
        session = self.db.get_session(query.from_user.id)
        if session is None or session["current_payload"] is None:
            await query.answer("Нет активной карточки", show_alert=True)
            return
        settings = self.db.get_user_settings(query.from_user.id)
        if not settings["hints_enabled"]:
            await query.answer("Подсказки отключены в настройках", show_alert=True)
            return
        card = self.db.get_card(session["current_payload"]["card_id"])
        if card is None or not card["hint"]:
            await query.answer("Для этой карточки подсказки нет", show_alert=True)
            return
        await query.answer(card["hint"], show_alert=True)

    async def skip_card(self, query) -> None:
        user_id = query.from_user.id
        session = self.db.get_session(user_id)
        if session is None or session["current_payload"] is None:
            await query.edit_message_text(
                "Активная сессия не найдена.",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("🏠 В меню", callback_data="menu:root")]]
                ),
            )
            return

        if not session["queue"]:
            await query.answer("Это последняя карточка в очереди", show_alert=True)
            return

        await query.answer("Карточка перенесена в конец очереди")
        queue = list(session["queue"])
        queue.append(session["current_payload"])
        self.db.update_session(user_id, current_payload=None, queue=queue)
        await self.move_to_next_card(query)

    async def process_binary_answer(self, query, is_correct: bool) -> None:
        await self.finalize_answer(query, is_correct, selected_option=None)

    async def process_choice_answer(self, query, selected_option: int) -> None:
        user_id = query.from_user.id
        session = self.db.get_session(user_id)
        if session is None or session["current_payload"] is None:
            await query.edit_message_text(
                "Активная сессия не найдена.",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("🏠 В меню", callback_data="menu:root")]]
                ),
            )
            return

        payload = session["current_payload"]
        correct_option = payload.get("correct_option")
        if correct_option is None:
            await query.answer("Для этой карточки нет вариантов ответа", show_alert=True)
            return
        await self.finalize_answer(
            query,
            is_correct=(selected_option == int(correct_option)),
            selected_option=selected_option,
        )

    async def finalize_answer(
        self,
        query,
        is_correct: bool,
        selected_option: int | None,
    ) -> None:
        user_id = query.from_user.id
        session = self.db.get_session(user_id)
        if session is None or session["current_payload"] is None:
            await query.edit_message_text(
                "Активная сессия не найдена.",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("🏠 В меню", callback_data="menu:root")]]
                ),
            )
            return

        payload = session["current_payload"]
        card = self.db.get_card(payload["card_id"])
        if card is None:
            self.db.clear_session(user_id)
            await query.edit_message_text(
                "Карточка не найдена. Сессия завершена.",
                reply_markup=finish_keyboard(),
            )
            return

        result = self.db.record_answer(user_id, card["id"], is_correct)
        queue = list(session["queue"])
        if result["status"] != "mastered":
            recycled_payload = dict(payload)
            recycled_payload["revealed"] = False
            queue.append(recycled_payload)

        self.db.update_session(
            user_id,
            current_payload=None,
            queue=queue,
            mode=session["mode"],
            training_mode=session["training_mode"],
            answered_cards=session["answered_cards"] + 1,
            total_cards=session["total_cards"] + (1 if result["status"] != "mastered" else 0),
        )

        title = "✅ Верно" if is_correct else "📌 Повторим ещё раз"
        text = self.compose_feedback_text(
            card,
            payload,
            result,
            selected_option=selected_option,
            is_correct=is_correct,
        )
        await query.edit_message_text(
            f"{title}\n\n{text}",
            reply_markup=self.after_answer_keyboard(bool(queue)),
        )

    def after_answer_keyboard(self, has_next: bool) -> InlineKeyboardMarkup:
        first_row = [
            InlineKeyboardButton(
                "➡️ Следующая карточка" if has_next else "🏁 Завершить сессию",
                callback_data="card:next" if has_next else "card:finish",
            )
        ]
        rows = [first_row]
        if has_next:
            rows.append([InlineKeyboardButton("⏸ Продолжить позже", callback_data="menu:root")])
        rows.append([InlineKeyboardButton("🏠 В меню", callback_data="menu:root")])
        return InlineKeyboardMarkup(rows)

    def compose_feedback_text(
        self,
        card,
        payload: dict[str, Any],
        result: dict[str, Any],
        *,
        selected_option: int | None,
        is_correct: bool,
    ) -> str:
        status_text = self.card_status_label(result["status"], result["card_streak"])
        answer_block = self.compose_answer_block(card)
        choice_block = ""
        options = payload.get("options", [])
        if selected_option is not None and options:
            selected_text = options[selected_option] if 0 <= selected_option < len(options) else "не выбран"
            correct_index = int(payload.get("correct_option", 0))
            correct_text = options[correct_index] if 0 <= correct_index < len(options) else card["answer"]
            choice_block = (
                f"Ваш выбор: {selected_text}\n"
                f"Правильный вариант: {correct_text}\n\n"
            )

        points_text = f"Баллы: +{result['awarded_points']}"
        if result["bonus"]:
            points_text += f" (включая бонус +{result['bonus']})"

        if result["status"] == "mastered":
            action_text = "Что произошло: карточка отмечена как выученная."
        elif is_correct:
            action_text = "Что произошло: прогресс вырос, карточка останется в повторении до закрепления."
        else:
            action_text = "Что произошло: карточка возвращена в повторение."

        return (
            f"{choice_block}"
            f"{answer_block}\n\n"
            f"{action_text}\n"
            f"Статус карточки: {status_text}\n"
            f"Верных подряд по карточке: {result['card_streak']}/{self.settings.mastered_streak}\n"
            f"{points_text}\n"
            f"Текущая серия: {result['user_streak']}"
        )

    def compose_answer_block(self, card) -> str:
        explanation = card["explanation"] or card["answer"]
        example = f"\nПример: {card['example']}" if card["example"] else ""
        return (
            f"Правильный ответ\n{card['answer']}\n\n"
            f"Коротко\n{explanation}{example}"
        )

    async def move_to_next_card(self, query) -> None:
        user_id = query.from_user.id
        session = self.db.pop_next_card(user_id)
        if session is None:
            self.db.clear_session(user_id)
            await query.edit_message_text(
                "🏁 Сессия завершена\n\n"
                "Все карточки из текущей подборки обработаны.",
                reply_markup=finish_keyboard(),
            )
            return
        await self.show_current_card(query, session)

    def empty_session_message(self, session_mode: str, training_mode: str) -> str:
        if session_mode == "review":
            return (
                "🔁 Для ревизии пока нет карточек.\n\n"
                "Сначала пройдите обучение, чтобы появились карточки для повторения."
            )
        return (
            f"Пока не нашлось карточек для режима «{TRAINING_MODE_LABELS.get(training_mode, training_mode)}».\n\n"
            "Проверьте выбранные главы или попробуйте другой формат обучения."
        )

    def render_reminder_text(self, settings: dict[str, Any]) -> str:
        status = "включены" if settings["reminder_enabled"] else "выключены"
        return (
            "🔔 Напоминания\n\n"
            f"Статус: {status}\n"
            f"Ежедневная цель: {settings['daily_target']} карточек\n"
            f"Время: {settings['reminder_time']}\n\n"
            "Бот будет раз в день напоминать о цели и возвращать вас к тренировке."
        )

    async def show_help(self, query) -> None:
        text = (
            "❓ Помощь\n\n"
            "Как начать\n"
            "1. Выберите главы.\n"
            "2. Нажмите «Начать тренировку».\n"
            "3. Выберите удобный режим ответа.\n\n"
            "Как работают карточки\n"
            "Обычные карточки помогают вспоминать ответ самостоятельно.\n"
            "Тесты и режим «Верно / неверно» подходят для быстрой проверки.\n\n"
            "Что такое ревизия\n"
            "Ревизия повторяет уже встречавшиеся карточки: с ошибками, в процессе и ранее выученные.\n\n"
            "Статистика\n"
            "Показывает общий прогресс, серию, ошибки и количество карточек, которые ждут повторения."
        )
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("⬅️ Назад", callback_data="menu:root")]]
            ),
        )

    def render_home_text(self, user_id: int) -> str:
        stats = self.db.get_stats(user_id)
        selected_count = len(stats["selected_chapters"])
        selected_text = f"{selected_count}" if selected_count else "все"
        return (
            "⚖️ Законник\n\n"
            "Учите главы УК РФ короткими сессиями, повторяйте сложные карточки и отслеживайте прогресс каждый день.\n\n"
            f"Сегодня: {stats['today_correct']}/{stats['daily_target']} карточек\n"
            f"Ждут ревизии: {stats['review_ready']}\n"
            f"Выбрано глав: {selected_text}"
        )

    def progress_bar(self, current: int, total: int, length: int = 8) -> str:
        safe_total = max(total, 1)
        clamped = min(max(current, 0), safe_total)
        filled = round((clamped / safe_total) * length)
        return "█" * filled + "░" * (length - filled)

    def stats_headline(self, stats: dict[str, Any], success_rate: int) -> str:
        if stats["review_ready"] >= max(stats["learning"], 3):
            return "Есть хороший прогресс, и часть карточек уже просится на повторение."
        if stats["cards_with_errors"] > 0:
            return "Есть что закрепить: сложные карточки уже видны, и это хороший ориентир."
        if stats["mastered"] and success_rate >= 80:
            return "Хороший темп: материал закрепляется уверенно."
        if stats["correct_answers"] == 0 and stats["incorrect_answers"] == 0:
            return "Статистика появится после первых ответов. Можно начать с короткой тренировки."
        return "Прогресс уже есть. Продолжайте в комфортном ритме."

    def compose_chapter_summary(self, chapters: list[dict[str, Any]]) -> list[str]:
        if not chapters:
            return ["• Пока нет данных по выбранным главам."]

        prepared: list[dict[str, Any]] = []
        for item in chapters:
            total_cards = item["total_cards"] or 0
            mastered_cards = item["mastered_cards"] or 0
            learning_cards = item["learning_cards"] or 0
            error_cards = item.get("error_cards", 0) or 0
            progress = round((mastered_cards / total_cards) * 100) if total_cards else 0
            prepared.append(
                {
                    "chapter_code": item["chapter_code"],
                    "total_cards": total_cards,
                    "mastered_cards": mastered_cards,
                    "learning_cards": learning_cards,
                    "error_cards": error_cards,
                    "progress": progress,
                }
            )

        active = [item for item in prepared if item["mastered_cards"] or item["learning_cards"] or item["error_cards"]]
        visible = active[:5] if active else prepared[:5]
        lines = []
        for item in visible:
            mood = "почти готово" if item["progress"] >= 75 else "идёт работа" if item["progress"] >= 25 else "старт"
            lines.append(
                f"• Глава {item['chapter_code']}: {item['mastered_cards']}/{item['total_cards']} · {item['progress']}% · {mood}"
            )
        hidden = len(active if active else prepared) - len(visible)
        if hidden > 0:
            lines.append(f"• Ещё глав в подборке: {hidden}")
        return lines

    def stats_recommendation(self, stats: dict[str, Any], success_rate: int) -> str:
        if stats["cards_with_errors"] > 0:
            return "Есть карточки с ошибками — лучше сначала пройти ревизию и закрепить их."
        if stats["review_ready"] >= max(3, stats["daily_target"] // 2):
            return "Пора на ревизию: уже накопились карточки, которые стоит освежить."
        if stats["new_cards"] > 0 and success_rate >= 70:
            return "Хороший прогресс. Можно продолжить обучение и взять новые карточки."
        if stats["learning"] > 0:
            return "Сейчас полезнее продолжить обучение и добить карточки, которые уже в работе."
        return "Подборка выглядит уверенно. Можно выбрать новую главу или устроить короткую ревизию."

    def format_last_activity(self, raw_value: str | None) -> str:
        if not raw_value:
            return "ещё не было ответов"
        try:
            parsed = datetime.fromisoformat(raw_value)
        except ValueError:
            return raw_value
        return parsed.strftime("%d.%m.%Y %H:%M")

    def difficulty_label(self, value: str | None) -> str:
        mapping = {
            "easy": "Лёгкая",
            "medium": "Средняя",
            "hard": "Сложная",
        }
        return mapping.get((value or "").lower(), "Не указана")

    def card_status_label(self, status: str, streak: int) -> str:
        if status == "mastered":
            return "Выучена"
        if status == "learning" and streak >= max(self.settings.mastered_streak - 1, 1):
            return "Почти выучена"
        if status == "learning":
            return "В процессе"
        return "Новая"

    def session_mode_icon(self, mode: str) -> str:
        return "🎓" if mode == "study" else "🔁"

    def schedule_reminder(
        self,
        application: Application,
        user_id: int,
        reminder_time: str,
        daily_target: int,
    ) -> None:
        hours, minutes = map(int, reminder_time.split(":"))
        job_name = self.reminder_job_name(user_id)
        for job in application.job_queue.get_jobs_by_name(job_name):
            job.schedule_removal()
        application.job_queue.run_daily(
            self.send_reminder,
            time=time(hour=hours, minute=minutes, tzinfo=self.settings.timezone),
            chat_id=user_id,
            name=job_name,
            data={"daily_target": daily_target},
        )

    def reschedule_reminder(
        self, application: Application, user_id: int, settings: dict[str, Any]
    ) -> None:
        job_name = self.reminder_job_name(user_id)
        for job in application.job_queue.get_jobs_by_name(job_name):
            job.schedule_removal()
        if settings["reminder_enabled"]:
            self.schedule_reminder(
                application,
                user_id,
                settings["reminder_time"],
                settings["daily_target"],
            )

    async def send_reminder(self, context: ContextTypes.DEFAULT_TYPE) -> None:
        job = context.job
        user_id = job.chat_id
        if user_id is None:
            return
        stats = self.db.get_stats(user_id)
        remaining = max(stats["daily_target"] - stats["today_correct"], 0)
        text = (
            "Напоминание об обучении УК РФ.\n\n"
            f"Цель на сегодня: {stats['daily_target']} карточек.\n"
            f"Уже выполнено: {stats['today_correct']}.\n"
            f"Осталось: {remaining}.\n\n"
            "Откройте бота и продолжите обучение, чтобы не терять серию."
        )
        await context.bot.send_message(chat_id=user_id, text=text, reply_markup=main_menu_keyboard())

    def reminder_job_name(self, user_id: int) -> str:
        return f"daily-reminder-{user_id}"
