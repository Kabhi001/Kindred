import secrets
import threading
from functools import wraps
from django.contrib.auth.hashers import make_password, check_password
import json
from datetime import timedelta
from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse, HttpResponseBadRequest, HttpResponseForbidden
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import ensure_csrf_cookie
from django.core.mail import send_mail
from django.utils import timezone
from django.db import transaction
from django.db.models import Q
from django.conf import settings

from .models import (
    HostelBlock, Room, StudentUser, AllotmentCalendar,
    Question, Response, PairScore, Request, Pair, Allotment, AuditLog, OTPVerification,
    GuardianConsent, Ticket, Feedback, Notification
)
from .scoring import (
    calculate_mutual_score, compute_ranked_matches_for_student,
    run_blossom_leftover_matching, run_automated_room_allotment
)
from .matching import calculate_persona, encode_profile_code, decode_profile_code


def get_current_user(request):
    """Retrieves the authenticated StudentUser from session, or returns None."""
    user_id = request.session.get('current_user_id')
    if user_id:
        return StudentUser.objects.filter(id=user_id).first()
    return None


def login_required_api(view_func):
    """
    Reusable view decorator ensuring the user is authenticated as a StudentUser.
    Returns 401 Unauthorized for API endpoints if not authenticated.
    Attaches authenticated student to request.current_user.
    """
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        user = get_current_user(request)
        if not user:
            return JsonResponse({'error': 'Authentication required. Please sign in.'}, status=401)
        request.current_user = user
        return view_func(request, *args, **kwargs)
    return _wrapped

# Maintain alias for backward compatibility
login_required_custom = login_required_api


def send_mail_async(subject, message, from_email, recipient_list, fail_silently=False):
    """
    Hands off OTP and notification emails to an asynchronous background worker
    thread so the user's HTTP request cycle is not blocked by slow SMTP servers.
    In testing environments with locmem backend, executes immediately to ensure
    test assertions on mail.outbox remain completely deterministic.
    """
    def _send():
        try:
            send_mail(
                subject=subject,
                message=message,
                from_email=from_email,
                recipient_list=recipient_list,
                fail_silently=fail_silently,
            )
        except Exception:
            pass

    is_test_env = getattr(settings, 'EMAIL_BACKEND', '') == 'django.core.mail.backends.locmem.EmailBackend'
    if is_test_env:
        _send()
        return None

    thread = threading.Thread(target=_send, daemon=True)
    thread.start()
    return thread


def role_required(allowed_roles):
    """
    Decorator for views that checks the user is authenticated and has one of the allowed roles.
    allowed_roles: list, tuple, or set of role strings, e.g. ['admin'] or ['warden', 'admin']
    Returns 401 if not logged in, or 403 Forbidden if user lacks the required role.
    """
    if isinstance(allowed_roles, str):
        allowed_roles = [allowed_roles]

    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            user = get_current_user(request)
            if not user:
                return JsonResponse({'error': 'Authentication required. Please sign in.'}, status=401)
            if user.role not in allowed_roles:
                return JsonResponse({
                    'error': f'Access denied. Required role: {", ".join(allowed_roles)}.'
                }, status=403)
            return view_func(request, *args, **kwargs)
        return _wrapped_view
    return decorator


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

    sample_student = StudentUser.objects.filter(role='student', roll_no='12310266').first() or StudentUser.objects.filter(role='student').first()
    sample_warden = StudentUser.objects.filter(role='warden').first()
    sample_admin = StudentUser.objects.filter(role='admin').first()

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
        'sample_student': sample_student,
        'sample_warden': sample_warden,
        'sample_admin': sample_admin,
    }
    return render(request, 'matcher/home.html', context)


@ensure_csrf_cookie
def index_view(request):
    current_user = get_current_user(request)
    if not current_user or current_user.role != 'student':
        return redirect('/login/?role=student')
    calendar = AllotmentCalendar.get_current()
    pairings_count = Pair.objects.count()
    all_blocks = HostelBlock.objects.all().order_by('name')

    context = {
        'current_student': current_user,
        'calendar': calendar,
        'pairings_count': pairings_count,
        'blocks': all_blocks,
    }
    return render(request, 'matcher/index.html', context)


@ensure_csrf_cookie
def warden_dashboard_view(request):
    current_user = get_current_user(request)
    if not current_user or current_user.role not in ['warden', 'admin']:
        return redirect('/login/?role=warden')
    expire_stale_requests()
    calendar = AllotmentCalendar.get_current()
    pairs = Pair.objects.select_related('user_a', 'user_b', 'room', 'room__block').all().order_by('-confirmed_at')
    
    paired_ids = set(pairs.values_list('user_a_id', flat=True)) | set(pairs.values_list('user_b_id', flat=True))
    all_students = StudentUser.objects.filter(role='student').select_related('block').order_by('name')
    unpaired_students = [s for s in all_students if s.id not in paired_ids]

    vacant_rooms = Room.objects.filter(pairs__isnull=True).select_related('block')
    audit_logs = AuditLog.objects.all().order_by('-timestamp')[:25]
    tickets = Ticket.objects.select_related('student').order_by('-created_at')[:25]
    open_tickets_count = Ticket.objects.filter(status='OPEN').count()

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
        'current_user': current_user,
        'calendar': calendar,
        'pairs_data': pairs_data,
        'unpaired_students': unpaired_students,
        'vacant_rooms': vacant_rooms,
        'audit_logs': audit_logs,
        'tickets': tickets,
        'open_tickets_count': open_tickets_count,
        'total_students_count': all_students.count(),
        'confirmed_pairs_count': pairs.count(),
        'allotted_count': pairs.filter(status='ALLOTTED').count(),
        'pending_requests_count': Request.objects.filter(status='SENT').count(),
    }
    return render(request, 'matcher/warden.html', context)


# ==========================================
# REST / JSON API ENDPOINTS
# ==========================================

