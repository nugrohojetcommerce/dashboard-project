from django.urls import path
from django.contrib.auth import views as auth_views
# from django.conf import settings
# from django.urls import include, path
# import settings
from .views import (
    brand_performance_api_new,
    brand_performance,
    api_gmv,
    brand_performance_new,
    api_brand_performance,
    update_profile
)
from django.views.decorators.cache import never_cache

urlpatterns = [
    path('', brand_performance_new, name="brand_performance_new"),
    path('brand_performance_api_new', brand_performance_api_new, name="brand_performance_api_new"),
    # path('',brand_performance_view),
    path('api/gmv', api_gmv),
    path('api/brand_performance',api_brand_performance),
    path('brand_performance/',brand_performance, name="brand_performance"),
    path('profile/', update_profile, name='update_profile'),
    path('profile/password/', never_cache(auth_views.PasswordChangeView.as_view(template_name='password_change.html', success_url='/profile/')), name='password_change'),
]
# if settings.DEBUG:
#     urlpatterns += [
#         path("__debug__/", include("debug_toolbar.urls")),
#     ]