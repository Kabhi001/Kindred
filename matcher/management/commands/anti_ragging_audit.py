"""
Management command to audit anti-ragging compliance.
Checks for any freshman-senior roommate pairings.

Usage: python manage.py anti_ragging_audit
"""
from django.core.management.base import BaseCommand
from matcher.models import Pair, AuditLog


class Command(BaseCommand):
    help = 'Audit roommate pairs for anti-ragging compliance (freshman-senior isolation)'

    def handle(self, *args, **options):
        violations = []
        pairs = Pair.objects.select_related('user_a', 'user_b').all()

        for p in pairs:
            a_fresh = getattr(p.user_a, 'is_freshman', False) or (p.user_a.year in ['1st Year', 'First Year'])
            b_fresh = getattr(p.user_b, 'is_freshman', False) or (p.user_b.year in ['1st Year', 'First Year'])

            if a_fresh != b_fresh:
                violations.append(p)
                self.stdout.write(self.style.WARNING(
                    f'  VIOLATION: {p.user_a.name} ({"Freshman" if a_fresh else p.user_a.year}) '
                    f'paired with {p.user_b.name} ({"Freshman" if b_fresh else p.user_b.year}) '
                    f'in Room {p.room.number if p.room else "Unassigned"}'
                ))

        if violations:
            self.stdout.write(self.style.ERROR(f'\n{len(violations)} anti-ragging violation(s) detected!'))
            AuditLog.objects.create(
                actor='System (anti_ragging_audit)',
                action='ANTI_RAGGING_VIOLATIONS_FOUND',
                target=f'{len(violations)} pairs',
                reason='Automated anti-ragging audit found cross-year roommate pairings'
            )
        else:
            self.stdout.write(self.style.SUCCESS('All roommate pairings are strictly anti-ragging compliant.'))

