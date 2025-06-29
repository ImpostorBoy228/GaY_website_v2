from pathlib import Path
from django.core.management.base import BaseCommand
from django.db import transaction
from django.contrib.auth import get_user_model

from skins.models import Skin, SkinSlot, EquippedSkin


class Command(BaseCommand):
    help = "Создаёт дефолтные скины и экипирует их всем пользователям"

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Перезаписать существующие дефолтные скины",
        )

    def handle(self, *args, **options):
        force = options.get("force")

        with transaction.atomic():
            created = 0
            for slot in SkinSlot.values:
                skin, was_created = Skin.objects.get_or_create(
                    slot=slot,
                    name="Default",
                    defaults=dict(
                        html=f"<!-- default {slot} html -->",
                        css=f"/* default {slot} css */",
                        js="",
                        is_default=True,
                    ),
                )
                if not was_created and force:
                    # Обновляем содержимое, если --force
                    skin.html = f"<!-- default {slot} html -->"
                    skin.css = f"/* default {slot} css */"
                    skin.js = ""
                    skin.is_default = True
                    skin.save()
                created += int(was_created)

            # Экипируем всем пользователям дефолтные скины
            User = get_user_model()
            users = User.objects.all()
            defaults = {
                s.slot: s for s in Skin.objects.filter(is_default=True)
            }
            for user in users:
                for slot, skin in defaults.items():
                    EquippedSkin.objects.get_or_create(
                        user=user, slot=slot, defaults=dict(skin=skin)
                    )

        self.stdout.write(
            self.style.SUCCESS(
                f"Default skins ensured for {len(SkinSlot)} slots; {created} freshly created."
            )
        )
