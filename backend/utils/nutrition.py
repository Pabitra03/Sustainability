import re


FOOD_FACTS = {
    "roti": {
        "aliases": ["roti", "chapati", "phulka"],
        "calories": 110,
        "protein_g": 3,
        "carbs_g": 22,
        "fat_g": 1,
        "fiber_g": 3,
        "default_qty": 1,
        "unit": "piece",
    },
    "paratha": {
        "aliases": ["paratha", "parantha"],
        "calories": 260,
        "protein_g": 6,
        "carbs_g": 34,
        "fat_g": 11,
        "fiber_g": 4,
        "default_qty": 1,
        "unit": "piece",
    },
    "rice": {
        "aliases": ["rice", "chawal", "pulao"],
        "calories": 210,
        "protein_g": 4,
        "carbs_g": 45,
        "fat_g": 1,
        "fiber_g": 1,
        "default_qty": 1,
        "unit": "plate",
    },
    "dal": {
        "aliases": ["dal", "daal", "lentil", "lentils", "sambar"],
        "calories": 180,
        "protein_g": 12,
        "carbs_g": 28,
        "fat_g": 3,
        "fiber_g": 8,
        "default_qty": 1,
        "unit": "bowl",
    },
    "rajma": {
        "aliases": ["rajma", "kidney bean", "kidney beans"],
        "calories": 220,
        "protein_g": 13,
        "carbs_g": 36,
        "fat_g": 2,
        "fiber_g": 10,
        "default_qty": 1,
        "unit": "bowl",
    },
    "chana": {
        "aliases": ["chana", "chole", "chickpea", "chickpeas"],
        "calories": 230,
        "protein_g": 12,
        "carbs_g": 38,
        "fat_g": 4,
        "fiber_g": 10,
        "default_qty": 1,
        "unit": "bowl",
    },
    "sabzi": {
        "aliases": ["sabzi", "sabji", "subzi", "veg curry", "vegetable curry", "mix veg"],
        "calories": 140,
        "protein_g": 4,
        "carbs_g": 18,
        "fat_g": 6,
        "fiber_g": 6,
        "default_qty": 1,
        "unit": "bowl",
    },
    "egg": {
        "aliases": ["egg", "eggs", "omelette", "anda", "bhurji"],
        "calories": 78,
        "protein_g": 6,
        "carbs_g": 1,
        "fat_g": 5,
        "fiber_g": 0,
        "default_qty": 1,
        "unit": "piece",
    },
    "chicken": {
        "aliases": ["chicken", "chicken curry", "chicken masala"],
        "calories": 220,
        "protein_g": 28,
        "carbs_g": 0,
        "fat_g": 9,
        "fiber_g": 0,
        "default_qty": 100,
        "unit": "g",
    },
    "fish": {
        "aliases": ["fish", "fish curry"],
        "calories": 180,
        "protein_g": 24,
        "carbs_g": 0,
        "fat_g": 8,
        "fiber_g": 0,
        "default_qty": 100,
        "unit": "g",
    },
    "paneer": {
        "aliases": ["paneer"],
        "calories": 265,
        "protein_g": 18,
        "carbs_g": 6,
        "fat_g": 20,
        "fiber_g": 0,
        "default_qty": 100,
        "unit": "g",
    },
    "soya": {
        "aliases": ["soya", "soy chunk", "soy chunks", "soya chunk", "soya chunks"],
        "calories": 170,
        "protein_g": 26,
        "carbs_g": 15,
        "fat_g": 1,
        "fiber_g": 6,
        "default_qty": 50,
        "unit": "g",
    },
    "curd": {
        "aliases": ["curd", "dahi", "yogurt"],
        "calories": 100,
        "protein_g": 5,
        "carbs_g": 7,
        "fat_g": 5,
        "fiber_g": 0,
        "default_qty": 100,
        "unit": "g",
    },
    "milk": {
        "aliases": ["milk"],
        "calories": 150,
        "protein_g": 8,
        "carbs_g": 12,
        "fat_g": 8,
        "fiber_g": 0,
        "default_qty": 200,
        "unit": "ml",
    },
    "sprouts": {
        "aliases": ["sprout", "sprouts", "sprouted moong"],
        "calories": 80,
        "protein_g": 6,
        "carbs_g": 13,
        "fat_g": 1,
        "fiber_g": 4,
        "default_qty": 100,
        "unit": "g",
    },
    "salad": {
        "aliases": ["salad", "kachumber"],
        "calories": 40,
        "protein_g": 2,
        "carbs_g": 8,
        "fat_g": 0,
        "fiber_g": 3,
        "default_qty": 1,
        "unit": "plate",
    },
    "poha": {
        "aliases": ["poha"],
        "calories": 250,
        "protein_g": 6,
        "carbs_g": 45,
        "fat_g": 6,
        "fiber_g": 3,
        "default_qty": 1,
        "unit": "plate",
    },
    "upma": {
        "aliases": ["upma"],
        "calories": 260,
        "protein_g": 7,
        "carbs_g": 44,
        "fat_g": 7,
        "fiber_g": 4,
        "default_qty": 1,
        "unit": "plate",
    },
    "idli": {
        "aliases": ["idli", "idli sambar"],
        "calories": 60,
        "protein_g": 2,
        "carbs_g": 12,
        "fat_g": 0.5,
        "fiber_g": 0.5,
        "default_qty": 1,
        "unit": "piece",
    },
    "dosa": {
        "aliases": ["dosa"],
        "calories": 170,
        "protein_g": 4,
        "carbs_g": 28,
        "fat_g": 5,
        "fiber_g": 2,
        "default_qty": 1,
        "unit": "piece",
    },
    "fruit": {
        "aliases": ["fruit", "banana", "apple"],
        "calories": 95,
        "protein_g": 1,
        "carbs_g": 24,
        "fat_g": 0,
        "fiber_g": 3,
        "default_qty": 1,
        "unit": "piece",
    },
    "biryani": {
        "aliases": ["biryani"],
        "calories": 420,
        "protein_g": 18,
        "carbs_g": 55,
        "fat_g": 14,
        "fiber_g": 3,
        "default_qty": 1,
        "unit": "plate",
    },
    "fried snack": {
        "aliases": ["fried", "pakora", "samosa", "puri", "poori"],
        "calories": 300,
        "protein_g": 5,
        "carbs_g": 35,
        "fat_g": 15,
        "fiber_g": 1,
        "default_qty": 1,
        "unit": "serving",
    },
    "noodles": {
        "aliases": ["noodles", "maggi"],
        "calories": 360,
        "protein_g": 8,
        "carbs_g": 52,
        "fat_g": 14,
        "fiber_g": 3,
        "default_qty": 1,
        "unit": "plate",
    },
    "tea": {
        "aliases": ["tea", "chai"],
        "calories": 80,
        "protein_g": 2,
        "carbs_g": 12,
        "fat_g": 3,
        "fiber_g": 0,
        "default_qty": 1,
        "unit": "cup",
    },
}


