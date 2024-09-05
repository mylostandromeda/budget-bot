import os
import psycopg2
from flask import Flask, request
from telegram.ext import Updater, CommandHandler
import telegram

# Отримуємо токен із змінних оточення
TOKEN = os.getenv("TOKEN")

# Налаштування Flask для вебхуків
app = Flask(__name__)

# Ініціалізація об'єкта Updater
updater = Updater(TOKEN, use_context=True)


# Підключення до бази даних PostgreSQL
def connect_db():
    return psycopg2.connect(os.getenv('DATABASE_URL'), sslmode='require')


# Створення таблиць для зберігання даних
def create_tables():
    conn = connect_db()
    cur = conn.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            user_id BIGINT UNIQUE,
            role VARCHAR(20),
            budget FLOAT,
            balance FLOAT
        )
    ''')
    conn.commit()
    cur.close()
    conn.close()


# Функція для встановлення бюджету
def set_budget(user_id, budget):
    conn = connect_db()
    cur = conn.cursor()
    cur.execute('''
        INSERT INTO users (user_id, role, budget, balance)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (user_id) 
        DO UPDATE SET budget = %s, balance = %s
    ''', (user_id, 'owner', budget, budget, budget, budget))
    conn.commit()
    cur.close()
    conn.close()


# Функція для оновлення балансу після витрат
def update_balance(user_id, amount):
    conn = connect_db()
    cur = conn.cursor()
    cur.execute('UPDATE users SET balance = balance - %s WHERE user_id = %s', (amount, user_id))
    conn.commit()
    cur.close()
    conn.close()


# Функція для отримання балансу
def get_balance(user_id):
    conn = connect_db()
    cur = conn.cursor()
    cur.execute('SELECT balance FROM users WHERE user_id = %s', (user_id,))
    result = cur.fetchone()
    cur.close()
    conn.close()
    if result:
        return result[0]
    return None


# Функція для перевірки ролі користувача
def get_user_role(user_id):
    conn = connect_db()
    cur = conn.cursor()
    cur.execute('SELECT role FROM users WHERE user_id = %s', (user_id,))
    result = cur.fetchone()
    cur.close()
    conn.close()
    if result:
        return result[0]
    return None


# Функція для додавання спостерігача
def add_observer(owner_id, observer_id):
    conn = connect_db()
    cur = conn.cursor()
    cur.execute('''
        INSERT INTO users (user_id, role)
        VALUES (%s, %s)
        ON CONFLICT (user_id)
        DO NOTHING
    ''', (observer_id, 'observer'))
    conn.commit()
    cur.close()
    conn.close()


# Команда для старту бота
def start(update, context):
    user_id = update.message.from_user.id
    role = get_user_role(user_id)

    if role == 'owner':
        update.message.reply_text(
            "Привіт! Ти власник цього бота. Використовуй /setbudget <сума> для встановлення бюджету.")
    elif role == 'observer':
        update.message.reply_text("Привіт! Ти спостерігач цього бота. Використовуй /balance, щоб переглянути залишок.")
    else:
        update.message.reply_text("Привіт! Використовуй /start для реєстрації.")


# Команда для встановлення бюджету
def setbudget(update, context):
    user_id = update.message.from_user.id
    role = get_user_role(user_id)

    if role == 'owner':
        try:
            budget = float(context.args[0])
            set_budget(user_id, budget)
            update.message.reply_text(f"Твій бюджет встановлено: {budget} грн.")
        except (IndexError, ValueError):
            update.message.reply_text("Будь ласка, введи коректну суму. Приклад: /setbudget 5000")
    else:
        update.message.reply_text("Ти не маєш прав встановлювати бюджет.")


# Команда для витрат
def spend(update, context):
    user_id = update.message.from_user.id
    role = get_user_role(user_id)

    if role == 'owner':
        try:
            amount = float(context.args[0])
            update_balance(user_id, amount)
            balance = get_balance(user_id)
            update.message.reply_text(f"Витрачено {amount} грн. Залишок: {balance} грн.")
        except (IndexError, ValueError):
            update.message.reply_text("Будь ласка, введи коректну суму витрат. Приклад: /spend 500")
    else:
        update.message.reply_text("Ти не маєш прав витрачати кошти.")


# Команда для перевірки балансу
def balance(update, context):
    user_id = update.message.from_user.id
    balance = get_balance(user_id)

    if balance is not None:
        update.message.reply_text(f"Залишок: {balance} грн.")
    else:
        update.message.reply_text("Будь ласка, спочатку встанови бюджет за допомогою /setbudget.")


# Команда для додавання спостерігача
def addobserver(update, context):
    owner_id = update.message.from_user.id
    role = get_user_role(owner_id)

    if role == 'owner':
        try:
            observer_id = int(context.args[0])
            add_observer(owner_id, observer_id)
            update.message.reply_text(f"Користувач {observer_id} доданий як спостерігач.")
        except (IndexError, ValueError):
            update.message.reply_text("Будь ласка, введи коректний ID спостерігача. Приклад: /addobserver 123456789")
    else:
        update.message.reply_text("Ти не маєш прав додавати спостерігачів.")


# Основна функція для запуску бота
def main():
    # Ініціалізація Telegram Updater
    dp = updater.dispatcher

    # Додаємо обробники для команд
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("setbudget", setbudget))
    dp.add_handler(CommandHandler("spend", spend))
    dp.add_handler(CommandHandler("balance", balance))
    dp.add_handler(CommandHandler("addobserver", addobserver))

    # Створюємо таблиці при першому запуску
    create_tables()

    # Налаштування вебхука для Telegram
    PORT = int(os.environ.get('PORT', 5000))
    updater.start_webhook(listen="0.0.0.0",
                          port=PORT,
                          url_path=TOKEN)

    # Вказуємо Telegram API, де знаходиться вебхук
    updater.bot.setWebhook(f"https://{os.getenv('HEROKU_APP_NAME')}.herokuapp.com/{TOKEN}")

    # Запускаємо бота
    updater.idle()


# Обробка запитів від Telegram через Flask
@app.route(f"/{TOKEN}", methods=["POST"])
def webhook():
    # Використання об'єкта updater для обробки оновлень
    update = telegram.Update.de_json(request.get_json(force=True), updater.bot)
    updater.dispatcher.process_update(update)
    return "ok", 200


# Запуск Flask програми
if __name__ == "__main__":
    # Отримуємо порт для запуску Flask з середовища (або використовуємо 5000 за замовчуванням)
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
