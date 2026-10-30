import secrets
from django.contrib.auth.hashers import make_password, check_password
import json
from datetime import timedelta
from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse, HttpResponseBadRequest, HttpResponseForbidden
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import ensure_csrf_cookie, csrf_exempt
from django.utils import timezone
from django.db import transaction
from django.db.models import Q

from .models import (
    HostelBlock, Room, StudentUser, AllotmentCalendar,
    Question, Response, PairScore, Request, Pair, Allotment, AuditLog, OTPVerification
)
from .scoring import (
    calculate_mutual_score, compute_ranked_matches_for_student,
    run_blossom_leftover_matching, run_automated_room_allotment
)
from .matching import calculate_persona, encode_profile_code, decode_profile_code


def get_current_user(request) -> StudentUser:
    user_id = request.session.get('current_user_id')
    user = None
    if user_id:
        user = StudentUser.objects.filter(id=user_id).first()
    if not user:
        user = StudentUser.objects.filter(role='student', name="Aarav Patel").first()
        if not user:
            user = StudentUser.objects.filter(role='student').first()
        if not user:
            user = StudentUser.objects.create(
                roll_no="DEMO-2026-001",
                name="Aarav Patel",
                email="aarav@hostel.edu",
                gender='M',
                year="1st Year",
                branch="Computer Science",
                role='student',
                avatar_hue=270,
                is_demo=True
            )
        request.session['current_user_id'] = user.id
    return user


def expire_stale_requests():
    """Sets requests older than 48 hours to EXPIRED."""
    now = timezone.now()
    Request.objects.filter(status='SENT', expires_at__lt=now).update(status='EXPIRED')


@ensure_csrf_cookie

def home_view(request):
    """Public Landing & Home Page for Kindred Hostel Allotment Platform."""
    calendar = AllotmentCalendar.get_current()
    students_count = StudentUser.objects.filter(role='student').count()
    pairs = Pair.objects.all()
    confirmed_pairs_count = pairs.count()
    allotted_count = pairs.filter(status='ALLOTTED').count()
    rooms = Room.objects.all().select_related('block')
    total_rooms = rooms.count()
    total_beds = sum(r.capacity for r in rooms)
    occupied_beds = Allotment.objects.filter(is_active=True).count()

    blocks = HostelBlock.objects.all().prefetch_related('rooms')
    blocks_data = []
    for b in blocks:
        b_rooms = b.rooms.all()
        b_capacity = sum(r.capacity for r in b_rooms)
        b_occupied = Allotment.objects.filter(room__block=b, is_active=True).count()
        pct = int((b_occupied / b_capacity * 100)) if b_capacity > 0 else 0
        blocks_data.append({
            'block': b,
            'room_count': b_rooms.count(),
            'capacity': b_capacity,
            'occupied': b_occupied,
            'available': max(0, b_capacity - b_occupied),
            'percent': pct
        })

    current_user_id = request.session.get('current_user_id')
    logged_in_user = StudentUser.objects.filter(id=current_user_id).first() if current_user_id else None

    context = {
        'calendar': calendar,
        'students_count': students_count,
        'confirmed_pairs_count': confirmed_pairs_count,
        'allotted_count': allotted_count,
        'total_rooms': total_rooms,
        'total_beds': total_beds,
        'occupied_beds': occupied_beds,
        'available_beds': max(0, total_beds - occupied_beds),
        'blocks_data': blocks_data,
        'logged_in_user': logged_in_user,
    }
    return render(request, 'matcher/home.html', context)


def index_view(request):
    current_user = get_current_user(request)
    calendar = AllotmentCalendar.get_current()
    demo_students = StudentUser.objects.filter(role='student', is_demo=True).order_by('name')
    pairings_count = Pair.objects.count()

    context = {
        'current_student': current_user,
        'demo_students': demo_students,
        'calendar': calendar,
        'pairings_count': pairings_count,
    }
    return render(request, 'matcher/index.html', context)


def warden_dashboard_view(request):
    expire_stale_requests()
    calendar = AllotmentCalendar.get_current()
    pairs = Pair.objects.select_related('user_a', 'user_b', 'room', 'room__block').all().order_by('-confirmed_at')
    
    paired_ids = set(pairs.values_list('user_a_id', flat=True)) | set(pairs.values_list('user_b_id', flat=True))
    all_students = StudentUser.objects.filter(role='student').select_related('block').order_by('name')
    unpaired_students = [s for s in all_students if s.id not in paired_ids]

    vacant_rooms = Room.objects.filter(pairs__isnull=True).select_related('block')
    audit_logs = AuditLog.objects.all().order_by('-timestamp')[:25]

    pairs_data = []
    for p in pairs:
        score_info = PairScore.objects.filter(user_a=p.user_a, user_b=p.user_b).first()
        score_val = int(score_info.final_score) if score_info else 85
        pairs_data.append({
            'pairing': p,
            'score': score_val,
            's1': p.user_a,
            's2': p.user_b,
        })

    context = {
        'calendar': calendar,
        'pairs_data': pairs_data,
        'unpaired_students': unpaired_students,
        'vacant_rooms': vacant_rooms,
        'audit_logs': audit_logs,
        'total_students_count': all_students.count(),
        'confirmed_pairs_count': pairs.count(),
        'allotted_count': pairs.filter(status='ALLOTTED').count(),
        'pending_requests_count': Request.objects.filter(status='SENT').count(),
    }
    return render(request, 'matcher/warden.html', context)


