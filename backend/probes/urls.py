from django.urls import path

from .views import ProbeActiveConfigsView, ProbeNodesListView, ProbeReportView

urlpatterns = [
    path("nodes/", ProbeNodesListView.as_view(), name="probe-nodes"),
    path("report/", ProbeReportView.as_view(), name="probe-report"),
    path("configs/", ProbeActiveConfigsView.as_view(), name="probe-configs"),
]