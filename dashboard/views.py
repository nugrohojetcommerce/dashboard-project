from __future__ import annotations

from datetime import date, timedelta
from typing import Any
from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render, redirect
from django.utils.dateparse import parse_date
from dashboard.models import (
    OrderMartDashboardBrandDF as OrderMart,
    # User, UserBrand
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
    brand_filter,
    get_base_queryset,
    get_user_brands,
    get_brand_variants,
)

# ===== NEW: Consolidate Sales imports =====
from .services.consolidated_sales import (
    get_consolidate_sales_data,
    get_consolidate_brand_variants,
    get_consolidate_platforms,
)

# def get_user_brands(user: User) -> list[str]:
#     return list(
#         user.userbrand_set.values_list(
#             "brand__name",
#             flat=True,
#         ).distinct()
#     )

# def brand_filter(queryset: QuerySet, brand_list: list[str]) -> QuerySet:
#     """Filters a queryset using case-insensitive partial matching (OR logic)"""
#     if not brand_list:
#         return queryset.none()
#     conditions = [Q(brand__istartswith=brand) for brand in brand_list]
#     return queryset.filter(reduce(operator.or_, conditions))

# def get_base_queryset(
#     user: User,
# ) -> QuerySet[OrderMart]:
#     # return OrderMart.objects.filter(brand__in=get_user_brands(user))
#     user_brands = get_user_brands(user)
#     return brand_filter(OrderMart.objects.all(), user_brands)


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
            ).distinct()
        ),
        "start_date": today.replace(day=1).isoformat(),
        "end_date": today.isoformat(),
    }

    return render(
        request,
        "brand_performance_new.html",
        context,
    )


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

    t1 = time.time()
    queryset = OrderMart.objects.filter(
        date__range=[
            start_date,
            end_date,
        ]
    )
    print("Execution Time all object:")
    print("Execution Time start brand:")
    print(f"execute in :{time.time()-t1} s")
    if selected_brands:
        queryset = queryset.filter(brand__in=selected_brands)
        print("Execution Time brand filter:")
        print(f"execute in :{time.time()-t1} s")
    else:
        queryset = brand_filter(queryset, get_user_brands(request.user))

    if selected_platforms:
        queryset = queryset.filter(platform__in=selected_platforms)
        print("Execution Time platform filter:")
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


def brand_performance(
    request: HttpRequest,
) -> HttpResponse:
    # queryset = get_base_queryset(request.user)
    today = date.today() - timedelta(days=1)
    context: dict[str, Any] = {
        "brands": get_brand_variants(request.user),
        "platforms": list(
            OrderMart.objects.values_list(
                "platform",
                flat=True,
            ).distinct()
        ),
        "start_date": request.GET.get("start_date") or today.replace(day=1).isoformat(),
        "end_date": request.GET.get("end_date") or today.isoformat(),
    }

    return render(
        request,
        "brand_performance.html",
        context,
    )


def brand_performance_api(
    request: HttpRequest,
) -> JsonResponse:

    start_date = request.GET.get("start_date")
    end_date = request.GET.get("end_date")

    selected_brands = request.GET.getlist("brand")
    selected_platforms = request.GET.getlist("platform")

    data = get_brand_performance_data(
        user=request.user,
        start_date=start_date,
        end_date=end_date,
        selected_brands=selected_brands,
        selected_platforms=selected_platforms,
    )
    return JsonResponse(data)


# ======================================================================
# ===== NEW: Consolidate Sales — same flow/pattern as brand_performance
# ======================================================================

def consolidate_sales(
    request: HttpRequest,
) -> HttpResponse:
    today = date.today() - timedelta(days=1)
    context: dict[str, Any] = {
        "brands": get_consolidate_brand_variants(request.user),
        "platforms": get_consolidate_platforms(),
        "start_date": request.GET.get("start_date") or today.replace(day=1).isoformat(),
        "end_date": request.GET.get("end_date") or today.isoformat(),
    }

    return render(
        request,
        "consolidated_sales.html",
        context,
    )


def consolidate_sales_api(
    request: HttpRequest,
) -> JsonResponse:

    start_date = request.GET.get("start_date")
    end_date = request.GET.get("end_date")

    selected_brands = request.GET.getlist("brand")
    selected_platforms = request.GET.getlist("platform")

    data = get_consolidate_sales_data(
        user=request.user,
        start_date=start_date,
        end_date=end_date,
        selected_brands=selected_brands,
        selected_platforms=selected_platforms,
    )
    return JsonResponse(data)


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
