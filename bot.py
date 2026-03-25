from __future__ import annotations

import logging
from datetime import time
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
                InlineKeyboardButton("Начать обучение", callback_data="menu:start"),
                InlineKeyboardButton("Выбрать главу УК", callback_data="menu:chapters"),
            ],
            [
                InlineKeyboardButton("Продолжить обучение", callback_data="menu:continue"),
                InlineKeyboardButton("Моя статистика", callback_data="menu:stats"),
            ],
            [InlineKeyboardButton("Настройки", callback_data="menu:settings")],
        ]
    )


def start_kind_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Обучение", callback_data="sessionkind:study"),
                InlineKeyboardButton("Ревизия", callback_data="sessionkind:review"),
            ],
            [InlineKeyboardButton("Назад", callback_data="menu:root")],
        ]
    )


def training_mode_keyboard(session_mode: str, settings: dict[str, Any]) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton("Обычные карточки", callback_data=f"training:{session_mode}:flashcard"),
            InlineKeyboardButton("Тест с вариантами", callback_data=f"training:{session_mode}:multiple_choice"),
        ],
        [InlineKeyboardButton("Верно / неверно", callback_data=f"training:{session_mode}:true_false")],
    ]
    if settings["mixed_mode_enabled"]:
        rows.append(
            [InlineKeyboardButton("Смешанный режим", callback_data=f"training:{session_mode}:mixed")]
        )
    rows.append([InlineKeyboardButton("Назад", callback_data="menu:start")])
    return InlineKeyboardMarkup(rows)


def settings_keyboard(settings: dict[str, Any]) -> InlineKeyboardMarkup:
    hints_label = "Подсказки: вкл" if settings["hints_enabled"] else "Подсказки: выкл"
    mixed_label = "Смешанный режим: вкл" if settings["mixed_mode_enabled"] else "Смешанный режим: выкл"
    options_label = (
        "Варианты ответа: вкл" if settings["options_enabled"] else "Варианты ответа: выкл"
    )
    reminder_label = (
        f"Напоминания: {settings['reminder_time']}"
        if settings["reminder_enabled"]
        else "Напоминания: выкл"
    )
    preferred_label = TRAINING_MODE_LABELS.get(
        settings["preferred_training_mode"],
        TRAINING_MODE_LABELS["mixed"],
    )
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(f"Режим по умолчанию: {preferred_label}", callback_data="settings:preferred_mode")],
            [InlineKeyboardButton(mixed_label, callback_data="settings:mixed")],
            [InlineKeyboardButton(options_label, callback_data="settings:options_default")],
            [InlineKeyboardButton("Карточек за сессию", callback_data="settings:size")],
            [InlineKeyboardButton(hints_label, callback_data="settings:hints")],
            [InlineKeyboardButton(reminder_label, callback_data="settings:reminders")],
            [InlineKeyboardButton("Сбросить прогресс", callback_data="settings:reset")],
            [InlineKeyboardButton("Назад", callback_data="menu:root")],
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
    rows.append([InlineKeyboardButton("Назад", callback_data="menu:settings")])
    return InlineKeyboardMarkup(rows)


def session_size_keyboard(current_size: int) -> InlineKeyboardMarkup:
    rows = []
    for size in (5, 10, 15, 20):
        prefix = "• " if size == current_size else ""
        rows.append([InlineKeyboardButton(f"{prefix}{size} карточек", callback_data=f"size:set:{size}")])
    rows.append([InlineKeyboardButton("Назад", callback_data="menu:settings")])
    return InlineKeyboardMarkup(rows)


def reminder_keyboard(settings: dict[str, Any]) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                "Выключить" if settings["reminder_enabled"] else "Включить",
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
        [InlineKeyboardButton("Назад", callback_data="menu:settings")],
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


