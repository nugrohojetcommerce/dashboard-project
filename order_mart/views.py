import operator
from datetime import date, datetime, timedelta
from datetime import time as dtime
from functools import lru_cache, reduce
from typing import Any

import django.shortcuts  # type: ignore
import django.views.decorators.cache  # type: ignore
from dateutil.relativedelta import relativedelta
from django.contrib.auth.decorators import login_required  # type: ignore
from django.db.models import (  # type: ignore
    Case,
    ExpressionWrapper,
    F,
    FloatField,
    Q,
    Sum,
    Value,
    When,
)
from django.db.models.functions import Coalesce  # type: ignore
from django.http import HttpRequest, JsonResponse  # type: ignore
from django.utils.timezone import make_aware  # type: ignore

from dashboard.models import User, UserBrand

from .models import OrderMartDWDDF


@lru_cache(maxsize=256)
def get_user_brands_cached(user_id: int):
    return tuple(
        UserBrand.objects.filter(user_id=user_id).values_list("brand__name", flat=True)
    )

@lru_cache(maxsize=1)
def get_all_brand_variants():
    return list(OrderMartDWDDF.objects.values_list("brand", flat=True).distinct())

def get_user_brands(user: User) -> list[str]:
    return list(get_user_brands_cached(user.id))

def get_brand_variants(user):
    user_brands = get_user_brands(user)
    return sorted(
        [
            brand
            for brand in get_all_brand_variants()
            if any(
                brand.lower().startswith(user_brand.lower())
                for user_brand in user_brands
            )
        ]
    )

def index(request):
    today = date.today() - timedelta(days=1)  # noqa: DTZ011
    context: dict[str, Any] = {
        "brands": get_brand_variants(request.user),
        "platforms": list(
            OrderMartDWDDF.objects.values_list(
                "platform",
                flat=True,
            ).distinct()
        ),
        "start_date": request.GET.get("start_date") or today.replace(day=1).isoformat(),
        "end_date": request.GET.get("end_date") or today.isoformat(),
    }

    return django.shortcuts.render(
        request,
        "order_mart/index.html",
        context,
    )

def apply_filters(qs, request, user):
    selected_brands = request.GET.getlist("brand")
    selected_platforms = request.GET.getlist("platform")

    if selected_brands:
        qs = qs.filter(brand__in=selected_brands)
    else:
        condition = reduce(
            operator.or_, [Q(brand__istartswith=x) for x in get_user_brands(user)]
        )
        qs = qs.filter(condition)

    if selected_platforms:
        qs = qs.filter(platform__in=selected_platforms)

    return qs

def get_aggregated_metrics_by_group(qs):
    grouped = (
        qs.values("brand", "platform")
        .annotate(
            total_nmv=Coalesce(Sum("total_nmv"), 0.0, output_field=FloatField()),
            total_gmv=Coalesce(Sum("total_gmv"), 0.0, output_field=FloatField()),
            net_orders=Coalesce(Sum("net_orders"), 0.0, output_field=FloatField()),
            gross_orders=Coalesce(Sum("gross_orders"), 0.0, output_field=FloatField()),
            net_quantity=Coalesce(Sum("net_quantity"), 0.0, output_field=FloatField()),
            seller_discount=Coalesce(Sum("seller_discount"), 0.0, output_field=FloatField()),
            platform_discount=Coalesce(Sum("platform_discount"), 0.0, output_field=FloatField()),
            total_seller_voucher=Coalesce(Sum("total_seller_voucher"), 0.0, output_field=FloatField()),
            total_platform_voucher=Coalesce(Sum("total_platform_voucher"), 0.0, output_field=FloatField()),
        )
    )

    result = {}

    for row in grouped:

        nmv = row["total_nmv"]
        orders = row["net_orders"]
        qty = row["net_quantity"]

        row["seller_discount_percentage"] = (
            row["seller_discount"] / nmv if nmv else 0
        )

        row["platform_discount_percentage"] = (
            row["platform_discount"] / nmv if nmv else 0
        )

        row["seller_voucher_percentage"] = (
            row["total_seller_voucher"] / nmv if nmv else 0
        )

        row["platform_voucher_percentage"] = (
            row["total_platform_voucher"] / nmv if nmv else 0
        )

        row["AOV"] = nmv / orders if orders else 0
        row["ASP"] = nmv / qty if qty else 0

        result[(row["brand"], row["platform"])] = row

    return result

