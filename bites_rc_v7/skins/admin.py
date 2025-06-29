from django.contrib import admin

from .models import Skin, UserSkin, EquippedSkin

@admin.register(Skin)
class SkinAdmin(admin.ModelAdmin):
    list_display = ("id", "slot", "name", "is_default", "created_at")
    list_filter = ("slot", "is_default")
    search_fields = ("name", "html", "css")
    ordering = ("slot", "name")
    readonly_fields = ("created_at",)

@admin.register(UserSkin)
class UserSkinAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "skin", "owned_at")
    list_filter = ("user", "skin__slot")
    search_fields = ("user__username", "skin__name")
    ordering = ("-owned_at",)
    readonly_fields = ("owned_at",)

@admin.register(EquippedSkin)
class EquippedSkinAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "slot", "skin")
    list_filter = ("user", "slot")
    search_fields = ("user__username", "skin__name")
    ordering = ("user", "slot")