@require_http_methods(["GET"])
@login_required_api
def api_me(request):
    expire_stale_requests()
    user = get_current_user(request)
    if not user:
        return JsonResponse({'error': 'Authentication required. Please sign in.'}, status=401)
    calendar = AllotmentCalendar.get_current()
    
    responses = Response.objects.filter(user=user).select_related('question')
    answers = {r.question.key: r.answer for r in responses}
    importance = {r.question.key: r.importance for r in responses}
    dealbreakers = {r.question.key: getattr(r, 'is_dealbreaker', False) or (r.importance == 3) for r in responses}
    has_quiz = user.has_completed_survey

    pair = user.get_pair()
    pair_info = None
    if pair:
        partner = pair.partner_of(user)
        pair_info = {
            'partner_name': partner.name,
            'partner_roll': partner.roll_no,
            'partner_registration_no': partner.roll_no,
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
        'registration_no': user.roll_no,
        'email': user.email,
        'gender': user.get_gender_display(),
        'gender_code': user.gender,
        'phone': user.phone,
        'year': user.year,
        'branch': user.branch,
        'role': user.role,
        'persona': user.persona,
        'avatar_hue': user.avatar_hue,
        'block': user.block.name if user.block else "Main Hostel",
        'block_id': user.block_id if user.block else None,
        'all_blocks': [
            {
                'id': b.id,
                'name': b.name,
                'hostel': b.hostel_name,
                'block': b.block_name,
                'gender': b.gender,
                'gender_display': b.get_gender_display(),
            }
            for b in HostelBlock.objects.all().order_by('name')
        ],
        'consent_given': user.consent_given,
        'has_quiz': has_quiz,
        'answers': answers,
        'importance': importance,
        'dealbreakers': dealbreakers,
        'is_paired': bool(pair),
        'pairing': pair_info,
        'profile_code': encode_profile_code({'n': user.name, 'p': user.persona, 'a': answers, 'i': importance}) if has_quiz else "",
        'calendar': {
            'phase': calendar.phase,
            'phase_name': calendar.get_phase_display(),
            'can_survey': calendar.phase in ['SURVEY_OPEN', 'MATCHING_OPEN'],
            'can_match': calendar.phase == 'MATCHING_OPEN',
            'is_frozen': calendar.phase in ['FREEZE', 'LEFTOVER_PAIRING', 'WARDEN_ALLOTMENT', 'PUBLISHED'],
            'is_published': calendar.phase == 'PUBLISHED',
        },
        'unread_notifications_count': user.notifications.filter(is_read=False).count(),
        'notifications': [
            {
                'id': n.id,
                'title': n.title,
                'message': n.message,
                'category': n.category,
                'is_read': n.is_read,
                'created_at': n.created_at.strftime('%Y-%m-%d %H:%M')
            }
            for n in user.notifications.all()[:10]
        ]
    }
    return JsonResponse(data)


@require_http_methods(["POST"])
@login_required_api
def api_update_profile(request):
    """
    Allows a student to correct or update their profile details in real time.
    Saves updates immediately to the database and refreshes compatibility.
    """
    user = get_current_user(request)
    if not user:
        return JsonResponse({'error': 'Authentication required. Please sign in.'}, status=401)
    
    try:
        data = json.loads(request.body.decode('utf-8'))
    except Exception:
        return JsonResponse({'error': 'Invalid JSON format.'}, status=400)

    name = data.get('name', '').strip()
    roll_no = data.get('roll_no', '').strip()
    email = data.get('email', '').strip()
    gender = data.get('gender', '').strip()
    year = data.get('year', '').strip()
    branch = data.get('branch', '').strip()
    phone = data.get('phone', '').strip()
    block_id = data.get('block_id')

    if not name:
        return JsonResponse({'error': 'Full name cannot be empty.'}, status=400)
    if not roll_no:
        return JsonResponse({'error': 'Registration number cannot be empty.'}, status=400)

    # Validate uniqueness of roll_no if changed
    old_roll = user.roll_no
    if roll_no != user.roll_no:
        if StudentUser.objects.filter(roll_no=roll_no).exclude(id=user.id).exists():
            return JsonResponse({'error': f'Registration number "{roll_no}" is already registered by another student.'}, status=400)
        user.roll_no = roll_no

    # Validate uniqueness of email if changed
    if email and email != user.email:
        if StudentUser.objects.filter(email=email).exclude(id=user.id).exists():
            return JsonResponse({'error': f'Email address "{email}" is already in use.'}, status=400)
        user.email = email

    gender_or_block_changed = False
    if gender in ['M', 'F', 'O'] and gender != user.gender:
        user.gender = gender
        gender_or_block_changed = True

    if block_id is not None and str(block_id).strip() != "":
        try:
            b_id = int(block_id)
            if b_id != user.block_id:
                new_block = HostelBlock.objects.filter(id=b_id).first()
                if new_block:
                    user.block = new_block
                    gender_or_block_changed = True
        except (ValueError, TypeError):
            pass

    user.name = name
    if year:
        user.year = year
    if branch:
        user.branch = branch
    if phone is not None:
        user.phone = phone

    user.save()

    # If hostel block or gender changed, invalidate cached PairScore entries to trigger real-time recalculation
    if gender_or_block_changed:
        PairScore.objects.filter(Q(user_a=user) | Q(user_b=user)).delete()

    # Record audit trail
    AuditLog.objects.create(
        actor=user.name,
        action="PROFILE_UPDATED",
        target=user.roll_no,
        reason=f"Student updated profile details in real time. (Old Reg: {old_roll} -> {user.roll_no}, Hostel: {user.block.name if user.block else 'None'})"
    )

    return JsonResponse({
        'success': True,
        'message': 'Profile details updated and saved successfully!',
        'user': {
            'id': user.id,
            'name': user.name,
            'roll_no': user.roll_no,
            'email': user.email,
            'gender': user.get_gender_display(),
            'gender_code': user.gender,
            'year': user.year,
            'branch': user.branch,
            'phone': user.phone,
            'block': user.block.name if user.block else "Main Hostel",
            'block_id': user.block_id if user.block else None,
            'persona': user.persona
        }
    })


@require_http_methods(["POST"])
@login_required_api
def api_consent_agree(request):
    user = get_current_user(request)
    if not user:
        return JsonResponse({'error': 'Authentication required.'}, status=401)
    user.consent_given = True
    user.consent_at = timezone.now()
    user.save(update_fields=['consent_given', 'consent_at'])
    return JsonResponse({'ok': True, 'message': 'Consent recorded under DPDP Act 2023.'})


@require_http_methods(["POST"])
def api_switch_student(request):
    if not settings.DEBUG:
        return HttpResponseForbidden("Student account switching is disabled outside debug mode.")

    try:
        body = json.loads(request.body.decode('utf-8'))
    except Exception:
        return HttpResponseBadRequest("Invalid JSON")

    user_id = body.get('student_id')
    user = StudentUser.objects.filter(id=user_id).first()
    if not user:
        return JsonResponse({'error': 'User not found'}, status=404)

    if not getattr(user, 'is_demo', False):
        return HttpResponseForbidden("Cannot switch to non-demo accounts.")

    request.session.cycle_key()
    request.session['current_user_id'] = user.id
    request.session['user_role'] = user.role
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
            'registration_no': s.roll_no,
            'persona': s.persona,
            'branch': s.branch,
            'block': s.block.name if s.block else "Main Hostel",
            'is_current': (s.id == current.id) if current else False,
            'is_paired': s.is_paired,
        })
    return JsonResponse({'students': data})


