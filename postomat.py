import telebot
from telebot import types
import threading
import os
import json
import time
import requests
from datetime import datetime, timedelta

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
            # Получаем последние 10 постов
            response = requests.post(
                "https://api.vk.ru/method/wall.get",
                params={
                    "access_token": token,
                    "owner_id": f"-{group_id}",
                    "count": 10,
                    "v": "5.131",
                }
            ).json()

            posts = response.get("response", {}).get("items", [])
            # Удаляем только свои посты
            for post in posts:
                if post.get("from_id") == current_user_id:
                    requests.post(
                        "https://api.vk.ru/method/wall.delete",
                        params={
                            "access_token": token,
                            "owner_id": f"-{group_id}",
                            "post_id": post["id"],
                            "v": "5.131",
                        }
                    )

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

                self.remove_existing_posts(token, group_id)

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

        self.bot.polling(none_stop=True)

if __name__ == "__main__":
    # Замените 'YOUR_TELEGRAM_BOT_TOKEN' на реальный токен вашего бота
    bot = TelegramVKPostManagerBot('8411053706:AAEVLWMhJr_cNrl-yInK3ibyMt6awNUd0X4')
    bot.run()
