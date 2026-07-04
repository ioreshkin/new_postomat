import telebot
from telebot import types
import threading
import os
import json
import random
import time
import requests
from datetime import datetime, timedelta

try:
    import vk_api
    from vk_api.bot_longpoll import VkBotEventType, VkBotLongPoll
    from vk_api.keyboard import VkKeyboard, VkKeyboardColor
except ImportError:
    vk_api = None
    VkBotEventType = None
    VkBotLongPoll = None
    VkKeyboard = None
    VkKeyboardColor = None

class TelegramVKPostManagerBot:
    CONFIG_DIR = "vk_post_configs"

    def __init__(self, token):
        self.bot = telebot.TeleBot(token)
        self.user_sessions = {}

        # Создаем директории если их нет
        os.makedirs(self.CONFIG_DIR, exist_ok=True)

        self.setup_handlers()

    def get_user_session(self, user_id):
        if user_id not in self.user_sessions:
            self.user_sessions[user_id] = {
                'account_threads': {},
                'account_status': {},
                'temp_data': {},
                'state': None
            }
        return self.user_sessions[user_id]

    def get_user_configs_dir(self, user_id):
        user_dir = os.path.join(self.CONFIG_DIR, str(user_id))
        os.makedirs(user_dir, exist_ok=True)
        return user_dir

    def setup_handlers(self):
        @self.bot.message_handler(commands=['start'])
        def start(message):
            self.show_main_menu(message.chat.id)

        @self.bot.message_handler(commands=['id'])
        def show_id(message):
            self.bot.send_message(message.chat.id, f"Ваш Telegram ID: {message.from_user.id}")

        @self.bot.message_handler(func=lambda message: message.text == "🏠 Главное меню")
        def main_menu(message):
            self.show_main_menu(message.chat.id)

        @self.bot.message_handler(func=lambda message: message.text == "🚀 Запущенные конфигурации")
        def running_configs(message):
            self.show_running_configs(message.chat.id, message.from_user.id)

        @self.bot.message_handler(func=lambda message: message.text == "🆕 Запустить конфигурацию")
        def start_config(message):
            self.show_available_configs(message.chat.id, message.from_user.id, action="start")

        @self.bot.message_handler(func=lambda message: message.text == "🛑 Остановить все")
        def stop_all(message):
            self.stop_all_configs(message.chat.id, message.from_user.id)

        @self.bot.message_handler(func=lambda message: message.text == "📋 Все конфигурации")
        def all_configs(message):
            self.show_all_configs_menu(message.chat.id, message.from_user.id)

        @self.bot.callback_query_handler(func=lambda call: True)
        def callback_query(call):
            user_id = call.from_user.id
            chat_id = call.message.chat.id
            data = call.data.split(":")

            if data[0] == "running_config":
                config_name = data[1]
                self.show_running_config_details(chat_id, user_id, config_name)

            elif data[0] == "stop_config":
                config_name = data[1]
                self.stop_config(chat_id, user_id, config_name)
                self.show_running_configs(chat_id, user_id)

            elif data[0] == "start_config":
                config_name = data[1]
                self.prepare_to_start_config(chat_id, user_id, config_name)

            elif data[0] == "select_date":
                config_name = data[1]
                selected_date = data[2]
                self.handle_date_selection(chat_id, user_id, config_name, selected_date)

            elif data[0] == "config_action":
                config_name = data[1]
                action = data[2]

                if action == "view":
                    self.show_config_details(chat_id, user_id, config_name)
                elif action == "edit_text":
                    self.edit_config_text(chat_id, user_id, config_name)
                elif action == "edit_interval":
                    self.edit_config_interval(chat_id, user_id, config_name)
                elif action == "delete":
                    self.delete_config(chat_id, user_id, config_name)

            elif data[0] == "add_config":
                self.add_new_config(chat_id, user_id)

            elif data[0] == "back_to_running":
                self.show_running_configs(chat_id, user_id)

            elif data[0] == "back_to_all_configs":
                self.show_all_configs_menu(chat_id, user_id)

            elif data[0] == "back_to_main":
                self.show_main_menu(chat_id)

            self.bot.answer_callback_query(call.id)

    def show_main_menu(self, chat_id):
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        btn1 = types.KeyboardButton("🚀 Запущенные конфигурации")
        btn2 = types.KeyboardButton("🆕 Запустить конфигурацию")
        btn3 = types.KeyboardButton("🛑 Остановить все")
        btn4 = types.KeyboardButton("📋 Все конфигурации")
        markup.add(btn1, btn2, btn3, btn4)
        self.bot.send_message(chat_id, "Главное меню:", reply_markup=markup)

    def show_running_configs(self, chat_id, user_id):
        session = self.get_user_session(user_id)
        running_configs = []
        user_configs_dir = self.get_user_configs_dir(user_id)

        for key in session['account_threads']:
            token, group_id = key
            for config_file in os.listdir(user_configs_dir):
                if config_file.endswith(".json"):
                    with open(os.path.join(user_configs_dir, config_file), "r") as f:
                        config = json.load(f)
                        if config.get("ACCESS_TOKEN") == token and str(config.get("GROUP_ID")) == str(group_id):
                            running_configs.append(config_file[:-5])

        if not running_configs:
            self.bot.send_message(chat_id, "Нет запущенных конфигураций.")
            return

        markup = types.InlineKeyboardMarkup()
        for config_name in running_configs:
            markup.add(types.InlineKeyboardButton(
                text=config_name,
                callback_data=f"running_config:{config_name}"
            ))
        markup.add(types.InlineKeyboardButton(
            text="🔙 Назад",
            callback_data="back_to_main"
        ))

        self.bot.send_message(chat_id, "Выберите конфигурацию для остановки:", reply_markup=markup)

    def show_running_config_details(self, chat_id, user_id, config_name):
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton(
            text="🛑 Остановить",
            callback_data=f"stop_config:{config_name}"
        ))
        markup.add(types.InlineKeyboardButton(
            text="🔙 Назад",
            callback_data="back_to_running"
        ))

        self.bot.send_message(chat_id, f"Конфигурация: {config_name}\nВыберите действие:", reply_markup=markup)

    def stop_config(self, chat_id, user_id, config_name):
        session = self.get_user_session(user_id)
        user_configs_dir = self.get_user_configs_dir(user_id)
        config_path = os.path.join(user_configs_dir, f"{config_name}.json")

        if not os.path.exists(config_path):
            self.bot.send_message(chat_id, "Конфигурация не найдена.")
            return

        with open(config_path, "r") as f:
            config = json.load(f)

        key = (config["ACCESS_TOKEN"], str(config["GROUP_ID"]))

        if key in session['account_threads']:
            session['account_status'][key] = False
            del session['account_threads'][key]
            del session['account_status'][key]
            self.bot.send_message(chat_id, f"Конфигурация {config_name} остановлена.")
        else:
            self.bot.send_message(chat_id, "Эта конфигурация не была запущена.")

    def stop_all_configs(self, chat_id, user_id):
        session = self.get_user_session(user_id)

        if not session['account_threads']:
            self.bot.send_message(chat_id, "Нет запущенных конфигураций.")
            return

        for key in list(session['account_threads'].keys()):
            session['account_status'][key] = False
            del session['account_threads'][key]
            del session['account_status'][key]

        self.bot.send_message(chat_id, "Все конфигурации остановлены.")

    def show_available_configs(self, chat_id, user_id, action="start"):
        user_configs_dir = self.get_user_configs_dir(user_id)
        all_configs = [f[:-5] for f in os.listdir(user_configs_dir) if f.endswith(".json")]

        if not all_configs:
            self.bot.send_message(chat_id,
                                  "Нет доступных конфигураций. Сначала создайте конфигурацию в разделе 'Все конфигурации'.")
            return

        session = self.get_user_session(user_id)
        running_keys = set(session['account_threads'].keys())
        running_configs = []

        for config_file in os.listdir(user_configs_dir):
            if config_file.endswith(".json"):
                with open(os.path.join(user_configs_dir, config_file), "r") as f:
                    config = json.load(f)
                    key = (config["ACCESS_TOKEN"], str(config["GROUP_ID"]))
                    if key in running_keys:
                        running_configs.append(config_file[:-5])

        available_configs = [c for c in all_configs if c not in running_configs]

        if not available_configs:
            self.bot.send_message(chat_id, "Все конфигурации уже запущены.")
            return

        markup = types.InlineKeyboardMarkup()
        for config_name in available_configs:
            markup.add(types.InlineKeyboardButton(
                text=config_name,
                callback_data=f"start_config:{config_name}"
            ))
        markup.add(types.InlineKeyboardButton(
            text="🔙 Назад",
            callback_data="back_to_main"
        ))

        self.bot.send_message(chat_id, "Выберите конфигурацию для запуска:", reply_markup=markup)

    def prepare_to_start_config(self, chat_id, user_id, config_name):
        session = self.get_user_session(user_id)
        session['temp_data'] = {"config_name": config_name}
        session['state'] = "preparing_to_start"

        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton(
            text="Сегодня",
            callback_data=f"select_date:{config_name}:today"
        ))
        markup.add(types.InlineKeyboardButton(
            text="Завтра",
            callback_data=f"select_date:{config_name}:tomorrow"
        ))
        markup.add(types.InlineKeyboardButton(
            text="🔙 Назад",
            callback_data="back_to_main"
        ))

        self.bot.send_message(chat_id, "Выберите дату публикации:", reply_markup=markup)

    def handle_date_selection(self, chat_id, user_id, config_name, selected_date):
        session = self.get_user_session(user_id)

        if selected_date == "today":
            post_date = datetime.now()
        else:
            post_date = datetime.now() + timedelta(days=1)

        session['temp_data']["post_date"] = post_date
        session['state'] = "waiting_time"

        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton(
            text="🔙 Назад",
            callback_data=f"start_config:{config_name}"
        ))

        self.bot.send_message(chat_id, "Введите время публикации (любой формат, например 13:30 или 14:00-15:30):",
                              reply_markup=markup)

    def process_time_input(self, message):
        user_id = message.from_user.id
        chat_id = message.chat.id
        session = self.get_user_session(user_id)

        if session['state'] != "waiting_time":
            return

        try:
            time_str = message.text
            config_name = session['temp_data']["config_name"]
            user_configs_dir = self.get_user_configs_dir(user_id)
            config_path = os.path.join(user_configs_dir, f"{config_name}.json")

            if not os.path.exists(config_path):
                self.bot.send_message(chat_id, "Конфигурация не найдена.")
                return

            with open(config_path, "r") as f:
                config = json.load(f)

            # Заменяем метки в тексте (включая время)
            post_text = config["POST_TEXT"]
            post_text = self.replace_placeholders(post_text, session['temp_data']["post_date"], time_str)

            # Запускаем конфигурацию
            key = (config["ACCESS_TOKEN"], str(config["GROUP_ID"]))
            interval = int(config["INTERVAL"])

            session['account_status'][key] = True
            thread = threading.Thread(
                target=self.post_to_vk,
                args=(user_id, key, post_text, interval),
                daemon=True
            )
            session['account_threads'][key] = thread
            thread.start()

            self.bot.send_message(chat_id, f"Конфигурация {config_name} запущена! Время: {time_str}")
            session['state'] = None
            session['temp_data'] = {}
            self.show_main_menu(message.chat.id)

        except Exception as e:
            self.bot.send_message(chat_id, f"Произошла ошибка: {str(e)}")

    def remove_existing_posts(self, token, group_id):
        try:
            # Получаем ID текущего пользователя
            user_info = requests.post(
                "https://api.vk.ru/method/users.get",
                params={
                    "access_token": token,
                    "v": "5.131"
                }
            ).json()

            current_user_id = user_info["response"][0]["id"]
            # Получаем последние 100 постов
            response = requests.post(
                "https://api.vk.ru/method/wall.get",
                params={
                    "access_token": token,
                    "owner_id": f"-{group_id}",
                    "count": 100,
                    "v": "5.131",
                }
            ).json()

            posts = response.get("response", {}).get("items", [])
            flag = False

            # Удаляем только свои посты
            for post in posts:
                if post.get("from_id") == current_user_id:
                    flag = True

                    requests.post(
                        "https://api.vk.ru/method/wall.delete",
                        params={
                            "access_token": token,
                            "owner_id": f"-{group_id}",
                            "post_id": post["id"],
                            "v": "5.131",
                        }
                    )
            return flag

        except Exception as e:
            print(f"Ошибка при удалении постов: {str(e)}")

    def replace_placeholders(self, text, post_date, time_str):
        weekdays = [
            "в понедельник", "во вторник", "в среду",
            "в четверг", "в пятницу", "в субботу", "в воскресенье"
        ]

        replacements = {
            "<time>": time_str,
            "<day>": post_date.strftime("%d.%m"),
            "<weekday>": weekdays[post_date.weekday()]
        }

        for placeholder, value in replacements.items():
            text = text.replace(placeholder, value)

        return text

    def show_all_configs_menu(self, chat_id, user_id):
        user_configs_dir = self.get_user_configs_dir(user_id)
        configs = [f[:-5] for f in os.listdir(user_configs_dir) if f.endswith(".json")]

        markup = types.InlineKeyboardMarkup()

        if configs:
            for config_name in configs:
                markup.add(types.InlineKeyboardButton(
                    text=config_name,
                    callback_data=f"config_action:{config_name}:view"
                ))

        markup.add(types.InlineKeyboardButton(
            text="➕ Добавить конфигурацию",
            callback_data="add_config"
        ))
        markup.add(types.InlineKeyboardButton(
            text="🔙 Назад",
            callback_data="back_to_main"
        ))

        self.bot.send_message(chat_id, "Все конфигурации:", reply_markup=markup)

    def show_config_details(self, chat_id, user_id, config_name):
        user_configs_dir = self.get_user_configs_dir(user_id)
        config_path = os.path.join(user_configs_dir, f"{config_name}.json")

        if not os.path.exists(config_path):
            self.bot.send_message(chat_id, "Конфигурация не найдена.")
            return

        with open(config_path, "r") as f:
            config = json.load(f)

        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton(
            text="✏️ Редактировать текст",
            callback_data=f"config_action:{config_name}:edit_text"
        ))
        markup.add(types.InlineKeyboardButton(
            text="⌚ Изменить интервал",
            callback_data=f"config_action:{config_name}:edit_interval"
        ))
        markup.add(types.InlineKeyboardButton(
            text="🗑️ Удалить",
            callback_data=f"config_action:{config_name}:delete"
        ))
        markup.add(types.InlineKeyboardButton(
            text="🔙 Назад",
            callback_data="back_to_all_configs"
        ))

        response = (
            f"Конфигурация: {config_name}\n"
            f"Токен: {config.get('ACCESS_TOKEN', '')}\n"
            f"ID группы: {config.get('GROUP_ID', '')}\n"
            f"Текст поста:\n{config.get('POST_TEXT', '')}"
            f"\nИнтервал публикации: {config.get('INTERVAL', '')}"
        )

        self.bot.send_message(chat_id, response, reply_markup=markup)

    def edit_config_text(self, chat_id, user_id, config_name):
        user_configs_dir = self.get_user_configs_dir(user_id)
        config_path = os.path.join(user_configs_dir, f"{config_name}.json")

        if not os.path.exists(config_path):
            self.bot.send_message(chat_id, "Конфигурация не найдена.")
            return

        session = self.get_user_session(user_id)
        session['state'] = f"editing_text:{config_name}"

        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton(
            text="🔙 Назад",
            callback_data=f"config_action:{config_name}:view"
        ))

        self.bot.send_message(chat_id, "Введите новый текст поста (можно использовать метки <time>, <day>, <weekday>):",
                              reply_markup=markup)

    def edit_config_interval(self, chat_id, user_id, config_name):
        user_configs_dir = self.get_user_configs_dir(user_id)
        config_path = os.path.join(user_configs_dir, f"{config_name}.json")

        if not os.path.exists(config_path):
            self.bot.send_message(chat_id, "Конфигурация не найдена.")
            return

        session = self.get_user_session(user_id)
        session['state'] = f"editing_interval:{config_name}"

        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton(
            text="🔙 Назад",
            callback_data=f"config_action:{config_name}:view"
        ))

        self.bot.send_message(chat_id,
                              "Введите интервал публикации (в минутах):",
                              reply_markup=markup)

    def process_text_edit(self, message):
        user_id = message.from_user.id
        chat_id = message.chat.id
        session = self.get_user_session(user_id)

        if not session['state'] or not session['state'].startswith("editing_text:"):
            return

        config_name = session['state'].split(":")[1]
        user_configs_dir = self.get_user_configs_dir(user_id)
        config_path = os.path.join(user_configs_dir, f"{config_name}.json")

        if not os.path.exists(config_path):
            self.bot.send_message(chat_id, "Конфигурация не найдена.")
            return

        with open(config_path, "r") as f:
            config = json.load(f)

        config["POST_TEXT"] = message.text

        with open(config_path, "w") as f:
            json.dump(config, f)

        self.bot.send_message(chat_id, "Текст поста обновлен!")
        session['state'] = None
        self.show_config_details(chat_id, user_id, config_name)

    def process_interval_edit(self, message):
        user_id = message.from_user.id
        chat_id = message.chat.id
        session = self.get_user_session(user_id)

        if not session['state'] or not session['state'].startswith("editing_interval:"):
            return

        config_name = session['state'].split(":")[1]
        user_configs_dir = self.get_user_configs_dir(user_id)
        config_path = os.path.join(user_configs_dir, f"{config_name}.json")

        if not os.path.exists(config_path):
            self.bot.send_message(chat_id, "Конфигурация не найдена.")
            return

        with open(config_path, "r") as f:
            config = json.load(f)

        config["INTERVAL"] = message.text

        with open(config_path, "w") as f:
            json.dump(config, f)

        self.bot.send_message(chat_id, "Интервал публикации обновлен!")
        session['state'] = None
        self.show_config_details(chat_id, user_id, config_name)

    def delete_config(self, chat_id, user_id, config_name):
        session = self.get_user_session(user_id)
        user_configs_dir = self.get_user_configs_dir(user_id)
        config_path = os.path.join(user_configs_dir, f"{config_name}.json")

        if not os.path.exists(config_path):
            self.bot.send_message(chat_id, "Конфигурация не найдена.")
            return

        # Проверяем, не запущена ли конфигурация
        with open(config_path, "r") as f:
            config = json.load(f)

        key = (config["ACCESS_TOKEN"], str(config["GROUP_ID"]))

        if key in session['account_threads']:
            self.bot.send_message(chat_id, "Сначала остановите эту конфигурацию!")
            return

        os.remove(config_path)
        self.bot.send_message(chat_id, f"Конфигурация {config_name} удалена.")
        self.show_all_configs_menu(chat_id, user_id)

    def add_new_config(self, chat_id, user_id):
        session = self.get_user_session(user_id)
        session['state'] = "adding_config:name"
        session['temp_data'] = {}

        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton(
            text="🔙 Назад",
            callback_data="back_to_all_configs"
        ))

        self.bot.send_message(chat_id, "Введите название новой конфигурации:", reply_markup=markup)

    def process_config_creation(self, message):
        user_id = message.from_user.id
        chat_id = message.chat.id
        session = self.get_user_session(user_id)

        if not session['state'] or not session['state'].startswith("adding_config:"):
            return

        current_step = session['state'].split(":")[1]

        if current_step == "name":
            config_name = message.text
            user_configs_dir = self.get_user_configs_dir(user_id)

            if f"{config_name}.json" in os.listdir(user_configs_dir):
                self.bot.send_message(chat_id, "Конфигурация с таким именем уже существует. Введите другое название:")
                return

            session['temp_data']['name'] = config_name
            session['state'] = "adding_config:token"

            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton(
                text="🔙 Назад",
                callback_data="add_config"
            ))

            self.bot.send_message(chat_id, "Введите токен VK:", reply_markup=markup)

        elif current_step == "token":
            session['temp_data']['token'] = message.text
            session['state'] = "adding_config:group_id"

            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton(
                text="🔙 Назад",
                callback_data="add_config"
            ))

            self.bot.send_message(chat_id, "Введите ID группы:", reply_markup=markup)

        elif current_step == "group_id":
            try:
                group_id = int(message.text)
                session['temp_data']['group_id'] = group_id
                session['state'] = "adding_config:text"

                markup = types.InlineKeyboardMarkup()
                markup.add(types.InlineKeyboardButton(
                    text="🔙 Назад",
                    callback_data="add_config"
                ))

                self.bot.send_message(chat_id,
                                      "Введите текст поста (можно использовать метки <time>, <day>, <weekday>):",
                                      reply_markup=markup)
            except ValueError:
                self.bot.send_message(chat_id, "ID группы должен быть числом. Введите корректный ID:")

        elif current_step == "text":
            session['temp_data']['text'] = message.text
            session['state'] = "adding_config:interval"

            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton(
                text="🔙 Назад",
                callback_data="add_config"
            ))

            self.bot.send_message(chat_id, "Введите интервал публикации (в минутах):", reply_markup=markup)

        elif current_step == "interval":
            try:
                interval = int(message.text)
                if interval <= 0:
                    raise ValueError

                config_data = {
                    "ACCESS_TOKEN": session['temp_data']['token'],
                    "GROUP_ID": session['temp_data']['group_id'],
                    "POST_TEXT": session['temp_data']['text'],
                    "INTERVAL": interval
                }

                user_configs_dir = self.get_user_configs_dir(user_id)
                config_path = os.path.join(user_configs_dir, f"{session['temp_data']['name']}.json")
                with open(config_path, "w") as f:
                    json.dump(config_data, f)

                self.bot.send_message(chat_id, f"Конфигурация {session['temp_data']['name']} успешно создана!")
                session['state'] = None
                session['temp_data'] = {}

                self.show_all_configs_menu(chat_id, user_id)

            except ValueError:
                self.bot.send_message(chat_id,
                                      "Интервал должен быть положительным числом. Введите корректное значение:")

    def post_to_vk(self, user_id, key, message, interval):
        token, group_id = key
        session = self.get_user_session(user_id)
        status = session['account_status'].get(key, False)
        if (status): self.remove_existing_posts(token, group_id)

        while status:
            try:
                # Публикуем новый пост
                post_url = "https://api.vk.ru/method/wall.post"
                post_params = {
                    "access_token": token,
                    "owner_id": f"-{group_id}",
                    "message": message,
                    "v": "5.131",
                }
                response = requests.post(post_url, params=post_params).json()

                if "error" in response:
                    print(f"Ошибка публикации: {response['error']['error_msg']}")
                    break

                print(f"Пост опубликован: {response['response']['post_id']}")
                status = session['account_status'].get(key, False)

                time.sleep(interval * 60)

                if self.remove_existing_posts(token, group_id) == False:
                    session['account_status'][key] = False
                    del session['account_threads'][key]
                    del session['account_status'][key]
                    break

            except Exception as e:
                print(f"Произошла ошибка: {str(e)}")
                break

    def run(self):
        @self.bot.message_handler(func=lambda message: True)
        def handle_all_messages(message):
            user_id = message.from_user.id
            chat_id = message.chat.id
            session = self.get_user_session(user_id)

            if session['state']:
                if session['state'] == "waiting_time":
                    self.process_time_input(message)
                elif session['state'].startswith("editing_text:"):
                    self.process_text_edit(message)
                elif session['state'].startswith("editing_interval:"):
                    self.process_interval_edit(message)
                elif session['state'].startswith("adding_config:"):
                    self.process_config_creation(message)
                else:
                    self.show_main_menu(chat_id)
            else:
                self.show_main_menu(chat_id)

        # безопасный запуск polling
        while True:
            try:
                self.bot.infinity_polling(
                    none_stop=True,
                    timeout=60,  # время ожидания ответа Telegram
                    long_polling_timeout=60  # время ожидания апдейта
                )
            except requests.exceptions.ReadTimeout:
                print("⚠️ ReadTimeout — пробую переподключиться...")
                time.sleep(5)
            except requests.exceptions.ConnectionError:
                print("⚠️ ConnectionError — нет соединения, жду...")
                time.sleep(5)
            except Exception as e:
                print(f"❌ Неожиданная ошибка: {e}")
                time.sleep(5)


