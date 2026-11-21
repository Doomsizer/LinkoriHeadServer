from django.urls import path

from .views import ProbeActiveConfigsView, ProbeNodesListView, ProbeReportView

urlpatterns = [
    # Общие маршруты (или определяют LTE/Wi-Fi автоматически по токену ProbeStand)
    path("nodes/", ProbeNodesListView.as_view(), name="probe-nodes"),
    path("report/", ProbeReportView.as_view(), name="probe-report"),
    path("configs/", ProbeActiveConfigsView.as_view(), name="probe-configs"),
    # Раздельные маршруты для LTE-стендов
    path("lte/nodes/", ProbeNodesListView.as_view(network_type="lte"), name="probe-lte-nodes"),
    path("lte/report/", ProbeReportView.as_view(network_type="lte"), name="probe-lte-report"),
    path("lte/configs/", ProbeActiveConfigsView.as_view(network_type="lte"), name="probe-lte-configs"),
    # Раздельные маршруты для Wi-Fi-стендов
    path("wifi/nodes/", ProbeNodesListView.as_view(network_type="wifi"), name="probe-wifi-nodes"),
    path("wifi/report/", ProbeReportView.as_view(network_type="wifi"), name="probe-wifi-report"),
    path("wifi/configs/", ProbeActiveConfigsView.as_view(network_type="wifi"), name="probe-wifi-configs"),
]