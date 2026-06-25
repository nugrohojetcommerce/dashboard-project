from __future__ import annotations

from datetime import date
from typing import Any
from django.core.cache import cache

from django.contrib.auth.decorators import login_required
from django.db.models import QuerySet, Sum, Q
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render, redirect
from django.utils.dateparse import parse_date

from dashboard.models import (
    OrderMartDashboardBrandDF as OrderMart,
    User, UserBrand
)
import time
from dashboard.services.dashboard_performance import get_cards
from django.contrib import messages
from .forms import UserProfileForm

from .services.dashboard_performance import (
    filter_data,
    get_brand_performance_data,
    get_nmv_line,
    get_order_mart_dashboard_brand,
)
from .services.gmv_services import get_gmv
from functools import reduce
import operator


# def get_user_brands(user: User) -> list[str]:
#     return list(
#         user.userbrand_set.values_list(
#             "brand__name",
#             flat=True,
#         ).distinct()
#     )

def brand_filter(queryset: QuerySet, brand_list: list[str]) -> QuerySet:
    """Filters a queryset using case-insensitive partial matching (OR logic)"""
    if not brand_list:
        return queryset.none()
    conditions = [Q(brand__istartswith=brand) for brand in brand_list]
    return queryset.filter(reduce(operator.or_, conditions))

def get_base_queryset(
    user: User,
) -> QuerySet[OrderMart]:
    # return OrderMart.objects.filter(brand__in=get_user_brands(user))
    user_brands = get_user_brands(user)
    return brand_filter(OrderMart.objects.all(), user_brands)


@login_required
def brand_performance_new(
    request: HttpRequest,
) -> HttpResponse:
    # queryset = get_base_queryset(request.user)
    today = date.today()
    context: dict[str, Any] = {
        # "brands": list(
        #     queryset.values_list(
        #         "brand",
        #         flat=True,
        #     )
        #     .distinct()
        #     .order_by("brand")
        # ),
        # "brands" : sorted(get_user_brands(request.user)),
        "brands": get_brand_variants(request.user),
        # "platforms": list(
        #     queryset.values_list(
        #         "platform",
        #         flat=True,
        #     )
        #     .distinct()
        #     .order_by("platform")
        # ),
        "platforms": list(
            OrderMart.objects.values_list(
                "platform",
                flat=True,
            )
            .distinct()
        ),
        "start_date": today.replace(day=1).isoformat(),
        "end_date": today.isoformat(),
    }

    return render(
        request,
        "brand_performance_new.html",
        context,
    )


from functools import lru_cache

@lru_cache(maxsize=256)
def get_user_brands_cached(user_id: int):
    return tuple(
        UserBrand.objects.filter(user_id=user_id)
        .values_list("brand__name", flat=True)
    )

def get_user_brands(user: User) -> list[str]:
    return list(get_user_brands_cached(user.id))

@lru_cache(maxsize=1)
def get_all_brand_variants():
    return list(
        OrderMart.objects
        .values_list("brand", flat=True)
        .distinct()
    )

# def get_brand_variants(user: User):
#     user_brands = get_user_brands(user)

#     conditions = [
#         Q(brand__istartswith=brand)
#         for brand in user_brands
#     ]

#     return list(
#         OrderMart.objects.filter(
#             reduce(operator.or_, conditions)
#         )
#         .values_list("brand", flat=True)
#         .distinct()
#     )

# def get_brand_variants(user):
#     cache_key = f"brand_variants_{user.id}"

#     brands = cache.get(cache_key)

#     if brands is None:
#         user_brands = get_user_brands(user)

#         conditions = [
#             Q(brand__istartswith=brand)
#             for brand in user_brands
#         ]

#         brands = list(
#             OrderMart.objects.filter(
#                 reduce(operator.or_, conditions)
#             )
#             .values_list("brand", flat=True)
#             .distinct()
#             .order_by("brand")
#         )

#         cache.set(cache_key, brands, 3600)

#     return brands

def get_brand_variants(user):
    user_brands = get_user_brands(user)

    return sorted([
        brand
        for brand in get_all_brand_variants()
        if any(
            brand.lower().startswith(user_brand.lower())
            for user_brand in user_brands
        )
    ])

