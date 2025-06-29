import logging
from django import template
from django.template import Template, Context
from django.utils.safestring import mark_safe

from skins.models import SkinSlot, Skin, EquippedSkin

logger = logging.getLogger('skins.skins_tags')

register = template.Library()


def _resolve_skin(slot: str, user=None):
    """Возвращает Skin для данного слота с учётом пользователя."""
    logger.info(f"[SKIN] Поиск скина для слота: {slot}, user: {getattr(user, 'username', None) if user else None}")
    # Authenticated user – пытаемся взять экипированный
    if user and getattr(user, "is_authenticated", False):
        equipped = (
            EquippedSkin.objects.select_related("skin")
            .filter(user=user, slot=slot)
            .first()
        )
        if equipped:
            logger.info(f"[SKIN] Найден экипированный скин: {equipped.skin} (slot={slot})")
            return equipped.skin
        else:
            logger.info(f"[SKIN] Нет экипированного скина для пользователя {user}")
    # Фолбек на дефолтный
    default_skin = Skin.objects.filter(slot=slot, is_default=True).order_by("id").first()
    if default_skin:
        logger.info(f"[SKIN] Используется дефолтный скин: {default_skin}")
    else:
        logger.warning(f"[SKIN] Нет дефолтного скина для слота {slot}")
    return default_skin


@register.simple_tag(takes_context=True)
def skin_html(context, slot_name):
    """Вставляет HTML выбранного скина."""
    slot = slot_name if isinstance(slot_name, str) else str(slot_name)
    skin = _resolve_skin(slot, context.request.user)
    if not skin or not skin.html:
        logger.warning(f"[SKIN] Не найден скин или пустой html для слота {slot} (user: {getattr(context.request.user, 'username', None)})")
        return ""  # pragma: no cover
    logger.info(f"[SKIN] Рендерим html скина {skin} для слота {slot}")
    tpl = Template(skin.html)
    rendered = tpl.render(Context(context))
    return mark_safe(rendered)


@register.simple_tag(takes_context=True)
def skin_css(context, slot_name):
    """Вставляет <style>…</style> выбранного скина."""

    slot = slot_name if isinstance(slot_name, str) else str(slot_name)
    skin = _resolve_skin(slot, context.request.user)
    if not skin or not skin.css:
        return ""
    return mark_safe(f"<style>{skin.css}</style>")


@register.simple_tag(takes_context=True)
def skin_js(context, slot_name):
    """Вставляет <script>…</script> выбранного скина."""

    slot = slot_name if isinstance(slot_name, str) else str(slot_name)
    skin = _resolve_skin(slot, context.request.user)
    if not skin or not skin.js:
        return ""
    return mark_safe(f"<script>{skin.js}</script>")
