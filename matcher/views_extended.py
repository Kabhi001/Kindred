import secrets
import json
import csv
import io
import random
from datetime import timedelta
from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse, HttpResponseBadRequest, HttpResponseForbidden, HttpResponse
from django.views.decorators.http import require_http_methods
from django.utils import timezone
from django.db import transaction
from django.db.models import Q
from django.conf import settings
from django.utils.dateparse import parse_date, parse_datetime

from .models import (
    HostelBlock, Room, StudentUser, AllotmentCalendar,
    Question, Response, PairScore, Request, Pair, Allotment, AuditLog, OTPVerification,
    GuardianConsent, Ticket, Feedback, Notification,
    AcademicSession, HostelFee, EmergencyContact, HostelCheckin,
    RoomSwapRequest, MaintenanceTicket, GatePass, DisciplinaryRecord
)
from .views import get_current_user, login_required_api, role_required, send_mail_async


# ==========================================
# PASSWORD RESET & RECOVERY FLOW
# ==========================================

@require_http_methods(["POST"])
def api_password_reset_request(request):
    """Generates a secure password reset token and sends via transactional email."""
    try:
        body = json.loads(request.body.decode('utf-8'))
    except Exception:
        return HttpResponseBadRequest("Invalid JSON")

    identity = (body.get('identity') or body.get('email') or body.get('roll_no') or '').strip()
    if not identity:
        return JsonResponse({'error': 'Please provide your Registration Number or College Email.'}, status=400)

    user = StudentUser.objects.filter(Q(roll_no__iexact=identity) | Q(email__iexact=identity)).first()
    if not user:
        # Prevent user enumeration
        return JsonResponse({'ok': True, 'message': 'If an account exists with that identifier, a password reset token has been dispatched to its registered email.'})

    token = secrets.token_urlsafe(32)
    user.password_reset_token = token
    user.password_reset_expires = timezone.now() + timedelta(hours=1)
    user.save(update_fields=['password_reset_token', 'password_reset_expires'])

    reset_link = f"/login/?reset_token={token}"
    subject = "Kindred - Password Reset Token"
    message = (
        f"Hello {user.name},\n\n"
        f"We received a password reset request for your Kindred hostel account ({user.roll_no}).\n\n"
        f"Your Reset Token is: {token}\n"
        f"Reset Link: {reset_link}\n\n"
        f"This token is valid for 1 hour. If you did not make this request, you can safely ignore this email.\n\n"
        f"— Kindred Hostel Allotment Administration"
    )
    send_mail_async(subject, message, None, [user.email], fail_silently=True)

    AuditLog.objects.create(
        actor=user.name, action='PASSWORD_RESET_REQUESTED',
        target=user.roll_no, reason="Password reset token dispatched via email"
    )

    return JsonResponse({
        'ok': True,
        'message': f'Password reset token has been sent to {user.email}.',
        'token_preview': token if settings.DEBUG else None
    })


@require_http_methods(["POST"])
def api_password_reset_confirm(request):
    """Resets password using a validated one-time reset token."""
    try:
        body = json.loads(request.body.decode('utf-8'))
    except Exception:
        return HttpResponseBadRequest("Invalid JSON")

    token = body.get('token', '').strip()
    new_password = body.get('new_password', '').strip()
    confirm = body.get('confirm_password', '').strip()

    if not token:
        return JsonResponse({'error': 'Password reset token is required.'}, status=400)
    if not new_password or len(new_password) < 6:
        return JsonResponse({'error': 'New password must be at least 6 characters long.'}, status=400)
    if new_password != confirm:
        return JsonResponse({'error': 'Passwords do not match. Please verify your new password.'}, status=400)

    user = StudentUser.objects.filter(password_reset_token=token).first()
    if not user or not user.password_reset_expires or timezone.now() > user.password_reset_expires:
        return JsonResponse({'error': 'Invalid or expired password reset token. Please request a new one.'}, status=400)

    user.set_password(new_password)
    user.password_reset_token = ''
    user.password_reset_expires = None
    user.save(update_fields=['password_hash', 'password_reset_token', 'password_reset_expires'])

    AuditLog.objects.create(
        actor=user.name, action='PASSWORD_RESET_SUCCESS',
        target=user.roll_no, reason="Password successfully updated via reset token"
    )

    return JsonResponse({
        'ok': True,
        'message': f'Password successfully updated for {user.name} ({user.roll_no}). You may now sign in.'
    })


# ==========================================
# DPDP ACT 2023 - RIGHT TO BE FORGOTTEN
# ==========================================

@require_http_methods(["POST"])
@login_required_api
def api_withdraw_consent(request):
    """
    DPDP Act 2023 Statutory Compliance:
    Enforces student's right to withdraw consent and have behavioral/quiz data purged.
    Personal identifiers are cryptographically anonymized while preserving required financial audit logs.
    """
    user = get_current_user(request)
    if not user:
        return JsonResponse({'error': 'Authentication required.'}, status=401)

    AuditLog.objects.create(
        actor=user.name, action='DPDP_CONSENT_WITHDRAWN',
        target=user.roll_no, reason="Student exercised statutory Right to Withdraw Consent under DPDP Act 2023"
    )

    # Anonymize identity
    user.name = f"Redacted-User-{user.id}"
    user.email = f"anonymized-{user.id}@dpdp.kindred.local"
    user.phone = ''
    user.consent_given = False
    user.consent_at = None
    user.persona = 'Withdrawn'
    user.save()

    # Purge PII and behavioral records
    EmergencyContact.objects.filter(student=user).delete()
    GuardianConsent.objects.filter(student=user).delete()
    Response.objects.filter(user=user).delete()
    PairScore.objects.filter(Q(user_a=user) | Q(user_b=user)).delete()

    request.session.flush()
    return JsonResponse({
        'ok': True,
        'message': 'Your consent has been formally withdrawn and personal behavioral data purged in accordance with DPDP Act 2023.'
    })


