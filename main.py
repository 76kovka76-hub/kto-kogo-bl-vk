import os
import re
import json
import html
import hashlib
import random
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo

VK_TOKEN = os.environ["VK_ACCESS_TOKEN"]
GROUP_ID = int(os.environ.get("VK_GROUP_ID", "79887216"))
TZ = ZoneInfo("Europe/Moscow")
HISTORY_FILE = "post_history.json"
MAX_AGE_HOURS = 48
POSTS_PER_DAY = 25

FEEDS = [
    ("MMA", "https://news.google.com/rss/search?q=UFC+OR+MMA+OR+%D1%81%D0%BC%D0%B5%D1%88%D0%B0%D0%BD%D0%BD%D1%8B%D0%B5+%D0%B5%D0%B4%D0%B8%D0%BD%D0%BE%D0%B1%D0%BE%D1%80%D1%81%D1%82%D0%B2%D0%B0&hl=ru&gl=RU&ceid=RU:ru"),
    ("Бокс", "https://news.google.com/rss/search?q=%D0%B1%D0%BE%D0%BA%D1%81+OR+%D0%B1%D0%BE%D0%BA%D1%81%D0%B5%D1%80+OR+%D1%87%D0%B5%D0%BC%D0%BF%D0%B8%D0%BE%D0%BD%D1%81%D0%BA%D0%B8%D0%B9+%D0%B1%D0%BE%D0%B9&hl=ru&gl=RU&ceid=RU:ru"),
    ("Борьба", "https://news.google.com/rss/search?q=%D0%B2%D0%BE%D0%BB%D1%8C%D0%BD%D0%B0%D1%8F+%D0%B1%D0%BE%D1%80%D1%8C%D0%B1%D0%B0+OR+%D0%B3%D1%80%D0%B5%D0%BA%D0%BE-%D1%80%D0%B8%D0%BC%D1%81%D0%BA%D0%B0%D1%8F+OR+%D0%B4%D0%B6%D0%B8%D1%83%D0%B4%D0%B6%D0%B8%D1%82%D1%81%D1%83&hl=ru&gl=RU&ceid=RU:ru"),
]

PROMO = re.compile(r"\b(промокод|скидк\w*|купить билет|билеты на|реклама|партн[её]рск\w*|розыгрыш|мерч|магазин|ставк\w*|букмекер|казино|подписывайтесь|регистрируйтес)\b", re.I)
NOISE = re.compile(r"\s+")
TAGS = {
    "MMA": ["#ММА", "#UFC", "#Единоборства", "#БойцовскийКлуб", "#НовостиММА", "#Октагон", "#Бой", "#Нокаут", "#Боец", "#СмешанныеЕдиноборства", "#MMAnews", "#UFCnews", "#FightNight", "#БойцовскийМир", "#Арена", "#ТитульныйБой", "#Грэпплинг", "#Самбо", "#Борьба", "#Спорт"],
    "Бокс": ["#Бокс", "#ПрофессиональныйБокс", "#Ринг", "#НовостиБокса", "#Нокаут", "#Единоборства", "#Бой", "#Боксёр", "#Чемпион", "#Титул", "#Поединок", "#БоксерскийМир", "#ТяжёлыйВес", "#ЛёгкийВес", "#БоксСегодня", "#Спорт", "#Арена", "#Раунд", "#Победа", "#БойцовскийМир"],
    "Борьба": ["#Борьба", "#ВольнаяБорьба", "#ГрекоРимскаяБорьба", "#Единоборства", "#Спорт", "#НовостиСпорта", "#Грэпплинг", "#ДжиуДжитсу", "#Самбо", "#Ковёр", "#Схватка", "#Чемпионат", "#Борец", "#Победа", "#Турнир", "#БойцовскийМир", "#СпортивнаяБорьба", "#Захват", "#Финал", "#Арена"],
}

def clean(value):
    value = html.unescape(re.sub(r"<[^>]+>", " ", value or ""))
    return NOISE.sub(" ", value).strip()

def load_history():
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            data.setdefault("posted", [])
            data.setdefault("last_slot", "")
            return data
    except (FileNotFoundError, json.JSONDecodeError):
        return {"posted": [], "last_slot": ""}

def save_history(data):
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def parse_date(item):
    raw = item.findtext("pubDate")
    if not raw:
        return datetime.now(timezone.utc)
    try:
        dt = parsedate_to_datetime(raw)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return datetime.now(timezone.utc)

