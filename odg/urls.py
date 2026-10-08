from django.urls import include, path

urlpatterns = [
    path("", include("core.urls")),
    path("dashboard/pos/", include("pos.urls")),
    path("dashboard/finance/", include("finance.urls")),
    # Website dashboard + the public website. The public part is last
    # because it owns "/" and "/<page-slug>/".
    path("", include("website.urls")),
]

handler403 = "core.views.forbidden"
handler404 = "website.views.not_found"
