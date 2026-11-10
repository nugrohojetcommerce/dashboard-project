from django.urls import path
from . import views

app_name = 'double_date'

urlpatterns = [
    path('', views.index_view, name='index'),
    path('api/data/', views.api_campaign_data, name='api_data'),
]

