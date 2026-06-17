from django.db import connection
from ..models import OrderMartDashboardBrandDF
from django.db.models import Sum, Count, Q
# from dashboard import models

def get_cards(start, end, brands):
    print("DEBUG: get_cards called with start =", start, "end =", end, "brands =", brands)
    data = list(OrderMartDashboardBrandDF.objects.filter(date__range=(start, end), brand__in=brands).values())
    total_gmv = sum(item['gmv'] for item in data if item['gmv'] is not None)
    total_nmv = sum(item['gmv'] for item in data if item['is_nmv'] == 1 and item['gmv'] is not None)
    total_net_order = len(set(item['order_number'] for item in data if item['order_number'] is not None))
    total_net_quantity = sum(item['quantity'] for item in data if item['quantity'] is not None)
    # total_gmv = data.aggregate(total_gmv=Sum('gmv'))['total_gmv'] or 0
    return {
        "total_gmv": total_gmv,
        "total_nmv": total_nmv,
        "total_net_order": total_net_order,
        "total_net_quantity": total_net_quantity
    }

def get_nmv_line(start, end, brands):
    data = (
        OrderMartDashboardBrandDF.objects
        .filter(date__range=(start, end), brand__in=brands, is_nmv=1)
        .values('date')
        .annotate(gmv_sum=Sum('gmv'))
        .order_by('date')
    )
    return [
        {"date": str(r['date']), "gmv": float(r['gmv_sum'])}
        for r in data
    ]