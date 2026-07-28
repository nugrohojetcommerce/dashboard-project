from ..models import OrderMartDashboardBrandDF
from concurrent.futures import ThreadPoolExecutor
from django.db import close_old_connections
from django.db.models import (
    Sum,
    Max,
    Count,
    Q,
    QuerySet,
    F,
    Case,
    When,
    Value,
    CharField,
    IntegerField,
    Func,
)
from django.db.models.functions import Lower, Length
from dashboard.models import OrderMartDashboardBrandDF as OrderMart, User, UserBrand
from datetime import date, datetime, timedelta
from dateutil.relativedelta import relativedelta

import operator
from functools import reduce
from functools import lru_cache
import time

DELIVERY_GROUP_CASE = Case(
    When(delivery_option_lower__contains="instan", then=Value("Instant")),
    When(
        Q(delivery_option_lower__contains="argo")
        | Q(delivery_option_lower__contains="jtr"),
        then=Value("Kargo"),
    ),
    When(
        Q(delivery_option_lower__contains="reg")
        | Q(delivery_option_lower__contains="standar")
        | (
            Q(delivery_option_lower__contains="expres")
            & ~Q(delivery_option_lower__contains="grab")
        ),
        then=Value("Regular"),
    ),
    When(
        Q(delivery_option_lower__contains="econ")
        | Q(
            delivery_option_lower__in=[
                "hemat",
                "spx hemat",
                "sicepat gokil",
                "sicepat halu",
            ]
        ),
        then=Value("Regular Hemat"),
    ),
    When(delivery_option_lower__contains="same", then=Value("Same Day")),
    When(delivery_option_lower__contains="seller", then=Value("Shipped by Seller")),
    When(
        Q(delivery_option_len_trim=F("delivery_option_len_replace")),
        then=Value("Regular"),
    ),
    default=Value("Others"),
    output_field=CharField(),
)

PRICE_BAND_CASE = Case(
    When(selling_price__lte=50000, then=Value("<50k")),
    When(selling_price__lte=100000, then=Value("50k-100k")),
    When(selling_price__lte=200000, then=Value("100k-200k")),
    When(selling_price__lte=500000, then=Value("200k-500k")),
    When(selling_price__lte=1000000, then=Value("500k-1mio")),
    When(selling_price__lte=2000000, then=Value("1mio-2mio")),
    When(selling_price__lte=5000000, then=Value("2mio-5mio")),
    default=Value(">5mio"),
    output_field=CharField(),
)

SORT_CASE = Case(
    When(price_band="<50k", then=Value(1)),
    When(price_band="50k-100k", then=Value(2)),
    When(price_band="100k-200k", then=Value(3)),
    When(price_band="200k-500k", then=Value(4)),
    When(price_band="500k-1mio", then=Value(5)),
    When(price_band="1mio-2mio", then=Value(6)),
    When(price_band="2mio-5mio", then=Value(7)),
    default=Value(8),
    output_field=IntegerField(),
)


class Replace(Func):
    function = "REPLACE"
    template = "%(function)s(%(expressions)s, ' ', '')"


class Trim(Func):
    function = "TRIM"


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


@lru_cache(maxsize=256)
def get_user_brands_cached(user_id: int):
    return tuple(
        UserBrand.objects.filter(user_id=user_id).values_list("brand__name", flat=True)
    )


def get_user_brands(user: User) -> list[str]:
    return list(get_user_brands_cached(user.id))


@lru_cache(maxsize=1)
def get_all_brand_variants():
    return list(OrderMart.objects.values_list("brand", flat=True).distinct())


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


def get_order_mart_dashboard_brand(user_brands):
    data = (
        OrderMartDashboardBrandDF.objects
        # filter(date__range=(start, end), brand__in=brands, is_nmv=1).values('date').annotate(gmv_sum=Sum('gmv')).order_by('date')
        .filter(brand__in=user_brands).values()
    )
    # print("DATA: ",data)
    return data