# ==========================================
# REST / JSON API ENDPOINTS
# ==========================================

def api_me(request):
    expire_stale_requests()
    user = get_current_user(request)
    calendar = AllotmentCalendar.get_current()
    
    responses = Response.objects.filter(user=user).select_related('question')
    answers = {r.question.key: r.answer for r in responses}
    importance = {r.question.key: r.importance for r in responses}
    has_quiz = len(answers) >= 8

    pair = user.get_pair()
    pair_info = None
    if pair:
        partner = pair.partner_of(user)
        pair_info = {
            'partner_name': partner.name,
            'partner_roll': partner.roll_no,
            'partner_avatar_hue': partner.avatar_hue,
            'method': pair.get_method_display(),
            'status': pair.get_status_display(),
            'room': pair.room.number if pair.room else None,
            'block': pair.room.block.name if pair.room else None,
        }

    data = {
        'id': user.id,
        'name': user.name,
        'roll_no': user.roll_no,
        'email': user.email,
        'gender': user.get_gender_display(),
        'year': user.year,
        'branch': user.branch,
        'role': user.role,
        'persona': user.persona,
        'avatar_hue': user.avatar_hue,
        'block': user.block.name if user.block else "Main Hostel",
        'consent_given': user.consent_given,
        'has_quiz': has_quiz,
        'answers': answers,
        'importance': importance,
        'is_paired': bool(pair),
        'pairing': pair_info,
        'profile_code': encode_profile_code({'n': user.name, 'p': user.persona, 'a': answers, 'i': importance}) if has_quiz else "",
        'calendar': {
            'phase': calendar.phase,
            'phase_name': calendar.get_phase_display(),
            'can_survey': calendar.phase in ['SURVEY_OPEN', 'MATCHING_OPEN'],
            'can_match': calendar.phase == 'MATCHING_OPEN',
            'is_frozen': calendar.phase in ['FREEZE', 'WARDEN_ALLOTMENT', 'LEFTOVER_PAIRING', 'PUBLISHED'],
            'is_published': calendar.phase == 'PUBLISHED',
        }
    }
    return JsonResponse(data)


@csrf_exempt
@require_http_methods(["POST"])
def api_consent_agree(request):
    user = get_current_user(request)
    user.consent_given = True
    user.consent_at = timezone.now()
    user.save(update_fields=['consent_given', 'consent_at'])
    return JsonResponse({'ok': True, 'message': 'Consent recorded under DPDP Act 2023.'})


@csrf_exempt
@require_http_methods(["POST"])
def api_switch_student(request):
    try:
        body = json.loads(request.body.decode('utf-8'))
    except Exception:
        return HttpResponseBadRequest("Invalid JSON")

    user_id = body.get('student_id')
    user = StudentUser.objects.filter(id=user_id).first()
    if not user:
        return JsonResponse({'error': 'User not found'}, status=404)

    request.session['current_user_id'] = user.id
    return JsonResponse({
        'ok': True,
        'id': user.id,
        'name': user.name,
        'role': user.role,
        'persona': user.persona
    })


def api_students_list(request):
    current = get_current_user(request)
    students = StudentUser.objects.filter(role='student').order_by('name')
    data = []
    for s in students:
        data.append({
            'id': s.id,
            'name': s.name,
            'roll_no': s.roll_no,
            'persona': s.persona,
            'branch': s.branch,
            'block': s.block.name if s.block else "Main Hostel",
            'is_current': s.id == current.id,
            'is_paired': s.is_paired,
        })
    return JsonResponse({'students': data})


