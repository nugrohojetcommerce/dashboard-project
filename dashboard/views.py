from datetime import date
from typing import Any

from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db.models import QuerySet, Sum
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render

from .models import OrderMartDashboardBrandDF as OrderMart


def get_user_brands(user: User) -> list[str]:
    return list(
        user.userbrand_set
        .values_list(
            "brand__name",
            flat=True,
        )
        .distinct()
    )


def get_base_queryset(
    user: User,
) -> QuerySet[OrderMart]:
    return OrderMart.objects.filter(
        brand__in=get_user_brands(user)
    )


@login_required
def brand_performance(
    request: HttpRequest,
) -> HttpResponse:

    queryset = get_base_queryset(
        request.user
    )

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
        "start_date": today.replace(
            day=1
        ).isoformat(),
        "end_date": today.isoformat(),
    }

    return render(
        request,
        "brand_performance_view.html",
        context,
    )


@login_required
def brand_performance_api(
    request: HttpRequest,
) -> JsonResponse:

    today = date.today()

    start_date = request.GET.get(
        "start_date",
        today.replace(day=1).isoformat(),
    )

    end_date = request.GET.get(
        "end_date",
        today.isoformat(),
    )

    selected_brands = request.GET.getlist(
        "brand"
    )

    selected_platforms = request.GET.getlist(
        "platform"
    )

    queryset = (
        get_base_queryset(request.user)
        .filter(
            date__range=[
                start_date,
                end_date,
            ]
        )
    )

    if selected_brands:
        queryset = queryset.filter(
            brand__in=selected_brands
        )

    if selected_platforms:
        queryset = queryset.filter(
            platform__in=selected_platforms
        )

    cards = queryset.aggregate(
        total_nmv=Sum("nmv"),
        total_gmv=Sum("gmv"),
    )

    # trend = [
    #     {
    #         "date": row["date"].isoformat(),
    #         "nmv": float(
    #             row["nmv"] or 0
    #         ),
    #     }
    #     for row in (
    #         queryset
    #         .values("date")
    #         .annotate(
    #             nmv=Sum("nmv")
    #         )
    #         .order_by("date")
    #     )
    # ]
    trend = [
    {
        "date": row["date"].isoformat(),
        "nmv": float(row["nmv"] or 0),
        "gmv": float(row["gmv"] or 0),
    }
    for row in (
        queryset
        .values("date")
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
                "total_nmv": float(
                    cards["total_nmv"] or 0
                ),
                "total_gmv": float(
                    cards["total_gmv"] or 0
                ),
            },
            "trend": trend,
        }
    )