def filter_data(data, start, end, brands, platforms):
    print(
        "DEBUG: get_cards called with start =",
        start,
        "end =",
        end,
        "brands =",
        brands,
        "platforms =",
        platforms,
    )
    # 1. Filter data secara manual di Python dari parameter `data`
    filtered_data = []
    data = data.filter()
    for item in data:
        # Filter date__range (start <= date <= end)
        if not (item["date"] and start <= item["date"] <= end):
            continue
        # Filter brand__in
        if item["brand"] not in brands:
            continue
        # Filter platform (kalau bukan "all")
        if platforms != "all" and item["platform"] != platforms:
            continue
        filtered_data.append(item)

    return filtered_data


def get_cards(filtered_data):
    total_gmv = sum(item["gmv"] for item in filtered_data if item["gmv"] is not None)
    total_nmv = sum(
        item["gmv"]
        for item in filtered_data
        if item["is_nmv"] == 1 and item["gmv"] is not None
    )
    total_net_order = len({item["order_number"]for item in filtered_data if item["order_number"] is not None})
    total_net_quantity = sum(
        item["quantity"] for item in filtered_data if item["quantity"] is not None
    )

    return {
        "total_gmv": total_gmv,
        "total_nmv": total_nmv,
        "total_net_order": total_net_order,
        "total_net_quantity": total_net_quantity,
    }


def get_nmv_line(filtered_data):
    return [{"date": str(r["date"]), "gmv": float(r["gmv_sum"])} for r in filtered_data]


# ======= REFACTORED FROM HERE ==============
def apply_filters(queryset, user, selected_brands, selected_platforms):
    if selected_brands:
        queryset = queryset.filter(brand__in=selected_brands)
    else:
        queryset = brand_filter(queryset, get_user_brands(user))

    if selected_platforms:
        queryset = queryset.filter(platform__in=selected_platforms)

    return queryset


def calc_growth(current, previous):
    if current is None or previous is None:
        return None
    if previous == 0:
        return None if current > 0 else 0

    return round((current - previous) / previous * 100, 2)


def get_trend(queryset):
    qs = (
        queryset.order_by()
        .values("date")
        .annotate(
            nmv=Sum("nmv"),
            gmv=Sum("gmv"),
        )
        .order_by("date")
    )
    # print(qs.explain(analyze=True, buffers=True))
    return list(qs)


def get_platform(queryset):
    qs = (
        queryset.order_by().values("platform").annotate(nmv=Sum("nmv")).order_by("-nmv")
    )
    # print(qs.explain(analyze=True, buffers=True))
    return list(qs)


def get_brand(queryset):
    qs = queryset.order_by().values("brand").annotate(nmv=Sum("nmv")).order_by("-nmv")
    # print(qs.explain(analyze=True, buffers=True))
    return list(qs)


def get_product(queryset):
    qs = (
        queryset.order_by()
        .values("sku_reference_no")
        .annotate(
            product_name=Max("product_name"),
            nmv=Sum("nmv"),
            orders=Count("order_number", distinct=True),
        )
        .order_by("-nmv")
    )
    # print(qs.explain(analyze=True, buffers=True))
    return list(qs)


def get_payment(queryset):
    qs = (
        queryset.order_by()
        .values("payment_type")
        .annotate(orders=Count("order_number", distinct=True))
        .order_by("-orders")
    )
    # print(qs.explain(analyze=True, buffers=True))
    return list(qs)


def get_delivery(queryset):

    delivery_group_case = DELIVERY_GROUP_CASE
    qs = (
        queryset.order_by()
        .annotate(
            delivery_option_lower=Lower("delivery_option"),
            delivery_option_len_trim=Length(Trim("delivery_option")),
            delivery_option_len_replace=Length(Replace(Trim("delivery_option"))),
        )
        .annotate(delivery_group=delivery_group_case)
        .values("delivery_group")
        .annotate(orders=Count("order_number", distinct=True))
        .order_by("-orders")
    )
    # print(qs.explain(analyze=True, buffers=True))
    return list(qs)


