from django.core.management.base import BaseCommand
from django.utils import timezone
from matcher.models import (
    HostelBlock, Room, StudentUser, AllotmentCalendar,
    Question, Response, Request, Pair, Allotment, AuditLog
)
from matcher.matching import calculate_persona


class Command(BaseCommand):
    help = "Seed database with production hostel data, questions, calendar, and real students"

    def handle(self, *args, **options):
        self.stdout.write("Initializing Kindred production data...")

        # 1. Calendar
        calendar = AllotmentCalendar.get_current()
        calendar.phase = 'MATCHING_OPEN'
        calendar.survey_deadline = timezone.now() + timezone.timedelta(days=3)
        calendar.matching_deadline = timezone.now() + timezone.timedelta(days=7)
        calendar.freeze_at = timezone.now() + timezone.timedelta(days=8)
        calendar.save()
        self.stdout.write("  [OK] Calendar initialized to MATCHING_OPEN")

        # 2. Hostel Blocks
        block_b1, _ = HostelBlock.objects.get_or_create(
            name="Mandakini Hall (Block A)",
            defaults={'gender': 'M', 'total_floors': 4, 'campus': 'North Campus'}
        )
        block_g1, _ = HostelBlock.objects.get_or_create(
            name="Cauvery Hall (Block B)",
            defaults={'gender': 'F', 'total_floors': 4, 'campus': 'North Campus'}
        )

        # 3. Rooms
        for b in [block_b1, block_g1]:
            for floor in [1, 2, 3]:
                for num in [1, 2, 3, 4, 5]:
                    Room.objects.get_or_create(
                        block=b,
                        number=f"{'A' if b == block_b1 else 'B'}-{floor}0{num}",
                        defaults={'capacity': 2, 'floor': floor, 'is_accessible': (floor == 1 and num == 1)}
                    )
        self.stdout.write("  [OK] Hostel blocks and rooms generated")

        # 4. Versioned Questions
        questions_spec = [
            ("sleep", "When does your day usually end?", 1, 4, 5.0),
            ("wake", "And when do you usually wake up?", 1, 4, 3.0),
            ("smoke", "Where do you stand on smoking?", 1, 3, 5.0),
            ("tidy", "Your side of the room usually looks...", 1, 4, 4.0),
            ("noise", "While studying or sleeping, the room should be...", 1, 4, 4.0),
            ("study", "Where do you do your best work?", 1, 4, 3.0),
            ("guests", "Friends visiting the room are...", 1, 4, 3.0),
            ("social", "After a long day you recharge by...", 1, 4, 2.0),
        ]
        created_questions = {}
        for key, text, min_v, max_v, weight in questions_spec:
            q, _ = Question.objects.update_or_create(
                key=key,
                defaults={
                    'text': text,
                    'min_val': min_v,
                    'max_val': max_v,
                    'base_weight': weight,
                    'version': 1,
                    'is_active': True
                }
            )
            created_questions[key] = q
        self.stdout.write("  [OK] Version 1 core questions seeded")

        # 5. Real Student Users
        students_spec = [
            {
                "roll_no": "CS26B014",
                "name": "Aarav Patel",
                "email": "aarav.p@college.edu",
                "gender": "M",
                "year": "1st Year",
                "branch": "Computer Science",
                "block": block_b1,
                "role": "student",
                "avatar_hue": 270,
                "is_demo": True,
                "answers": {"sleep": 3, "wake": 3, "smoke": 1, "tidy": 4, "noise": 1, "study": 3, "guests": 1, "social": 1},
                "importance": {"sleep": 2, "wake": 2, "smoke": 3, "tidy": 3, "noise": 2, "study": 2, "guests": 2, "social": 1}
            },
            {
                "roll_no": "EE26B042",
                "name": "Rohan Verma",
                "email": "rohan.v@college.edu",
                "gender": "M",
                "year": "1st Year",
                "branch": "Electrical Engineering",
                "block": block_b1,
                "role": "student",
                "avatar_hue": 190,
                "is_demo": True,
                "answers": {"sleep": 1, "wake": 1, "smoke": 1, "tidy": 3, "noise": 1, "study": 2, "guests": 1, "social": 1},
                "importance": {"sleep": 3, "wake": 3, "smoke": 3, "tidy": 2, "noise": 3, "study": 2, "guests": 2, "social": 1}
            },
            {
                "roll_no": "ME26B105",
                "name": "Kabir Sharma",
                "email": "kabir.s@college.edu",
                "gender": "M",
                "year": "1st Year",
                "branch": "Mechanical Engineering",
                "block": block_b1,
                "role": "student",
                "avatar_hue": 25,
                "is_demo": True,
                "answers": {"sleep": 4, "wake": 4, "smoke": 2, "tidy": 1, "noise": 4, "study": 4, "guests": 4, "social": 3},
                "importance": {"sleep": 1, "wake": 1, "smoke": 1, "tidy": 1, "noise": 1, "study": 1, "guests": 3, "social": 2}
            },
            {
                "roll_no": "AR26B067",
                "name": "Dev Dixit",
                "email": "dev.d@college.edu",
                "gender": "M",
                "year": "1st Year",
                "branch": "Architecture",
                "block": block_b1,
                "role": "student",
                "avatar_hue": 45,
                "is_demo": True,
                "answers": {"sleep": 4, "wake": 3, "smoke": 1, "tidy": 2, "noise": 3, "study": 1, "guests": 3, "social": 2},
                "importance": {"sleep": 2, "wake": 1, "smoke": 2, "tidy": 1, "noise": 1, "study": 2, "guests": 2, "social": 2}
            },
            {
                "roll_no": "PH26B053",
                "name": "Ishaan Gupta",
                "email": "ishaan.g@college.edu",
                "gender": "M",
                "year": "1st Year",
                "branch": "Engineering Physics",
                "block": block_b1,
                "role": "student",
                "avatar_hue": 210,
                "is_demo": True,
                "answers": {"sleep": 3, "wake": 3, "smoke": 1, "tidy": 4, "noise": 2, "study": 3, "guests": 2, "social": 2},
                "importance": {"sleep": 2, "wake": 2, "smoke": 3, "tidy": 2, "noise": 2, "study": 2, "guests": 2, "social": 2}
            },
            {
                "roll_no": "DS26B088",
                "name": "Meera Nair",
                "email": "meera.n@college.edu",
                "gender": "F",
                "year": "1st Year",
                "branch": "Design",
                "block": block_g1,
                "role": "student",
                "avatar_hue": 330,
                "is_demo": True,
                "answers": {"sleep": 3, "wake": 3, "smoke": 1, "tidy": 4, "noise": 2, "study": 3, "guests": 2, "social": 2},
                "importance": {"sleep": 2, "wake": 2, "smoke": 3, "tidy": 2, "noise": 2, "study": 2, "guests": 2, "social": 2}
            },
            {
                "roll_no": "BT26B031",
                "name": "Ananya Roy",
                "email": "ananya.r@college.edu",
                "gender": "F",
                "year": "1st Year",
                "branch": "Biotechnology",
                "block": block_g1,
                "role": "student",
                "avatar_hue": 140,
                "is_demo": True,
                "answers": {"sleep": 2, "wake": 2, "smoke": 1, "tidy": 3, "noise": 2, "study": 3, "guests": 2, "social": 2},
                "importance": {"sleep": 2, "wake": 2, "smoke": 3, "tidy": 2, "noise": 2, "study": 2, "guests": 2, "social": 2}
            },
            {
                "roll_no": "EC26B079",
                "name": "Sanya Kapoor",
                "email": "sanya.k@college.edu",
                "gender": "F",
                "year": "1st Year",
                "branch": "Economics",
                "block": block_g1,
                "role": "student",
                "avatar_hue": 310,
                "is_demo": True,
                "answers": {"sleep": 1, "wake": 1, "smoke": 1, "tidy": 4, "noise": 1, "study": 3, "guests": 1, "social": 2},
                "importance": {"sleep": 3, "wake": 3, "smoke": 3, "tidy": 3, "noise": 3, "study": 2, "guests": 2, "social": 2}
            }
        ]

        created_students = {}
        for s in students_spec:
            user, _ = StudentUser.objects.update_or_create(
                roll_no=s["roll_no"],
                defaults={
                    "name": s["name"],
                    "email": s["email"],
                    "gender": s["gender"],
                    "year": s["year"],
                    "branch": s["branch"],
                    "block": s["block"],
                    "role": s["role"],
                    "avatar_hue": s["avatar_hue"],
                    "is_demo": s["is_demo"],
                    "consent_given": True,
                    "consent_at": timezone.now(),
                    "persona": calculate_persona(s["answers"])
                }
            )
            created_students[s["name"]] = user

            # Save responses
            for key, val in s["answers"].items():
                Response.objects.update_or_create(
                    user=user,
                    question=created_questions[key],
                    defaults={
                        'answer': val,
                        'importance': s["importance"].get(key, 2)
                    }
                )
            self.stdout.write(f"  [OK] Student {user.name} ({user.roll_no}) - the {user.persona}")

        # 6. Seed a confirmed pair between Sanya and Ananya
        sanya = created_students.get("Sanya Kapoor")
        ananya = created_students.get("Ananya Roy")
        if sanya and ananya:
            u_min = min(sanya, ananya, key=lambda u: u.id)
            u_max = max(sanya, ananya, key=lambda u: u.id)
            room_b1 = Room.objects.filter(block=block_g1, floor=1).first()
            pair, _ = Pair.objects.get_or_create(
                user_a=u_min,
                user_b=u_max,
                defaults={
                    'method': 'MUTUAL_REQUEST',
                    'status': 'ALLOTTED',
                    'room': room_b1
                }
            )
            if room_b1:
                Allotment.objects.get_or_create(room=room_b1, user=u_min)
                Allotment.objects.get_or_create(room=room_b1, user=u_max)
            self.stdout.write(f"  [OK] Confirmed Pair: {u_min.name} & {u_max.name} -> {room_b1}")

        # 7. Seed an open request: Dev -> Kabir
        dev = created_students.get("Dev Dixit")
        kabir = created_students.get("Kabir Sharma")
        if dev and kabir:
            Request.objects.get_or_create(
                from_user=dev,
                to_user=kabir,
                defaults={
                    'note': "Hey Kabir, late night jam sessions and tea? Let's pair up!",
                    'status': 'SENT',
                    'expires_at': timezone.now() + timezone.timedelta(hours=48)
                }
            )
            self.stdout.write("  [OK] Open 48h Request: Dev Dixit -> Kabir Sharma")

        self.stdout.write(self.style.SUCCESS("Database successfully initialized with real hostel configuration!"))