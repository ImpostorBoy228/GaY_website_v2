from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _


class SkinSlot(models.TextChoices):
    """Перечень заменяемых элементов интерфейса."""

    VIDEO_GRID = "VIDEO_GRID", "VIDEO_GRID"
    BASE_UI = "BASE_UI", "BASE_UI"
    GLOBAL_BG = "GLOBAL_BG", "GLOBAL_BG"
    VIDEO_PLAYER = "VIDEO_PLAYER", "VIDEO_PLAYER"
    HEADER_FOOTER = "HEADER_FOOTER", "HEADER_FOOTER"


class Skin(models.Model):
    """Шаблон (HTML/CSS/JS) одного интерфейс-слота."""

    slot = models.CharField(
        max_length=32,
        choices=SkinSlot.choices,
        db_index=True,
    )
    name = models.CharField(max_length=255)
    html = models.TextField(blank=True, default="")
    css = models.TextField(blank=True, default="")
    js = models.TextField(blank=True, default="")
    preview = models.ImageField(upload_to="skin_previews/", blank=True, null=True)
    is_default = models.BooleanField(default=False, help_text="Использовать, если у пользователя нет своего выбора.")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("slot", "name")
        ordering = ["slot", "name"]

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.get_slot_display()} – {self.name}"


class UserSkin(models.Model):
    """Какие скины принадлежат пользователю (магазин/дроп)."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    skin = models.ForeignKey(Skin, on_delete=models.CASCADE)
    owned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "skin")
        ordering = ["-owned_at"]

    def __str__(self):  # pragma: no cover
        return f"{self.user} owns {self.skin}"


class EquippedSkin(models.Model):
    """Надетый скин в конкретном слоте у пользователя."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    slot = models.CharField(max_length=32, choices=SkinSlot.choices)
    skin = models.ForeignKey(Skin, on_delete=models.CASCADE)

    class Meta:
        unique_together = ("user", "slot")

    def __str__(self):  # pragma: no cover
        return f"{self.user} ↦ {self.slot}: {self.skin}"
