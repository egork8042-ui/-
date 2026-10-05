import os
import re
import sqlite3
import asyncio
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

TOKEN = os.environ.get("BOT_TOKEN", "").strip()
TZ = ZoneInfo(os.environ.get("TZ", "Asia/Tomsk"))
DB_PATH = os.environ.get("DB_PATH", "iron_schedule.db")
REMINDER_MINUTES = 15

SCHEDULE = {
    0: ["Разговоры о важном", "Алгебра", "Русский язык", "Физика", "Русский язык", "Химия", "География"],
    1: ["Литература", "Английский язык", "Геометрия", "Физкультура", "Биология", "История", "ОБЗР"],
    2: ["Информатика / Труд", "Алгебра", "Алгебра", "Английский язык", "Информатика / Труд", "Физика", "Литература"],
    3: ["Биология", "Химия", "Геометрия", "Литература", "История", "Английский язык", "Россия — мои горизонты"],
    4: ["География", "Физика", "Физкультура", "Вероятность", "Обществознание", "Русский язык", "Русский язык"],
}
DEFAULT_TIMES = ["08:30", "09:25", "10:20", "11:25", "12:20", "13:15", "14:10"]
DAYS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]

bot = Bot(TOKEN)
dp = Dispatcher()


def db():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def init_db():
    con = db()
    con.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        chat_id INTEGER PRIMARY KEY,
        first_name TEXT,
        timezone TEXT DEFAULT 'Asia/Tomsk',
        morning_enabled INTEGER DEFAULT 1,
        lesson_enabled INTEGER DEFAULT 1,
        created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS lesson_times (
        chat_id INTEGER NOT NULL,
        lesson INTEGER NOT NULL,
        time TEXT NOT NULL,
        PRIMARY KEY(chat_id, lesson)
    );
    CREATE TABLE IF NOT EXISTS homework (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id INTEGER NOT NULL,
        subject TEXT NOT NULL,
        text TEXT NOT NULL,
        due TEXT,
        done INTEGER DEFAULT 0,
        created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS tests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id INTEGER NOT NULL,
        subject TEXT NOT NULL,
        text TEXT NOT NULL,
        when_at TEXT NOT NULL,
        done INTEGER DEFAULT 0,
        created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS reminders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id INTEGER NOT NULL,
        text TEXT NOT NULL,
        when_at TEXT NOT NULL,
        sent INTEGER DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS sent_marks (
        chat_id INTEGER NOT NULL,
        mark TEXT NOT NULL,
        PRIMARY KEY(chat_id, mark)
    );
    """)
    con.commit()
    con.close()


def ensure_user(message: Message):
    con = db()
    now = datetime.now(TZ).isoformat()
    con.execute("INSERT OR IGNORE INTO users(chat_id, first_name, created_at) VALUES (?, ?, ?)",
                (message.chat.id, message.from_user.first_name or "", now))
    for i, t in enumerate(DEFAULT_TIMES, 1):
        con.execute("INSERT OR IGNORE INTO lesson_times(chat_id, lesson, time) VALUES (?, ?, ?)",
                    (message.chat.id, i, t))
    con.commit(); con.close()


def get_times(chat_id):
    con = db()
    rows = con.execute("SELECT lesson,time FROM lesson_times WHERE chat_id=? ORDER BY lesson", (chat_id,)).fetchall()
    con.close()
    return [r[1] for r in rows] if len(rows) == 7 else DEFAULT_TIMES


def set_times(chat_id, times):
    con = db()
    for i, t in enumerate(times, 1):
        con.execute("INSERT OR REPLACE INTO lesson_times(chat_id, lesson, time) VALUES (?, ?, ?)", (chat_id, i, t))
    con.commit(); con.close()


def main_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📚 Сегодня", callback_data="today"), InlineKeyboardButton(text="📅 Неделя", callback_data="week")],
        [InlineKeyboardButton(text="📝 Домашка", callback_data="homework"), InlineKeyboardButton(text="🧪 Контрольные", callback_data="tests")],
        [InlineKeyboardButton(text="⏰ Напоминание", callback_data="help_reminder"), InlineKeyboardButton(text="🔔 Настройки", callback_data="settings")],
        [InlineKeyboardButton(text="🕐 Время уроков", callback_data="times")]
    ])


def format_day(d: date, chat_id: int):
    if d.weekday() >= 5:
        return f"{DAYS[d.weekday()]} {d.strftime('%d.%m')} — выходной"
    times = get_times(chat_id)
    lines = [f"<b>{DAYS[d.weekday()]} {d.strftime('%d.%m')}</b>"]
    for i, subject in enumerate(SCHEDULE[d.weekday()], 1):
        lines.append(f"{i}. <b>{times[i-1]}</b> — {subject}")
    return "\n".join(lines)


def parse_dt(s: str):
    for fmt in ("%Y-%m-%d %H:%M", "%d.%m.%Y %H:%M", "%d.%m %H:%M"):
        try:
            dt = datetime.strptime(s, fmt)
            if fmt == "%d.%m %H:%M":
                dt = dt.replace(year=datetime.now(TZ).year)
            return dt.replace(tzinfo=TZ)
        except ValueError:
            pass
    return None


def valid_time(t):
    return bool(re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", t))


@dp.message(Command("start"))
async def start(message: Message):
    ensure_user(message)
    await message.answer(
        "<b>IRON SCHEDULE</b> ⚡\n\n"
        "Твой школьный бот для 9Б.\n"
        "🌅 Расписание каждый будний день в 07:00\n"
        "🔔 Напоминание за 15 минут до урока\n"
        "📝 Домашка\n🧪 Контрольные\n📅 Неделя\n\n"
        "Часовой пояс: Asia/Tomsk",
        reply_markup=main_kb())


@dp.message(Command("today"))
async def today(message: Message):
    ensure_user(message)
    await message.answer(format_day(datetime.now(TZ).date(), message.chat.id), reply_markup=main_kb())


@dp.message(Command("week"))
async def week(message: Message):
    ensure_user(message)
    today_d = datetime.now(TZ).date()
    monday = today_d - timedelta(days=today_d.weekday())
    await message.answer("<b>📅 НЕДЕЛЯ 9Б</b>\n\n" + "\n\n".join(format_day(monday + timedelta(days=i), message.chat.id) for i in range(5)))


@dp.message(Command("times"))
async def times_cmd(message: Message):
    ensure_user(message)
    values = message.text.split()[1:]
    if not values:
        await message.answer(
            "<b>🕐 Время уроков</b>\n\n"
            "Первый урок по умолчанию: 08:30.\n"
            "Чтобы задать все 7 начал, отправь одной строкой:\n\n"
            "<code>/times 08:30 09:25 10:20 11:25 12:20 13:15 14:10</code>\n\n"
            "Напоминание приходит за 15 минут до каждого времени.")
        return
    if len(values) != 7 or not all(valid_time(x) for x in values):
        await message.answer("Нужно ровно 7 времён в формате HH:MM.\nПример:\n<code>/times 08:30 09:25 10:20 11:25 12:20 13:15 14:10</code>")
        return
    set_times(message.chat.id, values)
    await message.answer("✅ Время 7 уроков сохранено.\n\n" + "\n".join(f"{i}. {t}" for i,t in enumerate(values,1)))


@dp.message(Command("homework"))
async def homework(message: Message):
    ensure_user(message)
    con = db(); rows = con.execute("SELECT id,subject,text,due FROM homework WHERE chat_id=? AND done=0 ORDER BY COALESCE(due,'9999')", (message.chat.id,)).fetchall(); con.close()
    if not rows:
        await message.answer("📝 Домашки пока нет.")
        return
    lines = ["<b>📝 ДОМАШКА</b>"]
    for r in rows:
        due = f" · до {r['due']}" if r['due'] else ""
        lines.append(f"\n#{r['id']} <b>{r['subject']}</b>{due}\n{r['text']}")
    lines.append("\nДобавить: <code>/addhw Предмет | задание | 2026-10-06</code>\nЗакрыть: <code>/donehw ID</code>")
    await message.answer("\n".join(lines))


@dp.message(Command("addhw"))
async def addhw(message: Message):
    ensure_user(message)
    raw = message.text.partition(" ")[2].strip()
    parts = [p.strip() for p in raw.split("|")]
    if len(parts) < 2:
        await message.answer("Формат:\n<code>/addhw Алгебра | №123, 124 | 2026-10-07</code>")
        return
    subject, text_ = parts[0], parts[1]
    due = parts[2] if len(parts) > 2 else None
    con = db(); con.execute("INSERT INTO homework(chat_id,subject,text,due,created_at) VALUES (?,?,?,?,?)", (message.chat.id,subject,text_,due,datetime.now(TZ).isoformat())); con.commit(); con.close()
    await message.answer(f"✅ Домашка добавлена: <b>{subject}</b>\n{text_}")


@dp.message(Command("donehw"))
async def donehw(message: Message):
    try: ident = int(message.text.split(maxsplit=1)[1])
    except Exception:
        await message.answer("Укажи ID: <code>/donehw 3</code>"); return
    con=db(); cur=con.execute("UPDATE homework SET done=1 WHERE id=? AND chat_id=?",(ident,message.chat.id)); con.commit(); con.close()
    await message.answer("✅ Готово." if cur.rowcount else "Не найдено.")


@dp.message(Command("tests"))
async def tests(message: Message):
    ensure_user(message)
    con=db(); rows=con.execute("SELECT id,subject,text,when_at FROM tests WHERE chat_id=? AND done=0 ORDER BY when_at",(message.chat.id,)).fetchall(); con.close()
    if not rows:
        await message.answer("🧪 Контрольных пока нет."); return
    lines=["<b>🧪 КОНТРОЛЬНЫЕ</b>"]
    for r in rows: lines.append(f"\n#{r['id']} <b>{r['subject']}</b> — {r['when_at']}\n{r['text']}")
    lines.append("\nДобавить: <code>/addtest Предмет | дата-время | что учить</code>")
    await message.answer("\n".join(lines))


@dp.message(Command("addtest"))
async def addtest(message: Message):
    ensure_user(message)
    raw=message.text.partition(" ")[2].strip(); parts=[p.strip() for p in raw.split("|")]
    if len(parts)<3:
        await message.answer("Формат: <code>/addtest Алгебра | 2026-10-10 09:00 | Параграф 5</code>"); return
    dt=parse_dt(parts[1])
    if not dt: await message.answer("Не понял дату. Используй YYYY-MM-DD HH:MM."); return
    con=db(); con.execute("INSERT INTO tests(chat_id,subject,text,when_at,created_at) VALUES (?,?,?,?,?)",(message.chat.id,parts[0],parts[2],dt.isoformat(),datetime.now(TZ).isoformat())); con.commit(); con.close()
    await message.answer(f"🧪 Контрольная добавлена: <b>{parts[0]}</b>\n{dt.strftime('%d.%m.%Y %H:%M')}")


@dp.message(Command("reminder"))
async def reminder(message: Message):
    ensure_user(message)
    raw=message.text.partition(" ")[2].strip()
    m=re.match(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2})\s+(.+)$", raw)
    if not m:
        await message.answer("Формат: <code>/reminder 2026-10-06 19:00 Сделать домашку</code>"); return
    dt=parse_dt(m.group(1)); text_=m.group(2)
    if not dt: await message.answer("Неверная дата."); return
    if dt <= datetime.now(TZ): await message.answer("⛔ Время уже прошло."); return
    con=db(); con.execute("INSERT INTO reminders(chat_id,text,when_at) VALUES (?,?,?)",(message.chat.id,text_,dt.isoformat())); con.commit(); con.close()
    await message.answer(f"⏰ Напоминание поставлено на <b>{dt.strftime('%d.%m.%Y %H:%M')}</b>\n{text_}")


@dp.message(Command("reminders"))
async def reminders(message: Message):
    ensure_user(message)
    con=db(); rows=con.execute("SELECT id,text,when_at FROM reminders WHERE chat_id=? AND sent=0 ORDER BY when_at",(message.chat.id,)).fetchall(); con.close()
    if not rows: await message.answer("⏰ Активных напоминаний нет."); return
    lines=["<b>⏰ НАПОМИНАНИЯ</b>"]
    for r in rows: lines.append(f"#{r['id']} · {datetime.fromisoformat(r['when_at']).astimezone(TZ).strftime('%d.%m %H:%M')} — {r['text']}")
    lines.append("\nУдалить: <code>/delrem ID</code>")
    await message.answer("\n".join(lines))


@dp.message(Command("delrem"))
async def delrem(message: Message):
    try: ident=int(message.text.split(maxsplit=1)[1])
    except: await message.answer("<code>/delrem 3</code>"); return
    con=db(); cur=con.execute("DELETE FROM reminders WHERE id=? AND chat_id=?",(ident,message.chat.id)); con.commit(); con.close()
    await message.answer("🗑️ Удалено." if cur.rowcount else "Не найдено.")


@dp.message(Command("help"))
async def help_cmd(message: Message):
    await message.answer("""<b>Команды IRON SCHEDULE</b>\n\n/start — меню\n/today — сегодня\n/week — неделя\n/times — настроить звонки\n/homework — домашка\n/addhw — добавить домашку\n/donehw — закрыть домашку\n/tests — контрольные\n/addtest — добавить контрольную\n/reminder — добавить напоминание\n/reminders — список напоминаний\n/delrem — удалить напоминание\n""")


@dp.callback_query(F.data=="today")
async def cb_today(c: CallbackQuery):
    await c.answer(); await c.message.answer(format_day(datetime.now(TZ).date(), c.message.chat.id))

@dp.callback_query(F.data=="week")
async def cb_week(c: CallbackQuery):
    await c.answer(); d=datetime.now(TZ).date(); mon=d-timedelta(days=d.weekday()); await c.message.answer("<b>📅 НЕДЕЛЯ 9Б</b>\n\n"+"\n\n".join(format_day(mon+timedelta(days=i),c.message.chat.id) for i in range(5)))

@dp.callback_query(F.data=="homework")
async def cb_hw(c: CallbackQuery):
    await c.answer()
    cid=c.from_user.id
    con=db(); rows=con.execute("SELECT id,subject,text,due FROM homework WHERE chat_id=? AND done=0 ORDER BY COALESCE(due,'9999')",(cid,)).fetchall(); con.close()
    if not rows:
        await c.message.answer("📝 Домашки пока нет."); return
    lines=["<b>📝 ДОМАШКА</b>"]
    for r in rows:
        due=f" · до {r['due']}" if r['due'] else ""
        lines.append(f"\n#{r['id']} <b>{r['subject']}</b>{due}\n{r['text']}")
    lines.append("\nДобавить: <code>/addhw Предмет | задание | 2026-10-06</code>\nЗакрыть: <code>/donehw ID</code>")
    await c.message.answer("\n".join(lines))
@dp.callback_query(F.data=="tests")
async def cb_tests(c: CallbackQuery):
    await c.answer()
    cid=c.from_user.id
    con=db(); rows=con.execute("SELECT id,subject,text,when_at FROM tests WHERE chat_id=? AND done=0 ORDER BY when_at",(cid,)).fetchall(); con.close()
    if not rows:
        await c.message.answer("🧪 Контрольных пока нет."); return
    lines=["<b>🧪 КОНТРОЛЬНЫЕ</b>"]
    for r in rows: lines.append(f"\n#{r['id']} <b>{r['subject']}</b> — {r['when_at']}\n{r['text']}")
    lines.append("\nДобавить: <code>/addtest Предмет | дата-время | что учить</code>")
    await c.message.answer("\n".join(lines))
@dp.callback_query(F.data=="help_reminder")
async def cb_rem(c: CallbackQuery): await c.answer(); await c.message.answer("⏰ Добавить напоминание:\n<code>/reminder 2026-10-06 19:00 Сделать домашку</code>\n\nСписок: /reminders")
@dp.callback_query(F.data=="times")
async def cb_times(c: CallbackQuery):
    await c.answer()
    await c.message.answer("<b>🕐 Время уроков</b>\n\nТекущее: "+" ".join(get_times(c.from_user.id))+"\n\nИзменить: <code>/times 08:30 09:25 10:20 11:25 12:20 13:15 14:10</code>")
@dp.callback_query(F.data=="settings")
async def cb_settings(c: CallbackQuery): await c.answer(); await c.message.answer("🔔 Утреннее сообщение: 07:00\n🔔 Уроки: за 15 минут\n🌍 Часовой пояс: Asia/Tomsk\n\nВремя уроков: /times")


async def scheduler():
    while True:
        now=datetime.now(TZ).replace(second=0,microsecond=0)
        con=db()
        users=con.execute("SELECT chat_id,morning_enabled,lesson_enabled FROM users").fetchall()
        for u in users:
            cid=u[0]
            # Morning schedule, weekdays at 07:00.
            mark=f"morning:{now.date().isoformat()}"
            if now.weekday()<5 and now.hour==7 and now.minute==0 and u[1]:
                exists=con.execute("SELECT 1 FROM sent_marks WHERE chat_id=? AND mark=?",(cid,mark)).fetchone()
                if not exists:
                    await bot.send_message(cid,"🌅 <b>Доброе утро, 9Б!</b>\n\n"+format_day(now.date(),cid),reply_markup=main_kb())
                    con.execute("INSERT INTO sent_marks(chat_id,mark) VALUES (?,?)",(cid,mark))
            # Lesson reminders 15 minutes before each lesson.
            if now.weekday()<5 and u[2]:
                times=get_times(cid)
                for i,t in enumerate(times,1):
                    h,m=map(int,t.split(":")); target=now.replace(hour=h,minute=m)
                    if target-timedelta(minutes=REMINDER_MINUTES)==now:
                        mark=f"lesson:{now.date().isoformat()}:{i}"
                        exists=con.execute("SELECT 1 FROM sent_marks WHERE chat_id=? AND mark=?",(cid,mark)).fetchone()
                        if not exists:
                            subject=SCHEDULE[now.weekday()][i-1]
                            await bot.send_message(cid,f"⏰ <b>Через 15 минут урок {i}</b>\n📚 {subject}\n🕐 Начало: {t}")
                            con.execute("INSERT INTO sent_marks(chat_id,mark) VALUES (?,?)",(cid,mark))
            # Custom reminders.
            rows=con.execute("SELECT id,text,when_at FROM reminders WHERE chat_id=? AND sent=0",(cid,)).fetchall()
            for r in rows:
                try: dt=datetime.fromisoformat(r[2]).astimezone(TZ).replace(second=0,microsecond=0)
                except: continue
                if dt<=now:
                    await bot.send_message(cid,f"⏰ <b>НАПОМИНАНИЕ</b>\n{r[1]}")
                    con.execute("UPDATE reminders SET sent=1 WHERE id=?",(r[0],))
        con.commit(); con.close()
        await asyncio.sleep(60)


async def main():
    if not TOKEN:
        raise RuntimeError("BOT_TOKEN is not set")
    init_db()
    asyncio.create_task(scheduler())
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())

if __name__ == "__main__":
    asyncio.run(main())
