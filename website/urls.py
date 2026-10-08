from django.urls import path

from . import views

app_name = "website"

urlpatterns = [
    # dashboard
    path("dashboard/website/pages/", views.pages, name="pages"),
    path("dashboard/website/pages/new/", views.page_edit, name="page_new"),
    path("dashboard/website/pages/<int:pk>/", views.page_edit, name="page_edit"),
    path("dashboard/website/pages/<int:pk>/delete/", views.page_delete, name="page_delete"),
    path("dashboard/website/pages/<int:pk>/duplicate/", views.page_duplicate, name="page_duplicate"),
    path("dashboard/website/revision/<int:pk>/restore/", views.revision_restore, name="revision_restore"),
    path("dashboard/website/appearance/", views.appearance, name="appearance"),
    path("dashboard/website/footer/", views.footer_builder, name="footer"),
    path("dashboard/website/menus/", views.menus, name="menus"),
    path("dashboard/website/menus/<int:pk>/", views.menus, name="menu"),
    path("dashboard/website/brand/", views.brand, name="brand"),
    path("dashboard/website/seo/", views.seo, name="seo"),
    path("dashboard/website/media/", views.media, name="media"),
    path("dashboard/website/media/<int:pk>/delete/", views.media_delete, name="media_delete"),
    # public website
    path("book/slots/", views.booking_slots, name="booking_slots"),
    path("book/", views.book, name="book"),
    path("robots.txt", views.robots_txt, name="robots"),
    path("sitemap.xml", views.sitemap_xml, name="sitemap"),
    path("", views.home, name="home"),
    path("<slug:slug>/", views.page_view, name="page"),
]
