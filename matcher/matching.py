"""
Core matching algorithm and profile encoding/decoding utilities for Kindred.
"""

import base64
import json
from typing import Dict, Any, List, Optional

# Core lifestyle traits evaluated in the kindred quiz
KEYS = ['sleep', 'wake', 'smoke', 'tidy', 'noise', 'study', 'guests', 'social']

# Possible range (1 to max_val) for each trait
RANGE = {
    'sleep': 4,   # 1: <10pm, 2: ~11pm, 3: past midnight, 4: 2am+
    'wake': 4,    # 1: <6am, 2: 6-8am, 3: 8-10am, 4: late morning
    'smoke': 3,   # 1: Never, 2: Occasionally not indoors, 3: Regularly
    'tidy': 4,    # 4: Spotless, 3: Tidy, 2: Lived-in, 1: Creative storm
    'noise': 4,   # 1: Silent, 2: Quiet hum, 3: Soft music, 4: Any noise
    'study': 4,   # 1: Room night, 2: Room day, 3: Library, 4: Anywhere
    'guests': 4,  # 1: Rare, 2: Now and then, 3: Often, 4: Open house
    'social': 4,  # 1: Alone, 2: One close friend, 3: Big group, 4: Depends
}

# Base weight importance in roommate harmony
BASE_WEIGHTS = {
    'sleep': 5.0,
    'smoke': 5.0,
    'tidy': 4.0,
    'noise': 4.0,
    'wake': 3.0,
    'study': 3.0,
    'guests': 3.0,
    'social': 2.0,
}

# Multiplier for user-specified importance (1: a little, 2: it matters, 3: deal-breaker)
IMPORTANCE_MULTIPLIER = {
    1: 0.5,
    2: 1.0,
    3: 2.0,
}

# Short display labels
SHORT_LABELS = {
    'sleep': 'Sleep',
    'wake': 'Morning',
    'smoke': 'Smoke',
    'tidy': 'Tidy',
    'noise': 'Noise',
    'study': 'Study',
    'guests': 'Guests',
    'social': 'Social',
}

# Friendly trait names
TRAIT_NAMES = {
    'sleep': 'sleep schedule',
    'wake': 'wake-up rhythm',
    'smoke': 'smoking stance',
    'tidy': 'room cleanliness',
    'noise': 'noise tolerance',
    'study': 'study habits',
    'guests': 'guest policy',
    'social': 'social recharge style',
}

# Harmonious descriptors
GOOD_DESCRIPTORS = {
    'sleep': 'wind down at a similar time',
    'wake': 'have matching morning routines',
    'smoke': 'share the same stance on smoking',
    'tidy': 'keep a similar level of tidiness',
    'noise': 'thrive with the same sound level',
    'study': 'share preferred study spaces',
    'guests': 'feel comfortable with the same guest policy',
    'social': 'recharge in complementary ways',
}

# Friction descriptors
FRICTION_DESCRIPTORS = {
    'sleep': 'different sleep timing',
    'wake': 'different wake-up hours',
    'smoke': 'conflicting views on smoking',
    'tidy': 'different tidiness expectations',
    'noise': 'different noise comfort levels',
    'study': 'different study environments',
    'guests': 'different guest boundaries',
    'social': 'different social energies',
}


def calculate_persona(answers: Dict[str, int]) -> str:
    """
    Calculate the poetic persona archetype based on quiz answers.
    e.g. 'Moonlit Scholar', 'Dawn Curator', 'Midnight Host'.
    """
    sleep_val = answers.get('sleep', 2)
    sleep_prefixes = ['Dawn', 'Daylight', 'Moonlit', 'Midnight']
    idx = max(0, min(sleep_val - 1, 3))
    prefix = sleep_prefixes[idx]

    guests = answers.get('guests', 2)
    tidy = answers.get('tidy', 2)
    noise = answers.get('noise', 2)
    study = answers.get('study', 2)

    if guests >= 3:
        suffix = 'Host'
    elif tidy == 4:
        suffix = 'Curator'
    elif noise == 1:
        suffix = 'Sage'
    elif study in (1, 3):
        suffix = 'Scholar'
    elif tidy == 1:
        suffix = 'Dreamer'
    else:
        suffix = 'Wanderer'

    return f'{prefix} {suffix}'