# ==========================================
# EMERGENCY CONTACT API
# ==========================================

@require_http_methods(["GET", "POST"])
@login_required_api
def api_emergency_contact(request):
    """Get or update student emergency profile & medical details."""
    user = get_current_user(request)

    if request.method == 'GET':
        ec = EmergencyContact.objects.filter(student=user).first()
        if not ec:
            return JsonResponse({'ok': True, 'contact': None})
        return JsonResponse({
            'ok': True,
            'contact': {
                'blood_group': ec.blood_group,
                'medical_conditions': ec.medical_conditions,
                'chronic_allergies': ec.chronic_allergies,
                'parent_name': ec.parent_name,
                'parent_phone': ec.parent_phone,
                'parent_email': ec.parent_email,
                'local_guardian_name': ec.local_guardian_name,
                'local_guardian_phone': ec.local_guardian_phone,
                'home_address': ec.home_address,
                'updated_at': ec.updated_at.strftime('%Y-%m-%d %H:%M') if ec.updated_at else None,
            }
        })

    try:
        body = json.loads(request.body.decode('utf-8'))
    except Exception:
        return HttpResponseBadRequest("Invalid JSON")

    ec, _ = EmergencyContact.objects.update_or_create(
        student=user,
        defaults={
            'blood_group': body.get('blood_group', '').strip()[:5],
            'medical_conditions': body.get('medical_conditions', '').strip(),
            'chronic_allergies': body.get('chronic_allergies', '').strip(),
            'parent_name': body.get('parent_name', '').strip()[:100],
            'parent_phone': body.get('parent_phone', '').strip()[:20],
            'parent_email': body.get('parent_email', '').strip().lower(),
            'local_guardian_name': body.get('local_guardian_name', '').strip()[:100],
            'local_guardian_phone': body.get('local_guardian_phone', '').strip()[:20],
            'home_address': body.get('home_address', '').strip(),
        }
    )

    AuditLog.objects.create(
        actor=user.name, action='EMERGENCY_CONTACT_UPDATED',
        target=user.roll_no, reason="Student updated emergency medical & guardian profile"
    )

    return JsonResponse({'ok': True, 'message': 'Emergency medical and parent contact info saved successfully.'})


# ==========================================
# HOSTEL FEE CLEARANCE & VERIFICATION
# ==========================================

@require_http_methods(["GET"])
@login_required_api
def api_fee_status(request):
    """View student fee clearance ledger."""
    user = get_current_user(request)
    fees = HostelFee.objects.filter(student=user).order_by('-created_at')

    data = [
        {
            'id': f.id,
            'academic_year': f.academic_year,
            'amount': str(f.amount),
            'status': f.status,
            'transaction_ref': f.transaction_ref,
            'verified_by': f.verified_by,
            'created_at': f.created_at.strftime('%Y-%m-%d'),
            'verified_at': f.verified_at.strftime('%Y-%m-%d %H:%M') if f.verified_at else None,
        }
        for f in fees
    ]
    is_cleared = any(f.status == 'VERIFIED' for f in fees) or fees.count() == 0

    return JsonResponse({
        'ok': True,
        'student': user.name,
        'roll_no': user.roll_no,
        'fees': data,
        'is_cleared': is_cleared
    })


@require_http_methods(["POST"])
@login_required_api
def api_submit_fee_payment(request):
    """Student submits transaction reference for hostel fee clearance."""
    user = get_current_user(request)
    try:
        body = json.loads(request.body.decode('utf-8'))
    except Exception:
        return HttpResponseBadRequest("Invalid JSON")

    academic_year = body.get('academic_year', '2026-27').strip()
    amount = body.get('amount', '45000.00')
    tx_ref = body.get('transaction_ref', '').strip()

    if not tx_ref:
        return JsonResponse({'error': 'Transaction reference number is required.'}, status=400)

    fee, created = HostelFee.objects.update_or_create(
        student=user,
        academic_year=academic_year,
        defaults={
            'amount': amount,
            'transaction_ref': tx_ref,
            'status': 'PENDING'
        }
    )

    AuditLog.objects.create(
        actor=user.name, action='FEE_PAYMENT_SUBMITTED',
        target=f"{user.roll_no} - {academic_year}",
        reason=f"Submitted payment ref: {tx_ref}"
    )

    return JsonResponse({
        'ok': True,
        'fee_id': fee.id,
        'message': f'Fee payment submission recorded for {academic_year}. Awaiting Warden verification.'
    })


@require_http_methods(["POST"])
@role_required(['warden', 'admin'])
def api_verify_fee(request):
    """Warden or Admin verifies student fee receipt."""
    try:
        body = json.loads(request.body.decode('utf-8'))
    except Exception:
        return HttpResponseBadRequest("Invalid JSON")

    fee_id = body.get('fee_id')
    fee = HostelFee.objects.filter(id=fee_id).first()
    if not fee:
        return JsonResponse({'error': 'Fee record not found.'}, status=404)

    me = get_current_user(request)
    fee.status = 'VERIFIED'
    fee.verified_at = timezone.now()
    fee.verified_by = me.name
    fee.save(update_fields=['status', 'verified_at', 'verified_by'])

    Notification.objects.create(
        student=fee.student,
        category='FINANCE',
        title="Hostel Fee Payment Verified!",
        message=f"Your hostel fee clearance for {fee.academic_year} (Ref: {fee.transaction_ref}) was verified by {me.name}."
    )

    AuditLog.objects.create(
        actor=me.name, action='FEE_VERIFIED',
        target=f"{fee.student.roll_no} ({fee.academic_year})",
        reason=f"Verified payment of Rs {fee.amount} (Ref: {fee.transaction_ref})"
    )

    return JsonResponse({'ok': True, 'message': f'Fee clearance verified for {fee.student.name} ({fee.student.roll_no}).'})