@require_http_methods(["POST"])
@login_required_api
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
    if not user:
        return JsonResponse({'error': 'Authentication required.'}, status=401)
    if not user.consent_given:
        user.consent_given = True
        user.consent_at = timezone.now()

    name = body.get('name', '').strip()
    if name:
        user.name = name

    answers = body.get('answers', {})
    importance = body.get('importance', {})
    dealbreakers = body.get('dealbreakers', {})

    user.persona = calculate_persona(answers)
    user.save()

    questions = {q.key: q for q in Question.objects.filter(is_active=True)}
    for key, val in answers.items():
        if key in questions:
            imp_val = importance.get(key, 2)
            if isinstance(dealbreakers, dict):
                is_db = bool(dealbreakers.get(key, False)) or (int(imp_val) == 3)
            elif isinstance(dealbreakers, list):
                is_db = (key in dealbreakers) or (int(imp_val) == 3)
            else:
                is_db = (int(imp_val) == 3)

            Response.objects.update_or_create(
                user=user,
                question=questions[key],
                defaults={
                    'answer': int(val),
                    'importance': int(imp_val),
                    'is_dealbreaker': is_db
                }
            )

    PairScore.objects.filter(Q(user_a=user) | Q(user_b=user)).delete()

    return JsonResponse({
        'ok': True,
        'name': user.name,
        'persona': user.persona,
        'message': 'Survey responses saved and persona calculated!'
    })


@require_http_methods(["GET"])
@login_required_api
def api_matches(request):
    calendar = AllotmentCalendar.get_current()
    if calendar.phase not in ['MATCHING_OPEN', 'LEFTOVER_PAIRING', 'WARDEN_ALLOTMENT', 'PUBLISHED']:
        return JsonResponse({'matches': [], 'has_quiz': False, 'message': 'Matching is not open yet.'})

    user = get_current_user(request)
    if not user:
        return JsonResponse({'error': 'Authentication required.', 'matches': [], 'has_quiz': False}, status=401)
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

        # Determine qualitative harmony band
        score_val = m['final_score']
        has_clash = m['is_dealbreaker']
        if score_val >= 85 and not has_clash:
            band_title = "Natural Harmony"
            band_code = "HARMONY"
        elif score_val >= 70 and not has_clash:
            band_title = "Compatible with Adaptation"
            band_code = "ADAPTATION"
        else:
            band_title = "High Friction Risk"
            band_code = "RISK"

        # Privacy Seal: Anonymize specific clash dimensions into generic rhythm label
        clash_labels = ["Major lifestyle rhythm mismatch"] if has_clash else []

        formatted.append({
            'id': m['id'],
            'name': m['name'],
            'roll_no': m['roll_no'],
            'registration_no': m['roll_no'],
            'persona': m['persona'],
            'branch': m['branch'],
            'year': m['year'],
            'block': m['block'],
            'avatar_hue': m['avatar_hue'],
            'score': m['final_score'],
            'harmony_band': {
                'title': band_title,
                'code': band_code
            },
            'good': m['good_reasons'],
            'friction': m['frictions'][0] if m['frictions'] else None,
            'clashes': clash_labels,
            'has_clash': has_clash,
            'is_dealbreaker': has_clash,
            'request_status': req_status,
            'request_id': req_id,
        })

    return JsonResponse({'matches': formatted, 'has_quiz': True})


@require_http_methods(["GET"])
@login_required_api
def api_get_requests(request):
    expire_stale_requests()
    user = get_current_user(request)
    if not user:
        return JsonResponse({'error': 'Authentication required.', 'requests': []}, status=401)

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


@require_http_methods(["POST"])
@login_required_api
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
    if not me:
        return JsonResponse({'error': 'Authentication required.'}, status=401)
    if me.is_paired:
        return JsonResponse({'error': 'You are already in a confirmed roommate pairing.'}, status=400)

    active_outgoing = me.outgoing_requests.filter(status='SENT').count()
    if active_outgoing >= 3:
        return JsonResponse({'error': 'Limit reached: You can have at most 3 active outgoing requests at a time.'}, status=400)

    receiver_id = body.get('receiver_id')
    peer_roll_no = (body.get('peer_registration_no') or body.get('peer_roll_no', '')).strip()
    peer_name = body.get('peer_name', '').strip()
    note = body.get('note', '').strip()[:150]

    to_user = None
    if receiver_id:
        to_user = StudentUser.objects.filter(id=receiver_id).first()
    elif peer_roll_no:
        to_user = StudentUser.objects.filter(roll_no__iexact=peer_roll_no).first()
    elif peer_name:
        to_user = StudentUser.objects.filter(
            Q(roll_no__iexact=peer_name) | Q(name__iexact=peer_name) | Q(name__icontains=peer_name)
        ).first()

    lookup_identifier = peer_roll_no or peer_name or str(receiver_id)
    if not to_user:
        return JsonResponse({'error': f'Student "{lookup_identifier}" was not found.'}, status=404)

    if to_user.id == me.id:
        return JsonResponse({'error': 'You cannot send a pairing request to yourself.'}, status=400)

    if to_user.is_paired:
        return JsonResponse({'error': f'{to_user.name} is already paired with another roommate.'}, status=400)

    # Strict Same-Gender Roommate Policy (Male-to-Male and Female-to-Female only)
    if to_user.gender != me.gender:
        return JsonResponse({'error': 'Hostel regulations require roommates to be of the same gender (Male-to-Male and Female-to-Female only). Cross-gender pairing is not permitted.'}, status=400)

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
        reason=note or "Direct friend pairing request"
    )

    # Real-time transaction notification for recipient
    Notification.objects.create(
        student=to_user,
        category='REQUEST',
        title=f"Pairing Request from {me.name}",
        message=f"{me.name} ({me.roll_no}) sent you a roommate pairing request. Note: '{note or 'Let us pair up!'}'"
    )

    return JsonResponse({
        'ok': True,
        'id': req.id,
        'message': f"Request sent to {to_user.name} ({to_user.roll_no}). Valid for 48 hours."
    })


