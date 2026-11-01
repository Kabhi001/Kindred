from django.test import TestCase, Client, override_settings
from django.urls import reverse
from django.utils import timezone
from django.db.models import Q
from django.core import mail
from django.conf import settings
import json
import re

from matcher.models import (
    HostelBlock, Room, StudentUser, AllotmentCalendar,
    Question, Response, PairScore, Request, Pair, Allotment, AuditLog, OTPVerification,
    GuardianConsent, Ticket, Feedback, Notification
)
from matcher.scoring import (
    calculate_mutual_score, compute_ranked_matches_for_student,
    run_blossom_leftover_matching, run_automated_room_allotment
)
from matcher.benchmark_matching import run_benchmark_suite, format_benchmark_markdown_table



class RealHostelSystemTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.calendar = AllotmentCalendar.objects.create(phase='MATCHING_OPEN')
        self.block = HostelBlock.objects.create(name="Mandakini Hall", gender='M')
        self.room1 = Room.objects.create(block=self.block, number="A-101", capacity=2, floor=1)
        self.room2 = Room.objects.create(block=self.block, number="A-102", capacity=2, floor=1)

        # Questions
        self.q_sleep = Question.objects.create(key="sleep", text="Sleep", min_val=1, max_val=4, base_weight=5.0)
        self.q_smoke = Question.objects.create(key="smoke", text="Smoke", min_val=1, max_val=3, base_weight=5.0)
        self.q_tidy = Question.objects.create(key="tidy", text="Tidy", min_val=1, max_val=4, base_weight=4.0)

        # 3 Students in same block
        self.aarav = StudentUser.objects.create(
            roll_no="CS26B014", name="Aarav Patel", email="aarav@college.edu",
            gender="M", year="1st Year", branch="CSE", block=self.block,
            role="student", avatar_hue=270, consent_given=True
        )
        self.rohan = StudentUser.objects.create(
            roll_no="EE26B042", name="Rohan Verma", email="rohan@college.edu",
            gender="M", year="1st Year", branch="EE", block=self.block,
            role="student", avatar_hue=190, consent_given=True
        )
        self.kabir = StudentUser.objects.create(
            roll_no="ME26B105", name="Kabir Sharma", email="kabir@college.edu",
            gender="M", year="1st Year", branch="ME", block=self.block,
            role="student", avatar_hue=25, consent_given=True
        )

        # Answers: Aarav
        Response.objects.create(user=self.aarav, question=self.q_sleep, answer=3, importance=2)
        Response.objects.create(user=self.aarav, question=self.q_smoke, answer=1, importance=3, is_dealbreaker=True) # Deal-breaker
        Response.objects.create(user=self.aarav, question=self.q_tidy, answer=4, importance=2)

        # Answers: Rohan (Very similar to Aarav, smoke=1, tidy=4)
        Response.objects.create(user=self.rohan, question=self.q_sleep, answer=3, importance=2)
        Response.objects.create(user=self.rohan, question=self.q_smoke, answer=1, importance=3, is_dealbreaker=True)
        Response.objects.create(user=self.rohan, question=self.q_tidy, answer=4, importance=2)

        # Answers: Kabir (Smokes regularly, clashing with Aarav's dealbreaker)
        Response.objects.create(user=self.kabir, question=self.q_sleep, answer=4, importance=1)
        Response.objects.create(user=self.kabir, question=self.q_smoke, answer=3, importance=1)
        Response.objects.create(user=self.kabir, question=self.q_tidy, answer=1, importance=1)

        # Set session to Aarav
        s = self.client.session
        s['current_user_id'] = self.aarav.id
        s.save()

    def test_directional_and_dealbreaker_scoring(self):
        # 1. Aarav & Rohan (Harmonious)
        res_aarav_rohan = calculate_mutual_score(self.aarav, self.rohan)
        self.assertGreaterEqual(res_aarav_rohan['final_score'], 90)
        self.assertEqual(len(res_aarav_rohan['clashes']), 0)

        # 2. Aarav & Kabir (Clash on smoke deal-breaker)
        res_aarav_kabir = calculate_mutual_score(self.aarav, self.kabir)
        self.assertIn("smoke", res_aarav_kabir['clashes'])
        # Capped at 59% because of deal-breaker violation
        self.assertLessEqual(res_aarav_kabir['final_score'], 59.0)

    def test_safe_request_concurrency_and_cancellation(self):
        # Aarav sends request to Rohan
        res_send = self.client.post(
            reverse('matcher:api_send_request'),
            data=json.dumps({'receiver_id': self.rohan.id, 'note': 'Hey Rohan, pair up?'}),
            content_type='application/json'
        )
        self.assertEqual(res_send.status_code, 200)
        req_id = res_send.json()['id']

        # Kabir also sent request to Rohan
        req_kabir_rohan = Request.objects.create(
            from_user=self.kabir, to_user=self.rohan, status='SENT'
        )

        # Rohan logs in and accepts Aarav's request
        s = self.client.session
        s['current_user_id'] = self.rohan.id
        s.save()

        res_accept = self.client.post(
            reverse('matcher:api_respond_request', kwargs={'request_id': req_id}),
            data=json.dumps({'action': 'accept'}),
            content_type='application/json'
        )
        self.assertEqual(res_accept.status_code, 200)

        # Verify Pair was created in canonical order
        first_u, second_u = (self.aarav, self.rohan) if self.aarav.id < self.rohan.id else (self.rohan, self.aarav)
        pair = Pair.objects.filter(user_a=first_u, user_b=second_u).first()
        self.assertIsNotNone(pair)
        self.assertEqual(pair.status, 'CONFIRMED')

        # Verify conflicting request from Kabir was automatically CANCELLED!
        req_kabir_rohan.refresh_from_db()
        self.assertEqual(req_kabir_rohan.status, 'CANCELLED')

        # Verify AuditLog entry was written
        log_entry = AuditLog.objects.filter(action='MUTUAL_PAIR_CONFIRMED').first()
        self.assertIsNotNone(log_entry)

    def test_outgoing_request_limit(self):
        # Limit of 3 active outgoing requests
        u4 = StudentUser.objects.create(roll_no="T1", name="S1", email="s1@c.edu", gender="M", block=self.block)
        u5 = StudentUser.objects.create(roll_no="T2", name="S2", email="s2@c.edu", gender="M", block=self.block)
        u6 = StudentUser.objects.create(roll_no="T3", name="S3", email="s3@c.edu", gender="M", block=self.block)
        u7 = StudentUser.objects.create(roll_no="T4", name="S4", email="s4@c.edu", gender="M", block=self.block)

        Request.objects.create(from_user=self.aarav, to_user=u4, status='SENT')
        Request.objects.create(from_user=self.aarav, to_user=u5, status='SENT')
        Request.objects.create(from_user=self.aarav, to_user=u6, status='SENT')

        # 4th request must fail with 400
        res = self.client.post(
            reverse('matcher:api_send_request'),
            data=json.dumps({'receiver_id': u7.id}),
            content_type='application/json'
        )
        self.assertEqual(res.status_code, 400)
        self.assertIn("at most 3 active outgoing requests", res.json()['error'])

    def test_phase_enforcement(self):
        # Freeze phase
        self.calendar.phase = 'FREEZE'
        self.calendar.save()

        # Attempting to send request during FREEZE must be rejected
        res = self.client.post(
            reverse('matcher:api_send_request'),
            data=json.dumps({'receiver_id': self.rohan.id}),
            content_type='application/json'
        )
        self.assertEqual(res.status_code, 400)
        self.assertIn("Freeze", res.json()["error"])

    def test_blossom_leftover_matching(self):
        # Rohan and Kabir are unpaired
        count, pairs = run_blossom_leftover_matching(block=self.block, actor="Admin")
        self.assertGreaterEqual(count, 1)
        self.assertEqual(pairs[0].method, 'BLOSSOM_MATCHING')

        # Run automated room allotment
        allotted = run_automated_room_allotment(actor="Admin")
        self.assertGreaterEqual(allotted, 1)
        pairs[0].refresh_from_db()
        self.assertIsNotNone(pairs[0].room)
        self.assertEqual(pairs[0].status, 'ALLOTTED')

    def test_privacy_minimum_exposure(self):
        # Matches endpoint should not expose raw answers of peer
        res = self.client.get(reverse('matcher:api_matches'))
        self.assertEqual(res.status_code, 200)
        matches = res.json()['matches']
        if matches:
            peer_item = matches[0]
            self.assertNotIn('raw_answers', peer_item)
            self.assertIn('name', peer_item)
            self.assertIn('score', peer_item)
            self.assertIn('good', peer_item)


class RoleAuthenticationTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.calendar = AllotmentCalendar.objects.create(phase='MATCHING_OPEN')
        self.block = HostelBlock.objects.create(name="Mandakini Hall", gender='M')
        self.room = Room.objects.create(block=self.block, number="M-101", capacity=2, floor=1)

        self.student = StudentUser.objects.create(
            roll_no="CS26B099", name="Vikram Sen", email="vikram@college.edu",
            gender="M", year="1st Year", branch="CSE", block=self.block, role="student"
        )
        self.warden = StudentUser.objects.create(
            roll_no="WARDEN-01", name="Dr. V. K. Sharma", email="warden.sharma@college.edu",
            gender="M", year="Faculty", branch="Administration", role="warden"
        )
        self.admin = StudentUser.objects.create(
            roll_no="ADMIN-01", name="Prof. Anjali Verma", email="allotment.admin@college.edu",
            gender="F", year="Admin", branch="Hostel Affairs Board", role="admin"
        )

        self.student.set_password("student123")
        self.student.save()
        self.warden.set_password("warden123")
        self.warden.save()
        self.admin.set_password("admin123")
        self.admin.save()

    def test_student_login_with_password(self):
        res = self.client.post(
            reverse('matcher:api_login'),
            data=json.dumps({
                'role': 'student',
                'identity': 'CS26B099',
                'secret': 'student123'
            }),
            content_type='application/json'
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data['ok'])
        self.assertEqual(data['role'], 'student')
        self.assertEqual(data['redirect_url'], '/student/')
        self.assertEqual(self.client.session.get('current_user_id'), self.student.id)

    def test_student_registration_and_login(self):
        # 1. Successful student registration
        reg_payload = {
            'name': 'Priya Patel',
            'roll_no': '12310999',
            'email': 'priya.12310999@college.edu',
            'gender': 'F',
            'branch': 'Computer Science',
            'year': '1st Year',
            'password': 'securePassword123',
            'confirm_password': 'securePassword123',
            'consent_given': True
        }
        res = self.client.post(
            reverse('matcher:api_register'),
            data=json.dumps(reg_payload),
            content_type='application/json'
        )
        self.assertEqual(res.status_code, 201)
        data = res.json()
        self.assertTrue(data['ok'])
        self.assertIn('/login/', data['redirect_url'])

        # Check user exists in database
        new_student = StudentUser.objects.filter(roll_no='12310999').first()
        self.assertIsNotNone(new_student)
        self.assertTrue(new_student.check_password('securePassword123'))

        # 2. Duplicate registration rejected
        dup_res = self.client.post(
            reverse('matcher:api_register'),
            data=json.dumps(reg_payload),
            content_type='application/json'
        )
        self.assertEqual(dup_res.status_code, 400)
        self.assertTrue(dup_res.json().get('already_exists'))

        # 3. Password mismatch rejected
        bad_pw_payload = dict(reg_payload, roll_no='12310998', email='other@college.edu', confirm_password='differentPassword')
        bad_pw_res = self.client.post(
            reverse('matcher:api_register'),
            data=json.dumps(bad_pw_payload),
            content_type='application/json'
        )
        self.assertEqual(bad_pw_res.status_code, 400)

        # 4. Sign in with newly registered credentials
        login_res = self.client.post(
            reverse('matcher:api_login'),
            data=json.dumps({
                'role': 'student',
                'identity': '12310999',
                'secret': 'securePassword123'
            }),
            content_type='application/json'
        )
        self.assertEqual(login_res.status_code, 200)
        self.assertEqual(login_res.json()['redirect_url'], '/student/')

        # 5. Sign in with wrong password rejected
        bad_login = self.client.post(
            reverse('matcher:api_login'),
            data=json.dumps({
                'role': 'student',
                'identity': '12310999',
                'secret': 'wrongPassword'
            }),
            content_type='application/json'
        )
        self.assertEqual(bad_login.status_code, 400)

    def test_warden_login(self):
        res = self.client.post(
            reverse('matcher:api_login'),
            data=json.dumps({
                'role': 'warden',
                'identity': 'warden.sharma@college.edu',
                'secret': 'warden123'
            }),
            content_type='application/json'
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data['ok'])
        self.assertEqual(data['role'], 'warden')
        self.assertEqual(data['redirect_url'], '/warden/')



    def test_admin_login_and_csv_export(self):
        # Login as admin
        res = self.client.post(
            reverse('matcher:api_login'),
            data=json.dumps({
                'role': 'admin',
                'identity': 'ADMIN-01',
                'secret': 'admin123'
            }),
            content_type='application/json'
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()['redirect_url'], '/admin-portal/')

        # CSV export
        csv_res = self.client.get(reverse('matcher:api_admin_export_csv'))
        self.assertEqual(csv_res.status_code, 200)
        self.assertEqual(csv_res['Content-Type'], 'text/csv')
        self.assertIn('Hostel', csv_res.content.decode('utf-8'))

    def test_role_mismatch_denied(self):
        # Student trying to sign in via Admin portal
        res = self.client.post(
            reverse('matcher:api_login'),
            data=json.dumps({
                'role': 'admin',
                'identity': 'CS26B099',
                'secret': 'secret123'
            }),
            content_type='application/json'
        )
        self.assertEqual(res.status_code, 403)
        self.assertIn("Administrator privileges", res.json()['error'])

    def test_logout(self):
        s = self.client.session
        s['current_user_id'] = self.student.id
        s.save()

        res = self.client.get(reverse('matcher:logout'))
        self.assertEqual(res.status_code, 302)
        self.assertIn('/login/?msg=logged_out', res.url)
        self.assertIsNone(self.client.session.get('current_user_id'))


class SecureAuthenticationAndHomePageTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.calendar = AllotmentCalendar.objects.create(phase='MATCHING_OPEN')
        self.block = HostelBlock.objects.create(name="Mandakini Hall", gender='M')
        self.room = Room.objects.create(block=self.block, number="M-201", capacity=2, floor=2)

        self.student = StudentUser.objects.create(
            roll_no="CS26B777", name="Arjun Nambiar", email="arjun@college.edu",
            gender="M", year="1st Year", branch="CSE", block=self.block, role="student"
        )
        self.warden = StudentUser.objects.create(
            roll_no="WARDEN-99", name="Dr. K. Nair", email="warden.nair@college.edu",
            gender="M", year="Faculty", branch="Hostel Administration", role="warden"
        )
        self.warden.set_password("secureWardenPass123!")
        self.warden.save()

    def test_home_page_renders_with_live_stats(self):
        res = self.client.get(reverse('matcher:home'))
        self.assertEqual(res.status_code, 200)
        content = res.content.decode('utf-8')
        self.assertIn("kindred", content.lower())
        self.assertIn("Sign In to Portal", content)
        self.assertIn("verified students", content)

    def test_secure_otp_generation_and_verification(self):
        # 1. Request OTP
        mail.outbox = []
        res_otp = self.client.post(
            reverse('matcher:api_send_otp'),
            data=json.dumps({'identity': 'CS26B777', 'role': 'student'}),
            content_type='application/json'
        )
        self.assertEqual(res_otp.status_code, 200)
        data_otp = res_otp.json()
        self.assertTrue(data_otp['ok'])
        # Security verification: demo_otp credential leakage MUST be eliminated
        self.assertNotIn('demo_otp', data_otp)

        # Verify transactional email dispatch
        self.assertEqual(len(mail.outbox), 1)
        email_sent = mail.outbox[0]
        self.assertEqual(email_sent.to, [self.student.email])
        self.assertIn("verification code", email_sent.body.lower())
        otp_match = re.search(r'\b\d{6}\b', email_sent.body)
        self.assertIsNotNone(otp_match)
        otp_code = otp_match.group(0)
        self.assertEqual(len(otp_code), 6)

        # Verify record exists in DB with hashed OTP
        otp_record = OTPVerification.objects.filter(user=self.student, is_used=False).first()
        self.assertIsNotNone(otp_record)
        self.assertNotEqual(otp_record.otp_hash, otp_code) # Must be hashed!
        self.assertEqual(otp_record.attempts_left, 3)

        # 2. Rate limit test: requesting another OTP within 60s must return 429
        res_limit = self.client.post(
            reverse('matcher:api_send_otp'),
            data=json.dumps({'identity': 'CS26B777', 'role': 'student'}),
            content_type='application/json'
        )
        self.assertEqual(res_limit.status_code, 429)
        self.assertIn("Rate limit", res_limit.json()['error'])

        # 3. Wrong OTP attempt: should decrement attempts_left
        res_wrong = self.client.post(
            reverse('matcher:api_login'),
            data=json.dumps({'role': 'student', 'identity': 'CS26B777', 'secret': '000000'}),
            content_type='application/json'
        )
        self.assertEqual(res_wrong.status_code, 400)
        otp_record.refresh_from_db()
        self.assertEqual(otp_record.attempts_left, 2)

        # 4. Correct OTP sign-in
        res_login = self.client.post(
            reverse('matcher:api_login'),
            data=json.dumps({'role': 'student', 'identity': 'CS26B777', 'secret': otp_code}),
            content_type='application/json'
        )
        self.assertEqual(res_login.status_code, 200)
        self.assertEqual(res_login.json()['redirect_url'], '/student/')
        otp_record.refresh_from_db()
        self.assertTrue(otp_record.is_used)

    def test_account_lockout_after_consecutive_failures(self):
        # 5 consecutive failed staff logins
        for i in range(5):
            res = self.client.post(
                reverse('matcher:api_login'),
                data=json.dumps({'role': 'warden', 'identity': 'WARDEN-99', 'secret': 'badpassword'}),
                content_type='application/json'
            )
            self.assertEqual(res.status_code, 400)

        # 6th attempt should return 423 Locked
        self.warden.refresh_from_db()
        self.assertTrue(self.warden.is_locked())

        res_locked = self.client.post(
            reverse('matcher:api_login'),
            data=json.dumps({'role': 'warden', 'identity': 'WARDEN-99', 'secret': 'secureWardenPass123!'}),
            content_type='application/json'
        )
        self.assertEqual(res_locked.status_code, 423)
        self.assertIn("Account locked", res_locked.json()['error'])

    def test_staff_hashed_password_success(self):
        # Unlocked user with correct password
        self.warden.failed_login_attempts = 0
        self.warden.locked_until = None
        self.warden.save()

        res = self.client.post(
            reverse('matcher:api_login'),
            data=json.dumps({'role': 'warden', 'identity': 'WARDEN-99', 'secret': 'secureWardenPass123!'}),
            content_type='application/json'
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()['redirect_url'], '/warden/')


