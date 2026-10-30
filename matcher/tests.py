from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
import json

from matcher.models import (
    HostelBlock, Room, StudentUser, AllotmentCalendar,
    Question, Response, PairScore, Request, Pair, Allotment, AuditLog, OTPVerification
)
from matcher.scoring import (
    calculate_mutual_score, compute_ranked_matches_for_student,
    run_blossom_leftover_matching, run_automated_room_allotment
)


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
        Response.objects.create(user=self.aarav, question=self.q_smoke, answer=1, importance=3) # Deal-breaker
        Response.objects.create(user=self.aarav, question=self.q_tidy, answer=4, importance=2)

        # Answers: Rohan (Very similar to Aarav, smoke=1, tidy=4)
        Response.objects.create(user=self.rohan, question=self.q_sleep, answer=3, importance=2)
        Response.objects.create(user=self.rohan, question=self.q_smoke, answer=1, importance=3)
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
        self.caretaker = StudentUser.objects.create(
            roll_no="CARETAKER-01", name="Ramesh Kumar", email="ramesh.caretaker@college.edu",
            gender="M", year="Staff", branch="Hostel Facility Desk", role="caretaker"
        )
        self.admin = StudentUser.objects.create(
            roll_no="ADMIN-01", name="Prof. Anjali Verma", email="allotment.admin@college.edu",
            gender="F", year="Admin", branch="Hostel Affairs Board", role="admin"
        )

        self.allotment = Allotment.objects.create(
            room=self.room, user=self.student, is_active=True
        )

    def test_student_login_with_otp(self):
        res = self.client.post(
            reverse('matcher:api_login'),
            data=json.dumps({
                'role': 'student',
                'identity': 'CS26B099',
                'secret': '482910'
            }),
            content_type='application/json'
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data['ok'])
        self.assertEqual(data['role'], 'student')
        self.assertEqual(data['redirect_url'], '/student/')
        self.assertEqual(self.client.session.get('current_user_id'), self.student.id)

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

    def test_caretaker_login_and_toggle(self):
        # Login as caretaker
        res = self.client.post(
            reverse('matcher:api_login'),
            data=json.dumps({
                'role': 'caretaker',
                'identity': 'CARETAKER-01',
                'secret': 'caretaker123'
            }),
            content_type='application/json'
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()['redirect_url'], '/caretaker/')

        # Toggle check-in status
        self.assertFalse(self.allotment.checked_in)
        toggle_res = self.client.post(
            reverse('matcher:api_caretaker_toggle'),
            data=json.dumps({'allotment_id': self.allotment.id, 'action': 'checkin'}),
            content_type='application/json'
        )
        self.assertEqual(toggle_res.status_code, 200)
        self.allotment.refresh_from_db()
        self.assertTrue(self.allotment.checked_in)
        self.assertIsNotNone(self.allotment.checked_in_at)

        # Toggle room key issuance
        self.assertFalse(self.allotment.key_issued)
        toggle_key = self.client.post(
            reverse('matcher:api_caretaker_toggle'),
            data=json.dumps({'allotment_id': self.allotment.id, 'action': 'key'}),
            content_type='application/json'
        )
        self.assertEqual(toggle_key.status_code, 200)
        self.allotment.refresh_from_db()
        self.assertTrue(self.allotment.key_issued)

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
        self.assertIn('Hostel Block', csv_res.content.decode('utf-8'))

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
        self.assertIn("kindred", content)
        self.assertIn("Mandakini Hall", content)
        self.assertIn("four dedicated portals", content)

    def test_secure_otp_generation_and_verification(self):
        # 1. Request OTP
        res_otp = self.client.post(
            reverse('matcher:api_send_otp'),
            data=json.dumps({'identity': 'CS26B777', 'role': 'student'}),
            content_type='application/json'
        )
        self.assertEqual(res_otp.status_code, 200)
        data_otp = res_otp.json()
        self.assertTrue(data_otp['ok'])
        otp_code = data_otp['demo_otp']
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
