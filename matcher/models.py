import time
from datetime import timedelta
from django.db import models
from django.utils import timezone
from django.db.models import Q, F, CheckConstraint, UniqueConstraint


class HostelBlock(models.Model):
    GENDER_CHOICES = [
        ('M', 'Boys Hostel (BH)'),
        ('F', 'Girls Hostel (GH)'),
        ('COED', 'Co-Ed Hostel'),
    ]
    name = models.CharField(max_length=80, unique=True, help_text="e.g. BH-1 - Block A")
    hostel_name = models.CharField(max_length=30, blank=True, default="", help_text="e.g. BH-1, GH-2")
    block_name = models.CharField(max_length=20, blank=True, default="", help_text="e.g. Block A, Block B, Block C")
    gender = models.CharField(max_length=10, choices=GENDER_CHOICES, default='M')
    total_floors = models.PositiveSmallIntegerField(default=10, help_text="Standard 10-floor hostel tower")
    campus = models.CharField(max_length=80, default="Main Campus")

    def __str__(self):
        return f"{self.name} ({self.get_gender_display()})"


class Room(models.Model):
    block = models.ForeignKey(HostelBlock, on_delete=models.CASCADE, related_name='rooms')
    number = models.CharField(max_length=20)
    capacity = models.PositiveSmallIntegerField(default=2, help_text="Dual student room: strictly 2 students")
    floor = models.PositiveSmallIntegerField(default=1)
    is_accessible = models.BooleanField(default=False, help_text="Priority for students with accessibility needs")
    amenities = models.JSONField(default=list, blank=True, help_text="List of room amenities")
    room_type = models.CharField(max_length=10, choices=[('SINGLE','Single'),('DOUBLE','Double'),('TRIPLE','Triple'),('QUAD','Quad')], default='DOUBLE')
    facility_flags = models.JSONField(default=list, blank=True, help_text="e.g. ['AC','ATTACHED_WASH','BALCONY','ACCESSIBLE']")
    bed_labels = models.JSONField(default=list, blank=True, help_text="e.g. ['Bed-A','Bed-B']")
    status = models.CharField(max_length=12, choices=[('AVAILABLE','Available'),('OCCUPIED','Occupied'),('MAINTENANCE','Under Maintenance'),('RESERVED','Reserved')], default='AVAILABLE')
    price_per_semester = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    class Meta:
        unique_together = ('block', 'number')
        ordering = ['block', 'floor', 'number']

    def __str__(self):
        return f"{self.block.name} - Room {self.number} (Dual Occupancy)"

    @property
    def occupied_count(self):
        return self.allotments.filter(is_active=True).count()

    @property
    def is_available(self):
        return self.occupied_count < self.capacity


