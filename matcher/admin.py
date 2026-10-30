from django.contrib import admin
from .models import (
    HostelBlock, Room, StudentUser, AllotmentCalendar,
    Question, Response, PairScore, Request, Pair, Allotment, AuditLog
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