@csrf_exempt
@require_http_methods(["POST"])
def api_submit_quiz(request):
    calendar = AllotmentCalendar.get_current()
    if calendar.phase not in ['SURVEY_OPEN', 'MATCHING_OPEN']:
        return JsonResponse({
            'error': f"Survey submissions are closed during the '{calendar.get_phase_display()}' phase."
        }, status=400)

    try:
        body = json.loads(request.body.decode('utf-8'))
    except Exception:
        return HttpResponseBadRequest("Invalid JSON")

    user = get_current_user(request)
    if not user.consent_given:
        user.consent_given = True
        user.consent_at = timezone.now()

    name = body.get('name', '').strip()
    if name:
        user.name = name

    answers = body.get('answers', {})
    importance = body.get('importance', {})

    user.persona = calculate_persona(answers)
    user.save()

    questions = {q.key: q for q in Question.objects.filter(is_active=True)}
    for key, val in answers.items():
        if key in questions:
            imp_val = importance.get(key, 2)
            Response.objects.update_or_create(
                user=user,
                question=questions[key],
                defaults={'answer': int(val), 'importance': int(imp_val)}
            )

    PairScore.objects.filter(Q(user_a=user) | Q(user_b=user)).delete()

    return JsonResponse({
        'ok': True,
        'name': user.name,
        'persona': user.persona,
        'message': 'Survey responses saved and persona calculated!'
    })


def api_matches(request):
    calendar = AllotmentCalendar.get_current()
    if calendar.phase not in ['MATCHING_OPEN', 'WARDEN_ALLOTMENT', 'LEFTOVER_PAIRING', 'PUBLISHED']:
        return JsonResponse({'matches': [], 'has_quiz': False, 'message': 'Matching is not open yet.'})

    user = get_current_user(request)
    if not user.has_completed_survey:
        return JsonResponse({'matches': [], 'has_quiz': False})

    ranked = compute_ranked_matches_for_student(user)

    my_sent = {r.to_user_id: r for r in user.outgoing_requests.filter(status__in=['SENT', 'ACCEPTED'])}
    my_received = {r.from_user_id: r for r in user.incoming_requests.filter(status__in=['SENT', 'ACCEPTED'])}

    formatted = []
    for m in ranked:
        peer_id = m['id']
        req_status = None
        req_id = None
        if peer_id in my_sent:
            req = my_sent[peer_id]
            req_status = 'confirmed' if req.status == 'ACCEPTED' else 'sent'
            req_id = req.id
        elif peer_id in my_received:
            req = my_received[peer_id]
            req_status = 'confirmed' if req.status == 'ACCEPTED' else 'pending'
            req_id = req.id

        formatted.append({
            'id': m['id'],
            'name': m['name'],
            'roll_no': m['roll_no'],
            'persona': m['persona'],
            'branch': m['branch'],
            'year': m['year'],
            'block': m['block'],
            'avatar_hue': m['avatar_hue'],
            'score': m['final_score'],
            'good': m['good_reasons'],
            'friction': m['frictions'][0] if m['frictions'] else None,
            'clashes': m['clashes'],
            'is_dealbreaker': m['is_dealbreaker'],
            'request_status': req_status,
            'request_id': req_id,
            'peer_answers': m.get('peer_answers', {}),
            'peer_importance': m.get('peer_importance', {}),
        })

    return JsonResponse({'matches': formatted, 'has_quiz': True})


def api_get_requests(request):
    expire_stale_requests()
    user = get_current_user(request)

    incoming = user.incoming_requests.select_related('from_user').all()
    outgoing = user.outgoing_requests.select_related('to_user').all()

    req_list = []
    for r in incoming:
        score_obj = PairScore.objects.filter(
            Q(user_a=r.from_user, user_b=user) | Q(user_a=user, user_b=r.from_user)
        ).first()
        status_str = 'pending' if r.status == 'SENT' else ('confirmed' if r.status == 'ACCEPTED' else r.status.lower())
        req_list.append({
            'id': r.id,
            'dir': 'in',
            'peer': r.from_user.name,
            'peer_roll': r.from_user.roll_no,
            'peer_avatar_hue': r.from_user.avatar_hue,
            'note': r.note,
            'status': status_str,
            'score': int(score_obj.final_score) if score_obj else 85,
            'ts': int(r.created_at.timestamp() * 1000),
            'expires_at': int(r.expires_at.timestamp() * 1000),
            'is_expired': r.is_expired,
        })

    for r in outgoing:
        score_obj = PairScore.objects.filter(
            Q(user_a=r.to_user, user_b=user) | Q(user_a=user, user_b=r.to_user)
        ).first()
        status_str = 'confirmed' if r.status == 'ACCEPTED' else r.status.lower()
        req_list.append({
            'id': r.id,
            'dir': 'out',
            'peer': r.to_user.name,
            'peer_roll': r.to_user.roll_no,
            'peer_avatar_hue': r.to_user.avatar_hue,
            'note': r.note,
            'status': status_str,
            'score': int(score_obj.final_score) if score_obj else 85,
            'ts': int(r.created_at.timestamp() * 1000),
            'expires_at': int(r.expires_at.timestamp() * 1000),
            'is_expired': r.is_expired,
        })

    req_list.sort(key=lambda x: x['ts'], reverse=True)

    confirmed_count = sum(1 for r in req_list if r['status'] == 'confirmed')
    sent_count = sum(1 for r in req_list if r['dir'] == 'out' and r['status'] == 'sent')
    received_count = sum(1 for r in req_list if r['dir'] == 'in' and r['status'] == 'pending')

    return JsonResponse({
        'requests': req_list,
        'stats': {
            'sent': sent_count,
            'received': received_count,
            'confirmed': confirmed_count,
        }
    })


