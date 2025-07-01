from django.urls import path

from portfolio.views import Top, contact

app_name = 'portfolio'

urlpatterns = [
    path('top/', Top.as_view(), name='top'),
    path('contact', contact, name='contact'),
]
