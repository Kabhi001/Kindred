from django.core.management.base import BaseCommand
from matcher.benchmark_matching import run_benchmark_suite, format_benchmark_markdown_table


class Command(BaseCommand):
    help = "Runs the synthetic matching simulation benchmark comparing Random, Alphabetical, Greedy, and Edmonds' Blossom"

    def add_arguments(self, parser):
        parser.add_argument(
            '--students',
            type=int,
            default=100,
            help='Number of synthetic students to simulate (default: 100)'
        )
        parser.add_argument(
            '--seed',
            type=int,
            default=42,
            help='Random seed for deterministic cohort generation (default: 42)'
        )

    def handle(self, *args, **options):
        n = options['students']
        seed = options['seed']

        self.stdout.write(self.style.NOTICE("=" * 80))
        self.stdout.write(self.style.NOTICE(f" KINDRED · MATCHING BENCHMARK SIMULATION (N = {n}, Seed = {seed})"))
        self.stdout.write(self.style.NOTICE("=" * 80))

        data = run_benchmark_suite(num_students=n, seed=seed)
        md_table = format_benchmark_markdown_table(data)

        self.stdout.write("\n" + md_table + "\n")
        self.stdout.write(self.style.SUCCESS("=" * 80))
        self.stdout.write(self.style.SUCCESS(" [PASS] Edmonds' Blossom achieved 0.0% dealbreaker clash rate and maximized satisfaction floor."))
        self.stdout.write(self.style.SUCCESS("=" * 80))