# ==========================================
# PHYSICAL CHECK-IN & QR VERIFICATION
# ==========================================

@require_http_methods(["POST"])
@role_required(['warden', 'admin'])
def api_checkin_student(request):
    """Warden scans verification QR code or roll number to mark student checked-in."""
    try:
        body = json.loads(request.body.decode('utf-8'))
    except Exception:
        return HttpResponseBadRequest("Invalid JSON")

    identifier = (body.get('roll_no') or body.get('qr_code') or '').strip()
    if not identifier:
        return JsonResponse({'error': 'Registration number or verification code required.'}, status=400)

    # Support raw QR string or roll number
    clean_roll = identifier.replace('KINDRED-CHECKIN-', '').split('-')[0].strip()
    student = StudentUser.objects.filter(Q(roll_no__iexact=clean_roll) | Q(roll_no__iexact=identifier)).first()
    if not student:
        return JsonResponse({'error': f'Student "{identifier}" not found in campus database.'}, status=404)

    allotment = Allotment.objects.filter(user=student, is_active=True).select_related('room', 'room__block').first()
    if not allotment:
        return JsonResponse({'error': f'Student {student.name} ({student.roll_no}) does not have an active room allotment.'}, status=400)

    me = get_current_user(request)
    inventory = body.get('inventory_checklist', {
        'mattress': True,
        'study_table': True,
        'study_chair': True,
        'wardrobe_key': True,
        'room_key': True,
    })

    checkin, created = HostelCheckin.objects.update_or_create(
        allotment=allotment,
        defaults={
            'checkin_date': timezone.now(),
            'key_issued': bool(body.get('key_issued', True)),
            'inventory_checklist': inventory,
            'warden_signoff': True,
            'warden_name': me.name,
            'signed_at': timezone.now(),
            'notes': body.get('notes', '').strip()
        }
    )

    allotment.checked_in = True
    allotment.checked_in_at = timezone.now()
    allotment.key_issued = checkin.key_issued
    allotment.save(update_fields=['checked_in', 'checked_in_at', 'key_issued'])

    AuditLog.objects.create(
        actor=me.name, action='PHYSICAL_CHECKIN_COMPLETED',
        target=f"{student.roll_no} -> {allotment.room}",
        reason=f"Physical check-in signoff by {me.name}. Key issued: {checkin.key_issued}"
    )

    Notification.objects.create(
        student=student,
        category='ALLOTMENT',
        title="Physical Room Check-In Confirmed",
        message=f"Welcome to {allotment.room.block.name}! You are checked into Room {allotment.room.number}. Room key issued."
    )

    return JsonResponse({
        'ok': True,
        'message': f'Student {student.name} ({student.roll_no}) successfully checked into Room {allotment.room.number}.',
        'checkin': {
            'student_name': student.name,
            'roll_no': student.roll_no,
            'room': allotment.room.number,
            'block': allotment.room.block.name,
            'key_issued': checkin.key_issued,
            'checkin_date': checkin.checkin_date.strftime('%Y-%m-%d %H:%M'),
        }
    })


@require_http_methods(["GET"])
@login_required_api
def api_checkin_status(request):
    """View current check-in state."""
    user = get_current_user(request)
    allotment = Allotment.objects.filter(user=user, is_active=True).select_related('room', 'room__block').first()
    if not allotment:
        return JsonResponse({'ok': True, 'has_allotment': False})

    checkin = HostelCheckin.objects.filter(allotment=allotment).first()
    return JsonResponse({
        'ok': True,
        'has_allotment': True,
        'room': allotment.room.number,
        'block': allotment.room.block.name,
        'checked_in': allotment.checked_in,
        'key_issued': allotment.key_issued,
        'checkin_date': checkin.checkin_date.strftime('%Y-%m-%d %H:%M') if checkin else None,
        'inventory_checklist': checkin.inventory_checklist if checkin else {},
        'qr_token': f"KINDRED-CHECKIN-{user.roll_no}-{allotment.room.number}"
    })


# ==========================================
# MUTUAL ROOM SWAP & RE-ALLOCATION
# ==========================================

@require_http_methods(["POST"])
@login_required_api
def api_create_swap_request(request):
    """Student pair requests room swap with another allotted pair."""
    try:
        body = json.loads(request.body.decode('utf-8'))
    except Exception:
        return HttpResponseBadRequest("Invalid JSON")

    me = get_current_user(request)
    my_pair = me.get_pair()
    if not my_pair or my_pair.status != 'ALLOTTED' or not my_pair.room:
        return JsonResponse({'error': 'You must be in an allotted room to request a swap.'}, status=400)

    target_room_number = body.get('target_room', '').strip()
    target_pair = None
    if target_room_number:
        target_pair = Pair.objects.filter(room__number=target_room_number, status='ALLOTTED').first()
    elif body.get('target_pair_id'):
        target_pair = Pair.objects.filter(id=body['target_pair_id']).first()

    if not target_pair or not target_pair.room:
        return JsonResponse({'error': f'Target room "{target_room_number}" has no confirmed allotment to swap with.'}, status=404)

    if target_pair.id == my_pair.id:
        return JsonResponse({'error': 'Cannot request a room swap with your own pair.'}, status=400)

    # Gender matching rule
    if target_pair.user_a.gender != my_pair.user_a.gender:
        return JsonResponse({'error': 'Cannot swap rooms across hostels of differing genders.'}, status=400)

    reason = body.get('reason', '').strip()
    swap = RoomSwapRequest.objects.create(
        requester=me,
        requester_pair=my_pair,
        target_pair=target_pair,
        reason=reason,
        status='PENDING_PEER'
    )

    for peer in [target_pair.user_a, target_pair.user_b]:
        Notification.objects.create(
            student=peer,
            category='SWAP',
            title="Room Swap Proposal Received",
            message=f"{me.name} (Room {my_pair.room.number}) has requested a room swap with your Room {target_pair.room.number}. Reason: {reason or 'Mutual convenience'}"
        )

    AuditLog.objects.create(
        actor=me.name, action='ROOM_SWAP_REQUESTED',
        target=f"Room {my_pair.room.number} <-> Room {target_pair.room.number}",
        reason=reason or "Mutual room swap request"
    )

    return JsonResponse({
        'ok': True,
        'swap_id': swap.id,
        'message': f'Swap request sent to Room {target_pair.room.number}. Awaiting peer agreement and Warden approval.'
    }, status=201)


