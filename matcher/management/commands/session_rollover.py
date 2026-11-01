"""
Management command for end-of-year academic session rollover.
- Deactivates allotments for graduating students (4th Year by default)
- Frees their rooms
- Archives pairs
- Switches academic session

Usage: python manage.py session_rollover --graduating-year "4th Year" --new-session "2027-28"
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db.models import Q
from matcher.models import (
    StudentUser, Pair, Allotment, AuditLog, Room, AcademicSession
)


class Command(BaseCommand):
    help = 'End-of-year session rollover: deactivate graduating students, free rooms, archive pairs'

    def add_arguments(self, parser):
        parser.add_argument('--graduating-year', type=str, default='4th Year',
                          help='Year label of graduating batch (default: "4th Year")')
        parser.add_argument('--new-session', type=str, default='',
                          help='New academic session name (e.g. "2027-28")')
        parser.add_argument('--dry-run', action='store_true',
                          help='Preview changes without committing')

    def handle(self, *args, **options):
        grad_year = options['graduating_year']
        dry_run = options['dry_run']
        new_session = options['new_session']

        graduating = StudentUser.objects.filter(role='student', year=grad_year)
        grad_count = graduating.count()

        self.stdout.write(f'Found {grad_count} students in "{grad_year}"')

        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN - no changes will be made'))

        # Step 1: Deactivate allotments
        allotments = Allotment.objects.filter(user__in=graduating, is_active=True)
        allot_count = allotments.count()
        if not dry_run:
            allotments.update(is_active=False)
        self.stdout.write(f'  Deactivated {allot_count} allotments')

        # Step 2: Delete pairs involving graduating students
        pairs = Pair.objects.filter(Q(user_a__in=graduating) | Q(user_b__in=graduating))
        pair_count = pairs.count()
        if not dry_run:
            pairs.delete()
        self.stdout.write(f'  Removed {pair_count} pairs')

        # Step 3: Log
        if not dry_run:
            AuditLog.objects.create(
                actor='System (session_rollover)',
                action='SESSION_ROLLOVER',
                target=f'{grad_year} batch',
                reason=f'Deactivated {allot_count} allotments and {pair_count} pairs for {grad_count} graduating students'
            )

        # Step 4: Switch academic session if provided
        if new_session and not dry_run:
            try:
                AcademicSession.objects.filter(is_current=True).update(is_current=False)
                session, created = AcademicSession.objects.get_or_create(
                    name=new_session,
                    defaults={
                        'start_date': timezone.now().date(),
                        'end_date': timezone.now().date().replace(year=timezone.now().year + 1),
                        'is_current': True,
                    }
                )
                if not created:
                    session.is_current = True
                    session.save()
                self.stdout.write(f'  Switched to session: {new_session}')
            except Exception as e:
                self.stdout.write(self.style.WARNING(f'  Could not switch session: {e}'))

        verb = 'Would process' if dry_run else 'Processed'
        self.stdout.write(self.style.SUCCESS(
            f'{verb} session rollover: {grad_count} students, {allot_count} allotments, {pair_count} pairs'
        ))

