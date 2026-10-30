from django.urls import path
from . import views

app_name = 'matcher'

urlpatterns = [
    # Public Home / Landing Page
    path('', views.home_view, name='home'),

    # Authentication & Access Portals
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('api/auth/send-otp/', views.api_send_otp, name='api_send_otp'),
    path('api/auth/login/', views.api_login, name='api_login'),

    # Student Matcher Portal
    path('student/', views.index_view, name='student_portal'),
    path('matcher/', views.index_view, name='matcher_alias'),
    path('index/', views.index_view, name='index'),

    # Role Specific Portals
    path('warden/', views.warden_dashboard_view, name='warden_dashboard'),
    path('caretaker/', views.caretaker_dashboard_view, name='caretaker_dashboard'),
    path('api/caretaker/toggle/', views.api_caretaker_toggle, name='api_caretaker_toggle'),
    path('admin-portal/', views.admin_dashboard_view, name='admin_dashboard'),
    path('api/admin/export-csv/', views.api_admin_export_csv, name='api_admin_export_csv'),

    # Student & Matching APIs
    path('api/me/', views.api_me, name='api_me'),
    path('api/consent/agree/', views.api_consent_agree, name='api_consent_agree'),
    path('api/students/', views.api_students_list, name='api_students_list'),
    path('api/students/switch/', views.api_switch_student, name='api_switch_student'),
    path('api/switch-student/', views.api_switch_student, name='api_switch_student_alias'),
    path('api/quiz/submit/', views.api_submit_quiz, name='api_submit_quiz'),
    path('api/matches/', views.api_matches, name='api_matches'),
    path('api/requests/', views.api_get_requests, name='api_get_requests'),
    path('api/requests/send/', views.api_send_request, name='api_send_request'),
    path('api/requests/<int:request_id>/respond/', views.api_respond_request, name='api_respond_request'),
    path('api/requests/<int:request_id>/cancel/', views.api_cancel_request, name='api_cancel_request'),

    # Warden & Admin APIs
    path('api/warden/allot/<int:pairing_id>/', views.api_warden_allot, name='api_warden_allot'),
    path('api/admin/set-phase/', views.api_set_calendar_phase, name='api_set_calendar_phase'),
    path('api/admin/run-blossom/', views.api_run_blossom_matching, name='api_run_blossom_matching'),
    path('api/admin/auto-allot/', views.api_auto_allot_rooms, name='api_auto_allot_rooms'),
]
