import tkinter as tk
from time import sleep
from tkinter import messagebox
import requests
import threading
import time
import json
import os

class VKPostManager:
    CONFIG_DIR = "vk_post_configs"

    def __init__(self, root):
        self.root = root
        self.root.title("VK Post Manager")
        self.account_threads = {}
        self.account_status = {}

        # Поля для ввода данных
        tk.Label(root, text="Токен пользователя:").grid(row=0, column=0, padx=5, pady=5)
        self.token_entry = tk.Entry(root, width=40)
        self.token_entry.grid(row=0, column=1, padx=5, pady=5)
        self.add_context_menu(self.token_entry)

        tk.Label(root, text="Айди группы:").grid(row=1, column=0, padx=5, pady=5)
        self.group_id_entry = tk.Entry(root, width=40)
        self.group_id_entry.grid(row=1, column=1, padx=5, pady=5)
        self.add_context_menu(self.group_id_entry)

        tk.Label(root, text="Текст поста:").grid(row=2, column=0, padx=5, pady=5)
        self.post_text_entry = tk.Text(root, width=40, height=5)
        self.post_text_entry.grid(row=2, column=1, padx=5, pady=5)
        self.add_context_menu(self.post_text_entry)

        tk.Label(root, text="Интервал обновления (секунды):").grid(row=3, column=0, padx=5, pady=5)
        self.interval_entry = tk.Entry(root, width=40)
        self.interval_entry.grid(row=3, column=1, padx=5, pady=5)

        # Кнопки управления
        tk.Button(root, text="Запустить", command=self.start_posting).grid(row=4, column=0, columnspan=2, pady=10)
        tk.Button(root, text="Остановить", command=self.stop_posting).grid(row=5, column=0, columnspan=2, pady=5)

        # Кнопки для управления конфигурациями
        tk.Button(root, text="Сохранить конфиг", command=self.save_config).grid(row=0, column=2, padx=5, pady=5)
        tk.Button(root, text="Загрузить конфиг", command=self.load_config).grid(row=1, column=2, padx=5, pady=5)
        tk.Label(root, text="Имя конфига:").grid(row=2, column=2, padx=5, pady=5)
        self.config_name_entry = tk.Entry(root, width=20)
        self.config_name_entry.grid(row=3, column=2, padx=5, pady=5)

        # Создание директории для конфигов
        if not os.path.exists(self.CONFIG_DIR):
            os.makedirs(self.CONFIG_DIR)

    def add_context_menu(self, widget):
        # Создание контекстного меню
        menu = tk.Menu(widget, tearoff=0)
        menu.add_command(label="Вырезать", command=lambda: widget.event_generate("<<Cut>>"))
        menu.add_command(label="Копировать", command=lambda: widget.event_generate("<<Copy>>"))
        menu.add_command(label="Вставить", command=lambda: widget.event_generate("<<Paste>>"))

        def show_menu(event):
            menu.post(event.x_root, event.y_root)

        widget.bind("<Button-3>", show_menu)  # Привязка правой кнопки мыши

    def remove_existing_posts(self, token, group_id):
        try:
            # Получаем ID пользователя, связанный с токеном
            user_info_url = "https://api.vk.com/method/users.get"
            user_info_params = {
                "access_token": token,
                "v": "5.131",
            }
            user_response = requests.get(user_info_url, params=user_info_params).json()

            if "error" in user_response:
                print(f"Ошибка получения ID пользователя: {user_response['error']['error_msg']}")
                return

            user_id = user_response["response"][0]["id"]
            print(f"ID пользователя: {user_id}")

            # Получаем все посты на стене группы
            get_url = "https://api.vk.com/method/wall.get"
            get_params = {
                "access_token": token,
                "owner_id": f"-{group_id}",
                "count": 50,
                "v": "5.131",
            }
            response = requests.get(get_url, params=get_params).json()

            if "error" in response:
                print(f"Ошибка получения постов: {response['error']['error_msg']}")
                return

            posts = response.get("response", {}).get("items", [])

            # Фильтруем посты, чтобы оставить только посты от конкретного пользователя
            user_posts = [post for post in posts if post.get("from_id") == user_id]

            # Ограничиваем количество удаляемых постов
            posts_to_remove = user_posts[:30]

            for post in posts_to_remove:
                post_id = post["id"]
                # Пытаемся удалить пост
                delete_url = "https://api.vk.com/method/wall.delete"
                delete_params = {
                    "access_token": token,
                    "owner_id": f"-{group_id}",
                    "post_id": post_id,
                    "v": "5.131",
                }
                delete_response = requests.post(delete_url, params=delete_params).json()

                if "error" in delete_response:
                    print(f"Ошибка удаления поста {post_id}: {delete_response['error']['error_msg']}")
                else:
                    print(f"Пост {post_id} удален")

        except Exception as e:
            print(f"Произошла ошибка при удалении постов: {str(e)}")

    def post_to_vk(self, key, message, interval):
        token, group_id = key
        is_first = True
        status = self.account_status[key]
        while status:  # Проверяем индивидуальный статус
            try:
                if not is_first:
                    # Удаление поста
                    delete_url = "https://api.vk.com/method/wall.delete"
                    delete_params = {
                        "access_token": token,
                        "owner_id": f"-{group_id}",
                        "post_id": post_id,
                        "v": "5.131",
                    }
                    delete_response = requests.post(delete_url, params=delete_params).json()

                    if "error" in delete_response:
                        print("Ошибка", f"Ошибка удаления: {delete_response['error']['error_msg']}")
                        break

                    print(f"Пост удален: {post_id}")

                # Публикация поста
                post_url = "https://api.vk.com/method/wall.post"
                post_params = {
                    "access_token": token,
                    "owner_id": f"-{group_id}",
                    "message": message,
                    "v": "5.131",
                }
                response = requests.post(post_url, params=post_params).json()

                if "error" in response:
                    print("Ошибка", f"Ошибка публикации: {response['error']['error_msg']}")
                    break

                post_id = response["response"]["post_id"]
                print(f"Пост опубликован: {post_id}")
                is_first = False
                time.sleep(interval)
                status = self.account_status[key]

            except Exception as e:
                print("Ошибка", f"Произошла ошибка: {str(e)}")
                break

    def start_posting(self):
        token = self.token_entry.get().strip().replace('\n', '')
        group_id = self.group_id_entry.get().strip().replace('\n', '')
        message = self.post_text_entry.get("1.0", tk.END).strip()
        interval = self.interval_entry.get()

        if not token or not group_id or not message or not interval:
            messagebox.showerror("Ошибка", "Заполните все поля!")
            return

        try:
            interval = int(interval)
        except ValueError:
            messagebox.showerror("Ошибка", "Интервал должен быть числом!")
            return

        key = (token, group_id)  # Уникальный ключ для потока

        if key in self.account_threads:
            messagebox.showerror("Ошибка", "Этот аккаунт и группа уже запущены!")
            return

        # Проверяем и удаляем существующие посты перед началом
        self.remove_existing_posts(token, group_id)

        sleep(1)

        self.account_status[key] = True  # Устанавливаем статус на "выполняется"
        thread = threading.Thread(target=self.post_to_vk, args=(key, message, interval), daemon=True)
        self.account_threads[key] = thread
        thread.start()

    def stop_posting(self):
        token = self.token_entry.get().strip().replace('\n', '')
        group_id = self.group_id_entry.get().strip().replace('\n', '')

        if not token or not group_id:
            messagebox.showerror("Ошибка", "Введите токен и ID группы для остановки!")
            return

        key = (token, group_id)

        if key not in self.account_threads:
            messagebox.showerror("Ошибка", "Этот аккаунт и группа не активны!")
            return

        # Остановка работы потока
        del self.account_threads[key]  # Удаляем поток из словаря
        self.account_status[key] = False
        print("Успех, публикация остановлена.")

    def save_config(self):
        config_name = self.config_name_entry.get().strip()
        if not config_name:
            messagebox.showerror("Ошибка", "Введите имя для конфигурации!")
            return

        config_path = os.path.join(self.CONFIG_DIR, f"{config_name}.json")
        config = {
            "ACCESS_TOKEN": self.token_entry.get().strip().replace('\n', ''),
            "GROUP_ID": self.group_id_entry.get().strip().replace('\n', ''),
            "POST_TEXT": self.post_text_entry.get("1.0", tk.END).strip(),
            "INTERVAL": self.interval_entry.get(),
        }
        with open(config_path, "w") as f:
            json.dump(config, f)
        messagebox.showinfo("Успех", f"Конфигурация '{config_name}' сохранена.")

    def load_config(self):
        config_name = self.config_name_entry.get().strip()
        if not config_name:
            messagebox.showerror("Ошибка", "Введите имя для конфигурации!")
            return

        config_path = os.path.join(self.CONFIG_DIR, f"{config_name}.json")
        if not os.path.exists(config_path):
            messagebox.showerror("Ошибка", f"Конфигурация '{config_name}' не найдена.")
            return

        with open(config_path, "r") as f:
            config = json.load(f)
            self.token_entry.delete(0, tk.END)
            self.token_entry.insert(0, config.get("ACCESS_TOKEN", ""))

            self.group_id_entry.delete(0, tk.END)
            self.group_id_entry.insert(0, config.get("GROUP_ID", ""))

            self.post_text_entry.delete("1.0", tk.END)
            self.post_text_entry.insert("1.0", config.get("POST_TEXT", ""))

            self.interval_entry.delete(0, tk.END)
            self.interval_entry.insert(0, config.get("INTERVAL", ""))
        print("Успех", f"Конфигурация '{config_name}' загружена.")

# Запуск приложения
if __name__ == "__main__":
    root = tk.Tk()
    app = VKPostManager(root)
    root.mainloop()