@csrf_exempt
@require_http_methods(["POST"])
def api_send_request(request):
    calendar = AllotmentCalendar.get_current()
    if calendar.phase != 'MATCHING_OPEN':
        return JsonResponse({
            'error': f"Requests are not permitted in the '{calendar.get_phase_display()}' phase."
        }, status=400)

    try:
        body = json.loads(request.body.decode('utf-8'))
    except Exception:
        return HttpResponseBadRequest("Invalid JSON")

    me = get_current_user(request)
    if me.is_paired:
        return JsonResponse({'error': 'You are already in a confirmed roommate pairing.'}, status=400)

    active_outgoing = me.outgoing_requests.filter(status='SENT').count()
    if active_outgoing >= 3:
        return JsonResponse({'error': 'Limit reached: You can have at most 3 active outgoing requests at a time.'}, status=400)

    receiver_id = body.get('receiver_id')
    peer_name = body.get('peer_name', '').strip()
    note = body.get('note', '').strip()[:150]

    to_user = None
    if receiver_id:
        to_user = StudentUser.objects.filter(id=receiver_id).first()
    elif peer_name:
        to_user = StudentUser.objects.filter(
            Q(name__iexact=peer_name) | Q(roll_no__iexact=peer_name) | Q(name__icontains=peer_name)
        ).first()

    if not to_user:
        return JsonResponse({'error': f'Student "{peer_name}" was not found.'}, status=404)

    if to_user.id == me.id:
        return JsonResponse({'error': 'You cannot send a request to yourself.'}, status=400)

    if to_user.is_paired:
        return JsonResponse({'error': f'{to_user.name} is already paired with another roommate.'}, status=400)

    u1_id = min(me.id, to_user.id)
    u2_id = max(me.id, to_user.id)
    pair_hash = f"{u1_id}_{u2_id}"

    existing = Request.objects.filter(pair_hash=pair_hash, status__in=['SENT', 'ACCEPTED']).first()
    if existing:
        if existing.status == 'ACCEPTED':
            return JsonResponse({'error': f'You and {to_user.name} are already paired!'}, status=400)
        return JsonResponse({'error': f'An active request between you and {to_user.name} is already open.'}, status=400)

    req = Request.objects.create(
        from_user=me,
        to_user=to_user,
        note=note,
        status='SENT'
    )

    AuditLog.objects.create(
        actor=me.name,
        action='REQUEST_SENT',
        target=f"{me.roll_no} -> {to_user.roll_no}",
        reason=note or "Roommate pairing request"
    )

    return JsonResponse({
        'ok': True,
        'id': req.id,
        'message': f"Request sent to {to_user.name}. Valid for 48 hours."
    })


@csrf_exempt
@require_http_methods(["POST"])
def api_respond_request(request, request_id):
    calendar = AllotmentCalendar.get_current()
    if calendar.phase != 'MATCHING_OPEN':
        return JsonResponse({
            'error': f"Requests cannot be answered in the '{calendar.get_phase_display()}' phase."
        }, status=400)

    try:
        body = json.loads(request.body.decode('utf-8'))
    except Exception:
        return HttpResponseBadRequest("Invalid JSON")

    action = body.get('action')  # 'accept' or 'decline'
    me = get_current_user(request)

    with transaction.atomic():
        try:
            req = Request.objects.select_for_update().get(id=request_id)
        except Request.DoesNotExist:
            return JsonResponse({'error': 'Request not found.'}, status=404)

        if req.to_user != me and req.from_user != me:
            return HttpResponseForbidden("Not authorized for this request.")

        if req.status != 'SENT' or req.is_expired:
            return JsonResponse({'error': 'This request is no longer active or has expired.'}, status=400)

        u_a = req.from_user
        u_b = req.to_user

        if Pair.objects.filter(Q(user_a=u_a) | Q(user_b=u_a) | Q(user_a=u_b) | Q(user_b=u_b)).exists():
            req.status = 'CANCELLED'
            req.save()
            return JsonResponse({'error': 'One of the students has already confirmed another pairing.'}, status=400)

        if action == 'accept':
            req.status = 'ACCEPTED'
            req.save()

            first_u, second_u = (u_a, u_b) if u_a.id < u_b.id else (u_b, u_a)
            pair = Pair.objects.create(
                user_a=first_u,
                user_b=second_u,
                method='MUTUAL_REQUEST',
                status='CONFIRMED'
            )

            cancelled_count = Request.objects.filter(
                Q(from_user__in=[u_a, u_b]) | Q(to_user__in=[u_a, u_b]),
                status='SENT'
            ).exclude(id=req.id).update(status='CANCELLED')

            AuditLog.objects.create(
                actor=me.name,
                action='MUTUAL_PAIR_CONFIRMED',
                target=f"{first_u.roll_no} & {second_u.roll_no}",
                reason=f"Mutual request confirmed. Cancelled {cancelled_count} other conflicting requests."
            )

            return JsonResponse({
                'ok': True,
                'status': 'confirmed',
                'message': f"Pairing confirmed between {first_u.name} and {second_u.name}! Ready for warden room allotment."
            })

        elif action == 'decline':
            req.status = 'DECLINED'
            req.save()
            AuditLog.objects.create(
                actor=me.name,
                action='REQUEST_DECLINED',
                target=f"{req.from_user.roll_no} -> {req.to_user.roll_no}",
                reason="Student declined pairing"
            )
            return JsonResponse({'ok': True, 'status': 'declined', 'message': 'Request declined.'})

    return HttpResponseBadRequest("Invalid action.")


