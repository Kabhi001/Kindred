import json
from datetime import timedelta
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from django.core.management import call_command
import io

from matcher.models import (
    HostelBlock, Room, StudentUser, AllotmentCalendar,
    Question, Response, PairScore, Request, Pair, Allotment, AuditLog,
    AcademicSession, HostelFee, EmergencyContact, HostelCheckin,
    RoomSwapRequest, MaintenanceTicket, GatePass, DisciplinaryRecord
)


class ComprehensiveCampusFeaturesTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.calendar = AllotmentCalendar.objects.create(phase='MATCHING_OPEN')
        self.block = HostelBlock.objects.create(name="BH-1 - Block A", gender='M', total_floors=4)

        self.room1 = Room.objects.create(block=self.block, number="101", capacity=2, floor=1, room_type='DOUBLE')
        self.room2 = Room.objects.create(block=self.block, number="102", capacity=2, floor=1, room_type='DOUBLE')

        # Admin user
        self.admin = StudentUser.objects.create(
            roll_no="ADM001", name="Chief Admin", email="admin@campus.edu",
            role="admin", gender="M", consent_given=True
        )
        self.admin.set_password("admin123")
        self.admin.save()

        # Warden user
        self.warden = StudentUser.objects.create(
            roll_no="WRD001", name="Warden Sharma", email="warden@campus.edu",
            role="warden", gender="M", block=self.block, consent_given=True
        )
        self.warden.set_password("warden123")
        self.warden.save()

        # Students
        self.student1 = StudentUser.objects.create(
            roll_no="12310266", name="Pranshu Kumar", email="pranshu@campus.edu",
            role="student", gender="M", year="1st Year", is_freshman=True,
            block=self.block, consent_given=True
        )
        self.student1.set_password("pass123")
        self.student1.save()

        self.student2 = StudentUser.objects.create(
            roll_no="12519174", name="Aman Singh", email="aman@campus.edu",
            role="student", gender="M", year="1st Year", is_freshman=True,
            block=self.block, consent_given=True
        )
        self.student2.set_password("pass123")
        self.student2.save()

        self.senior = StudentUser.objects.create(
            roll_no="12100450", name="Senior Rahul", email="senior@campus.edu",
            role="student", gender="M", year="3rd Year", is_freshman=False,
            block=self.block, consent_given=True
        )
        self.senior.set_password("pass123")
        self.senior.save()

    def _login(self, user):
        session = self.client.session
        session['current_user_id'] = user.id
        session['user_role'] = user.role
        session.save()

    # 1. Password Reset Flow
    def test_password_reset_flow(self):
        # Request token
        res = self.client.post(
            reverse('matcher:api_password_reset_request'),
            data=json.dumps({'identity': self.student1.roll_no}),
            content_type='application/json'
        )
        self.assertEqual(res.status_code, 200)
        self.student1.refresh_from_db()
        self.assertTrue(len(self.student1.password_reset_token) > 10)
        self.assertIsNotNone(self.student1.password_reset_expires)

        # Confirm reset with valid token
        token = self.student1.password_reset_token
        res2 = self.client.post(
            reverse('matcher:api_password_reset_confirm'),
            data=json.dumps({
                'token': token,
                'new_password': 'brandnewpassword123',
                'confirm_password': 'brandnewpassword123'
            }),
            content_type='application/json'
        )
        self.assertEqual(res2.status_code, 200)
        self.student1.refresh_from_db()
        self.assertTrue(self.student1.check_password('brandnewpassword123'))
        self.assertEqual(self.student1.password_reset_token, '')

    # 2. DPDP Act Right to be Forgotten
    def test_dpdp_withdraw_consent(self):
        self._login(self.student1)
        EmergencyContact.objects.create(student=self.student1, parent_name="Parent", blood_group="O+")
        res = self.client.post(reverse('matcher:api_withdraw_consent'))
        self.assertEqual(res.status_code, 200)
        self.student1.refresh_from_db()
        self.assertIn("Redacted-User", self.student1.name)
        self.assertFalse(self.student1.consent_given)
        self.assertFalse(EmergencyContact.objects.filter(student=self.student1).exists())

    # 3. Emergency Contact CRUD
    def test_emergency_contact_api(self):
        self._login(self.student1)
        # Create/Update
        res = self.client.post(
            reverse('matcher:api_emergency_contact'),
            data=json.dumps({
                'blood_group': 'B+',
                'medical_conditions': 'None',
                'chronic_allergies': 'Peanuts',
                'parent_name': 'Ramesh Kumar',
                'parent_phone': '9876543210',
                'parent_email': 'ramesh@example.com',
                'home_address': 'Sector 14, Chandigarh'
            }),
            content_type='application/json'
        )
        self.assertEqual(res.status_code, 200)

        # GET
        res_get = self.client.get(reverse('matcher:api_emergency_contact'))
        self.assertEqual(res_get.status_code, 200)
        data = res_get.json()
        self.assertEqual(data['contact']['blood_group'], 'B+')
        self.assertEqual(data['contact']['parent_name'], 'Ramesh Kumar')

    # 4. Hostel Fee Clearance & Verification
    def test_fee_clearance_workflow(self):
        self._login(self.student1)
        # Submit payment
        res = self.client.post(
            reverse('matcher:api_submit_fee_payment'),
            data=json.dumps({'academic_year': '2026-27', 'amount': '50000.00', 'transaction_ref': 'TXN123456789'}),
            content_type='application/json'
        )
        self.assertEqual(res.status_code, 200)
        fee = HostelFee.objects.get(student=self.student1)
        self.assertEqual(fee.status, 'PENDING')

        # Warden verifies fee
        self._login(self.warden)
        res_ver = self.client.post(
            reverse('matcher:api_verify_fee'),
            data=json.dumps({'fee_id': fee.id}),
            content_type='application/json'
        )
        self.assertEqual(res_ver.status_code, 200)
        fee.refresh_from_db()
        self.assertEqual(fee.status, 'VERIFIED')
        self.assertEqual(fee.verified_by, self.warden.name)

    # 5. Physical Check-in & QR Verification
    def test_physical_checkin(self):
        pair = Pair.objects.create(user_a=self.student1, user_b=self.student2, room=self.room1, status='ALLOTTED')
        Allotment.objects.create(room=self.room1, user=self.student1, is_active=True)
        Allotment.objects.create(room=self.room1, user=self.student2, is_active=True)

        self._login(self.warden)
        res = self.client.post(
            reverse('matcher:api_checkin_student'),
            data=json.dumps({
                'roll_no': self.student1.roll_no,
                'key_issued': True,
                'inventory_checklist': {'mattress': True, 'table': True, 'chair': True}
            }),
            content_type='application/json'
        )
        self.assertEqual(res.status_code, 200)
        allotment = Allotment.objects.get(room=self.room1, user=self.student1)
        self.assertTrue(allotment.checked_in)
        self.assertTrue(allotment.key_issued)
        checkin = HostelCheckin.objects.get(allotment=allotment)
        self.assertTrue(checkin.warden_signoff)

    # 6. Mutual Room Swap
    def test_room_swap_request_flow(self):
        pair1 = Pair.objects.create(user_a=self.student1, user_b=self.student2, room=self.room1, status='ALLOTTED')
        Allotment.objects.create(room=self.room1, user=self.student1, is_active=True)
        Allotment.objects.create(room=self.room1, user=self.student2, is_active=True)

        s3 = StudentUser.objects.create(roll_no="S3", name="Student Three", email="s3@campus.edu", gender="M", block=self.block, role="student")
        s4 = StudentUser.objects.create(roll_no="S4", name="Student Four", email="s4@campus.edu", gender="M", block=self.block, role="student")
        pair2 = Pair.objects.create(user_a=s3, user_b=s4, room=self.room2, status='ALLOTTED')
        Allotment.objects.create(room=self.room2, user=s3, is_active=True)
        Allotment.objects.create(room=self.room2, user=s4, is_active=True)

        self._login(self.student1)
        res = self.client.post(
            reverse('matcher:api_create_swap_request'),
            data=json.dumps({'target_room': self.room2.number, 'reason': 'Prefers higher sunlight'}),
            content_type='application/json'
        )
        self.assertEqual(res.status_code, 201)
        swap = RoomSwapRequest.objects.first()
        self.assertEqual(swap.status, 'PENDING_PEER')

        # Warden approves swap
        self._login(self.warden)
        res_app = self.client.post(
            reverse('matcher:api_review_swap_request', kwargs={'swap_id': swap.id}),
            data=json.dumps({'action': 'approve', 'note': 'Approved for sunlight preference'}),
            content_type='application/json'
        )
        self.assertEqual(res_app.status_code, 200)
        pair1.refresh_from_db()
        pair2.refresh_from_db()
        self.assertEqual(pair1.room, self.room2)
        self.assertEqual(pair2.room, self.room1)

    # 7. Maintenance Ticket Lifecycle
    def test_maintenance_ticket_lifecycle(self):
        Allotment.objects.create(room=self.room1, user=self.student1, is_active=True)
        self._login(self.student1)

        # File ticket
        res = self.client.post(
            reverse('matcher:api_create_maintenance_ticket'),
            data=json.dumps({
                'category': 'ELECTRICAL',
                'subject': 'Ceiling fan making clicking noise',
                'description': 'Speed regulator not working and fan makes clicking noise on speed 3.',
                'priority': 2
            }),
            content_type='application/json'
        )
        self.assertEqual(res.status_code, 201)
        ticket_id = res.json()['ticket_id']

        # Warden updates ticket
        self._login(self.warden)
        res_up = self.client.post(
            reverse('matcher:api_update_maintenance_ticket', kwargs={'ticket_id': ticket_id}),
            data=json.dumps({
                'status': 'RESOLVED',
                'assigned_to': 'Electrician Raju',
                'resolution_notes': 'Replaced fan regulator and greased bearing.'
            }),
            content_type='application/json'
        )
        self.assertEqual(res_up.status_code, 200)
        ticket = MaintenanceTicket.objects.get(id=ticket_id)
        self.assertEqual(ticket.status, 'RESOLVED')
        self.assertEqual(ticket.assigned_to, 'Electrician Raju')

    # 8. Digital Gate Pass
    def test_gate_pass_request_and_review(self):
        self._login(self.student1)
        leave = timezone.now() + timedelta(days=1)
        ret = timezone.now() + timedelta(days=3)

        res = self.client.post(
            reverse('matcher:api_create_gate_pass'),
            data=json.dumps({
                'leave_date': leave.isoformat(),
                'return_date': ret.isoformat(),
                'destination': 'Home, Chandigarh',
                'reason': 'Family function',
                'parent_contact': '9876543210'
            }),
            content_type='application/json'
        )
        self.assertEqual(res.status_code, 201)
        pass_id = res.json()['pass_id']

        # Warden approves
        self._login(self.warden)
        res_app = self.client.post(
            reverse('matcher:api_review_gate_pass', kwargs={'pass_id': pass_id}),
            data=json.dumps({'action': 'approve'}),
            content_type='application/json'
        )
        self.assertEqual(res_app.status_code, 200)
        gp = GatePass.objects.get(id=pass_id)
        self.assertEqual(gp.status, 'APPROVED')
        self.assertEqual(gp.approved_by, self.warden.name)

    # 9. Disciplinary Records
    def test_disciplinary_action(self):
        self._login(self.warden)
        res = self.client.post(
            reverse('matcher:api_create_disciplinary_record'),
            data=json.dumps({
                'roll_no': self.student1.roll_no,
                'violation': 'Loud music past curfew hours',
                'description': 'Speaker playing after 11:30 PM.',
                'severity': 2,
                'fine_amount': 500,
                'fine_paid': False
            }),
            content_type='application/json'
        )
        self.assertEqual(res.status_code, 201)
        rec = DisciplinaryRecord.objects.get(student=self.student1)
        self.assertEqual(rec.fine_amount, 500)
        self.assertEqual(rec.issued_by, self.warden.name)

    # 10. Floor Map Matrix
    def test_floor_map_api(self):
        self._login(self.student1)
        res = self.client.get(reverse('matcher:api_floor_map'), {'block_id': self.block.id})
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data['ok'])
        self.assertEqual(data['total_rooms'], 2)
        self.assertTrue(len(data['floors']) > 0)

    # 11. Anti-Ragging Enforcement: Freshman vs Senior Block
    def test_anti_ragging_blocks_cross_year_request(self):
        self._login(self.student1)  # Freshman
        res = self.client.post(
            reverse('matcher:api_send_request'),
            data=json.dumps({
                'peer_roll_no': self.senior.roll_no,  # 3rd Year senior
                'note': 'Can we pair?'
            }),
            content_type='application/json'
        )
        self.assertEqual(res.status_code, 400)
        self.assertIn("Anti-Ragging", res.json()['error'])

    # 12. Anti-Ragging Audit API
    def test_anti_ragging_audit_api(self):
        self._login(self.admin)
        res = self.client.get(reverse('matcher:api_anti_ragging_check'))
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data['compliant'])
        self.assertEqual(data['violation_count'], 0)

    # 13. Algorithm Hyper-parameter Tuning
    def test_admin_weight_tuning(self):
        self._login(self.admin)
        q = Question.objects.create(key="test_sleep", text="Sleep Habit", base_weight=3.0)
        res = self.client.post(
            reverse('matcher:api_admin_update_weights'),
            data=json.dumps({'weights': {'test_sleep': 7.5}}),
            content_type='application/json'
        )
        self.assertEqual(res.status_code, 200)
        q.refresh_from_db()
        self.assertEqual(q.base_weight, 7.5)

    # 14. Bulk Student CSV Import
    def test_bulk_student_import(self):
        self._login(self.admin)
        csv_content = "roll_no,name,email,gender,year,branch\nCS26_01,Student One,s1@univ.edu,M,1st Year,CSE\nCS26_02,Student Two,s2@univ.edu,F,1st Year,ECE"
        res = self.client.post(
            reverse('matcher:api_bulk_import_students'),
            data=json.dumps({'csv_text': csv_content}),
            content_type='application/json'
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()['created_count'], 2)
        self.assertTrue(StudentUser.objects.filter(roll_no="CS26_01").exists())
        self.assertTrue(StudentUser.objects.filter(roll_no="CS26_02").exists())

    # 15. Allotment Slip View
    def test_allotment_slip_page(self):
        pair = Pair.objects.create(user_a=self.student1, user_b=self.student2, room=self.room1, status='ALLOTTED')
        self._login(self.student1)
        res = self.client.get(reverse('matcher:allotment_slip_me'))
        self.assertEqual(res.status_code, 200)
        content = res.content.decode('utf-8')
        self.assertIn("Official Allotment Slip", content)
        self.assertIn(self.student1.name, content)
        self.assertIn(self.room1.number, content)

    # 16. Management Command: generate_rooms
    def test_generate_rooms_command(self):
        call_command('generate_rooms', block=self.block.name, floors=2, start=10, end=12, capacity=2)
        self.assertTrue(Room.objects.filter(block=self.block, number="110").exists())
        self.assertTrue(Room.objects.filter(block=self.block, number="212").exists())

    # 17. Management Command: session_rollover
    def test_session_rollover_command(self):
        grad = StudentUser.objects.create(roll_no="GRAD01", name="Grad Student", email="grad01@campus.edu", role="student", year="4th Year", block=self.block)
        Allotment.objects.create(room=self.room1, user=grad, is_active=True)
        call_command('session_rollover', graduating_year='4th Year', new_session='2027-28')
        allotment = Allotment.objects.get(user=grad)
        self.assertFalse(allotment.is_active)
        self.assertTrue(AcademicSession.objects.filter(name='2027-28', is_current=True).exists())