class StudentUser(models.Model):
    ROLE_CHOICES = [
        ('student', 'Student'),
        ('warden', 'Hostel Warden'),
        ('admin', 'Allotment Admin'),
    ]
    GENDER_CHOICES = [
        ('M', 'Male'),
        ('F', 'Female'),
        ('O', 'Other'),
    ]
    roll_no = models.CharField(
        max_length=30, unique=True,
        verbose_name="Registration Number",
        help_text="University registration number (e.g. 12310266, 12519174)"
    )
    name = models.CharField(max_length=80)
    email = models.EmailField(unique=True)
    gender = models.CharField(max_length=10, choices=GENDER_CHOICES, default='M')
    year = models.CharField(max_length=30, default="1st Year")
    branch = models.CharField(max_length=80, default="Computer Science")
    block = models.ForeignKey(HostelBlock, on_delete=models.SET_NULL, null=True, blank=True, related_name='residents')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='student')
    phone = models.CharField(max_length=20, blank=True, default="")
    
    # DPDP Act 2023 privacy consent
    consent_given = models.BooleanField(default=False)
    consent_at = models.DateTimeField(null=True, blank=True)

    persona = models.CharField(max_length=60, blank=True, default="Wanderer")
    avatar_hue = models.PositiveSmallIntegerField(default=260)
    is_demo = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    # Security & Authentication Controls
    password_hash = models.CharField(max_length=255, blank=True, default="")
    failed_login_attempts = models.PositiveSmallIntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)
    last_login_at = models.DateTimeField(null=True, blank=True)
    last_login_ip = models.CharField(max_length=45, blank=True, default="")
    is_freshman = models.BooleanField(default=False, help_text="First-year flag for anti-ragging isolation rules")
    disability_verified = models.BooleanField(default=False, help_text="True when disability documentation approved")
    dietary_pref = models.CharField(max_length=20, choices=[('VEG','Vegetarian'),('NONVEG','Non-Vegetarian'),('VEGAN','Vegan'),('JAIN','Jain'),('ANY','No Preference')], default='ANY', blank=True)
    mess_plan = models.CharField(max_length=20, blank=True, default='', help_text="Assigned mess/dining hall plan")
    password_reset_token = models.CharField(max_length=64, blank=True, default='')
    password_reset_expires = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['name']
        indexes = [
            models.Index(fields=['role', 'gender', 'block'], name='student_role_gender_block_idx'),
        ]

    def set_password(self, raw_password):
        from django.contrib.auth.hashers import make_password
        self.password_hash = make_password(raw_password)

    def check_password(self, raw_password):
        from django.contrib.auth.hashers import check_password
        if not self.password_hash:
            return False
        return check_password(raw_password, self.password_hash)

    def is_locked(self):
        if self.locked_until and timezone.now() < self.locked_until:
            return True
        return False

    def record_failed_login(self):
        self.failed_login_attempts += 1
        if self.failed_login_attempts >= 5:
            self.locked_until = timezone.now() + timedelta(minutes=15)
        self.save(update_fields=['failed_login_attempts', 'locked_until'])

    def reset_failed_logins(self, ip_address=""):
        self.failed_login_attempts = 0
        self.locked_until = None
        self.last_login_at = timezone.now()
        if ip_address:
            self.last_login_ip = ip_address
        self.save(update_fields=['failed_login_attempts', 'locked_until', 'last_login_at', 'last_login_ip'])

    @property
    def registration_no(self):
        return self.roll_no

    @registration_no.setter
    def registration_no(self, value):
        self.roll_no = value

    def __str__(self):
        return f"{self.name} ({self.roll_no}) - {self.role.capitalize()}"

    @property
    def is_paired(self):
        return Pair.objects.filter(
            Q(user_a=self) | Q(user_b=self)
        ).exists()

    def get_pair(self):
        return Pair.objects.filter(
            Q(user_a=self) | Q(user_b=self)
        ).first()

    @property
    def has_completed_survey(self):
        active_count = Question.objects.filter(is_active=True).count()
        threshold = min(8, active_count) if active_count > 0 else 8
        return self.responses.count() >= threshold


class AllotmentCalendar(models.Model):
    PHASE_CHOICES = [
        ('REGISTRATION', '1. Registration (Account Verification)'),
        ('SURVEY_OPEN', '2. Survey Open (Students Fill/Edit Quiz)'),
        ('MATCHING_OPEN', '3. Matching Open (Ranked Matches & Requests)'),
        ('FREEZE', '4. Freeze (Quiz & Requests Locked)'),
        ('LEFTOVER_PAIRING', '5. Leftover Pairing (Automated Blossom Matching)'),
        ('WARDEN_ALLOTMENT', '6. Warden Allotment (Confirmed Pairs Assigned Rooms)'),
        ('PUBLISHED', '7. Published (Students View Final Room & Roommate)'),
    ]

    phase = models.CharField(max_length=30, choices=PHASE_CHOICES, default='MATCHING_OPEN')
    survey_deadline = models.DateTimeField(null=True, blank=True)
    matching_deadline = models.DateTimeField(null=True, blank=True)
    freeze_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.CharField(max_length=80, blank=True, default="Admin")

    @classmethod
    def get_current(cls):
        obj, _ = cls.objects.get_or_create(id=1, defaults={'phase': 'MATCHING_OPEN'})
        return obj

    def __str__(self):
        return f"Calendar: {self.get_phase_display()}"


class Question(models.Model):
    key = models.CharField(max_length=30, unique=True)
    text = models.CharField(max_length=255)
    type = models.CharField(max_length=30, default="choice")
    min_val = models.IntegerField(default=1)
    max_val = models.IntegerField(default=4)
    base_weight = models.FloatField(default=3.0)
    is_circular = models.BooleanField(default=False, help_text="True if values wrap circularly, e.g. sleep/wake clock")
    cycle_period = models.PositiveSmallIntegerField(default=4, help_text="Number of distinct intervals in the cycle")
    version = models.PositiveIntegerField(default=1)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['id']

    def __str__(self):
        return f"Q v{self.version}: {self.key} - {self.text[:40]}"


