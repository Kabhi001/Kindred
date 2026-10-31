from itertools import combinations
from typing import Dict, Any, List, Optional
import networkx as nx
from django.db import transaction
from django.utils import timezone
from django.db.models import Q, F, Count

from .models import (
    StudentUser, Question, Response, PairScore, Pair,
    Room, Allotment, AuditLog, HostelBlock
)
from .matching import calculate_persona, GOOD_DESCRIPTORS, FRICTION_DESCRIPTORS, TRAIT_NAMES


def get_user_responses_dict(user: StudentUser):
    res_qs = Response.objects.filter(user=user).select_related('question')
    answers = {}
    importance = {}
    dealbreakers = {}
    for r in res_qs:
        answers[r.question.key] = r.answer
        importance[r.question.key] = r.importance
        dealbreakers[r.question.key] = getattr(r, 'is_dealbreaker', False)
    return answers, importance, dealbreakers


def calculate_directional_score(answers_a, importance_a, dealbreakers_or_answers_b, answers_b_or_qdict=None, questions_dict=None):
    if questions_dict is None:
        # Called with 4 arguments: (answers_a, importance_a, answers_b, questions_dict)
        dealbreakers_a = {}
        answers_b = dealbreakers_or_answers_b
        questions_dict = answers_b_or_qdict
    else:
        dealbreakers_a = dealbreakers_or_answers_b or {}
        answers_b = answers_b_or_qdict

    total_weighted_sim = 0.0
    total_weight = 0.0
    sims = {}
    clashes = []

    imp_multiplier = {1: 0.5, 2: 1.0, 3: 2.0}

    for key, q in questions_dict.items():
        val_a = answers_a.get(key, 2)
        val_b = answers_b.get(key, 2)

        # Handle circular distance for sleep/wake time dimensions
        is_circ = getattr(q, 'is_circular', False) or (key in ['sleep', 'wake'])
        if is_circ:
            period = getattr(q, 'cycle_period', 4) or max(4, (q.max_val - q.min_val + 1))
            raw_diff = abs(val_a - val_b)
            circ_diff = min(raw_diff, period - raw_diff)
            max_diff = period / 2.0
            sim = 1.0 - (circ_diff / max_diff) if max_diff > 0 else 1.0
        else:
            rng = max(1, q.max_val - q.min_val)
            sim = 1.0 - (abs(val_a - val_b) / float(rng))

        sim = max(0.0, min(1.0, sim))
        sims[key] = sim

        imp = importance_a.get(key, 2)
        weight = q.base_weight * imp_multiplier.get(imp, 1.0)

        total_weighted_sim += weight * sim
        total_weight += weight

        # Deal-breaker rule: separate boolean veto triggers clash when similarity < 0.5
        is_db = dealbreakers_a.get(key, False)
        if is_db and sim < 0.5:
            clashes.append(key)

    raw_score = (total_weighted_sim / total_weight * 100) if total_weight > 0 else 50.0
    return raw_score, sims, clashes


def calculate_mutual_score(user_a: StudentUser, user_b: StudentUser, questions=None, responses_cache=None):
    if questions is None:
        questions = list(Question.objects.filter(is_active=True))
    q_dict = {q.key: q for q in questions}

    if responses_cache and user_a.id in responses_cache:
        ans_a, imp_a, db_a = responses_cache[user_a.id]
    else:
        ans_a, imp_a, db_a = get_user_responses_dict(user_a)

    if responses_cache and user_b.id in responses_cache:
        ans_b, imp_b, db_b = responses_cache[user_b.id]
    else:
        ans_b, imp_b, db_b = get_user_responses_dict(user_b)

    score_a_to_b, sims_a, clashes_a = calculate_directional_score(ans_a, imp_a, db_a, ans_b, q_dict)
    score_b_to_a, sims_b, clashes_b = calculate_directional_score(ans_b, imp_b, db_b, ans_a, q_dict)

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


class BlossomResult(tuple):
    """
    Subclass of tuple (count, pairs) ensuring 100% backward compatibility
    with `count, pairs = run_blossom_leftover_matching(...)` while carrying rich metrics.
    """
    def __new__(cls, matched_count, created_pairs, pass1_pairs=None, pass2_compromise_pairs=None, odd_students=None):
        instance = super().__new__(cls, (matched_count, created_pairs))
        instance.matched_count = matched_count
        instance.created_pairs = created_pairs
        instance.pass1_pairs = pass1_pairs or []
        instance.pass2_compromise_pairs = pass2_compromise_pairs or []
        instance.odd_students = odd_students or []
        return instance


