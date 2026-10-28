from django.urls import path
from django.contrib.auth import views as auth_views
# from django.conf import settings
# from django.urls import include, path
# import settings
from .views import (
    brand_performance_api_new,
    brand_performance,
    brand_performance_api,
    # api_gmv,
    brand_performance_new,
    # api_brand_performance,
    consolidate_sales,
    consolidate_sales_api,
    update_profile,
    change_password_api,
    ads_dashboard_api,
    ads_dashboard,
    insight_dashboard_api,
    insight_dashboard,
    tiktok_shop_callback,
)
from django.views.decorators.cache import never_cache
from django.views.generic import RedirectView


urlpatterns = [
    # =============== contoh
    path('logout/', auth_views.LogoutView.as_view(next_page='/'), name='logout'),
    path('', RedirectView.as_view(url='/brand_performance_v2/', permanent=False), name="home_redirect"),
    path('brand_performance_api_new', brand_performance_api_new, name="brand_performance_api_new"),
    # path('',brand_performance_view),
    # path('api/gmv', api_gmv),
    # path('api/brand_performance',api_brand_performance),
    path('brand_performance/',brand_performance, name="brand_performance"),
    path('profile/', update_profile, name='update_profile'),
    path('api/change-password/', change_password_api, name='change_password_api'),
    path('profile/password/', never_cache(auth_views.PasswordChangeView.as_view(template_name='password_change.html', success_url='/profile/')), name='custom_password_change'),
    path('logout/', auth_views.LogoutView.as_view(next_page='/'), name='logout'),
    # path('brand_performance/',brand_performance, name="brand_performance"),
    path('brand_performance_api/',brand_performance_api, name="brand_performance_api"),

    path('consolidate_sales/', consolidate_sales, name="consolidate_sales"),
    path('consolidate_sales_api/',consolidate_sales_api,name="consolidate_sales_api"),

    path('ads_dashboard/',ads_dashboard,name="ads_dashboard"),
    path('ads_dashboard_api/',ads_dashboard_api,name="ads_dashboard_api"),

    path('dashboard_insight/',insight_dashboard,name="insight_dashboard"),
    path('dashboard_insight_api/',insight_dashboard_api,name="insight_dashboard_api"),

    path('product_mapping/', RedirectView.as_view(url='/data_management/product_mapping/', permanent=False)),
    path('tiktokshop/callback/', tiktok_shop_callback, name='tiktok_shop_callback'),

]
