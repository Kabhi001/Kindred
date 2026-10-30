from django.core.management.base import BaseCommand
from django.utils import timezone
from matcher.models import (
    HostelBlock, Room, StudentUser, AllotmentCalendar,
    Question, Response, Request, Pair, Allotment, AuditLog
)
from matcher.matching import calculate_persona


class Command(BaseCommand):
    help = "Seed database with production hostel data (BH-1..6, GH-1..6, 3 blocks each, 10 floors, 30 dual rooms), questions, calendar, and real students with 8-digit registration numbers"

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

        # 2. Hostels & Blocks Specification
        # BH-1 to BH-6 (Boys Hostels) and GH-1 to GH-6 (Girls Hostels)
        # Each hostel has 3 blocks: Block-A, Block-B, Block-C
        # Each block is a 10-floor tower containing 30 rooms (3 rooms per floor)
        # Each room is strictly Dual student occupancy (capacity = 2)
        hostel_specs = []
        for i in range(1, 7):
            hostel_specs.append((f"BH-{i}", 'M'))
        for i in range(1, 7):
            hostel_specs.append((f"GH-{i}", 'F'))

        block_letters = ['Block-A', 'Block-B', 'Block-C']
        created_blocks = {}
        total_rooms_created = 0

        for h_name, gender in hostel_specs:
            for b_letter in block_letters:
                full_name = f"{h_name} - {b_letter}"
                block_obj, _ = HostelBlock.objects.get_or_create(
                    name=full_name,
                    defaults={
                        'hostel_name': h_name,
                        'block_name': b_letter,
                        'gender': gender,
                        'total_floors': 10,
                        'campus': 'Main Campus'
                    }
                )
                created_blocks[full_name] = block_obj

                # 30 rooms: 10 floors x 3 rooms per floor
                for flr in range(1, 11):
                    for rm in range(1, 4):
                        rm_no = f"{flr}{rm:02d}"
                        _, created = Room.objects.get_or_create(
                            block=block_obj,
                            number=rm_no,
                            defaults={
                                'capacity': 2,
                                'floor': flr,
                                'is_accessible': (flr == 1 and rm == 1)
                            }
                        )
                        if created:
                            total_rooms_created += 1

        self.stdout.write(f"  [OK] Hostel blocks (36 total) and dual rooms initialized across BH-1..6 & GH-1..6")

        # 3. Versioned Questions
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
            is_circ = key in ['sleep', 'wake']
            q, _ = Question.objects.update_or_create(
                key=key,
                defaults={
                    'text': text,
                    'min_val': min_v,
                    'max_val': max_v,
                    'base_weight': weight,
                    'version': 1,
                    'is_circular': is_circ,
                    'cycle_period': 4 if is_circ else 4,
                    'is_active': True
                }
            )
            created_questions[key] = q
        self.stdout.write("  [OK] Version 1 core questions seeded")

        # 4. Staff Accounts
        warden, _ = StudentUser.objects.get_or_create(
            roll_no="WARDEN-01",
            defaults={
                'name': "Dr. V. K. Sharma",
                'email': "warden.sharma@college.edu",
                'gender': 'M',
                'year': "Faculty",
                'branch': "Administration",
                'role': "warden",
                'avatar_hue': 45,
                'is_demo': False
            }
        )
        warden.set_password("warden123")
        warden.save()

        admin, _ = StudentUser.objects.get_or_create(
            roll_no="ADMIN-01",
            defaults={
                'name': "Prof. Anjali Verma",
                'email': "allotment.admin@college.edu",
                'gender': 'F',
                'year': "Admin",
                'branch': "Hostel Affairs Board",
                'role': "admin",
                'avatar_hue': 200,
                'is_demo': False
            }
        )
        admin.set_password("admin123")
        admin.save()
        self.stdout.write("  [OK] Seeded staff accounts (Warden, Admin)")

        # 5. Real Student Users with 8-digit Registration Numbers
        bh1_a = created_blocks.get("BH-1 - Block-A")
        bh1_b = created_blocks.get("BH-1 - Block-B")
        bh1_c = created_blocks.get("BH-1 - Block-C")
        bh2_a = created_blocks.get("BH-2 - Block-A")

        gh1_a = created_blocks.get("GH-1 - Block-A")
        gh1_b = created_blocks.get("GH-1 - Block-B")
        gh1_c = created_blocks.get("GH-1 - Block-C")

        students_spec = [
            {
                "roll_no": "12310266",
                "name": "Aarav Patel",
                "email": "aarav.12310266@college.edu",
                "gender": "M",
                "year": "1st Year",
                "branch": "Computer Science",
                "block": bh1_a,
                "role": "student",
                "avatar_hue": 270,
                "is_demo": True,
                "answers": {"sleep": 3, "wake": 3, "smoke": 1, "tidy": 4, "noise": 1, "study": 3, "guests": 1, "social": 1},
                "importance": {"sleep": 2, "wake": 2, "smoke": 3, "tidy": 3, "noise": 2, "study": 2, "guests": 2, "social": 1}
            },
            {
                "roll_no": "12310267",
                "name": "Rohan Verma",
                "email": "rohan.12310267@college.edu",
                "gender": "M",
                "year": "1st Year",
                "branch": "Electrical Engineering",
                "block": bh1_a,
                "role": "student",
                "avatar_hue": 190,
                "is_demo": True,
                "answers": {"sleep": 1, "wake": 1, "smoke": 1, "tidy": 3, "noise": 1, "study": 2, "guests": 1, "social": 1},
                "importance": {"sleep": 3, "wake": 3, "smoke": 3, "tidy": 2, "noise": 3, "study": 2, "guests": 2, "social": 1}
            },
            {
                "roll_no": "12310268",
                "name": "Kabir Sharma",
                "email": "kabir.12310268@college.edu",
                "gender": "M",
                "year": "1st Year",
                "branch": "Mechanical Engineering",
                "block": bh1_b,
                "role": "student",
                "avatar_hue": 25,
                "is_demo": True,
                "answers": {"sleep": 4, "wake": 4, "smoke": 2, "tidy": 1, "noise": 4, "study": 4, "guests": 4, "social": 3},
                "importance": {"sleep": 1, "wake": 1, "smoke": 1, "tidy": 1, "noise": 1, "study": 1, "guests": 3, "social": 2}
            },
            {
                "roll_no": "12310269",
                "name": "Ishaan Gupta",
                "email": "ishaan.12310269@college.edu",
                "gender": "M",
                "year": "1st Year",
                "branch": "Physics",
                "block": bh1_b,
                "role": "student",
                "avatar_hue": 210,
                "is_demo": True,
                "answers": {"sleep": 3, "wake": 3, "smoke": 1, "tidy": 4, "noise": 2, "study": 3, "guests": 2, "social": 2},
                "importance": {"sleep": 2, "wake": 2, "smoke": 3, "tidy": 2, "noise": 2, "study": 2, "guests": 2, "social": 2}
            },
            {
                "roll_no": "12310270",
                "name": "Dev Dixit",
                "email": "dev.12310270@college.edu",
                "gender": "M",
                "year": "1st Year",
                "branch": "Architecture",
                "block": bh1_c,
                "role": "student",
                "avatar_hue": 45,
                "is_demo": True,
                "answers": {"sleep": 4, "wake": 3, "smoke": 1, "tidy": 2, "noise": 3, "study": 1, "guests": 3, "social": 2},
                "importance": {"sleep": 2, "wake": 1, "smoke": 2, "tidy": 1, "noise": 1, "study": 2, "guests": 2, "social": 2}
            },
            {
                "roll_no": "12310271",
                "name": "Siddharth Malhotra",
                "email": "siddharth.12310271@college.edu",
                "gender": "M",
                "year": "1st Year",
                "branch": "Civil Engineering",
                "block": bh2_a,
                "role": "student",
                "avatar_hue": 210,
                "is_demo": True,
                "answers": {"sleep": 2, "wake": 2, "smoke": 1, "tidy": 3, "noise": 2, "study": 2, "guests": 2, "social": 2},
                "importance": {"sleep": 2, "wake": 2, "smoke": 3, "tidy": 2, "noise": 2, "study": 2, "guests": 2, "social": 2}
            },
            {
                "roll_no": "12519174",
                "name": "Meera Nair",
                "email": "meera.12519174@college.edu",
                "gender": "F",
                "year": "1st Year",
                "branch": "Data Science",
                "block": gh1_a,
                "role": "student",
                "avatar_hue": 330,
                "is_demo": True,
                "answers": {"sleep": 3, "wake": 3, "smoke": 1, "tidy": 4, "noise": 2, "study": 3, "guests": 2, "social": 2},
                "importance": {"sleep": 2, "wake": 2, "smoke": 3, "tidy": 2, "noise": 2, "study": 2, "guests": 2, "social": 2}
            },
            {
                "roll_no": "12519175",
                "name": "Ananya Roy",
                "email": "ananya.12519175@college.edu",
                "gender": "F",
                "year": "1st Year",
                "branch": "Biotechnology",
                "block": gh1_a,
                "role": "student",
                "avatar_hue": 140,
                "is_demo": True,
                "answers": {"sleep": 2, "wake": 2, "smoke": 1, "tidy": 3, "noise": 2, "study": 3, "guests": 2, "social": 2},
                "importance": {"sleep": 2, "wake": 2, "smoke": 3, "tidy": 2, "noise": 2, "study": 2, "guests": 2, "social": 1}
            },
            {
                "roll_no": "12519176",
                "name": "Diya Sharma",
                "email": "diya.12519176@college.edu",
                "gender": "F",
                "year": "1st Year",
                "branch": "AI & Robotics",
                "block": gh1_b,
                "role": "student",
                "avatar_hue": 290,
                "is_demo": True,
                "answers": {"sleep": 1, "wake": 1, "smoke": 1, "tidy": 3, "noise": 1, "study": 2, "guests": 1, "social": 1},
                "importance": {"sleep": 2, "wake": 2, "smoke": 3, "tidy": 2, "noise": 2, "study": 2, "guests": 2, "social": 1}
            },
            {
                "roll_no": "12519177",
                "name": "Riya Sen",
                "email": "riya.12519177@college.edu",
                "gender": "F",
                "year": "1st Year",
                "branch": "Chemical Engineering",
                "block": gh1_b,
                "role": "student",
                "avatar_hue": 10,
                "is_demo": True,
                "answers": {"sleep": 3, "wake": 2, "smoke": 1, "tidy": 2, "noise": 2, "study": 2, "guests": 3, "social": 3},
                "importance": {"sleep": 1, "wake": 1, "smoke": 3, "tidy": 2, "noise": 1, "study": 2, "guests": 2, "social": 2}
            },
            {
                "roll_no": "12519178",
                "name": "Tanvi Patel",
                "email": "tanvi.12519178@college.edu",
                "gender": "F",
                "year": "1st Year",
                "branch": "Mathematics",
                "block": gh1_c,
                "role": "student",
                "avatar_hue": 80,
                "is_demo": True,
                "answers": {"sleep": 2, "wake": 2, "smoke": 1, "tidy": 4, "noise": 1, "study": 3, "guests": 1, "social": 1},
                "importance": {"sleep": 2, "wake": 2, "smoke": 3, "tidy": 3, "noise": 2, "study": 2, "guests": 1, "social": 1}
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
                    "is_demo": False,
                    "consent_given": True,
                    "consent_at": timezone.now(),
                    "persona": calculate_persona(s["answers"])
                }
            )
            if not user.password_hash:
                user.set_password("student123")
                user.save(update_fields=['password_hash'])
            created_students[s["name"]] = user

            # Save responses
            for key, val in s["answers"].items():
                imp_val = s["importance"].get(key, 2)
                is_db = (imp_val == 3) or (key == 'smoke' and val == 1)
                Response.objects.update_or_create(
                    user=user,
                    question=created_questions[key],
                    defaults={
                        'answer': val,
                        'importance': imp_val,
                        'is_dealbreaker': is_db
                    }
                )
            self.stdout.write(f"  [OK] Student {user.name} ({user.roll_no}) - the {user.persona}")

        # 6. Seed an open request: Dev Dixit -> Kabir Sharma
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