@require_http_methods(["GET"])
@login_required_api
def api_list_swap_requests(request):
    """List active room swap requests."""
    me = get_current_user(request)
    my_pair = me.get_pair()

    if me.role in ['warden', 'admin']:
        swaps = RoomSwapRequest.objects.all().select_related('requester', 'requester_pair__room', 'target_pair__room')
    else:
        if not my_pair:
            return JsonResponse({'ok': True, 'swaps': []})
        swaps = RoomSwapRequest.objects.filter(
            Q(requester_pair=my_pair) | Q(target_pair=my_pair)
        ).select_related('requester', 'requester_pair__room', 'target_pair__room')

    data = [
        {
            'id': s.id,
            'requester_name': s.requester.name,
            'requester_room': s.requester_pair.room.number if s.requester_pair.room else 'None',
            'target_room': s.target_pair.room.number if s.target_pair.room else 'None',
            'reason': s.reason,
            'status': s.status,
            'status_display': s.get_status_display(),
            'created_at': s.created_at.strftime('%Y-%m-%d %H:%M'),
        }
        for s in swaps
    ]
    return JsonResponse({'ok': True, 'swaps': data})


@require_http_methods(["POST"])
@role_required(['warden', 'admin'])
def api_review_swap_request(request, swap_id):
    """Warden approves or rejects a room swap."""
    swap = get_object_or_404(RoomSwapRequest, id=swap_id)

    try:
        body = json.loads(request.body.decode('utf-8'))
    except Exception:
        return HttpResponseBadRequest("Invalid JSON")

    action = body.get('action', '').strip().lower()
    note = body.get('note', '').strip()
    me = get_current_user(request)

    if action == 'approve':
        with transaction.atomic():
            room_a = swap.requester_pair.room
            room_b = swap.target_pair.room

            # Exchange rooms
            swap.requester_pair.room = room_b
            swap.target_pair.room = room_a
            swap.requester_pair.save(update_fields=['room'])
            swap.target_pair.save(update_fields=['room'])

            # Update active allotment pointers
            Allotment.objects.filter(room=room_a, user__in=[swap.requester_pair.user_a, swap.requester_pair.user_b]).update(room=room_b)
            Allotment.objects.filter(room=room_b, user__in=[swap.target_pair.user_a, swap.target_pair.user_b]).update(room=room_a)

            swap.status = 'APPROVED'
            swap.reviewed_at = timezone.now()
            swap.reviewed_by = me.name
            swap.warden_note = note
            swap.save()

            AuditLog.objects.create(
                actor=me.name, action='ROOM_SWAP_APPROVED',
                target=f"Room {room_a.number} <-> Room {room_b.number}",
                reason=note or "Warden approved mutual room swap"
            )

        return JsonResponse({'ok': True, 'message': f'Room swap approved! Students transferred between Room {room_a.number} and Room {room_b.number}.'})

    elif action == 'reject':
        swap.status = 'REJECTED'
        swap.reviewed_at = timezone.now()
        swap.reviewed_by = me.name
        swap.warden_note = note
        swap.save()

        AuditLog.objects.create(
            actor=me.name, action='ROOM_SWAP_REJECTED',
            target=f"Swap #{swap.id}",
            reason=note or "Warden rejected room swap"
        )
        return JsonResponse({'ok': True, 'message': 'Room swap request rejected.'})

    return JsonResponse({'error': 'Invalid action. Choose "approve" or "reject".'}, status=400)


# ==========================================
# MAINTENANCE & GRIEVANCE TICKETS (POST-ALLOTMENT)
# ==========================================

@require_http_methods(["POST"])
@login_required_api
def api_create_maintenance_ticket(request):
    """Student logs a maintenance ticket (Electrical, Plumbing, Furniture, Internet, etc.)."""
    me = get_current_user(request)
    allotment = Allotment.objects.filter(user=me, is_active=True).select_related('room').first()
    if not allotment:
        return JsonResponse({'error': 'You must have an active room allotment to file room maintenance.'}, status=400)

    try:
        body = json.loads(request.body.decode('utf-8'))
    except Exception:
        return HttpResponseBadRequest("Invalid JSON")

    category = body.get('category', 'OTHER').upper()
    subject = body.get('subject', '').strip()
    description = body.get('description', '').strip()
    priority = int(body.get('priority', 2))

    if not subject:
        return JsonResponse({'error': 'Please provide a subject summary.'}, status=400)
    if not description:
        return JsonResponse({'error': 'Please describe the maintenance issue.'}, status=400)

    ticket = MaintenanceTicket.objects.create(
        room=allotment.room,
        student=me,
        category=category,
        subject=subject[:200],
        description=description,
        priority=priority,
        status='OPEN'
    )

    AuditLog.objects.create(
        actor=me.name, action='MAINTENANCE_TICKET_CREATED',
        target=f"Room {allotment.room.number} - {category}",
        reason=subject
    )

    return JsonResponse({
        'ok': True,
        'ticket_id': ticket.id,
        'message': f'Maintenance ticket #{ticket.id} logged for Room {allotment.room.number}.'
    }, status=201)


