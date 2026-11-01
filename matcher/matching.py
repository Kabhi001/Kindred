"""
Core matching algorithm and profile encoding/decoding utilities for Kindred.
Incorporates empirical university roommate compatibility dimensions and
constructive, non-blaming clash warning rules.
"""

import base64
import json
from typing import Dict, Any, List, Optional, Tuple

# 10 core lifestyle dimensions derived from empirical campus housing research
KEYS = [
    'sleep',
    'privacy',
    'noise',
    'tidy',
    'temp',
    'guests',
    'sharing',
    'intent',
    'flexibility',
    'communication',
]

# Possible range (1 to max_val) for each trait
RANGE = {
    'sleep': 4,          # 1: <11pm, 2: 11pm-1am, 3: 1am-3am, 4: 3am+
    'privacy': 4,        # 1: A lot, 2: A few hours, 3: A little, 4: Barely
    'noise': 4,          # 1: Quiet/silent, 2: Earphones, 3: Speaker sometimes, 4: Out loud normal
    'tidy': 4,           # 1: Spotless daily, 2: Neat, 3: Lived-in, 4: Relaxed
    'guests': 4,         # 1: Almost never, 2: Occasionally heads-up, 3: Most weeks, 4: Open door
    'sharing': 4,        # 1: Keep separate, 2: Ask first, 3: Small things ok, 4: Share all
    'intent': 4,         # 1: Keep to ourselves, 2: Friendly separate, 3: Good friends, 4: Best friends
    'flexibility': 4,    # 1: Adjust easily, 2: Adjust after talk, 3: Prefer my way compromise, 4: Strongly prefer
    'temp': 4,           # 1: Chilly (AC strong), 2: Cool, 3: Moderate (fan only), 4: Warm & fresh
    'communication': 4,  # 1: Within a day, 2: After few days, 3: Drop hints, 4: Say nothing
    # Backward compatibility for legacy test cases
    'smoke': 4,          # Legacy fallback
    # Backward compatibility for legacy test cases
    'wake': 4,
    'study': 4,
    'social': 4,
}

# Empirical weights reflecting friction impact in shared campus living (Total: 100)
BASE_WEIGHTS = {
    'sleep': 18.0,
    'privacy': 16.0,
    'noise': 12.0,
    'tidy': 12.0,
    'temp': 8.0,
    'guests': 10.0,
    'sharing': 8.0,
    'intent': 8.0,
    'flexibility': 4.0,
    'communication': 4.0,
    # Backward compatibility
    'smoke': 5.0,
    'wake': 3.0,
    'study': 3.0,
    'social': 2.0,
}

# Multiplier for user-specified importance (1: a little, 2: it matters, 3: deal-breaker)
IMPORTANCE_MULTIPLIER = {
    1: 0.5,
    2: 1.0,
    3: 2.0,
}

# Short display labels for radar/bloom chart and summary chips
SHORT_LABELS = {
    'sleep': 'Sleep',
    'privacy': 'Privacy',
    'noise': 'Noise',
    'tidy': 'Tidy',
    'guests': 'Guests',
    'sharing': 'Sharing',
    'intent': 'Bond',
    'flexibility': 'Flexibility',
    'temp': 'Climate',
    'communication': 'Openness',
    'smoke': 'Smoke',
    # Legacy fallbacks
    'wake': 'Morning',
    'study': 'Study',
    'social': 'Social',
}

# Friendly trait names
TRAIT_NAMES = {
    'sleep': 'sleep schedule',
    'privacy': 'personal space',
    'noise': 'room sound level',
    'tidy': 'room cleanliness',
    'guests': 'guest boundaries',
    'sharing': 'sharing belongings',
    'intent': 'roommate closeness',
    'flexibility': 'handling differences',
    'temp': 'room temperature & cooling',
    'communication': 'communication style',
    'smoke': 'smoking stance',
    # Legacy fallbacks
    'wake': 'wake-up rhythm',
    'study': 'study habits',
    'social': 'social recharge style',
}

