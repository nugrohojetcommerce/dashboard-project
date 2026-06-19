from django.db import connection
from ..models import OrderMartDashboardBrandDF
from django.db.models import Sum, Count, Q, Window, F
from dashboard.models import OrderMartDashboardBrandDF as OrderMart
from datetime import date
import pandas as pd
# from dashboard import models

def get_order_mart_dashboard_brand(user_brands):
    data = (
        OrderMartDashboardBrandDF.objects
        # filter(date__range=(start, end), brand__in=brands, is_nmv=1).values('date').annotate(gmv_sum=Sum('gmv')).order_by('date')
        .filter(brand__in=user_brands)
        .values()
        )
    return data

def filter_data(data, start, end, brands, platforms):
    print("DEBUG: get_cards called with start =", start, "end =", end, "brands =", brands, "platforms =", platforms)
    # 1. Filter data secara manual di Python dari parameter `data`
    filtered_data = []
    data = data.filter()
    for item in data:
        # Filter date__range (start <= date <= end)
        if not (item['date'] and start <= item['date'] <= end):
            continue
            
        # Filter brand__in
        if item['brand'] not in brands:
            continue
            
        # Filter platform (kalau bukan "all")
        if platforms != "all" and item['platform'] != platforms:
            continue
            
        filtered_data.append(item)
    
    return filtered_data


def get_cards(filtered_data):
    total_gmv = sum(item['gmv'] for item in filtered_data if item['gmv'] is not None)
    total_nmv = sum(item['gmv'] for item in filtered_data if item['is_nmv'] == 1 and item['gmv'] is not None)
    total_net_order = len(set(item['order_number'] for item in filtered_data if item['order_number'] is not None))
    total_net_quantity = sum(item['quantity'] for item in filtered_data if item['quantity'] is not None)

    return {
        "total_gmv": total_gmv,
        "total_nmv": total_nmv,
        "total_net_order": total_net_order,
        "total_net_quantity": total_net_quantity
    }

def get_nmv_line(filtered_data):
    return [
        {"date": str(r['date']), "gmv": float(r['gmv_sum'])}
        for r in filtered_data
    ]

# ======= REFACTORED FROM HERE ==============

def get_brand_performance_data(user, start_date=None, end_date=None, selected_brands=None, selected_platforms=None):

    if not start_date:
        start_date = date.today().replace(day=1).isoformat()

    if not end_date:
        end_date = date.today().isoformat()

    user_brands = list(
        user.userbrand_set
        .values_list("brand__name", flat=True)
        .order_by("brand__name")
        .distinct()
    )

    base_queryset = (
        OrderMart.objects
        .filter(
            date__range=[start_date, end_date],
            brand__in=user_brands
        )
    )

    all_brands = list(
        base_queryset
        .values_list("brand", flat=True)
        .distinct()
        .order_by("brand")
    )

    all_platforms = list(
        base_queryset
        .values_list("platform", flat=True)
        .distinct()
        .order_by("platform")
    )

    selected_brands = selected_brands or all_brands
    selected_platforms = selected_platforms or all_platforms

    # CASCADING BRANDS AND PLATFORMS
    brands = list(
        base_queryset
        .filter(
            platform__in=selected_platforms
        )
        .values_list("brand", flat=True)
        .distinct()
        .order_by("brand")
    )

    platforms = list(
        base_queryset
        .filter(
            brand__in=selected_brands
        )
        .values_list("platform", flat=True)
        .distinct()
        .order_by("platform")
    )

    queryset = (
        base_queryset
        .filter(
            brand__in=selected_brands,
            platform__in=selected_platforms
        )
    )

    # ===== Score Cards =====
    cards = queryset.aggregate(
        total_nmv=Sum("nmv"),
        total_gmv=Sum("gmv"),
        total_orders=Count("order_number",distinct=True, filter = Q(is_nmv=1)),
        total_quantity=Count("quantity")
    )

    cards["total_nmv"] = float(
        cards["total_nmv"] or 0
    )

    cards["total_gmv"] = float(
        cards["total_gmv"] or 0
    )

    cards["total_orders"] = float(
        cards["total_orders"] or 0
    )

    cards["total_quantity"] = float(
        cards["total_quantity"] or 0
    )

    # ===== NMV Trends =====

    rows = (
        queryset
        .values("date")
        .annotate(
            nmv=Sum("nmv")
        )
        .order_by("date")
    )

    df = pd.DataFrame(list(rows))
    df["cum_nmv"] = df["nmv"].cumsum()

    trend = [
        {
            "date": row["date"].isoformat(),
            "nmv": float(row["nmv"] or 0),
        }
        for row in (
            queryset
            .values("date")
            .annotate(
                nmv=Sum("nmv")
            )
            .order_by("date")
        )
    ]

    trend_cum = [
        {
            "date": row["date"].isoformat(),
            "nmv": float(row["cum_nmv"])
        }
        for _, row in df.iterrows()
    ]

    platform_rows = (
        queryset
        .values("platform")
        .annotate(
            nmv=Sum("nmv")
        )
        .order_by("-nmv")
    )
    df_platform = pd.DataFrame(list(platform_rows))

    platform_nmv = [
        {
        "platform": row["platform"],
        "nmv":row["nmv"]
        }
        for _, row in df_platform.iterrows()
    ]

    return {
            "brands": brands,
            "platforms": platforms,
            "selected_brands": selected_brands,
            "selected_platforms": selected_platforms,
            "start_date": start_date,
            "end_date": end_date,
            "cards": cards,
            "trend_json": trend,
            "trend_cum_json" : trend_cum,
            "platform_nmv_json" : platform_nmv
        }
