"""Mint invite codes from the command line.

    python manage.py makeinvite                 # one open code
    python manage.py makeinvite --count 5        # five codes
    python manage.py makeinvite --email a@b.com  # bound to one email
    python manage.py makeinvite --days 14        # expires in 14 days
"""

from __future__ import annotations

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from invites.models import Invite


class Command(BaseCommand):
    help = "Create one or more invite codes and print them."

    def add_arguments(self, parser):
        parser.add_argument("--count", type=int, default=1)
        parser.add_argument("--email", type=str, default="")
        parser.add_argument("--days", type=int, default=0, help="Expire after N days (0 = never).")
        parser.add_argument("--note", type=str, default="")

    def handle(self, *args, **opts):
        expires = timezone.now() + timedelta(days=opts["days"]) if opts["days"] else None
        for _ in range(max(1, opts["count"])):
            inv = Invite.objects.create(email=opts["email"], note=opts["note"], expires_at=expires)
            self.stdout.write(self.style.SUCCESS(inv.code))