# Harmonious descriptors
GOOD_DESCRIPTORS = {
    'sleep': 'wind down at similar times',
    'privacy': 'have aligned personal space needs',
    'noise': 'prefer the same room sound level',
    'tidy': 'keep a similar level of cleanliness',
    'guests': 'feel comfortable with the same guest policy',
    'sharing': 'share similar boundaries on belongings',
    'intent': 'seek the same kind of roommate relationship',
    'flexibility': 'balance flexibility and personal preferences',
    'temp': 'prefer similar room temperature and AC settings',
    'communication': 'handle feedback with open communication',
    'smoke': 'share matching substance boundaries',
    # Legacy fallbacks
    'wake': 'have matching morning routines',
    'study': 'share preferred study spaces',
    'social': 'recharge in complementary ways',
}

# Friction descriptors
FRICTION_DESCRIPTORS = {
    'sleep': 'different sleep timing',
    'privacy': 'different personal space needs',
    'noise': 'different noise comfort levels',
    'tidy': 'different tidiness expectations',
    'guests': 'different guest boundaries',
    'sharing': 'different sharing boundaries',
    'intent': 'different expectations for closeness',
    'flexibility': 'both have very strong preferences',
    'temp': 'different room temperature and AC preferences',
    'communication': 'both tend to leave issues unspoken',
    'smoke': 'conflicting views on smoking/substances',
    # Legacy fallbacks
    'wake': 'different wake-up hours',
    'study': 'different study environments',
    'social': 'different social energies',
}


def evaluate_clashes_and_warnings(answers_a: Dict[str, int], answers_b: Dict[str, int]) -> Tuple[List[str], List[str]]:
    """
    Evaluate empirical deal-breaker clashes and constructive friction warnings
    based on the 10 university lifestyle dimensions.
    Returns: (clashes, warnings)
    """
    clashes: List[str] = []
    warnings: List[str] = []

    # 1. Sleep Schedule Deal-Breaker: Gap >= 2
    sleep_a = answers_a.get('sleep', 2)
    sleep_b = answers_b.get('sleep', 2)
    if abs(sleep_a - sleep_b) >= 2:
        clashes.append('sleep')
        warnings.append("Different sleep rhythms: You two tend to sleep at quite different times. Agree on lights-out time, desk-lamp or earphone rules in your first week.")

    # 2. Personal Space (Privacy) Deal-Breaker: Gap >= 2
    priv_a = answers_a.get('privacy', 2)
    priv_b = answers_b.get('privacy', 2)
    if abs(priv_a - priv_b) >= 2:
        clashes.append('privacy')
        warnings.append("Different need for personal space: One of you may want quiet, private time in the room, while the other likes the room to be more social. Decide early on 'room to myself' hours.")

    # 3. Smoking Filter Deal-Breaker (Legacy / Unit-Test backward compatibility)
    if 'smoke' in answers_a or 'smoke' in answers_b:
        smoke_a = answers_a.get('smoke', 1)
        smoke_b = answers_b.get('smoke', 1)
        if (smoke_a == 1 and smoke_b > 1) or (smoke_b == 1 and smoke_a > 1):
            clashes.append('smoke')
            warnings.append("Smoking / substance boundary mismatch: One student requires a strictly smoke-free environment.")

    # Room Temperature / AC Sensitivity Warning: Gap >= 2
    temp_a = answers_a.get('temp', 2)
    temp_b = answers_b.get('temp', 2)
    if abs(temp_a - temp_b) >= 2:
        warnings.append("Room climate difference: You have different AC and cooling preferences. Agree on nighttime thermostat or fan settings.")

    # 4. Noise Warning: Gap >= 2 or student 3-4 paired with student 1
    noise_a = answers_a.get('noise', 2)
    noise_b = answers_b.get('noise', 2)
    if abs(noise_a - noise_b) >= 2 or (noise_a >= 3 and noise_b == 1) or (noise_b >= 3 and noise_a == 1):
        warnings.append("Noise and sleep sensitivity: One of you is comfortable with sound in the room, and the other may be more sensitive to it. Earphones after a set hour work well.")

    # 5. Cleanliness & Tidiness Warning: Gap >= 2
    tidy_a = answers_a.get('tidy', 2)
    tidy_b = answers_b.get('tidy', 2)
    if abs(tidy_a - tidy_b) >= 2:
        warnings.append("Different tidiness standards: You have different ideas of what 'clean enough' means. A simple cleaning schedule usually settles this.")

    # 6. Flexibility Conflict Warning: Both have strong preferences (>= 3)
    flex_a = answers_a.get('flexibility', 2)
    flex_b = answers_b.get('flexibility', 2)
    if flex_a >= 3 and flex_b >= 3:
        warnings.append("Both have strong preferences: You both know what you like. Agree early on who decides what and how you'll settle disagreements.")

    # 7. Communication Style Warning: Both avoid awkward conversations (>= 3)
    comm_a = answers_a.get('communication', 2)
    comm_b = answers_b.get('communication', 2)
    if comm_a >= 3 and comm_b >= 3:
        warnings.append("Both prefer to avoid awkward conversations: Small problems can pile up unspoken. Try a quick check-in at the end of week one: 'Anything I could do differently?'")

    return list(dict.fromkeys(clashes)), list(dict.fromkeys(warnings))