@csrf_exempt
@require_http_methods(["POST"])
def api_cancel_request(request, request_id):
    me = get_current_user(request)
    req = get_object_or_404(Request, id=request_id)
    if req.from_user != me:
        return HttpResponseForbidden("You can only cancel your own outgoing requests.")
    req.status = 'CANCELLED'
    req.save()
    return JsonResponse({'ok': True, 'message': 'Request cancelled.'})


# ==========================================
# ADMIN & WARDEN CONTROL ENDPOINTS
# ==========================================

@require_http_methods(["POST"])
def api_set_calendar_phase(request):
    try:
        body = json.loads(request.body.decode('utf-8'))
    except Exception:
        return HttpResponseBadRequest("Invalid JSON")

    new_phase = body.get('phase')
    valid_phases = dict(AllotmentCalendar.PHASE_CHOICES).keys()
    if new_phase not in valid_phases:
        return JsonResponse({'error': 'Invalid phase'}, status=400)

    cal = AllotmentCalendar.get_current()
    old_phase = cal.phase
    cal.phase = new_phase
    cal.updated_by = get_current_user(request).name
    cal.save()

    AuditLog.objects.create(
        actor=cal.updated_by,
        action='PHASE_CHANGE',
        target=f"{old_phase} -> {new_phase}",
        reason="Admin advanced calendar phase"
    )

    return JsonResponse({
        'ok': True,
        'phase': cal.phase,
        'phase_name': cal.get_phase_display(),
        'message': f"System phase changed to {cal.get_phase_display()}."
    })


@require_http_methods(["POST"])
def api_run_blossom_matching(request):
    user = get_current_user(request)
    count, pairs = run_blossom_leftover_matching(actor=user.name)
    return JsonResponse({
        'ok': True,
        'matched_count': count,
        'message': f"Blossom maximum-weight algorithm paired {count} remaining student groups optimally!"
    })


@require_http_methods(["POST"])
def api_auto_allot_rooms(request):
    user = get_current_user(request)
    count = run_automated_room_allotment(actor=user.name)
    return JsonResponse({
        'ok': True,
        'allotted_count': count,
        'message': f"Successfully allotted rooms to {count} confirmed pairs!"
    })


@require_http_methods(["POST"])
def api_warden_allot(request, pairing_id):
    try:
        body = json.loads(request.body.decode('utf-8'))
    except Exception:
        return HttpResponseBadRequest("Invalid JSON")

    room_number = body.get('room_number', '').strip()
    reason = body.get('reason', '').strip() or "Standard Warden room allotment"

    pairing = get_object_or_404(Pair, id=pairing_id)
    blk = pairing.user_a.block or HostelBlock.objects.first()

    room, _ = Room.objects.get_or_create(
        block=blk,
        number=room_number,
        defaults={'capacity': 2, 'floor': 1}
    )

    pairing.room = room
    pairing.status = 'ALLOTTED'
    pairing.save()

    Allotment.objects.update_or_create(room=room, user=pairing.user_a, defaults={'is_active': True})
    Allotment.objects.update_or_create(room=room, user=pairing.user_b, defaults={'is_active': True})

    AuditLog.objects.create(
        actor=get_current_user(request).name,
        action='WARDEN_ALLOT_ROOM',
        target=f"{pairing.user_a.roll_no} & {pairing.user_b.roll_no} -> {room.number}",
        reason=reason
    )

    return JsonResponse({
        'ok': True,
        'status': pairing.status,
        'room_number': room.number,
        'message': f"Room {room.number} officially allotted to {pairing.user_a.name} & {pairing.user_b.name}."
    })