def get_buyer(queryset):
    qs = (
        queryset.order_by()
        .annotate(
            buyer_type=Case(
                When(is_new_buyer=1, then=Value("New Buyer")),
                When(is_new_buyer=0, then=Value("Existing Buyer")),
                default=Value("Unknown"),
                output_field=CharField(),
            )
        )
        .values("buyer_type")
        .annotate(total_buyers=Count("username", distinct=True))
        .order_by("-total_buyers")
    )
    # print(qs.explain(analyze=True, buffers=True))
    return list(qs)


def get_priceband(queryset):
    price_band = PRICE_BAND_CASE
    sort_case = SORT_CASE
    qs = (
        queryset.order_by()
        .annotate(price_band=price_band)
        .values("price_band")
        .annotate(orders=Count("order_number", distinct=True))
        .annotate(sort_order=sort_case)
        .order_by("sort_order")
    )
    # print(qs.explain(analyze=True, buffers=True))
    return list(qs)


def get_province(queryset):
    qs = (
        queryset.order_by()
        .values("province")
        .annotate(
            value=Count(
                "order_number",
                distinct=True,
                filter=Q(is_nmv=1),
            )
        )
        .order_by("-value")
    )
    return list(qs)


def run_query(func, queryset):
    close_old_connections()
    t = time.time()
    try:
        result = func(queryset)
        print(f"{func.__name__}: {time.time() - t:.3f}s")
        return result
    finally:
        close_old_connections()


