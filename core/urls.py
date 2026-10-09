from django.urls import path

from . import views, views_app, views_demo

app_name = "core"

urlpatterns = [
    path("manifest.webmanifest", views_app.manifest, name="manifest"),
    path("sw.js", views_app.service_worker, name="service_worker"),
    path("app/", views_app.app_home, name="app"),
    path("app/offline/", views_app.offline, name="offline"),
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("media/public/<path:path>", views.public_media, name="public_media"),
    path("demo/", views_demo.landing, name="demo"),
    path("demo/site/", views_demo.site_home, name="demo_site"),
    path("demo/site/book/slots/", views_demo.site_slots, name="demo_site_slots"),
    path("demo/site/book/", views_demo.site_book, name="demo_site_book"),
    path("demo/site/<slug:slug>/", views_demo.site_page, name="demo_site_page"),
    path("demo/start/<str:role>/", views_demo.start, name="demo_start"),
    path("demo/code/", views_demo.resume, name="demo_resume"),
    path("demo/reset/", views_demo.reset, name="demo_reset"),
    path("demo/exit/", views_demo.exit_demo, name="demo_exit"),
    path("dashboard/demo/enter/", views_demo.enter, name="demo_enter"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("dashboard/home/", views.home, name="home"),
    path("dashboard/home/activity/", views.activity, name="activity"),
    path("dashboard/updates/", views.updates, name="updates"),
    path("dashboard/updates/apply/", views.update_apply, name="update_apply"),
    path("dashboard/updates/backup/<str:name>", views.backup_download, name="backup_download"),
    path("dashboard/notifications/", views.notifications, name="notifications"),
    path("dashboard/notifications/<int:pk>/", views.notification_open, name="notification_open"),
    path("dashboard/profile/", views.profile, name="profile"),
    path("dashboard/avatar/<int:pk>/", views.avatar, name="avatar"),
    path("dashboard/users/employees/", views.employees, name="employees"),
    path("dashboard/users/system/", views.users_system, name="users_system"),
    path("dashboard/users/staff/", views.users_staff, name="users_staff"),
    path("dashboard/users/<str:kind>/new/", views.user_edit, name="user_new"),
    path("dashboard/users/<str:kind>/<int:pk>/", views.user_edit, name="user_edit"),
    path("dashboard/users/<str:kind>/<int:pk>/action/", views.user_action, name="user_action"),
    path("dashboard/settings/", views.system_settings, name="settings"),
    path("dashboard/settings/backup/", views.backup_now, name="backup_now"),
]
