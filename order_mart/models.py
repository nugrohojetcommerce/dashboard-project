from typing import ClassVar

import django.db  # type: ignore


# class OrderMartDWDDF(django.db.models.Model):

#     key_id = django.db.models.BigIntegerField(primary_key=True)

#     create_order_date_time = django.db.models.DateTimeField(null=True, blank=True)
#     order_number = django.db.models.TextField(null=True, blank=True)
#     variation = django.db.models.TextField(null=True, blank=True)
#     quantity = django.db.models.BigIntegerField(null=True, blank=True)
#     total_product_price = django.db.models.BigIntegerField(null=True, blank=True)
#     total_discount = django.db.models.BigIntegerField(null=True, blank=True)
#     discount_from_seller = django.db.models.BigIntegerField(null=True, blank=True)
#     discount_from_platform = django.db.models.BigIntegerField(null=True, blank=True)
#     order_status = django.db.models.TextField(null=True, blank=True)
#     reason_for_cancellation = django.db.models.TextField(null=True, blank=True)
#     return_status = django.db.models.TextField(null=True, blank=True)
#     tracking_number = django.db.models.TextField(null=True, blank=True)
#     shipping_company = django.db.models.TextField(null=True, blank=True)
#     pick_up_option = django.db.models.TextField(null=True, blank=True)
#     expected_shipping_date = django.db.models.DateTimeField(null=True, blank=True)
#     shipping_date_time = django.db.models.DateTimeField(null=True, blank=True)
#     payment_date_time = django.db.models.DateTimeField(null=True, blank=True)
#     payment_method = django.db.models.TextField(null=True, blank=True)
#     parent_sku_no = django.db.models.TextField(null=True, blank=True)
#     product_name = django.db.models.TextField(null=True, blank=True)
#     sku_reference_no = django.db.models.TextField(null=True, blank=True)
#     rsp = django.db.models.BigIntegerField(null=True, blank=True)
#     selling_price = django.db.models.BigIntegerField(null=True, blank=True)
#     voucher_paid_by_seller = django.db.models.BigIntegerField(null=True, blank=True)
#     coins_cashback_code = django.db.models.BigIntegerField(null=True, blank=True)
#     voucher_paid_by_platform = django.db.models.BigIntegerField(null=True, blank=True)
#     bundle_deal_participation = django.db.models.TextField(null=True, blank=True)
#     budle_deal_discount_paid_by_shopee = django.db.models.BigIntegerField(null=True, blank=True)
#     budle_deal_discount_paid_by_seller = django.db.models.BigIntegerField(null=True, blank=True)
#     discount_from_coins = django.db.models.BigIntegerField(null=True, blank=True)
#     credit_card_discount = django.db.models.BigIntegerField(null=True, blank=True)
#     shipping_fee_paid_by_buyer = django.db.models.BigIntegerField(null=True, blank=True)
#     shipping_fee_paid_by_platform = django.db.models.BigIntegerField(null=True, blank=True)
#     return_shipping_fee = django.db.models.BigIntegerField(null=True, blank=True)
#     total_buyer_payment = django.db.models.BigIntegerField(null=True, blank=True)
#     shipping_fee = django.db.models.BigIntegerField(null=True, blank=True)
#     note_from_buyer = django.db.models.TextField(null=True, blank=True)
#     note = django.db.models.TextField(null=True, blank=True)
#     username = django.db.models.TextField(null=True, blank=True)
#     receiver_name = django.db.models.TextField(null=True, blank=True)
#     phone_number = django.db.models.TextField(null=True, blank=True)
#     district = django.db.models.TextField(null=True, blank=True)
#     province = django.db.models.TextField(null=True, blank=True)
#     completed_order_date_time = django.db.models.DateTimeField(null=True, blank=True)
#     country = django.db.models.TextField(null=True, blank=True)
#     platform = django.db.models.TextField(null=True, blank=True)
#     brand = django.db.models.TextField(null=True, blank=True)
#     datetime_download_order = django.db.models.DateTimeField(null=True, blank=True)
#     set = django.db.models.TextField(null=True, blank=True)
#     gudang_pengiriman = django.db.models.TextField(null=True, blank=True)
#     gmv = django.db.models.BigIntegerField(null=True, blank=True)
#     delivery_option = django.db.models.TextField(null=True, blank=True)
#     order_type = django.db.models.TextField(null=True, blank=True)
#     product_id = django.db.models.TextField(null=True, blank=True)
#     postal_code = django.db.models.TextField(null=True, blank=True)
#     cancelreturninitiator = django.db.models.TextField(null=True, blank=True)
#     sku_code = django.db.models.TextField(null=True, blank=True)
#     delivered_time = django.db.models.DateTimeField(null=True, blank=True)
#     weight = django.db.models.TextField(null=True, blank=True)
#     campaign_name = django.db.models.TextField(null=True, blank=True)
#     campaign_type = django.db.models.TextField(null=True, blank=True)
#     payment_type = django.db.models.TextField(null=True, blank=True)
#     category = django.db.models.TextField(null=True, blank=True)
#     brand_group = django.db.models.TextField(null=True, blank=True)
#     is_nmv = django.db.models.BigIntegerField(null=True, blank=True)

#     class Meta:
#         managed = False
#         db_table = "postgre_order_mart_dwd_df"
        # indexes = [
        #     django.db.models.Index(fields=['order_number']),
        #     django.db.models.Index(fields=['create_order_date_time', 'brand', 'platform']),
        # ]
        # indexes = [models.Index(fields=['create_order_date_time', 'brand', 'platform'])]

class OrderMartDWDDF(django.db.models.Model):
    key_id = django.db.models.BigIntegerField(primary_key=True)
    create_order_date_time_date = django.db.models.DateField(blank=True,null=True)
    brand = django.db.models.TextField()
    brand_group = django.db.models.TextField()
    platform = django.db.models.TextField()
    total_nmv = django.db.models.BigIntegerField(null=True, blank=True)
    total_gmv = django.db.models.BigIntegerField(null=True, blank=True)
    net_orders = django.db.models.BigIntegerField(null=True, blank=True)
    gross_orders = django.db.models.BigIntegerField(null=True, blank=True)
    net_quantity = django.db.models.BigIntegerField(null=True, blank=True)
    gross_quantity = django.db.models.BigIntegerField(null=True, blank=True)
    platform_discount = django.db.models.BigIntegerField(null=True, blank=True)
    seller_discount = django.db.models.BigIntegerField(null=True, blank=True)
    total_seller_voucher = django.db.models.BigIntegerField(null=True, blank=True)
    total_platform_voucher = django.db.models.BigIntegerField(null=True, blank=True)
    page_view = django.db.models.BigIntegerField(null=True, blank=True)
    visitors = django.db.models.BigIntegerField(null=True, blank=True)

    class Meta:
        managed = False
        db_table = "order_mart_summary"