@login_required
def brand_performance_api_new(
    request: HttpRequest,
) -> JsonResponse:

    today = date.today()
    start_date = parse_date(request.GET.get("start_date", ""))

    end_date = parse_date(request.GET.get("end_date", ""))

    if start_date is None:
        start_date = today.replace(day=1)

    if end_date is None:
        end_date = today

    selected_brands = request.GET.getlist("brand")
    selected_platforms = request.GET.getlist("platform")
    # queryset = get_base_queryset(request.user).filter(
    #     date__range=[
    #         start_date,
    #         end_date,
    #     ]
    # )
    t1 = time.time()
    queryset = OrderMart.objects.filter(
        date__range=[
            start_date,
            end_date,
        ]
    )
    print("Execution Time all object:")
    # print(queryset.query)
    # print(f"execute in :{time.time()-t1} s")
    # queryset = brand_filter(
    #     queryset,
    #     get_user_brands(request.user)
    # )
    print("Execution Time start brand:")
    # print(queryset.query)
    print(f"execute in :{time.time()-t1} s")
    if selected_brands:
        queryset = queryset.filter(brand__in=selected_brands)
        print("Execution Time brand filter:")
        # print(queryset.query)
        print(f"execute in :{time.time()-t1} s")
        # queryset = brand_filter(queryset,selected_brands)
    else:
        queryset = brand_filter(
        queryset,
        get_user_brands(request.user)
    )

    
    if selected_platforms:
        queryset = queryset.filter(platform__in=selected_platforms)
        print("Execution Time platform filter:")
        # print(queryset.query)
        print(f"execute in :{time.time()-t1} s")
    print(
        queryset.explain(
            analyze=True,
            verbose=True,
            buffers=True,
        )
    )
    cards = queryset.aggregate(
        total_nmv=Sum("nmv"),
        total_gmv=Sum("gmv"),
    )
    print("Execution Time card :")
    # print(queryset.query)
    print(f"execute in :{time.time()-t1} s")

    trend = [
        {
            "date": row["date"].isoformat(),
            "nmv": float(row["nmv"] or 0),
            "gmv": float(row["gmv"] or 0),
        }
        for row in (
            queryset.values("date")
            .annotate(
                nmv=Sum("nmv"),
                gmv=Sum("gmv"),
            )
            .order_by("date")
        )
    ]
    return JsonResponse(
        {
            "cards": {
                "total_nmv": float(cards["total_nmv"] or 0),
                "total_gmv": float(cards["total_gmv"] or 0),
            },
            "trend": trend,
        }
    )


@login_required
def dashboard_view(request):
    brands = list(request.user.userbrand_set.values_list("brand__name", flat=True))

    return render(request, "dashboard.html", {"brands": brands})


@login_required
def api_gmv(request):
    brands = list(request.user.userbrand_set.values_list("brand__name", flat=True))

    data = get_gmv(request.GET.get("start_date"), request.GET.get("end_date"), brands)

    return JsonResponse(data, safe=False)


@login_required
def brand_performance_view(request):
    brands: list[str] = list(
        request.user.userbrand_set.select_related("brand")
        .values_list("brand__name", flat=True)
        .order_by("brand__name")
        .distinct()
    )

    return render(request, "brand_performance.html", {"brands": brands})


@login_required
def brand_performance(request):

    start_date = request.GET.get("start_date")
    end_date = request.GET.get("end_date")

    selected_brands = request.GET.getlist("brand")
    selected_platforms = request.GET.getlist("platform")

    context = get_brand_performance_data(
        user=request.user,
        start_date=start_date,
        end_date=end_date,
        selected_brands=selected_brands,
        selected_platforms=selected_platforms,
    )
    return render(request, "brand_performance.html", context)


@login_required
def api_brand_performance(request, order_data=None):
    # 1. Ambil semua list brand yang di-assign ke user ini
    user_brands = list(request.user.userbrand_set.values_list("brand__name", flat=True))

    # 2. Tangkap parameter filter dari AJAX request GET
    start_date = request.GET.get("start_date")
    end_date = request.GET.get("end_date")
    selected_brand = request.GET.get("brand", "all")
    selected_platform = request.GET.get("platform", "all")

    # start_date = "2026-01-01"
    # end_date = "2026-01-31"
    # selected_brand = "Loreal"

    # 3. Logika penentuan brand yang akan di-query
    # Jika user memilih brand spesifik dan brand tersebut ada di dalam hak aksesnya
    if selected_brand != "all":
        if selected_brand in user_brands:
            brands_to_query = [selected_brand]
        else:
            # Antisipasi jika user nembak brand yang bukan hak miliknya lewat API
            return JsonResponse({"error": "Unauthorized brand access"}, status=403)
    else:
        # Jika milih 'all', query semua brand milik user tersebut
        brands_to_query = user_brands

    # 4. Panggil kedua fungsi service layer lu
    # filtered_data = request.get("filtered_data")
    # if star
    # filtered_data = filtered_data or get_data(start_date,end_date,brands_to_query,selected_platform)
    # order_data = request.GET.get("order_data")
    order_data = order_data or get_order_mart_dashboard_brand(user_brands)
    filtered_data = filter_data(
        order_data, start_date, end_date, brands_to_query, selected_platform
    )
    cards_data = get_cards(filtered_data)
    trend_data = get_nmv_line(filtered_data)

    # 5. Gabungkan hasilnya ke dalam satu response object sesuai ekspektasi AJAX HTML
    context_response = {
        "cards": cards_data,
        "trend": trend_data,
        "order_data": order_data,
    }

    return JsonResponse(context_response)


@login_required
def update_profile(request):
    if request.method == "POST":
        form = UserProfileForm(request.POST, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, "Your profile was successfully updated!")
            return redirect("/")  # Redirect back to home/dashboard
    else:
        form = UserProfileForm(instance=request.user)
    assigned_brands = request.user.brands.all()
    context = {"form": form, "assigned_brands": assigned_brands}
    return render(request, "profile.html", context)
