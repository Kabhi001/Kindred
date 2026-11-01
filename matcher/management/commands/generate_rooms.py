"""
Management command to batch-generate rooms for a hostel.
Usage: python manage.py generate_rooms --hostel "BH-1" --floors 10 --start 1 --end 20 --capacity 2
"""
from django.core.management.base import BaseCommand
from matcher.models import HostelBlock, Room


class Command(BaseCommand):
    help = 'Batch-generate rooms for a hostel'

    def add_arguments(self, parser):
        parser.add_argument('--block', '--hostel', dest='block', type=str, required=True, help='Hostel name (e.g. "BH-1")')
        parser.add_argument('--floors', type=int, default=10, help='Number of floors')
        parser.add_argument('--start', type=int, default=1, help='Starting room number per floor')
        parser.add_argument('--end', type=int, default=20, help='Ending room number per floor')
        parser.add_argument('--capacity', type=int, default=2, help='Room capacity (beds per room)')
        parser.add_argument('--room-type', type=str, default='DOUBLE', help='Room type: SINGLE, DOUBLE, TRIPLE, QUAD')

    def handle(self, *args, **options):
        hostel_name = options.get('block') or options.get('hostel')
        block = HostelBlock.objects.filter(name__icontains=hostel_name).first()
        if not block:
            self.stderr.write(self.style.ERROR(f'Hostel "{hostel_name}" not found. Available hostels:'))
            for b in HostelBlock.objects.all():
                self.stderr.write(f'  - {b.name}')
            return

        floors = options['floors']
        start = options['start']
        end = options['end']
        capacity = options['capacity']
        room_type = options['room_type']
        created = 0

        for floor in range(1, floors + 1):
            for room_num in range(start, end + 1):
                number = f"{floor}{str(room_num).zfill(2)}"
                _, was_created = Room.objects.get_or_create(
                    block=block,
                    number=number,
                    defaults={
                        'capacity': capacity,
                        'floor': floor,
                        'room_type': room_type,
                        'status': 'AVAILABLE',
                    }
                )
                if was_created:
                    created += 1

        self.stdout.write(self.style.SUCCESS(f'Created {created} rooms in {block.name} ({floors} floors, rooms {start}-{end})'))

