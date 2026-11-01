from django.contrib import admin
from .models import (
    HostelBlock, Room, StudentUser, AllotmentCalendar,
    Question, Response, PairScore, Request, Pair, Allotment, AuditLog,
    GuardianConsent, Ticket, Feedback, Notification,
    AcademicSession, HostelFee, EmergencyContact, HostelCheckin,
    RoomSwapRequest, MaintenanceTicket, GatePass, DisciplinaryRecord
)


@admin.register(HostelBlock)
class HostelBlockAdmin(admin.ModelAdmin):
    list_display = ('name', 'gender', 'total_floors', 'campus')
    list_filter = ('gender', 'campus')


@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):
    list_display = ('block', 'number', 'capacity', 'floor', 'is_accessible', 'occupied_count', 'is_available')
    list_filter = ('block', 'floor', 'is_accessible')
    search_fields = ('number', 'block__name')


@admin.register(StudentUser)
class StudentUserAdmin(admin.ModelAdmin):
    list_display = ('name', 'roll_no', 'role', 'gender', 'year', 'branch', 'block', 'persona', 'is_paired', 'consent_given')
    list_filter = ('role', 'gender', 'year', 'block', 'consent_given')
    search_fields = ('name', 'roll_no', 'email', 'branch')


@admin.register(AllotmentCalendar)
class AllotmentCalendarAdmin(admin.ModelAdmin):
    list_display = ('phase', 'survey_deadline', 'matching_deadline', 'freeze_at', 'updated_at', 'updated_by')


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ('key', 'text', 'base_weight', 'version', 'is_active')
    list_filter = ('version', 'is_active')


@admin.register(Response)
class ResponseAdmin(admin.ModelAdmin):
    list_display = ('user', 'question', 'answer', 'importance', 'updated_at')
    list_filter = ('importance', 'question')
    search_fields = ('user__name', 'user__roll_no')


@admin.register(PairScore)
class PairScoreAdmin(admin.ModelAdmin):
    list_display = ('user_a', 'user_b', 'final_score', 'score_a_to_b', 'score_b_to_a', 'computed_at')
    search_fields = ('user_a__name', 'user_b__name', 'user_a__roll_no', 'user_b__roll_no')


@admin.register(Request)
class RequestAdmin(admin.ModelAdmin):
    list_display = ('from_user', 'to_user', 'status', 'created_at', 'expires_at')
    list_filter = ('status', 'created_at')
    search_fields = ('from_user__name', 'to_user__name')


@admin.register(Pair)
class PairAdmin(admin.ModelAdmin):
    list_display = ('user_a', 'user_b', 'room', 'method', 'status', 'confirmed_at')
    list_filter = ('method', 'status')
    search_fields = ('user_a__name', 'user_b__name', 'room__number')


@admin.register(Allotment)
class AllotmentAdmin(admin.ModelAdmin):
    list_display = ('room', 'user', 'allotted_by', 'allotted_at', 'is_active')
    list_filter = ('is_active', 'allotted_at')
    search_fields = ('user__name', 'room__number')


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ('timestamp', 'actor', 'action', 'target', 'reason')
    list_filter = ('action', 'timestamp')
    search_fields = ('actor', 'target', 'reason')


@admin.register(GuardianConsent)
class GuardianConsentAdmin(admin.ModelAdmin):
    list_display = ('student', 'is_minor', 'guardian_name', 'guardian_email', 'consent_verified', 'verified_at')
    list_filter = ('is_minor', 'consent_verified')
    search_fields = ('student__name', 'student__roll_no', 'guardian_name', 'guardian_email')


@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):
    list_display = ('student', 'ticket_type', 'subject', 'status', 'created_at')
    list_filter = ('ticket_type', 'status', 'created_at')
    search_fields = ('student__name', 'student__roll_no', 'subject', 'description')


@admin.register(Feedback)
class FeedbackAdmin(admin.ModelAdmin):
    list_display = ('student', 'roommate_harmony_rating', 'cleanliness_rating', 'would_recommend_partner', 'submitted_at')
    list_filter = ('roommate_harmony_rating', 'would_recommend_partner')
    search_fields = ('student__name', 'student__roll_no', 'comments')


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('student', 'title', 'category', 'is_read', 'created_at')
    list_filter = ('category', 'is_read', 'created_at')
    search_fields = ('student__name', 'student__roll_no', 'title', 'message')


@admin.register(AcademicSession)
class AcademicSessionAdmin(admin.ModelAdmin):
    list_display = ('name', 'start_date', 'end_date', 'is_current', 'created_at')
    list_filter = ('is_current',)
    search_fields = ('name',)


@admin.register(HostelFee)
class HostelFeeAdmin(admin.ModelAdmin):
    list_display = ('student', 'academic_year', 'amount', 'status', 'transaction_ref', 'created_at', 'verified_at')
    list_filter = ('status', 'academic_year')
    search_fields = ('student__name', 'student__roll_no', 'transaction_ref')


@admin.register(EmergencyContact)
class EmergencyContactAdmin(admin.ModelAdmin):
    list_display = ('student', 'blood_group', 'parent_name', 'parent_phone', 'local_guardian_name')
    search_fields = ('student__name', 'student__roll_no', 'parent_name')


@admin.register(HostelCheckin)
class HostelCheckinAdmin(admin.ModelAdmin):
    list_display = ('allotment', 'checkin_date', 'key_issued', 'warden_signoff', 'signed_at')
    list_filter = ('key_issued', 'warden_signoff')


@admin.register(RoomSwapRequest)
class RoomSwapRequestAdmin(admin.ModelAdmin):
    list_display = ('requester', 'requester_pair', 'target_pair', 'status', 'created_at')
    list_filter = ('status',)
    search_fields = ('requester__name', 'requester__roll_no')


@admin.register(MaintenanceTicket)
class MaintenanceTicketAdmin(admin.ModelAdmin):
    list_display = ('room', 'student', 'category', 'subject', 'priority', 'status', 'created_at')
    list_filter = ('category', 'priority', 'status')
    search_fields = ('student__name', 'subject', 'description')


@admin.register(GatePass)
class GatePassAdmin(admin.ModelAdmin):
    list_display = ('student', 'leave_date', 'return_date', 'destination', 'status', 'approved_by')
    list_filter = ('status',)
    search_fields = ('student__name', 'student__roll_no', 'destination')


@admin.register(DisciplinaryRecord)
class DisciplinaryRecordAdmin(admin.ModelAdmin):
    list_display = ('student', 'violation', 'severity', 'fine_amount', 'fine_paid', 'issued_by', 'issued_at')
    list_filter = ('severity', 'fine_paid')
    search_fields = ('student__name', 'student__roll_no', 'violation')