def calculate_persona(answers: Dict[str, int]) -> str:
    """
    Calculate the poetic persona archetype based on quiz answers.
    e.g. 'Moonlit Curator', 'Dawn Sage', 'Midnight Host'.
    """
    sleep_val = answers.get('sleep', 2)
    sleep_prefixes = ['Dawn', 'Daylight', 'Moonlit', 'Midnight']
    idx = max(0, min(sleep_val - 1, 3))
    prefix = sleep_prefixes[idx]

    guests = answers.get('guests', 2)
    tidy = answers.get('tidy', 2)
    noise = answers.get('noise', 2)
    privacy = answers.get('privacy', 2)
    study = answers.get('study', 2)

    if guests >= 3:
        suffix = 'Host'
    elif tidy == 1:
        suffix = 'Curator'
    elif noise == 1:
        suffix = 'Sage'
    elif privacy == 1:
        suffix = 'Sanctuary'
    elif study in (1, 3):
        suffix = 'Scholar'
    elif tidy == 4:
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

    active_keys = [k for k in KEYS if k in my_answers or k in peer_answers]
    if not active_keys:
        active_keys = KEYS

    for k in active_keys:
        my_val = my_answers.get(k, 2)
        peer_val = peer_answers.get(k, 2)
        rng = RANGE.get(k, 4)

        sim = 1.0 - (abs(my_val - peer_val) / (rng - 1.0))
        sim = max(0.0, min(1.0, sim))
        similarities[k] = sim

        imp = my_importance.get(k, 2)
        weight = BASE_WEIGHTS.get(k, 5.0) * IMPORTANCE_MULTIPLIER.get(imp, 1.0)

        total_weighted_sim += weight * sim
        total_weight += weight

        if imp == 3 and sim < 0.5:
            clashes.append(k)

        if peer_importance:
            peer_imp = peer_importance.get(k, 2)
            if peer_imp == 3 and sim < 0.5 and k not in clashes:
                clashes.append(k)

    # Incorporate empirical clashes & warnings
    emp_clashes, emp_warnings = evaluate_clashes_and_warnings(my_answers, peer_answers)
    for c in emp_clashes:
        if c not in clashes:
            clashes.append(c)

    if total_weight > 0:
        raw_score = round((total_weighted_sim / total_weight) * 100)
    else:
        raw_score = 50

    final_score = min(raw_score, 59) if clashes else raw_score

    strong_traits = [k for k in active_keys if similarities.get(k, 0) >= 0.85]
    strong_traits.sort(key=lambda k: BASE_WEIGHTS.get(k, 5.0), reverse=True)
    top_good = strong_traits[:3]

    friction_candidates = [k for k in active_keys if similarities.get(k, 1) < 0.6]
    friction_candidates.sort(
        key=lambda k: BASE_WEIGHTS.get(k, 5.0) * (1.0 - similarities.get(k, 1)),
        reverse=True
    )
    top_friction = friction_candidates[0] if friction_candidates else None

    return {
        'score': final_score,
        'clashes': clashes,
        'warnings': emp_warnings,
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