class Response(models.Model):
    user = models.ForeignKey(StudentUser, on_delete=models.CASCADE, related_name='responses')
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='responses')
    answer = models.IntegerField()
    importance = models.PositiveSmallIntegerField(default=2, help_text="1: a little, 2: it matters, 3: essential weight")
    is_dealbreaker = models.BooleanField(default=False, help_text="Strict veto: mismatch causes hard clash")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('user', 'question')
        ordering = ['user', 'question']

    def __str__(self):
        return f"{self.user.name} - {self.question.key}: {self.answer} (Weight: {self.importance}, Dealbreaker: {self.is_dealbreaker})"


class PairScore(models.Model):
    user_a = models.ForeignKey(StudentUser, on_delete=models.CASCADE, related_name='scores_as_a')
    user_b = models.ForeignKey(StudentUser, on_delete=models.CASCADE, related_name='scores_as_b')
    score_a_to_b = models.FloatField()
    score_b_to_a = models.FloatField()
    final_score = models.FloatField(help_text="Lower of the two scores for mutual satisfaction")
    good_reasons = models.JSONField(default=list, blank=True)
    frictions = models.JSONField(default=list, blank=True)
    clashes = models.JSONField(default=list, blank=True)
    algorithm_version = models.CharField(max_length=20, default="2.1.0")
    computed_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('user_a', 'user_b')
        ordering = ['-final_score']
        indexes = [
            models.Index(fields=['user_a', 'user_b', 'final_score'], name='pairscore_lookup_score_idx'),
        ]

    def __str__(self):
        return f"Score {self.user_a.name} <-> {self.user_b.name}: {self.final_score:.0f}%"


class Request(models.Model):
    STATUS_CHOICES = [
        ('SENT', 'Sent'),
        ('ACCEPTED', 'Accepted'),
        ('DECLINED', 'Declined'),
        ('EXPIRED', 'Expired (48h)'),
        ('CANCELLED', 'Cancelled (Auto-cancelled upon another pairing)'),
    ]

    from_user = models.ForeignKey(StudentUser, on_delete=models.CASCADE, related_name='outgoing_requests')
    to_user = models.ForeignKey(StudentUser, on_delete=models.CASCADE, related_name='incoming_requests')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='SENT')
    note = models.CharField(max_length=150, blank=True, default="")
    pair_hash = models.CharField(max_length=80, db_index=True, help_text="Canonical hash of (min_id, max_id) for uniqueness constraint")
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    class Meta:
        ordering = ['-created_at']
        constraints = [
            CheckConstraint(condition=~Q(from_user=F('to_user')), name='prevent_self_request'),
        ]
        indexes = [
            models.Index(fields=['from_user', 'status'], name='request_from_status_idx'),
            models.Index(fields=['to_user', 'status'], name='request_to_status_idx'),
        ]

    def save(self, *args, **kwargs):
        if not self.expires_at:
            self.expires_at = timezone.now() + timedelta(hours=48)
        u1_id = min(self.from_user_id, self.to_user_id)
        u2_id = max(self.from_user_id, self.to_user_id)
        self.pair_hash = f"{u1_id}_{u2_id}"
        super().save(*args, **kwargs)

    @property
    def is_expired(self):
        return timezone.now() > self.expires_at and self.status == 'SENT'

    def __str__(self):
        return f"Req: {self.from_user.name} -> {self.to_user.name} ({self.status})"


