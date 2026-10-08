from django.urls import path

from . import views

app_name = "finance"

urlpatterns = [
    path("", views.overview, name="overview"),
    path("report/", views.report, name="report"),
    path("export/", views.export_csv, name="export"),
    path("expenses/", views.expenses, name="expenses"),
    path("expenses/new/", views.expense_edit, name="expense_new"),
    path("expenses/<int:pk>/", views.expense_edit, name="expense_edit"),
    path("expenses/<int:pk>/receipt/", views.receipt_file, name="receipt"),
]