@django.views.decorators.cache.never_cache
@login_required
def daily_sales_api(request: HttpRequest) -> JsonResponse:
    start_date = request.GET.get("start_date")
    end_date = request.GET.get("end_date")
    start_date = start_date or date.today().replace(day=1).isoformat()  # noqa: DTZ011
    end_date = end_date or date.today().isoformat()  # noqa: DTZ011
    
    start = datetime.fromisoformat(start_date).date()
    end = datetime.fromisoformat(end_date).date()
    user = request.user

    prev_end = end - relativedelta(months=1)
    prev_start = start - relativedelta(months=1)
    yoy_start = start - relativedelta(years=1)
    yoy_end = end - relativedelta(years=1)

    dt_start = make_aware(datetime.combine(start, dtime.min))
    dt_end = make_aware(datetime.combine(end, dtime.max))
    
    prev_dt_start = make_aware(datetime.combine(prev_start, dtime.min))
    prev_dt_end = make_aware(datetime.combine(prev_end, dtime.max))
    
    yoy_dt_start = make_aware(datetime.combine(yoy_start, dtime.min))
    yoy_dt_end = make_aware(datetime.combine(yoy_end, dtime.max))

    base_qs = apply_filters(OrderMartDWDDF.objects.filter(create_order_date_time_date__range=[dt_start, dt_end]), request, user)
    prev_qs = apply_filters(OrderMartDWDDF.objects.filter(create_order_date_time_date__range=[prev_dt_start, prev_dt_end]), request, user)
    yoy_qs = apply_filters(OrderMartDWDDF.objects.filter(create_order_date_time_date__range=[yoy_dt_start, yoy_dt_end]), request, user)

    queryset = base_qs.annotate(
        seller_discount_percentage=Case(
            When(total_nmv__gt=0, then=ExpressionWrapper(F("seller_discount") / F("total_nmv"), output_field=FloatField())),
            default=Value(0.0), output_field=FloatField()
        ),
        platform_discount_percentage=Case(
            When(total_nmv__gt=0, then=ExpressionWrapper(F("platform_discount") / F("total_nmv"), output_field=FloatField())),
            default=Value(0.0), output_field=FloatField()
        ),
        seller_voucher_percentage=Case(
            When(total_nmv__gt=0, then=ExpressionWrapper(F("total_seller_voucher") / F("total_nmv"), output_field=FloatField())),
            default=Value(0.0), output_field=FloatField()
        ),
        platform_voucher_percentage=Case(
            When(total_nmv__gt=0, then=ExpressionWrapper(F("total_platform_voucher") / F("total_nmv"), output_field=FloatField())),
            default=Value(0.0), output_field=FloatField()
        ),
        AOV=Case(
            When(net_orders__gt=0, then=ExpressionWrapper(F("total_nmv") / F("net_orders"), output_field=FloatField())),
            default=Value(0.0), output_field=FloatField()
        ),
        ASP=Case(
            When(net_quantity__gt=0, then=ExpressionWrapper(F("total_nmv") / F("net_quantity"), output_field=FloatField())),
            default=Value(0.0), output_field=FloatField()
        ),
    ).order_by("-create_order_date_time_date")

    daily_data = list(queryset.values())

    current_map = get_aggregated_metrics_by_group(base_qs)
    prev_map = get_aggregated_metrics_by_group(prev_qs)
    yoy_map = get_aggregated_metrics_by_group(yoy_qs)

    all_keys = sorted(list(set(current_map.keys()) | set(prev_map.keys()) | set(yoy_map.keys())))  # noqa: C414
    period_label = f"{start.strftime('%Y%m%d')}-{end.strftime('%Y%m%d')}"

    metric_definitions = [
        ("total_nmv", "NMV"),
        ("total_gmv", "GMV"),
        ("net_orders", "Net Orders"),
        ("gross_orders", "Gross Orders"),
        ("net_quantity", "Net Quantity"),
        ("seller_discount", "Seller Discount"),
        ("seller_discount_percentage", "% Seller Disc"),
        ("platform_discount", "Platform Discount"),
        ("platform_discount_percentage", "% Platform Disc"),
        ("total_seller_voucher", "Seller Voucher"),
        ("seller_voucher_percentage", "% Seller Voucher"),
        ("total_platform_voucher", "Platform Voucher"),
        ("platform_voucher_percentage", "% Platform Voucher"),
        ("AOV", "AOV"),
        ("ASP", "ASP"),
    ]
    period_label = f"{start.strftime('%Y%m%d')}-{end.strftime('%Y%m%d')}"

    pivot_rows = []

    for brand, platform in all_keys:

        current = current_map.get((brand, platform), {})
        previous = prev_map.get((brand, platform), {})
        yoy = yoy_map.get((brand, platform), {})

        row = {
            "period": period_label,
            "brand": brand,
            "platform": platform,
        }

        for metric_key, metric_label in metric_definitions:

            curr = current.get(metric_key, 0)
            prev = previous.get(metric_key, 0)
            yy = yoy.get(metric_key, 0)

            row[f"{metric_key}_selected"] = curr
            row[f"{metric_key}_prev"] = prev
            row[f"{metric_key}_growth_prev"] = (
                (curr - prev) / prev if prev else 0
            )

            row[f"{metric_key}_yoy"] = yy
            row[f"{metric_key}_growth_yoy"] = (
                (curr - yy) / yy if yy else 0
            )

        pivot_rows.append(row)

    columns_config = [
        {"data": "period", "title": "Period"},
        {"data": "brand", "title": "Brand"},
        {"data": "platform", "title": "Platform"},
    ]
    for metric_key, metric_label in metric_definitions:

        columns_config.extend([
            {"data": f"{metric_key}_selected", "title": f"{metric_label} Selected", "type": "numeric"},
            {"data": f"{metric_key}_prev", "title": f"{metric_label} Prev", "type": "numeric"},
            {"data": f"{metric_key}_growth_prev", "title": f"{metric_label} vs Prev", "type": "numeric"},
            {"data": f"{metric_key}_yoy", "title": f"{metric_label} YoY", "type": "numeric"},
            {"data": f"{metric_key}_growth_yoy", "title": f"{metric_label} vs YoY", "type": "numeric"},
        ])
    
    return JsonResponse({
        "daily_data": daily_data,
        "pivot_data": pivot_rows,
        "pivot_columns": columns_config,
    })