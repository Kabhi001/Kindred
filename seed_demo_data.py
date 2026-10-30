"""
Kindred - Database Seeder
Populates initial hostel blocks, rooms, questions, demo students, and staff accounts.
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

def run():
    print("[+] Seeding Kindred database...")

    # 1. Calendar
    calendar = AllotmentCalendar.get_current()
    calendar.phase = 'MATCHING_OPEN'
    calendar.save()
    print("[*] Allotment calendar set to Phase 3: Matching Open")

    # 2. Hostel Blocks
    mandakini, _ = HostelBlock.objects.get_or_create(
        name="Mandakini Hall",
        defaults={'gender': 'M', 'total_floors': 4, 'campus': 'North Campus'}
    )
    ganga, _ = HostelBlock.objects.get_or_create(
        name="Ganga Hall",
        defaults={'gender': 'F', 'total_floors': 4, 'campus': 'South Campus'}
    )
    print("[*] Hostel blocks created: Mandakini Hall (Boys), Ganga Hall (Girls)")

    # 3. Rooms
    for b in [mandakini, ganga]:
        for flr in range(1, 4):
            for rm in range(1, 6):
                rm_no = f"{b.name[0]}-{flr}0{rm}"
                Room.objects.get_or_create(
                    block=b,
                    number=rm_no,
                    defaults={'capacity': 2, 'floor': flr, 'is_accessible': flr == 1}
                )
    print(f"[*] Created 30 residential rooms across {HostelBlock.objects.count()} blocks")

    # 4. Standard Questions
    questions_data = [
        ("sleep", "When does your day usually end?", 1, 4, 5.0),
        ("wake", "And when do you usually wake up?", 1, 4, 3.0),
        ("smoke", "Where do you stand on smoking?", 1, 3, 5.0),
        ("tidy", "Your side of the room usually looks...", 1, 4, 4.0),
        ("noise", "While you study or sleep, the room should be...", 1, 4, 4.0),
        ("study", "Where do you do your best work?", 1, 4, 3.0),
        ("guests", "Friends visiting the room are...", 1, 4, 3.0),
        ("social", "After a long day you recharge by...", 1, 4, 2.0),
    ]
    for key, text, min_v, max_v, weight in questions_data:
        Question.objects.get_or_create(
            key=key,
            defaults={'text': text, 'min_val': min_v, 'max_val': max_v, 'base_weight': weight, 'is_active': True}
        )
    print("[*] 8 lifestyle questions initialized")

    # 5. Staff Accounts
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
            'is_demo': True
        }
    )
    warden.set_password("warden123")
    warden.save()

    caretaker, _ = StudentUser.objects.get_or_create(
        roll_no="CARETAKER-01",
        defaults={
            'name': "Ramesh Kumar",
            'email': "ramesh.caretaker@college.edu",
            'gender': 'M',
            'year': "Staff",
            'branch': "Hostel Facility Desk",
            'role': "caretaker",
            'avatar_hue': 140,
            'is_demo': True
        }
    )
    caretaker.set_password("caretaker123")
    caretaker.save()

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
            'is_demo': True
        }
    )
    admin.set_password("admin123")
    admin.save()
    print("[*] Seeded staff accounts (Warden, Caretaker, Administrator)")

    # 6. Students
    students_data = [
        ("CS26B014", "Aarav Patel", "aarav@college.edu", "M", "1st Year", "CSE", mandakini, 270, "Midnight Curator",
         {"sleep": 3, "wake": 2, "smoke": 1, "tidy": 4, "noise": 2, "study": 1, "guests": 2, "social": 1},
         {"sleep": 2, "wake": 1, "smoke": 3, "tidy": 2, "noise": 2, "study": 1, "guests": 2, "social": 1}),

        ("EE26B042", "Rohan Verma", "rohan@college.edu", "M", "1st Year", "EE", mandakini, 190, "Midnight Curator",
         {"sleep": 3, "wake": 2, "smoke": 1, "tidy": 4, "noise": 2, "study": 1, "guests": 2, "social": 2},
         {"sleep": 2, "wake": 1, "smoke": 3, "tidy": 2, "noise": 2, "study": 1, "guests": 2, "social": 1}),

        ("ME26B105", "Kabir Sharma", "kabir@college.edu", "M", "1st Year", "ME", mandakini, 25, "Dawn Host",
         {"sleep": 1, "wake": 1, "smoke": 2, "tidy": 2, "noise": 3, "study": 3, "guests": 3, "social": 3},
         {"sleep": 2, "wake": 2, "smoke": 1, "tidy": 1, "noise": 1, "study": 2, "guests": 2, "social": 2}),

        ("DS26B088", "Meera Nair", "meera@college.edu", "F", "1st Year", "Data Science", ganga, 320, "Daylight Scholar",
         {"sleep": 2, "wake": 2, "smoke": 1, "tidy": 3, "noise": 1, "study": 3, "guests": 2, "social": 1},
         {"sleep": 2, "wake": 2, "smoke": 3, "tidy": 2, "noise": 3, "study": 2, "guests": 2, "social": 1}),

        ("BT26B031", "Ananya Roy", "ananya@college.edu", "F", "1st Year", "Biotech", ganga, 160, "Daylight Scholar",
         {"sleep": 2, "wake": 2, "smoke": 1, "tidy": 4, "noise": 1, "study": 3, "guests": 2, "social": 2},
         {"sleep": 2, "wake": 2, "smoke": 3, "tidy": 2, "noise": 3, "study": 2, "guests": 2, "social": 1}),

        ("PH26B053", "Ishaan Gupta", "ishaan@college.edu", "M", "1st Year", "Physics", mandakini, 220, "Midnight Sage",
         {"sleep": 4, "wake": 3, "smoke": 1, "tidy": 3, "noise": 1, "study": 1, "guests": 1, "social": 1},
         {"sleep": 2, "wake": 1, "smoke": 3, "tidy": 2, "noise": 3, "study": 2, "guests": 1, "social": 1}),

        ("AR26B067", "Dev Dixit", "dev@college.edu", "M", "1st Year", "Architecture", mandakini, 340, "Moonlit Dreamer",
         {"sleep": 4, "wake": 3, "smoke": 1, "tidy": 1, "noise": 3, "study": 4, "guests": 3, "social": 3},
         {"sleep": 1, "wake": 1, "smoke": 1, "tidy": 1, "noise": 1, "study": 1, "guests": 2, "social": 2}),
    ]

    for roll, name, email, g, yr, br, blk, hue, pers, answers, importance in students_data:
        student, _ = StudentUser.objects.get_or_create(
            roll_no=roll,
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
                'is_demo': True
            }
        )
        for q_key, ans_val in answers.items():
            q_obj = Question.objects.filter(key=q_key).first()
            if q_obj:
                imp_val = importance.get(q_key, 2)
                Response.objects.update_or_create(
                    user=student,
                    question=q_obj,
                    defaults={'answer': ans_val, 'importance': imp_val}
                )

    print("[*] Seeded 7 students with completed 8-factor lifestyle surveys")
    print("[SUCCESS] Kindred seeding complete! Ready to launch.")

if __name__ == '__main__':
    run()