class Pair(models.Model):
    METHOD_CHOICES = [
        ('MUTUAL_REQUEST', 'Mutual Student Request'),
        ('BLOSSOM_MATCHING', 'Automated Blossom Max-Weight Matching'),
        ('WARDEN_OVERRIDE', 'Warden Administrative Assignment'),
    ]
    STATUS_CHOICES = [
        ('CONFIRMED', 'Confirmed Pair (Awaiting Room)'),
        ('ALLOTTED', 'Room Allotted'),
        ('OVERRIDDEN', 'Overridden by Warden'),
    ]

    user_a = models.ForeignKey(StudentUser, on_delete=models.CASCADE, related_name='pairs_as_a')
    user_b = models.ForeignKey(StudentUser, on_delete=models.CASCADE, related_name='pairs_as_b')
    room = models.ForeignKey(Room, on_delete=models.SET_NULL, null=True, blank=True, related_name='pairs')
    method = models.CharField(max_length=30, choices=METHOD_CHOICES, default='MUTUAL_REQUEST')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='CONFIRMED')
    confirmed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-confirmed_at']
        constraints = [
            UniqueConstraint(fields=['user_a'], name='one_pair_a'),
            UniqueConstraint(fields=['user_b'], name='one_pair_b'),
            CheckConstraint(condition=Q(user_a_id__lt=F('user_b_id')), name='canonical_pair_ordering'),
        ]

    def __str__(self):
        return f"Pair: {self.user_a.name} & {self.user_b.name} -> {self.room.number if self.room else 'No Room'}"

    def partner_of(self, user):
        if self.user_a == user:
            return self.user_b
        return self.user_a


class Allotment(models.Model):
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name='allotments')
    user = models.ForeignKey(StudentUser, on_delete=models.CASCADE, related_name='allotments')
    allotted_by = models.ForeignKey(StudentUser, on_delete=models.SET_NULL, null=True, related_name='administered_allotments')
    allotted_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)
    checked_in = models.BooleanField(default=False)
    checked_in_at = models.DateTimeField(null=True, blank=True)
    key_issued = models.BooleanField(default=False)
    maintenance_notes = models.TextField(blank=True, default="")

    class Meta:
        unique_together = ('room', 'user')
        ordering = ['-allotted_at']

    def __str__(self):
        return f"Allotment: {self.user.name} -> {self.room}"


class AuditLog(models.Model):
    actor = models.CharField(max_length=80, default="System")
    action = models.CharField(max_length=60)
    target = models.CharField(max_length=120)
    reason = models.TextField(blank=True, default="")
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-timestamp']

    def __str__(self):
        return f"[{self.timestamp.strftime('%Y-%m-%d %H:%M')}] {self.actor} - {self.action}: {self.target}"

class OTPVerification(models.Model):
    user = models.ForeignKey(StudentUser, on_delete=models.CASCADE, related_name='otps')
    otp_hash = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    attempts_left = models.PositiveSmallIntegerField(default=3)
    is_used = models.BooleanField(default=False)
    ip_address = models.CharField(max_length=45, blank=True, default="")

    class Meta:
        ordering = ['-created_at']

    @property
    def is_expired(self):
        return timezone.now() > self.expires_at

    def verify(self, raw_otp):
        from django.contrib.auth.hashers import check_password
        if self.is_used or self.is_expired or self.attempts_left <= 0:
            return False
        match = check_password(str(raw_otp).strip(), self.otp_hash)
        if not match:
            self.attempts_left = max(0, self.attempts_left - 1)
            self.save(update_fields=['attempts_left'])
            return False
        self.is_used = True
        self.save(update_fields=['is_used'])
        return True

    def __str__(self):
        return f"OTP for {self.user.roll_no} (Expires: {self.expires_at.strftime('%H:%M:%S')}, Used: {self.is_used})"


class GuardianConsent(models.Model):
    student = models.OneToOneField(StudentUser, on_delete=models.CASCADE, related_name='guardian_consent')
    is_minor = models.BooleanField(default=False)
    guardian_name = models.CharField(max_length=100, blank=True, default="")
    guardian_email = models.EmailField(blank=True, default="")
    guardian_phone = models.CharField(max_length=20, blank=True, default="")
    consent_verified = models.BooleanField(default=False)
    consent_token = models.CharField(max_length=64, blank=True, default="")
    verified_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Guardian Consent"
        verbose_name_plural = "Guardian Consents"

    def __str__(self):
        return f"Guardian Consent: {self.student.roll_no} (Minor: {self.is_minor}, Verified: {self.consent_verified})"