# ==========================================
# AUTHENTICATION & MULTI-ROLE VIEWS
# ==========================================

def login_view(request):
    """Unified login portal for Students, Wardens, Caretakers, and Admins."""
    role = request.GET.get('role', 'student')
    students = StudentUser.objects.filter(role='student').order_by('name')[:6]
    warden = StudentUser.objects.filter(role='warden').first()
    caretaker = StudentUser.objects.filter(role='caretaker').first()
    admin = StudentUser.objects.filter(role='admin').first()

    context = {
        'initial_role': role,
        'demo_students': students,
        'demo_warden': warden,
        'demo_caretaker': caretaker,
        'demo_admin': admin,
    }
    return render(request, 'matcher/login.html', context)



@csrf_exempt
@require_http_methods(["POST"])
def api_send_otp(request):
    """Generates and securely stores a hashed 6-digit OTP with rate limiting & expiration."""
    try:
        body = json.loads(request.body.decode('utf-8'))
    except Exception:
        return HttpResponseBadRequest("Invalid JSON")

    identity = body.get('identity', '').strip()
    if not identity:
        return JsonResponse({'error': 'Please provide your Roll Number or College Email.'}, status=400)

    user = StudentUser.objects.filter(
        Q(roll_no__iexact=identity) | Q(email__iexact=identity)
    ).first()

    if not user:
        user = StudentUser.objects.filter(name__icontains=identity, role='student').first()

    if not user:
        return JsonResponse({'error': f'No registered student found matching "{identity}".'}, status=404)

    if user.is_locked():
        wait_min = max(1, int((user.locked_until - timezone.now()).total_seconds() // 60) + 1)
        return JsonResponse({'error': f'Account locked due to multiple failed login attempts. Try again in {wait_min} minutes.'}, status=423)

    # Rate limiting: 60-second cooldown per student
    last_otp = OTPVerification.objects.filter(user=user).order_by('-created_at').first()
    if last_otp and not last_otp.is_expired:
        elapsed = (timezone.now() - last_otp.created_at).total_seconds()
        if elapsed < 60:
            remaining = int(60 - elapsed)
            return JsonResponse({'error': f'Rate limit: Please wait {remaining}s before requesting a new OTP.'}, status=429)

    # Cryptographically secure 6-digit OTP
    raw_otp = "".join(secrets.choice("0123456789") for _ in range(6))

    # Invalidate previous unused OTPs for this user
    OTPVerification.objects.filter(user=user, is_used=False).update(is_used=True)

    # Store hashed OTP in database
    OTPVerification.objects.create(
        user=user,
        otp_hash=make_password(raw_otp),
        expires_at=timezone.now() + timedelta(minutes=5),
        attempts_left=3,
        ip_address=request.META.get('REMOTE_ADDR', '')
    )

    AuditLog.objects.create(
        actor=user.name,
        action='AUTH_OTP_REQUESTED',
        target=f"{user.roll_no} ({user.email})",
        reason="Generated secure login OTP (valid for 5 mins, max 3 attempts)"
    )

    return JsonResponse({
        'ok': True,
        'message': f'Verification OTP sent to {user.email} (valid 5 min)',
        'demo_otp': raw_otp,
        'user_name': user.name,
        'roll_no': user.roll_no,
        'expires_in': 300,
    })


@csrf_exempt
@require_http_methods(["POST"])
def api_login(request):
    try:
        body = json.loads(request.body.decode('utf-8'))
    except Exception:
        return HttpResponseBadRequest("Invalid JSON")

    role = body.get('role', 'student').strip().lower()
    identity = body.get('identity', '').strip()
    secret = body.get('secret', '').strip()

    if not identity:
        return JsonResponse({'error': 'Please provide your Roll Number, Staff ID, or Email.'}, status=400)
    if not secret:
        return JsonResponse({'error': 'Please provide your Password, Passcode, or OTP code.'}, status=400)

    # Lookup user
    user = StudentUser.objects.filter(
        Q(roll_no__iexact=identity) | Q(email__iexact=identity)
    ).first()

    if not user:
        user = StudentUser.objects.filter(name__icontains=identity, role=role).first()

    if not user:
        return JsonResponse({'error': f'No registered account found with identifier "{identity}" for role {role}.'}, status=404)

    # Check if account is locked
    if user.is_locked():
        wait_min = max(1, int((user.locked_until - timezone.now()).total_seconds() // 60) + 1)
        AuditLog.objects.create(
            actor=identity,
            action='AUTH_LOGIN_BLOCKED_LOCKED',
            target=user.roll_no,
            reason=f"Account locked until {user.locked_until.strftime('%H:%M')}"
        )
        return JsonResponse({'error': f'Account locked due to consecutive failed attempts. Try again in {wait_min} minutes.'}, status=423)

    # Role validation
    if role == 'warden' and user.role not in ['warden', 'admin']:
        return JsonResponse({'error': 'This account does not have Warden staff privileges.'}, status=403)
    if role == 'caretaker' and user.role not in ['caretaker', 'warden', 'admin']:
        return JsonResponse({'error': 'This account does not have Caretaker staff privileges.'}, status=403)
    if role == 'admin' and user.role != 'admin':
        return JsonResponse({'error': 'This account does not have Administrator privileges.'}, status=403)

    # Verification based on role:
    if role == 'student':
        # Verify 6-digit OTP from OTPVerification table
        otp_record = OTPVerification.objects.filter(
            user=user, is_used=False
        ).order_by('-created_at').first()

        # Demo bypass fallback if secret matches known demo secret or newly requested OTP
        verified = False
        if otp_record and not otp_record.is_expired and otp_record.attempts_left > 0:
            if otp_record.verify(secret):
                verified = True
            else:
                user.record_failed_login()
                rem = otp_record.attempts_left
                attempts_msg = f"{rem} attempt(s) remaining" if rem > 0 else "OTP is now permanently invalidated"
                AuditLog.objects.create(
                    actor=identity,
                    action='AUTH_LOGIN_FAILED_BAD_OTP',
                    target=user.roll_no,
                    reason=f"Wrong OTP entered ({attempts_msg})"
                )
                return JsonResponse({'error': f'Incorrect OTP code. {attempts_msg}.'}, status=400)
        elif secret in ['482910', '739102', '519284', '391048']:
            # Seeded demo OTP fallback
            verified = True
        else:
            user.record_failed_login()
            AuditLog.objects.create(
                actor=identity,
                action='AUTH_LOGIN_FAILED_NO_OTP',
                target=user.roll_no,
                reason="No active unexpired OTP found"
            )
            return JsonResponse({'error': 'No active OTP found or code has expired. Please click "Send OTP" to receive a new code.'}, status=400)

    else:
        # Staff role: PBKDF2 Password Check
        password_ok = user.check_password(secret)
        # Fallback for initial demo seed if not yet hashed
        if not password_ok:
            if role == 'warden' and secret == 'warden123':
                password_ok = True
                user.set_password(secret)
            elif role == 'caretaker' and secret == 'caretaker123':
                password_ok = True
                user.set_password(secret)
            elif role == 'admin' and secret == 'admin123':
                password_ok = True
                user.set_password(secret)

        if not password_ok:
            user.record_failed_login()
            AuditLog.objects.create(
                actor=identity,
                action='AUTH_LOGIN_FAILED_BAD_PASSWORD',
                target=f"{user.roll_no} ({role})",
                reason=f"Incorrect {role} password/passcode"
            )
            return JsonResponse({'error': f'Invalid credentials for {role.capitalize()} account.'}, status=400)

    # Login successful! Reset failed attempts
    user.reset_failed_logins(ip_address=request.META.get('REMOTE_ADDR', ''))

    # Prevent session fixation
    request.session.cycle_key()
    request.session['current_user_id'] = user.id
    request.session['user_role'] = user.role
    request.session.set_expiry(86400 * 7) # 7-day session

    # Audit login success
    AuditLog.objects.create(
        actor=user.name,
        action='AUTH_LOGIN_SUCCESS',
        target=f"{user.roll_no} ({user.role})",
        reason=f"Signed in successfully to {role.capitalize()} Portal"
    )

    # Role-based redirection target
    redirect_map = {
        'student': '/student/',
        'warden': '/warden/',
        'caretaker': '/caretaker/',
        'admin': '/admin-portal/',
    }
    redirect_url = redirect_map.get(user.role, '/student/')

    return JsonResponse({
        'ok': True,
        'id': user.id,
        'name': user.name,
        'role': user.role,
        'redirect_url': redirect_url,
        'message': f"Authenticated as {user.name} ({user.role.capitalize()})"
    })


def logout_view(request):
    """Safely flushes user session and redirects to login."""
    current_user_id = request.session.get('current_user_id')
    if current_user_id:
        user = StudentUser.objects.filter(id=current_user_id).first()
        if user:
            AuditLog.objects.create(
                actor=user.name,
                action='USER_LOGOUT',
                target=f"{user.roll_no}",
                reason="Explicit session logout"
            )
    request.session.flush()
    return redirect('/login/?msg=logged_out')


# ==========================================
# CARETAKER FACILITY DESK VIEWS
# ==========================================

def caretaker_dashboard_view(request):
    """Caretaker desk: view room occupancy, manage check-in/check-out and key issuance."""
    rooms = Room.objects.all().select_related('block').prefetch_related('allotments__user')
    allotments = Allotment.objects.filter(is_active=True).select_related('room', 'user')

    rooms_data = []
    for rm in rooms:
        rm_allotments = list(rm.allotments.filter(is_active=True).select_related('user'))
        rooms_data.append({
            'room': rm,
            'allotments': rm_allotments,
            'is_occupied': len(rm_allotments) > 0,
        })

    total_rooms = rooms.count()
    total_capacity = sum(r.capacity for r in rooms)
    total_allotted = allotments.count()
    checked_in_count = allotments.filter(checked_in=True).count()
    keys_issued_count = allotments.filter(key_issued=True).count()

    context = {
        'rooms_data': rooms_data,
        'total_rooms': total_rooms,
        'total_capacity': total_capacity,
        'total_allotted': total_allotted,
        'checked_in_count': checked_in_count,
        'keys_issued_count': keys_issued_count,
    }
    return render(request, 'matcher/caretaker.html', context)


@csrf_exempt
@require_http_methods(["POST"])
def api_caretaker_toggle(request):
    try:
        body = json.loads(request.body.decode('utf-8'))
    except Exception:
        return HttpResponseBadRequest("Invalid JSON")

    allotment_id = body.get('allotment_id')
    action = body.get('action') # 'checkin' or 'key'

    allotment = get_object_or_404(Allotment, id=allotment_id)
    actor_name = get_current_user(request).name

    if action == 'checkin':
        allotment.checked_in = not allotment.checked_in
        allotment.checked_in_at = timezone.now() if allotment.checked_in else None
        allotment.save(update_fields=['checked_in', 'checked_in_at'])
        status_msg = "checked in" if allotment.checked_in else "checked out"
        AuditLog.objects.create(
            actor=actor_name,
            action='CARETAKER_CHECKIN',
            target=f"{allotment.user.roll_no} - {allotment.room}",
            reason=f"Resident marked {status_msg}"
        )
        return JsonResponse({'ok': True, 'message': f"{allotment.user.name} marked as {status_msg}!"})

    elif action == 'key':
        allotment.key_issued = not allotment.key_issued
        allotment.save(update_fields=['key_issued'])
        status_msg = "handed over" if allotment.key_issued else "recalled to desk"
        AuditLog.objects.create(
            actor=actor_name,
            action='CARETAKER_KEY',
            target=f"{allotment.user.roll_no} - {allotment.room}",
            reason=f"Key {status_msg}"
        )
        return JsonResponse({'ok': True, 'message': f"Key for {allotment.room.number} {status_msg} for {allotment.user.name}!"})

    return HttpResponseBadRequest("Invalid action type")


# ==========================================
# ADMIN GOVERNANCE & ROSTER VIEWS
# ==========================================

def admin_dashboard_view(request):
    """Allotment Admin portal: calendar phases, blocks overview, roster, and audit log."""
    calendar = AllotmentCalendar.get_current()
    students = StudentUser.objects.filter(role='student').order_by('name')
    pairs = Pair.objects.all().select_related('user_a', 'user_b', 'room')
    allotments = Allotment.objects.filter(is_active=True)
    audit_logs = AuditLog.objects.all().order_by('-timestamp')[:30]

    paired_ids = set(pairs.values_list('user_a_id', flat=True)) | set(pairs.values_list('user_b_id', flat=True))
    unpaired_students = students.exclude(id__in=paired_ids)

    context = {
        'calendar': calendar,
        'phases': AllotmentCalendar.PHASE_CHOICES,
        'students': students,
        'total_students': students.count(),
        'confirmed_pairs': pairs.count(),
        'allotted_count': pairs.filter(status='ALLOTTED').count(),
        'unpaired_count': unpaired_students.count(),
        'audit_logs': audit_logs,
    }
    return render(request, 'matcher/admin.html', context)


def api_admin_export_csv(request):
    """Generates and downloads the official master allotment report as CSV."""
    import csv
    from django.http import HttpResponse

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="kindred_allotments_master.csv"'

    writer = csv.writer(response)
    writer.writerow([
        'Hostel Block', 'Room Number', 'Student 1 Name', 'Student 1 Roll',
        'Student 2 Name', 'Student 2 Roll', 'Pairing Method', 'Allotment Status', 'Date Confirmed'
    ])

    pairs = Pair.objects.all().select_related('user_a', 'user_b', 'room', 'room__block')
    for p in pairs:
        blk = p.room.block.name if p.room else (p.user_a.block.name if p.user_a.block else "Main Hostel")
        rm_num = p.room.number if p.room else "Unassigned"
        writer.writerow([
            blk, rm_num,
            p.user_a.name, p.user_a.roll_no,
            p.user_b.name, p.user_b.roll_no,
            p.get_method_display(), p.get_status_display(),
            p.confirmed_at.strftime('%Y-%m-%d %H:%M')
        ])

    return response
