import json, random, os

_dir = os.path.dirname(os.path.abspath(__file__))

with open(os.path.join(_dir, 'questions.json'), encoding='utf-8') as f:
    ALL_QUESTIONS = json.load(f)

with open(os.path.join(_dir, 'vocab.json'), encoding='utf-8') as f:
    ALL_VOCAB = json.load(f)


def get_daily_question(seed: int) -> dict:
    rng = random.Random(seed)
    return rng.choice(ALL_QUESTIONS)


def get_random_question(subject: str = None) -> dict:
    pool = ALL_QUESTIONS
    if subject == 'math':
        pool = [q for q in ALL_QUESTIONS if q['s'] == 'm']
    elif subject == 'reading':
        pool = [q for q in ALL_QUESTIONS if q['s'] == 'r']
    if not pool:
        pool = ALL_QUESTIONS
    return random.choice(pool)


def get_daily_word(seed: int) -> dict:
    rng = random.Random(seed + 9999)
    return rng.choice(ALL_VOCAB)


def format_question(q: dict) -> tuple[str, list[str]]:
    subject_icon = "📐" if q['s'] == 'm' else "📖"
    topic = q.get('t', 'SAT')  # fallback if no topic
    text = (
        f"{subject_icon} <b>{topic.upper()}</b>\n\n"
        f"{q['q']}"
    )
    choices = q['c']
    return text, choices
