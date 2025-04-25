import json
import sqlite3
from telebot import TeleBot, types

# Загрузка вопросов из JSON
with open('questions.json', 'r', encoding='utf-8') as f:
    QUESTIONS = json.load(f)

# Инициализация бота
bot = TeleBot("ваш супер-пупер токен")

# Подключение к БД
conn = sqlite3.connect('quiz.db', check_same_thread=False)
cursor = conn.cursor()


# Создание таблиц
def init_db():
    try:
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER UNIQUE NOT NULL,
            username TEXT,
            full_name TEXT NOT NULL,
            math_score INTEGER DEFAULT 0,
            cs_score INTEGER DEFAULT 0,
            history_score INTEGER DEFAULT 0,
            total_score INTEGER DEFAULT 0,
            last_active TEXT DEFAULT CURRENT_TIMESTAMP
        )
        ''')

        cursor.execute('''
        CREATE TABLE IF NOT EXISTS test_progress (
            user_id INTEGER PRIMARY KEY,
            subject TEXT NOT NULL,
            current_question INTEGER DEFAULT 0,
            correct_answers INTEGER DEFAULT 0,
            FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE
        )
        ''')
        conn.commit()
    except sqlite3.Error as e:
        print(f"Ошибка при создании таблиц: {e}")


init_db()


# Клавиатуры
def main_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    buttons = [
        types.KeyboardButton(f"🧮 Математика ({len(QUESTIONS['math'])} вопр.)"),
        types.KeyboardButton(f"💻 Информатика ({len(QUESTIONS['cs'])} вопр.)"),
        types.KeyboardButton(f"🏛️ История ({len(QUESTIONS['history'])} вопр.)"),
        types.KeyboardButton("🏆 Топ игроков"),
        types.KeyboardButton("ℹ️ О боте"),
    ]
    markup.add(*buttons)
    return markup


def question_markup(options):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    for option in options:
        markup.add(types.KeyboardButton(option))
    markup.add(types.KeyboardButton("❌ Отменить тест"))
    return markup


# Обработчики команд
@bot.message_handler(commands=['start'])
def start(message):
    user = message.from_user
    try:
        cursor.execute(
            "INSERT OR IGNORE INTO users (user_id, username, full_name) VALUES (?, ?, ?)",
            (user.id, user.username, user.first_name)
        )
        cursor.execute(
            "UPDATE users SET last_active = CURRENT_TIMESTAMP WHERE user_id = ?",
            (user.id,)
        )
        conn.commit()
    except sqlite3.Error as e:
        print(f"Ошибка БД: {e}")

    bot.send_message(
        message.chat.id,
        f"Привет, {user.first_name}! 👋\nВыбери тест:",
        reply_markup=main_menu()
    )


@bot.message_handler(func=lambda m: any(subj in m.text for subj in ["Математика", "Информатика", "История"]))
def start_test(message):
    subject_map = {
        "Математика": "math",
        "Информатика": "cs",
        "История": "history"
    }
    subject_name = next((subj for subj in subject_map if subj in message.text), None)

    if not subject_name:
        return

    subject = subject_map[subject_name]

    try:
        cursor.execute(
            "INSERT OR REPLACE INTO test_progress (user_id, subject, current_question, correct_answers) VALUES (?, ?, ?, ?)",
            (message.from_user.id, subject, 0, 0)
        )
        conn.commit()
        send_question(message.chat.id, message.from_user.id, subject, 0)
    except sqlite3.Error as e:
        print(f"Ошибка БД: {e}")
        bot.send_message(message.chat.id, "Ошибка при запуске теста. Попробуйте позже.")


def send_question(chat_id, user_id, subject, question_num):
    questions = QUESTIONS.get(subject, [])

    if question_num >= len(questions):
        finish_test(chat_id, user_id, subject)
        return

    question = questions[question_num]
    bot.send_message(
        chat_id,
        f"{question['emoji']} Вопрос {question_num + 1}/{len(questions)}\n{question['question']}",
        reply_markup=question_markup(question['options'])
    )


@bot.message_handler(func=lambda m: True)
def handle_message(message):
    try:
        cursor.execute(
            "SELECT subject, current_question, correct_answers FROM test_progress WHERE user_id = ?",
            (message.from_user.id,)
        )
        progress = cursor.fetchone()

        if not progress:
            if message.text == "🏆 Топ игроков":
                show_top(message)
            elif message.text == "ℹ️ О боте":
                about(message)
            return

        subject, question_num, correct = progress

        if message.text == "❌ Отменить тест":
            cursor.execute(
                "DELETE FROM test_progress WHERE user_id = ?",
                (message.from_user.id,)
            )
            conn.commit()
            bot.send_message(
                message.chat.id,
                "Тест отменён",
                reply_markup=main_menu()
            )
            return

        questions = QUESTIONS.get(subject, [])
        if question_num >= len(questions):
            return

        question = questions[question_num]

        if message.text in question['options']:
            if message.text == question['options'][question['answer']]:
                correct += 1
                response = "✅ Верно!"
            else:
                response = f"❌ Неверно! Правильный ответ: {question['options'][question['answer']]}"

            cursor.execute(
                "UPDATE test_progress SET current_question = ?, correct_answers = ? WHERE user_id = ?",
                (question_num + 1, correct, message.from_user.id)
            )
            conn.commit()

            bot.send_message(message.chat.id, response)
            send_question(message.chat.id, message.from_user.id, subject, question_num + 1)

    except sqlite3.Error as e:
        print(f"Ошибка БД: {e}")
        bot.send_message(message.chat.id, "Произошла ошибка. Попробуйте позже.")


def finish_test(chat_id, user_id, subject):
    try:
        cursor.execute(
            "SELECT correct_answers FROM test_progress WHERE user_id = ?",
            (user_id,)
        )
        correct = cursor.fetchone()[0]

        cursor.execute(
            f"UPDATE users SET {subject}_score = {subject}_score + ?, total_score = total_score + ? WHERE user_id = ?",
            (correct, correct, user_id)
        )
        cursor.execute(
            "DELETE FROM test_progress WHERE user_id = ?",
            (user_id,)
        )
        conn.commit()

        bot.send_message(
            chat_id,
            f"🎉 Тест завершён!\nПравильных ответов: {correct}/{len(QUESTIONS.get(subject, []))}",
            reply_markup=main_menu()
        )
    except sqlite3.Error as e:
        print(f"Ошибка БД: {e}")
        bot.send_message(chat_id, "Ошибка при завершении теста")


def show_top(message):
    try:
        cursor.execute(
            "SELECT username, total_score FROM users ORDER BY total_score DESC LIMIT 10"
        )
        top = cursor.fetchall()

        response = "🏆 ТОП-10 ИГРОКОВ 🏆\n\n"
        for i, (username, score) in enumerate(top, 1):
            response += f"{i}. @{username if username else 'anonymous'} - {score} очков\n"

        bot.send_message(
            message.chat.id,
            response,
            reply_markup=main_menu()
        )
    except sqlite3.Error as e:
        print(f"Ошибка БД: {e}")
        bot.send_message(message.chat.id, "Ошибка при получении топа игроков")


def about(message):
    bot.send_message(
        message.chat.id,
        "🤖 Бот-викторина v1.0\n\n"
        "Доступные тесты:\n"
        f"- Математика: {len(QUESTIONS['math'])} вопросов\n"
        f"- Информатика: {len(QUESTIONS['cs'])} вопросов\n"
        f"- История: {len(QUESTIONS['history'])} вопросов\n\n"
        "Автор: @your_username",
        reply_markup=main_menu()
    )


if __name__ == '__main__':
    print("Бот запущен! 🚀")
    try:
        bot.polling(none_stop=True)
    except Exception as e:
        print(f"Ошибка бота: {e}")
    finally:
        conn.close()