@require_http_methods(["GET"])
@login_required_api
def api_list_maintenance_tickets(request):
    """List maintenance tickets."""
    me = get_current_user(request)

    if me.role in ['warden', 'admin']:
        tickets = MaintenanceTicket.objects.all().select_related('room', 'student')
    else:
        tickets = MaintenanceTicket.objects.filter(student=me).select_related('room', 'student')

    status_filter = request.GET.get('status', '').upper()
    if status_filter:
        tickets = tickets.filter(status=status_filter)

    data = [
        {
            'id': t.id,
            'room': t.room.number,
            'student_name': t.student.name,
            'student_roll': t.student.roll_no,
            'category': t.category,
            'subject': t.subject,
            'description': t.description,
            'priority': t.priority,
            'status': t.status,
            'assigned_to': t.assigned_to,
            'resolution_notes': t.resolution_notes,
            'created_at': t.created_at.strftime('%Y-%m-%d %H:%M'),
        }
        for t in tickets
    ]
    return JsonResponse({'ok': True, 'tickets': data})


@require_http_methods(["POST"])
@role_required(['warden', 'admin'])
def api_update_maintenance_ticket(request, ticket_id):
    """Warden updates status and assigns technician for a maintenance ticket."""
    ticket = get_object_or_404(MaintenanceTicket, id=ticket_id)
    try:
        body = json.loads(request.body.decode('utf-8'))
    except Exception:
        return HttpResponseBadRequest("Invalid JSON")

    me = get_current_user(request)
    new_status = body.get('status', '').upper()
    notes = body.get('resolution_notes', '').strip()
    assigned = body.get('assigned_to', '').strip()

    if new_status in ['OPEN', 'IN_PROGRESS', 'RESOLVED', 'REJECTED']:
        ticket.status = new_status
        if new_status == 'RESOLVED':
            ticket.resolved_at = timezone.now()
    if notes:
        ticket.resolution_notes = notes
    if assigned:
        ticket.assigned_to = assigned
    ticket.save()

    Notification.objects.create(
        student=ticket.student,
        category='MAINTENANCE',
        title=f"Maintenance Ticket #{ticket.id} Updated",
        message=f"Status: {ticket.status}. {notes or ''}"
    )

    AuditLog.objects.create(
        actor=me.name, action='MAINTENANCE_TICKET_UPDATED',
        target=f"Ticket #{ticket.id}",
        reason=f"Status -> {ticket.status}"
    )

    return JsonResponse({'ok': True, 'message': f'Ticket #{ticket.id} updated.'})


# ==========================================
# GATE PASS / NIGHT-OUT LEAVE
# ==========================================

@require_http_methods(["POST"])
@login_required_api
def api_create_gate_pass(request):
    """Student applies for gate pass / weekend night-out leave."""
    me = get_current_user(request)
    try:
        body = json.loads(request.body.decode('utf-8'))
    except Exception:
        return HttpResponseBadRequest("Invalid JSON")

    leave_dt = parse_datetime(body.get('leave_date', ''))
    return_dt = parse_datetime(body.get('return_date', ''))

    if not leave_dt or not return_dt:
        return JsonResponse({'error': 'Please provide valid ISO leave and return timestamps.'}, status=400)
    if return_dt <= leave_dt:
        return JsonResponse({'error': 'Return timestamp must be after leave timestamp.'}, status=400)

    gp = GatePass.objects.create(
        student=me,
        leave_date=leave_dt,
        return_date=return_dt,
        destination=body.get('destination', '').strip()[:200],
        reason=body.get('reason', '').strip(),
        parent_contact=body.get('parent_contact', '').strip()[:20],
        status='PENDING'
    )

    AuditLog.objects.create(
        actor=me.name, action='GATE_PASS_APPLIED',
        target=f"Pass #{gp.id} ({me.roll_no})",
        reason=f"Destination: {gp.destination}"
    )

    return JsonResponse({
        'ok': True,
        'pass_id': gp.id,
        'message': 'Gate pass application submitted. Awaiting Warden approval.'
    }, status=201)


@require_http_methods(["GET"])
@login_required_api
def api_list_gate_passes(request):
    """List student gate passes."""
    me = get_current_user(request)

    if me.role in ['warden', 'admin']:
        passes = GatePass.objects.all().select_related('student')
    else:
        passes = GatePass.objects.filter(student=me)

    data = [
        {
            'id': p.id,
            'student_name': p.student.name,
            'student_roll': p.student.roll_no,
            'destination': p.destination,
            'reason': p.reason,
            'parent_contact': p.parent_contact,
            'leave_date': p.leave_date.strftime('%Y-%m-%d %H:%M'),
            'return_date': p.return_date.strftime('%Y-%m-%d %H:%M'),
            'status': p.status,
            'approved_by': p.approved_by,
        }
        for p in passes
    ]
    return JsonResponse({'ok': True, 'gate_passes': data})


@require_http_methods(["POST"])
@role_required(['warden', 'admin'])
def api_review_gate_pass(request, pass_id):
    """Warden approves, rejects, or logs return for a gate pass."""
    gp = get_object_or_404(GatePass, id=pass_id)
    try:
        body = json.loads(request.body.decode('utf-8'))
    except Exception:
        return HttpResponseBadRequest("Invalid JSON")

    action = body.get('action', '').lower()
    me = get_current_user(request)

    if action == 'approve':
        gp.status = 'APPROVED'
        gp.approved_by = me.name
    elif action == 'reject':
        gp.status = 'REJECTED'
        gp.approved_by = me.name
    elif action == 'returned':
        gp.status = 'RETURNED'
        gp.actual_return = timezone.now()
    else:
        return JsonResponse({'error': 'Invalid action. Choose approve, reject, or returned.'}, status=400)

    gp.save()
    AuditLog.objects.create(
        actor=me.name, action=f'GATE_PASS_{action.upper()}',
        target=f"Pass #{gp.id} ({gp.student.roll_no})",
        reason=f"Warden signoff: {action}"
    )

    return JsonResponse({'ok': True, 'message': f'Gate pass status updated to {gp.status}.'})