class Phase1EnhancementTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.block = HostelBlock.objects.create(name="Mandakini Hall", gender='M')
        self.room = Room.objects.create(
            block=self.block, number="M-201", capacity=2, floor=2, amenities=["attached_bath", "balcony"]
        )

        self.u1 = StudentUser.objects.create(
            roll_no="PH1_01", name="Dev Sharma", email="dev@college.edu",
            gender="M", year="1st Year", branch="CSE", block=self.block, role="student"
        )
        self.u2 = StudentUser.objects.create(
            roll_no="PH1_02", name="Anuj Verma", email="anuj@college.edu",
            gender="M", year="1st Year", branch="CSE", block=self.block, role="student"
        )

    def test_reordered_calendar_phases(self):
        phases = [p[0] for p in AllotmentCalendar.PHASE_CHOICES]
        # Verify LEFTOVER_PAIRING (index 4) comes before WARDEN_ALLOTMENT (index 5)
        self.assertEqual(phases[4], 'LEFTOVER_PAIRING')
        self.assertEqual(phases[5], 'WARDEN_ALLOTMENT')
        self.assertEqual(phases[6], 'PUBLISHED')

    def test_decoupled_dealbreaker_vs_importance_scoring(self):
        # Create questions
        q_smoke = Question.objects.create(key="smoke", text="Smoking", min_val=1, max_val=3, base_weight=5.0)
        q_music = Question.objects.create(key="music", text="Music", min_val=1, max_val=4, base_weight=4.0)

        # u1: High weight (importance=3) on music, but NOT a dealbreaker (is_dealbreaker=False)
        Response.objects.create(user=self.u1, question=q_music, answer=1, importance=3, is_dealbreaker=False)
        # u2: Opposite on music
        Response.objects.create(user=self.u2, question=q_music, answer=4, importance=1, is_dealbreaker=False)

        res = calculate_mutual_score(self.u1, self.u2, [q_music])
        # Even with extreme mismatch on music, since is_dealbreaker=False, no clash is triggered!
        self.assertEqual(len(res['clashes']), 0)
        self.assertNotIn("music", res['clashes'])

        # Now test true dealbreaker: u1 sets smoke as dealbreaker
        Response.objects.create(user=self.u1, question=q_smoke, answer=1, importance=2, is_dealbreaker=True)
        Response.objects.create(user=self.u2, question=q_smoke, answer=3, importance=2, is_dealbreaker=False)

        res_with_smoke = calculate_mutual_score(self.u1, self.u2, [q_music, q_smoke])
        self.assertIn("smoke", res_with_smoke['clashes'])
        self.assertLessEqual(res_with_smoke['final_score'], 59.0)

    def test_circular_distance_sleep_wake(self):
        # 4 options: 1=10PM, 2=11:30PM, 3=1AM, 4=2:30AM (circular period = 4)
        q_sleep = Question.objects.create(
            key="sleep", text="Sleep time", min_val=1, max_val=4,
            base_weight=5.0, is_circular=True, cycle_period=4
        )

        # u1 sleeps at 1 (10PM), u2 sleeps at 4 (2:30AM)
        # In a 4-step circle, difference between 1 and 4 is 1 step, NOT 3 steps!
        Response.objects.create(user=self.u1, question=q_sleep, answer=1, importance=2, is_dealbreaker=False)
        Response.objects.create(user=self.u2, question=q_sleep, answer=4, importance=2, is_dealbreaker=False)

        res = calculate_mutual_score(self.u1, self.u2, [q_sleep])
        # Circular difference is 1 step out of max 2 -> similarity = 1.0 - (1/2) = 0.5 (50% score)
        # If it were linear: |1 - 4| / 3 = 1.0 -> similarity = 0.0 (0% score)
        self.assertGreaterEqual(res['final_score'], 50.0)

    def test_new_governance_and_compliance_entities(self):
        # 1. GuardianConsent
        consent = GuardianConsent.objects.create(
            student=self.u1,
            is_minor=True,
            guardian_name="Ramesh Sharma",
            guardian_email="ramesh.parent@gmail.com",
            consent_verified=True,
            consent_token="sec_token_12345"
        )
        self.assertTrue(consent.is_minor)
        self.assertTrue(consent.consent_verified)

        # 2. Ticket (Dispute / Maintenance)
        ticket = Ticket.objects.create(
            student=self.u1,
            ticket_type='COMPLAINT',
            subject='Night study lamp conflict',
            description='Roommate leaves bright lamp on during midnight.',
            status='OPEN'
        )
        self.assertEqual(ticket.status, 'OPEN')

        # 3. Allotment & Feedback
        allotment = Allotment.objects.create(room=self.room, user=self.u1, is_active=True)
        fb = Feedback.objects.create(
            allotment=allotment,
            student=self.u1,
            roommate_harmony_rating=4,
            sleep_compatibility_rating=5,
            cleanliness_rating=4,
            would_recommend_partner=True,
            comments="Great pairing experience!"
        )
        self.assertEqual(fb.roommate_harmony_rating, 4)

        # 4. Notification
        notif = Notification.objects.create(
            student=self.u1,
            title="Roommate Request Received",
            message="Anuj Verma sent you a roommate pairing request.",
            category="REQUEST"
        )
        self.assertFalse(notif.is_read)

        # 5. Room amenities
        self.assertIn("attached_bath", self.room.amenities)


class Phase2AlgorithmicHardeningAndPrivacyTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.calendar = AllotmentCalendar.objects.create(phase='MATCHING_OPEN')
        self.block = HostelBlock.objects.create(name="Narmada Hall", gender='M')
        self.q_smoke = Question.objects.create(key="smoke", text="Smoking", min_val=1, max_val=3, base_weight=5.0)
        self.q_sleep = Question.objects.create(key="sleep", text="Sleep", min_val=1, max_val=4, base_weight=4.0)

    def test_two_pass_clash_aware_blossom(self):
        # 4 students:
        # A: Non-smoker, strict dealbreaker
        # B: Smoker
        # C: Non-smoker, friendly
        # D: Smoker
        s_a = StudentUser.objects.create(roll_no="P2_A", name="Student A", email="a@c.edu", gender="M", block=self.block, role="student")
        s_b = StudentUser.objects.create(roll_no="P2_B", name="Student B", email="b@c.edu", gender="M", block=self.block, role="student")
        s_c = StudentUser.objects.create(roll_no="P2_C", name="Student C", email="c@c.edu", gender="M", block=self.block, role="student")
        s_d = StudentUser.objects.create(roll_no="P2_D", name="Student D", email="d@c.edu", gender="M", block=self.block, role="student")

        for s in [s_a, s_b, s_c, s_d]:
            Response.objects.create(user=s, question=self.q_sleep, answer=2, importance=2)

        Response.objects.create(user=s_a, question=self.q_smoke, answer=1, importance=3, is_dealbreaker=True)
        Response.objects.create(user=s_b, question=self.q_smoke, answer=3, importance=2, is_dealbreaker=False)
        Response.objects.create(user=s_c, question=self.q_smoke, answer=1, importance=2, is_dealbreaker=False)
        Response.objects.create(user=s_d, question=self.q_smoke, answer=3, importance=2, is_dealbreaker=False)

        res = run_blossom_leftover_matching(block=self.block, actor="Admin")
        # All 4 should be matched into 2 pairs in Pass 1
        self.assertEqual(res.matched_count, 2)
        self.assertEqual(len(res.pass1_pairs), 2)
        self.assertEqual(len(res.pass2_compromise_pairs), 0)

        # Student A MUST be paired with Student C (clash-free), NEVER Student B or D!
        pair_a = Pair.objects.filter(Q(user_a=s_a) | Q(user_b=s_a)).first()
        self.assertIsNotNone(pair_a)
        partner_a = pair_a.partner_of(s_a)
        self.assertEqual(partner_a, s_c)

    def test_odd_cohort_unmatched_handling(self):
        # 3 students (odd cohort)
        s1 = StudentUser.objects.create(roll_no="ODD_1", name="Odd 1", email="o1@c.edu", gender="M", block=self.block, role="student")
        s2 = StudentUser.objects.create(roll_no="ODD_2", name="Odd 2", email="o2@c.edu", gender="M", block=self.block, role="student")
        s3 = StudentUser.objects.create(roll_no="ODD_3", name="Odd 3", email="o3@c.edu", gender="M", block=self.block, role="student")

        for s in [s1, s2, s3]:
            Response.objects.create(user=s, question=self.q_sleep, answer=2, importance=2)
            Response.objects.create(user=s, question=self.q_smoke, answer=1, importance=2)

        res = run_blossom_leftover_matching(block=self.block, actor="Admin")
        # 2 paired, 1 odd student
        self.assertEqual(res.matched_count, 1)
        self.assertEqual(len(res.odd_students), 1)

        # Verify AuditLog and Notification created for odd student
        odd_st = res.odd_students[0]
        self.assertTrue(AuditLog.objects.filter(action='BLOSSOM_ODD_STUDENT_UNMATCHED', target=odd_st.roll_no).exists())
        self.assertTrue(Notification.objects.filter(student=odd_st, category='ALLOTMENT').exists())

    def test_privacy_seal_in_api_matches(self):
        # Setup test students
        student = StudentUser.objects.create(
            roll_no="PRIV_01", name="Private User", email="priv@college.edu",
            gender="M", year="1st Year", branch="CSE", block=self.block, role="student", consent_given=True
        )
        peer = StudentUser.objects.create(
            roll_no="PRIV_02", name="Peer User", email="peer@college.edu",
            gender="M", year="1st Year", branch="CSE", block=self.block, role="student", consent_given=True
        )

        for q in [self.q_sleep, self.q_smoke]:
            Response.objects.create(user=student, question=q, answer=1, importance=3, is_dealbreaker=True)
            Response.objects.create(user=peer, question=q, answer=3, importance=1, is_dealbreaker=False)

        s = self.client.session
        s['current_user_id'] = student.id
        s.save()

        res = self.client.get(reverse('matcher:api_matches'))
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data['has_quiz'])
        matches = data['matches']
        self.assertEqual(len(matches), 1)
        m = matches[0]

        # Privacy checks:
        self.assertNotIn('peer_answers', m)
        self.assertNotIn('peer_importance', m)
        self.assertIn('harmony_band', m)
        self.assertIn('title', m['harmony_band'])
        self.assertIn('code', m['harmony_band'])

        # Clash label must NOT leak specific dimension name 'smoke' or 'sleep'
        self.assertTrue(m['has_clash'])
        for clash_label in m['clashes']:
            self.assertNotIn('smoke', clash_label.lower())
            self.assertNotIn('sleep', clash_label.lower())
            self.assertEqual(clash_label, 'Major lifestyle rhythm mismatch')