def chapter_keyboard(chapters: list[dict[str, Any]], selected: list[str]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for chapter in chapters:
        marker = "✅ " if chapter["chapter_code"] in selected else ""
        rows.append(
            [
                InlineKeyboardButton(
                    f"{marker}Глава {chapter['chapter_code']}. {chapter['chapter_title']}",
                    callback_data=f"chapter:toggle:{chapter['chapter_code']}",
                )
            ]
        )
    rows.extend(
        [
            [
                InlineKeyboardButton("Выбрать все", callback_data="chapter:all"),
                InlineKeyboardButton("Очистить", callback_data="chapter:clear"),
            ],
            [InlineKeyboardButton("В главное меню", callback_data="menu:root")],
        ]
    )
    return InlineKeyboardMarkup(rows)


def finish_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Новая сессия", callback_data="menu:start"),
                InlineKeyboardButton("Статистика", callback_data="menu:stats"),
            ],
            [InlineKeyboardButton("В меню", callback_data="menu:root")],
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
                ("start", "Запустить бота"),
                ("menu", "Открыть главное меню"),
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
        text = (
            "Бот помогает учить УК РФ по карточкам разных форматов.\n\n"
            "Можно работать в обычном режиме, решать тесты с вариантами ответа, "
            "проходить задания формата «верно / неверно» и запускать смешанные сессии."
        )
        await update.effective_chat.send_message(text=text, reply_markup=main_menu_keyboard())

    async def menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.effective_user is None or update.effective_chat is None:
            return
        self.db.upsert_user(update.effective_user)
        await update.effective_chat.send_message("Главное меню:", reply_markup=main_menu_keyboard())

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
                await query.edit_message_text("Главное меню:", reply_markup=main_menu_keyboard())
                return
            if data == "menu:start":
                await query.answer()
                await query.edit_message_text(
                    "Выберите, что хотите запустить:",
                    reply_markup=start_kind_keyboard(),
                )
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
                chapter_code = data.rsplit(":", maxsplit=1)[1]
                await self.toggle_chapter(query, chapter_code)
                return
            if data == "chapter:all":
                await query.answer("Выбраны все главы")
                chapters = [row["chapter_code"] for row in self.db.list_chapters()]
                self.db.set_selected_chapters(user.id, chapters)
                await self.show_chapters(query)
                return
            if data == "chapter:clear":
                await query.answer("Список глав очищен")
                self.db.set_selected_chapters(user.id, [])
                await self.show_chapters(query)
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
                await query.answer("Отмечено как правильный ответ")
                await self.process_binary_answer(query, is_correct=True)
                return
            if data == "answer:dont":
                await query.answer("Карточка вернется на повторение")
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
                    "Сессия завершена. Можно запустить новую или открыть статистику.",
                    reply_markup=finish_keyboard(),
                )
                return
            if data == "settings:preferred_mode":
                await query.answer()
                settings = self.db.get_user_settings(user.id)
                await query.edit_message_text(
                    "Выберите предпочитаемый режим обучения:",
                    reply_markup=preferred_mode_keyboard(
                        settings["preferred_training_mode"],
                        settings["mixed_mode_enabled"],
                    ),
                )
                return
            if data.startswith("pref:set:"):
                training_mode = data.rsplit(":", maxsplit=1)[1]
                self.db.set_preferred_training_mode(user.id, training_mode)
                await query.answer("Режим по умолчанию обновлен")
                await self.show_settings(query)
                return
            if data == "settings:mixed":
                settings = self.db.get_user_settings(user.id)
                new_state = not settings["mixed_mode_enabled"]
                self.db.set_mixed_mode_enabled(user.id, new_state)
                if not new_state and settings["preferred_training_mode"] == "mixed":
                    self.db.set_preferred_training_mode(user.id, "flashcard")
                await query.answer("Настройка смешанного режима обновлена")
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
                    "Сколько карточек показывать за одну сессию?",
                    reply_markup=session_size_keyboard(settings["session_size"]),
                )
                return
            if data.startswith("size:set:"):
                await query.answer("Размер сессии обновлен")
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
                    "Сбросить весь прогресс по карточкам, истории ответов и текущей сессии?",
                    reply_markup=reset_keyboard(),
                )
                return
            if data == "reset:confirm":
                self.db.reset_progress(user.id)
                await query.answer("Прогресс сброшен")
                await query.edit_message_text(
                    "Прогресс обнулен. Выбранные главы и остальные настройки сохранены.",
                    reply_markup=InlineKeyboardMarkup(
                        [[InlineKeyboardButton("В настройки", callback_data="menu:settings")]]
                    ),
                )
                return

            await query.answer("Неизвестное действие", show_alert=True)
        except Exception as exc:
            LOGGER.exception("Ошибка обработки callback %s", data, exc_info=exc)
            await query.answer("Произошла ошибка. Попробуйте еще раз.", show_alert=True)

    async def show_training_modes(self, query, session_mode: str) -> None:
        settings = self.db.get_user_settings(query.from_user.id)
        title = "обучения" if session_mode == "study" else "ревизии"
        await query.edit_message_text(
            f"Выберите формат {title}:",
            reply_markup=training_mode_keyboard(session_mode, settings),
        )

    async def show_chapters(self, query) -> None:
        user_id = query.from_user.id
        settings = self.db.get_user_settings(user_id)
        chapters = [dict(row) for row in self.db.list_chapters()]
        selected = settings["selected_chapters"]
        subtitle = "Если главы не выбраны, бот использует все доступные карточки."
        await query.edit_message_text(
            f"Выберите одну или несколько глав.\n\n{subtitle}",
            reply_markup=chapter_keyboard(chapters, selected),
        )

    async def toggle_chapter(self, query, chapter_code: str) -> None:
        user_id = query.from_user.id
        settings = self.db.get_user_settings(user_id)
        selected = set(settings["selected_chapters"])
        if chapter_code in selected:
            selected.remove(chapter_code)
        else:
            selected.add(chapter_code)
        self.db.set_selected_chapters(user_id, list(selected))
        await self.show_chapters(query)

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
            "Настройки обучения:\n\n"
            f"Режим по умолчанию: {preferred_label}\n"
            f"Смешанный режим: {'включен' if settings['mixed_mode_enabled'] else 'выключен'}\n"
            f"Варианты ответа по умолчанию: {'включены' if settings['options_enabled'] else 'выключены'}\n"
            f"Карточек за сессию: {settings['session_size']}\n"
            f"Подсказки: {'включены' if settings['hints_enabled'] else 'выключены'}\n"
            f"Напоминания: {'включены' if settings['reminder_enabled'] else 'выключены'}\n"
            f"Цель в день: {settings['daily_target']}\n"
            f"Время напоминания: {settings['reminder_time']}\n"
            f"Выбранные главы: {selected_text}"
        )
        await query.edit_message_text(text, reply_markup=settings_keyboard(settings))

    async def show_stats(self, query) -> None:
        user_id = query.from_user.id
        stats = self.db.get_stats(user_id)
        selected_text = ", ".join(stats["selected_chapters"]) if stats["selected_chapters"] else "все"
        chapter_lines = []
        for item in stats["chapters"]:
            chapter_lines.append(
                f"- Глава {item['chapter_code']}: {item['mastered_cards']}/{item['total_cards']} выучено"
            )
        if not chapter_lines:
            chapter_lines.append("- Нет данных по выбранным главам")

        text = (
            "Моя статистика:\n\n"
            f"Выбранные главы: {selected_text}\n"
            f"Карточек всего: {stats['total_cards']}\n"
            f"Выучено: {stats['mastered']}\n"
            f"В процессе: {stats['learning']}\n"
            f"Новых: {stats['new_cards']}\n"
            f"Правильных ответов: {stats['correct_answers']}\n"
            f"Ошибок: {stats['incorrect_answers']}\n"
            f"Баллы: {stats['points']}\n"
            f"Текущая серия: {stats['streak']}\n"
            f"Лучшая серия: {stats['best_streak']}\n"
            f"Сегодня выполнено: {stats['today_correct']}/{stats['daily_target']}\n"
            f"Режим по умолчанию: {TRAINING_MODE_LABELS.get(stats['preferred_training_mode'], TRAINING_MODE_LABELS['mixed'])}\n"
            f"Смешанный режим: {'вкл' if stats['mixed_mode_enabled'] else 'выкл'}\n"
            f"Варианты ответа: {'вкл' if stats['options_enabled'] else 'выкл'}\n\n"
            "Прогресс по главам:\n"
            + "\n".join(chapter_lines)
        )
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("В меню", callback_data="menu:root")]]
            ),
        )

    async def start_session(self, query, session_mode: str, training_mode: str) -> None:
        user_id = query.from_user.id
        session = self.db.create_session(user_id, session_mode, training_mode)
        if session is None:
            await query.edit_message_text(
                self.empty_session_message(session_mode, training_mode),
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton("Выбрать главы", callback_data="menu:chapters"),
                            InlineKeyboardButton("Другой формат", callback_data=f"sessionkind:{session_mode}"),
                        ],
                        [InlineKeyboardButton("В меню", callback_data="menu:root")],
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
                        [[InlineKeyboardButton("В меню", callback_data="menu:root")]]
                    ),
                )
                return
        await self.show_current_card(query, session)

    async def show_current_card(self, query, session: dict[str, Any]) -> None:
        payload = session["current_payload"]
        if payload is None:
            await query.edit_message_text(
                "В сессии не осталось карточек.",
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
        text, keyboard = self.render_card(card, payload, session["mode"], settings)
        await query.edit_message_text(text, reply_markup=keyboard)

    def render_card(
        self,
        card,
        payload: dict[str, Any],
        session_mode: str,
        settings: dict[str, Any],
    ) -> tuple[str, InlineKeyboardMarkup]:
        presentation = payload["presentation_type"]
        header = (
            f"Режим: {SESSION_MODE_LABELS.get(session_mode, 'Обучение')}\n"
            f"Формат: {PRESENTATION_LABELS.get(presentation, 'Карточка')}\n"
            f"Глава {card['chapter_code']}. {card['chapter_title']}\n"
            f"Статья: {card['article']}"
        )

        if presentation in {"multiple_choice", "scenario_choice"}:
            options_lines = [
                f"{index + 1}. {option}" for index, option in enumerate(payload.get("options", []))
            ]
            prompt_label = "Ситуация" if presentation == "scenario_choice" else "Вопрос"
            text = (
                f"{header}\n\n"
                f"{prompt_label}:\n{card['question']}\n\n"
                "Варианты ответа:\n"
                + "\n".join(options_lines)
            )
            return text, self.choice_keyboard(payload.get("options", []), settings["hints_enabled"], bool(card["hint"]))

        if presentation == "true_false":
            text = (
                f"{header}\n\n"
                f"Утверждение:\n{card['question']}\n\n"
                "Выберите, верно это утверждение или нет."
            )
            return text, self.true_false_keyboard(settings["hints_enabled"], bool(card["hint"]))

        prompt_label = "Ситуация" if presentation == "scenario" else "Вопрос"
        text = f"{header}\n\n{prompt_label}:\n{card['question']}"
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
            rows.append([InlineKeyboardButton("Показать ответ", callback_data="card:reveal")])
        if hints_enabled and has_hint:
            rows.append([InlineKeyboardButton("Подсказка", callback_data="card:hint")])
        rows.append(
            [
                InlineKeyboardButton("Знаю", callback_data="answer:know"),
                InlineKeyboardButton("Не знаю", callback_data="answer:dont"),
            ]
        )
        rows.append([InlineKeyboardButton("Пропустить", callback_data="card:skip")])
        rows.append([InlineKeyboardButton("В меню", callback_data="menu:root")])
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
            rows.append([InlineKeyboardButton("Подсказка", callback_data="card:hint")])
        rows.append([InlineKeyboardButton("Пропустить", callback_data="card:skip")])
        rows.append([InlineKeyboardButton("В меню", callback_data="menu:root")])
        return InlineKeyboardMarkup(rows)

    def true_false_keyboard(self, hints_enabled: bool, has_hint: bool) -> InlineKeyboardMarkup:
        rows = [
            [
                InlineKeyboardButton("Верно", callback_data="answer:option:0"),
                InlineKeyboardButton("Неверно", callback_data="answer:option:1"),
            ]
        ]
        if hints_enabled and has_hint:
            rows.append([InlineKeyboardButton("Подсказка", callback_data="card:hint")])
        rows.append([InlineKeyboardButton("Пропустить", callback_data="card:skip")])
        rows.append([InlineKeyboardButton("В меню", callback_data="menu:root")])
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
                    [[InlineKeyboardButton("В меню", callback_data="menu:root")]]
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
                    [[InlineKeyboardButton("В меню", callback_data="menu:root")]]
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
                    [[InlineKeyboardButton("В меню", callback_data="menu:root")]]
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
        )

        title = "Верно" if is_correct else "Нужно повторить"
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
                "Следующая карточка" if has_next else "Завершить сессию",
                callback_data="card:next" if has_next else "card:finish",
            )
        ]
        return InlineKeyboardMarkup([first_row, [InlineKeyboardButton("В меню", callback_data="menu:root")]])

    def compose_feedback_text(
        self,
        card,
        payload: dict[str, Any],
        result: dict[str, Any],
        *,
        selected_option: int | None,
        is_correct: bool,
    ) -> str:
        status_text = {
            "new": "новая",
            "learning": "в процессе",
            "mastered": "выучена",
        }[result["status"]]
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

        points_text = f"Очки: +{result['awarded_points']}"
        if result["bonus"]:
            points_text += f" (включая бонус +{result['bonus']})"

        return (
            f"{choice_block}"
            f"{answer_block}\n\n"
            f"Статус карточки: {status_text}\n"
            f"Верных подряд по карточке: {result['card_streak']}/{self.settings.mastered_streak}\n"
            f"{points_text}\n"
            f"Серия пользователя: {result['user_streak']}"
        )

    def compose_answer_block(self, card) -> str:
        explanation = card["explanation"] or card["answer"]
        example = f"\nПример: {card['example']}" if card["example"] else ""
        return (
            f"Правильный ответ:\n{card['answer']}\n\n"
            f"Пояснение:\n{explanation}{example}"
        )

    async def move_to_next_card(self, query) -> None:
        user_id = query.from_user.id
        session = self.db.pop_next_card(user_id)
        if session is None:
            self.db.clear_session(user_id)
            await query.edit_message_text(
                "Сессия завершена. Все карточки из текущей колоды обработаны.",
                reply_markup=finish_keyboard(),
            )
            return
        await self.show_current_card(query, session)

    def empty_session_message(self, session_mode: str, training_mode: str) -> str:
        if session_mode == "review":
            return (
                "Для ревизии пока нет карточек.\n\n"
                "Сначала пройдите обучение, чтобы появились карточки для повторения."
            )
        return (
            f"Не нашлось карточек для режима «{TRAINING_MODE_LABELS.get(training_mode, training_mode)}».\n\n"
            "Проверьте выбранные главы или попробуйте другой формат обучения."
        )

    def render_reminder_text(self, settings: dict[str, Any]) -> str:
        status = "включены" if settings["reminder_enabled"] else "выключены"
        return (
            "Напоминания:\n\n"
            f"Статус: {status}\n"
            f"Цель в день: {settings['daily_target']} карточек\n"
            f"Время: {settings['reminder_time']}\n\n"
            "Когда напоминания включены, бот раз в день присылает сообщение о дневной цели."
        )

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