def compute_ranked_matches_for_student(student: StudentUser):
    paired_ids = set()
    for u_a, u_b in Pair.objects.values_list('user_a_id', 'user_b_id'):
        paired_ids.add(u_a)
        paired_ids.add(u_b)

    if student.id in paired_ids:
        return []

    candidates_qs = StudentUser.objects.filter(
        role='student',
        gender=student.gender,
    ).exclude(id=student.id).exclude(id__in=paired_ids).select_related('block')

    if student.block_id:
        candidates_qs = candidates_qs.filter(Q(block=student.block) | Q(block__isnull=True))

    candidates = list(candidates_qs)
    if not candidates:
        return []

    candidate_ids = [c.id for c in candidates]
    all_user_ids = [student.id] + candidate_ids

    questions = list(Question.objects.filter(is_active=True))
    active_count = len(questions)
    threshold = min(8, active_count) if active_count > 0 else 8

    # Batch pre-fetch all active responses into a dictionary in memory in 1 query
    from collections import defaultdict
    cached_responses = defaultdict(lambda: ({}, {}, {}))
    responses_qs = Response.objects.filter(
        user_id__in=all_user_ids,
        question__is_active=True
    ).select_related('question')

    for r in responses_qs:
        ans_d, imp_d, db_d = cached_responses[r.user_id]
        k = r.question.key
        ans_d[k] = r.answer
        imp_d[k] = r.importance
        db_d[k] = getattr(r, 'is_dealbreaker', False) or (r.importance == 3)

    # Filter candidate peers that have completed the survey using in-memory response counts
    eligible_peers = [
        peer for peer in candidates
        if len(cached_responses[peer.id][0]) >= threshold
    ]
    if not eligible_peers:
        return []

    eligible_peer_ids = [p.id for p in eligible_peers]

    # Query all relevant PairScore records in 1 query with user_a/user_b filters
    pair_scores_qs = PairScore.objects.filter(
        Q(user_a=student, user_b_id__in=eligible_peer_ids) |
        Q(user_b=student, user_a_id__in=eligible_peer_ids)
    )
    pair_scores_map = {
        (min(ps.user_a_id, ps.user_b_id), max(ps.user_a_id, ps.user_b_id)): ps
        for ps in pair_scores_qs
    }

    results = []
    new_pair_scores = []

    for peer in eligible_peers:
        u1, u2 = (student, peer) if student.id < peer.id else (peer, student)
        pair_key = (u1.id, u2.id)
        ps = pair_scores_map.get(pair_key)

        if not ps:
            res = calculate_mutual_score(u1, u2, questions, responses_cache=cached_responses)
            ps = PairScore(
                user_a=u1,
                user_b=u2,
                score_a_to_b=res['score_a_to_b'],
                score_b_to_a=res['score_b_to_a'],
                final_score=res['final_score'],
                good_reasons=res['good_reasons'],
                frictions=res['frictions'],
                clashes=res['clashes'],
                algorithm_version='2.1.0'
            )
            new_pair_scores.append(ps)
            pair_scores_map[pair_key] = ps

        score_for_me = ps.score_a_to_b if student == u1 else ps.score_b_to_a
        score_for_peer = ps.score_b_to_a if student == u1 else ps.score_a_to_b

        # Privacy Seal: Raw peer responses are NEVER serialized or exposed
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
        })

    if new_pair_scores:
        PairScore.objects.bulk_create(new_pair_scores, ignore_conflicts=True)

    results.sort(key=lambda x: x['final_score'], reverse=True)
    return results