def fetch_feed(category, url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; KtoKogoNewsBot/1.0)"})
    with urllib.request.urlopen(req, timeout=25) as response:
        root = ET.fromstring(response.read())
    items = []
    for item in root.findall(".//item"):
        title = clean(item.findtext("title"))
        desc = clean(item.findtext("description"))
        link = (item.findtext("link") or "").strip()
        published = parse_date(item)
        if not title or not link or PROMO.search(title + " " + desc):
            continue
        age = datetime.now(timezone.utc) - published
        if age < timedelta(minutes=-10) or age > timedelta(hours=MAX_AGE_HOURS):
            continue
        items.append({"category": category, "title": title, "desc": desc, "link": link, "published": published.isoformat()})
    return items

def summarize(item):
    title = item["title"].strip().rstrip(".!?")
    desc = item["desc"].strip()
    if desc and len(desc) > 35 and desc.lower() not in title.lower():
        lead = re.split(r"(?<=[.!?])\s+", desc)[0].strip()
        lead = re.sub(r"\s*[-–|]\s*[^-–|]{2,50}$", "", lead).strip()
        sentence = lead if 45 <= len(lead) <= 220 else title
    else:
        sentence = title
    sentence = sentence[:260].rstrip(" ,;:-")
    if not sentence.endswith((".", "!", "?")):
        sentence += "."
    if re.search(r"слух|инсайд|может подписать|возможно", sentence, re.I):
        sentence = "Появилась неподтверждённая информация: " + sentence[0].lower() + sentence[1:]
    return sentence

def make_post(item, history):
    pool = TAGS[item["category"]][:]
    recent_tags = {tag for entry in history["posted"][-25:] for tag in entry.get("tags", [])}
    available = [tag for tag in pool if tag not in recent_tags]
    if len(available) < 3:
        available = pool
    rng = random.Random(hashlib.sha256(item["link"].encode()).hexdigest())
    rng.shuffle(available)
    selected = available[:3]

    reaction = {
        "MMA": ["Вот это уже интересно, блядь!", "В октагоне спокойно не бывает.", "Бойцовский мир снова шумит."],
        "Бокс": ["Ринг опять подкинул поводы для разговоров.", "В боксе скучать не дают, блядь.", "Вот это поворот в мире бокса."],
        "Борьба": ["На ковре тоже жарко.", "Борцовский мир держит в напряжении.", "Вот это новости с ковра, блядь."],
    }[item["category"]]
    text = summarize(item) + " " + rng.choice(reaction)
    return text + "\n\nИсточник: " + item["link"] + "\n\n" + " ".join(selected), selected

def vk_post(message):
    import urllib.parse
    data = urllib.parse.urlencode({
        "access_token": VK_TOKEN,
        "v": "5.199",
        "owner_id": -GROUP_ID,
        "from_group": 1,
        "message": message,
    }).encode()
    req = urllib.request.Request("https://api.vk.com/method/wall.post", data=data)
    with urllib.request.urlopen(req, timeout=30) as response:
        result = json.loads(response.read().decode("utf-8"))
    if "error" in result:
        raise RuntimeError(result["error"].get("error_msg", str(result["error"])))
    return result["response"]["post_id"]

def main():
    now = datetime.now(TZ)
    minutes_today = now.hour * 60 + now.minute
    slot_index = (minutes_today * POSTS_PER_DAY) // 1440
    slot = f"{now.date()}-{slot_index}"
    history = load_history()
    if history.get("last_slot") == slot:
        print("Слот уже обработан.")
        return

    # Safety cap: never publish more than 25 posts in one Moscow calendar day.
    today_count = sum(
        1 for entry in history["posted"]
        if entry.get("posted_at", "").startswith(str(now.date()))
    )
    if today_count >= POSTS_PER_DAY:
        print("Дневной лимит 25 публикаций уже достигнут.")
        return

    candidates = []
    for category, url in FEEDS:
        try:
            batch = fetch_feed(category, url)
            print(f"{category}: получено {len(batch)} свежих новостей")
            candidates.extend(batch)
        except Exception as exc:
            print(f"Ошибка RSS ({category}): {exc}")

    posted_links = {x["link"] for x in history["posted"]}
    candidates = [x for x in candidates if x["link"] not in posted_links]
    candidates.sort(key=lambda x: x["published"], reverse=True)
    if not candidates:
        print("Нет свежей уникальной новости — публикацию пропускаем.")
        history["last_slot"] = slot
        save_history(history)
        return

    item = candidates[0]
    message, tags = make_post(item, history)
    post_id = vk_post(message)
    history["posted"].append({
        "link": item["link"], "category": item["category"], "tags": tags,
        "post_id": post_id, "posted_at": now.isoformat(), "slot": slot,
    })
    history["posted"] = history["posted"][-1000:]
    history["last_slot"] = slot
    save_history(history)
    print(f"УСПЕХ: опубликовано ({item['category']}), post_id={post_id}, публикаций сегодня={today_count + 1}")
    print(message)

if __name__ == "__main__":
    main()
