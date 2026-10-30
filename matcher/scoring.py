from itertools import combinations
from typing import Dict, Any, List, Optional
import networkx as nx
from django.db import transaction
from django.utils import timezone
from django.db.models import Q

from .models import (
    StudentUser, Question, Response, PairScore, Pair,
    Room, Allotment, AuditLog, HostelBlock
)
from .matching import calculate_persona, GOOD_DESCRIPTORS, FRICTION_DESCRIPTORS, TRAIT_NAMES


def get_user_responses_dict(user: StudentUser):
    res_qs = Response.objects.filter(user=user).select_related('question')
    answers = {}
    importance = {}
    for r in res_qs:
        answers[r.question.key] = r.answer
        importance[r.question.key] = r.importance
    return answers, importance


def calculate_directional_score(answers_a, importance_a, answers_b, questions_dict):
    total_weighted_sim = 0.0
    total_weight = 0.0
    sims = {}
    clashes = []

    imp_multiplier = {1: 0.5, 2: 1.0, 3: 2.0}

    for key, q in questions_dict.items():
        val_a = answers_a.get(key, 2)
        val_b = answers_b.get(key, 2)
        rng = max(1, q.max_val - q.min_val)

        sim = 1.0 - (abs(val_a - val_b) / float(rng))
        sim = max(0.0, min(1.0, sim))
        sims[key] = sim

        imp = importance_a.get(key, 2)
        weight = q.base_weight * imp_multiplier.get(imp, 1.0)

        total_weighted_sim += weight * sim
        total_weight += weight

        # Deal-breaker rule
        if imp == 3 and sim < 0.5:
            clashes.append(key)

    raw_score = (total_weighted_sim / total_weight * 100) if total_weight > 0 else 50.0
    return raw_score, sims, clashes


def calculate_mutual_score(user_a: StudentUser, user_b: StudentUser, questions=None):
    if questions is None:
        questions = list(Question.objects.filter(is_active=True))
    q_dict = {q.key: q for q in questions}

    ans_a, imp_a = get_user_responses_dict(user_a)
    ans_b, imp_b = get_user_responses_dict(user_b)

    score_a_to_b, sims_a, clashes_a = calculate_directional_score(ans_a, imp_a, ans_b, q_dict)
    score_b_to_a, sims_b, clashes_b = calculate_directional_score(ans_b, imp_b, ans_a, q_dict)

    all_clashes = list(set(clashes_a + clashes_b))
    raw_final = min(score_a_to_b, score_b_to_a)
    final_score = min(raw_final, 59.0) if all_clashes else raw_final

    good_keys = [k for k, s in sims_a.items() if s >= 0.85]
    good_reasons = [GOOD_DESCRIPTORS.get(k, f"align on {k}") for k in good_keys[:3]]

    friction_keys = [k for k, s in sims_a.items() if s < 0.6]
    frictions = [FRICTION_DESCRIPTORS.get(k, f"differ on {k}") for k in friction_keys[:2]]

    return {
        'score_a_to_b': round(score_a_to_b, 1),
        'score_b_to_a': round(score_b_to_a, 1),
        'final_score': round(final_score, 1),
        'clashes': all_clashes,
        'good_reasons': good_reasons,
        'frictions': frictions,
    }