NUMBER_WORDS = {
    "half": 0.5,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
}


def _word_boundary(alias):
    return r"(?<![a-z])" + re.escape(alias) + r"(?![a-z])"


def _quantity_from_text(segment, alias, facts, only_match):
    alias_match = re.search(_word_boundary(alias), segment)
    if not alias_match:
        return 1.0

    window = segment[max(0, alias_match.start() - 18):alias_match.end() + 18]
    number_pattern = r"(\d+(?:\.\d+)?)\s*(g|gm|gram|grams|ml|milliliter|milliliters|bowl|katori|plate|cup|piece|pieces|pc|pcs)?"
    candidates = re.findall(number_pattern, window)

    if not candidates and only_match:
        candidates = re.findall(number_pattern, segment)

    if candidates:
        value = float(candidates[0][0])
        unit = (candidates[0][1] or "").lower()
        if unit in ["g", "gm", "gram", "grams", "ml", "milliliter", "milliliters"] and facts["unit"] in ["g", "ml"]:
            return max(0.1, value / facts["default_qty"])
        return max(0.1, value)

    for word, value in NUMBER_WORDS.items():
        if re.search(rf"\b{word}\b", window):
            return value

    if re.search(r"\b(extra|double)\b", window):
        return 1.5

    return 1.0


def estimate_menu_food(items_text):
    text = (items_text or "").lower()
    text = re.sub(r"[/\n;]", ",", text)
    segments = [part.strip() for part in re.split(r",|\+|&|\band\b|\bwith\b", text) if part.strip()]
    totals = {"calories": 0, "protein_g": 0, "carbs_g": 0, "fat_g": 0, "fiber_g": 0}
    matches = []

    for segment in segments:
        if re.search(r"\b(no|not|without|except|zero|none)\b", segment):
            continue

        found = []
        for key, facts in FOOD_FACTS.items():
            alias = next((name for name in facts["aliases"] if re.search(_word_boundary(name), segment)), None)
            if alias:
                found.append((key, alias, facts))

        for key, alias, facts in found:
            scale = _quantity_from_text(segment, alias, facts, len(found) == 1)
            matches.append(key)
            for metric in totals.keys():
                totals[metric] += facts[metric] * scale

    if not matches and text.strip():
        words = [word for word in re.sub(r"[^a-z0-9. ]", " ", text).split() if len(word) > 2]
        portions = max(1, min(3, len(words) // 2 or 1))
        totals = {
            "calories": 180 * portions,
            "protein_g": 6 * portions,
            "carbs_g": 28 * portions,
            "fat_g": 5 * portions,
            "fiber_g": 3 * portions,
        }

    return totals, sorted(set(matches))