def get_brand_performance_data(
    user, start_date=None, end_date=None, selected_brands=None, selected_platforms=None
):

    start_date = start_date or date.today().replace(day=1).isoformat()
    end_date = end_date or date.today().isoformat()
    start = datetime.fromisoformat(start_date).date()
    end = datetime.fromisoformat(end_date).date()

    period_days = (end - start).days + 1

    prev_end = start - timedelta(days=1)
    prev_start = prev_end - timedelta(days=period_days - 1)
    yoy_start = start - relativedelta(years=1)
    yoy_end = end - relativedelta(years=1)

    t1 = time.time()
    base_queryset = OrderMart.objects.filter(
        date__range=[start_date, end_date],
        # brand__in=user_brands
    )
    # if not base_queryset:
    previous_queryset = OrderMart.objects.filter(
        date__range=[prev_start, prev_end],
        # brand__in=user_brands
    )
    yoy_queryset = OrderMart.objects.filter(
        date__range=[yoy_start, yoy_end],
        # brand__in=user_brands
    )

    print(f"first checkpoint{time.time()-t1} seconds")

    if selected_brands:
        base_queryset = base_queryset.filter(brand__in=selected_brands)
        previous_queryset = previous_queryset.filter(brand__in=selected_brands)
        yoy_queryset = yoy_queryset.filter(brand__in=selected_brands)
    else:
        condition = reduce(
            operator.or_, [Q(brand__istartswith=x) for x in get_user_brands(user)]
        )
        base_queryset = base_queryset.filter(condition)
        previous_queryset = previous_queryset.filter(condition)
        yoy_queryset = yoy_queryset.filter(condition)
        # base_queryset = brand_filter(base_queryset, get_user_brands(user))
        # previous_queryset = brand_filter(previous_queryset, get_user_brands(user))
        # yoy_queryset = brand_filter(yoy_queryset, get_user_brands(user))

    print(f"second checkpoint{time.time()-t1} seconds")

    if selected_platforms:
        base_queryset = base_queryset.filter(platform__in=selected_platforms)
        previous_queryset = previous_queryset.filter(platform__in=selected_platforms)
        yoy_queryset = yoy_queryset.filter(platform__in=selected_platforms)
    # if not base_queryset:
    #     return None
    # return JsonResponse(
    #             {"error": "Invalid date format. Expected YYYY-MM-DD."},
    #             status=400,
    #         )
    queryset = base_queryset
    t = time.time()
    # print(queryset.count())
    print(time.time() - t)
    print(f"third checkpoint{time.time()-t1} seconds")
    # ===== Score Cards =====
    cards = queryset.aggregate(
        total_nmv=Sum("nmv"),
        total_gmv=Sum("gmv"),
        total_orders=Count("order_number", distinct=True, filter=Q(is_nmv=1)),
        total_quantity=Sum("quantity", filter=Q(is_nmv=1)),
    )
    
    previous_cards = previous_queryset.aggregate(
        total_nmv=Sum("nmv"),
        total_gmv=Sum("gmv"),
        total_orders=Count("order_number", distinct=True, filter=Q(is_nmv=1)),
        total_quantity=Sum("quantity", filter=Q(is_nmv=1)),
    )
    yoy_cards = yoy_queryset.aggregate(
        total_nmv=Sum("nmv"),
        total_gmv=Sum("gmv"),
        total_orders=Count("order_number", distinct=True, filter=Q(is_nmv=1)),
        total_quantity=Sum("quantity", filter=Q(is_nmv=1)),
    )
    print("aggregation 1 :", time.time() - t1, "seconds")
    previous_cards["total_nmv"] = float(previous_cards["total_nmv"] or 0)
    previous_cards["total_gmv"] = float(previous_cards["total_gmv"] or 0)
    previous_cards["total_orders"] = float(previous_cards["total_orders"] or 0)
    previous_cards["total_quantity"] = float(previous_cards["total_quantity"] or 0)
    yoy_cards["total_nmv"] = float(yoy_cards["total_nmv"] or 0)
    yoy_cards["total_gmv"] = float(yoy_cards["total_gmv"] or 0)
    yoy_cards["total_orders"] = float(yoy_cards["total_orders"] or 0)
    yoy_cards["total_quantity"] = float(yoy_cards["total_quantity"] or 0)
    cards["nmv_growth"] = calc_growth(cards["total_nmv"], previous_cards["total_nmv"])
    cards["gmv_growth"] = calc_growth(cards["total_gmv"], previous_cards["total_gmv"])
    cards["orders_growth"] = calc_growth(
        cards["total_orders"], previous_cards["total_orders"]
    )
    cards["quantity_growth"] = calc_growth(
        cards["total_quantity"], previous_cards["total_quantity"]
    )
    cards["nmv_yoy_growth"] = calc_growth(cards["total_nmv"], yoy_cards["total_nmv"])
    cards["gmv_yoy_growth"] = calc_growth(cards["total_gmv"], yoy_cards["total_gmv"])
    cards["orders_yoy_growth"] = calc_growth(
        cards["total_orders"], yoy_cards["total_orders"]
    )
    cards["quantity_yoy_growth"] = calc_growth(
        cards["total_quantity"], yoy_cards["total_quantity"]
    )
    cards["total_nmv"] = float(cards["total_nmv"] or 0)

    cards["total_gmv"] = float(cards["total_gmv"] or 0)

    cards["total_orders"] = float(cards["total_orders"] or 0)

    cards["total_quantity"] = float(cards["total_quantity"] or 0)
    print("aggregation 2:", time.time() - t1, "seconds")
    with ThreadPoolExecutor(max_workers=9) as executor:
        future_trend = executor.submit(run_query, get_trend, queryset)
        # print("aggregation trend:", time.time() - t1, "seconds")
        future_platform = executor.submit(run_query, get_platform, queryset)
        # print("aggregation platform:", time.time() - t1, "seconds")
        future_brand = executor.submit(run_query, get_brand, queryset)
        # print("aggregation brand:", time.time() - t1, "seconds")
        future_product = executor.submit(run_query, get_product, queryset)
        # print("aggregation product:", time.time() - t1, "seconds")
        future_payment = executor.submit(run_query, get_payment, queryset)
        # print("aggregation payment:", time.time() - t1, "seconds")
        future_delivery = executor.submit(run_query, get_delivery, queryset)
        # print("aggregation delivery:", time.time() - t1, "seconds")
        future_buyer = executor.submit(run_query, get_buyer, queryset)
        # print("aggregation buyer:", time.time() - t1, "seconds")
        future_priceband = executor.submit(run_query, get_priceband, queryset)
        # print("aggregation price:", time.time() - t1, "seconds")
        future_province = executor.submit(run_query, get_province, queryset)
        # print("aggregation province:", time.time() - t1, "seconds")
    trend_rows = future_trend.result()
    platform_rows = future_platform.result()
    brand_rows = future_brand.result()
    product_rows = future_product.result()
    payment_type_rows = future_payment.result()
    delivery_option_rows = future_delivery.result()
    new_existing_buyer_rows = future_buyer.result()
    price_band_rows = future_priceband.result()
    province_rows = future_province.result()
    # ===== NMV Trends =====
    trend = []
    trend_cum = []

    cum_nmv = 0.0

    for row in trend_rows:
        nmv = float(row["nmv"] or 0)
        trend.append(
            {
                "date": row["date"].isoformat(),
                "nmv": nmv,
                "gmv": float(row["gmv"] or 0),
            }
        )
        cum_nmv += nmv
        trend_cum.append(
            {
                "date": row["date"].isoformat(),
                "nmv": cum_nmv,
            }
        )
    print("trend 1:", time.time() - t1, "seconds")
    # ===== Platform NMV Contribution =====
    platform_nmv = [
        {"platform": r["platform"], "nmv": float(r["nmv"] or 0)} for r in platform_rows
    ]
    # ===== Brand NMV Contribution =====
    brand_nmv = [{"brand": row["brand"], "nmv": row["nmv"]} for row in brand_rows]
    print("trend 2:", time.time() - t1, "seconds")
    # ===== Top Product by NMV =====
    product_table_nmv = []
    product_nmv = []

    for i, row in enumerate(product_rows):
        item = {
            "product_name": row["sku_reference_no"],
            "nmv": float(row["nmv"] or 0),
            "orders": row["orders"],
        }
        product_table_nmv.append(item)
        if i < 10:
            product_nmv.append(
                {"product_name": item["product_name"], "nmv": item["nmv"]}
            )
    print("trend product:", time.time() - t1, "seconds")
    # ===== Payment Type Contribution =====
    payment_type_orders = [
        {"payment_type": row["payment_type"], "orders": row["orders"]}
        for row in payment_type_rows
    ]
    print("payment type:", time.time() - t1, "seconds")
    # ===== Delivery Option Contribution =====

    # Definisikan anotasi untuk kategori delivery_group
    # # Jalankan Queryset dengan mendaftarkan panjang karakternya dulu di .annotate()
    delivery_option_orders = [
        {"delivery_option": row["delivery_group"], "orders": row["orders"]}
        for row in delivery_option_rows
    ]

    print("Delivery :", time.time() - t1, "seconds")
    # ===== New vs Existing Buyer =====
    new_existing_buyer = [
        {"buyer_type": row["buyer_type"], "total_buyers": row["total_buyers"]}
        for row in new_existing_buyer_rows
    ]
    print("Buyer :", time.time() - t1, "seconds")

    # ===== Price Band Distribution =====

    # Definisikan anotasi untuk kategori delivery_group
    price_band_orders = [
        {"price_band": row["price_band"], "orders": row["orders"]}
        for row in price_band_rows
    ]
    print("Price Band :", time.time() - t1, "seconds")

    province_orders = [
        {
            "name": row["province"],
            "value": int(row["value"] or 0),
        }
        for row in province_rows
    ]
    print("chart constructions:", time.time() - t1, "seconds")

    return {
        "brands": selected_brands,
        "platforms": selected_platforms,
        "selected_brands": selected_brands,
        "selected_platforms": selected_platforms,
        "start_date": start_date,
        "end_date": end_date,
        "cards": cards,
        "trend_json": trend,
        "trend_cum_json": trend_cum,
        "platform_nmv_json": platform_nmv,
        "brand_nmv_json": brand_nmv,
        "product_nmv_json": product_nmv,
        "payment_type_orders_json": payment_type_orders,
        "delivery_option_orders_json": delivery_option_orders,
        "new_existing_buyer_json": new_existing_buyer,
        "product_table_nmv_json": product_table_nmv,
        "price_band_orders_json": price_band_orders,
        "province_orders_json": province_orders,
    }
