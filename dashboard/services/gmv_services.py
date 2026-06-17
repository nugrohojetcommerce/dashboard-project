from django.db import connection
from ..models import OrderMartDashboardBrandDF

def get_gmv(start, end, brands):
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT date, SUM(gmv)
            FROM order_mart_dashboard_brand_df
            WHERE date BETWEEN %s AND %s
            AND brand = ANY(%s)
            AND is_nmv = 1
            GROUP BY date
            ORDER BY date
        """, [start, end, brands])

        rows = cursor.fetchall()
        print(rows)
        # row.get
        df = OrderMartDashboardBrandDF.objects.first()
        df = df.__dict__
        # filter(date__range=(start, end), brand__in=brands, is_nmv=1).values('date').annotate(gmv_sum=Sum('gmv')).order_by('date')
        print(df)
    return [
        {"date": str(r[0]), "gmv": float(r[1])}
        for r in rows
    ]  


