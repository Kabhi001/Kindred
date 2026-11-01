from django.urls import path
from . import views

app_name = 'matcher'

urlpatterns = [
    # Public Home / Landing Page
    path('', views.home_view, name='home'),

    # Authentication & Access Portals
    path('login/', views.login_view, name='login'),
    path('register/', views.register_view, name='register'),
    path('logout/', views.logout_view, name='logout'),
    path('api/auth/send-otp/', views.api_send_otp, name='api_send_otp'),
    path('api/auth/register/', views.api_register, name='api_register'),
    path('api/auth/login/', views.api_login, name='api_login'),

    # Password Reset & Recovery
    path('api/auth/password-reset/', views.api_password_reset_request, name='api_password_reset_request'),
    path('api/auth/password-reset/confirm/', views.api_password_reset_confirm, name='api_password_reset_confirm'),

    # Student Matcher Portal
    path('student/', views.index_view, name='student_portal'),
    path('matcher/', views.index_view, name='matcher_alias'),
    path('index/', views.index_view, name='index'),

    # Role Specific Portals
    path('warden/', views.warden_dashboard_view, name='warden_dashboard'),
    path('admin-portal/', views.admin_dashboard_view, name='admin_dashboard'),
    path('api/admin/export-csv/', views.api_admin_export_csv, name='api_admin_export_csv'),

    # Student & Matching APIs
    path('api/me/', views.api_me, name='api_me'),
    path('api/profile/update/', views.api_update_profile, name='api_update_profile'),
    path('api/consent/agree/', views.api_consent_agree, name='api_consent_agree'),
    path('api/consent/withdraw/', views.api_withdraw_consent, name='api_withdraw_consent'),
    path('api/students/', views.api_students_list, name='api_students_list'),
    path('api/students/switch/', views.api_switch_student, name='api_switch_student'),
    path('api/switch-student/', views.api_switch_student, name='api_switch_student_alias'),
    path('api/quiz/submit/', views.api_submit_quiz, name='api_submit_quiz'),
    path('api/matches/', views.api_matches, name='api_matches'),
    path('api/requests/', views.api_get_requests, name='api_get_requests'),
    path('api/requests/send/', views.api_send_request, name='api_send_request'),
    path('api/requests/<int:request_id>/respond/', views.api_respond_request, name='api_respond_request'),
    path('api/requests/<int:request_id>/cancel/', views.api_cancel_request, name='api_cancel_request'),

    # Student Welfare & Emergency Profile
    path('api/emergency-contact/', views.api_emergency_contact, name='api_emergency_contact'),

    # Hostel Fee Clearance & Payment Tracking
    path('api/fees/', views.api_fee_status, name='api_fee_status'),
    path('api/fees/submit-payment/', views.api_submit_fee_payment, name='api_submit_fee_payment'),
    path('api/fees/verify/', views.api_verify_fee, name='api_verify_fee'),

    # Physical Check-In & QR Verification
    path('api/checkin/', views.api_checkin_student, name='api_checkin_student'),
    path('api/checkin/status/', views.api_checkin_status, name='api_checkin_status'),

    # Mutual Room Swap & Re-Allocation
    path('api/swap/create/', views.api_create_swap_request, name='api_create_swap_request'),
    path('api/swap/list/', views.api_list_swap_requests, name='api_list_swap_requests'),
    path('api/swap/<int:swap_id>/review/', views.api_review_swap_request, name='api_review_swap_request'),

    # Maintenance & Grievance Tickets
    path('api/maintenance/', views.api_list_maintenance_tickets, name='api_list_maintenance_tickets'),
    path('api/maintenance/create/', views.api_create_maintenance_ticket, name='api_create_maintenance_ticket'),
    path('api/maintenance/<int:ticket_id>/update/', views.api_update_maintenance_ticket, name='api_update_maintenance_ticket'),

    # Digital Gate Pass & Night-Out Leave
    path('api/gatepass/', views.api_list_gate_passes, name='api_list_gate_passes'),
    path('api/gatepass/create/', views.api_create_gate_pass, name='api_create_gate_pass'),
    path('api/gatepass/<int:pass_id>/review/', views.api_review_gate_pass, name='api_review_gate_pass'),

    # Disciplinary & Fine Tracking
    path('api/discipline/', views.api_list_disciplinary_records, name='api_list_disciplinary_records'),
    path('api/discipline/create/', views.api_create_disciplinary_record, name='api_create_disciplinary_record'),

    # Interactive Floor Map Matrix
    path('api/floormap/', views.api_floor_map, name='api_floor_map'),
    path('api/floor-map/', views.api_floor_map, name='api_floor_map_alias'),

    # Warden Operations & Bulk Roster Export
    path('api/warden/allot/<int:pairing_id>/', views.api_warden_allot, name='api_warden_allot'),
    path('api/warden/roster-export/', views.api_warden_roster_export, name='api_warden_roster_export'),

    # Admin Control & Phase Management
    path('api/admin/set-phase/', views.api_set_calendar_phase, name='api_set_calendar_phase'),
    path('api/admin/run-blossom/', views.api_run_blossom_matching, name='api_run_blossom_matching'),
    path('api/admin/auto-allot/', views.api_auto_allot_rooms, name='api_auto_allot_rooms'),
    path('api/admin/wardens/assign/', views.api_admin_assign_warden, name='api_admin_assign_warden'),
    path('api/admin/wardens/create/', views.api_admin_create_warden, name='api_admin_create_warden'),
    path('api/admin/wardens/<int:user_id>/revoke/', views.api_admin_revoke_warden, name='api_admin_revoke_warden'),

    # Bulk Student & Room CSV Importer / Generator
    path('api/admin/import-students/', views.api_bulk_import_students, name='api_bulk_import_students'),
    path('api/admin/generate-rooms/', views.api_bulk_generate_rooms, name='api_bulk_generate_rooms'),

    # Multi-Year Academic Session Lifecycle
    path('api/admin/sessions/', views.api_academic_sessions, name='api_academic_sessions'),
    path('api/admin/sessions/create/', views.api_create_academic_session, name='api_create_academic_session'),

    # Statutory Anti-Ragging Audit
    path('api/admin/anti-ragging-check/', views.api_anti_ragging_check, name='api_anti_ragging_check'),

    # Algorithm Hyper-Parameter Weight Tuning
    path('api/admin/weights/', views.api_admin_get_weights, name='api_admin_get_weights'),
    path('api/admin/weights/update/', views.api_admin_update_weights, name='api_admin_update_weights'),

    # Official Downloadable / Printable Allotment Slip
    path('allotment/slip/', views.allotment_slip_view, name='allotment_slip_me'),
    path('allotment/slip/<int:pair_id>/', views.allotment_slip_view, name='allotment_slip_pair'),

    # Dispute Tickets
    path('api/tickets/', views.api_tickets_list, name='api_tickets_list'),
    path('api/tickets/create/', views.api_create_ticket, name='api_create_ticket'),
    path('api/tickets/<int:ticket_id>/update-status/', views.api_update_ticket_status, name='api_update_ticket_status'),

    # Post-Stay Roommate Feedback Loop
    path('api/feedback/submit/', views.api_submit_feedback, name='api_submit_feedback'),
    path('api/feedback/summary/', views.api_feedback_summary, name='api_feedback_summary'),
]
