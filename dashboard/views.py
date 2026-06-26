from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from django.contrib.auth.decorators import login_required
from django.db.models import QuerySet, Sum
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render
from django.utils.dateparse import parse_date

from dashboard.models import (
    OrderMartDashboardBrandDF as OrderMart,
    User,
)
from dashboard.services.dashboard_performance import get_cards

from .services.dashboard_performance import (
    filter_data,
    get_brand_performance_data,
    get_nmv_line,
    get_order_mart_dashboard_brand,
)
from .services.gmv_services import get_gmv


def get_user_brands(user: User) -> list[str]:
    return list(
        user.userbrand_set.values_list(
            "brand__name",
            flat=True,
        ).distinct()
    )


def get_base_queryset(
    user: User,
) -> QuerySet[OrderMart]:
    return OrderMart.objects.filter(brand__in=get_user_brands(user))


def brand_performance_new(
    request: HttpRequest,
) -> HttpResponse:
    queryset = get_base_queryset(request.user)
    today = date.today()
    context: dict[str, Any] = {
        "brands": list(
            queryset.values_list(
                "brand",
                flat=True,
            )
            .distinct()
            .order_by("brand")
        ),
        "platforms": list(
            queryset.values_list(
                "platform",
                flat=True,
            )
            .distinct()
            .order_by("platform")
        ),
        "start_date": today.replace(day=1).isoformat(),
        "end_date": today.isoformat(),
    }

    return render(
        request,
        "brand_performance_new.html",
        context,
    )


def brand_performance_api_new(
    request: HttpRequest,
) -> JsonResponse:
    
    today = date.today()
    start_date = parse_date(
    request.GET.get("start_date", "")
    )

    end_date = parse_date(
        request.GET.get("end_date", "")
    )

    if start_date is None:
        start_date = today.replace(day=1)

    if end_date is None:
        end_date = today

    selected_brands = request.GET.getlist("brand")
    selected_platforms = request.GET.getlist("platform")
    queryset = get_base_queryset(request.user).filter(
        date__range=[
            start_date,
            end_date,
        ]
    )
    if selected_brands:
        queryset = queryset.filter(brand__in=selected_brands)
    if selected_platforms:
        queryset = queryset.filter(platform__in=selected_platforms)
    cards = queryset.aggregate(
        total_nmv=Sum("nmv"),
        total_gmv=Sum("gmv"),
    )

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


# ================== DEV IMAM UNDER HERE
# @login_required
# def brand_performance(request):

#     start_date = request.GET.get("start_date")
#     end_date = request.GET.get("end_date")

#     selected_brands = request.GET.getlist("brand")
#     selected_platforms = request.GET.getlist("platform")

#     context = get_brand_performance_data(
#         user=request.user,
#         start_date=start_date,
#         end_date=end_date,
#         selected_brands=selected_brands,
#         selected_platforms=selected_platforms,
#     )
#     return render(request, "brand_performance.html", context)

def brand_performance(
    request: HttpRequest,
) -> HttpResponse:
    queryset = get_base_queryset(request.user)
    today = date.today() - timedelta(days=1)
    context: dict[str, Any] = {
        "brands": list(
            queryset.values_list(
                "brand",
                flat=True,
            )
            .distinct()
            .order_by("brand")
        ),
        "platforms": list(
            queryset.values_list(
                "platform",
                flat=True,
            )
            .distinct()
            .order_by("platform")
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
    # return render(request, "brand_performance.html", context)