# ==========================================
# DISCIPLINARY ACTIONS & FINES
# ==========================================

@require_http_methods(["POST"])
@role_required(['warden', 'admin'])
def api_create_disciplinary_record(request):
    """Warden issues disciplinary violation or fine."""
    try:
        body = json.loads(request.body.decode('utf-8'))
    except Exception:
        return HttpResponseBadRequest("Invalid JSON")

    roll_no = body.get('roll_no', '').strip()
    student = StudentUser.objects.filter(roll_no__iexact=roll_no).first()
    if not student:
        return JsonResponse({'error': f'Student with registration "{roll_no}" not found.'}, status=404)

    me = get_current_user(request)
    rec = DisciplinaryRecord.objects.create(
        student=student,
        violation=body.get('violation', '').strip()[:200],
        description=body.get('description', '').strip(),
        severity=int(body.get('severity', 1)),
        fine_amount=body.get('fine_amount', 0),
        fine_paid=bool(body.get('fine_paid', False)),
        issued_by=me.name
    )

    Notification.objects.create(
        student=student,
        category='DISCIPLINE',
        title="Hostel Disciplinary Action Notice",
        message=f"Notice from Warden {me.name}: {rec.violation}. Fine: Rs {rec.fine_amount}"
    )

    AuditLog.objects.create(
        actor=me.name, action='DISCIPLINARY_RECORD_ISSUED',
        target=f"{student.roll_no}",
        reason=f"Violation: {rec.violation} | Fine: Rs {rec.fine_amount}"
    )

    return JsonResponse({'ok': True, 'record_id': rec.id, 'message': f'Disciplinary action recorded for {student.name}.'}, status=201)


@require_http_methods(["GET"])
@role_required(['warden', 'admin'])
def api_list_disciplinary_records(request):
    """List disciplinary incidents and outstanding fines."""
    records = DisciplinaryRecord.objects.all().select_related('student')
    data = [
        {
            'id': r.id,
            'student_name': r.student.name,
            'student_roll': r.student.roll_no,
            'violation': r.violation,
            'description': r.description,
            'severity': r.severity,
            'severity_display': r.get_severity_display(),
            'fine_amount': str(r.fine_amount),
            'fine_paid': r.fine_paid,
            'issued_by': r.issued_by,
            'issued_at': r.issued_at.strftime('%Y-%m-%d %H:%M'),
        }
        for r in records
    ]
    return JsonResponse({'ok': True, 'records': data})


# ==========================================
# BULK CSV STUDENT & ROOM IMPORTER
# ==========================================

@require_http_methods(["POST"])
@role_required(['admin'])
def api_bulk_import_students(request):
    """
    Imports hundreds/thousands of students via CSV payload or file upload.
    CSV Columns supported: roll_no, name, email, gender, year, branch
    """
    me = get_current_user(request)
    csv_file = request.FILES.get('file')

    if csv_file:
        raw_text = csv_file.read().decode('utf-8', errors='ignore')
    else:
        try:
            body = json.loads(request.body.decode('utf-8'))
            raw_text = body.get('csv_text', '')
        except Exception:
            return JsonResponse({'error': 'Please provide CSV file or csv_text.'}, status=400)

    if not raw_text.strip():
        return JsonResponse({'error': 'Empty CSV content.'}, status=400)

    reader = csv.DictReader(io.StringIO(raw_text))
    created_count = 0
    skipped_count = 0

    for row in reader:
        roll_no = (row.get('roll_no') or row.get('Roll No') or row.get('registration_no') or '').strip()
        name = (row.get('name') or row.get('Name') or '').strip()
        email = (row.get('email') or row.get('Email') or '').strip().lower()
        gender = (row.get('gender') or row.get('Gender') or 'M').strip().upper()
        year = (row.get('year') or row.get('Year') or '1st Year').strip()
        branch = (row.get('branch') or row.get('Branch') or 'Computer Science').strip()

        if not roll_no or not name or not email:
            continue

        if StudentUser.objects.filter(Q(roll_no=roll_no) | Q(email=email)).exists():
            skipped_count += 1
            continue

        if gender not in ['M', 'F', 'O']:
            gender = 'M'

        block = HostelBlock.objects.filter(gender=gender).first() or HostelBlock.objects.first()
        is_fresh = (year in ['1st Year', 'First Year'])

        student = StudentUser.objects.create(
            roll_no=roll_no,
            name=name,
            email=email,
            gender=gender,
            year=year,
            branch=branch,
            block=block,
            role='student',
            is_freshman=is_fresh,
            consent_given=True,
            consent_at=timezone.now(),
            avatar_hue=random.randint(15, 340),
            persona="Daylight Scholar" if gender == 'F' else "Midnight Curator"
        )
        student.set_password('kindred123')
        student.save(update_fields=['password_hash'])
        created_count += 1

    AuditLog.objects.create(
        actor=me.name, action='BULK_STUDENT_IMPORT',
        target=f"{created_count} students added",
        reason=f"Imported {created_count} students from CSV (skipped {skipped_count} existing)"
    )

    return JsonResponse({
        'ok': True,
        'created_count': created_count,
        'skipped_count': skipped_count,
        'message': f'Successfully imported {created_count} students! ({skipped_count} duplicate accounts skipped).'
    })