@require_http_methods(["POST"])
@login_required_api
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
    if not me:
        return JsonResponse({'error': 'Authentication required.'}, status=401)

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

            Notification.objects.create(
                student=first_u,
                category='ALLOTMENT',
                title="Roommate Pairing Confirmed! 🎉",
                message=f"You and {second_u.name} ({second_u.roll_no}) are officially paired! Awaiting room allotment by the Warden."
            )
            Notification.objects.create(
                student=second_u,
                category='ALLOTMENT',
                title="Roommate Pairing Confirmed! 🎉",
                message=f"You and {first_u.name} ({first_u.roll_no}) are officially paired! Awaiting room allotment by the Warden."
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


@require_http_methods(["POST"])
@login_required_api
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
@role_required(['admin'])
def api_set_calendar_phase(request):
    try:
        body = json.loads(request.body.decode('utf-8'))
    except Exception:
        return HttpResponseBadRequest("Invalid JSON")

    new_phase = body.get('phase')
    force = body.get('force', False)
    reason = body.get('reason', '').strip()
    valid_phases = dict(AllotmentCalendar.PHASE_CHOICES).keys()
    if new_phase not in valid_phases:
        return JsonResponse({'error': 'Invalid phase'}, status=400)

    cal = AllotmentCalendar.get_current()
    old_phase = cal.phase

    # Guard 1: Cannot transition directly to WARDEN_ALLOTMENT if unpaired students exist without running LEFTOVER_PAIRING
    if new_phase == 'WARDEN_ALLOTMENT' and not force:
        paired_ids = set(Pair.objects.values_list('user_a_id', flat=True)) | set(Pair.objects.values_list('user_b_id', flat=True))
        unpaired_count = StudentUser.objects.filter(role='student').exclude(id__in=paired_ids).count()
        if unpaired_count > 0 and old_phase != 'LEFTOVER_PAIRING':
            return JsonResponse({
                'error': f"Guard check failed: {unpaired_count} student(s) remain unpaired. Please run Phase 5 (Leftover Pairing) first, or pass force=True.",
                'guard_triggered': True,
                'unpaired_count': unpaired_count
            }, status=400)

    # Guard 2: Cannot transition to PUBLISHED if confirmed pairs have no rooms assigned
    if new_phase == 'PUBLISHED' and not force:
        unallotted_count = Pair.objects.filter(status='CONFIRMED', room__isnull=True).count()
        if unallotted_count > 0:
            return JsonResponse({
                'error': f"Guard check failed: {unallotted_count} confirmed pair(s) have not been allotted rooms. Complete room allotments or pass force=True.",
                'guard_triggered': True,
                'unallotted_pairs_count': unallotted_count
            }, status=400)

    user = get_current_user(request)
    cal.phase = new_phase
    cal.updated_by = user.name
    cal.save()

    AuditLog.objects.create(
        actor=user.name,
        action='PHASE_CHANGE',
        target=f"{old_phase} -> {new_phase}",
        reason=reason or (f"System phase advanced to {cal.get_phase_display()}" + (" (Administrative override)" if force else ""))
    )

    return JsonResponse({
        'ok': True,
        'phase': cal.phase,
        'phase_name': cal.get_phase_display(),
        'message': f"System phase changed to {cal.get_phase_display()}."
    })


@require_http_methods(["POST"])
@role_required(['admin'])
def api_run_blossom_matching(request):
    user = get_current_user(request)
    body = {}
    try:
        if request.body:
            body = json.loads(request.body.decode('utf-8'))
    except Exception:
        pass
    dry_run = body.get('dry_run', False)

    res = run_blossom_leftover_matching(actor=user.name, dry_run=dry_run)
    return JsonResponse({
        'ok': True,
        'matched_count': res.matched_count,
        'pass1_count': len(res.pass1_pairs),
        'pass2_compromise_count': len(res.pass2_compromise_pairs),
        'odd_students_count': len(res.odd_students),
        'odd_students': [{'id': s.id, 'roll_no': s.roll_no, 'name': s.name} for s in res.odd_students],
        'dry_run': dry_run,
        'message': f"Two-Pass Blossom matched {res.matched_count} pairs ({len(res.pass1_pairs)} clash-free, {len(res.pass2_compromise_pairs)} compromise) with {len(res.odd_students)} queued for Warden."
    })


@require_http_methods(["POST"])
@role_required(['admin'])
def api_auto_allot_rooms(request):
    user = get_current_user(request)
    count = run_automated_room_allotment(actor=user.name)
    return JsonResponse({
        'ok': True,
        'allotted_count': count,
        'message': f"Successfully allotted rooms to {count} confirmed pairs!"
    })


@require_http_methods(["POST"])
@role_required(['warden', 'admin'])
def api_warden_allot(request, pairing_id):
    try:
        body = json.loads(request.body.decode('utf-8'))
    except Exception:
        return HttpResponseBadRequest("Invalid JSON")

    room_number = body.get('room_number', '').strip()
    reason = body.get('reason', '').strip()

    pairing = get_object_or_404(Pair, id=pairing_id)
    # Require mandatory reason if overriding an already allotted room
    is_reallotment = pairing.room is not None and pairing.room.number != room_number
    if is_reallotment and not reason:
        return JsonResponse({
            'error': 'Warden room re-allocation override requires a mandatory justification note.'
        }, status=400)

    reason = reason or "Standard Warden room allotment"
    blk = pairing.user_a.block or HostelBlock.objects.first()

    with transaction.atomic():
        room, _ = Room.objects.get_or_create(
            block=blk,
            number=room_number,
            defaults={'capacity': 2, 'floor': 1}
        )
        # Row-level concurrency lock preventing race condition overbookings
        room = Room.objects.select_for_update().get(id=room.id)

        # Capacity validation under lock
        active_allotments = room.allotments.filter(is_active=True).exclude(
            user__in=[pairing.user_a, pairing.user_b]
        ).count()
        if active_allotments + 2 > room.capacity:
            return JsonResponse({
                'error': f'Room {room.number} is already at full capacity ({room.capacity} beds).'
            }, status=400)

        if pairing.room and pairing.room != room:
            Allotment.objects.filter(room=pairing.room, user__in=[pairing.user_a, pairing.user_b]).update(is_active=False)

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

@ensure_csrf_cookie
def login_view(request):
    """Unified login portal for Students, Wardens, and Admins."""
    role = request.GET.get('role', 'student')
    registered = request.GET.get('registered')
    registered_roll = request.GET.get('roll', '').strip()

    context = {
        'initial_role': role,
        'registered': registered,
        'registered_roll': registered_roll,
    }
    return render(request, 'matcher/login.html', context)


@ensure_csrf_cookie
def register_view(request):
    """Dedicated student registration portal."""
    blocks = HostelBlock.objects.all().order_by('gender', 'name')
    return render(request, 'matcher/register.html', {'blocks': blocks})


@require_http_methods(["POST"])
def api_register(request):
    """
    Registers a new student user with Registration Number (roll_no) and Password.
    Prevents duplicate accounts and enforces valid credential requirements.
    """
    try:
        body = json.loads(request.body.decode('utf-8'))
    except Exception:
        return HttpResponseBadRequest("Invalid JSON payload")

    name = body.get('name', '').strip()
    roll_no = body.get('roll_no', '').strip()
    email = body.get('email', '').strip().lower()
    password = body.get('password', '').strip()
    confirm_password = body.get('confirm_password', '').strip()
    gender = body.get('gender', 'M').strip().upper()
    branch = body.get('branch', 'Computer Science').strip()
    year = body.get('year', '1st Year').strip()
    phone = body.get('phone', '').strip()
    block_id = body.get('block_id')
    consent_given = bool(body.get('consent_given', True))

    if not name:
        return JsonResponse({'error': 'Please enter your Full Name.'}, status=400)
    if not roll_no:
        return JsonResponse({'error': 'Please enter your University Registration Number.'}, status=400)
    if not email or '@' not in email:
        return JsonResponse({'error': 'Please enter a valid College Email Address.'}, status=400)
    if not password:
        return JsonResponse({'error': 'Please provide a secure password.'}, status=400)
    if len(password) < 6:
        return JsonResponse({'error': 'Password must be at least 6 characters long.'}, status=400)
    if password != confirm_password:
        return JsonResponse({'error': 'Passwords do not match. Please verify your password.'}, status=400)
    if gender not in ['M', 'F', 'O']:
        gender = 'M'

    # Check for existing account by registration number or email
    if StudentUser.objects.filter(roll_no__iexact=roll_no).exists():
        return JsonResponse({
            'error': f'An account with Registration Number "{roll_no}" already exists. Please sign in with your password.',
            'already_exists': True
        }, status=400)

    if StudentUser.objects.filter(email__iexact=email).exists():
        return JsonResponse({
            'error': f'An account with Email "{email}" already exists. Please sign in with your password.',
            'already_exists': True
        }, status=400)

    # Assign hostel block based on choice or gender
    block = None
    if block_id:
        block = HostelBlock.objects.filter(id=block_id).first()
    if not block:
        block = HostelBlock.objects.filter(gender=gender).first()
    if not block:
        block = HostelBlock.objects.first()

    import random
    user = StudentUser.objects.create(
        roll_no=roll_no,
        name=name,
        email=email,
        gender=gender,
        year=year,
        branch=branch,
        block=block,
        role='student',
        phone=phone,
        consent_given=consent_given,
        consent_at=timezone.now() if consent_given else None,
        avatar_hue=random.randint(15, 340),
        persona="Daylight Scholar" if gender == "F" else "Midnight Curator",
    )
    user.set_password(password)
    user.save()

    AuditLog.objects.create(
        actor=user.name,
        action='STUDENT_REGISTRATION',
        target=user.roll_no,
        reason=f"New student {user.name} ({user.roll_no}) registered."
    )

    return JsonResponse({
        'ok': True,
        'message': f'Account created successfully for {user.name}! Please sign in using your Registration Number and Password.',
        'roll_no': user.roll_no,
        'redirect_url': f'/login/?registered=1&roll={user.roll_no}'
    }, status=201)



@require_http_methods(["POST"])
def api_send_otp(request):
    """Generates and securely stores a hashed 6-digit OTP with rate limiting & expiration."""
    try:
        body = json.loads(request.body.decode('utf-8'))
    except Exception:
        return HttpResponseBadRequest("Invalid JSON")

    identity = (body.get('identity') or body.get('registration_no') or body.get('roll_no', '')).strip()
    if not identity:
        return JsonResponse({'error': 'Please provide your Registration Number or College Email.'}, status=400)

    user = StudentUser.objects.filter(
        Q(roll_no__iexact=identity) | Q(email__iexact=identity)
    ).first()

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

    # Dispatch real transactional email
    subject = "Your kindred Verification Code"
    message = (
        f"Hello {user.name},\n\n"
        f"Your one-time verification code is: {raw_otp}\n\n"
        f"This code is valid for 5 minutes and will expire afterwards.\n"
        f"If you did not request this OTP, please contact your hostel administration immediately.\n\n"
        f"— Kindred Allotment Team"
    )
    send_mail_async(
        subject=subject,
        message=message,
        from_email=None,
        recipient_list=[user.email],
        fail_silently=False,
    )

    return JsonResponse({
        'ok': True,
        'message': f'Verification OTP sent to {user.email} (valid 5 min)',
        'user_name': user.name,
        'roll_no': user.roll_no,
        'registration_no': user.roll_no,
        'expires_in': 300,
    })


@require_http_methods(["POST"])
def api_login(request):
    try:
        body = json.loads(request.body.decode('utf-8'))
    except Exception:
        return HttpResponseBadRequest("Invalid JSON")

    role = body.get('role', 'student').strip().lower()
    identity = (body.get('identity') or body.get('registration_no') or body.get('roll_no', '')).strip()
    secret = body.get('secret', '').strip()

    if not identity:
        return JsonResponse({'error': 'Please provide your Registration Number, Staff ID, or Email.'}, status=400)
    if not secret:
        return JsonResponse({'error': 'Please provide your Password, Passcode, or OTP code.'}, status=400)

    # Lookup user
    user = StudentUser.objects.filter(
        Q(roll_no__iexact=identity) | Q(email__iexact=identity)
    ).first()

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
    if role == 'admin' and user.role != 'admin':
        return JsonResponse({'error': 'This account does not have Administrator privileges.'}, status=403)

    # Verification using PBKDF2 Password Check for all roles
    password_ok = user.check_password(secret)

    # Fallback for demo seed accounts if not yet hashed (strictly restricted to demo accounts in DEBUG mode)
    if not password_ok and settings.DEBUG and getattr(user, 'is_demo', False):
        if role == 'student' and secret in ['student123', '123456']:
            password_ok = True
            user.set_password(secret)
            user.save(update_fields=['password_hash'])
        elif role == 'warden' and secret == 'warden123':
            password_ok = True
            user.set_password(secret)
            user.save(update_fields=['password_hash'])
        elif role == 'admin' and secret == 'kindred10266':
            password_ok = True
            user.set_password(secret)
            user.save(update_fields=['password_hash'])

    # Optional OTP fallback if student requested an OTP
    if not password_ok and role == 'student':
        otp_record = OTPVerification.objects.filter(
            user=user, is_used=False
        ).order_by('-created_at').first()
        if otp_record and not otp_record.is_expired and otp_record.attempts_left > 0:
            if otp_record.verify(secret):
                password_ok = True
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

    if not password_ok:
        user.record_failed_login()
        AuditLog.objects.create(
            actor=identity,
            action='AUTH_LOGIN_FAILED_BAD_PASSWORD',
            target=f"{user.roll_no} ({role})",
            reason=f"Incorrect {role} password"
        )
        return JsonResponse({
            'error': f'Incorrect password for {user.name} ({user.roll_no}). Please check your password or register if you are a new student.'
        }, status=400)

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
        'admin': '/admin-portal/',
    }
    redirect_url = redirect_map.get(user.role, '/student/')

    return JsonResponse({
        'ok': True,
        'id': user.id,
        'name': user.name,
        'roll_no': user.roll_no,
        'registration_no': user.roll_no,
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
# ADMIN GOVERNANCE & ROSTER VIEWS
# ==========================================

@ensure_csrf_cookie
def admin_dashboard_view(request):
    """Allotment Admin portal: calendar phases, blocks overview, roster, wardens management, and audit log."""
    current_user = get_current_user(request)
    if not current_user or current_user.role != 'admin':
        return redirect('/login/?role=admin')
    calendar = AllotmentCalendar.get_current()
    students = StudentUser.objects.filter(role='student').select_related('block').order_by('name')
    wardens = StudentUser.objects.filter(role='warden').select_related('block').order_by('name')
    blocks = HostelBlock.objects.all().order_by('name')
    pairs = Pair.objects.all().select_related('user_a', 'user_b', 'room')
    allotments = Allotment.objects.filter(is_active=True)
    audit_logs = AuditLog.objects.all().order_by('-timestamp')[:30]

    paired_ids = set(pairs.values_list('user_a_id', flat=True)) | set(pairs.values_list('user_b_id', flat=True))
    unpaired_students = students.exclude(id__in=paired_ids)

    context = {
        'current_user': current_user,
        'calendar': calendar,
        'phases': AllotmentCalendar.PHASE_CHOICES,
        'students': students,
        'wardens': wardens,
        'total_wardens': wardens.count(),
        'blocks': blocks,
        'total_students': students.count(),
        'confirmed_pairs': pairs.count(),
        'allotted_count': pairs.filter(status='ALLOTTED').count(),
        'unpaired_count': unpaired_students.count(),
        'audit_logs': audit_logs,
    }
    return render(request, 'matcher/admin.html', context)


@require_http_methods(["GET"])
@role_required(['admin'])
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


# ==========================================
# WARDEN ACCESS & ROLE PROMOTION ENDPOINTS
# ==========================================

@require_http_methods(["POST"])
@role_required(['admin'])
def api_admin_assign_warden(request):
    """
    Elevates an existing user to the 'warden' role, granting them hostel administration privileges.
    Payload: { "user_id": <int> } or { "roll_no": "<str>", "block_id": <int or None> }
    """
    admin_user = get_current_user(request)
    try:
        data = json.loads(request.body)
    except Exception:
        return JsonResponse({'error': 'Invalid JSON request payload.'}, status=400)

    user_id = data.get('user_id')
    roll_no = (data.get('roll_no') or '').strip()
    block_id = data.get('block_id')

    user = None
    if user_id:
        user = StudentUser.objects.filter(id=user_id).first()
    elif roll_no:
        user = StudentUser.objects.filter(roll_no=roll_no).first()
        if not user:
            user = StudentUser.objects.filter(email=roll_no).first()

    if not user:
        return JsonResponse({'error': 'User not found. Please verify the ID or Registration Number.'}, status=404)

    block = None
    if block_id:
        block = HostelBlock.objects.filter(id=block_id).first()
    elif user.block:
        block = user.block

    user.role = 'warden'
    if block:
        user.block = block
    if user.branch in ['Computer Science', 'General', 'Electronics', 'Mechanical', 'Civil']:
        user.branch = 'Hostel Administration'
    if user.year in ['1st Year', '2nd Year', '3rd Year', '4th Year']:
        user.year = 'Faculty / Staff'

    user.save(update_fields=['role', 'block', 'branch', 'year'])

    AuditLog.objects.create(
        actor=admin_user.name,
        action='WARDEN_ROLE_ASSIGNED',
        target=f"{user.name} ({user.roll_no})",
        reason=f"Admin {admin_user.name} elevated user to Hostel Warden" + (f" for {block.name}" if block else "")
    )

    return JsonResponse({
        'ok': True,
        'message': f"{user.name} ({user.roll_no}) has been granted Hostel Warden privileges.",
        'user': {
            'id': user.id,
            'name': user.name,
            'roll_no': user.roll_no,
            'email': user.email,
            'role': user.role,
            'block': user.block.name if user.block else 'All Campus Blocks',
        }
    })


@require_http_methods(["POST"])
@role_required(['admin'])
def api_admin_create_warden(request):
    """
    Creates a new Warden staff account from scratch.
    Payload: { "name": "...", "roll_no": "...", "email": "...", "gender": "M/F", "block_id": <int>, "password": "..." }
    """
    admin_user = get_current_user(request)
    try:
        data = json.loads(request.body)
    except Exception:
        return JsonResponse({'error': 'Invalid JSON request payload.'}, status=400)

    name = (data.get('name') or '').strip()
    roll_no = (data.get('roll_no') or '').strip()
    email = (data.get('email') or '').strip()
    gender = (data.get('gender') or 'M').strip().upper()
    block_id = data.get('block_id')
    password = (data.get('password') or '').strip() or 'warden123'

    if not name:
        return JsonResponse({'error': 'Full name is required.'}, status=400)
    if not roll_no:
        return JsonResponse({'error': 'Staff ID / Registration Number is required.'}, status=400)
    if not email:
        return JsonResponse({'error': 'Staff email address is required.'}, status=400)

    if StudentUser.objects.filter(roll_no=roll_no).exists():
        return JsonResponse({'error': f'An account with Registration/Staff ID "{roll_no}" already exists.'}, status=400)
    if StudentUser.objects.filter(email=email).exists():
        return JsonResponse({'error': f'An account with email "{email}" already exists.'}, status=400)

    block = HostelBlock.objects.filter(id=block_id).first() if block_id else None

    warden = StudentUser.objects.create(
        name=name,
        roll_no=roll_no,
        email=email,
        gender=gender if gender in ['M', 'F', 'O'] else 'M',
        year='Faculty / Staff',
        branch='Hostel Administration',
        role='warden',
        block=block,
        consent_given=True,
        is_demo=False
    )
    warden.set_password(password)
    warden.save(update_fields=['password_hash'])

    AuditLog.objects.create(
        actor=admin_user.name,
        action='WARDEN_CREATED',
        target=f"{warden.name} ({warden.roll_no})",
        reason=f"New Warden account created by Admin {admin_user.name}" + (f" for {block.name}" if block else "")
    )

    return JsonResponse({
        'ok': True,
        'message': f"Warden account for {warden.name} ({warden.roll_no}) created successfully.",
        'user': {
            'id': warden.id,
            'name': warden.name,
            'roll_no': warden.roll_no,
            'email': warden.email,
            'role': warden.role,
            'block': warden.block.name if warden.block else 'All Campus Blocks',
        }
    })


@require_http_methods(["POST"])
@role_required(['admin'])
def api_admin_revoke_warden(request, user_id):
    """
    Revokes Warden privileges, returning the user to 'student' role.
    """
    admin_user = get_current_user(request)
    if admin_user.id == user_id:
        return JsonResponse({'error': 'Cannot revoke privileges from the currently logged in administrator.'}, status=400)

    user = StudentUser.objects.filter(id=user_id, role='warden').first()
    if not user:
        return JsonResponse({'error': 'Warden account not found.'}, status=404)

    user.role = 'student'
    user.branch = 'Computer Science'
    user.year = '1st Year'
    user.save(update_fields=['role', 'branch', 'year'])

    AuditLog.objects.create(
        actor=admin_user.name,
        action='WARDEN_ROLE_REVOKED',
        target=f"{user.name} ({user.roll_no})",
        reason=f"Admin {admin_user.name} revoked Warden privileges. Account reverted to student."
    )

    return JsonResponse({
        'ok': True,
        'message': f"Warden privileges for {user.name} ({user.roll_no}) have been revoked."
    })


# ==========================================
# DISPUTE & MAINTENANCE TICKET ENDPOINTS
# ==========================================

@require_http_methods(["GET"])
@login_required_custom
def api_tickets_list(request):
    """
    Returns tickets.
    Students see only their own tickets.
    Staff (Warden, Admin) see all tickets across the hostel.
    Supports ?status=OPEN & ?type=COMPLAINT filtering.
    """
    me = get_current_user(request)
    if not me:
        return JsonResponse({'error': 'Authentication required. Please sign in.'}, status=401)
    status_filter = request.GET.get('status', '').strip().upper()
    type_filter = request.GET.get('type', '').strip().upper()

    if me.role in ['warden', 'admin']:
        tickets = Ticket.objects.all().select_related('student')
    else:
        tickets = Ticket.objects.filter(student=me).select_related('student')

    if status_filter:
        tickets = tickets.filter(status=status_filter)
    if type_filter:
        tickets = tickets.filter(ticket_type=type_filter)

    tickets_data = [
        {
            'id': t.id,
            'student_id': t.student.id,
            'student_name': t.student.name,
            'student_roll': t.student.roll_no,
            'ticket_type': t.ticket_type,
            'ticket_type_display': t.get_ticket_type_display(),
            'subject': t.subject,
            'description': t.description,
            'status': t.status,
            'status_display': t.get_status_display(),
            'resolution_notes': t.resolution_notes,
            'created_at': t.created_at.strftime('%Y-%m-%d %H:%M'),
            'updated_at': t.updated_at.strftime('%Y-%m-%d %H:%M'),
        }
        for t in tickets
    ]
    return JsonResponse({'ok': True, 'tickets': tickets_data, 'count': len(tickets_data)})


@require_http_methods(["POST"])
@login_required_custom
def api_create_ticket(request):
    """
    Allows a student to log a complaint, maintenance ticket, or room change request.
    """
    me = get_current_user(request)
    if not me:
        return JsonResponse({'error': 'Authentication required. Please sign in.'}, status=401)
    try:
        body = json.loads(request.body.decode('utf-8'))
    except Exception:
        return HttpResponseBadRequest("Invalid JSON")

    subject = body.get('subject', '').strip()
    description = body.get('description', '').strip()
    ticket_type = body.get('ticket_type', 'COMPLAINT').strip().upper()

    valid_types = dict(Ticket.TICKET_TYPES).keys()
    if ticket_type not in valid_types:
        return JsonResponse({
            'error': f'Invalid ticket type "{ticket_type}". Must be one of: {", ".join(valid_types)}.'
        }, status=400)

    if not subject:
        return JsonResponse({'error': 'Please provide a subject for your ticket.'}, status=400)
    if not description:
        return JsonResponse({'error': 'Please provide a description of the issue.'}, status=400)

    ticket = Ticket.objects.create(
        student=me,
        ticket_type=ticket_type,
        subject=subject[:150],
        description=description,
        status='OPEN'
    )

    AuditLog.objects.create(
        actor=me.name,
        action='TICKET_CREATED',
        target=f"Ticket #{ticket.id} ({ticket.ticket_type})",
        reason=f"Subject: {ticket.subject}"
    )

    Notification.objects.create(
        student=me,
        category='TICKET',
        title=f"Ticket #{ticket.id} Logged",
        message=f"Your ticket '{ticket.subject}' has been submitted and is currently Open."
    )

    return JsonResponse({
        'ok': True,
        'ticket_id': ticket.id,
        'status': ticket.status,
        'status_display': ticket.get_ticket_type_display(),
        'message': f"Ticket #{ticket.id} submitted successfully."
    }, status=201)


@require_http_methods(["POST"])
@role_required(['warden', 'admin'])
def api_update_ticket_status(request, ticket_id):
    """
    Allows Warden or Admin staff to update ticket status and append resolution notes.
    """
    me = get_current_user(request)
    if not me:
        return JsonResponse({'error': 'Authentication required. Please sign in.'}, status=401)
    if me.role not in ['warden', 'admin']:
        return HttpResponseForbidden("Only staff (Warden, Admin) can update ticket status.")

    try:
        body = json.loads(request.body.decode('utf-8'))
    except Exception:
        return HttpResponseBadRequest("Invalid JSON")

    ticket = get_object_or_404(Ticket, id=ticket_id)
    new_status = body.get('status', '').strip().upper()
    notes = body.get('resolution_notes', '').strip()

    valid_statuses = dict(Ticket.STATUS_CHOICES).keys()
    if new_status not in valid_statuses:
        return JsonResponse({
            'error': f'Invalid status "{new_status}". Must be one of: {", ".join(valid_statuses)}.'
        }, status=400)

    old_status = ticket.status
    ticket.status = new_status
    if notes:
        ticket.resolution_notes = notes
    ticket.save()

    AuditLog.objects.create(
        actor=me.name,
        action='TICKET_STATUS_UPDATED',
        target=f"Ticket #{ticket.id} ({old_status} -> {new_status})",
        reason=notes or f"Status updated by {me.name}"
    )

    Notification.objects.create(
        student=ticket.student,
        category='TICKET',
        title=f"Ticket #{ticket.id} Status Updated",
        message=f"Your ticket '{ticket.subject}' has been marked as {ticket.get_status_display()}." + (f" Note: {notes}" if notes else "")
    )

    return JsonResponse({
        'ok': True,
        'ticket_id': ticket.id,
        'status': ticket.status,
        'status_display': ticket.get_status_display(),
        'resolution_notes': ticket.resolution_notes,
        'message': f"Ticket #{ticket.id} status updated to {ticket.get_status_display()}."
    })


# ==========================================
# POST-STAY FEEDBACK LOOP ENDPOINTS
# ==========================================

@require_http_methods(["POST"])
@login_required_api
def api_submit_feedback(request):
    """
    Allows a student with an active room allotment to submit post-stay feedback
    evaluating actual roommate harmony, sleep, cleanliness, and recommendation.
    """
    me = get_current_user(request)
    allotment = Allotment.objects.filter(user=me, is_active=True).first()
    if not allotment:
        return JsonResponse({
            'error': 'You do not have an active hostel room allotment to evaluate.'
        }, status=400)

    if Feedback.objects.filter(allotment=allotment, student=me).exists():
        return JsonResponse({
            'error': 'You have already submitted feedback for this allotment.'
        }, status=400)

    try:
        body = json.loads(request.body.decode('utf-8'))
    except Exception:
        return HttpResponseBadRequest("Invalid JSON")

    try:
        harmony = int(body.get('roommate_harmony_rating', 5))
        sleep = int(body.get('sleep_compatibility_rating', 5))
        cleanliness = int(body.get('cleanliness_rating', 5))
    except (ValueError, TypeError):
        return JsonResponse({'error': 'Ratings must be integers between 1 and 5.'}, status=400)

    for r_name, r_val in [('harmony', harmony), ('sleep', sleep), ('cleanliness', cleanliness)]:
        if not (1 <= r_val <= 5):
            return JsonResponse({'error': f'Rating for {r_name} must be between 1 and 5.'}, status=400)

    would_recommend = bool(body.get('would_recommend_partner', True))
    comments = str(body.get('comments', '')).strip()

    fb = Feedback.objects.create(
        allotment=allotment,
        student=me,
        roommate_harmony_rating=harmony,
        sleep_compatibility_rating=sleep,
        cleanliness_rating=cleanliness,
        would_recommend_partner=would_recommend,
        comments=comments
    )

    AuditLog.objects.create(
        actor=me.name,
        action='FEEDBACK_SUBMITTED',
        target=f"{me.roll_no} -> Room {allotment.room.number}",
        reason=f"Harmony: {harmony}/5, Recommend: {would_recommend}"
    )

    Notification.objects.create(
        student=me,
        category='FEEDBACK',
        title="Post-Stay Feedback Recorded",
        message="Thank you for reviewing your roommate experience! Your evaluation helps improve algorithmic accuracy."
    )

    return JsonResponse({
        'ok': True,
        'feedback_id': fb.id,
        'harmony_rating': fb.roommate_harmony_rating,
        'would_recommend': fb.would_recommend_partner,
        'message': 'Post-stay feedback submitted successfully! Thank you for helping improve roommate compatibility.'
    }, status=201)


@require_http_methods(["GET"])
def api_feedback_summary(request):
    """
    Computes aggregate post-stay feedback analytics comparing algorithm predictions
    against actual lived roommate satisfaction.
    """
    from django.db.models import Avg
    feedbacks = Feedback.objects.all()
    count = feedbacks.count()

    if count == 0:
        return JsonResponse({
            'ok': True,
            'total_evaluations': 0,
            'metrics': {
                'average_harmony': 0.0,
                'average_sleep': 0.0,
                'average_cleanliness': 0.0,
                'recommendation_rate': 0.0,
                'satisfaction_percentage': 0.0,
            },
            'recent_reviews': []
        })

    aggregates = feedbacks.aggregate(
        avg_harmony=Avg('roommate_harmony_rating'),
        avg_sleep=Avg('sleep_compatibility_rating'),
        avg_cleanliness=Avg('cleanliness_rating'),
    )

    rec_count = feedbacks.filter(would_recommend_partner=True).count()
    rec_rate = (rec_count / count) * 100.0

    avg_harmony = float(aggregates['avg_harmony'] or 0.0)
    avg_sleep = float(aggregates['avg_sleep'] or 0.0)
    avg_cleanliness = float(aggregates['avg_cleanliness'] or 0.0)
    satisfaction_pct = (avg_harmony / 5.0) * 100.0

    recent_reviews = [
        {
            'id': f.id,
            'room': f.allotment.room.number,
            'block': f.allotment.room.block.name,
            'harmony_rating': f.roommate_harmony_rating,
            'would_recommend': f.would_recommend_partner,
            'comments': f.comments,
            'submitted_at': f.submitted_at.strftime('%Y-%m-%d')
        }
        for f in feedbacks.order_by('-submitted_at')[:10]
        if f.comments
    ]

    return JsonResponse({
        'ok': True,
        'total_evaluations': count,
        'metrics': {
            'average_harmony': round(avg_harmony, 2),
            'average_sleep': round(avg_sleep, 2),
            'average_cleanliness': round(avg_cleanliness, 2),
            'recommendation_rate': round(rec_rate, 1),
            'satisfaction_percentage': round(satisfaction_pct, 1),
        },
        'recent_reviews': recent_reviews
    })