def run_blossom_leftover_matching(block=None, actor="System", dry_run=False):
    from .models import Notification
    paired_ids = set(Pair.objects.values_list('user_a_id', flat=True)) | set(Pair.objects.values_list('user_b_id', flat=True))
    
    qs = StudentUser.objects.filter(role='student').exclude(id__in=paired_ids)
    if block:
        qs = qs.filter(block=block)

    unpaired_students = list(qs)
    if len(unpaired_students) < 2:
        return BlossomResult(0, [], [], [], list(unpaired_students))

    groups = {}
    for st in unpaired_students:
        key = (st.gender, st.block_id)
        groups.setdefault(key, []).append(st)

    created_pairs = []
    pass1_pairs = []
    pass2_compromise_pairs = []
    all_odd_students = []
    questions = list(Question.objects.filter(is_active=True))

    for (gender, blk_id), group_students in groups.items():
        if len(group_students) < 2:
            all_odd_students.extend(group_students)
            continue

        # Precompute pairwise compatibility
        pairwise_eval = {}
        for s1, s2 in combinations(group_students, 2):
            u_min = min(s1.id, s2.id)
            u_max = max(s1.id, s2.id)
            pairwise_eval[(u_min, u_max)] = calculate_mutual_score(s1, s2, questions)

        # -------------------------------------------------------------
        # PASS 1: Pure Clash-Free Graph
        # Excludes all edges with deal-breaker clashes!
        # -------------------------------------------------------------
        G1 = nx.Graph()
        for s in group_students:
            G1.add_node(s.id)

        for (u1_id, u2_id), res in pairwise_eval.items():
            if len(res['clashes']) == 0:
                G1.add_edge(u1_id, u2_id, weight=res['final_score'])

        matching_p1 = nx.max_weight_matching(G1, maxcardinality=True)
        matched_p1_ids = set()

        for u1_id, u2_id in matching_p1:
            u_min = min(u1_id, u2_id)
            u_max = max(u1_id, u2_id)
            matched_p1_ids.add(u_min)
            matched_p1_ids.add(u_max)
            user_a = StudentUser.objects.get(id=u_min)
            user_b = StudentUser.objects.get(id=u_max)
            eval_data = pairwise_eval.get((u_min, u_max), {})

            if not dry_run:
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
                        pass1_pairs.append(pair)
                        AuditLog.objects.create(
                            actor=actor,
                            action='BLOSSOM_MATCHING',
                            target=f"{user_a.roll_no} & {user_b.roll_no}",
                            reason=f"Pass 1 Clash-Free Blossom pairing (Harmony: {eval_data.get('final_score', 0):.0f}%)"
                        )
            else:
                pass1_pairs.append((user_a, user_b, eval_data.get('final_score', 0), []))

        # -------------------------------------------------------------
        # PASS 2: Compromise Graph for Unmatched Remainder
        # -------------------------------------------------------------
        remaining_students = [s for s in group_students if s.id not in matched_p1_ids]

        if len(remaining_students) >= 2:
            G2 = nx.Graph()
            for s in remaining_students:
                G2.add_node(s.id)

            for s1, s2 in combinations(remaining_students, 2):
                u_min = min(s1.id, s2.id)
                u_max = max(s1.id, s2.id)
                res = pairwise_eval.get((u_min, u_max))
                if res:
                    G2.add_edge(u_min, u_max, weight=res['final_score'])

            matching_p2 = nx.max_weight_matching(G2, maxcardinality=True)
            matched_p2_ids = set()

            for u1_id, u2_id in matching_p2:
                u_min = min(u1_id, u2_id)
                u_max = max(u1_id, u2_id)
                matched_p2_ids.add(u_min)
                matched_p2_ids.add(u_max)
                user_a = StudentUser.objects.get(id=u_min)
                user_b = StudentUser.objects.get(id=u_max)
                eval_data = pairwise_eval.get((u_min, u_max), {})
                clashes_str = ", ".join(eval_data.get('clashes', []))

                if not dry_run:
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
                            pass2_compromise_pairs.append(pair)
                            AuditLog.objects.create(
                                actor=actor,
                                action='BLOSSOM_MATCHING_COMPROMISE',
                                target=f"{user_a.roll_no} & {user_b.roll_no}",
                                reason=f"Pass 2 Compromise pairing with clashes ({clashes_str}). Flagged for Warden review."
                            )
                else:
                    pass2_compromise_pairs.append((user_a, user_b, eval_data.get('final_score', 0), eval_data.get('clashes', [])))

            # Odd remainder after Pass 2
            odd_rem = [s for s in remaining_students if s.id not in matched_p2_ids]
            all_odd_students.extend(odd_rem)
        else:
            all_odd_students.extend(remaining_students)

    # Log and notify odd/unmatched students
    if not dry_run:
        for odd_student in all_odd_students:
            AuditLog.objects.create(
                actor=actor,
                action='BLOSSOM_ODD_STUDENT_UNMATCHED',
                target=odd_student.roll_no,
                reason="Student remained unmatched after 2-pass Blossom allocation. Forwarded to Warden manual queue."
            )
            Notification.objects.get_or_create(
                student=odd_student,
                category='ALLOTMENT',
                title='Allotment Forwarded to Warden',
                defaults={
                    'message': 'Your room allocation has been routed to the Warden Desk for personalized room allotment.'
                }
            )

    total_count = len(created_pairs) if not dry_run else (len(pass1_pairs) + len(pass2_compromise_pairs))
    return BlossomResult(
        total_count,
        created_pairs if not dry_run else [],
        pass1_pairs,
        pass2_compromise_pairs,
        all_odd_students
    )


def run_automated_room_allotment(actor="System"):
    unallotted_pairs = Pair.objects.filter(room__isnull=True, status='CONFIRMED').select_related('user_a', 'user_b')
    allotted_count = 0

    for pair in unallotted_pairs:
        blk = pair.user_a.block or pair.user_b.block or HostelBlock.objects.first()
        if not blk:
            continue

        with transaction.atomic():
            # Capacity-aware room search using bulk annotation and select_for_update() row locks
            vacant_room = Room.objects.select_for_update().filter(block=blk).annotate(
                occupied=Count('allotments', filter=Q(allotments__is_active=True))
            ).filter(occupied__lte=F('capacity') - 2).order_by('floor', 'number').first()

            if not vacant_room:
                # Fallback search respecting student gender policy
                student_gender = pair.user_a.gender
                vacant_room = Room.objects.select_for_update().filter(
                    Q(block__gender=student_gender) | Q(block__gender='COED')
                ).annotate(
                    occupied=Count('allotments', filter=Q(allotments__is_active=True))
                ).filter(occupied__lte=F('capacity') - 2).order_by('block', 'floor', 'number').first()

            if vacant_room:
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
                    reason=f"Capacity-aware room allotment to Room {vacant_room.number} (Floor {vacant_room.floor}, Capacity {vacant_room.capacity})"
                )
                allotted_count += 1

    return allotted_count