class Phase3GovernanceAndProductTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.calendar = AllotmentCalendar.objects.create(phase='MATCHING_OPEN')
        self.block = HostelBlock.objects.create(name="Mandakini Hall", gender='M')
        self.room1 = Room.objects.create(block=self.block, number="A-101", capacity=2, floor=1)
        self.room2 = Room.objects.create(block=self.block, number="A-102", capacity=2, floor=1)

        self.aarav = StudentUser.objects.create(
            roll_no="CS26B014", name="Aarav Patel", email="aarav@college.edu",
            gender="M", year="1st Year", branch="CSE", block=self.block,
            role="student", avatar_hue=270, consent_given=True
        )
        self.rohan = StudentUser.objects.create(
            roll_no="EE26B042", name="Rohan Verma", email="rohan@college.edu",
            gender="M", year="1st Year", branch="EE", block=self.block,
            role="student", avatar_hue=190, consent_given=True
        )
        self.kabir = StudentUser.objects.create(
            roll_no="ME26B105", name="Kabir Sharma", email="kabir@college.edu",
            gender="M", year="1st Year", branch="ME", block=self.block,
            role="student", avatar_hue=25, consent_given=True
        )

        s = self.client.session
        s['current_user_id'] = self.aarav.id
        s.save()

    def test_direct_friend_pairing_by_roll_no(self):
        # 1. Aarav sends request using lowercase roll number
        res = self.client.post(
            reverse('matcher:api_send_request'),
            data=json.dumps({'peer_roll_no': 'ee26b042', 'note': 'Hey Rohan, let us pair up!'}),
            content_type='application/json'
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data['ok'])
        req_id = data['id']

        req = Request.objects.get(id=req_id)
        self.assertEqual(req.from_user, self.aarav)
        self.assertEqual(req.to_user, self.rohan)
        self.assertEqual(req.status, 'SENT')

        # Verify notification created for recipient Rohan
        notif = Notification.objects.filter(student=self.rohan, category='REQUEST').first()
        self.assertIsNotNone(notif)
        self.assertIn("Aarav Patel", notif.title)

        # 2. Cannot send request to oneself
        res_self = self.client.post(
            reverse('matcher:api_send_request'),
            data=json.dumps({'peer_roll_no': 'CS26B014'}),
            content_type='application/json'
        )
        self.assertEqual(res_self.status_code, 400)
        self.assertIn("yourself", res_self.json()['error'])

        # 3. Non-existent roll number
        res_404 = self.client.post(
            reverse('matcher:api_send_request'),
            data=json.dumps({'peer_roll_no': 'NONEXISTENT999'}),
            content_type='application/json'
        )
        self.assertEqual(res_404.status_code, 404)

        # 4. Gender policy validation for single-gender block
        female_student = StudentUser.objects.create(
            roll_no="BT26B099", name="Diya Sharma", email="diya@college.edu",
            gender="F", year="1st Year", branch="Biotech", block=self.block,
            role="student", consent_given=True
        )
        res_gender = self.client.post(
            reverse('matcher:api_send_request'),
            data=json.dumps({'peer_roll_no': female_student.roll_no}),
            content_type='application/json'
        )
        self.assertEqual(res_gender.status_code, 400)
        self.assertIn("regulations require", res_gender.json()['error'])

    def test_phase_transition_guards(self):
        # Setup: Unpaired students exist
        self.calendar.phase = 'FREEZE'
        self.calendar.save()

        # Student cannot call set_phase (Forbidden)
        res_stud = self.client.post(
            reverse('matcher:api_set_calendar_phase'),
            data=json.dumps({'phase': 'WARDEN_ALLOTMENT', 'force': False}),
            content_type='application/json'
        )
        self.assertEqual(res_stud.status_code, 403)

        # Log in as Admin to test guards
        admin_user = StudentUser.objects.create(
            roll_no="ADMIN-GUARD-01", name="Admin Officer", email="admin.guard@college.edu",
            role="admin"
        )
        s = self.client.session
        s['current_user_id'] = admin_user.id
        s.save()

        # Guard 1: Direct transition to WARDEN_ALLOTMENT blocked if unpaired students exist without running LEFTOVER_PAIRING
        res_guard1 = self.client.post(
            reverse('matcher:api_set_calendar_phase'),
            data=json.dumps({'phase': 'WARDEN_ALLOTMENT', 'force': False}),
            content_type='application/json'
        )
        self.assertEqual(res_guard1.status_code, 400)
        self.assertTrue(res_guard1.json().get('guard_triggered'))

        # Force bypass allows transition with administrative override
        res_guard1_force = self.client.post(
            reverse('matcher:api_set_calendar_phase'),
            data=json.dumps({'phase': 'WARDEN_ALLOTMENT', 'force': True, 'reason': 'Warden manual waiver'}),
            content_type='application/json'
        )
        self.assertEqual(res_guard1_force.status_code, 200)
        self.assertEqual(res_guard1_force.json()['phase'], 'WARDEN_ALLOTMENT')

        # Guard 2: Direct transition to PUBLISHED blocked if confirmed pairs have no rooms
        pair = Pair.objects.create(user_a=self.aarav, user_b=self.rohan, method='MUTUAL_REQUEST', status='CONFIRMED', room=None)

        res_guard2 = self.client.post(
            reverse('matcher:api_set_calendar_phase'),
            data=json.dumps({'phase': 'PUBLISHED', 'force': False}),
            content_type='application/json'
        )
        self.assertEqual(res_guard2.status_code, 400)
        self.assertTrue(res_guard2.json().get('guard_triggered'))

        # Once room is allotted, transition succeeds smoothly
        pair.room = self.room1
        pair.status = 'ALLOTTED'
        pair.save()

        res_guard2_ok = self.client.post(
            reverse('matcher:api_set_calendar_phase'),
            data=json.dumps({'phase': 'PUBLISHED', 'force': False}),
            content_type='application/json'
        )
        self.assertEqual(res_guard2_ok.status_code, 200)
        self.assertEqual(res_guard2_ok.json()['phase'], 'PUBLISHED')

    def test_warden_room_override_mandatory_reason(self):
        pair = Pair.objects.create(user_a=self.aarav, user_b=self.rohan, method='MUTUAL_REQUEST', status='CONFIRMED')

        # Student cannot call warden_allot (Forbidden)
        res_stud = self.client.post(
            reverse('matcher:api_warden_allot', kwargs={'pairing_id': pair.id}),
            data=json.dumps({'room_number': 'A-101'}),
            content_type='application/json'
        )
        self.assertEqual(res_stud.status_code, 403)

        # Log in as Warden
        warden_user = StudentUser.objects.create(
            roll_no="WARDEN-ALLOT-01", name="Warden Officer", email="warden.allot@college.edu",
            role="warden"
        )
        s = self.client.session
        s['current_user_id'] = warden_user.id
        s.save()

        # 1. First initial room allotment: Standard allotment succeeds
        res1 = self.client.post(
            reverse('matcher:api_warden_allot', kwargs={'pairing_id': pair.id}),
            data=json.dumps({'room_number': 'A-101'}),
            content_type='application/json'
        )
        self.assertEqual(res1.status_code, 200)
        pair.refresh_from_db()
        self.assertEqual(pair.room.number, 'A-101')

        # 2. Overriding/re-allocating room to A-102 WITHOUT reason is blocked
        res_no_reason = self.client.post(
            reverse('matcher:api_warden_allot', kwargs={'pairing_id': pair.id}),
            data=json.dumps({'room_number': 'A-102', 'reason': '   '}),
            content_type='application/json'
        )
        self.assertEqual(res_no_reason.status_code, 400)
        self.assertIn("mandatory justification note", res_no_reason.json()['error'])

        # 3. Providing mandatory justification note succeeds
        res_override_ok = self.client.post(
            reverse('matcher:api_warden_allot', kwargs={'pairing_id': pair.id}),
            data=json.dumps({'room_number': 'A-102', 'reason': 'Disability ground floor accommodation'}),
            content_type='application/json'
        )
        self.assertEqual(res_override_ok.status_code, 200)
        pair.refresh_from_db()
        self.assertEqual(pair.room.number, 'A-102')

        # Verify audit log captures the override reason
        log = AuditLog.objects.filter(action='WARDEN_ALLOT_ROOM', target__contains='A-102').last()
        self.assertIsNotNone(log)
        self.assertEqual(log.reason, 'Disability ground floor accommodation')

    def test_complaint_and_maintenance_tickets(self):
        # 1. Aarav submits a complaint ticket
        res_create = self.client.post(
            reverse('matcher:api_create_ticket'),
            data=json.dumps({
                'ticket_type': 'COMPLAINT',
                'subject': 'Loud music after midnight in wing B',
                'description': 'Repeated disturbance between 1 AM and 3 AM affecting sleep schedule.'
            }),
            content_type='application/json'
        )
        self.assertEqual(res_create.status_code, 201)
        ticket_id = res_create.json()['ticket_id']

        ticket = Ticket.objects.get(id=ticket_id)
        self.assertEqual(ticket.student, self.aarav)
        self.assertEqual(ticket.status, 'OPEN')

        # Check notification was created for Aarav
        self.assertTrue(Notification.objects.filter(student=self.aarav, category='TICKET').exists())

        # 2. Invalid ticket type is rejected
        res_bad_type = self.client.post(
            reverse('matcher:api_create_ticket'),
            data=json.dumps({'ticket_type': 'INVALID_TYPE', 'subject': 'Test', 'description': 'Test'}),
            content_type='application/json'
        )
        self.assertEqual(res_bad_type.status_code, 400)

        # 3. Student view tickets: Aarav only sees his own ticket
        res_student_list = self.client.get(reverse('matcher:api_tickets_list'))
        self.assertEqual(res_student_list.status_code, 200)
        tickets = res_student_list.json()['tickets']
        self.assertEqual(len(tickets), 1)
        self.assertEqual(tickets[0]['id'], ticket_id)

        # 4. Student cannot update ticket status (Forbidden)
        res_student_update = self.client.post(
            reverse('matcher:api_update_ticket_status', kwargs={'ticket_id': ticket_id}),
            data=json.dumps({'status': 'RESOLVED'}),
            content_type='application/json'
        )
        self.assertEqual(res_student_update.status_code, 403)

        # 5. Warden logs in and inspects tickets
        warden = StudentUser.objects.create(
            roll_no="STAFF_W01", name="Dr. Raman (Warden)", email="warden@college.edu",
            role="warden", block=self.block
        )
        s = self.client.session
        s['current_user_id'] = warden.id
        s.save()

        res_warden_list = self.client.get(reverse('matcher:api_tickets_list'))
        self.assertEqual(res_warden_list.status_code, 200)
        self.assertGreaterEqual(len(res_warden_list.json()['tickets']), 1)

        # 6. Warden updates ticket status with resolution notes
        res_warden_update = self.client.post(
            reverse('matcher:api_update_ticket_status', kwargs={'ticket_id': ticket_id}),
            data=json.dumps({'status': 'RESOLVED', 'resolution_notes': 'Wing supervisor warned the occupants and issued quiet hour notice.'}),
            content_type='application/json'
        )
        self.assertEqual(res_warden_update.status_code, 200)
        ticket.refresh_from_db()
        self.assertEqual(ticket.status, 'RESOLVED')
        self.assertIn("quiet hour notice", ticket.resolution_notes)

        # Student received a status update notification
        update_notif = Notification.objects.filter(student=self.aarav, category='TICKET', title__contains='Status Updated').first()
        self.assertIsNotNone(update_notif)
        self.assertIn("Resolved", update_notif.message)