class Ticket(models.Model):
    TICKET_TYPES = [
        ('ROOM_CHANGE', 'Room Change Request'),
        ('COMPLAINT', 'Roommate Conflict Complaint'),
        ('MAINTENANCE', 'Facility / Room Maintenance'),
        ('OTHER', 'General Inquiry'),
    ]
    STATUS_CHOICES = [
        ('OPEN', 'Open'),
        ('IN_REVIEW', 'Under Warden Review'),
        ('RESOLVED', 'Resolved'),
        ('REJECTED', 'Rejected'),
    ]

    student = models.ForeignKey(StudentUser, on_delete=models.CASCADE, related_name='tickets')
    ticket_type = models.CharField(max_length=30, choices=TICKET_TYPES, default='COMPLAINT')
    subject = models.CharField(max_length=150)
    description = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='OPEN')
    resolution_notes = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"[{self.get_ticket_type_display()}] {self.student.roll_no}: {self.subject} ({self.status})"


class Feedback(models.Model):
    allotment = models.ForeignKey(Allotment, on_delete=models.CASCADE, related_name='feedbacks')
    student = models.ForeignKey(StudentUser, on_delete=models.CASCADE, related_name='feedbacks')
    roommate_harmony_rating = models.PositiveSmallIntegerField(default=5, help_text="Rating 1-5")
    sleep_compatibility_rating = models.PositiveSmallIntegerField(default=5, help_text="Rating 1-5")
    cleanliness_rating = models.PositiveSmallIntegerField(default=5, help_text="Rating 1-5")
    would_recommend_partner = models.BooleanField(default=True)
    comments = models.TextField(blank=True, default="")
    submitted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-submitted_at']
        unique_together = ('allotment', 'student')

    def __str__(self):
        return f"Feedback from {self.student.roll_no} (Harmony: {self.roommate_harmony_rating}/5)"


class Notification(models.Model):
    student = models.ForeignKey(StudentUser, on_delete=models.CASCADE, related_name='notifications')
    title = models.CharField(max_length=120)
    message = models.TextField()
    category = models.CharField(max_length=30, default='INFO')  # e.g., 'REQUEST', 'SYSTEM', 'ALLOTMENT', 'TICKET'
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Notification for {self.student.roll_no}: {self.title} (Read: {self.is_read})"

class AcademicSession(models.Model):
    name = models.CharField(max_length=20, unique=True, help_text="e.g. '2026-27'")
    start_date = models.DateField()
    end_date = models.DateField()
    is_current = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-start_date']

    def __str__(self):
        return f"{self.name} ({'Current' if self.is_current else 'Archived'})"


class HostelFee(models.Model):
    FEE_STATUS = [('PENDING','Pending'),('VERIFIED','Verified'),('EXEMPTED','Exempted')]
    student = models.ForeignKey(StudentUser, on_delete=models.CASCADE, related_name='fees')
    academic_session = models.ForeignKey(AcademicSession, on_delete=models.CASCADE, related_name='fees', null=True, blank=True)
    academic_year = models.CharField(max_length=20, help_text="e.g. '2026-27'")
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    transaction_ref = models.CharField(max_length=64, blank=True, default='')
    status = models.CharField(max_length=10, choices=FEE_STATUS, default='PENDING')
    receipt_file = models.FileField(upload_to='fee_receipts/', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    verified_at = models.DateTimeField(null=True, blank=True)
    verified_by = models.CharField(max_length=80, blank=True, default='')

    class Meta:
        ordering = ['-created_at']
        unique_together = ('student', 'academic_year')

    def __str__(self):
        return f"Fee: {self.student.roll_no} - {self.academic_year} ({self.status})"


class EmergencyContact(models.Model):
    student = models.OneToOneField(StudentUser, on_delete=models.CASCADE, related_name='emergency_contact')
    blood_group = models.CharField(max_length=5, blank=True, default='')
    medical_conditions = models.TextField(blank=True, default='')
    chronic_allergies = models.TextField(blank=True, default='')
    parent_name = models.CharField(max_length=100, blank=True, default='')
    parent_phone = models.CharField(max_length=20, blank=True, default='')
    parent_email = models.EmailField(blank=True, default='')
    local_guardian_name = models.CharField(max_length=100, blank=True, default='')
    local_guardian_phone = models.CharField(max_length=20, blank=True, default='')
    home_address = models.TextField(blank=True, default='')
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Emergency: {self.student.roll_no} - {self.parent_name}"


class HostelCheckin(models.Model):
    allotment = models.OneToOneField(Allotment, on_delete=models.CASCADE, related_name='checkin')
    checkin_date = models.DateTimeField(default=timezone.now)
    key_issued = models.BooleanField(default=False)
    inventory_checklist = models.JSONField(default=dict, blank=True, help_text="e.g. {'mattress':true,'table':true,'chair':true,'cupboard_key':false}")
    warden_signoff = models.BooleanField(default=False)
    warden_name = models.CharField(max_length=80, blank=True, default='')
    signed_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True, default='')

    def __str__(self):
        return f"Check-in: {self.allotment.user.roll_no} @ {self.allotment.room} ({self.checkin_date.strftime('%Y-%m-%d')})"