def calculate_match_score(
    my_answers: Dict[str, int],
    my_importance: Dict[str, int],
    peer_answers: Dict[str, int],
    peer_importance: Optional[Dict[str, int]] = None
) -> Dict[str, Any]:
    """
    Calculate compatibility between two students.
    """
    total_weighted_sim = 0.0
    total_weight = 0.0
    similarities = {}
    clashes = []

    for k in KEYS:
        my_val = my_answers.get(k, 2)
        peer_val = peer_answers.get(k, 2)
        rng = RANGE[k]

        sim = 1.0 - (abs(my_val - peer_val) / (rng - 1.0))
        similarities[k] = max(0.0, min(1.0, sim))

        imp = my_importance.get(k, 2)
        weight = BASE_WEIGHTS[k] * IMPORTANCE_MULTIPLIER.get(imp, 1.0)

        total_weighted_sim += weight * sim
        total_weight += weight

        if imp == 3 and sim < 0.5:
            clashes.append(k)

        if peer_importance:
            peer_imp = peer_importance.get(k, 2)
            if peer_imp == 3 and sim < 0.5 and k not in clashes:
                clashes.append(k)

    if total_weight > 0:
        raw_score = round((total_weighted_sim / total_weight) * 100)
    else:
        raw_score = 50

    final_score = min(raw_score, 59) if clashes else raw_score

    strong_traits = [k for k in KEYS if similarities[k] >= 0.85]
    strong_traits.sort(key=lambda k: BASE_WEIGHTS[k], reverse=True)
    top_good = strong_traits[:3]

    friction_candidates = [k for k in KEYS if similarities[k] < 0.6]
    friction_candidates.sort(
        key=lambda k: BASE_WEIGHTS[k] * (1.0 - similarities[k]),
        reverse=True
    )
    top_friction = friction_candidates[0] if friction_candidates else None

    return {
        'score': final_score,
        'clashes': clashes,
        'is_dealbreaker': len(clashes) > 0,
        'good': top_good,
        'friction': top_friction,
        'similarities': {k: round(v, 2) for k, v in similarities.items()},
    }


def encode_profile_code(profile_dict: Dict[str, Any]) -> str:
    """Encode profile data into a KP- token identical to frontend prototype."""
    data_str = json.dumps(profile_dict, separators=(',', ':'))
    encoded = base64.b64encode(data_str.encode('utf-8')).decode('utf-8')
    return f'KP-{encoded}'


def decode_profile_code(code_str: str) -> Optional[Dict[str, Any]]:
    """Decode a KP- token into a profile dictionary."""
    code_str = code_str.strip()
    if not code_str.startswith('KP-'):
        return None
    try:
        raw_b64 = code_str[3:]
        decoded_bytes = base64.b64decode(raw_b64.encode('utf-8'))
        return json.loads(decoded_bytes.decode('utf-8'))
    except Exception:
        return None


def encode_request_code(request_dict: Dict[str, Any]) -> str:
    """Encode request data into a KR- token."""
    data_str = json.dumps(request_dict, separators=(',', ':'))
    encoded = base64.b64encode(data_str.encode('utf-8')).decode('utf-8')
    return f'KR-{encoded}'


def decode_request_code(code_str: str) -> Optional[Dict[str, Any]]:
    """Decode a KR- token."""
    code_str = code_str.strip()
    if not code_str.startswith('KR-'):
        return None
    try:
        raw_b64 = code_str[3:]
        decoded_bytes = base64.b64decode(raw_b64.encode('utf-8'))
        return json.loads(decoded_bytes.decode('utf-8'))
    except Exception:
        return None