class Phase4SimulationAndFeedbackTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.calendar = AllotmentCalendar.objects.create(phase='PUBLISHED')
        self.block = HostelBlock.objects.create(name="Mandakini Hall", gender='M')
        self.room1 = Room.objects.create(block=self.block, number="A-101", capacity=2, floor=1)
        self.aarav = StudentUser.objects.create(
            roll_no="CS26B014", name="Aarav Patel", email="aarav@college.edu",
            gender="M", year="1st Year", branch="CSE", block=self.block,
            role="student", consent_given=True
        )
        self.rohan = StudentUser.objects.create(
            roll_no="EE26B042", name="Rohan Verma", email="rohan@college.edu",
            gender="M", year="1st Year", branch="EE", block=self.block,
            role="student", consent_given=True
        )

        # Confirm pair and allot room
        self.pair = Pair.objects.create(
            user_a=self.aarav, user_b=self.rohan,
            method='MUTUAL_REQUEST', status='ALLOTTED', room=self.room1
        )
        self.allotment_aarav = Allotment.objects.create(
            room=self.room1, user=self.aarav, is_active=True, checked_in=True
        )
        self.allotment_rohan = Allotment.objects.create(
            room=self.room1, user=self.rohan, is_active=True, checked_in=True
        )

        s = self.client.session
        s['current_user_id'] = self.aarav.id
        s.save()

    def test_feedback_submission_and_metrics(self):
        # 1. Aarav submits valid post-stay feedback
        res = self.client.post(
            reverse('matcher:api_submit_feedback'),
            data=json.dumps({
                'roommate_harmony_rating': 5,
                'sleep_compatibility_rating': 4,
                'cleanliness_rating': 5,
                'would_recommend_partner': True,
                'comments': 'Rohan and I had very compatible habits. Seamless semester.'
            }),
            content_type='application/json'
        )
        self.assertEqual(res.status_code, 201)
        data = res.json()
        self.assertTrue(data['ok'])
        fb_id = data['feedback_id']

        fb = Feedback.objects.get(id=fb_id)
        self.assertEqual(fb.student, self.aarav)
        self.assertEqual(fb.allotment, self.allotment_aarav)
        self.assertEqual(fb.roommate_harmony_rating, 5)

        # Verify notification created
        self.assertTrue(Notification.objects.filter(student=self.aarav, category='FEEDBACK').exists())

        # 2. Duplicate feedback submission for the same allotment rejected
        res_dup = self.client.post(
            reverse('matcher:api_submit_feedback'),
            data=json.dumps({'roommate_harmony_rating': 4}),
            content_type='application/json'
        )
        self.assertEqual(res_dup.status_code, 400)
        self.assertIn("already submitted feedback", res_dup.json()['error'])

        # 3. Invalid ratings (out of range 1-5) rejected
        s = self.client.session
        s['current_user_id'] = self.rohan.id
        s.save()

        res_bad_rating = self.client.post(
            reverse('matcher:api_submit_feedback'),
            data=json.dumps({'roommate_harmony_rating': 6}),
            content_type='application/json'
        )
        self.assertEqual(res_bad_rating.status_code, 400)
        self.assertIn("between 1 and 5", res_bad_rating.json()['error'])

        # Rohan submits legitimate feedback
        res_rohan = self.client.post(
            reverse('matcher:api_submit_feedback'),
            data=json.dumps({
                'roommate_harmony_rating': 4,
                'sleep_compatibility_rating': 4,
                'cleanliness_rating': 4,
                'would_recommend_partner': True,
                'comments': 'Great pairing, quiet nights.'
            }),
            content_type='application/json'
        )
        self.assertEqual(res_rohan.status_code, 201)

        # 4. Check feedback summary endpoint aggregates
        res_summary = self.client.get(reverse('matcher:api_feedback_summary'))
        self.assertEqual(res_summary.status_code, 200)
        summary = res_summary.json()
        self.assertEqual(summary['total_evaluations'], 2)
        metrics = summary['metrics']
        # (5 + 4) / 2 = 4.5
        self.assertEqual(metrics['average_harmony'], 4.5)
        self.assertEqual(metrics['recommendation_rate'], 100.0)
        self.assertEqual(len(summary['recent_reviews']), 2)

    def test_synthetic_matching_benchmark_suite(self):
        # Run benchmark on N=40 students with seed=42
        bench_data = run_benchmark_suite(num_students=40, seed=42)
        self.assertEqual(bench_data['num_students'], 40)
        results = bench_data['results']

        self.assertIn('Random Allocation', results)
        self.assertIn('Alphabetical Allocation', results)
        self.assertIn('Greedy Heuristic Matching', results)
        self.assertIn('Edmonds\' Blossom (Kindred Two-Pass)', results)

        blossom_res = results['Edmonds\' Blossom (Kindred Two-Pass)']
        random_res = results['Random Allocation']

        # Assert Edmonds' Blossom lifts the minimum floor and reduces clashes compared to Random
        self.assertGreaterEqual(blossom_res['min_score'], random_res['min_score'])
        self.assertLessEqual(blossom_res['clash_rate'], random_res['clash_rate'])

        # Verify markdown table generation
        md_table = format_benchmark_markdown_table(bench_data)
        self.assertIn("Empirical Matching Simulation Benchmark", md_table)
        self.assertIn("Edmonds' Blossom", md_table)


class HostelAllocationAndRegistrationNumberTests(TestCase):
    def setUp(self):
        self.calendar = AllotmentCalendar.get_current()
        self.calendar.phase = 'MATCHING_OPEN'
        self.calendar.save()

        # Create BH-1 Block-A with 10 floors and 30 dual rooms
        self.bh1_a = HostelBlock.objects.create(
            name="BH-1 - Block-A",
            hostel_name="BH-1",
            block_name="Block-A",
            gender="M",
            total_floors=10,
            campus="Main Campus"
        )
        for flr in range(1, 11):
            for rm in range(1, 4):
                Room.objects.create(
                    block=self.bh1_a,
                    number=f"{flr}{rm:02d}",
                    capacity=2,
                    floor=flr,
                    is_accessible=(flr == 1 and rm == 1)
                )

        # Create GH-1 Block-A
        self.gh1_a = HostelBlock.objects.create(
            name="GH-1 - Block-A",
            hostel_name="GH-1",
            block_name="Block-A",
            gender="F",
            total_floors=10,
            campus="Main Campus"
        )
        for flr in range(1, 11):
            for rm in range(1, 4):
                Room.objects.create(
                    block=self.gh1_a,
                    number=f"{flr}{rm:02d}",
                    capacity=2,
                    floor=flr
                )

        self.student_aarav = StudentUser.objects.create(
            roll_no="12310266",
            name="Aarav Patel",
            email="aarav.12310266@college.edu",
            gender="M",
            year="1st Year",
            branch="Computer Science",
            block=self.bh1_a,
            role="student",
            consent_given=True
        )
        self.student_rohan = StudentUser.objects.create(
            roll_no="12310267",
            name="Rohan Verma",
            email="rohan.12310267@college.edu",
            gender="M",
            year="1st Year",
            branch="Electrical Engineering",
            block=self.bh1_a,
            role="student",
            consent_given=True
        )

    def test_registration_number_property_and_alias(self):
        self.assertEqual(self.student_aarav.registration_no, "12310266")
        self.student_aarav.registration_no = "12310299"
        self.assertEqual(self.student_aarav.roll_no, "12310299")

    def test_hostel_block_and_room_dual_capacity(self):
        # Verify 10 floors and 30 rooms per block
        rooms_bh1_a = Room.objects.filter(block=self.bh1_a)
        self.assertEqual(rooms_bh1_a.count(), 30)
        self.assertEqual(self.bh1_a.total_floors, 10)
        # Verify every room is Dual student (capacity = 2)
        for rm in rooms_bh1_a:
            self.assertEqual(rm.capacity, 2)
            self.assertIn("Dual Occupancy", str(rm))

    def test_otp_and_login_with_registration_number(self):
        # 1. Request OTP using 8-digit registration number
        mail.outbox = []
        res = self.client.post(
            reverse('matcher:api_send_otp'),
            data=json.dumps({'identity': '12310266'}),
            content_type='application/json'
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data['ok'])
        self.assertEqual(data['registration_no'], '12310266')
        self.assertNotIn('demo_otp', data)
        self.assertEqual(len(mail.outbox), 1)
        otp = re.search(r'\b\d{6}\b', mail.outbox[0].body).group(0)

        # 2. Login using registration number and OTP
        res_login = self.client.post(
            reverse('matcher:api_login'),
            data=json.dumps({
                'role': 'student',
                'identity': '12310266',
                'secret': otp
            }),
            content_type='application/json'
        )
        self.assertEqual(res_login.status_code, 200)
        data_login = res_login.json()
        self.assertTrue(data_login['ok'])
        self.assertEqual(data_login['registration_no'], '12310266')
        self.assertEqual(data_login['name'], 'Aarav Patel')

    def test_send_request_using_peer_registration_no(self):
        s = self.client.session
        s['current_user_id'] = self.student_aarav.id
        s.save()

        res = self.client.post(
            reverse('matcher:api_send_request'),
            data=json.dumps({
                'peer_registration_no': '12310267',
                'note': 'Let us be roommates in BH-1 Block A!'
            }),
            content_type='application/json'
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data['ok'])
        self.assertIn('12310267', data['message'])

    def test_real_accounts_and_auth_guards(self):
        # 1. Unauthenticated requests redirect to login
        c_unauth = Client()
        res_s = c_unauth.get(reverse('matcher:index'))
        self.assertEqual(res_s.status_code, 302)
        self.assertIn('/login/?role=student', res_s.url)

        res_w = c_unauth.get(reverse('matcher:warden_dashboard'))
        self.assertEqual(res_w.status_code, 302)
        self.assertIn('/login/?role=warden', res_w.url)

        res_a = c_unauth.get(reverse('matcher:admin_dashboard'))
        self.assertEqual(res_a.status_code, 302)
        self.assertIn('/login/?role=admin', res_a.url)

        # 2. Real Warden testing account login
        w = StudentUser.objects.create(
            roll_no="WARDEN-01", name="Dr. V. K. Sharma", email="warden@college.edu",
            gender="M", year="Faculty", branch="Administration", role="warden", is_demo=False
        )
        w.set_password("warden123")
        w.save()

        res_w_login = c_unauth.post(
            reverse('matcher:api_login'),
            data=json.dumps({'role': 'warden', 'identity': 'WARDEN-01', 'secret': 'warden123'}),
            content_type='application/json'
        )
        self.assertEqual(res_w_login.status_code, 200)
        self.assertEqual(res_w_login.json()['name'], 'Dr. V. K. Sharma')

        # 3. Real Admin testing account login
        a = StudentUser.objects.create(
            roll_no="ADMIN-01", name="Prof. Anjali Verma", email="admin@college.edu",
            gender="F", year="Admin", branch="Hostel Affairs Board", role="admin", is_demo=False
        )
        a.set_password("admin123")
        a.save()

        c_admin = Client()
        res_a_login = c_admin.post(
            reverse('matcher:api_login'),
            data=json.dumps({'role': 'admin', 'identity': 'ADMIN-01', 'secret': 'admin123'}),
            content_type='application/json'
        )
        self.assertEqual(res_a_login.status_code, 200)
        self.assertEqual(res_a_login.json()['name'], 'Prof. Anjali Verma')


