"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.shortcuts import redirect
from django.urls import include, path
from django.views.generic import RedirectView

urlpatterns = [
    # Adminのログインページをallauthのログインページにリダイレクト
    # path('admin/login/', RedirectView.as_view(url='/accounts/login/', query_string=True), name='admin_login_redirect'),
    path('admin/', admin.site.urls),
    path('i18n/', include('django.conf.urls.i18n')),

    path('', lambda request: redirect('portfolio/top/', permanent=True)),  # リダイレクト設定
    # path('accounts/', include('accounts.urls')),
    path('portfolio/', include('portfolio.urls')),

    path("favicon.ico", RedirectView.as_view(url="/static/favicon.ico")),
]