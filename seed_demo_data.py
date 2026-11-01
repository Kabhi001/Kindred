"""
Kindred - Database Seeder
Populates initial hostels (BH-1..6, GH-1..6, 10 floors, 30 dual rooms each),
10 research-backed empirical roommate harmony questions, demo students with 8-digit registration numbers
(e.g. 12310266, 12519174), and staff accounts.
"""
import os
import sys
import django

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'kindred_project.settings')
django.setup()

from django.utils import timezone
from matcher.models import (
    HostelBlock, Room, StudentUser, AllotmentCalendar,
    Question, Response, Pair, Allotment, AuditLog
)
from matcher.matching import calculate_persona

def run():
    print("[+] Seeding Kindred database...")

    # 1. Calendar
    calendar = AllotmentCalendar.get_current()
    calendar.phase = 'MATCHING_OPEN'
    calendar.save()
    print("[*] Allotment calendar set to Phase 3: Matching Open")

    # 2. Hostels Specification (BH-1 to BH-6, GH-1 to GH-6)
    hostel_specs = []
    for i in range(1, 7):
        hostel_specs.append((f"BH-{i}", 'M'))
    for i in range(1, 7):
        hostel_specs.append((f"GH-{i}", 'F'))

    created_hostels = {}
    total_rooms_created = 0

    for h_name, gender in hostel_specs:
        hostel_obj, _ = HostelBlock.objects.get_or_create(
            name=h_name,
            defaults={
                'hostel_name': h_name,
                'block_name': '',
                'gender': gender,
                'total_floors': 10,
                'campus': 'Main Campus'
            }
        )
        created_hostels[h_name] = hostel_obj

        for flr in range(1, 11):
            for rm in range(1, 4):
                rm_no = f"{flr}{rm:02d}"
                _, created = Room.objects.get_or_create(
                    block=hostel_obj,
                    number=rm_no,
                    defaults={
                        'capacity': 2,
                        'floor': flr,
                        'is_accessible': (flr == 1 and rm == 1)
                    }
                )
                if created:
                    total_rooms_created += 1

    total_hostels_count = HostelBlock.objects.count()
    total_rooms_count = Room.objects.count()
    print(f"[*] Created/verified {total_hostels_count} hostels across BH-1..6 & GH-1..6")
    print(f"[*] Total rooms in database: {total_rooms_count} (strictly 2 students capacity each)")

    # 3. 10 Research-Backed Empirical Questions
    questions_data = [
        ("sleep", "On normal college days, when did you usually fall asleep?", 1, 4, 18.0),
        ("privacy", "How much do you need the room to yourself, to rest, study, or be alone?", 1, 4, 16.0),
        ("noise", "What does your room usually sound like when you're in it?", 1, 4, 12.0),
        ("tidy", "How often do you properly clean up your desk and space?", 1, 4, 12.0),
        ("guests", "How often would you want friends visiting our room?", 1, 4, 10.0),
        ("sharing", "How do you feel about people using your snacks, charger, or toiletries?", 1, 4, 8.0),
        ("intent", "What are you hoping for in a roommate?", 1, 4, 8.0),
        ("flexibility", "When room rules or plans don't go your way, you usually...", 1, 4, 6.0),
        ("temp", "How do you like your room temperature?", 1, 4, 8.0),
        ("communication", "If your roommate did something that bugged you, you'd...", 1, 4, 4.0),
    ]

    active_keys = [k for k, _, _, _, _ in questions_data]
    Question.objects.exclude(key__in=active_keys).update(is_active=False)

    for key, text, min_v, max_v, weight in questions_data:
        is_circ = (key == 'sleep')
        q, created = Question.objects.get_or_create(
            key=key,
            defaults={
                'text': text,
                'min_val': min_v,
                'max_val': max_v,
                'base_weight': weight,
                'is_circular': is_circ,
                'cycle_period': 4 if is_circ else 4,
                'is_active': True
            }
        )
        if not created:
            q.text = text
            q.base_weight = weight
            q.is_active = True
            q.save()
    print("[*] 10 research-backed lifestyle questions initialized")

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
        roll_no="10266",
        defaults={
            'name': "Kindred Administrator",
            'email': "admin10266@college.edu",
            'gender': 'M',
            'year': "Admin",
            'branch': "Hostel Affairs Board",
            'role': "admin",
            'avatar_hue': 200,
            'is_demo': False
        }
    )
    admin.set_password("kindred10266")
    admin.save()
    print("[*] Seeded staff accounts (Warden, Administrator)")

    # 5. Students with 8-digit Registration Numbers
    bh1 = created_hostels.get("BH-1") or HostelBlock.objects.filter(name="BH-1").first()
    bh2 = created_hostels.get("BH-2") or HostelBlock.objects.filter(name="BH-2").first()
    gh1 = created_hostels.get("GH-1") or HostelBlock.objects.filter(name="GH-1").first()
    gh2 = created_hostels.get("GH-2") or HostelBlock.objects.filter(name="GH-2").first()

    students_data = [
        # Male Students (Allocated to BH-1 / BH-2)
        ("12310266", "Aarav Patel", "aarav.12310266@college.edu", "M", "1st Year", "Computer Science", bh1, 270,
         {"sleep": 3, "privacy": 2, "noise": 2, "tidy": 1, "guests": 2, "sharing": 2, "intent": 3, "flexibility": 2, "communication": 1, "temp": 2},
         {"sleep": 3, "privacy": 2, "noise": 2, "tidy": 2, "guests": 2, "sharing": 2, "intent": 2, "flexibility": 2, "communication": 2, "temp": 1}),

        ("12310267", "Rohan Verma", "rohan.12310267@college.edu", "M", "1st Year", "Electrical Engineering", bh1, 190,
         {"sleep": 3, "privacy": 2, "noise": 2, "tidy": 1, "guests": 2, "sharing": 2, "intent": 3, "flexibility": 2, "communication": 1, "temp": 2},
         {"sleep": 3, "privacy": 2, "noise": 2, "tidy": 2, "guests": 2, "sharing": 2, "intent": 2, "flexibility": 2, "communication": 2, "temp": 1}),

        ("12310268", "Kabir Sharma", "kabir.12310268@college.edu", "M", "1st Year", "Mechanical Engineering", bh1, 35,
         {"sleep": 1, "privacy": 4, "noise": 3, "tidy": 3, "guests": 4, "sharing": 4, "intent": 4, "flexibility": 1, "communication": 2, "temp": 3},
         {"sleep": 2, "privacy": 2, "noise": 2, "tidy": 1, "guests": 3, "sharing": 1, "intent": 2, "flexibility": 1, "communication": 1, "temp": 2}),

        ("12310269", "Ishaan Gupta", "ishaan.12310269@college.edu", "M", "1st Year", "Physics", bh1, 220,
         {"sleep": 4, "privacy": 1, "noise": 1, "tidy": 2, "guests": 1, "sharing": 1, "intent": 1, "flexibility": 3, "communication": 3, "temp": 2},
         {"sleep": 3, "privacy": 3, "noise": 3, "tidy": 2, "guests": 2, "sharing": 2, "intent": 2, "flexibility": 2, "communication": 2, "temp": 1}),

        ("12310270", "Dev Dixit", "dev.12310270@college.edu", "M", "1st Year", "Architecture", bh1, 340,
         {"sleep": 4, "privacy": 3, "noise": 3, "tidy": 4, "guests": 3, "sharing": 3, "intent": 3, "flexibility": 2, "communication": 2, "temp": 3},
         {"sleep": 2, "privacy": 2, "noise": 2, "tidy": 1, "guests": 2, "sharing": 1, "intent": 2, "flexibility": 1, "communication": 2, "temp": 2}),

        ("12310271", "Siddharth Malhotra", "siddharth.12310271@college.edu", "M", "1st Year", "Civil Engineering", bh2, 210,
         {"sleep": 2, "privacy": 2, "noise": 2, "tidy": 2, "guests": 2, "sharing": 2, "intent": 2, "flexibility": 2, "communication": 2, "temp": 2},
         {"sleep": 2, "privacy": 2, "noise": 2, "tidy": 2, "guests": 2, "sharing": 2, "intent": 2, "flexibility": 2, "communication": 2, "temp": 1}),

        # Female Students (Allocated to GH-1)
        ("12519174", "Meera Nair", "meera.12519174@college.edu", "F", "1st Year", "Data Science", gh1, 320,
         {"sleep": 2, "privacy": 2, "noise": 1, "tidy": 1, "guests": 2, "sharing": 2, "intent": 2, "flexibility": 2, "communication": 1, "temp": 2},
         {"sleep": 2, "privacy": 2, "noise": 3, "tidy": 2, "guests": 2, "sharing": 2, "intent": 2, "flexibility": 2, "communication": 2, "temp": 1}),

        ("12519175", "Ananya Roy", "ananya.12519175@college.edu", "F", "1st Year", "Biotechnology", gh1, 160,
         {"sleep": 2, "privacy": 2, "noise": 1, "tidy": 1, "guests": 2, "sharing": 2, "intent": 3, "flexibility": 2, "communication": 1, "temp": 2},
         {"sleep": 2, "privacy": 2, "noise": 3, "tidy": 2, "guests": 2, "sharing": 2, "intent": 2, "flexibility": 2, "communication": 2, "temp": 1}),

        ("12519176", "Diya Sharma", "diya.12519176@college.edu", "F", "1st Year", "AI & Robotics", gh1, 290,
         {"sleep": 1, "privacy": 1, "noise": 1, "tidy": 2, "guests": 1, "sharing": 1, "intent": 1, "flexibility": 3, "communication": 2, "temp": 2},
         {"sleep": 3, "privacy": 3, "noise": 3, "tidy": 2, "guests": 2, "sharing": 2, "intent": 2, "flexibility": 2, "communication": 2, "temp": 1}),

        ("12519177", "Riya Sen", "riya.12519177@college.edu", "F", "1st Year", "Chemical Engineering", gh1, 10,
         {"sleep": 3, "privacy": 3, "noise": 2, "tidy": 3, "guests": 3, "sharing": 3, "intent": 3, "flexibility": 2, "communication": 2, "temp": 2},
         {"sleep": 2, "privacy": 2, "noise": 2, "tidy": 2, "guests": 2, "sharing": 2, "intent": 2, "flexibility": 2, "communication": 2, "temp": 1}),

        ("12519178", "Tanvi Patel", "tanvi.12519178@college.edu", "F", "1st Year", "Mathematics", gh1, 80,
         {"sleep": 2, "privacy": 2, "noise": 1, "tidy": 1, "guests": 1, "sharing": 2, "intent": 2, "flexibility": 2, "communication": 2, "temp": 2},
         {"sleep": 2, "privacy": 2, "noise": 3, "tidy": 2, "guests": 2, "sharing": 2, "intent": 2, "flexibility": 2, "communication": 2, "temp": 1}),
    ]

    for reg_no, name, email, g, yr, br, blk, hue, answers, importance in students_data:
        pers = calculate_persona(answers)
        student, _ = StudentUser.objects.update_or_create(
            roll_no=reg_no,
            defaults={
                'name': name,
                'email': email,
                'gender': g,
                'year': yr,
                'branch': br,
                'block': blk,
                'role': 'student',
                'avatar_hue': hue,
                'persona': pers,
                'consent_given': True,
                'consent_at': timezone.now(),
                'is_demo': False
            }
        )
        if not student.password_hash:
            student.set_password("student123")
            student.save(update_fields=['password_hash'])
        for q_key, ans_val in answers.items():
            q_obj = Question.objects.filter(key=q_key).first()
            if q_obj:
                imp_val = importance.get(q_key, 2)
                is_db = (imp_val == 3) or (q_key in ['sleep', 'privacy'] and imp_val == 3) 
                Response.objects.update_or_create(
                    user=student,
                    question=q_obj,
                    defaults={'answer': ans_val, 'importance': imp_val, 'is_dealbreaker': is_db}
                )

    print(f"[*] Seeded {len(students_data)} students with official 8-digit Registration Numbers and lifestyle surveys")
    print("[SUCCESS] Kindred seeding complete! Ready for registration and pairing.")

if __name__ == '__main__':
    run()