def compute_ranked_matches_for_student(student: StudentUser):
    if student.is_paired:
        return []

    paired_ids = set(Pair.objects.values_list('user_a_id', flat=True)) | set(Pair.objects.values_list('user_b_id', flat=True))

    candidates = StudentUser.objects.filter(
        role='student',
        gender=student.gender,
    ).exclude(id=student.id).exclude(id__in=paired_ids)

    if student.block_id:
        candidates = candidates.filter(Q(block=student.block) | Q(block__isnull=True))

    questions = list(Question.objects.filter(is_active=True))
    results = []

    for peer in candidates:
        if not peer.has_completed_survey:
            continue

        u1, u2 = (student, peer) if student.id < peer.id else (peer, student)
        ps = PairScore.objects.filter(user_a=u1, user_b=u2).first()
        if not ps:
            res = calculate_mutual_score(u1, u2, questions)
            ps, _ = PairScore.objects.update_or_create(
                user_a=u1,
                user_b=u2,
                defaults={
                    'score_a_to_b': res['score_a_to_b'],
                    'score_b_to_a': res['score_b_to_a'],
                    'final_score': res['final_score'],
                    'good_reasons': res['good_reasons'],
                    'frictions': res['frictions'],
                    'clashes': res['clashes']
                }
            )

        score_for_me = ps.score_a_to_b if student == u1 else ps.score_b_to_a
        score_for_peer = ps.score_b_to_a if student == u1 else ps.score_a_to_b

        peer_ans, peer_imp = get_user_responses_dict(peer)

        results.append({
            'id': peer.id,
            'name': peer.name,
            'roll_no': peer.roll_no,
            'branch': peer.branch,
            'year': peer.year,
            'persona': peer.persona,
            'block': peer.block.name if peer.block else "Main Hostel",
            'avatar_hue': peer.avatar_hue,
            'final_score': int(ps.final_score),
            'my_score': int(score_for_me),
            'peer_score': int(score_for_peer),
            'clashes': ps.clashes,
            'is_dealbreaker': len(ps.clashes) > 0,
            'good_reasons': ps.good_reasons,
            'frictions': ps.frictions,
            'peer_answers': peer_ans,
            'peer_importance': peer_imp,
        })

    results.sort(key=lambda x: x['final_score'], reverse=True)
    return results


def run_blossom_leftover_matching(block=None, actor="System"):
    paired_ids = set(Pair.objects.values_list('user_a_id', flat=True)) | set(Pair.objects.values_list('user_b_id', flat=True))
    
    qs = StudentUser.objects.filter(role='student').exclude(id__in=paired_ids)
    if block:
        qs = qs.filter(block=block)

    unpaired_students = list(qs)
    if len(unpaired_students) < 2:
        return 0, []

    groups = {}
    for st in unpaired_students:
        key = (st.gender, st.block_id)
        groups.setdefault(key, []).append(st)

    created_pairs = []
    questions = list(Question.objects.filter(is_active=True))

    for (gender, blk_id), group_students in groups.items():
        if len(group_students) < 2:
            continue

        G = nx.Graph()
        for s in group_students:
            G.add_node(s.id)

        for s1, s2 in combinations(group_students, 2):
            res = calculate_mutual_score(s1, s2, questions)
            G.add_edge(s1.id, s2.id, weight=res['final_score'])

        matching = nx.max_weight_matching(G, maxcardinality=True)

        for u1_id, u2_id in matching:
            u_min = min(u1_id, u2_id)
            u_max = max(u1_id, u2_id)
            user_a = StudentUser.objects.get(id=u_min)
            user_b = StudentUser.objects.get(id=u_max)

            with transaction.atomic():
                pair, created = Pair.objects.get_or_create(
                    user_a=user_a,
                    user_b=user_b,
                    defaults={
                        'method': 'BLOSSOM_MATCHING',
                        'status': 'CONFIRMED'
                    }
                )
                if created:
                    created_pairs.append(pair)
                    AuditLog.objects.create(
                        actor=actor,
                        action='BLOSSOM_MATCHING',
                        target=f"{user_a.roll_no} & {user_b.roll_no}",
                        reason=f"Automated Blossom max-weight pairing (weight {G[u1_id][u2_id]['weight']:.0f})"
                    )

    return len(created_pairs), created_pairs


def run_automated_room_allotment(actor="System"):
    unallotted_pairs = Pair.objects.filter(room__isnull=True, status='CONFIRMED').select_related('user_a', 'user_b')
    allotted_count = 0

    for pair in unallotted_pairs:
        blk = pair.user_a.block or pair.user_b.block or HostelBlock.objects.first()
        if not blk:
            continue

        vacant_room = Room.objects.filter(
            block=blk,
            capacity__gte=2
        ).exclude(
            pairs__isnull=False
        ).first()

        if vacant_room:
            with transaction.atomic():
                pair.room = vacant_room
                pair.status = 'ALLOTTED'
                pair.save()

                Allotment.objects.update_or_create(
                    room=vacant_room, user=pair.user_a,
                    defaults={'is_active': True}
                )
                Allotment.objects.update_or_create(
                    room=vacant_room, user=pair.user_b,
                    defaults={'is_active': True}
                )

                AuditLog.objects.create(
                    actor=actor,
                    action='ROOM_ALLOTTED',
                    target=f"{pair.user_a.roll_no} & {pair.user_b.roll_no} -> {vacant_room}",
                    reason=f"Automated allotment to room {vacant_room.number}"
                )
                allotted_count += 1

    return allotted_count