class RoomSwapRequest(models.Model):
    SWAP_STATUS = [('PENDING_PEER','Peer Approval Pending'),('WARDEN_REVIEW','Warden Review'),('APPROVED','Approved'),('REJECTED','Rejected')]
    requester = models.ForeignKey(StudentUser, on_delete=models.CASCADE, related_name='swap_requests_out')
    requester_pair = models.ForeignKey(Pair, on_delete=models.CASCADE, related_name='outgoing_swaps')
    target_pair = models.ForeignKey(Pair, on_delete=models.CASCADE, related_name='incoming_swaps')
    reason = models.TextField(blank=True, default='')
    status = models.CharField(max_length=20, choices=SWAP_STATUS, default='PENDING_PEER')
    peer_approved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.CharField(max_length=80, blank=True, default='')
    warden_note = models.TextField(blank=True, default='')

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Swap: {self.requester.roll_no} -> Pair#{self.target_pair.id} ({self.status})"


class MaintenanceTicket(models.Model):
    CATEGORY_CHOICES = [('ELECTRICAL','Electrical'),('PLUMBING','Plumbing'),('FURNITURE','Furniture'),('INTERNET','Internet'),('ROOMMATE','Roommate Dispute'),('OTHER','Other')]
    PRIORITY_CHOICES = [(1,'Low'),(2,'Medium'),(3,'High'),(4,'Critical')]
    STATUS_CHOICES = [('OPEN','Open'),('IN_PROGRESS','In Progress'),('RESOLVED','Resolved'),('REJECTED','Rejected')]
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name='maintenance_tickets')
    student = models.ForeignKey(StudentUser, on_delete=models.CASCADE, related_name='filed_maintenance')
    category = models.CharField(max_length=12, choices=CATEGORY_CHOICES, default='OTHER')
    subject = models.CharField(max_length=200)
    description = models.TextField()
    priority = models.IntegerField(choices=PRIORITY_CHOICES, default=2)
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default='OPEN')
    resolution_notes = models.TextField(blank=True, default='')
    assigned_to = models.CharField(max_length=80, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-priority', '-created_at']

    def __str__(self):
        return f"Maint#{self.id}: {self.category} - {self.subject} ({self.status})"


class GatePass(models.Model):
    PASS_STATUS = [('PENDING','Pending'),('APPROVED','Approved'),('REJECTED','Rejected'),('RETURNED','Returned')]
    student = models.ForeignKey(StudentUser, on_delete=models.CASCADE, related_name='gate_passes')
    leave_date = models.DateTimeField()
    return_date = models.DateTimeField()
    destination = models.CharField(max_length=200)
    reason = models.TextField(blank=True, default='')
    parent_contact = models.CharField(max_length=20, blank=True, default='')
    status = models.CharField(max_length=10, choices=PASS_STATUS, default='PENDING')
    approved_by = models.CharField(max_length=80, blank=True, default='')
    actual_return = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"GatePass: {self.student.roll_no} ({self.leave_date.strftime('%Y-%m-%d')} to {self.return_date.strftime('%Y-%m-%d')}) - {self.status}"


class DisciplinaryRecord(models.Model):
    SEVERITY_CHOICES = [(1,'Warning'),(2,'Fine'),(3,'Suspension'),(4,'Expulsion')]
    student = models.ForeignKey(StudentUser, on_delete=models.CASCADE, related_name='disciplinary_records')
    violation = models.CharField(max_length=200)
    description = models.TextField(blank=True, default='')
    severity = models.IntegerField(choices=SEVERITY_CHOICES, default=1)
    fine_amount = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    fine_paid = models.BooleanField(default=False)
    issued_by = models.CharField(max_length=80)
    issued_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-issued_at']

    def __str__(self):
        return f"Discipline: {self.student.roll_no} - {self.violation} (Severity: {self.severity})"

