from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.sessions.models import Session
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from .models import CustomUser, EncryptionKey


class UserAdmin(BaseUserAdmin):
    fieldsets = (
        (None, {'fields': ('username', 'email', 'password')}),
        (_('Personal info'), {'fields': ('date_joined', 'last_login')}),
        (_('Permissions'), {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        (_('Encryption'), {'fields': ('secret_key',)}),
        (_('Login Options'), {'fields': ('use_login_by_code', 'use_one_time_password')}),  # 修正: タプルに変更
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('username', 'email', 'password1', 'password2'),
        }),
    )
    list_display = ('username', 'email', 'is_staff', 'is_superuser', 'use_login_by_code', 'use_one_time_password')  # 修正: 空の要素を削除
    search_fields = ('username', 'email')
    ordering = ('username',)

class EncryptionKeyAdmin(admin.ModelAdmin):
    list_display = ('user', 'created_at', 'expires_at', 'is_valid')
    search_fields = ('user__username', 'user__email')
    ordering = ('user',)

admin.site.register(CustomUser, UserAdmin)
admin.site.register(EncryptionKey, EncryptionKeyAdmin)

class CustomAdminSite(admin.AdminSite):
    def login(self, request, extra_context=None):
        # 管理画面へのアクセス時にallauthのログインページにリダイレクトし、ログイン後に元の管理画面に戻るようにする
        return redirect(reverse('account_login') + '?next=' + request.get_full_path())

admin_site = CustomAdminSite(name='custom_admin')

class SessionAdmin(admin.ModelAdmin):
    list_display = ['session_key', 'session_data', 'expire_date']

admin.site.register(Session, SessionAdmin)
