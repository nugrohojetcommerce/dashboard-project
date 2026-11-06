from django.db import models


class OrderMartDDSummary(models.Model):
    key_id = models.BigIntegerField(primary_key=True)
    brand = models.TextField(null=True, blank=True)
    brand_group = models.TextField(null=True, blank=True)
    date = models.DateField(null=True, blank=True)
    hour = models.IntegerField(null=True, blank=True)
    platform = models.TextField(null=True, blank=True)
    total_nmv = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    total_gmv = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    net_orders = models.BigIntegerField(null=True, blank=True)
    gross_orders = models.BigIntegerField(null=True, blank=True)
    net_quantity = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    gross_quantity = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    platform_discount = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    seller_discount = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    total_platform_voucher = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    total_seller_voucher = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)

    class Meta:
        managed = False
        db_table = 'order_mart_dd_summary'
        ordering = ['date', 'hour', 'brand', 'platform']

    def __str__(self):
        return f"{self.brand} - {self.platform} - {self.date} {self.hour:02d}:00"


class TrafficMartDD(models.Model):
    key_id = models.BigIntegerField(primary_key=True)
    platform = models.TextField(null=True, blank=True)
    brand = models.TextField(null=True, blank=True)
    date = models.TextField(null=True, blank=True)  # Format 'YYYYMMDD'
    hour = models.TextField(null=True, blank=True)  # Format '00'..'23'
    uv = models.BigIntegerField(null=True, blank=True)
    pv = models.BigIntegerField(null=True, blank=True)

    class Meta:
        managed = False
        db_table = '"postgre_traffic_mart_DD"'
        ordering = ['date', 'hour', 'brand', 'platform']

    def __str__(self):
        return f"{self.brand} - {self.platform} - {self.date} {self.hour}:00 (UV: {self.uv})"


class DailyTargetMart(models.Model):
    key_id = models.BigIntegerField(primary_key=True)
    date = models.DateField(null=True, blank=True)
    brand_group = models.TextField(null=True, blank=True)
    store_name = models.TextField(null=True, blank=True)
    platform = models.TextField(null=True, blank=True)
    target = models.BigIntegerField(null=True, blank=True)
    store_pic = models.TextField(db_column='Store PIC', null=True, blank=True)

    class Meta:
        managed = False
        db_table = 'postgre_daily_target_mart'
        ordering = ['date', 'brand_group', 'store_name', 'platform']

    def __str__(self):
        return f"{self.store_name} ({self.platform}) - {self.date}: {self.target}"

