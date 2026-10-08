from django.urls import path

from . import views_cassa as cassa
from . import views_live as live
from . import views_manage as manage

app_name = "pos"

urlpatterns = [
    path("live/", live.live_state, name="live"),
    # waiter
    path("", live.tables, name="tables"),
    path("order/<int:table_id>/", live.order_screen, name="order"),
    path("order/<int:order_id>/submit/", live.order_submit, name="order_submit"),
    path("order/<int:order_id>/items/", live.items_action, name="items_action"),
    # bar & kitchen
    path("bar/", live.bar, name="bar"),
    path("kitchen/", live.kitchen, name="kitchen"),
    path("station/<str:station>/", live.station_action, name="station_action"),
    # manager / owner
    path("overview/", live.overview, name="overview"),
    path("floor/", live.floor, name="floor"),
    path("floor/design/", manage.floor_design, name="floor_design"),
    path("floor/save/", manage.floor_save, name="floor_save"),
    # cassa
    path("cassa/", cassa.cassa, name="cassa"),
    path("cassa/<int:order_id>/", cassa.cassa, name="cassa_order"),
    path("cassa/<int:order_id>/pay/", cassa.pay, name="pay"),
    path("cassa/<int:order_id>/proforma/", cassa.proforma, name="proforma"),
    path("cassa/<int:order_id>/void/", cassa.void_order, name="void_order"),
    path("cassa/day-close/", cassa.day_close, name="day_close"),
    path("day-closes/", cassa.day_closes, name="day_closes"),
    path("bill/<int:pk>/", cassa.bill_file, name="bill"),
    # history
    path("history/", cassa.history, name="history"),
    path("history/<int:pk>/", cassa.history_order, name="history_order"),
    # products
    path("products/", manage.products, name="products"),
    path("products/new/", manage.product_edit, name="product_new"),
    path("products/<int:pk>/", manage.product_edit, name="product_edit"),
    # reservations & customers
    path("reservations/", manage.reservations, name="reservations"),
    path("reservations/new/", manage.reservation_edit, name="reservation_new"),
    path("reservations/<int:pk>/", manage.reservation_edit, name="reservation_edit"),
    path("reservations/<int:pk>/status/", manage.reservation_status, name="reservation_status"),
    path("customers/", manage.customers, name="customers"),
    path("customers/new/", manage.customer_edit, name="customer_new"),
    path("customers/<int:pk>/", manage.customer_edit, name="customer"),
    path("customers/search/", manage.customer_search, name="customer_search"),
    path("performance/", manage.performance, name="performance"),
    # settings
    path("settings/", manage.pos_settings, name="settings"),
    path("settings/reservations/", manage.reservation_settings, name="reservation_settings"),
]
