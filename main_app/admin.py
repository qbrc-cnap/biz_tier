from django.contrib import admin

from main_app.models import *

class ProductAdmin(admin.ModelAdmin):
    list_display = ('name','unit_cost','cnap_workflow_pk', 'is_quantity_limited', 'quantity')

class PaymentAdmin(admin.ModelAdmin):
    list_display = ('payment_type','number','payment_date','client','code', 'payment_amount')

class PendingUserAdmin(admin.ModelAdmin):
    list_display = ('is_pi','info_json')

class BaseUserAdmin(admin.ModelAdmin):
    list_display = ('email','first_name', 'last_name')

class ResearchGroupAdmin(admin.ModelAdmin):
    list_display = ('pi_name','pi_email','has_harvard_appointment')

admin.site.register(Product, ProductAdmin)
admin.site.register(Payment, PaymentAdmin)
admin.site.register(PendingUser, PendingUserAdmin)
admin.site.register(BaseUser, BaseUserAdmin)
admin.site.register(ResearchGroup, ResearchGroupAdmin)
