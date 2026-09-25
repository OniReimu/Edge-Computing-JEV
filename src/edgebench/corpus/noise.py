"""Programmatic noise derivation from RQ2 clean requests with negator preservation."""
from __future__ import annotations

import random
import re
import string

from src.edgebench.contract import Case

NOISE_SEED = 20260924

NEGATORS = frozenset({
    "not",
    "no",
    "never",
    "don't",
    "dont",
    "without",
    "nobody",
    "nothing",
    "cannot",
    "can't",
    "cant",
    "won't",
    "wont",
})

QWERTY_ADJACENT: dict[str, str] = {
    "a": "qwsz",
    "b": "vghn",
    "c": "xdfv",
    "d": "serfcx",
    "e": "wsdr",
    "f": "drtgvc",
    "g": "ftyhbv",
    "h": "gyujnb",
    "i": "ujko",
    "j": "humnk",
    "k": "jmloi",
    "l": "kop",
    "m": "njk",
    "n": "bhjm",
    "o": "iklp",
    "p": "ol",
    "q": "wa",
    "r": "edft",
    "s": "awedxz",
    "t": "rfgy",
    "u": "yhji",
    "v": "cfgb",
    "w": "qase",
    "x": "zsdc",
    "y": "tghu",
    "z": "asx",
}

# Fixed 60-pair homophone mapping (symmetric, strictly zero negators)
HOMOPHONES_PAIRS = [
    ("there", "their"),
    ("their", "there"),
    ("to", "too"),
    ("too", "to"),
    ("hear", "here"),
    ("here", "hear"),
    ("see", "sea"),
    ("sea", "see"),
    ("buy", "by"),
    ("by", "buy"),
    ("for", "four"),
    ("four", "for"),
    ("one", "won"),
    ("won", "one"),
    ("right", "write"),
    ("write", "right"),
    ("weather", "whether"),
    ("whether", "weather"),
    ("break", "brake"),
    ("brake", "break"),
    ("piece", "peace"),
    ("peace", "piece"),
    ("meet", "meat"),
    ("meat", "meet"),
    ("hour", "our"),
    ("our", "hour"),
    ("son", "sun"),
    ("sun", "son"),
    ("week", "weak"),
    ("weak", "week"),
    ("mail", "male"),
    ("male", "mail"),
    ("sale", "sail"),
    ("sail", "sale"),
    ("tail", "tale"),
    ("tale", "tail"),
    ("cell", "sell"),
    ("sell", "cell"),
    ("cent", "scent"),
    ("scent", "cent"),
    ("dear", "deer"),
    ("deer", "dear"),
    ("die", "dye"),
    ("dye", "die"),
    ("fair", "fare"),
    ("fare", "fair"),
    ("flee", "flea"),
    ("flea", "flee"),
    ("flew", "flu"),
    ("flu", "flew"),
    ("flour", "flower"),
    ("flower", "flour"),
    ("heal", "heel"),
    ("heel", "heal"),
    ("hole", "whole"),
    ("whole", "hole"),
    ("idle", "idol"),
    ("idol", "idle"),
    ("night", "knight"),
    ("knight", "night"),
    ("pair", "pear"),
    ("pear", "pair"),
    ("plain", "plane"),
    ("plane", "plain"),
    ("root", "route"),
    ("route", "root"),
    ("scene", "seen"),
    ("seen", "scene"),
    ("stair", "stare"),
    ("stare", "stair"),
    ("steal", "steel"),
    ("steel", "steal"),
    ("sweet", "suite"),
    ("suite", "sweet"),
    ("waist", "waste"),
    ("waste", "waist"),
    ("wait", "weight"),
    ("weight", "wait"),
    ("ware", "wear"),
    ("wear", "ware"),
    ("way", "weigh"),
    ("weigh", "way"),
    ("wood", "would"),
    ("would", "wood"),
]
HOMOPHONE_MAP = dict(HOMOPHONES_PAIRS)


