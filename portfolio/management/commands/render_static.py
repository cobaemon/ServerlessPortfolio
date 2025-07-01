from django.core.management.base import BaseCommand
from django.template.loader import render_to_string
from django.conf import settings
from pathlib import Path

class Command(BaseCommand):
    help = 'Render portfolio_base.html to a static index.html'

    def handle(self, *args, **options):
        output_dir = Path(settings.STATIC_ROOT)
        output_dir.mkdir(parents=True, exist_ok=True)
        html = render_to_string('portfolio_base.html')
        (output_dir / 'index.html').write_text(html)
        self.stdout.write(self.style.SUCCESS('Rendered static index.html'))

