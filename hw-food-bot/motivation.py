import random
from pathlib import Path

with Path("hw-food-bot/motivation.txt").open("r") as f:
    motivation_lines = [line.strip() for line in f.readlines() if line]


def get_random_quote() -> str:
    return random.choice(motivation_lines)
