from django.urls import path

from portfolio.views import Top

app_name = 'portfolio'

urlpatterns = [
    path('top/', Top.as_view(), name='top'),
]