def is_negator(word: str) -> bool:
    cleaned = word.lower().strip(string.punctuation)
    return cleaned in NEGATORS


def apply_word_noise(word: str, rng: random.Random) -> str:
    """Apply one of 4 noise operations to a non-negator word."""
    if len(word) <= 1:
        return word

    op = rng.choice(["delete", "substitute", "transpose", "homophone"])
    lower_w = word.lower()

    if op == "homophone" and lower_w in HOMOPHONE_MAP:
        replacement = HOMOPHONE_MAP[lower_w]
        if word.isupper():
            return replacement.upper()
        if word.istitle():
            return replacement.capitalize()
        return replacement

    # If homophone not applicable, pick from remaining 3
    if op == "homophone":
        op = rng.choice(["delete", "substitute", "transpose"])

    if op == "delete":
        idx = rng.randint(0, len(word) - 1)
        return word[:idx] + word[idx + 1 :]

    if op == "substitute":
        idx = rng.randint(0, len(word) - 1)
        ch = word[idx].lower()
        if ch in QWERTY_ADJACENT:
            sub = rng.choice(QWERTY_ADJACENT[ch])
            sub = sub.upper() if word[idx].isupper() else sub
            return word[:idx] + sub + word[idx + 1 :]
        return word

    if op == "transpose":
        idx = rng.randint(0, len(word) - 2)
        return word[:idx] + word[idx + 1] + word[idx] + word[idx + 2 :]

    return word


def apply_noise_to_text(text: str, rng: random.Random, p: float = 0.08) -> str:
    # Tokenize by whitespace while preserving punctuation
    tokens = text.split()
    noisy_tokens: list[str] = []

    for tok in tokens:
        if is_negator(tok) or rng.random() >= p:
            noisy_tokens.append(tok)
        else:
            # Separate leading/trailing punctuation
            match = re.match(r"^([^\w]*)(.*?)([^\w]*)$", tok)
            if match:
                prefix, core, suffix = match.groups()
                if is_negator(core):
                    noisy_tokens.append(tok)
                else:
                    noisy_core = apply_word_noise(core, rng)
                    noisy_tokens.append(f"{prefix}{noisy_core}{suffix}")
            else:
                noisy_tokens.append(tok)

    result = " ".join(noisy_tokens)

    # 50% of cases: lowercase and strip punctuation (voice-transcript look)
    if rng.random() < 0.5:
        # Keep letters, numbers, spaces, and keep internal apostrophes for negators
        chars: list[str] = []
        for i, c in enumerate(result):
            if c.isalnum() or c.isspace():
                chars.append(c.lower())
            elif c == "'" and 0 < i < len(result) - 1 and result[i - 1].isalpha() and result[i + 1].isalpha():
                chars.append(c)  # keep internal apostrophes like don't, can't
            else:
                chars.append(" ")
        result = " ".join("".join(chars).split())

    return result


def derive_noise_cases(clean_cases: list[Case], seed: int = NOISE_SEED) -> list[Case]:
    sorted_clean = sorted(clean_cases, key=lambda c: c.case_id)
    rng = random.Random(seed)
    noise_cases: list[Case] = []

    for case in sorted_clean:
        noisy_text = apply_noise_to_text(case.text, rng, p=0.08)
        meta = dict(case.meta)
        meta["derived_from"] = case.case_id
        meta["derivation"] = "noise"
        meta["noise_seed"] = seed
        meta["generator"] = case.meta.get("generator", "")
        meta["verifier"] = case.meta.get("verifier", "")
        meta["generator_model"] = case.meta.get("generator_model", "")
        meta["verifier_model"] = case.meta.get("verifier_model", "")

        new_case_id = case.case_id.replace("clean", "noise")
        noise_cases.append(
            Case(
                case_id=new_case_id,
                text=noisy_text,
                fields=list(case.fields),
                service_options=case.service_options,
                bundle_size=case.bundle_size,
                truth=[dict(t) for t in case.truth],
                meta=meta,
            )
        )

    return noise_cases