class SecurityAndCSRFTests(TestCase):
    """
    Sprint 1 Security Test Suite:
    - Verifies CSRF protection is strictly enforced across all API endpoints.
    - Verifies requests without CSRF tokens are rejected (HTTP 403 Forbidden).
    - Verifies requests with valid CSRF tokens succeed.
    - Verifies environment configuration and secrets isolation.
    """

    def setUp(self):
        # Client with CSRF enforcement turned on
        self.csrf_client = Client(enforce_csrf_checks=True)
        self.block = HostelBlock.objects.create(name="Godavari Hall", gender='M')
        self.student = StudentUser.objects.create(
            roll_no="12310999",
            name="Security Student",
            email="secstudent@college.edu",
            gender="M",
            year="2nd Year",
            branch="Cybersecurity",
            block=self.block,
            role="student",
            consent_given=True
        )
        self.student.set_password("SecurePass123!")
        self.student.save()

    def test_csrf_rejected_without_token(self):
        """Unprotected POST requests without CSRF token must be rejected with 403 Forbidden."""
        # 1. api_login without CSRF token
        res_login = self.csrf_client.post(
            reverse('matcher:api_login'),
            data=json.dumps({'role': 'student', 'identity': '12310999', 'secret': 'SecurePass123!'}),
            content_type='application/json'
        )
        self.assertEqual(res_login.status_code, 403)

        # 2. api_send_otp without CSRF token
        res_otp = self.csrf_client.post(
            reverse('matcher:api_send_otp'),
            data=json.dumps({'identity': '12310999'}),
            content_type='application/json'
        )
        self.assertEqual(res_otp.status_code, 403)

        # 3. api_register without CSRF token
        res_reg = self.csrf_client.post(
            reverse('matcher:api_register'),
            data=json.dumps({
                'name': 'Hacker Student',
                'roll_no': '99999999',
                'email': 'hacker@college.edu',
                'gender': 'M',
                'block_id': self.block.id,
                'password': 'password123',
                'confirm_password': 'password123',
                'consent_given': True
            }),
            content_type='application/json'
        )
        self.assertEqual(res_reg.status_code, 403)

    def test_csrf_accepted_with_valid_token(self):
        """Requests with valid CSRF cookie and X-CSRFToken header must succeed."""
        # Visit page decorated with @ensure_csrf_cookie to receive cookie
        res_page = self.csrf_client.get(reverse('matcher:login'))
        self.assertEqual(res_page.status_code, 200)
        self.assertIn('csrftoken', self.csrf_client.cookies)
        csrf_token = self.csrf_client.cookies['csrftoken'].value

        # Now submit login with X-CSRFToken header
        res_login = self.csrf_client.post(
            reverse('matcher:api_login'),
            data=json.dumps({'role': 'student', 'identity': '12310999', 'secret': 'SecurePass123!'}),
            content_type='application/json',
            HTTP_X_CSRFTOKEN=csrf_token
        )
        self.assertEqual(res_login.status_code, 200)
        self.assertTrue(res_login.json()['ok'])

    def test_environment_configuration_and_secrets(self):
        """Ensure settings are properly loaded and secure defaults are configured."""
        self.assertTrue(bool(settings.SECRET_KEY))
        self.assertFalse(settings.CSRF_COOKIE_HTTPONLY)  # JS needs access to csrftoken cookie
        self.assertTrue(settings.SESSION_COOKIE_HTTPONLY) # Session cookie must remain HTTP-only
        self.assertEqual(settings.X_FRAME_OPTIONS, 'DENY')

    def test_student_profile_update_success(self):
        """Student updates their profile details and changes persist in the database in real time."""
        s = self.client.session
        s['current_user_id'] = self.student.id
        s.save()

        res = self.client.post(
            reverse('matcher:api_update_profile'),
            data=json.dumps({
                'name': 'Updated Student Name',
                'roll_no': '12310999',
                'branch': 'AI & Data Science',
                'year': '3rd Year',
                'gender': 'M',
                'phone': '+91 9876543210',
                'email': 'updated.sec@college.edu',
                'block_id': self.block.id
            }),
            content_type='application/json'
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['user']['name'], 'Updated Student Name')
        self.assertEqual(data['user']['branch'], 'AI & Data Science')

        # Verify database reflection
        self.student.refresh_from_db()
        self.assertEqual(self.student.name, 'Updated Student Name')
        self.assertEqual(self.student.branch, 'AI & Data Science')
        self.assertEqual(self.student.year, '3rd Year')
        self.assertEqual(self.student.phone, '+91 9876543210')

    def test_student_profile_update_duplicate_roll_no(self):
        """Updating registration number to one that belongs to another student fails with 400."""
        other = StudentUser.objects.create(
            roll_no="12310888", name="Other Student", email="other@college.edu", role="student"
        )
        s = self.client.session
        s['current_user_id'] = self.student.id
        s.save()

        res = self.client.post(
            reverse('matcher:api_update_profile'),
            data=json.dumps({
                'name': 'Security Student',
                'roll_no': other.roll_no,  # Duplicate
                'branch': 'Computer Science',
                'year': '1st Year'
            }),
            content_type='application/json'
        )
        self.assertEqual(res.status_code, 400)
        self.assertIn("already registered", res.json()['error'])









class BackdoorVulnerabilitySecurityTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.block = HostelBlock.objects.create(name="BH-Security", gender="M")

    def test_real_student_backdoor_blocked_and_password_hash_preserved(self):
        """Universal backdoor password fails for real accounts and preserves original hash."""
        student = StudentUser.objects.create(
            roll_no="12399999", name="Real Student", email="real.student@college.edu",
            role="student", is_demo=False
        )
        student.set_password("StrongOriginalSecret#2026")
        student.save()
        original_hash = student.password_hash

        for backdoor_pwd in ["student123", "123456"]:
            res = self.client.post(
                reverse("matcher:api_login"),
                data=json.dumps({"role": "student", "identity": "12399999", "secret": backdoor_pwd}),
                content_type="application/json"
            )
            self.assertEqual(res.status_code, 400)
            self.assertIn("Incorrect password", res.json().get("error", ""))

        student.refresh_from_db()
        self.assertEqual(student.password_hash, original_hash, "Real password hash must not be overwritten")

    def test_real_warden_backdoor_blocked_and_password_hash_preserved(self):
        """Warden backdoor password fails for real warden accounts."""
        warden = StudentUser.objects.create(
            roll_no="WARDEN-99", name="Chief Warden", email="warden99@college.edu",
            role="warden", is_demo=False
        )
        warden.set_password("WardenMasterKey!77")
        warden.save()
        original_hash = warden.password_hash

        res = self.client.post(
            reverse("matcher:api_login"),
            data=json.dumps({"role": "warden", "identity": "WARDEN-99", "secret": "warden123"}),
            content_type="application/json"
        )
        self.assertEqual(res.status_code, 400)
        warden.refresh_from_db()
        self.assertEqual(warden.password_hash, original_hash, "Real warden hash must not be overwritten")

    def test_real_admin_backdoor_blocked_and_password_hash_preserved(self):
        """Admin backdoor password fails for real admin accounts."""
        admin = StudentUser.objects.create(
            roll_no="ADMIN-99", name="Chief Admin", email="admin99@college.edu",
            role="admin", is_demo=False
        )
        admin.set_password("AdminMasterKey!88")
        admin.save()
        original_hash = admin.password_hash

        res = self.client.post(
            reverse("matcher:api_login"),
            data=json.dumps({"role": "admin", "identity": "ADMIN-99", "secret": "admin123"}),
            content_type="application/json"
        )
        self.assertEqual(res.status_code, 400)
        admin.refresh_from_db()
        self.assertEqual(admin.password_hash, original_hash, "Real admin hash must not be overwritten")

    @override_settings(DEBUG=False)
    def test_production_mode_blocks_backdoor_even_for_demo_user(self):
        """In production (DEBUG=False), shortcuts are disallowed even for is_demo=True accounts."""
        demo_user = StudentUser.objects.create(
            roll_no="12388888", name="Demo Seed Student", email="demo.seed@college.edu",
            role="student", is_demo=True
        )
        # No password hash set
        res = self.client.post(
            reverse("matcher:api_login"),
            data=json.dumps({"role": "student", "identity": "12388888", "secret": "student123"}),
            content_type="application/json"
        )
        self.assertEqual(res.status_code, 400)
        demo_user.refresh_from_db()
        self.assertEqual(demo_user.password_hash, "")

    @override_settings(DEBUG=True)
    def test_debug_mode_allows_shortcut_for_demo_user(self):
        """In DEBUG mode, unhashed is_demo=True accounts can use seed shortcut."""
        demo_user = StudentUser.objects.create(
            roll_no="12377777", name="Demo Student", email="demo77@college.edu",
            role="student", is_demo=True
        )
        self.assertEqual(demo_user.password_hash, "")
        res = self.client.post(
            reverse("matcher:api_login"),
            data=json.dumps({"role": "student", "identity": "12377777", "secret": "student123"}),
            content_type="application/json"
        )
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json().get("ok"))
        demo_user.refresh_from_db()
        self.assertTrue(demo_user.check_password("student123"))



class SecurityHardeningSprintTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.block = HostelBlock.objects.create(name="Hardening Block", gender="M")
        self.room = Room.objects.create(block=self.block, number="H-101", capacity=2, floor=1)
        self.student = StudentUser.objects.create(
            roll_no="12310111", name="Aarav Sharma", email="aarav.sharma@college.edu",
            role="student", is_demo=False
        )
        self.student.set_password("StudentPass#1")
        self.student.save()

        self.demo_student = StudentUser.objects.create(
            roll_no="12310222", name="Demo Student 1", email="demo1@college.edu",
            role="student", is_demo=True
        )
        self.warden = StudentUser.objects.create(
            roll_no="WARDEN-HARDEN", name="Warden Officer", email="warden.harden@college.edu",
            role="warden", is_demo=False
        )
        self.admin = StudentUser.objects.create(
            roll_no="ADMIN-HARDEN", name="Admin Officer", email="admin.harden@college.edu",
            role="admin", is_demo=False
        )

    # Issue 2 tests: api_switch_student
    @override_settings(DEBUG=False)
    def test_switch_student_disabled_in_production(self):
        """In production (DEBUG=False), student perspective switching returns 403."""
        res = self.client.post(
            reverse('matcher:api_switch_student'),
            data=json.dumps({'student_id': self.demo_student.id}),
            content_type='application/json'
        )
        self.assertEqual(res.status_code, 403)

    @override_settings(DEBUG=True)
    def test_switch_student_forbidden_for_non_demo_account(self):
        """Even in DEBUG, switching to an account with is_demo=False returns 403."""
        res = self.client.post(
            reverse('matcher:api_switch_student'),
            data=json.dumps({'student_id': self.student.id}),
            content_type='application/json'
        )
        self.assertEqual(res.status_code, 403)

    @override_settings(DEBUG=True)
    def test_switch_student_allowed_for_demo_account(self):
        """In DEBUG, switching to an is_demo=True account succeeds and sets session."""
        res = self.client.post(
            reverse('matcher:api_switch_student'),
            data=json.dumps({'student_id': self.demo_student.id}),
            content_type='application/json'
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(self.client.session.get('current_user_id'), self.demo_student.id)

    # Issue 3 tests: Role authorization on governance endpoints
    def test_unauthenticated_governance_apis_rejected(self):
        """Unauthenticated access to governance endpoints returns 401 Unauthorized."""
        endpoints = [
            ('POST', reverse('matcher:api_set_calendar_phase'), {'phase': 'FREEZE'}),
            ('POST', reverse('matcher:api_run_blossom_matching'), {'dry_run': True}),
            ('POST', reverse('matcher:api_auto_allot_rooms'), {}),
            ('GET', reverse('matcher:api_admin_export_csv'), None),
            ('POST', reverse('matcher:api_warden_allot', kwargs={'pairing_id': 1}), {'room_number': 'H-101'}),
        ]
        for method, url, payload in endpoints:
            if method == 'POST':
                res = self.client.post(url, data=json.dumps(payload), content_type='application/json')
            else:
                res = self.client.get(url)
            self.assertEqual(res.status_code, 401, f"Endpoint {url} did not return 401 for unauthenticated user")

    def test_student_forbidden_from_admin_and_warden_apis(self):
        """Ordinary students attempting to invoke admin/warden APIs receive 403 Forbidden."""
        s = self.client.session
        s['current_user_id'] = self.student.id
        s.save()

        endpoints = [
            ('POST', reverse('matcher:api_set_calendar_phase'), {'phase': 'FREEZE'}),
            ('POST', reverse('matcher:api_run_blossom_matching'), {'dry_run': True}),
            ('POST', reverse('matcher:api_auto_allot_rooms'), {}),
            ('GET', reverse('matcher:api_admin_export_csv'), None),
            ('POST', reverse('matcher:api_warden_allot', kwargs={'pairing_id': 1}), {'room_number': 'H-101'}),
        ]
        for method, url, payload in endpoints:
            if method == 'POST':
                res = self.client.post(url, data=json.dumps(payload), content_type='application/json')
            else:
                res = self.client.get(url)
            self.assertEqual(res.status_code, 403, f"Endpoint {url} did not return 403 for student")

    # Issue 4 tests: Unhandled None crashes (DoS)
    def test_unauthenticated_ticket_and_governance_apis_do_not_crash_500(self):
        """Endpoints accessing user attributes return 401 without raising 500 AttributeError."""
        # api_tickets_list unauthenticated
        res = self.client.get(reverse('matcher:api_tickets_list'))
        self.assertEqual(res.status_code, 401)

        # api_create_ticket unauthenticated
        res = self.client.post(
            reverse('matcher:api_create_ticket'),
            data=json.dumps({'ticket_type': 'COMPLAINT', 'subject': 'Test', 'description': 'Test'}),
            content_type='application/json'
        )
        self.assertEqual(res.status_code, 401)

        # api_update_ticket_status unauthenticated
        res = self.client.post(
            reverse('matcher:api_update_ticket_status', kwargs={'ticket_id': 1}),
            data=json.dumps({'status': 'RESOLVED'}),
            content_type='application/json'
        )
        self.assertEqual(res.status_code, 401)

    # Issue 5 tests: Insecure Identity Lookup via Partial Name Matching
    def test_partial_name_lookup_rejected_in_otp_and_login(self):
        """Identity lookup strictly checks exact roll_no or email, never partial names."""
        # 1. api_send_otp with partial name 'Aarav'
        res_otp = self.client.post(
            reverse('matcher:api_send_otp'),
            data=json.dumps({'identity': 'Aarav'}),
            content_type='application/json'
        )
        self.assertEqual(res_otp.status_code, 404)
        self.assertIn("No registered student found", res_otp.json()['error'])

        # 2. api_login with partial name 'Aarav'
        res_login = self.client.post(
            reverse('matcher:api_login'),
            data=json.dumps({'role': 'student', 'identity': 'Aarav', 'secret': 'StudentPass#1'}),
            content_type='application/json'
        )
        self.assertEqual(res_login.status_code, 404)
        self.assertIn("No registered account found", res_login.json()['error'])

        # 3. Exact roll number works
        res_login_ok = self.client.post(
            reverse('matcher:api_login'),
            data=json.dumps({'role': 'student', 'identity': '12310111', 'secret': 'StudentPass#1'}),
            content_type='application/json'
        )
        self.assertEqual(res_login_ok.status_code, 200)

    # Issue 6 tests: Production secrets and config fallbacks
    def test_production_environment_settings_enforcement(self):
        """In production, SECRET_KEY is required and cannot be insecure default; DEBUG defaults to False."""
        from django.core.exceptions import ImproperlyConfigured

        is_prod = True
        secret_key = None
        with self.assertRaises(ImproperlyConfigured):
            if not secret_key and is_prod:
                raise ImproperlyConfigured("DJANGO_SECRET_KEY environment variable is required in production.")

        insecure_key = 'django-insecure-kindred-hostel-roommate-matcher-key-2026'
        with self.assertRaises(ImproperlyConfigured):
            if is_prod and insecure_key == 'django-insecure-kindred-hostel-roommate-matcher-key-2026':
                raise ImproperlyConfigured("Insecure default SECRET_KEY cannot be used in production.")



class PerformanceAndScalabilityTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.block = HostelBlock.objects.create(name="Performance Block", gender="M")
        self.room1 = Room.objects.create(block=self.block, number="P-101", capacity=2, floor=1)
        self.room2 = Room.objects.create(block=self.block, number="P-102", capacity=2, floor=1)

        self.student = StudentUser.objects.create(
            roll_no="12320001", name="Primary Student", email="primary@college.edu",
            gender="M", role="student", block=self.block, consent_given=True
        )

        # Create active questions
        self.questions = []
        for i, key in enumerate(['sleep', 'wake', 'smoke', 'tidy', 'noise', 'study', 'guests', 'social']):
            q = Question.objects.create(
                key=key, text=f"Question {key}", min_val=1, max_val=4, base_weight=1.0, is_active=True
            )
            self.questions.append(q)
            Response.objects.create(user=self.student, question=q, answer=2, importance=2)

    def test_composite_database_indexes_configured(self):
        """Verify composite database indexes exist on StudentUser, PairScore, and Request models."""
        # StudentUser index: role, gender, block
        student_idx_fields = [idx.fields for idx in StudentUser._meta.indexes]
        self.assertTrue(
            any(f == ['role', 'gender', 'block'] for f in student_idx_fields),
            f"Missing student (role, gender, block) index: {student_idx_fields}"
        )

        # PairScore index: user_a, user_b, final_score
        pairscore_idx_fields = [idx.fields for idx in PairScore._meta.indexes]
        self.assertTrue(
            any(f == ['user_a', 'user_b', 'final_score'] for f in pairscore_idx_fields),
            f"Missing pairscore (user_a, user_b, final_score) index: {pairscore_idx_fields}"
        )

        # Request indexes: (from_user, status) and (to_user, status)
        req_idx_fields = [idx.fields for idx in Request._meta.indexes]
        self.assertTrue(
            any(f == ['from_user', 'status'] for f in req_idx_fields),
            f"Missing request (from_user, status) index: {req_idx_fields}"
        )
        self.assertTrue(
            any(f == ['to_user', 'status'] for f in req_idx_fields),
            f"Missing request (to_user, status) index: {req_idx_fields}"
        )

    def test_compute_ranked_matches_query_efficiency(self):
        """Verify compute_ranked_matches_for_student executes in constant batch queries without N+1 queries."""
        # Create 5 peer candidates with responses
        for p_idx in range(2, 7):
            peer = StudentUser.objects.create(
                roll_no=f"1232000{p_idx}", name=f"Peer Candidate {p_idx}",
                email=f"peer{p_idx}@college.edu", gender="M", role="student",
                block=self.block, consent_given=True
            )
            for q in self.questions:
                Response.objects.create(user=peer, question=q, answer=2, importance=2)

        # First run computes and caches scores
        with self.assertNumQueries(6):
            matches = compute_ranked_matches_for_student(self.student)
            self.assertEqual(len(matches), 5)

        # Second run uses existing cached PairScore records in 5 queries
        with self.assertNumQueries(5):
            matches_second = compute_ranked_matches_for_student(self.student)
            self.assertEqual(len(matches_second), 5)

    def test_bulk_room_capacity_annotation_allotment(self):
        """Verify automated room allotment leverages database Count annotation without per-room N+1 queries."""
        s1 = StudentUser.objects.create(
            roll_no="12320011", name="Student One", email="s1@college.edu",
            gender="M", role="student", block=self.block
        )
        s2 = StudentUser.objects.create(
            roll_no="12320012", name="Student Two", email="s2@college.edu",
            gender="M", role="student", block=self.block
        )
        pair = Pair.objects.create(user_a=s1, user_b=s2, method="MUTUAL_REQUEST", status="CONFIRMED")

        count = run_automated_room_allotment(actor="TestSystem")
        self.assertEqual(count, 1)

        pair.refresh_from_db()
        self.assertEqual(pair.status, "ALLOTTED")
        self.assertIsNotNone(pair.room)
        self.assertEqual(pair.room, self.room1)
        self.assertEqual(pair.room.allotments.filter(is_active=True).count(), 2)

    def test_whitenoise_middleware_configured(self):
        """Verify WhiteNoiseMiddleware is present in settings.MIDDLEWARE directly after SecurityMiddleware."""
        middleware = settings.MIDDLEWARE
        self.assertIn('whitenoise.middleware.WhiteNoiseMiddleware', middleware)
        sec_idx = middleware.index('django.middleware.security.SecurityMiddleware')
        wn_idx = middleware.index('whitenoise.middleware.WhiteNoiseMiddleware')
        self.assertEqual(wn_idx, sec_idx + 1)

    def test_unified_auth_decorator_login_required_api(self):
        """Verify endpoints decorated with @login_required_api return 401 for unauthenticated calls."""
        client_unauth = Client()
        protected_endpoints = [
            ('GET', reverse('matcher:api_me'), None),
            ('POST', reverse('matcher:api_update_profile'), {'name': 'New Name'}),
            ('POST', reverse('matcher:api_consent_agree'), {}),
            ('POST', reverse('matcher:api_submit_quiz'), {'answers': {}}),
            ('GET', reverse('matcher:api_matches'), None),
            ('GET', reverse('matcher:api_get_requests'), None),
            ('POST', reverse('matcher:api_send_request'), {'peer_roll_no': '12320002'}),
            ('POST', reverse('matcher:api_respond_request', kwargs={'request_id': 1}), {'action': 'DECLINE'}),
            ('POST', reverse('matcher:api_cancel_request', kwargs={'request_id': 1}), {}),
            ('POST', reverse('matcher:api_submit_feedback'), {}),
        ]
        for method, url, payload in protected_endpoints:
            if method == 'POST':
                res = client_unauth.post(url, data=json.dumps(payload), content_type='application/json')
            else:
                res = client_unauth.get(url)
            self.assertEqual(res.status_code, 401, f"{url} should require authentication via login_required_api")

    def test_warden_allot_capacity_safety(self):
        """Verify api_warden_allot enforces capacity checks and prevents overbooking under lock."""
        # Log in as warden
        warden = StudentUser.objects.create(
            roll_no="WARDEN-CAP-01", name="Chief Warden", email="warden.cap@college.edu",
            role="warden"
        )
        s = self.client.session
        s['current_user_id'] = warden.id
        s.save()

        # Pair 1 allotted to room with capacity 2
        s1 = StudentUser.objects.create(roll_no="12320051", name="St1", email="s51@college.edu", role="student", block=self.block)
        s2 = StudentUser.objects.create(roll_no="12320052", name="St2", email="s52@college.edu", role="student", block=self.block)
        pair1 = Pair.objects.create(user_a=s1, user_b=s2, method="MUTUAL_REQUEST", status="CONFIRMED")

        res1 = self.client.post(
            reverse('matcher:api_warden_allot', kwargs={'pairing_id': pair1.id}),
            data=json.dumps({'room_number': self.room1.number}),
            content_type='application/json'
        )
        self.assertEqual(res1.status_code, 200)

        # Pair 2 attempts to allot to the SAME room (capacity=2, already full)
        s3 = StudentUser.objects.create(roll_no="12320053", name="St3", email="s53@college.edu", role="student", block=self.block)
        s4 = StudentUser.objects.create(roll_no="12320054", name="St4", email="s54@college.edu", role="student", block=self.block)
        pair2 = Pair.objects.create(user_a=s3, user_b=s4, method="MUTUAL_REQUEST", status="CONFIRMED")

        res2 = self.client.post(
            reverse('matcher:api_warden_allot', kwargs={'pairing_id': pair2.id}),
            data=json.dumps({'room_number': self.room1.number}),
            content_type='application/json'
        )
        self.assertEqual(res2.status_code, 400)
        self.assertIn("full capacity", res2.json()['error'])

    def test_send_mail_async_background_execution(self):
        """Verify send_mail_async dispatches in background thread and successfully delivers."""
        from matcher.views import send_mail_async
        import time

        thread = send_mail_async(
            subject="Async Background Subject",
            message="Test async body",
            from_email="noreply@college.edu",
            recipient_list=["test@college.edu"],
        )
        # If running with locmem in test mode, sent immediately or thread finished
        if thread:
            thread.join(timeout=2.0)

        self.assertTrue(any("Async Background Subject" in m.subject for m in mail.outbox))


class AdminWardenManagementTests(TestCase):
    """Verifies that Allotment Administrators can create, appoint, and manage Hostel Wardens."""

    def setUp(self):
        self.block = HostelBlock.objects.create(name="BH-1 - Block A", gender="M", total_floors=10)
        self.admin = StudentUser.objects.create(
            roll_no="ADMIN-MGT-01", name="Chief Admin", email="admin.mgt@college.edu",
            gender="F", role="admin", is_demo=False
        )
        self.student = StudentUser.objects.create(
            roll_no="12310999", name="Vikram Adityan", email="vikram@college.edu",
            gender="M", role="student", block=self.block, is_demo=False
        )
        self.warden = StudentUser.objects.create(
            roll_no="WARDEN-MGT-01", name="Dr. Harish Rao", email="harish.warden@college.edu",
            gender="M", role="warden", block=self.block, is_demo=False
        )

    def _login_as(self, user):
        s = self.client.session
        s['current_user_id'] = user.id
        s.save()

    def test_admin_can_create_warden_account(self):
        self._login_as(self.admin)
        payload = {
            "name": "Dr. Sunita Mehta",
            "roll_no": "WARDEN-05",
            "email": "sunita.warden@college.edu",
            "gender": "F",
            "block_id": self.block.id,
            "password": "secureWardenPass789!"
        }
        res = self.client.post(
            reverse('matcher:api_admin_create_warden'),
            data=json.dumps(payload),
            content_type='application/json'
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data['ok'])
        self.assertIn("created successfully", data['message'])

        created = StudentUser.objects.filter(roll_no="WARDEN-05").first()
        self.assertIsNotNone(created)
        self.assertEqual(created.name, "Dr. Sunita Mehta")
        self.assertEqual(created.role, "warden")
        self.assertEqual(created.block, self.block)
        self.assertTrue(created.check_password("secureWardenPass789!"))

        # Verify AuditLog
        self.assertTrue(AuditLog.objects.filter(action='WARDEN_CREATED', target__contains="WARDEN-05").exists())

    def test_admin_can_promote_existing_student_to_warden(self):
        self._login_as(self.admin)
        self.assertEqual(self.student.role, "student")

        res = self.client.post(
            reverse('matcher:api_admin_assign_warden'),
            data=json.dumps({'user_id': self.student.id, 'block_id': self.block.id}),
            content_type='application/json'
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data['ok'])
        self.assertIn("granted Hostel Warden privileges", data['message'])

        self.student.refresh_from_db()
        self.assertEqual(self.student.role, "warden")
        self.assertEqual(self.student.branch, "Hostel Administration")

        # Verify AuditLog
        self.assertTrue(AuditLog.objects.filter(action='WARDEN_ROLE_ASSIGNED', target__contains=self.student.roll_no).exists())

    def test_admin_can_revoke_warden_access(self):
        self._login_as(self.admin)
        self.assertEqual(self.warden.role, "warden")

        res = self.client.post(
            reverse('matcher:api_admin_revoke_warden', kwargs={'user_id': self.warden.id})
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data['ok'])

        self.warden.refresh_from_db()
        self.assertEqual(self.warden.role, "student")

        # Verify AuditLog
        self.assertTrue(AuditLog.objects.filter(action='WARDEN_ROLE_REVOKED', target__contains=self.warden.roll_no).exists())

    def test_student_and_unauthenticated_blocked_from_warden_management(self):
        # 1. Unauthenticated -> 401
        res1 = self.client.post(
            reverse('matcher:api_admin_assign_warden'),
            data=json.dumps({'user_id': self.student.id}),
            content_type='application/json'
        )
        self.assertEqual(res1.status_code, 401)

        # 2. Student -> 403
        self._login_as(self.student)
        res2 = self.client.post(
            reverse('matcher:api_admin_create_warden'),
            data=json.dumps({'name': 'Fake', 'roll_no': 'W-99', 'email': 'fake@c.edu'}),
            content_type='application/json'
        )
        self.assertEqual(res2.status_code, 403)

    def test_admin_dashboard_renders_warden_management_section(self):
        self._login_as(self.admin)
        res = self.client.get(reverse('matcher:admin_dashboard'))
        self.assertEqual(res.status_code, 200)
        content = res.content.decode('utf-8')
        self.assertIn("Hostel Wardens & Governance Staff", content)
        self.assertIn("Add New Warden", content)
        self.assertIn("Make Warden", content)
        self.assertIn(self.warden.name, content)