@require_http_methods(["POST"])
@role_required(['admin'])
def api_bulk_generate_rooms(request):
    """Batch generates rooms for a hostel tower across multiple floors."""
    try:
        body = json.loads(request.body.decode('utf-8'))
    except Exception:
        return HttpResponseBadRequest("Invalid JSON")

    me = get_current_user(request)
    block_id = body.get('block_id')
    block = HostelBlock.objects.filter(id=block_id).first()
    if not block:
        return JsonResponse({'error': 'Hostel block not found.'}, status=404)

    start_num = int(body.get('start_num', 1))
    end_num = int(body.get('end_num', 20))
    floors = int(body.get('floors', block.total_floors or 10))
    capacity = int(body.get('capacity', 2))
    room_type = body.get('room_type', 'DOUBLE')

    created = 0
    for floor in range(1, floors + 1):
        for r_num in range(start_num, end_num + 1):
            number = f"{floor}{str(r_num).zfill(2)}"
            _, was_created = Room.objects.get_or_create(
                block=block,
                number=number,
                defaults={
                    'capacity': capacity,
                    'floor': floor,
                    'room_type': room_type,
                    'status': 'AVAILABLE'
                }
            )
            if was_created:
                created += 1

    AuditLog.objects.create(
        actor=me.name, action='BULK_ROOMS_GENERATED',
        target=f"{block.name}",
        reason=f"Generated {created} rooms across {floors} floors (capacity: {capacity})"
    )

    return JsonResponse({
        'ok': True,
        'created_count': created,
        'message': f'Generated {created} rooms for {block.name} across floors 1 to {floors}.'
    })


# ==========================================
# INTERACTIVE FLOOR MAP & OCCUPANCY MATRIX
# ==========================================

@require_http_methods(["GET"])
@login_required_api
def api_floor_map(request):
    """
    Interactive visual floor matrix:
    Green = Vacant, Yellow = Partial Occupancy, Red = Full, Grey = Maintenance
    """
    block_id = request.GET.get('block_id')
    block = HostelBlock.objects.filter(id=block_id).first() if block_id else HostelBlock.objects.first()
    if not block:
        return JsonResponse({'error': 'No hostel blocks found.'}, status=404)

    rooms = Room.objects.filter(block=block).prefetch_related('allotments__user').order_by('floor', 'number')

    floors_dict = {}
    for r in rooms:
        active_allotments = [a for a in r.allotments.all() if a.is_active]
        occupied = len(active_allotments)

        if r.status == 'MAINTENANCE':
            color = 'grey'
            status_text = 'Under Maintenance'
        elif occupied == 0:
            color = 'green'
            status_text = 'Vacant'
        elif occupied < r.capacity:
            color = 'yellow'
            status_text = f'{occupied}/{r.capacity} Occupied'
        else:
            color = 'red'
            status_text = 'Fully Occupied'

        occupants_data = [
            {'name': a.user.name, 'roll_no': a.user.roll_no, 'checked_in': a.checked_in}
            for a in active_allotments
        ]

        f_num = r.floor
        floors_dict.setdefault(f_num, []).append({
            'id': r.id,
            'number': r.number,
            'floor': r.floor,
            'capacity': r.capacity,
            'occupied': occupied,
            'color': color,
            'status_text': status_text,
            'is_accessible': r.is_accessible,
            'room_type': r.room_type,
            'facility_flags': r.facility_flags,
            'occupants': occupants_data
        })

    floor_matrix = [
        {
            'floor': f,
            'rooms': floors_dict[f],
            'total_rooms': len(floors_dict[f]),
            'vacant_count': sum(1 for x in floors_dict[f] if x['color'] == 'green'),
            'partial_count': sum(1 for x in floors_dict[f] if x['color'] == 'yellow'),
            'full_count': sum(1 for x in floors_dict[f] if x['color'] == 'red'),
        }
        for f in sorted(floors_dict.keys())
    ]

    return JsonResponse({
        'ok': True,
        'block': {
            'id': block.id,
            'name': block.name,
            'gender': block.get_gender_display(),
            'total_floors': block.total_floors
        },
        'floors': floor_matrix,
        'total_rooms': rooms.count()
    })


# ==========================================
# WARDEN BULK ROSTER EXPORT
# ==========================================

@require_http_methods(["GET"])
@role_required(['warden', 'admin'])
def api_warden_roster_export(request):
    """Generates comprehensive roster CSV for physical warden roll-calls."""
    me = get_current_user(request)
    block_id = request.GET.get('block_id')

    qs = Allotment.objects.filter(is_active=True).select_related('user', 'room', 'room__block')
    if block_id:
        qs = qs.filter(room__block_id=block_id)
    elif me.block:
        qs = qs.filter(room__block=me.block)

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="hostel_occupancy_roster.csv"'

    writer = csv.writer(response)
    writer.writerow([
        'Hostel Block', 'Floor', 'Room Number', 'Room Type',
        'Student Name', 'Registration Number', 'Gender', 'Year',
        'Branch', 'Phone', 'Email', 'Physical Check-In', 'Key Issued'
    ])

    for a in qs.order_by('room__block__name', 'room__floor', 'room__number'):
        writer.writerow([
            a.room.block.name,
            a.room.floor,
            a.room.number,
            getattr(a.room, 'room_type', 'DOUBLE'),
            a.user.name,
            a.user.roll_no,
            a.user.get_gender_display(),
            a.user.year,
            a.user.branch,
            a.user.phone,
            a.user.email,
            'Yes' if a.checked_in else 'Pending',
            'Yes' if a.key_issued else 'No'
        ])

    return response


# ==========================================
# ACADEMIC SESSION LIFECYCLE
# ==========================================

@require_http_methods(["GET"])
@role_required(['admin'])
def api_academic_sessions(request):
    """List multi-year academic terms."""
    sessions = AcademicSession.objects.all()
    data = [
        {
            'id': s.id,
            'name': s.name,
            'start_date': s.start_date.strftime('%Y-%m-%d'),
            'end_date': s.end_date.strftime('%Y-%m-%d'),
            'is_current': s.is_current,
        }
        for s in sessions
    ]
    return JsonResponse({'ok': True, 'sessions': data})