class VKPostManagerBot:
    LINKS_FILE = "vk_user_links.json"
    PAGE_SIZE = 4

    MAIN_TEXT_ACTIONS = {
        "🚀 Запущенные конфигурации": "running_configs",
        "🆕 Запустить конфигурацию": "start_config_menu",
        "🛑 Остановить все": "stop_all",
        "📋 Все конфигурации": "all_configs",
        "🏠 Главное меню": "back_to_main",
    }

    def __init__(self, manager, token, group_id):
        if vk_api is None:
            raise RuntimeError("Установите зависимость vk_api: pip install vk_api")

        self.manager = manager
        self.group_id = int(group_id)
        self.vk_session = vk_api.VkApi(token=token)
        self.vk = self.vk_session.get_api()
        self.longpoll = VkBotLongPoll(self.vk_session, self.group_id)
        self.user_links = self.load_user_links()
        self.vk_states = {}

    def load_user_links(self):
        if not os.path.exists(self.LINKS_FILE):
            return {}

        try:
            with open(self.LINKS_FILE, "r") as f:
                links = json.load(f)
            return {str(vk_id): int(telegram_id) for vk_id, telegram_id in links.items()}
        except Exception as e:
            print(f"Ошибка чтения {self.LINKS_FILE}: {e}")
            return {}

    def save_user_links(self):
        with open(self.LINKS_FILE, "w") as f:
            json.dump(self.user_links, f)

    def get_linked_user_id(self, vk_user_id):
        telegram_user_id = self.user_links.get(str(vk_user_id))
        if telegram_user_id is None:
            return None
        return int(telegram_user_id)

    def link_vk_user(self, vk_user_id, telegram_user_id):
        self.user_links[str(vk_user_id)] = int(telegram_user_id)
        self.save_user_links()

    def telegram_configs_dir_exists(self, telegram_user_id):
        user_dir = os.path.join(self.manager.CONFIG_DIR, str(telegram_user_id))
        return os.path.isdir(user_dir)

    def short_label(self, text):
        return text if len(text) <= 40 else f"{text[:37]}..."

    def build_keyboard(self, buttons, inline=True):
        keyboard = VkKeyboard(one_time=False, inline=inline and len(buttons) <= 6)
        buttons_per_line = 1 if inline and len(buttons) <= 6 else 2

        for index, button in enumerate(buttons):
            payload = {"action": button["action"]}
            for key, value in button.items():
                if key not in ("label", "action", "color"):
                    payload[key] = value

            keyboard.add_button(
                self.short_label(button["label"]),
                color=button.get("color", VkKeyboardColor.SECONDARY),
                payload=payload,
            )

            if index != len(buttons) - 1 and (index + 1) % buttons_per_line == 0:
                keyboard.add_line()

        return keyboard

    def main_keyboard(self):
        return self.build_keyboard([
            {"label": "🚀 Запущенные конфигурации", "action": "running_configs", "color": VkKeyboardColor.PRIMARY},
            {"label": "🆕 Запустить конфигурацию", "action": "start_config_menu", "color": VkKeyboardColor.POSITIVE},
            {"label": "🛑 Остановить все", "action": "stop_all", "color": VkKeyboardColor.NEGATIVE},
            {"label": "📋 Все конфигурации", "action": "all_configs", "color": VkKeyboardColor.PRIMARY},
        ], inline=False)

    def send_message(self, vk_user_id, text, keyboard=None):
        params = {
            "peer_id": vk_user_id,
            "message": text,
            "random_id": random.randint(1, 2_147_483_647),
        }

        if keyboard is not None:
            params["keyboard"] = keyboard.get_keyboard()

        self.vk.messages.send(**params)

    def extract_event_message(self, event):
        event_object = getattr(event, "obj", None) or getattr(event, "object", None)
        if event_object is None:
            return None

        if hasattr(event_object, "message"):
            return event_object.message

        if isinstance(event_object, dict):
            return event_object.get("message", event_object)

        return None

    def get_message_value(self, message, key, default=None):
        if hasattr(message, "get"):
            return message.get(key, default)
        return getattr(message, key, default)

    def parse_payload(self, raw_payload):
        if not raw_payload:
            return {}

        if isinstance(raw_payload, dict):
            return raw_payload

        try:
            return json.loads(raw_payload)
        except Exception:
            return {}

    def ask_telegram_id(self, vk_user_id):
        self.vk_states[str(vk_user_id)] = "waiting_telegram_id"
        self.send_message(
            vk_user_id,
            "Введите ваш Telegram ID, чтобы перенести конфигурации. "
            "В Telegram-боте можно написать /id, он покажет нужный ID.",
        )

    def process_telegram_id(self, vk_user_id, text):
        try:
            telegram_user_id = int(text.strip())
        except ValueError:
            self.send_message(vk_user_id, "Telegram ID должен быть числом. Введите корректный ID:")
            return

        if not self.telegram_configs_dir_exists(telegram_user_id):
            self.send_message(
                vk_user_id,
                "Конфиги для этого Telegram ID не найдены. Проверьте ID или сначала откройте конфиги в Telegram-боте.",
            )
            return

        self.link_vk_user(vk_user_id, telegram_user_id)
        self.vk_states.pop(str(vk_user_id), None)
        self.send_message(vk_user_id, "Готово, конфигурации привязаны к VK.")
        self.show_main_menu(vk_user_id)

    def clear_user_state(self, telegram_user_id):
        session = self.manager.get_user_session(telegram_user_id)
        session['state'] = None
        session['temp_data'] = {}

    def get_payload_page(self, payload):
        try:
            return max(0, int(payload.get("page", 0)))
        except (TypeError, ValueError):
            return 0

    def get_page_items(self, items, page):
        page_count = max(1, (len(items) + self.PAGE_SIZE - 1) // self.PAGE_SIZE)
        page = min(max(0, page), page_count - 1)
        start = page * self.PAGE_SIZE
        return items[start:start + self.PAGE_SIZE], page, page_count, start

    def add_page_buttons(self, buttons, action, page, page_count, back_action="back_to_main", extra_button=None):
        if page_count <= 1:
            if extra_button is not None:
                buttons.append(extra_button)
            buttons.append({"label": "🔙 Назад", "action": back_action, "color": VkKeyboardColor.PRIMARY})
            return

        if page > 0:
            buttons.append({"label": "⬅️ Назад", "action": action, "page": page - 1, "color": VkKeyboardColor.PRIMARY})
        elif extra_button is not None:
            buttons.append(extra_button)
        else:
            buttons.append({"label": "🏠 Меню", "action": back_action, "color": VkKeyboardColor.PRIMARY})

        if page < page_count - 1:
            buttons.append({"label": "➡️ Далее", "action": action, "page": page + 1, "color": VkKeyboardColor.PRIMARY})
        elif extra_button is not None:
            buttons.append(extra_button)
        else:
            buttons.append({"label": "🏠 Меню", "action": back_action, "color": VkKeyboardColor.PRIMARY})

    def handle_event(self, event):
        message = self.extract_event_message(event)
        if message is None:
            return

        vk_user_id = self.get_message_value(message, "from_id")
        peer_id = self.get_message_value(message, "peer_id", vk_user_id)
        text = (self.get_message_value(message, "text", "") or "").strip()
        payload = self.parse_payload(self.get_message_value(message, "payload"))

        if not vk_user_id or peer_id != vk_user_id:
            return

        self.handle_message(vk_user_id, text, payload)

    def handle_message(self, vk_user_id, text, payload):
        lowered_text = text.lower()

        if lowered_text in ("/link", "сменить telegram id"):
            self.user_links.pop(str(vk_user_id), None)
            self.save_user_links()
            self.ask_telegram_id(vk_user_id)
            return

        telegram_user_id = self.get_linked_user_id(vk_user_id)

        if telegram_user_id is None:
            if self.vk_states.get(str(vk_user_id)) == "waiting_telegram_id":
                self.process_telegram_id(vk_user_id, text)
            else:
                self.ask_telegram_id(vk_user_id)
            return

        if lowered_text in ("/start", "start", "начать"):
            self.show_main_menu(vk_user_id)
            return

        if payload.get("action"):
            self.handle_action(vk_user_id, telegram_user_id, payload)
            return

        if text in self.MAIN_TEXT_ACTIONS:
            self.handle_action(vk_user_id, telegram_user_id, {"action": self.MAIN_TEXT_ACTIONS[text]})
            return

        session = self.manager.get_user_session(telegram_user_id)
        if session['state']:
            if session['state'] == "waiting_time":
                self.process_time_input(vk_user_id, telegram_user_id, text)
            elif session['state'].startswith("editing_text:"):
                self.process_text_edit(vk_user_id, telegram_user_id, text)
            elif session['state'].startswith("editing_interval:"):
                self.process_interval_edit(vk_user_id, telegram_user_id, text)
            elif session['state'].startswith("adding_config:"):
                self.process_config_creation(vk_user_id, telegram_user_id, text)
            else:
                self.show_main_menu(vk_user_id)
        else:
            self.show_main_menu(vk_user_id)

    def handle_action(self, vk_user_id, telegram_user_id, payload):
        action = payload.get("action")

        if action == "running_configs":
            self.clear_user_state(telegram_user_id)
            self.show_running_configs(vk_user_id, telegram_user_id, self.get_payload_page(payload))
        elif action == "start_config_menu":
            self.clear_user_state(telegram_user_id)
            self.show_available_configs(vk_user_id, telegram_user_id, self.get_payload_page(payload))
        elif action == "stop_all":
            self.clear_user_state(telegram_user_id)
            self.stop_all_configs(vk_user_id, telegram_user_id)
        elif action == "all_configs":
            self.clear_user_state(telegram_user_id)
            self.show_all_configs_menu(vk_user_id, telegram_user_id, self.get_payload_page(payload))
        elif action == "running_config":
            self.show_running_config_details(vk_user_id, payload.get("config_name"), self.get_payload_page(payload))
        elif action == "stop_config":
            self.stop_config(vk_user_id, telegram_user_id, payload.get("config_name"))
            self.show_running_configs(vk_user_id, telegram_user_id, self.get_payload_page(payload))
        elif action == "start_config":
            self.prepare_to_start_config(vk_user_id, telegram_user_id, payload.get("config_name"))
        elif action == "select_date":
            self.handle_date_selection(
                vk_user_id,
                telegram_user_id,
                payload.get("config_name"),
                payload.get("selected_date"),
            )
        elif action == "config_action":
            config_name = payload.get("config_name")
            config_action = payload.get("config_action")

            if config_action == "view":
                self.clear_user_state(telegram_user_id)
                self.show_config_details(vk_user_id, telegram_user_id, config_name, self.get_payload_page(payload))
            elif config_action == "edit_text":
                self.edit_config_text(vk_user_id, telegram_user_id, config_name)
            elif config_action == "edit_interval":
                self.edit_config_interval(vk_user_id, telegram_user_id, config_name)
            elif config_action == "delete":
                self.delete_config(vk_user_id, telegram_user_id, config_name, self.get_payload_page(payload))
        elif action == "add_config":
            self.add_new_config(vk_user_id, telegram_user_id)
        elif action == "back_to_running":
            self.clear_user_state(telegram_user_id)
            self.show_running_configs(vk_user_id, telegram_user_id, self.get_payload_page(payload))
        elif action == "back_to_all_configs":
            self.clear_user_state(telegram_user_id)
            self.show_all_configs_menu(vk_user_id, telegram_user_id, self.get_payload_page(payload))
        elif action == "back_to_main":
            self.clear_user_state(telegram_user_id)
            self.show_main_menu(vk_user_id)
        else:
            self.show_main_menu(vk_user_id)

    def show_main_menu(self, vk_user_id):
        self.send_message(vk_user_id, "Главное меню:", keyboard=self.main_keyboard())

    def show_running_configs(self, vk_user_id, telegram_user_id, page=0):
        session = self.manager.get_user_session(telegram_user_id)
        running_configs = []
        user_configs_dir = self.manager.get_user_configs_dir(telegram_user_id)

        for key in session['account_threads']:
            token, group_id = key
            for config_file in os.listdir(user_configs_dir):
                if config_file.endswith(".json"):
                    with open(os.path.join(user_configs_dir, config_file), "r") as f:
                        config = json.load(f)
                        if config.get("ACCESS_TOKEN") == token and str(config.get("GROUP_ID")) == str(group_id):
                            running_configs.append(config_file[:-5])

        if not running_configs:
            self.send_message(vk_user_id, "Нет запущенных конфигураций.", keyboard=self.main_keyboard())
            return

        running_configs = sorted(running_configs)
        page_configs, page, page_count, start = self.get_page_items(running_configs, page)

        buttons = [
            {
                "label": config_name,
                "action": "running_config",
                "config_name": config_name,
                "page": page,
                "color": VkKeyboardColor.SECONDARY,
            }
            for config_name in page_configs
        ]
        self.add_page_buttons(buttons, "running_configs", page, page_count)

        self.send_message(
            vk_user_id,
            f"Выберите конфигурацию для остановки:\nСтраница {page + 1}/{page_count}. Показаны {start + 1}-{start + len(page_configs)} из {len(running_configs)}.",
            keyboard=self.build_keyboard(buttons),
        )

    def show_running_config_details(self, vk_user_id, config_name, page=0):
        buttons = [
            {"label": "🛑 Остановить", "action": "stop_config", "config_name": config_name, "page": page, "color": VkKeyboardColor.NEGATIVE},
            {"label": "🔙 Назад", "action": "back_to_running", "page": page, "color": VkKeyboardColor.PRIMARY},
        ]

        self.send_message(
            vk_user_id,
            f"Конфигурация: {config_name}\nВыберите действие:",
            keyboard=self.build_keyboard(buttons),
        )

    def stop_config(self, vk_user_id, telegram_user_id, config_name):
        session = self.manager.get_user_session(telegram_user_id)
        user_configs_dir = self.manager.get_user_configs_dir(telegram_user_id)
        config_path = os.path.join(user_configs_dir, f"{config_name}.json")

        if not os.path.exists(config_path):
            self.send_message(vk_user_id, "Конфигурация не найдена.")
            return

        with open(config_path, "r") as f:
            config = json.load(f)

        key = (config["ACCESS_TOKEN"], str(config["GROUP_ID"]))

        if key in session['account_threads']:
            session['account_status'][key] = False
            del session['account_threads'][key]
            del session['account_status'][key]
            self.send_message(vk_user_id, f"Конфигурация {config_name} остановлена.")
        else:
            self.send_message(vk_user_id, "Эта конфигурация не была запущена.")

    def stop_all_configs(self, vk_user_id, telegram_user_id):
        session = self.manager.get_user_session(telegram_user_id)

        if not session['account_threads']:
            self.send_message(vk_user_id, "Нет запущенных конфигураций.", keyboard=self.main_keyboard())
            return

        for key in list(session['account_threads'].keys()):
            session['account_status'][key] = False
            del session['account_threads'][key]
            del session['account_status'][key]

        self.send_message(vk_user_id, "Все конфигурации остановлены.", keyboard=self.main_keyboard())

    def show_available_configs(self, vk_user_id, telegram_user_id, page=0):
        user_configs_dir = self.manager.get_user_configs_dir(telegram_user_id)
        all_configs = [f[:-5] for f in os.listdir(user_configs_dir) if f.endswith(".json")]

        if not all_configs:
            self.send_message(
                vk_user_id,
                "Нет доступных конфигураций. Сначала создайте конфигурацию в разделе 'Все конфигурации'.",
                keyboard=self.main_keyboard(),
            )
            return

        session = self.manager.get_user_session(telegram_user_id)
        running_keys = set(session['account_threads'].keys())
        running_configs = []

        for config_file in os.listdir(user_configs_dir):
            if config_file.endswith(".json"):
                with open(os.path.join(user_configs_dir, config_file), "r") as f:
                    config = json.load(f)
                    key = (config["ACCESS_TOKEN"], str(config["GROUP_ID"]))
                    if key in running_keys:
                        running_configs.append(config_file[:-5])

        available_configs = [c for c in all_configs if c not in running_configs]

        if not available_configs:
            self.send_message(vk_user_id, "Все конфигурации уже запущены.", keyboard=self.main_keyboard())
            return

        available_configs = sorted(available_configs)
        page_configs, page, page_count, start = self.get_page_items(available_configs, page)

        buttons = [
            {
                "label": config_name,
                "action": "start_config",
                "config_name": config_name,
                "page": page,
                "color": VkKeyboardColor.POSITIVE,
            }
            for config_name in page_configs
        ]
        self.add_page_buttons(buttons, "start_config_menu", page, page_count)

        self.send_message(
            vk_user_id,
            f"Выберите конфигурацию для запуска:\nСтраница {page + 1}/{page_count}. Показаны {start + 1}-{start + len(page_configs)} из {len(available_configs)}.",
            keyboard=self.build_keyboard(buttons),
        )

    def prepare_to_start_config(self, vk_user_id, telegram_user_id, config_name):
        session = self.manager.get_user_session(telegram_user_id)
        session['temp_data'] = {"config_name": config_name}
        session['state'] = "preparing_to_start"

        buttons = [
            {"label": "Сегодня", "action": "select_date", "config_name": config_name, "selected_date": "today", "color": VkKeyboardColor.POSITIVE},
            {"label": "Завтра", "action": "select_date", "config_name": config_name, "selected_date": "tomorrow", "color": VkKeyboardColor.POSITIVE},
            {"label": "🔙 Назад", "action": "back_to_main", "color": VkKeyboardColor.PRIMARY},
        ]

        self.send_message(vk_user_id, "Выберите дату публикации:", keyboard=self.build_keyboard(buttons))

    def handle_date_selection(self, vk_user_id, telegram_user_id, config_name, selected_date):
        session = self.manager.get_user_session(telegram_user_id)

        if selected_date == "today":
            post_date = datetime.now()
        else:
            post_date = datetime.now() + timedelta(days=1)

        session['temp_data']["post_date"] = post_date
        session['state'] = "waiting_time"

        buttons = [
            {"label": "🔙 Назад", "action": "start_config", "config_name": config_name, "color": VkKeyboardColor.PRIMARY},
        ]

        self.send_message(
            vk_user_id,
            "Введите время публикации (любой формат, например 13:30 или 14:00-15:30):",
            keyboard=self.build_keyboard(buttons),
        )

    def process_time_input(self, vk_user_id, telegram_user_id, text):
        session = self.manager.get_user_session(telegram_user_id)

        if session['state'] != "waiting_time":
            return

        try:
            time_str = text
            config_name = session['temp_data']["config_name"]
            user_configs_dir = self.manager.get_user_configs_dir(telegram_user_id)
            config_path = os.path.join(user_configs_dir, f"{config_name}.json")

            if not os.path.exists(config_path):
                self.send_message(vk_user_id, "Конфигурация не найдена.")
                return

            with open(config_path, "r") as f:
                config = json.load(f)

            post_text = config["POST_TEXT"]
            post_text = self.manager.replace_placeholders(post_text, session['temp_data']["post_date"], time_str)

            key = (config["ACCESS_TOKEN"], str(config["GROUP_ID"]))
            interval = int(config["INTERVAL"])

            session['account_status'][key] = True
            thread = threading.Thread(
                target=self.manager.post_to_vk,
                args=(telegram_user_id, key, post_text, interval),
                daemon=True,
            )
            session['account_threads'][key] = thread
            thread.start()

            self.send_message(vk_user_id, f"Конфигурация {config_name} запущена! Время: {time_str}")
            session['state'] = None
            session['temp_data'] = {}
            self.show_main_menu(vk_user_id)

        except Exception as e:
            self.send_message(vk_user_id, f"Произошла ошибка: {str(e)}")

    def show_all_configs_menu(self, vk_user_id, telegram_user_id, page=0):
        user_configs_dir = self.manager.get_user_configs_dir(telegram_user_id)
        configs = sorted(f[:-5] for f in os.listdir(user_configs_dir) if f.endswith(".json"))
        page_configs, page, page_count, start = self.get_page_items(configs, page)

        buttons = [
            {
                "label": config_name,
                "action": "config_action",
                "config_name": config_name,
                "config_action": "view",
                "page": page,
                "color": VkKeyboardColor.SECONDARY,
            }
            for config_name in page_configs
        ]
        self.add_page_buttons(
            buttons,
            "all_configs",
            page,
            page_count,
            extra_button={"label": "➕ Добавить", "action": "add_config", "color": VkKeyboardColor.POSITIVE},
        )

        if configs:
            text = f"Все конфигурации:\nСтраница {page + 1}/{page_count}. Показаны {start + 1}-{start + len(page_configs)} из {len(configs)}."
        else:
            text = "Все конфигурации: пусто."

        self.send_message(vk_user_id, text, keyboard=self.build_keyboard(buttons))

    def show_config_details(self, vk_user_id, telegram_user_id, config_name, page=0):
        user_configs_dir = self.manager.get_user_configs_dir(telegram_user_id)
        config_path = os.path.join(user_configs_dir, f"{config_name}.json")

        if not os.path.exists(config_path):
            self.send_message(vk_user_id, "Конфигурация не найдена.")
            return

        with open(config_path, "r") as f:
            config = json.load(f)

        buttons = [
            {"label": "✏️ Редактировать текст", "action": "config_action", "config_name": config_name, "config_action": "edit_text", "page": page, "color": VkKeyboardColor.PRIMARY},
            {"label": "⌚ Изменить интервал", "action": "config_action", "config_name": config_name, "config_action": "edit_interval", "page": page, "color": VkKeyboardColor.PRIMARY},
            {"label": "🗑️ Удалить", "action": "config_action", "config_name": config_name, "config_action": "delete", "page": page, "color": VkKeyboardColor.NEGATIVE},
            {"label": "🔙 Назад", "action": "back_to_all_configs", "page": page, "color": VkKeyboardColor.PRIMARY},
        ]

        response = (
            f"Конфигурация: {config_name}\n"
            f"Токен: {config.get('ACCESS_TOKEN', '')}\n"
            f"ID группы: {config.get('GROUP_ID', '')}\n"
            f"Текст поста:\n{config.get('POST_TEXT', '')}"
            f"\nИнтервал публикации: {config.get('INTERVAL', '')}"
        )

        self.send_message(vk_user_id, response, keyboard=self.build_keyboard(buttons))

    def edit_config_text(self, vk_user_id, telegram_user_id, config_name):
        user_configs_dir = self.manager.get_user_configs_dir(telegram_user_id)
        config_path = os.path.join(user_configs_dir, f"{config_name}.json")

        if not os.path.exists(config_path):
            self.send_message(vk_user_id, "Конфигурация не найдена.")
            return

        session = self.manager.get_user_session(telegram_user_id)
        session['state'] = f"editing_text:{config_name}"

        buttons = [
            {"label": "🔙 Назад", "action": "config_action", "config_name": config_name, "config_action": "view", "color": VkKeyboardColor.PRIMARY},
        ]

        self.send_message(
            vk_user_id,
            "Введите новый текст поста (можно использовать метки <time>, <day>, <weekday>):",
            keyboard=self.build_keyboard(buttons),
        )

    def edit_config_interval(self, vk_user_id, telegram_user_id, config_name):
        user_configs_dir = self.manager.get_user_configs_dir(telegram_user_id)
        config_path = os.path.join(user_configs_dir, f"{config_name}.json")

        if not os.path.exists(config_path):
            self.send_message(vk_user_id, "Конфигурация не найдена.")
            return

        session = self.manager.get_user_session(telegram_user_id)
        session['state'] = f"editing_interval:{config_name}"

        buttons = [
            {"label": "🔙 Назад", "action": "config_action", "config_name": config_name, "config_action": "view", "color": VkKeyboardColor.PRIMARY},
        ]

        self.send_message(vk_user_id, "Введите интервал публикации (в минутах):", keyboard=self.build_keyboard(buttons))

    def process_text_edit(self, vk_user_id, telegram_user_id, text):
        session = self.manager.get_user_session(telegram_user_id)

        if not session['state'] or not session['state'].startswith("editing_text:"):
            return

        config_name = session['state'].split(":")[1]
        user_configs_dir = self.manager.get_user_configs_dir(telegram_user_id)
        config_path = os.path.join(user_configs_dir, f"{config_name}.json")

        if not os.path.exists(config_path):
            self.send_message(vk_user_id, "Конфигурация не найдена.")
            return

        with open(config_path, "r") as f:
            config = json.load(f)

        config["POST_TEXT"] = text

        with open(config_path, "w") as f:
            json.dump(config, f)

        self.send_message(vk_user_id, "Текст поста обновлен!")
        session['state'] = None
        self.show_config_details(vk_user_id, telegram_user_id, config_name)

    def process_interval_edit(self, vk_user_id, telegram_user_id, text):
        session = self.manager.get_user_session(telegram_user_id)

        if not session['state'] or not session['state'].startswith("editing_interval:"):
            return

        config_name = session['state'].split(":")[1]
        user_configs_dir = self.manager.get_user_configs_dir(telegram_user_id)
        config_path = os.path.join(user_configs_dir, f"{config_name}.json")

        if not os.path.exists(config_path):
            self.send_message(vk_user_id, "Конфигурация не найдена.")
            return

        with open(config_path, "r") as f:
            config = json.load(f)

        config["INTERVAL"] = text

        with open(config_path, "w") as f:
            json.dump(config, f)

        self.send_message(vk_user_id, "Интервал публикации обновлен!")
        session['state'] = None
        self.show_config_details(vk_user_id, telegram_user_id, config_name)

    def delete_config(self, vk_user_id, telegram_user_id, config_name, page=0):
        session = self.manager.get_user_session(telegram_user_id)
        user_configs_dir = self.manager.get_user_configs_dir(telegram_user_id)
        config_path = os.path.join(user_configs_dir, f"{config_name}.json")

        if not os.path.exists(config_path):
            self.send_message(vk_user_id, "Конфигурация не найдена.")
            return

        with open(config_path, "r") as f:
            config = json.load(f)

        key = (config["ACCESS_TOKEN"], str(config["GROUP_ID"]))

        if key in session['account_threads']:
            self.send_message(vk_user_id, "Сначала остановите эту конфигурацию!")
            return

        os.remove(config_path)
        self.send_message(vk_user_id, f"Конфигурация {config_name} удалена.")
        self.show_all_configs_menu(vk_user_id, telegram_user_id, page)

    def add_new_config(self, vk_user_id, telegram_user_id):
        session = self.manager.get_user_session(telegram_user_id)
        session['state'] = "adding_config:name"
        session['temp_data'] = {}

        buttons = [
            {"label": "🔙 Назад", "action": "back_to_all_configs", "color": VkKeyboardColor.PRIMARY},
        ]

        self.send_message(vk_user_id, "Введите название новой конфигурации:", keyboard=self.build_keyboard(buttons))

    def process_config_creation(self, vk_user_id, telegram_user_id, text):
        session = self.manager.get_user_session(telegram_user_id)

        if not session['state'] or not session['state'].startswith("adding_config:"):
            return

        current_step = session['state'].split(":")[1]

        if current_step == "name":
            config_name = text
            user_configs_dir = self.manager.get_user_configs_dir(telegram_user_id)

            if f"{config_name}.json" in os.listdir(user_configs_dir):
                self.send_message(vk_user_id, "Конфигурация с таким именем уже существует. Введите другое название:")
                return

            session['temp_data']['name'] = config_name
            session['state'] = "adding_config:token"

            buttons = [
                {"label": "🔙 Назад", "action": "add_config", "color": VkKeyboardColor.PRIMARY},
            ]

            self.send_message(vk_user_id, "Введите токен VK:", keyboard=self.build_keyboard(buttons))

        elif current_step == "token":
            session['temp_data']['token'] = text
            session['state'] = "adding_config:group_id"

            buttons = [
                {"label": "🔙 Назад", "action": "add_config", "color": VkKeyboardColor.PRIMARY},
            ]

            self.send_message(vk_user_id, "Введите ID группы:", keyboard=self.build_keyboard(buttons))

        elif current_step == "group_id":
            try:
                group_id = int(text)
                session['temp_data']['group_id'] = group_id
                session['state'] = "adding_config:text"

                buttons = [
                    {"label": "🔙 Назад", "action": "add_config", "color": VkKeyboardColor.PRIMARY},
                ]

                self.send_message(
                    vk_user_id,
                    "Введите текст поста (можно использовать метки <time>, <day>, <weekday>):",
                    keyboard=self.build_keyboard(buttons),
                )
            except ValueError:
                self.send_message(vk_user_id, "ID группы должен быть числом. Введите корректный ID:")

        elif current_step == "text":
            session['temp_data']['text'] = text
            session['state'] = "adding_config:interval"

            buttons = [
                {"label": "🔙 Назад", "action": "add_config", "color": VkKeyboardColor.PRIMARY},
            ]

            self.send_message(vk_user_id, "Введите интервал публикации (в минутах):", keyboard=self.build_keyboard(buttons))

        elif current_step == "interval":
            try:
                interval = int(text)
                if interval <= 0:
                    raise ValueError

                config_data = {
                    "ACCESS_TOKEN": session['temp_data']['token'],
                    "GROUP_ID": session['temp_data']['group_id'],
                    "POST_TEXT": session['temp_data']['text'],
                    "INTERVAL": interval,
                }

                user_configs_dir = self.manager.get_user_configs_dir(telegram_user_id)
                config_path = os.path.join(user_configs_dir, f"{session['temp_data']['name']}.json")
                with open(config_path, "w") as f:
                    json.dump(config_data, f)

                self.send_message(vk_user_id, f"Конфигурация {session['temp_data']['name']} успешно создана!")
                session['state'] = None
                session['temp_data'] = {}

                self.show_all_configs_menu(vk_user_id, telegram_user_id)

            except ValueError:
                self.send_message(vk_user_id, "Интервал должен быть положительным числом. Введите корректное значение:")

    def run(self):
        while True:
            try:
                for event in self.longpoll.listen():
                    if event.type == VkBotEventType.MESSAGE_NEW:
                        self.handle_event(event)
            except requests.exceptions.ReadTimeout:
                print("⚠️ VK ReadTimeout — пробую переподключиться...")
                time.sleep(5)
            except requests.exceptions.ConnectionError:
                print("⚠️ VK ConnectionError — нет соединения, жду...")
                time.sleep(5)
            except Exception as e:
                print(f"❌ Ошибка VK-бота: {e}")
                time.sleep(5)


if __name__ == "__main__":
    telegram_token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not telegram_token:
        raise RuntimeError("Задайте переменную окружения TELEGRAM_BOT_TOKEN")

    bot = TelegramVKPostManagerBot(telegram_token)

    vk_token = os.getenv("VK_BOT_GROUP_TOKEN")
    vk_group_id = os.getenv("VK_GROUP_ID")

    if vk_token and vk_group_id:
        vk_bot = VKPostManagerBot(bot, vk_token, vk_group_id)
        threading.Thread(target=bot.run, daemon=True).start()
        vk_bot.run()
    else:
        print("VK-бот не запущен: задайте VK_BOT_GROUP_TOKEN и VK_GROUP_ID")
        bot.run()