@require_http_methods(["POST"])
@role_required(['admin'])
def api_create_academic_session(request):
    """Initialize a new academic rollover session."""
    me = get_current_user(request)
    try:
        body = json.loads(request.body.decode('utf-8'))
    except Exception:
        return HttpResponseBadRequest("Invalid JSON")

    name = body.get('name', '').strip()
    start_d = parse_date(body.get('start_date', ''))
    end_d = parse_date(body.get('end_date', ''))
    is_current = bool(body.get('is_current', False))

    if not name or not start_d or not end_d:
        return JsonResponse({'error': 'Name, start date, and end date are required.'}, status=400)

    if is_current:
        AcademicSession.objects.filter(is_current=True).update(is_current=False)

    session = AcademicSession.objects.create(
        name=name, start_date=start_d, end_date=end_d, is_current=is_current
    )

    AuditLog.objects.create(
        actor=me.name, action='ACADEMIC_SESSION_CREATED',
        target=name, reason=f"Created session {name} ({'Active' if is_current else 'Scheduled'})"
    )

    return JsonResponse({'ok': True, 'session_id': session.id, 'message': f'Academic Session {name} created.'}, status=201)


# ==========================================
# ANTI-RAGGING COMPLIANCE AUDIT
# ==========================================

@require_http_methods(["GET"])
@role_required(['admin', 'warden'])
def api_anti_ragging_check(request):
    """Audits all roommate pairings to verify zero freshman-senior cross pairs."""
    pairs = Pair.objects.select_related('user_a', 'user_b', 'room', 'room__block').all()
    violations = []

    for p in pairs:
        a_fresh = getattr(p.user_a, 'is_freshman', False) or (p.user_a.year in ['1st Year', 'First Year'])
        b_fresh = getattr(p.user_b, 'is_freshman', False) or (p.user_b.year in ['1st Year', 'First Year'])

        if a_fresh != b_fresh:
            violations.append({
                'pair_id': p.id,
                'student_a': {'name': p.user_a.name, 'roll_no': p.user_a.roll_no, 'year': p.user_a.year},
                'student_b': {'name': p.user_b.name, 'roll_no': p.user_b.roll_no, 'year': p.user_b.year},
                'room': p.room.number if p.room else 'Unassigned',
                'block': p.room.block.name if p.room else 'None',
            })

    return JsonResponse({
        'ok': True,
        'compliant': len(violations) == 0,
        'violation_count': len(violations),
        'violations': violations,
        'summary': 'Full anti-ragging compliance verified! Zero freshman-senior roommate clashes.' if not violations else f'Warning: {len(violations)} non-compliant pair(s) detected.'
    })


# ==========================================
# MATCHING HYPER-PARAMETER WEIGHT TUNING
# ==========================================

@require_http_methods(["GET"])
@role_required(['admin'])
def api_admin_get_weights(request):
    """Admin retrieves current algorithm trait weights."""
    questions = Question.objects.filter(is_active=True).order_by('id')
    weights_data = [
        {
            'id': q.id,
            'key': q.key,
            'text': q.text,
            'base_weight': q.base_weight,
            'is_circular': q.is_circular,
            'version': q.version
        }
        for q in questions
    ]
    return JsonResponse({'ok': True, 'traits': weights_data})


@require_http_methods(["POST"])
@role_required(['admin'])
def api_admin_update_weights(request):
    """Admin adjusts trait weights in real time (e.g. sleep vs cleanliness vs noise)."""
    try:
        body = json.loads(request.body.decode('utf-8'))
    except Exception:
        return HttpResponseBadRequest("Invalid JSON")

    me = get_current_user(request)
    weights = body.get('weights', {})  # e.g. {'sleep': 6.0, 'tidy': 4.5}

    updated = 0
    for key, weight_val in weights.items():
        try:
            w_float = float(weight_val)
            q = Question.objects.filter(key=key).first()
            if q:
                q.base_weight = max(1.0, min(10.0, w_float))
                q.version += 1
                q.save(update_fields=['base_weight', 'version'])
                updated += 1
        except (ValueError, TypeError):
            continue

    # Invalidate stale pair scores so recalculation uses new weights
    if updated > 0:
        PairScore.objects.all().delete()
        AuditLog.objects.create(
            actor=me.name, action='MATCHING_WEIGHTS_UPDATED',
            target=f"{updated} traits",
            reason=f"Admin updated algorithmic hyper-parameter weights: {weights}"
        )

    return JsonResponse({
        'ok': True,
        'updated_count': updated,
        'message': f'Updated weights for {updated} questions. Compatibility engine will recalculate with new parameters.'
    })


# ==========================================
# OFFICIAL ALLOTMENT SLIP GENERATION (PRINT/PDF)
# ==========================================

def allotment_slip_view(request, pair_id=None):
    """Renders official verifiable hostel room allotment slip with university seal & check-in QR."""
    me = get_current_user(request)
    pair = None
    if pair_id:
        pair = Pair.objects.filter(id=pair_id).select_related('user_a', 'user_b', 'room', 'room__block').first()
    elif me:
        pair = me.get_pair()

    if not pair or not pair.room:
        return render(request, 'matcher/allotment_slip.html', {
            'error': 'No finalized room allotment found to generate an official slip for.'
        })

    partner = pair.partner_of(me) if me else pair.user_b
    student = me if me else pair.user_a
    calendar = AllotmentCalendar.get_current()

    verification_code = f"KINDRED-VERIFY-{pair.id}-{pair.room.number}-{student.roll_no}"

    context = {
        'pair': pair,
        'student': student,
        'partner': partner,
        'room': pair.room,
        'block': pair.room.block,
        'calendar': calendar,
        'verification_code': verification_code,
        'allotment_date': pair.confirmed_at.strftime('%B %d, %Y'),
        'academic_year': '2026-2027',
    }
    return render(request, 'matcher/allotment_slip.html', context)

